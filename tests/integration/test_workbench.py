"""All review mutations happen in temporary fixtures, never in the real benchmark."""

import errno
import json
import shutil
from pathlib import Path

import pytest

from llm_knowledge_audit.storage import digest, read_json, read_jsonl
from llm_knowledge_audit.workbench import server as server_module
from llm_knowledge_audit.workbench.server import serve
from llm_knowledge_audit.workbench.service import Workbench

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workbench(tmp_path):
    for name in ["configs", "data/benchmark", "tests/fixtures"]:
        shutil.copytree(ROOT / name, tmp_path / name)
    (tmp_path / "data/annotations").mkdir(parents=True)
    (tmp_path / "data/annotations/human_annotations.jsonl").write_text("")
    return Workbench(tmp_path)


def test_small_scope_balanced_and_contains_pilot(workbench):
    small = workbench.case_queue("starter")["rows"]
    pilot = workbench.case_queue("pilot")["rows"]
    assert len(small) == 12
    assert sum(c["case_type"] == "homonym" for c in small) == 6
    assert sum(c["case_type"] == "synonym" for c in small) == 6
    assert {r["case_id"] for r in pilot} <= {r["case_id"] for r in small}


def test_case_confirmation_requires_explicit_human_action(workbench):
    row = workbench.case_queue("pilot")["rows"][0]
    payload = dict(
        scope="pilot",
        case_id=row["case_id"],
        revision=row["revision"],
        reviewer="TEST ONLY",
        confirmed=False,
    )
    with pytest.raises(ValueError, match="确认"):
        workbench.verify_case(payload)
    assert workbench.case_queue("pilot")["reviewed"] == 0


def test_review_sync_and_stale_write_preserve_original_pool(workbench):
    pool = workbench.root / "data/benchmark/entity_cases.jsonl"
    before = pool.read_bytes()
    row = workbench.case_queue("pilot")["rows"][0]
    payload = dict(
        scope="pilot",
        case_id=row["case_id"],
        revision=row["revision"],
        reviewer="SYNTHETIC TEST REVIEWER",
        confirmed=True,
    )
    output = workbench.verify_case(payload)
    assert len(output["saved"]) == 2
    assert workbench.case_queue("pilot")["reviewed"] == 1
    assert workbench.case_queue("starter")["reviewed"] == 1
    assert pool.read_bytes() == before
    with pytest.raises(ValueError, match="变化"):
        workbench.verify_case(payload)
    assert len(list((workbench.root / "data/reviews/entity_history").glob("*.json"))) == 2


def test_mock_trace_snapshots_and_fixed_blind_sample(workbench):
    run = workbench.demo()["run"]
    data = workbench.overview(run)
    assert len(data["cases"]) == 12
    assert data["metrics"]["mode"] == "mock"
    trace = workbench.trace(run, "homonym_001")
    assert trace["claims"]
    review = workbench.review(run)
    assert review["sample_size"] == 20
    assert review == workbench.review(run)
    assert "judgment" not in json.dumps(review)
    assert review["completed"] == 0
    assert len(workbench.runs()) == 1
    snapshot = read_json(workbench.run_path(run) / "cases.json")
    assert data["cases"] == snapshot
    with pytest.raises(ValueError, match="演示数据"):
        workbench.annotate(run, {})


def test_draft_updates_do_not_change_run_case_snapshot(workbench):
    run = workbench.demo()["run"]
    before = workbench.overview(run)["cases"]
    row = workbench.case_queue("pilot")["rows"][0]
    workbench.verify_case(
        dict(
            scope="pilot",
            case_id=row["case_id"],
            revision=row["revision"],
            reviewer="TEST REVIEWER",
            confirmed=True,
        )
    )
    assert workbench.overview(run)["cases"] == before


@pytest.mark.parametrize(
    "run", ["../../README.md", "real/../../../secret", "mock/a/b", "/tmp/test"]
)
def test_paths_are_bounded(workbench, run):
    with pytest.raises(ValueError):
        workbench.run_path(run)


def test_annotation_validated_blind_saved_and_compared(workbench):
    # Build a synthetic saved-real fixture ONLY under tmp_path; never claim it as an experiment.
    mock = workbench.demo()["run"]
    run = "real/test-fixture"
    target = workbench.root / "results" / run
    shutil.copytree(workbench.run_path(mock), target)
    manifest = read_json(target / "manifest.json")
    manifest["mode"] = "real"
    (target / "manifest.json").write_text(json.dumps(manifest))
    before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    review = workbench.review(run)
    row = review["rows"][0]
    body = dict(
        triple_id=row["triple_id"],
        human_label="entailed",
        annotator_id="TEST ONLY",
        annotator_notes="Synthetic test; not a human research annotation.",
        evidence_ids=["bad"],
    )
    with pytest.raises(ValueError, match="证据"):
        workbench.annotate(run, body)
    body["evidence_ids"] = [row["evidence"][0]["passage_id"]]
    workbench.annotate(run, body)
    assert workbench.review(run)["completed"] == 1
    assert workbench.comparison(run)["metrics"]["annotated_n"] == 1
    saved = read_jsonl(workbench.annotation_path(run))[0]
    assert saved["evidence_sha256"] == digest(row["evidence"])
    assert "judgment" not in json.dumps(workbench.review(run))
    # Editing a review replaces its active label, while keeping history (no duplicate count).
    body["human_label"] = "not_enough_information"
    workbench.annotate(run, body)
    assert len(workbench.annotations(run)) == 1
    assert before == {
        str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()
    }


def test_ui_cannot_run_paid_by_changed_learning_config(workbench):
    import yaml

    config = workbench.root / "configs/learn.yaml"
    value = yaml.safe_load(config.read_text())
    value["offline"] = False
    config.write_text(yaml.safe_dump(value))
    with pytest.raises(ValueError, match="离线演示"):
        workbench.demo()


class _RaisingHTTPServer:
    """模拟"端口被占用"的绑定失败（测试全程断网，不创建真实 socket）。"""

    def __init__(self, address, handler):
        raise OSError(errno.EADDRINUSE, "Address already in use")


class _FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.data


def test_probe_recognises_only_workbench_response(monkeypatch):
    urlopen = server_module.urllib.request.urlopen
    monkeypatch.setattr(
        server_module.urllib.request, "urlopen", lambda url, timeout: _FakeResponse(b'{"runs": [], "token": "x"}')
    )
    assert server_module._is_workbench_running(8765)
    monkeypatch.setattr(
        server_module.urllib.request, "urlopen", lambda url, timeout: _FakeResponse(b"hello")
    )
    assert not server_module._is_workbench_running(8765)

    def refused(url, timeout):
        raise OSError("Connection refused")

    monkeypatch.setattr(server_module.urllib.request, "urlopen", refused)
    assert not server_module._is_workbench_running(8765)
    monkeypatch.setattr(server_module.urllib.request, "urlopen", urlopen)


def test_serve_reuses_running_instance(workbench, capsys, monkeypatch):
    # 端口被占用但探测到本工作台实例：应提示复用、打开浏览器，而不是崩溃
    monkeypatch.setattr(server_module, "ThreadingHTTPServer", _RaisingHTTPServer)
    monkeypatch.setattr(server_module, "_is_workbench_running", lambda port: True)
    opened: list[str] = []
    monkeypatch.setattr(server_module.webbrowser, "open", opened.append)
    serve(workbench.root, 9999, open_browser=True)
    assert "已在运行" in capsys.readouterr().out
    assert opened == ["http://127.0.0.1:9999"]


def test_serve_raises_when_port_held_by_other_program(workbench, monkeypatch):
    # 端口被占用且探测不到本工作台实例：应报清晰错误
    monkeypatch.setattr(server_module, "ThreadingHTTPServer", _RaisingHTTPServer)
    monkeypatch.setattr(server_module, "_is_workbench_running", lambda port: False)
    with pytest.raises(OSError, match="已被其他程序占用"):
        serve(workbench.root, 9999, open_browser=False)
