from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Response:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    usage_known: bool = True


class Provider(Protocol):
    def complete(
        self, task: str, system: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> Response: ...


class ProviderError(RuntimeError):
    """Sanitized failure; never includes credentials or raw HTTP headers."""


class ExecutionBlocked(Exception):
    """Approval, offline, or budget boundary: fatal, never a model classification."""
