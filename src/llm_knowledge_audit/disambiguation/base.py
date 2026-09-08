from typing import Protocol

from ..models import Resolution, StringCandidate


class StringResolver(Protocol):
    def resolve(self, surface_form: str, candidates: list[StringCandidate]) -> Resolution: ...
