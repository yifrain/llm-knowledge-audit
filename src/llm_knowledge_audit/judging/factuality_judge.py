from ..config import LLMConfig
from ..models import Evidence, Judgment, Triple
from ..providers.base import Provider
from ..providers.client import CallClient
from .prompts import SYSTEM, VERSION


def prepare_evidence(passages: list[Evidence], max_chars: int) -> list[Evidence]:
    seen_ids: set[str] = set()
    seen_text: set[str] = set()
    selected = []
    used = 0
    for passage in passages:
        text = " ".join(passage.text.split())
        if passage.passage_id in seen_ids or text in seen_text:
            continue
        seen_ids.add(passage.passage_id)
        seen_text.add(text)
        # Do not cut a passage mid-sentence and accidentally remove a negation.
        size = len(passage.model_dump_json())
        if used + size > max_chars:
            continue
        selected.append(passage)
        used += size
    return selected


def judge(
    triple: Triple,
    passages: list[Evidence],
    client: CallClient,
    provider: Provider,
    model: LLMConfig,
    max_chars: int,
) -> tuple[Judgment, list[Evidence]]:
    supplied = prepare_evidence(passages, max_chars)
    if not supplied:
        return Judgment(
            label="not_enough_information",
            confidence=0,
            evidence_ids=[],
            short_rationale="No usable retrieved evidence.",
        ), []
    result = client.call(
        provider,
        model,
        "judge",
        VERSION,
        SYSTEM,
        {
            "triple": triple.model_dump(),
            "evidence": [p.model_dump(mode="json") for p in supplied],
            "omitted_passages": len(passages) - len(supplied),
        },
        Judgment,
    )
    ids = {p.passage_id for p in supplied}
    if not set(result.evidence_ids) <= ids:
        raise ValueError("Judge cited unsupplied evidence")
    if result.label != "not_enough_information" and not result.evidence_ids:
        raise ValueError("Decisive label requires evidence citations")
    return result, supplied
