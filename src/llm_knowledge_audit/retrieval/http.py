"""Serial, rate-limited official API access with immutable response caching."""

from __future__ import annotations

import os
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from ..config import Config
from ..storage import Cache, digest, now


class RetrievalError(RuntimeError):
    pass


def retry_delay(value: str | None) -> float:
    if not value:
        return 0
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return 0


class PublicHTTP:
    def __init__(self, cfg: Config, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        self.cache = Cache(cfg.cache_dir / "public-http")
        self.raw = Cache(cfg.raw_dir / "http")
        self.transport = transport
        self.last_request = 0.0
        self.events: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        key = digest({"url": url, "params": params})
        cached = self.cache.get(key)
        if cached is not None:
            self.events.append(
                {
                    "cache_hit": True,
                    "attempts": 0,
                    "retries": 0,
                    "failure": False,
                    "latency_seconds": 0,
                }
            )
            result: dict[str, Any] = cached
            return result
        if self.cfg.offline:
            raise RetrievalError(f"Offline cache miss: {key}")
        event = {
            "cache_hit": False,
            "attempts": 0,
            "retries": 0,
            "failure": True,
            "latency_seconds": 0.0,
        }
        start = time.perf_counter()
        try:
            with httpx.Client(
                timeout=self.cfg.request_timeout,
                transport=self.transport,
                headers={
                    "User-Agent": os.environ.get(
                        "LLMKA_USER_AGENT",
                        "llm-knowledge-audit/0.1 (Yifan Li; TU Dresden research prototype)",
                    )
                },
                follow_redirects=True,
            ) as client:
                for attempt in range(self.cfg.max_attempts):
                    time.sleep(
                        max(0, self.cfg.request_interval - (time.monotonic() - self.last_request))
                    )
                    self.last_request = time.monotonic()
                    event["attempts"] += 1
                    retry_after = 0.0
                    try:
                        response = client.get(url, params=params)
                        retry_after = retry_delay(response.headers.get("Retry-After"))
                        if response.status_code in {408, 429, 500, 502, 503, 504}:
                            raise httpx.ReadTimeout("Transient HTTP failure")
                        if not response.is_success:
                            raise RetrievalError(f"Public API HTTP {response.status_code}")
                        data = response.json()
                        if not isinstance(data, dict):
                            raise RetrievalError("Expected a JSON object from public API")
                        if data.get("error", {}).get("code") in {
                            "maxlag",
                            "ratelimited",
                            "readonly",
                        }:
                            raise httpx.ReadTimeout("Transient MediaWiki failure")
                        if "error" in data:
                            raise RetrievalError("Non-transient public API error")
                        record = {
                            "data": data,
                            "source_url": str(response.url),
                            "retrieved_at": now(),
                            "response_sha256": digest(data),
                        }
                        self.raw.put(key, record)
                        self.cache.put(key, record)
                        event["failure"] = False
                        return record
                    except (httpx.TimeoutException, httpx.NetworkError) as exc:
                        if attempt + 1 == self.cfg.max_attempts:
                            raise RetrievalError("Public retrieval retries exhausted") from exc
                        event["retries"] += 1
                        time.sleep(max(2**attempt, retry_after))
                    except (httpx.HTTPError, ValueError) as exc:
                        raise RetrievalError("Invalid public API response") from exc
            raise AssertionError("unreachable")
        finally:
            event["latency_seconds"] = time.perf_counter() - start
            self.events.append(event)
