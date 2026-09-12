"""Mock 证据检索器：生成与真实检索无关的合成证据（全程断网）。"""

import json
from datetime import UTC, datetime

from ..models import Evidence, Triple
from ..storage import digest


class MockEvidenceRetriever:
    def retrieve(self, entity_id: str, triple: Triple) -> list[Evidence]:
        """为任意三元组返回固定的合成证据段落。

        关键约束：证据内容来自独立的 fixture 事实，绝不根据生成的三元组
        "量身定制"证据——否则 mock 模式下的判定就失去了评测意义。
        """
        # Independent fixture facts; never infer evidence from the generated object.
        facts = [("demo_value", "alpha"), ("demo_flag", "on"), ("demo_class", "sample")]
        return [
            Evidence(
                # passage_id 由内容哈希决定：同一条证据在不同运行中 ID 稳定
                passage_id="mock-" + digest([entity_id, rel, obj])[:16],
                text=json.dumps({"subject": triple.subject, "predicate": rel, "object": obj}),
                # .invalid 是 RFC 保留域名，明确表明这是不可能真实访问的合成来源
                source_url="https://example.invalid/synthetic-fixture/" + entity_id,
                retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
                revision_id="fixture-v1",
                license="Synthetic fixture; MIT",
                synthetic=True,
            )
            for rel, obj in facts
        ]
