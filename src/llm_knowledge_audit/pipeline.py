"""A stage invocation always creates a new immutable run, including resume.

每次调用阶段都会创建一个新的不可变运行记录（run），续跑（resume）也不例外。
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Config, LLMConfig
from .dataset.validate_cases import load_cases
from .disambiguation.context_guided import ContextGuided
from .disambiguation.string_baseline import StringBaseline
from .generation.generate_triples import generate
from .judging.factuality_judge import judge
from .logging_utils import event
from .models import Annotation, Candidate, EntityCase, Evidence, StringCandidate, Triple
from .providers.base import Provider
from .providers.client import CallClient
from .providers.mock import MockProvider
from .retrieval.base import EvidenceRetriever
from .retrieval.mock import MockEvidenceRetriever
from .storage import digest, now, read_json, write_jsonl_new, write_new

# 流水线的 8 个阶段
STAGES = [
    "collect-candidates",
    "disambiguate-string",
    "disambiguate-context",
    "generate-triples",
    "retrieve-evidence",
    "judge",
    "evaluate",
    "build-report",
]
# 阶段依赖关系（有向无环图）：执行某阶段前必须先完成其依赖阶段
DEPENDENCIES = {
    "collect-candidates": [],
    "disambiguate-string": ["collect-candidates"],
    "disambiguate-context": ["collect-candidates"],
    "generate-triples": ["disambiguate-string", "disambiguate-context"],
    "retrieve-evidence": ["generate-triples"],
    "judge": ["retrieve-evidence"],
    "evaluate": ["judge"],
    "build-report": ["evaluate"],
}


class Pipeline:
    def __init__(self, cfg: Config, resume: Path | None = None, approved: bool = False):
        self.cfg = cfg
        # 加载并截断评测案例（case_limit 控制数量）
        self.cases = load_cases(cfg.dataset)
        self.cases = self.cases[: cfg.case_limit]
        self.client = CallClient(cfg, approved)
        # 输入数据的校验和：数据集、人工标注、mock 候选快照
        inputs = {
            "dataset": hashlib.sha256(cfg.dataset.read_bytes()).hexdigest(),
            "annotations": hashlib.sha256(cfg.annotations.read_bytes()).hexdigest()
            if cfg.annotations.exists()
            else None,
            "mock_candidates": hashlib.sha256(cfg.mock_candidates.read_bytes()).hexdigest()
            if cfg.mode == "mock"
            else None,
        }
        source_dir = Path(__file__).parent
        # 运行签名 = 配置 + 输入数据 + 全部源码的哈希，用于保证运行可复现
        self.signature = digest(
            {
                "config": cfg.model_dump(mode="json"),
                "inputs": {k: v for k, v in inputs.items() if k != "annotations"},
                "code": {
                    str(f.relative_to(source_dir)): hashlib.sha256(f.read_bytes()).hexdigest()
                    for f in sorted(source_dir.rglob("*.py"))
                },
            }
        )
        # 续跑前先校验签名：配置、源码或输入校验和发生变化则拒绝续跑
        if resume and read_json(resume / "manifest.json")["signature"] != self.signature:
            raise ValueError("Resume rejected: config, source code, or input checksum changed")
        # 新的运行目录：<results_dir>/<mode>/<时间戳>-<随机后缀>
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
        self.path = cfg.results_dir / cfg.mode / run_id
        self.path.mkdir(parents=True, exist_ok=False)
        # 尝试记录当前 git 提交（失败则置空，不阻塞运行）
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=cfg.dataset.parent,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            commit = None
        # 运行清单（manifest）：记录运行元信息，供审计与续跑追溯
        write_new(
            self.path / "manifest.json",
            {
                "run_id": run_id,
                "created_at": now(),
                "mode": cfg.mode,
                "git_commit": commit,
                "signature": self.signature,
                "config": cfg.model_dump(mode="json"),
                "input_checksums": inputs,
                "prompt_versions": {
                    "generate": "generate-v1",
                    "resolve": "resolve-v1",
                    "judge": "judge-v1",
                },
                "parent_run": str(resume) if resume else None,
                "seed": cfg.seed,
                "paid_approved": approved,
                "human_verified_cases": sum(
                    c.verification_status == "human_verified" for c in self.cases
                ),
            },
        )
        # reused：从旧运行中直接复用的阶段列表
        write_new(self.path / "cases.json", [c.model_dump(mode="json") for c in self.cases])
        self.reused: list[str] = []
        inherited_reservations: list[dict[str, Any]] = []
        if resume:
            # 逐阶段复用旧运行产物：
            # - 失败阶段及其所有下游阶段被阻断（blocked），必须重跑；
            # - evaluate / build-report 总是重算，以反映最新的人工标注快照。
            blocked: set[str] = set()
            for stage in STAGES:
                old = resume / f"{stage}.json"
                if stage in {"evaluate", "build-report"}:
                    continue  # Recompute with the current human annotation snapshot.
                if any(d in blocked for d in DEPENDENCIES[stage]):
                    blocked.add(stage)
                    continue
                if old.exists():
                    artifact = read_json(old)
                    if any(
                        isinstance(r, dict) and r.get("status") == "failed"
                        for r in artifact.values()
                    ):
                        blocked.add(stage)
                        continue
                    shutil.copyfile(old, self.path / old.name)
                    self.reused.append(stage)
            # 逐条级缓存（items/）整体继承
            if (resume / "items").exists():
                shutil.copytree(resume / "items", self.path / "items")
            # judge 阶段被复用时，人工标注模板与盲评包一并继承
            if "judge" in self.reused:
                for name in ("annotations.template.jsonl", "annotation_packet.json"):
                    shutil.copyfile(resume / name, self.path / name)
            # 继承历史运行的费用预算预留（见下方 immutable lineage 说明）
            inherited_reservations = (
                read_json(resume / "inherited_budget.json")
                if (resume / "inherited_budget.json").exists()
                else []
            )
            inherited_reservations += [
                read_json(f) for f in (resume / "reservations").glob("*.json")
            ]
        # 恢复续跑前已预留的费用与调用次数统计
        self.client.reserved_usd = sum(r["reserved_usd"] for r in inherited_reservations)
        self.client.attempts = sum(r["attempts"] for r in inherited_reservations)
        self.client.reservation_dir = self.path / "reservations"
        # Separate immutable lineage artifact retains conservative reservations across resumes.
        # 独立的不可变血统工件：跨多次续跑累积保留保守的预算预留记录。
        write_new(self.path / "inherited_budget.json", inherited_reservations)
        self.failures: list[dict[str, Any]] = []
        self.retriever: EvidenceRetriever = MockEvidenceRetriever()
        self.public: Any = None
        # real 模式：初始化公开知识库（Wikidata 候选检索 + Wikipedia 证据检索）
        if cfg.mode == "real":
            from .retrieval.wikidata import Wikidata
            from .retrieval.wikipedia import WikipediaRetriever

            self.public = Wikidata(cfg)
            self.retriever = WikipediaRetriever(self.public)

    def provider(self, model: LLMConfig) -> Provider:
        """按配置选择 LLM 提供方：mock 用本地假实现，其余走 OpenAI 兼容接口。"""
        if model.provider == "mock":
            return MockProvider()
        from .providers.openai_compatible import OpenAICompatible

        return OpenAICompatible(model, self.cfg)

    def item(self, stage: str, key: str, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """逐条级缓存：以 stage + key 的哈希为文件名落盘，命中缓存则跳过计算。

        失败的结果会被保留供审计，但不会写入缓存（不作为已完成的检查点）。
        """
        path = self.path / "items" / stage / f"{digest(key)}.json"
        if path.exists():
            value: dict[str, Any] = read_json(path)
            return value
        before = len(self.client.events)
        value = compute()
        # Failed outputs are retained for audit but are not accepted as completed checkpoints.
        if value.get("status") != "failed":
            write_new(path, value)
        # 本次计算产生的 LLM 调用事件单独记入遥测文件
        new_events = self.client.events[before:]
        if new_events:
            write_new(self.path / "telemetry" / f"{uuid.uuid4().hex}.json", new_events)
        return value

    def ensure(self, stage: str) -> Any:
        """幂等地执行到指定阶段：

        产物已存在则直接返回；否则先递归确保依赖阶段完成，再执行本阶段并落盘。
        """
        if (
            stage != "collect-candidates"
            and self.cfg.mode == "real"
            and self.cfg.require_human_verified
        ):
            if any(c.verification_status != "human_verified" for c in self.cases):
                raise ValueError("Selected real-run cases require human verification")
        path = self.path / f"{stage}.json"
        if path.exists():
            return read_json(path)
        for dependency in DEPENDENCIES[stage]:
            self.ensure(dependency)
        event("stage_started", stage=stage, run=self.path.name)
        method = getattr(self, "stage_" + stage.replace("-", "_"))
        output = method()
        write_new(path, output)
        return output

    def execute(self, stage: str = "build-report") -> Path:
        """流水线主入口：执行到目标阶段（默认全流程），记录完成/失败状态。"""
        try:
            self.ensure(stage)
            # 成功（可能带部分失败）时写完成清单，列出全部输出文件
            write_new(
                self.path / "completion.json",
                {
                    "status": "completed_with_failures" if self.failures else "completed",
                    "completed_at": now(),
                    "reused_stages": self.reused,
                    "failures": self.failures,
                    "calls": self.client.events,
                    "public_http_calls": self.public.http.events if self.public else [],
                    "outputs": sorted(
                        str(p.relative_to(self.path)) for p in self.path.rglob("*") if p.is_file()
                    ),
                },
            )
        except Exception as exc:
            # 整体失败时写失败清单并重新抛出异常
            write_new(
                self.path / "failure.json",
                {
                    "status": "failed",
                    "type": type(exc).__name__,
                    "at": now(),
                    "calls": self.client.events,
                    "message": "Inspect stage artifacts; resume in a new run after diagnosis.",
                },
            )
            raise
        return self.path

    def stage_collect_candidates(self) -> dict[str, Any]:
        """阶段 1：为每个案例的表面形式收集候选实体。

        mock 模式读取固定候选快照；real 模式调用 Wikidata 搜索。
        """
        fixture = read_json(self.cfg.mock_candidates) if self.cfg.mode == "mock" else {}
        result = {}
        for case in self.cases:

            def compute(case: EntityCase = case) -> dict[str, Any]:
                candidates = (
                    [Candidate.model_validate(c) for c in fixture.get(case.surface_form, [])]
                    if self.cfg.mode == "mock"
                    else self.public.search(case.surface_form, self.cfg.candidate_k)
                )
                return {
                    "candidates": [
                        c.model_dump(mode="json") for c in candidates[: self.cfg.candidate_k]
                    ]
                }

            result[case.case_id] = self.item("candidates", case.surface_form, compute)
        return result

    def resolve(self, method: str) -> dict[str, Any]:
        """阶段 2/3 的公共实现：逐案例做实体消歧。

        method="string"：纯字符串基线（无 LLM）；method="context"：带上下文的 LLM 消歧。
        """
        raw = self.ensure("collect-candidates")
        result = {}
        for case in self.cases:
            candidates = [Candidate.model_validate(c) for c in raw[case.case_id]["candidates"]]

            def compute(
                case: EntityCase = case, candidates: list[Candidate] = candidates
            ) -> dict[str, Any]:
                try:
                    if method == "string":
                        prediction = StringBaseline(self.cfg.min_confidence).resolve(
                            case.surface_form,
                            [
                                StringCandidate(
                                    entity_id=c.entity_id, label=c.label, aliases=c.aliases
                                )
                                for c in candidates
                            ],
                        )
                    else:
                        prediction = ContextGuided(
                            self.client,
                            self.provider(self.cfg.resolver),
                            self.cfg.resolver,
                            self.cfg.min_confidence,
                        ).resolve(case.surface_form, case.context, case.source_triple, candidates)
                    return {"status": "ok", **prediction.model_dump()}
                except (ValueError, RuntimeError) as exc:
                    # 单条失败不中断整体：记入 failures 并返回失败状态
                    self.failures.append(
                        {"stage": method, "case_id": case.case_id, "type": type(exc).__name__}
                    )
                    return {
                        "status": "failed",
                        "selected_entity_id": None,
                        "error": type(exc).__name__,
                    }

            result[case.case_id] = self.item("resolve-" + method, case.case_id, compute)
        return result

    def stage_disambiguate_string(self) -> dict[str, Any]:
        """阶段 2：字符串基线消歧。"""
        return self.resolve("string")

    def stage_disambiguate_context(self) -> dict[str, Any]:
        """阶段 3：基于上下文的 LLM 消歧。"""
        return self.resolve("context")

    def stage_generate_triples(self) -> dict[str, Any]:
        """阶段 4：以两种消歧方法选中的实体为种子，用 LLM 生成三元组。"""
        candidates = self.ensure("collect-candidates")
        lookup = {
            c["entity_id"]: Candidate.model_validate(c)
            for row in candidates.values()
            for c in row["candidates"]
        }
        # 汇总两个消歧阶段的选中实体，并记录其来自哪些案例（resolution_links）
        seeds: dict[str, list[dict[str, str]]] = {}
        for method in ("string", "context"):
            for case_id, row in self.ensure("disambiguate-" + method).items():
                if row["selected_entity_id"]:
                    seeds.setdefault(row["selected_entity_id"], []).append(
                        {"method": method, "case_id": case_id}
                    )
        result = {}
        for qid, links in sorted(seeds.items()):

            def compute(qid: str = qid) -> dict[str, Any]:
                try:
                    triples, duplicates = generate(
                        lookup[qid],
                        self.cfg,
                        self.client,
                        self.provider(self.cfg.generator),
                        self.cfg.generator,
                    )
                    return {
                        "status": "ok",
                        "entity_id": qid,
                        "duplicates": duplicates,
                        # 每条三元组分配确定性 ID（内容哈希前缀），便于去重与追溯
                        "triples": [
                            {
                                "triple_id": "t-" + digest([qid, t.model_dump()])[:20],
                                "triple": t.model_dump(),
                            }
                            for t in triples
                        ],
                    }
                except (ValueError, RuntimeError) as exc:
                    self.failures.append(
                        {"stage": "generate", "entity_id": qid, "type": type(exc).__name__}
                    )
                    return {
                        "status": "failed",
                        "entity_id": qid,
                        "triples": [],
                        "error": type(exc).__name__,
                    }

            row = self.item("generate", qid, compute)
            result[qid] = {**row, "resolution_links": links}
        return result

    def stage_retrieve_evidence(self) -> dict[str, Any]:
        """阶段 5：为每条生成的三元组检索证据段落（Wikipedia）。"""
        result = {}
        for qid, generation in self.ensure("generate-triples").items():
            for row in generation["triples"]:

                def compute(qid: str = qid, row: dict[str, Any] = row) -> dict[str, Any]:
                    try:
                        passages = self.retriever.retrieve(
                            qid, Triple.model_validate(row["triple"])
                        )
                        return {
                            "status": "ok",
                            "passages": [p.model_dump(mode="json") for p in passages],
                        }
                    except (ValueError, RuntimeError) as exc:
                        self.failures.append(
                            {
                                "stage": "retrieve",
                                "triple_id": row["triple_id"],
                                "type": type(exc).__name__,
                            }
                        )
                        return {"status": "failed", "passages": [], "error": type(exc).__name__}

                result[row["triple_id"]] = self.item("evidence", row["triple_id"], compute)
        return result

    def stage_judge(self) -> dict[str, Any]:
        """阶段 6：对每条三元组做事实性判定，并生成人工标注模板与盲评包。"""
        evidence = self.ensure("retrieve-evidence")
        result = {}
        template = []
        for qid, generation in self.ensure("generate-triples").items():
            for row in generation["triples"]:
                tid = row["triple_id"]
                passages = [Evidence.model_validate(p) for p in evidence[tid]["passages"]]

                def compute(
                    row: dict[str, Any] = row, passages: list[Evidence] = passages, tid: str = tid
                ) -> dict[str, Any]:
                    try:
                        prediction, supplied = judge(
                            Triple.model_validate(row["triple"]),
                            passages,
                            self.client,
                            self.provider(self.cfg.judge),
                            self.cfg.judge,
                            self.cfg.evidence_max_chars,
                        )
                        return {
                            "status": "ok",
                            "judgment": prediction.model_dump(),
                            "supplied_evidence": [p.model_dump(mode="json") for p in supplied],
                        }
                    except (ValueError, RuntimeError) as exc:
                        self.failures.append(
                            {"stage": "judge", "triple_id": tid, "type": type(exc).__name__}
                        )
                        return {
                            "status": "failed",
                            "judgment": None,
                            "supplied_evidence": [],
                            "error": type(exc).__name__,
                        }

                result[tid] = {
                    **self.item("judge", digest([tid, evidence[tid]]), compute),
                    "triple": row["triple"],
                    "entity_id": qid,
                    "resolution_links": generation["resolution_links"],
                }
                # 为每条三元组预填人工标注模板（三元组与证据哈希用于去重追溯）
                annotation = Annotation(
                    triple_id=tid,
                    evidence_sha256=digest(result[tid]["supplied_evidence"]),
                    triple_sha256=digest(row["triple"]),
                )
                template.append(annotation.model_dump(mode="json"))
        write_jsonl_new(self.path / "annotations.template.jsonl", template)
        # Blinded review packet excludes judge decisions, confidence, and rationale.
        # 盲评包：不含模型判定结果、置信度与理由，避免影响人工标注者。
        write_new(
            self.path / "annotation_packet.json",
            {
                tid: {
                    "triple": r["triple"],
                    "entity_id": r["entity_id"],
                    "evidence": r["supplied_evidence"],
                    "mode": self.cfg.mode,
                }
                for tid, r in result.items()
            },
        )
        return result

    def stage_evaluate(self) -> dict[str, Any]:
        """阶段 7：对照人工标注评估模型判定（import 在函数内，避免启动时依赖）。"""
        from .evaluation.evaluate import evaluate

        return evaluate(self)

    def stage_build_report(self) -> dict[str, Any]:
        """阶段 8：基于评估结果生成报告。"""
        from .reporting.report import build_report

        return build_report(self.path, self.ensure("evaluate"), self.cfg.mode)
