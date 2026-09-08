from collections import Counter
from pathlib import Path
from typing import Any

from ..models import EntityCase
from ..storage import read_jsonl


def load_cases(path: Path, require_verified: bool = False) -> list[EntityCase]:
    cases = [EntityCase.model_validate(row) for row in read_jsonl(path)]
    if not cases or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("Cases must be nonempty and IDs unique")
    if require_verified and any(c.verification_status != "human_verified" for c in cases):
        raise ValueError("Dataset includes records awaiting human verification")
    return cases


def summary(cases: list[EntityCase]) -> dict[str, Any]:
    return {
        "n": len(cases),
        "types": dict(Counter(c.case_type for c in cases)),
        "domains": dict(Counter(c.domain for c in cases)),
        "human_verified": sum(c.verification_status == "human_verified" for c in cases),
        "pending_human_review": sum(c.verification_status != "human_verified" for c in cases),
    }
