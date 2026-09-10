from pathlib import Path
from typing import Annotated

import typer

from .config import load_config
from .dataset.validate_cases import load_cases, summary
from .pipeline import Pipeline

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
ConfigOption = Annotated[Path, typer.Option("--config", exists=True)]
ResumeOption = Annotated[Path | None, typer.Option("--resume", exists=True)]


@app.command("validate-data")
def validate_data(config: ConfigOption = Path("configs/mock.yaml")) -> None:
    cfg = load_config(config)
    typer.echo(summary(load_cases(cfg.dataset, cfg.require_human_verified)))


def run(stage: str, config: Path, resume: Path | None, approve_paid: bool) -> None:
    pipeline = Pipeline(load_config(config), resume, approve_paid)
    typer.echo(pipeline.execute(stage))


@app.command("run-all")
def run_all(
    config: ConfigOption = Path("configs/mock.yaml"),
    resume: ResumeOption = None,
    approve_paid: bool = False,
) -> None:
    run("build-report", config, resume, approve_paid)


@app.command("disambiguate")
def disambiguate(
    method: str = "string",
    config: ConfigOption = Path("configs/mock.yaml"),
    resume: ResumeOption = None,
    approve_paid: bool = False,
) -> None:
    if method not in {"string", "context"}:
        raise typer.BadParameter("method must be string or context")
    run("disambiguate-" + method, config, resume, approve_paid)


def register_stage(stage: str) -> None:
    def command(
        config: ConfigOption = Path("configs/mock.yaml"),
        resume: ResumeOption = None,
        approve_paid: bool = False,
    ) -> None:
        run(stage, config, resume, approve_paid)

    command.__doc__ = f"Execute {stage} and missing prerequisites in a new run."
    app.command(stage)(command)


for _stage in [
    "collect-candidates",
    "generate-triples",
    "retrieve-evidence",
    "judge",
    "evaluate",
    "build-report",
]:
    register_stage(_stage)


@app.command("plot")
def plot(run_dir: Annotated[Path, typer.Option(exists=True)]) -> None:
    """Write real-run figures to a fresh export directory; never modify the source run."""
    import uuid

    from .reporting.plots import plot_results
    from .storage import read_json

    metrics = read_json(run_dir / "evaluate.json")
    if metrics["mode"] != "real":
        raise typer.BadParameter("No empirical plots for mock runs")
    output = run_dir.parent / ("figures-" + uuid.uuid4().hex[:12])
    output.mkdir(exist_ok=False)
    typer.echo(plot_results(output, metrics))


@app.command("pilot-plan")
def pilot_plan(config: ConfigOption = Path("configs/pilot.yaml")) -> None:
    """No network or LLM calls; show the exact configured pilot and conservative call bound."""
    cfg = load_config(config)
    cases = load_cases(cfg.dataset)[: cfg.case_limit]
    n = len(cases)
    typer.echo(
        {
            "cases": [c.case_id for c in cases],
            "pending_review": sum(c.verification_status != "human_verified" for c in cases),
            "models": {
                role: getattr(cfg, role).model for role in ("resolver", "generator", "judge")
            },
            "max_unique_seeds": 2 * n,
            "max_logical_calls": n + 2 * n * (1 + cfg.triples_per_entity),
            "max_http_attempts": cfg.max_calls,
            "budget_cap_usd": cfg.budget_usd,
            "approval": "Required before any uncached model request",
        }
    )


@app.command("ui")
def ui(root: Path = Path("."), port: int = 8765, open_browser: bool = False) -> None:
    """打开中文本地工作台：流程、结果和轻量人工复核，无付费调用。"""
    from .workbench.server import serve

    serve(root.resolve(), port, open_browser)
