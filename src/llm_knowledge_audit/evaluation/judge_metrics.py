from collections import Counter
from typing import Any

from .entity_metrics import rate

LABELS = ["entailed", "contradicted", "not_enough_information"]


def agreement(gold: list[str], predicted: list[str | None]) -> dict[str, Any]:
    if len(gold) != len(predicted) or any(x not in LABELS for x in gold):
        raise ValueError("Aligned supported gold labels are required")
    if any(x not in [*LABELS, None] for x in predicted):
        raise ValueError("Unsupported prediction label")
    complete = [(g, p) for g, p in zip(gold, predicted, strict=True) if p is not None]
    n = len(complete)
    matrix = [[sum(g == a and p == b for g, p in complete) for b in LABELS] for a in LABELS]
    accuracy = sum(g == p for g, p in complete)
    by_label = {}
    ps, rs, fs = [], [], []
    for index, label in enumerate(LABELS):
        tp = matrix[index][index]
        support = sum(matrix[index])
        predicted_count = sum(row[index] for row in matrix)
        precision = tp / predicted_count if predicted_count else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        ps.append(precision)
        rs.append(recall)
        fs.append(f1)
        by_label[label] = {
            "precision": rate(tp, predicted_count),
            "recall": rate(tp, support),
            "f1": {
                "value": f1 if n else None,
                "support": support,
                "predicted_count": predicted_count,
            },
        }
    gc = Counter(g for g, _ in complete)
    pc = Counter(p for _, p in complete)
    expected = sum(gc[x] * pc[x] for x in LABELS) / n**2 if n else None
    kappa = (
        (accuracy / n - expected) / (1 - expected)
        if n and expected is not None and expected < 1
        else None
    )
    return {
        "annotated_n": len(gold),
        "prediction_coverage": rate(n, len(gold)),
        "accuracy": rate(accuracy, n, True),
        "accuracy_including_failures": rate(accuracy, len(gold), True),
        "macro_precision": {"value": sum(ps) / 3 if n else None, "n": n, "labels": 3},
        "macro_recall": {"value": sum(rs) / 3 if n else None, "n": n, "labels": 3},
        "macro_f1": {"value": sum(fs) / 3 if n else None, "n": n, "labels": 3},
        "confusion_matrix": {"rows": LABELS, "columns": LABELS, "counts": matrix, "n": n},
        "cohens_kappa": {"value": kappa, "n": n},
        "by_label": by_label,
        "zero_division": "Macro averages use zero for undefined label scores when n>0",
    }


def factuality(labels: list[str | None]) -> dict[str, Any]:
    counts = Counter(labels)
    valid = sum(counts[label] for label in LABELS)
    decisive = counts["entailed"] + counts["contradicted"]
    return {
        "attempted_n": len(labels),
        "valid_label_coverage": rate(valid, len(labels)),
        "proportions": {label: rate(counts[label], valid, True) for label in LABELS},
        "strict_precision": rate(counts["entailed"], len(labels), True),
        "decisive_precision": rate(counts["entailed"], decisive, True),
    }
