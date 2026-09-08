"""Cache validated outputs and retain telemetry for every attempted logical call."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, TypeVar

from pydantic import BaseModel

from ..config import Config, LLMConfig
from ..storage import Cache, digest, now
from .base import ExecutionBlocked, Provider, ProviderError

T = TypeVar("T", bound=BaseModel)


class CallClient:
    def __init__(self, cfg: Config, approved: bool = False):
        self.cfg = cfg
        self.approved = approved
        self.cache = Cache(cfg.cache_dir / "llm")
        self.events: list[dict[str, Any]] = []
        self.reserved_usd = 0.0
        self.attempts = 0
        self.reservation_dir = cfg.raw_dir / "reservations"

    def call(
        self,
        provider: Provider,
        model: LLMConfig,
        task: str,
        version: str,
        system: str,
        payload: dict[str, Any],
        output: type[T],
    ) -> T:
        request = {
            "model": model.model_dump(),
            "task": task,
            "version": version,
            "system": system,
            "payload": payload,
            "schema": output.model_json_schema(),
            "seed": self.cfg.seed,
        }
        key = digest(request)
        cached = self.cache.get(key)
        event: dict[str, Any] = {
            "task": task,
            "model": model.model,
            "provider": model.provider,
            "cache_key": key,
            "timestamp": now(),
            "cache_hit": False,
            "latency_seconds": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_usd": 0.0,
            "attempts": 0,
            "retries": 0,
            "schema_valid": False,
            "failure": None,
            "usage_known": True,
        }
        if cached is not None:
            result = output.model_validate(cached["result"])
            event.update(cache_hit=True, schema_valid=True)
            self.events.append(event)
            return result
        paid = model.provider != "mock"
        if paid and (self.cfg.offline or not self.approved):
            raise ExecutionBlocked("Uncached paid call requires online mode and --approve-paid")
        # UTF-8 byte count is a conservative input-token reservation, not a tokenizer estimate.
        upper_tokens = len(json.dumps(request, ensure_ascii=False).encode("utf-8")) + 4096
        per_attempt = (
            upper_tokens * model.input_usd_per_million
            + model.max_output_tokens * model.output_usd_per_million
        ) / 1_000_000
        start = time.perf_counter()
        try:
            for attempt in range(self.cfg.max_attempts):
                if paid:
                    if self.attempts >= self.cfg.max_calls:
                        raise ExecutionBlocked("Configured API call ceiling reached")
                    if self.reserved_usd + per_attempt > self.cfg.budget_usd:
                        raise ExecutionBlocked(
                            "Conservative budget reservation exceeds configured cap"
                        )
                    self.reserved_usd += per_attempt
                    self.attempts += 1
                    from ..storage import write_new

                    write_new(
                        self.reservation_dir / f"{uuid.uuid4().hex}.json",
                        {
                            "task": task,
                            "reserved_usd": per_attempt,
                            "attempts": 1,
                            "cache_key": key,
                            "timestamp": now(),
                        },
                    )
                event["attempts"] += 1
                try:
                    response = provider.complete(task, system, payload, output.model_json_schema())
                    event.update(
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        usage_known=response.usage_known,
                    )
                    event["estimated_usd"] += (
                        (
                            response.input_tokens * model.input_usd_per_million
                            + response.output_tokens * model.output_usd_per_million
                        )
                        / 1_000_000
                        if response.usage_known
                        else per_attempt
                    )
                    Cache(self.cfg.raw_dir / "llm").put(
                        digest([key, uuid.uuid4().hex]),
                        {
                            "request": request,
                            "content": response.content,
                            "created_at": now(),
                            "input_tokens": response.input_tokens,
                            "output_tokens": response.output_tokens,
                        },
                    )
                    event["response_received"] = True
                    try:
                        json.loads(response.content)
                        event["json_valid"] = True
                    except ValueError:
                        event["json_valid"] = False
                    result = output.model_validate_json(response.content)
                    event["schema_valid"] = True
                    self.cache.put(
                        key,
                        {
                            "result": result.model_dump(mode="json"),
                            "raw_content": response.content,
                            "request": request,
                            "created_at": now(),
                        },
                    )
                    return result
                except TransientProviderError as exc:
                    event["estimated_usd"] += per_attempt
                    event["usage_known"] = False
                    if attempt + 1 == self.cfg.max_attempts:
                        raise ProviderError("Transient API failure exhausted retries") from exc
                    event["retries"] += 1
                    time.sleep(max(2**attempt, exc.retry_after))
            raise AssertionError("unreachable")
        except Exception as exc:
            event["failure"] = type(exc).__name__
            if paid and event["attempts"] and not event.get("response_received"):
                event["usage_known"] = False
                event["estimated_usd"] = max(
                    event["estimated_usd"], per_attempt * event["attempts"]
                )
            raise
        finally:
            event["latency_seconds"] = 0.0 if not paid else time.perf_counter() - start
            event["reserved_usd"] = per_attempt * event["attempts"] if paid else 0
            self.events.append(event)


class TransientProviderError(ProviderError):
    def __init__(self, retry_after: float = 0):
        super().__init__("Transient provider failure")
        self.retry_after = retry_after
