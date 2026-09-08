"""Scientific plots from measured real runs only; no mock figures."""

from pathlib import Path
from typing import Any

from ..storage import write_new


def plot_results(path: Path, metrics: dict[str, Any]) -> list[str]:
    if metrics["mode"] != "real":
        raise ValueError("Empirical figures require a real run")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory = path / "figures"
    directory.mkdir(exist_ok=False)
    plt.rcParams.update({"font.size": 11, "figure.dpi": 150, "font.family": "DejaVu Sans"})
    outputs = []

    def save(fig: Any, name: str, data: Any) -> None:
        fig.tight_layout()
        fig.savefig(directory / f"{name}.png", metadata={"Software": "llm-knowledge-audit"})
        plt.close(fig)
        write_new(directory / f"{name}.json", data)
        outputs.append(f"figures/{name}.png")

    methods = list(metrics["entity"])
    scores = [metrics["entity"][m]["top1_accuracy"] for m in methods]
    if all(s["value"] is not None for s in scores):
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(methods, [s["value"] for s in scores], color=["#687d91", "#186c64"])
        ax.set(
            xlabel="Disambiguation method",
            ylabel="Top-1 accuracy",
            ylim=(0, 1),
            title="Entity disambiguation (n=" + str(scores[0]["denominator"]) + " cases)",
        )
        save(fig, "accuracy", dict(zip(methods, scores, strict=True)))
    cm = metrics["judge_agreement"]["confusion_matrix"]
    if cm["n"]:
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.imshow(cm["counts"], cmap="Blues")
        ax.set(
            xticks=range(3),
            yticks=range(3),
            xticklabels=["Entailed", "Contradicted", "NEI"],
            yticklabels=["Entailed", "Contradicted", "NEI"],
            xlabel="Judge label",
            ylabel="Human label",
            title=f"Judge agreement (n={cm['n']} reviewed triples)",
        )
        for i in range(3):
            for j in range(3):
                ax.text(j, i, str(cm["counts"][i][j]), ha="center", va="center")
        save(fig, "judge_confusion", cm)
    analysis = metrics["error_analysis"]
    flags = {k: v["flagged_count"] for k, v in analysis["categories"].items()}
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(list(flags), list(flags.values()), color="#9b6c45")
    ax.set(
        xlabel="Automatically flagged records (categories overlap)",
        ylabel="Review category",
        title=(
            f"Error review flags ({analysis['entity_case_n']} cases; "
            f"{analysis['triple_n']} triples)"
        ),
    )
    save(fig, "error_categories", analysis)
    ops = metrics["operations_by_task"]["resolve"]
    if ops["api_requests_n"]:
        fig, ax = plt.subplots(figsize=(6, 4))
        cost = ops["estimated_usd"]["total"]
        ax.scatter([0, cost], [s["value"] for s in scores], color=["#687d91", "#186c64"])
        for m, x, s in zip(methods, [0, cost], scores, strict=True):
            ax.annotate(m, (x, s["value"]), xytext=(4, 4), textcoords="offset points")
        ax.set(
            xlabel="Incremental resolver API cost this invocation (USD)",
            ylabel="Top-1 accuracy",
            ylim=(0, 1.05),
            title=f"Cost vs accuracy (n={scores[0]['denominator']} cases)",
        )
        save(fig, "cost_accuracy", {"scores": scores, "operations": ops})
    return outputs
