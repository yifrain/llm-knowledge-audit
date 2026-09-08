import json
from pathlib import Path
from typing import Any


def build_report(path: Path, metrics: dict[str, Any], mode: str) -> dict[str, Any]:
    kind = "MOCK / SYNTHETIC — not research findings" if mode == "mock" else "REAL EXPERIMENT"
    accuracy = metrics["entity"]
    lines = [
        f"# Run report: {kind}",
        "",
        f"Run: `{path.name}`",
        "",
        "## Entity resolution",
        "",
        "| Method | Correct / cases | Accuracy |",
        "|---|---:|---:|",
    ]
    for method, row in accuracy.items():
        score = row["top1_accuracy"]
        value = f"{score['value']:.3f}" if score["value"] is not None else "N/A"
        lines.append(f"| {method} | {score['numerator']} / {score['denominator']} | {value} |")
    coverage = metrics["annotation_coverage"]
    lines += [
        "",
        "## Human evaluation",
        "",
        f"Reviewed annotations: {coverage['numerator']} / {coverage['denominator']} triples.",
        "Missing human evaluation is unavailable, never inferred from model or fixture labels.",
        "",
        "## Error analysis",
        "",
        "Automatic flags are review leads; they do not establish causal explanations.",
        "",
    ]
    for category, row in metrics["error_analysis"]["categories"].items():
        lines += [
            f"### {category}",
            "",
            f"Status: {row['status']}; flags: {row['flagged_count']}.",
            "",
        ]
        for example in row["examples"][:3]:
            lines += ["```json", json.dumps(example, indent=2), "```", ""]
    lines += [
        "## Full metrics",
        "",
        "All denominators and evidence-linked disagreements are in "
        "[evaluate.json](evaluate.json). Costs describe this invocation; reused artifacts "
        "retain their original provenance in the parent run.",
        "",
        "## Limitations",
        "",
        "Human review is required before claiming benchmark validity. "
        "Mock accuracy and zero mock latency/cost do not predict real LLM performance. "
        "Pair observations are dependent; Wilson case intervals are descriptive only. "
        "No empirical plots are produced from mock results.",
        "",
    ]
    with (path / "report.md").open("x") as handle:
        handle.write("\n".join(lines))
    return {"report": "report.md", "metrics": "evaluate.json", "mode": mode}
