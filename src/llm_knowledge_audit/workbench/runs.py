"""Controlled background execution. Credentials never enter plans or persisted job records."""

from __future__ import annotations

import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..config import Config, LLMConfig, load_config
from ..dataset.validate_cases import load_cases
from ..pipeline import STAGES, Pipeline
from ..storage import digest, now, read_json, write_new

ROLES = ("resolver", "generator", "judge")
DATASETS = {"pilot": "pilot_cases.jsonl", "starter": "starter_cases.jsonl"}


class ConsoleError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def read_if(path: Path, default: Any = None) -> Any:
    try:
        return read_json(path) if path.exists() else default
    except (OSError, ValueError):
        # A stage/reservation may be observed between exclusive creation and final write.
        return default


class RunController:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.RLock()
        # plan = (配置, 续跑目录, 数据集指纹, 环境变量原名表, 已授权的变量名集合)
        # 最后一个元素是"网页端显式同意"的载体：只有出现在 authorized 里的密钥名
        # 才允许被 start() 使用，且随 plan 一起被消费/淘汰（= 每次执行都要重新确认）。
        self.plans: dict[str, tuple[Config, Path | None, str, dict[str, str], set[str]]] = {}
        self.active: str | None = None
        self.threads: dict[str, threading.Thread] = {}

    def _busy(self) -> None:
        if self.active:
            raise ConsoleError("run_busy")

    def defaults(self) -> dict[str, Any]:
        cfg = load_config(self.root / "configs/pilot.yaml")
        return {
            "models": {r: getattr(cfg, r).model_dump() for r in ROLES},
            "max_calls": cfg.max_calls,
            "budget_usd": cfg.budget_usd,
            "triples_per_entity": cfg.triples_per_entity,
        }

    def credentials(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self._busy()
            plan_id = str(body.get("plan", ""))
            plan = self.plans.get(plan_id)
            if not plan:
                raise ConsoleError("plan_expired")
            cfg, _resume, _fingerprint, default_names, authorized = plan
            use_env = body.get("use_env") is True
            values = body.get("keys", {})
            if not isinstance(values, dict) or set(values) - set(ROLES):
                raise ConsoleError("invalid_request")
            # use_env 与 clear 语义互斥，同时给出无法解释用户意图
            if use_env and body.get("clear") is True:
                raise ConsoleError("invalid_request")
            for _role, value in values.items():
                if not isinstance(value, str) or len(value) > 4096 or "\n" in value:
                    raise ConsoleError("invalid_credentials")
            granted: set[str] = set()
            cleared: set[str] = set()
            # Fixed role names for new runs; validated LLMKA_* names for resumes.
            for role in ROLES:
                name = getattr(cfg, role).api_key_env
                value = values.get(role, "")
                if value:
                    # 手动填写的密钥本身就是一次显式同意
                    os.environ[name] = value
                    granted.add(name)
                elif body.get("clear") is True:
                    os.environ.pop(name, None)
                    cleared.add(name)
                elif use_env and name not in authorized:
                    # 「使用 .env」= 把进程环境里已有的值复制到本 plan 的密钥名下，
                    # 值只在此进程内存中流转，绝不写回响应体。
                    inherited = os.environ.get(default_names[role])
                    if (
                        isinstance(inherited, str)
                        and inherited
                        and len(inherited) <= 4096
                        and "\n" not in inherited
                    ):
                        os.environ[name] = inherited
                        granted.add(name)
            current = (authorized | granted) - cleared
            ready = {
                r: getattr(cfg, r).api_key_env in current
                and bool(os.environ.get(getattr(cfg, r).api_key_env))
                for r in ROLES
            }
            # 按合并后的结果判断：重复点「使用 .env」不该被误判为"环境里没有"
            if use_env and not any(ready.values()):
                raise ConsoleError("env_unavailable")
            self.plans[plan_id] = (cfg, _resume, _fingerprint, default_names, current)
            return {"ready": ready}

    def _validate_model(self, model: LLMConfig) -> None:
        url = urlsplit(model.base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ConsoleError("invalid_endpoint")
        if not re.fullmatch(r"[A-Za-z0-9_./:@-]{1,160}", model.model):
            raise ConsoleError("invalid_model")
        if not re.fullmatch(r"LLMKA_[A-Z0-9_]{1,80}", model.api_key_env):
            raise ConsoleError("invalid_credentials")

    def config(self, body: dict[str, Any]) -> tuple[Config, Path | None, dict[str, str]]:
        """构建本次运行的配置。

        第三个返回值是 default_names：每个角色"环境里那份凭据叫什么名字"。
        网页端新运行会把 api_key_env 改名成 LLMKA_WEB_*，所以必须在改名**之前**捕获；
        续跑则沿用 manifest 里记录的名字。网页端据此确认「使用 .env」时该复制哪个变量。
        """
        if body.get("resume"):
            # run_path is supplied by Workbench and validates the allowed results tree.
            resume = self.run_path(str(body["resume"]))  # type: ignore[attr-defined]
            cfg = Config.model_validate(read_json(resume / "manifest.json")["config"])
            for name in ("dataset", "mock_candidates", "annotations", "cache_dir", "raw_dir"):
                if not getattr(cfg, name).resolve().is_relative_to(self.root):
                    raise ConsoleError("invalid_path")
            if cfg.results_dir.resolve() != self.root / "results":
                raise ConsoleError("invalid_path")
            default_names = {r: getattr(cfg, r).api_key_env for r in ROLES}
        else:
            resume = None
            scope = str(body.get("dataset", "pilot"))
            mode = body.get("mode", "real")
            if scope not in DATASETS or mode not in {"mock", "real"}:
                raise ConsoleError("invalid_request")
            cfg = load_config(
                self.root / ("configs/learn.yaml" if mode == "mock" else "configs/pilot.yaml")
            )
            if mode == "mock" and (cfg.mode != "mock" or not cfg.offline):
                raise ConsoleError("mock_offline_required")
            default_names = {r: getattr(cfg, r).api_key_env for r in ROLES}
            values = cfg.model_dump(mode="json")
            values.update(
                dataset=str(self.root / "data/benchmark" / DATASETS[scope]),
                case_limit=body.get("case_limit", 5 if scope == "pilot" else 12),
                require_human_verified=body.get("require_human_verified", False),
            )
            for name in ("max_calls", "budget_usd", "triples_per_entity"):
                if name in body:
                    values[name] = body[name]
            if mode == "real":
                values["offline"] = False
                models = body.get("models", {})
                if not isinstance(models, dict) or set(models) - set(ROLES):
                    raise ConsoleError("invalid_model")
                allowed = {
                    "model",
                    "base_url",
                    "input_usd_per_million",
                    "output_usd_per_million",
                    "max_output_tokens",
                }
                for role in ROLES:
                    edits = models.get(role, {})
                    if not isinstance(edits, dict) or set(edits) - allowed:
                        raise ConsoleError("invalid_model")
                    values[role].update(edits)
                    values[role]["api_key_env"] = f"LLMKA_WEB_{role.upper()}_KEY"
            cfg = Config.model_validate(values)
            if cfg.case_limit is None or cfg.case_limit > (5 if scope == "pilot" else 12):
                raise ConsoleError("invalid_request")
        if cfg.mode == "real":
            for role in ROLES:
                self._validate_model(getattr(cfg, role))
        elif not cfg.offline:
            raise ConsoleError("mock_offline_required")
        return cfg, resume, default_names

    def preview(self, body: dict[str, Any]) -> dict[str, Any]:
        cfg, resume, default_names = self.config(body)
        cases = load_cases(cfg.dataset)[: cfg.case_limit]
        n = len(cases)
        plan = uuid.uuid4().hex
        fingerprint = digest(cfg.dataset.read_text())
        with self.lock:
            # Bound in-memory plans; no keys or plans are written to disk.
            if len(self.plans) >= 64:
                self.plans.pop(next(iter(self.plans)))
            # 新 plan 的授权集恒为空：环境里有没有密钥 ≠ 用户同意使用它
            self.plans[plan] = (cfg, resume, fingerprint, default_names, set())
        inherited = []
        if resume:
            inherited = read_if(resume / "inherited_budget.json", []) + [
                read_if(p, {}) for p in (resume / "reservations").glob("*.json")
            ]
        return {
            "plan": plan,
            "mode": cfg.mode,
            "cases": [c.case_id for c in cases],
            "pending_review": sum(c.verification_status != "human_verified" for c in cases),
            "require_human_verified": cfg.require_human_verified,
            "models": {r: getattr(cfg, r).model_dump() for r in ROLES},
            "max_unique_seeds": 2 * n,
            "max_logical_calls": n + 2 * n * (1 + cfg.triples_per_entity),
            "max_http_attempts": cfg.max_calls,
            "budget_cap_usd": cfg.budget_usd,
            "inherited_attempts": sum(r.get("attempts", 0) for r in inherited),
            "inherited_reserved_usd": sum(r.get("reserved_usd", 0) for r in inherited),
            "credentials_ready": {r: False for r in ROLES},
            # 环境里是否存在可用的凭据（只报布尔，绝不回传值）；
            # mock 模式不使用凭据，直接给空对象，避免泄漏环境信息。
            "env_keys_available": (
                {r: bool(os.environ.get(default_names[r])) for r in ROLES}
                if cfg.mode == "real"
                else {}
            ),
            "resume": body.get("resume"),
        }

    def start(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self._busy()
            plan_id = str(body.get("plan", ""))
            if plan_id not in self.plans:
                raise ConsoleError("plan_expired")
            cfg, resume, fingerprint, _default_names, authorized = self.plans[plan_id]
            if digest(cfg.dataset.read_text()) != fingerprint:
                raise ConsoleError("plan_stale")
            if cfg.require_human_verified and cfg.mode == "real":
                if any(
                    c.verification_status != "human_verified"
                    for c in load_cases(cfg.dataset)[: cfg.case_limit]
                ):
                    raise ConsoleError("gold_required")
            approved = body.get("approve_paid") is True
            if cfg.mode == "real":
                if not approved:
                    raise ConsoleError("approval_required")
                # 必须"既在环境里、又被本次 plan 显式授权"才放行：
                # 光有 .env 不算同意，光点了确认但没有值也不算。
                if any(
                    getattr(cfg, r).api_key_env not in authorized
                    or not os.environ.get(getattr(cfg, r).api_key_env)
                    for r in ROLES
                ):
                    raise ConsoleError("credentials_required")
            job = uuid.uuid4().hex
            write_new(
                self.root / "data/reviews/jobs" / job / "queued.json",
                {
                    "id": "job/" + job,
                    "created_at": now(),
                    "mode": cfg.mode,
                    "status": "running",
                    "n": len(load_cases(cfg.dataset)[: cfg.case_limit]),
                    "approved": approved if cfg.mode == "real" else False,
                    "resume": str(resume.relative_to(self.root / "results")) if resume else None,
                },
            )
            self.active = job
            worker = threading.Thread(
                target=self._execute,
                args=(job, cfg, resume, approved),
                daemon=True,
                name="llmka-run-" + job,
            )
            self.threads[job] = worker
            self.plans.pop(plan_id)
            worker.start()
            return {"job": job, "run": "job/" + job}

    def _execute(self, job: str, cfg: Config, resume: Path | None, approved: bool) -> None:
        directory = self.root / "data/reviews/jobs" / job
        try:
            pipeline = Pipeline(cfg, resume, approved if cfg.mode == "real" else False)
            write_new(
                directory / "started.json",
                {"run": pipeline.path.relative_to(self.root / "results").as_posix()},
            )
            pipeline.execute()
            write_new(
                directory / "finished.json",
                {
                    "status": "failed" if pipeline.failures else "completed",
                    "code": "stage_failures" if pipeline.failures else None,
                    "at": now(),
                },
            )
        except Exception as exc:
            # Never persist exception text: provider/validation errors can contain user input.
            code = (
                "resume_changed"
                if resume and not (directory / "started.json").exists()
                else "execution_failed"
            )
            write_new(
                directory / "finished.json",
                {"status": "failed", "code": code, "type": type(exc).__name__, "at": now()},
            )
        finally:
            with self.lock:
                self.active = None

    def job(self, job: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-f0-9]{32}", job):
            raise ConsoleError("invalid_path")
        directory = self.root / "data/reviews/jobs" / job
        record = read_if(directory / "queued.json")
        if not record:
            raise ConsoleError("not_found")
        record.update(read_if(directory / "started.json", {}))
        record.update(read_if(directory / "finished.json", {}))
        if record["status"] == "running" and self.active != job:
            record.update(status="failed", code="interrupted")
        return dict(record)

    def progress(self, run: str) -> dict[str, Any]:
        if run.startswith("job/"):
            record = self.job(run.split("/")[1])
            return self.progress(record["run"]) if record.get("run") else record
        path = self.run_path(run)  # type: ignore[attr-defined]
        manifest = read_json(path / "manifest.json")
        completion = read_if(path / "completion.json", {})
        failure = read_if(path / "failure.json", {})
        owned = any(
            self.job(p.parent.name).get("run") == run
            for p in (self.root / "data/reviews/jobs").glob("*/started.json")
            if p.parent.name == self.active
        )
        status = (
            "failed"
            if failure or completion.get("failures")
            else "completed"
            if completion
            else "running"
            if owned
            else "failed"
        )
        stages = []
        active_found = False
        for stage in STAGES:
            artifact = read_if(path / f"{stage}.json")
            done = artifact is not None
            state = "completed" if done else "pending"
            if isinstance(artifact, dict) and any(
                isinstance(row, dict) and row.get("status") == "failed" for row in artifact.values()
            ):
                state = "failed"
            if not done and not active_found:
                state = (
                    "running"
                    if status == "running"
                    else "failed"
                    if status == "failed"
                    else "pending"
                )
                active_found = True
            stages.append({"id": stage, "status": state, "artifact_available": done})
        reservations = read_if(path / "inherited_budget.json", []) + [
            read_if(p, {}) for p in (path / "reservations").glob("*.json")
        ]
        return {
            "id": run,
            "mode": manifest["mode"],
            "status": status,
            "created_at": manifest["created_at"],
            "n": len(read_if(path / "cases.json", []))
            or read_if(path / "evaluate.json", {})
            .get("candidates", {})
            .get("recall_at_k", {})
            .get("denominator", 0),
            "stages": stages,
            "completed_stages": sum(s["artifact_available"] for s in stages),
            "attempts": sum(r.get("attempts", 0) for r in reservations),
            "reserved_usd": sum(r.get("reserved_usd", 0) for r in reservations),
            "budget_usd": manifest["config"]["budget_usd"],
            "max_calls": manifest["config"]["max_calls"],
            "paid_approved": manifest.get("paid_approved", False),
            "human_verified_cases": manifest.get("human_verified_cases", 0),
            "require_human_verified": manifest["config"].get("require_human_verified", True),
            "failure_code": (
                "stage_failures"
                if completion.get("failures")
                else "execution_failed"
                if failure
                else "interrupted"
                if status == "failed"
                else None
            ),
            "failures": completion.get("failures", []),
            "failure_type": failure.get("type"),
            "parent_run": manifest.get("parent_run"),
        }
