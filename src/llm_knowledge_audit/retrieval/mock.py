import json
from datetime import UTC, datetime

from ..models import Evidence, Triple
from ..storage import digest


class MockEvidenceRetriever:
    def retrieve(self, entity_id: str, triple: Triple) -> list[Evidence]:
        # Independent fixture facts; never infer evidence from the generated object.
        facts = [("demo_value", "alpha"), ("demo_flag", "on"), ("demo_class", "sample")]
        return [
            Evidence(
                passage_id="mock-" + digest([entity_id, rel, obj])[:16],
                text=json.dumps({"subject": triple.subject, "predicate": rel, "object": obj}),
                source_url="https://example.invalid/synthetic-fixture/" + entity_id,
                retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
                revision_id="fixture-v1",
                license="Synthetic fixture; MIT",
                synthetic=True,
            )
            for rel, obj in facts
        ]
