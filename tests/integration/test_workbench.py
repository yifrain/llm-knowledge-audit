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
    # 真实基准里的复核进度不能影响测试：在临时副本中重置为"待复核"
    for name in ["pilot_cases.jsonl", "starter_cases.jsonl"]:
        file = tmp_path / "data/benchmark" / name
        rows = read_jsonl(file)
        for row in rows:
            row["verification_status"] = "pending_human_review"
            row.pop("verified_by", None)
            row.pop("verified_at", None)
        file.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
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
    with pytest.raises(ValueError, match="confirmation_required"):
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
    with pytest.raises(ValueError, match="review_stale"):
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
    with pytest.raises(ValueError, match="mock_review_disabled"):
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
    with pytest.raises(ValueError, match="invalid_evidence"):
        workbench.annotate(run, body)
    body["evidence_ids"] = [row["evidence"][0]["passage_id"]]
    workbench.annotate(run, body)
    assert workbench.review(run)["completed"] == 1
    assert workbench.comparison(run)["locked"] is True
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
    with pytest.raises(ValueError, match="mock_offline_required"):
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
        server_module.urllib.request,
        "urlopen",
        lambda url, timeout: _FakeResponse(b'{"runs": [], "token": "x"}'),
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


def wait_job(wb, result):
    wb.threads[result["job"]].join(timeout=10)
    assert not wb.threads[result["job"]].is_alive()
    return wb.job(result["job"])


def test_background_mock_and_resume_are_immutable(workbench):
    plan = workbench.preview({"mode": "mock", "dataset": "pilot", "case_limit": 2})
    assert plan["max_logical_calls"] == 2 + 4 * 6
    job = wait_job(workbench, workbench.start({"plan": plan["plan"]}))
    assert job["status"] == "completed"
    run = job["run"]
    progress = workbench.progress(run)
    assert progress["completed_stages"] == 8
    assert progress["attempts"] == 0
    path = workbench.run_path(run)
    original = {p.relative_to(path): p.read_bytes() for p in path.rglob("*") if p.is_file()}
    resume = workbench.preview({"resume": run})
    child = wait_job(workbench, workbench.start({"plan": resume["plan"]}))
    assert child["run"] != run
    assert original == {p.relative_to(path): p.read_bytes() for p in path.rglob("*") if p.is_file()}
    assert read_json(workbench.run_path(child["run"]) / "manifest.json")["parent_run"] == str(path)


def test_paid_preflight_credentials_and_no_secret_persistence(workbench, monkeypatch):
    import os

    from llm_knowledge_audit.models import Candidate
    from llm_knowledge_audit.pipeline import Pipeline
    from llm_knowledge_audit.providers.mock import MockProvider
    from llm_knowledge_audit.retrieval.mock import MockEvidenceRetriever

    # Real orchestration and manifest, synthetic provider/retriever: never a real experiment.
    class Public:
        def __init__(self, cfg):
            self.http = type("HTTP", (), {"events": []})()

        def search(self, surface, k):
            return [
                Candidate.model_validate(c)
                for c in read_json(workbench.root / "tests/fixtures/candidates.json")[surface]
            ][:k]

    monkeypatch.setattr("llm_knowledge_audit.retrieval.wikidata.Wikidata", Public)
    monkeypatch.setattr(
        "llm_knowledge_audit.retrieval.wikipedia.WikipediaRetriever",
        lambda public: MockEvidenceRetriever(),
    )
    monkeypatch.setattr(Pipeline, "provider", lambda self, model: MockProvider())
    for role in ("RESOLVER", "GENERATOR", "JUDGE"):
        monkeypatch.delenv("LLMKA_WEB_" + role + "_KEY", raising=False)
    plan = workbench.preview({"mode": "real", "case_limit": 1, "require_human_verified": False})
    with pytest.raises(ValueError, match="approval_required"):
        workbench.start({"plan": plan["plan"]})
    with pytest.raises(ValueError, match="credentials_required"):
        workbench.start({"plan": plan["plan"], "approve_paid": True})
    secret = "SYNTHETIC_SECRET_DO_NOT_PERSIST_999"
    keys = {r: secret for r in ("resolver", "generator", "judge")}
    workbench.credentials({"plan": plan["plan"], "keys": keys})
    assert os.environ["LLMKA_WEB_JUDGE_KEY"] == secret
    job = wait_job(workbench, workbench.start({"plan": plan["plan"], "approve_paid": True}))
    assert job["status"] == "completed"
    manifest = read_json(workbench.run_path(job["run"]) / "manifest.json")
    assert manifest["paid_approved"] is True
    assert manifest["human_verified_cases"] == 0
    for p in workbench.root.rglob("*"):
        if p.is_file():
            assert secret.encode() not in p.read_bytes()
    assert secret not in json.dumps(workbench.overview(job["run"]))
    next_plan = workbench.preview({"mode": "real"})
    workbench.credentials({"plan": next_plan["plan"], "keys": {r: "" for r in keys}, "clear": True})
    assert "LLMKA_WEB_JUDGE_KEY" not in os.environ


def test_env_consent_gate_and_use_env_copy(workbench, monkeypatch):
    """环境里有密钥 ≠ 可以使用：必须网页端显式确认，值也不得回传或落盘。"""
    import os

    from llm_knowledge_audit.models import Candidate
    from llm_knowledge_audit.pipeline import Pipeline
    from llm_knowledge_audit.providers.mock import MockProvider
    from llm_knowledge_audit.retrieval.mock import MockEvidenceRetriever

    class Public:
        def __init__(self, cfg):
            self.http = type("HTTP", (), {"events": []})()

        def search(self, surface, k):
            return [
                Candidate.model_validate(c)
                for c in read_json(workbench.root / "tests/fixtures/candidates.json")[surface]
            ][:k]

    monkeypatch.setattr("llm_knowledge_audit.retrieval.wikidata.Wikidata", Public)
    monkeypatch.setattr(
        "llm_knowledge_audit.retrieval.wikipedia.WikipediaRetriever",
        lambda public: MockEvidenceRetriever(),
    )
    monkeypatch.setattr(Pipeline, "provider", lambda self, model: MockProvider())
    secret = "ENV_AMBIENT_SECRET_DO_NOT_LEAK_777"
    monkeypatch.setenv("LLMKA_API_KEY", secret)
    for role in ("RESOLVER", "GENERATOR", "JUDGE"):
        monkeypatch.delenv("LLMKA_WEB_" + role + "_KEY", raising=False)

    plan = workbench.preview({"mode": "real", "case_limit": 1, "require_human_verified": False})
    # 环境里有值，但未经确认 → ready 全假；可用性如实上报
    assert plan["credentials_ready"] == {"resolver": False, "generator": False, "judge": False}
    assert plan["env_keys_available"] == {"resolver": True, "generator": True, "judge": True}
    assert secret not in json.dumps(plan)

    with pytest.raises(ValueError, match="credentials_required"):
        workbench.start({"plan": plan["plan"], "approve_paid": True})

    output = workbench.credentials({"plan": plan["plan"], "use_env": True})
    assert output["ready"] == {"resolver": True, "generator": True, "judge": True}
    assert secret not in json.dumps(output)
    # 复制到本 plan 的密钥名下（web 新运行的 LLMKA_WEB_*）
    assert os.environ["LLMKA_WEB_JUDGE_KEY"] == secret

    job = wait_job(workbench, workbench.start({"plan": plan["plan"], "approve_paid": True}))
    assert job["status"] == "completed"
    for p in workbench.root.rglob("*"):
        if p.is_file():
            assert secret.encode() not in p.read_bytes()


def test_use_env_without_ambient_keys_raises(workbench, monkeypatch):
    """环境里什么都没有时确认「使用 .env」→ 报错，而不是静默放行。"""
    monkeypatch.delenv("LLMKA_API_KEY", raising=False)
    for role in ("RESOLVER", "GENERATOR", "JUDGE"):
        monkeypatch.delenv("LLMKA_WEB_" + role + "_KEY", raising=False)
    plan = workbench.preview({"mode": "real", "case_limit": 1, "require_human_verified": False})
    assert plan["env_keys_available"] == {"resolver": False, "generator": False, "judge": False}
    with pytest.raises(ValueError, match="env_unavailable"):
        workbench.credentials({"plan": plan["plan"], "use_env": True})


def test_consent_does_not_carry_across_plans(workbench, monkeypatch):
    """每个 plan 单独确认：上一个 plan 的同意/残留密钥不能让新 plan 直接开跑。"""
    for role in ("RESOLVER", "GENERATOR", "JUDGE"):
        monkeypatch.setenv("LLMKA_WEB_" + role + "_KEY", "stale-session-value")
    plan = workbench.preview({"mode": "real", "case_limit": 1, "require_human_verified": False})
    assert plan["credentials_ready"] == {"resolver": False, "generator": False, "judge": False}
    with pytest.raises(ValueError, match="credentials_required"):
        workbench.start({"plan": plan["plan"], "approve_paid": True})


def test_gold_gate_and_changed_preview_refuse_before_job(workbench):
    plan = workbench.preview({"require_human_verified": True})
    with pytest.raises(ValueError, match="gold_required"):
        workbench.start({"plan": plan["plan"], "approve_paid": True})
    file = workbench.root / "data/benchmark/pilot_cases.jsonl"
    file.write_text(file.read_text() + "\n")
    with pytest.raises(ValueError, match="plan_stale"):
        workbench.start({"plan": plan["plan"], "approve_paid": True})
    assert workbench.runs() == []


def test_batch_confirmation_records_origin_overrides_and_stale_rejection(workbench):
    rows = workbench.case_queue("pilot")["rows"]
    payload = {
        "scope": "pilot",
        "confirmed": True,
        "reviewer": "TEST BATCH",
        "rows": [{"case_id": r["case_id"], "revision": r["revision"]} for r in rows],
    }
    payload["rows"][1]["overrides"] = {"gold_description": "SYNTHETIC EDIT FOR TEST"}
    workbench.verify_batch(payload)
    assert workbench.case_queue("pilot")["reviewed"] == 5
    history = [
        read_json(p) for p in (workbench.root / "data/reviews/entity_history").glob("*.json")
    ]
    assert all(r["method"] == "batch_confirmation" for r in history)
    assert any(r.get("case_ids") == [r["case_id"] for r in rows] for r in history)
    count = len(history)
    with pytest.raises(ValueError, match="review_stale"):
        workbench.verify_batch(payload)
    assert len(list((workbench.root / "data/reviews/entity_history").glob("*.json"))) == count


def test_blind_gate_covers_metrics_trace_comparison_and_exports(workbench):
    mock = workbench.demo()["run"]
    run = "real/blind-fixture"
    path = workbench.root / "results" / run
    shutil.copytree(workbench.run_path(mock), path)
    manifest = read_json(path / "manifest.json")
    manifest["mode"] = "real"
    (path / "manifest.json").write_text(json.dumps(manifest))
    before = {p.relative_to(path): p.read_bytes() for p in path.rglob("*") if p.is_file()}
    review = workbench.review(run)
    for r in review["rows"]:
        assert not workbench.blind_complete(run)
        m = workbench.overview(run)["metrics"]
        for name in [
            "factuality",
            "factuality_by_method",
            "judge_agreement",
            "error_analysis",
            "disagreements",
        ]:
            assert name not in m
        assert workbench.overview(run)["comparison"] is None
        assert all(c["judgment"] is None for c in workbench.trace(run, "homonym_001")["claims"])
        for name in ["report.md", "evaluate.json", "figures.zip", "review-comparison.json"]:
            with pytest.raises(ValueError, match="blind_locked"):
                workbench.export(run, name)
        workbench.annotate(
            run,
            {
                "triple_id": r["triple_id"],
                "annotator_id": "TEST",
                "human_label": "not_enough_information",
                "evidence_ids": [],
            },
        )
    assert workbench.blind_complete(run)
    assert workbench.comparison(run)["metrics"]["annotated_n"] == 20
    assert workbench.export(run, "report.md")[0]
    assert before == {p.relative_to(path): p.read_bytes() for p in path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="not_found"):
        workbench.export(run, "../../README.md")


def test_async_failure_busy_and_restart_visibility(workbench, monkeypatch):
    import threading

    from llm_knowledge_audit.pipeline import Pipeline

    entered, release = threading.Event(), threading.Event()
    original = Pipeline.stage_collect_candidates

    def fail(self):
        entered.set()
        release.wait(5)
        raise RuntimeError("secret-like failure text must not be persisted")

    monkeypatch.setattr(Pipeline, "stage_collect_candidates", fail)
    plan = workbench.preview({"mode": "mock"})
    result = workbench.start({"plan": plan["plan"]})
    assert entered.wait(5)
    assert workbench.runs()[0]["status"] == "running"
    with pytest.raises(ValueError, match="run_busy"):
        workbench.start({"plan": plan["plan"]})
    release.set()
    job = wait_job(workbench, result)
    assert job["status"] == "failed"
    assert workbench.progress(job["run"])["failure_type"] == "RuntimeError"
    assert Workbench(workbench.root).runs()[0]["status"] == "failed"
    monkeypatch.setattr(Pipeline, "stage_collect_candidates", original)
    plan2 = workbench.preview({"resume": job["run"]})
    success = wait_job(workbench, workbench.start({"plan": plan2["plan"]}))
    assert success["status"] == "completed"
    for p in workbench.root.rglob("*.json"):
        assert "secret-like failure text" not in p.read_text()


def test_resume_signature_rejection_is_visible_without_altering_parent(workbench):
    run = workbench.demo()["run"]
    file = workbench.root / "data/benchmark/starter_cases.jsonl"
    file.write_text(file.read_text() + "\n")
    plan = workbench.preview({"resume": run})
    record = wait_job(workbench, workbench.start({"plan": plan["plan"]}))
    assert record["status"] == "failed"
    assert record["code"] == "resume_changed"
    assert not record.get("run")
    assert len(workbench.runs()) == 2


@pytest.mark.parametrize(
    "model",
    [
        {"api_key": "never-dump"},
        {"base_url": "https://key@example.org/v1"},
        {"base_url": "https://example.org/v1?key=secret"},
    ],
)
def test_model_fields_do_not_accept_credentials(workbench, model):
    with pytest.raises(ValueError):
        workbench.preview({"models": {"resolver": model}})
    assert not (workbench.root / "results").exists()


def test_http_origin_token_static_and_error_contract(workbench, monkeypatch):
    import io
    from email.message import Message

    captured = {}

    class Server:
        server_port = 9998

        def __init__(self, address, handler):
            assert address == ("127.0.0.1", 9998)
            captured["handler"] = handler

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr(server_module, "ThreadingHTTPServer", Server)
    serve(workbench.root, 9998)

    def request(path, method="GET", body=None, host="127.0.0.1:9998", origin=None, token=None):
        handler = captured["handler"].__new__(captured["handler"])
        handler.path = path
        handler.headers = Message()
        handler.headers["Host"] = host
        if origin:
            handler.headers["Origin"] = origin
        if token:
            handler.headers["X-Review-Token"] = token
        data = json.dumps(body or {}).encode()
        handler.headers["Content-Length"] = str(len(data))
        handler.headers["Content-Type"] = "application/json"
        handler.rfile, handler.wfile = io.BytesIO(data), io.BytesIO()
        output = {"headers": {}}
        handler.send_response = lambda status: output.update(status=status)
        handler.send_header = lambda name, value: output["headers"].update({name: value})
        handler.end_headers = lambda: None
        getattr(handler, "do_" + method)()
        output["body"] = handler.wfile.getvalue()
        return output

    assert request("/api/state", host="evil.example:9998")["status"] == 403
    assert request("/api/state", origin="https://evil.example")["status"] == 403
    state = json.loads(request("/api/state")["body"])
    # 只断言形状：同一 pytest 进程里模块级 _loaded 可能被其它测试写过，值不可依赖。
    assert set(state["env"]) == {"path", "names"}
    assert request("/api/start", "POST", {})["status"] == 403
    assert request("/api/start", "POST", {}, token="wrong")["status"] == 403
    result = request("/api/start", "POST", {}, token=state["token"])
    assert json.loads(result["body"])["error"] == "plan_expired"
    assert request("/../../README.md")["status"] == 404
    asset = request("/i18n.js")
    assert asset["status"] == 200
    assert "script-src 'self'" in asset["headers"]["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in asset["headers"]["Content-Security-Policy"]
    bad = request(
        "/api/preview", "POST", {"budget_usd": "PRIVATE_PAYLOAD_MARKER"}, token=state["token"]
    )
    assert bad["status"] == 400
    assert b"PRIVATE_PAYLOAD_MARKER" not in bad["body"]
    assert json.loads(bad["body"]) == {"error": "invalid_request"}


def test_written_artifact_with_failed_items_is_not_shown_as_success(workbench, monkeypatch):
    from llm_knowledge_audit.pipeline import Pipeline
    from llm_knowledge_audit.providers.base import ProviderError

    class BrokenProvider:
        def complete(self, *args):
            raise ProviderError("synthetic provider failure")

    monkeypatch.setattr(Pipeline, "provider", lambda self, model: BrokenProvider())
    plan = workbench.preview({"mode": "mock", "case_limit": 1})
    record = wait_job(workbench, workbench.start({"plan": plan["plan"]}))
    assert record["status"] == "failed"
    progress = workbench.progress(record["run"])
    assert progress["completed_stages"] == 8  # Artifacts written, not eight successful algorithms.
    assert progress["stages"][2]["artifact_available"] is True
    assert progress["stages"][2]["status"] == "failed"
    assert progress["failure_code"] == "stage_failures"
