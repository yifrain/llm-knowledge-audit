from pathlib import Path

import pytest

from llm_knowledge_audit.config import load_config
from llm_knowledge_audit.pipeline import Pipeline
from llm_knowledge_audit.storage import read_json

ROOT = Path(__file__).resolve().parents[2]


def config(tmp_path):
    cfg = load_config(ROOT / "configs/mock.yaml")
    cfg.results_dir = tmp_path / "results"
    cfg.cache_dir = tmp_path / "cache"
    return cfg


def test_offline_end_to_end_and_resume(tmp_path):
    cfg = config(tmp_path)
    first = Pipeline(cfg).execute()
    originals = {str(p.relative_to(first)): p.read_bytes() for p in first.rglob("*") if p.is_file()}
    second = Pipeline(cfg, resume=first).execute()
    assert first != second
    assert read_json(first / "judge.json") == read_json(second / "judge.json")
    assert originals == {
        str(p.relative_to(first)): p.read_bytes() for p in first.rglob("*") if p.is_file()
    }
    assert read_json(first / "evaluate.json")["judge_agreement"]["annotated_n"] == 0
    assert read_json(first / "evaluate.json")["operations_this_invocation"]["api_requests_n"] == 0


def test_reject_changed_resume(tmp_path):
    cfg = config(tmp_path)
    first = Pipeline(cfg).execute("collect-candidates")
    cfg.seed += 1
    with pytest.raises(ValueError, match="checksum changed"):
        Pipeline(cfg, resume=first)


def test_interruption_reuses_finished_items(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    interrupted = Pipeline(cfg)
    original = interrupted.item
    count = 0

    def stop(stage, key, compute):
        nonlocal count
        result = original(stage, key, compute)
        if stage == "generate":
            count += 1
            if count == 2:
                raise RuntimeError("simulated interruption")
        return result

    monkeypatch.setattr(interrupted, "item", stop)
    with pytest.raises(RuntimeError, match="interruption"):
        interrupted.execute()
    old_files = {
        str(p.relative_to(interrupted.path)): p.read_bytes()
        for p in interrupted.path.rglob("*")
        if p.is_file()
    }
    resumed = Pipeline(cfg, resume=interrupted.path)
    result = resumed.execute()
    assert read_json(result / "completion.json")["status"] == "completed"
    assert old_files == {
        str(p.relative_to(interrupted.path)): p.read_bytes()
        for p in interrupted.path.rglob("*")
        if p.is_file()
    }
    assert read_json(result / "evaluate.json")["factuality"]["attempted_n"] >= 100


def test_updated_annotations_recompute_only_evaluation(tmp_path):
    import json

    from llm_knowledge_audit.storage import read_jsonl

    cfg = config(tmp_path)
    cfg.annotations = tmp_path / "human.jsonl"
    cfg.annotations.write_text("")
    first = Pipeline(cfg).execute()
    item = read_jsonl(first / "annotations.template.jsonl")[0]
    # Explicitly synthetic TEST annotation, never written to repository data.
    item.update(
        human_label="not_enough_information",
        annotator_id="synthetic-test-annotator",
        annotated_at="2026-01-01T00:00:00Z",
    )
    cfg.annotations.write_text(json.dumps(item) + "\n")
    second = Pipeline(cfg, resume=first).execute()
    assert read_json(second / "evaluate.json")["annotation_coverage"]["numerator"] == 1
    assert read_json(second / "evaluate.json")["operations_this_invocation"]["api_requests_n"] == 0
    assert (second / "annotation_packet.json").exists()
    assert (second / "report.md").exists()


def test_annotation_packet_blinded_and_matches_judge_input(tmp_path):
    cfg = config(tmp_path)
    cfg.evidence_max_chars = 500
    run = Pipeline(cfg).execute()
    packet = read_json(run / "annotation_packet.json")
    judgments = read_json(run / "judge.json")
    for tid, row in packet.items():
        assert not {"judgment", "human_label", "confidence"} & row.keys()
        assert row["evidence"] == judgments[tid]["supplied_evidence"]


def test_cli_offline_and_gold_immutability(tmp_path):
    import yaml
    from typer.testing import CliRunner

    from llm_knowledge_audit.cli import app

    cfg = config(tmp_path)
    gold = cfg.dataset.read_bytes()
    configuration = tmp_path / "config.yaml"
    configuration.write_text(yaml.safe_dump(cfg.model_dump(mode="json")))
    result = CliRunner().invoke(app, ["run-all", "--config", str(configuration)])
    assert result.exit_code == 0, result.output
    assert cfg.dataset.read_bytes() == gold
    run = Path(result.output.strip())
    assert (run / "report.md").exists()
    assert CliRunner().invoke(app, ["plot", "--run-dir", str(run)]).exit_code != 0


def test_real_requires_human_review_before_any_paid_call(tmp_path):
    from llm_knowledge_audit.config import LLMConfig

    cfg = config(tmp_path)
    cfg.mode = "real"
    cfg.require_human_verified = True
    paid = LLMConfig(
        provider="openai_compatible",
        model="test",
        input_usd_per_million=1,
        output_usd_per_million=1,
    )
    cfg.generator = cfg.resolver = cfg.judge = paid
    pipeline = Pipeline(cfg, approved=True)
    with pytest.raises(ValueError, match="human verification"):
        pipeline.execute()
    assert pipeline.client.attempts == 0
