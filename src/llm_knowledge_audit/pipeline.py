"""A stage invocation always creates a new immutable run, including resume."""

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
        self.cases = load_cases(cfg.dataset)
        self.cases = self.cases[: cfg.case_limit]
        self.client = CallClient(cfg, approved)
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
        if resume and read_json(resume / "manifest.json")["signature"] != self.signature:
            raise ValueError("Resume rejected: config, source code, or input checksum changed")
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
        self.path = cfg.results_dir / cfg.mode / run_id
        self.path.mkdir(parents=True, exist_ok=False)
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=cfg.dataset.parent,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            commit = None
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
        self.reused: list[str] = []
        inherited_reservations: list[dict[str, Any]] = []
        if resume:
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
            if (resume / "items").exists():
                shutil.copytree(resume / "items", self.path / "items")
            if "judge" in self.reused:
                for name in ("annotations.template.jsonl", "annotation_packet.json"):
                    shutil.copyfile(resume / name, self.path / name)
            inherited_reservations = (
                read_json(resume / "inherited_budget.json")
                if (resume / "inherited_budget.json").exists()
                else []
            )
            inherited_reservations += [
                read_json(f) for f in (resume / "reservations").glob("*.json")
            ]
        self.client.reserved_usd = sum(r["reserved_usd"] for r in inherited_reservations)
        self.client.attempts = sum(r["attempts"] for r in inherited_reservations)
        self.client.reservation_dir = self.path / "reservations"
        # Separate immutable lineage artifact retains conservative reservations across resumes.
        write_new(self.path / "inherited_budget.json", inherited_reservations)
        self.failures: list[dict[str, Any]] = []
        self.retriever: EvidenceRetriever = MockEvidenceRetriever()
        self.public: Any = None
        if cfg.mode == "real":
            from .retrieval.wikidata import Wikidata
            from .retrieval.wikipedia import WikipediaRetriever

            self.public = Wikidata(cfg)
            self.retriever = WikipediaRetriever(self.public)

    def provider(self, model: LLMConfig) -> Provider:
        if model.provider == "mock":
            return MockProvider()
        from .providers.openai_compatible import OpenAICompatible

        return OpenAICompatible(model, self.cfg)

    def item(self, stage: str, key: str, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        path = self.path / "items" / stage / f"{digest(key)}.json"
        if path.exists():
            value: dict[str, Any] = read_json(path)
            return value
        before = len(self.client.events)
        value = compute()
        # Failed outputs are retained for audit but are not accepted as completed checkpoints.
        if value.get("status") != "failed":
            write_new(path, value)
        new_events = self.client.events[before:]
        if new_events:
            write_new(self.path / "telemetry" / f"{uuid.uuid4().hex}.json", new_events)
        return value

    def ensure(self, stage: str) -> Any:
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
        try:
            self.ensure(stage)
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
        return self.resolve("string")

    def stage_disambiguate_context(self) -> dict[str, Any]:
        return self.resolve("context")

    def stage_generate_triples(self) -> dict[str, Any]:
        candidates = self.ensure("collect-candidates")
        lookup = {
            c["entity_id"]: Candidate.model_validate(c)
            for row in candidates.values()
            for c in row["candidates"]
        }
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
                annotation = Annotation(
                    triple_id=tid,
                    evidence_sha256=digest(result[tid]["supplied_evidence"]),
                    triple_sha256=digest(row["triple"]),
                )
                template.append(annotation.model_dump(mode="json"))
        write_jsonl_new(self.path / "annotations.template.jsonl", template)
        # Blinded review packet excludes judge decisions, confidence, and rationale.
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
        from .evaluation.evaluate import evaluate

        return evaluate(self)

    def stage_build_report(self) -> dict[str, Any]:
        from .reporting.report import build_report

        return build_report(self.path, self.ensure("evaluate"), self.cfg.mode)
