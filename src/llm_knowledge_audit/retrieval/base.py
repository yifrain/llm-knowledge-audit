from typing import Protocol

from ..models import Evidence, Triple


class EvidenceRetriever(Protocol):
    def retrieve(self, entity_id: str, triple: Triple) -> list[Evidence]: ...
