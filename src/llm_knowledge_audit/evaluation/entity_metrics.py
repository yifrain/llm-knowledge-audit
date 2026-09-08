import math
from collections import Counter
from itertools import combinations
from typing import Any

from ..models import EntityCase


def rate(numerator: int | float, denominator: int, ci: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }
    if ci and denominator:
        proportion = numerator / denominator
        z = 1.959963984540054
        scale = 1 + z * z / denominator
        center = (proportion + z * z / (2 * denominator)) / scale
        half = (
            z
            * math.sqrt(proportion * (1 - proportion) / denominator + z * z / (4 * denominator**2))
            / scale
        )
        result["wilson_95"] = [max(0.0, center - half), min(1.0, center + half)]
    return result


def candidate_metrics(
    cases: list[EntityCase], candidates: dict[str, Any], k: int
) -> dict[str, Any]:
    ranks = []
    for case in cases:
        ids = [c["entity_id"] for c in candidates[case.case_id]["candidates"][:k]]
        ranks.append(ids.index(case.gold_entity_id) + 1 if case.gold_entity_id in ids else None)
    return {
        "recall_at_k": rate(sum(r is not None for r in ranks), len(cases), True),
        "k": k,
        "mrr": rate(sum(1 / r for r in ranks if r is not None), len(cases)),
    }


def entity_metrics(cases: list[EntityCase], predictions: dict[str, Any]) -> dict[str, Any]:
    pred = {c.case_id: predictions[c.case_id]["selected_entity_id"] for c in cases}
    n = len(cases)
    correct = sum(pred[c.case_id] == c.gold_entity_id for c in cases)
    abstentions = sum(pred[c.case_id] is None for c in cases)
    homo = [
        (a, b)
        for a, b in combinations(cases, 2)
        if a.case_type == b.case_type == "homonym"
        and a.group_id == b.group_id
        and a.gold_entity_id != b.gold_entity_id
    ]
    syn = [
        (a, b)
        for a, b in combinations(cases, 2)
        if a.case_type == b.case_type == "synonym"
        and a.group_id == b.group_id
        and a.gold_entity_id == b.gold_entity_id
        and a.surface_form != b.surface_form
    ]

    def both_correct(a: EntityCase, b: EntityCase) -> bool:
        return bool(pred[a.case_id] == a.gold_entity_id and pred[b.case_id] == b.gold_entity_id)

    errors = Counter(c.domain for c in cases if pred[c.case_id] != c.gold_entity_id)
    counts = Counter(c.domain for c in cases)
    return {
        "top1_accuracy": rate(correct, n, True),
        "abstention_rate": rate(abstentions, n, True),
        "accuracy_when_answered": rate(correct, n - abstentions, True),
        "homonym_separation_accuracy": rate(sum(both_correct(a, b) for a, b in homo), len(homo)),
        "homonym_conflation_rate": rate(
            sum(
                pred[a.case_id] is not None and pred[a.case_id] == pred[b.case_id] for a, b in homo
            ),
            len(homo),
        ),
        "synonym_merge_accuracy": rate(sum(both_correct(a, b) for a, b in syn), len(syn)),
        "domain_errors": {d: rate(errors[d], count) for d, count in sorted(counts.items())},
    }
