"""Small UI adapter over existing artifacts. Human edits never rewrite a run."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from ..config import load_config
from ..dataset.validate_cases import load_cases
from ..evaluation.judge_metrics import agreement
from ..models import Annotation, EntityCase
from ..pipeline import Pipeline
from ..storage import digest, now, read_json, read_jsonl, write_new

REVIEW_FIELDS = {"verification_status", "verified_by", "verified_at"}


def replace_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomic save for editable human files only; experiment artifacts stay immutable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Workbench:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.lock = threading.RLock()

    def run_path(self, run: str) -> Path:
        if not re.fullmatch(r"(?:mock|real)/[A-Za-z0-9_-]+", run):
            raise ValueError("请选择列表中的实验记录")
        path = (self.root / "results" / run).resolve()
        if not path.is_relative_to(self.root / "results") or not (path / "manifest.json").is_file():
            raise ValueError("实验记录不存在")
        return path

    def runs(self) -> list[dict[str, Any]]:
        rows = []
        for path in (self.root / "results").glob("*/*/manifest.json"):
            if not (path.parent / "evaluate.json").exists():
                continue
            try:
                manifest = read_json(path)
                completion = read_json(path.parent / "completion.json")
                rows.append(
                    {
                        "id": path.parent.relative_to(self.root / "results").as_posix(),
                        "mode": manifest["mode"],
                        "created_at": manifest["created_at"],
                        "status": completion["status"],
                        "n": read_json(path.parent / "evaluate.json")["candidates"]["recall_at_k"][
                            "denominator"
                        ],
                    }
                )
            except (ValueError, KeyError, FileNotFoundError):
                continue  # Incomplete runs are never presented as finished results.
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def cases(self, path: Path) -> list[dict[str, Any]]:
        if (path / "cases.json").exists():
            rows: list[dict[str, Any]] = read_json(path / "cases.json")
            return rows
        # Legacy runs did not save case snapshots. Do not quietly display modified gold data.
        manifest = read_json(path / "manifest.json")
        source = Path(manifest["config"]["dataset"])
        if not any(
            source.resolve().is_relative_to(folder)
            for folder in (self.root / "data", self.root / "tests/fixtures")
        ):
            raise ValueError("旧实验没有可用的案例快照，请运行一次新的离线演示")
        if (
            hashlib.sha256(source.read_bytes()).hexdigest()
            != manifest["input_checksums"]["dataset"]
        ):
            raise ValueError("旧实验的数据已改变，请运行新的离线演示；旧结果仍保留")
        return read_jsonl(source)[: manifest["config"].get("case_limit")]

    def overview(self, run: str) -> dict[str, Any]:
        path = self.run_path(run)
        return {
            "id": run,
            "cases": self.cases(path),
            "metrics": read_json(path / "evaluate.json"),
            "string": read_json(path / "disambiguate-string.json"),
            "context": read_json(path / "disambiguate-context.json"),
            "candidates": read_json(path / "collect-candidates.json"),
            "comparison": self.comparison(run),
        }

    def trace(self, run: str, case_id: str) -> dict[str, Any]:
        path = self.run_path(run)
        case = next((c for c in self.cases(path) if c["case_id"] == case_id), None)
        if case is None:
            raise ValueError("案例不存在")
        claims = []
        for tid, row in read_json(path / "judge.json").items():
            if any(link["case_id"] == case_id for link in row["resolution_links"]):
                claims.append(
                    {
                        "triple_id": tid,
                        "triple": row["triple"],
                        "entity_id": row["entity_id"],
                        "links": row["resolution_links"],
                        "evidence": row["supplied_evidence"],
                        # Real review remains blind; result details are exposed after review only.
                        "judgment": row["judgment"] if run.startswith("mock/") else None,
                    }
                )
        return {"case": case, "claims": claims}

    def case_queue(self, scope: str) -> dict[str, Any]:
        if scope not in {"pilot", "starter"}:
            raise ValueError("请选择 5 例试跑或 12 例扩展")
        file = self.root / f"data/benchmark/{scope}_cases.jsonl"
        rows = [c.model_dump(mode="json") for c in load_cases(file)]
        return {
            "scope": scope,
            "file": str(file.relative_to(self.root)),
            "rows": [{**r, "revision": digest(r)} for r in rows],
            "reviewed": sum(r["verification_status"] == "human_verified" for r in rows),
        }

    def verify_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        reviewer = str(payload.get("reviewer", "")).strip()
        if not reviewer or len(reviewer) > 100 or payload.get("confirmed") is not True:
            raise ValueError("请填写复核人，并确认已查看来源、核对实体含义")
        scope = str(payload.get("scope", "pilot"))
        with self.lock:
            queue = self.case_queue(scope)
            current = next(
                (r for r in queue["rows"] if r["case_id"] == payload.get("case_id")), None
            )
            if current is None or current["revision"] != payload.get("revision"):
                raise ValueError("记录已变化，请刷新后重新核对")
            original = {k: v for k, v in current.items() if k != "revision"}
            changes = {
                "verification_status": "human_verified",
                "verified_by": reviewer,
                "verified_at": now(),
            }
            # Share reviews only across identical pilot/starter cases.
            saved = []
            for target in ("pilot", "starter"):
                file = self.root / f"data/benchmark/{target}_cases.jsonl"
                rows = read_jsonl(file)
                for i, row in enumerate(rows):
                    same = {k: v for k, v in row.items() if k not in REVIEW_FIELDS} == {
                        k: v for k, v in original.items() if k not in REVIEW_FIELDS
                    }
                    if same:
                        updated = EntityCase.model_validate({**row, **changes}).model_dump(
                            mode="json"
                        )
                        write_new(
                            self.root / "data/reviews/entity_history" / f"{uuid.uuid4().hex}.json",
                            {
                                "file": str(file.relative_to(self.root)),
                                "before": row,
                                "after": updated,
                            },
                        )
                        rows[i] = updated
                        replace_jsonl(file, rows)
                        saved.append(str(file.relative_to(self.root)))
                        break
            return {"saved": saved, "message": "已保存你的人工确认；原始 40 例和历史实验未修改"}

    def annotation_path(self, run: str) -> Path:
        self.run_path(run)
        return self.root / "data/reviews" / run / "human_annotations.jsonl"

    def annotations(self, run: str) -> list[dict[str, Any]]:
        file = self.annotation_path(run)
        return read_jsonl(file) if file.exists() else []

    def sample_ids(self, run: str) -> list[str]:
        packet = read_json(self.run_path(run) / "annotation_packet.json")
        # Fixed uniform sample, not selected for agreement with the judge.
        return random.Random(42).sample(sorted(packet), min(20, len(packet)))

    def review(self, run: str) -> dict[str, Any]:
        packet = read_json(self.run_path(run) / "annotation_packet.json")
        ids = self.sample_ids(run)
        saved = {r["triple_id"]: r for r in self.annotations(run)}
        return {
            "rows": [
                {"triple_id": tid, **packet[tid], "annotation": saved.get(tid)} for tid in ids
            ],
            "sample_size": len(ids),
            "population_size": len(packet),
            "seed": 42,
            "completed": sum(tid in saved for tid in ids),
            "file": str(self.annotation_path(run).relative_to(self.root)),
        }

    def annotate(self, run: str, payload: dict[str, Any]) -> dict[str, Any]:
        if run.startswith("mock/"):
            raise ValueError("演示数据不用人工标注；请先选择已完成的真实实验")
        path = self.run_path(run)
        tid = str(payload.get("triple_id", ""))
        if tid not in self.sample_ids(run):
            raise ValueError("该记录不在本次固定的 20 条抽样内")
        packet = read_json(path / "annotation_packet.json")[tid]
        if not str(payload.get("annotator_id", "")).strip():
            raise ValueError("请填写复核人")
        ids = payload.get("evidence_ids", [])
        if not isinstance(ids, list) or not set(ids) <= {
            e["passage_id"] for e in packet["evidence"]
        }:
            raise ValueError("只能选择本条记录提供的证据")
        if payload.get("human_label") is None:
            raise ValueError("请选择支持、矛盾或证据不足；尚未阅读请跳过")
        annotation = Annotation.model_validate(
            {
                "triple_id": tid,
                "human_label": payload.get("human_label"),
                "annotator_notes": payload.get("annotator_notes", ""),
                "evidence_ids": ids,
                "annotator_id": payload["annotator_id"],
                "annotated_at": now(),
                "triple_sha256": digest(packet["triple"]),
                "evidence_sha256": digest(packet["evidence"]),
            }
        )
        with self.lock:
            rows = self.annotations(run)
            previous = next((r for r in rows if r["triple_id"] == tid), None)
            file = self.annotation_path(run)
            write_new(
                file.parent / "history" / f"{uuid.uuid4().hex}.json",
                {"before": previous, "after": annotation.model_dump(mode="json")},
            )
            rows = [r for r in rows if r["triple_id"] != tid]
            rows.append(annotation.model_dump(mode="json"))
            replace_jsonl(file, sorted(rows, key=lambda r: r["triple_id"]))
            return {
                "message": "已保存；复核对照会自动更新",
                "file": str(file.relative_to(self.root)),
            }

    def comparison(self, run: str) -> dict[str, Any]:
        path = self.run_path(run)
        judgments = read_json(path / "judge.json")
        rows = self.annotations(run)
        golden: list[str] = []
        predicted: list[str | None] = []
        pairs: list[dict[str, Any]] = []
        for row in rows:
            annotation = Annotation.model_validate(row)
            target = judgments[annotation.triple_id]
            if annotation.triple_sha256 != digest(
                target["triple"]
            ) or annotation.evidence_sha256 != digest(target["supplied_evidence"]):
                raise ValueError("人工记录与当前证据不匹配，请保留原文件后重新核对")
            if annotation.human_label is None:
                continue
            pred = target["judgment"]["label"] if target["judgment"] else None
            golden.append(annotation.human_label)
            predicted.append(pred)
            pairs.append(
                {
                    "triple_id": annotation.triple_id,
                    "human": annotation.human_label,
                    "judge": pred,
                    "triple": target["triple"],
                }
            )
        return {
            "metrics": agreement(golden, predicted),
            "pairs": pairs,
            "sample_size": len(self.sample_ids(run)),
            "note": "小样本探索性检查，不证明整体可靠性",
        }

    def demo(self) -> dict[str, Any]:
        with self.lock:
            cfg = load_config(self.root / "configs/learn.yaml")
            if cfg.mode != "mock" or not cfg.offline:
                raise ValueError("界面只允许离线演示，请保持 learn.yaml 为 mock + offline")
            output = Pipeline(cfg).execute()
            return {"run": output.relative_to(self.root / "results").as_posix()}
