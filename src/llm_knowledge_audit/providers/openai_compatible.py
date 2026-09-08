"""Minimal Chat Completions JSON-schema adapter; no SDK or implicit retries."""

import os
from typing import Any

import httpx

from ..config import Config, LLMConfig
from ..retrieval.http import retry_delay
from .base import ProviderError, Response
from .client import TransientProviderError


class OpenAICompatible:
    def __init__(
        self, model: LLMConfig, config: Config, transport: httpx.BaseTransport | None = None
    ):
        self.model, self.config, self.transport = model, config, transport

    def complete(
        self, task: str, system: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> Response:
        import json

        key = os.environ.get(self.model.api_key_env)
        if not key:
            raise ProviderError(f"Missing environment variable {self.model.api_key_env}")
        if not self.model.base_url.startswith("https://"):
            raise ProviderError("Remote provider endpoint must use HTTPS")
        body: dict[str, Any] = {
            "model": self.model.model,
            "temperature": self.model.temperature,
            "max_tokens": self.model.max_output_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": task, "strict": True, "schema": schema},
            },
        }
        if self.model.send_seed:
            body["seed"] = self.config.seed
        try:
            with httpx.Client(
                timeout=self.config.request_timeout,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    self.model.base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + key},
                    json=body,
                )
            if response.status_code in {408, 429, 500, 502, 503, 504}:
                raise TransientProviderError(retry_delay(response.headers.get("Retry-After")))
            if not response.is_success:
                raise ProviderError(
                    f"Provider HTTP {response.status_code}; response body suppressed"
                )
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            if message.get("refusal"):
                raise ProviderError("Judge/generator refused the request")
            if choice.get("finish_reason") != "stop":
                raise ProviderError("Provider output incomplete or filtered")
            if not isinstance(message.get("content"), str):
                raise ProviderError("Provider returned no text content")
            usage = data.get("usage") or {}
            known = "prompt_tokens" in usage and "completion_tokens" in usage
            return Response(
                message["content"],
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
                known,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TransientProviderError() from exc
        except (KeyError, ValueError, IndexError, TypeError) as exc:
            raise ProviderError("Malformed provider response envelope") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Provider transport failed") from exc
