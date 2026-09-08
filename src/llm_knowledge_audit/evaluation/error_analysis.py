from typing import Any

from ..models import EntityCase

CATEGORIES = [
    "same_label_wrong_sense",
    "synonyms_not_merged",
    "distinct_entities_merged",
    "candidate_retrieval_failure",
    "insufficient_context",
    "generic_description",
    "hallucinated_relation",
    "temporal_mismatch",
    "evidence_retrieval_failure",
    "judge_false_positive",
    "judge_false_negative",
    "judge_overuse_nei",
    "invalid_structured_output",
]


def errors(
    cases: list[EntityCase],
    candidates: dict[str, Any],
    predictions: dict[str, Any],
    judgments: dict[str, Any],
    human: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    output: dict[str, Any] = {
        category: {"examples": [], "status": "requires_human_error_review"}
        for category in CATEGORIES
    }

    def add(category: str, example: dict[str, Any]) -> None:
        output[category]["examples"].append(example)
        output[category]["status"] = "automatically_flagged_for_review"

    for case in cases:
        ids = [c["entity_id"] for c in candidates[case.case_id]["candidates"]]
        if case.gold_entity_id not in ids:
            add(
                "candidate_retrieval_failure",
                {"case_id": case.case_id, "gold": case.gold_entity_id},
            )
        for method, rows in predictions.items():
            row = rows[case.case_id]
            if row["status"] == "failed":
                add(
                    "invalid_structured_output",
                    {"case_id": case.case_id, "method": method, "failure_type": row.get("error")},
                )
            if row["selected_entity_id"] not in {None, case.gold_entity_id}:
                add(
                    "same_label_wrong_sense",
                    {
                        "case_id": case.case_id,
                        "method": method,
                        "predicted": row["selected_entity_id"],
                        "gold": case.gold_entity_id,
                    },
                )
    for method, rows in predictions.items():
        for i, a in enumerate(cases):
            for b in cases[i + 1 :]:
                if a.group_id != b.group_id:
                    continue
                pa, pb = (
                    rows[a.case_id]["selected_entity_id"],
                    rows[b.case_id]["selected_entity_id"],
                )
                example = {
                    "case_ids": [a.case_id, b.case_id],
                    "method": method,
                    "predictions": [pa, pb],
                }
                if a.gold_entity_id != b.gold_entity_id and pa is not None and pa == pb:
                    add("distinct_entities_merged", example)
                if a.case_type == b.case_type == "synonym" and a.gold_entity_id == b.gold_entity_id:
                    if pa is None or pb is None or pa != pb:
                        add("synonyms_not_merged", example)
    for tid, row in judgments.items():
        if evidence[tid]["status"] == "failed":
            add("evidence_retrieval_failure", {"triple_id": tid})
        if row["status"] == "failed":
            add("invalid_structured_output", {"triple_id": tid, "failure_type": row.get("error")})
        if tid not in human or not row["judgment"]:
            continue
        gold, predicted = human[tid]["human_label"], row["judgment"]["label"]
        example = {"triple_id": tid, "triple": row["triple"], "human": gold, "judge": predicted}
        if predicted == "entailed" and gold != "entailed":
            add("judge_false_positive", example)
        if gold == "entailed" and predicted != "entailed":
            add("judge_false_negative", example)
        if predicted == "not_enough_information" and gold != predicted:
            add("judge_overuse_nei", example)
    for group in output.values():
        group["flagged_count"] = len(group["examples"])
        # No automatic flag does not mean no errors: causes need review.
    return {
        "categories": output,
        "entity_case_n": len(cases),
        "triple_n": len(judgments),
        "human_annotation_n": len(human),
        "note": "Flags overlap; causal categories need review.",
    }
