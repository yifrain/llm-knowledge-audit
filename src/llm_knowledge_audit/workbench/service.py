"""Small UI adapter over existing artifacts. Human edits never rewrite a run.

现有运行工件之上的轻量 UI 适配层：
- 只读地呈现 results/ 里的实验记录；
- 人工编辑（案例确认、三元组标注）只写 data/reviews/ 与基准案例文件，
  任何历史实验运行的结果都保持不可变、永不被改写。
"""

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
from .runs import ConsoleError, RunController, read_if

# 人工复核字段集合：比对两个案例是否"同一案例"时忽略这些字段
REVIEW_FIELDS = {"verification_status", "verified_by", "verified_at"}


def replace_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomic save for editable human files only; experiment artifacts stay immutable.

    仅用于可编辑的人工文件（基准案例、标注文件）的原子保存：
    写临时文件 + fsync 后用 os.replace 原子替换，绝不用于实验工件。
    """
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


class Workbench(RunController):
    def __init__(self, root: Path):
        super().__init__(root.resolve())
        # 复核/标注的写操作加锁，避免并发读写同一个人工文件
        self.lock = threading.RLock()

    def run_path(self, run: str) -> Path:
        """把前端传来的 run 标识解析为结果目录，严格校验防路径穿越。

        只接受 `mock/xxx` 或 `real/xxx` 格式（安全字符集），
        且目录必须位于 results/ 下并包含 manifest.json。
        """
        if not re.fullmatch(r"(?:mock|real)/[A-Za-z0-9_-]+", run):
            raise ConsoleError("invalid_path")
        path = (self.root / "results" / run).resolve()
        if not path.is_relative_to(self.root / "results") or not (path / "manifest.json").is_file():
            raise ConsoleError("not_found")
        return path

    def runs(self) -> list[dict[str, Any]]:
        rows = []
        for path in (self.root / "results").glob("*/*/manifest.json"):
            try:
                rows.append(
                    self.progress(path.parent.relative_to(self.root / "results").as_posix())
                )
            except (ValueError, KeyError, OSError):
                continue
        for path in (self.root / "data/reviews/jobs").glob("*/queued.json"):
            record = self.job(path.parent.name)
            if not record.get("run"):
                rows.append(record)
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def cases(self, path: Path) -> list[dict[str, Any]]:
        """读取某次运行的案例快照。

        新运行直接读运行目录里的 cases.json（不可变快照）；
        旧运行没有快照时回退到源数据集文件，但必须先校验内容哈希，
        防止悄悄展示已被修改的金标准数据。
        """
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
            raise ConsoleError("snapshot_unavailable")
        if (
            hashlib.sha256(source.read_bytes()).hexdigest()
            != manifest["input_checksums"]["dataset"]
        ):
            raise ConsoleError("snapshot_changed")
        return read_jsonl(source)[: manifest["config"].get("case_limit")]

    def blind_complete(self, run: str) -> bool:
        if run.startswith("mock/"):
            return True
        path = self.run_path(run)
        if not (path / "annotation_packet.json").exists():
            return False
        packet = read_json(path / "annotation_packet.json")
        valid = self.valid_annotations(run, packet)
        return set(self.sample_ids(run)) <= set(valid)

    def valid_annotations(self, run: str, packet: dict[str, Any]) -> dict[str, Any]:
        valid = {}
        for raw in self.annotations(run):
            row = Annotation.model_validate(raw)
            target = packet.get(row.triple_id)
            if (
                target
                and row.human_label is not None
                and row.triple_sha256 == digest(target["triple"])
                and row.evidence_sha256 == digest(target["evidence"])
            ):
                valid[row.triple_id] = row.model_dump(mode="json")
        return valid

    def overview(self, run: str) -> dict[str, Any]:
        path = self.run_path(run)
        metrics = read_if(path / "evaluate.json", {})
        unlocked = self.blind_complete(run)
        if not unlocked:
            # Allowlist excludes aggregate labels, joint scores, disagreements and error flags.
            metrics = {
                k: v
                for k, v in metrics.items()
                if k
                in {
                    "mode",
                    "human_verified_cases",
                    "candidates",
                    "entity",
                    "generation",
                    "operations_this_invocation",
                    "operations_by_task",
                    "annotation_coverage",
                }
            }
        return {
            "id": run,
            "progress": self.progress(run),
            "blind_complete": unlocked,
            "cases": self.cases(path),
            "metrics": metrics,
            "string": read_if(path / "disambiguate-string.json", {}),
            "context": read_if(path / "disambiguate-context.json", {}),
            "candidates": read_if(path / "collect-candidates.json", {}),
            "comparison": self.comparison(run) if unlocked else None,
        }

    def trace(self, run: str, case_id: str) -> dict[str, Any]:
        """单案例追踪：找出与该案例关联的全部三元组及其证据。

        real 运行保持盲评——判定结果（judgment）在人工复核前不外露。
        """
        path = self.run_path(run)
        case = next((c for c in self.cases(path) if c["case_id"] == case_id), None)
        if case is None:
            raise ConsoleError("not_found")
        claims = []
        for tid, row in read_if(path / "judge.json", {}).items():
            if any(link["case_id"] == case_id for link in row["resolution_links"]):
                claims.append(
                    {
                        "triple_id": tid,
                        "triple": row["triple"],
                        "entity_id": row["entity_id"],
                        "links": row["resolution_links"],
                        "evidence": row["supplied_evidence"],
                        # Real review remains blind; result details are exposed after review only.
                        "judgment": row["judgment"] if self.blind_complete(run) else None,
                    }
                )
        if not (path / "judge.json").exists():
            evidence = read_if(path / "retrieve-evidence.json", {})
            for qid, row in read_if(path / "generate-triples.json", {}).items():
                if any(link["case_id"] == case_id for link in row["resolution_links"]):
                    for triple in row["triples"]:
                        claims.append(
                            {
                                **triple,
                                "entity_id": qid,
                                "links": row["resolution_links"],
                                "judgment": None,
                                "evidence": evidence.get(triple["triple_id"], {}).get(
                                    "passages", []
                                ),
                            }
                        )
        return {"case": case, "claims": claims}

    def case_queue(self, scope: str) -> dict[str, Any]:
        """案例复核队列：pilot（5 例试跑）或 starter（12 例扩展）。

        每行附带内容哈希 revision，作为提交时的乐观锁版本号。
        """
        if scope not in {"pilot", "starter"}:
            raise ConsoleError("invalid_request")
        file = self.root / f"data/benchmark/{scope}_cases.jsonl"
        rows = [c.model_dump(mode="json") for c in load_cases(file)]
        return {
            "scope": scope,
            "file": str(file.relative_to(self.root)),
            "rows": [{**r, "revision": digest(r)} for r in rows],
            "reviewed": sum(r["verification_status"] == "human_verified" for r in rows),
        }

    def verify_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        """保存一次人工案例确认：校验复核人、确认勾选与 revision 防陈旧写入。

        同一案例同时存在于 pilot 与 starter 队列时，两处同步更新；
        每次覆盖前都把旧记录写入 entity_history 审计目录。
        """
        reviewer = str(payload.get("reviewer", "")).strip()
        if not reviewer or len(reviewer) > 100 or payload.get("confirmed") is not True:
            raise ConsoleError("confirmation_required")
        scope = str(payload.get("scope", "pilot"))
        with self.lock:
            self._busy()
            queue = self.case_queue(scope)
            current = next(
                (r for r in queue["rows"] if r["case_id"] == payload.get("case_id")), None
            )
            if current is None or current["revision"] != payload.get("revision"):
                raise ConsoleError("review_stale")
            original = {k: v for k, v in current.items() if k != "revision"}
            overrides = payload.get("overrides", {})
            if not isinstance(overrides, dict) or set(overrides) - {
                "gold_entity_id",
                "gold_label",
                "gold_description",
                "source_url",
            }:
                raise ConsoleError("invalid_request")
            changes = {
                **overrides,
                "verification_status": "human_verified",
                "verified_by": reviewer,
                "verified_at": now(),
            }
            # Share reviews only across identical pilot/starter cases.
            # 只在 pilot/starter 两队列中"内容完全相同"的案例之间共享复核结果。
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
                                "method": payload.get("review_method", "individual_confirmation"),
                                "batch_id": payload.get("batch_id"),
                                "reviewer": reviewer,
                                "at": changes["verified_at"],
                                "before": row,
                                "after": updated,
                            },
                        )
                        rows[i] = updated
                        replace_jsonl(file, rows)
                        saved.append(str(file.relative_to(self.root)))
                        break
            return {"saved": saved, "message": "saved"}

    def annotation_path(self, run: str) -> Path:
        """某次运行的人工标注文件路径（在 data/reviews/ 下，不触碰实验工件）。"""
        self.run_path(run)
        return self.root / "data/reviews" / run / "human_annotations.jsonl"

    def annotations(self, run: str) -> list[dict[str, Any]]:
        """读取某次运行已保存的人工标注。"""
        file = self.annotation_path(run)
        return read_jsonl(file) if file.exists() else []

    def sample_ids(self, run: str) -> list[str]:
        """固定随机抽样（seed 42，最多 20 条），而非挑选与判定一致的记录。"""
        packet = read_json(self.run_path(run) / "annotation_packet.json")
        # Fixed uniform sample, not selected for agreement with the judge.
        return random.Random(42).sample(sorted(packet), min(20, len(packet)))

    def review(self, run: str) -> dict[str, Any]:
        """盲评界面数据：抽样三元组 + 证据 + 已有标注（不含模型判定结果）。"""
        packet = read_json(self.run_path(run) / "annotation_packet.json")
        ids = self.sample_ids(run)
        saved = self.valid_annotations(run, packet)
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
        """保存一条三元组人工标注（仅限 real 运行的固定抽样内记录）。

        校验：不在抽样内、证据不在盲评包提供范围内、未选标签都拒绝；
        同一三元组重复标注视为修订：旧记录写入 history，新记录替换原条目。
        """
        if run.startswith("mock/"):
            raise ConsoleError("mock_review_disabled")
        path = self.run_path(run)
        tid = str(payload.get("triple_id", ""))
        if tid not in self.sample_ids(run):
            raise ConsoleError("outside_sample")
        packet = read_json(path / "annotation_packet.json")[tid]
        if not str(payload.get("annotator_id", "")).strip():
            raise ConsoleError("reviewer_required")
        ids = payload.get("evidence_ids", [])
        if not isinstance(ids, list) or not set(ids) <= {
            e["passage_id"] for e in packet["evidence"]
        }:
            raise ConsoleError("invalid_evidence")
        if payload.get("human_label") is None:
            raise ConsoleError("label_required")
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
            # 先写审计历史（before/after），再替换标注文件中的该条记录
            write_new(
                file.parent / "history" / f"{uuid.uuid4().hex}.json",
                {"before": previous, "after": annotation.model_dump(mode="json")},
            )
            rows = [r for r in rows if r["triple_id"] != tid]
            rows.append(annotation.model_dump(mode="json"))
            replace_jsonl(file, sorted(rows, key=lambda r: r["triple_id"]))
            return {
                "message": "saved",
                "file": str(file.relative_to(self.root)),
            }

    def comparison(self, run: str) -> dict[str, Any]:
        """人工标注 vs 模型判定的一致性对照。

        先校验标注的哈希与当前三元组/证据一致（防止标的版本和看的版本不同），
        再计算两者标签的一致率。
        """
        if not self.blind_complete(run):
            return {"locked": True, "pairs": [], "metrics": None}
        path = self.run_path(run)
        judgments = read_if(path / "judge.json", {})
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
                raise ConsoleError("annotation_mismatch")
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
            "sample_size": len(self.sample_ids(run))
            if (path / "annotation_packet.json").exists()
            else 0,
            "note": "exploratory_sample",
        }

    def demo(self) -> dict[str, Any]:
        """运行一次新的离线 mock 演示（唯一的"运行"入口，且强制离线免费）。"""
        with self.lock:
            cfg = load_config(self.root / "configs/learn.yaml")
            if cfg.mode != "mock" or not cfg.offline:
                raise ConsoleError("mock_offline_required")
            output = Pipeline(cfg).execute()
            return {"run": output.relative_to(self.root / "results").as_posix()}

    def verify_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Prevalidate all revisions, then record an explicitly batch-origin confirmation."""
        with self.lock:
            self._busy()
            if (
                payload.get("confirmed") is not True
                or not str(payload.get("reviewer", "")).strip()
                or len(str(payload.get("reviewer", ""))) > 100
            ):
                raise ConsoleError("confirmation_required")
            queue = self.case_queue(str(payload.get("scope", "pilot")))
            current = {r["case_id"]: r for r in queue["rows"]}
            rows = payload.get("rows")
            if not isinstance(rows, list) or not rows:
                raise ConsoleError("invalid_request")
            if len({r["case_id"] for r in rows}) != len(rows):
                raise ConsoleError("invalid_request")
            for row in rows:
                if row.get("case_id") not in current or current[row["case_id"]][
                    "revision"
                ] != row.get("revision"):
                    raise ConsoleError("review_stale")
                overrides = row.get("overrides", {})
                if not isinstance(overrides, dict) or set(overrides) - {
                    "gold_entity_id",
                    "gold_label",
                    "gold_description",
                    "source_url",
                }:
                    raise ConsoleError("invalid_request")
                EntityCase.model_validate(
                    {
                        **{k: v for k, v in current[row["case_id"]].items() if k != "revision"},
                        **overrides,
                    }
                )
            batch = uuid.uuid4().hex
            write_new(
                self.root / "data/reviews/entity_history" / (batch + ".json"),
                {
                    "method": "batch_confirmation",
                    "reviewer": payload["reviewer"],
                    "at": now(),
                    "scope": queue["scope"],
                    "case_ids": [r["case_id"] for r in rows],
                },
            )
            for row in rows:
                self.verify_case(
                    {
                        **row,
                        "scope": queue["scope"],
                        "confirmed": True,
                        "reviewer": payload["reviewer"],
                        "batch_id": batch,
                        "review_method": "batch_confirmation",
                    }
                )
            return {"saved": len(rows), "batch_id": batch}

    def export(self, run: str, name: str) -> tuple[bytes, str]:
        """Explicit downloads only. Sensitive reports cannot bypass the blind-review gate."""
        path = self.run_path(run)
        safe = {"manifest.json", "cases.json", "annotation_packet.json"}
        gated = {"evaluate.json", "report.md"}
        if name == "summary.json":
            return json.dumps(self.overview(run), ensure_ascii=False, indent=2).encode(), name
        if name == "review-comparison.json":
            if not self.blind_complete(run):
                raise ConsoleError("blind_locked")
            return json.dumps(self.comparison(run), indent=2).encode(), name
        if name == "figures.zip":
            if not self.blind_complete(run):
                raise ConsoleError("blind_locked")
            if run.startswith("mock/"):
                raise ConsoleError("mock_figures_disabled")
            import io
            import zipfile

            from ..reporting.plots import plot_results

            # Plotting uses fresh temporary exports; the original run is never touched.
            with self.lock, tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                plot_results(folder, read_json(path / "evaluate.json"))
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                    for item in sorted(folder.rglob("*")):
                        if item.is_file():
                            archive.write(item, item.relative_to(folder))
                return output.getvalue(), name
        if name not in safe | gated:
            raise ConsoleError("not_found")
        if name in gated and not self.blind_complete(run):
            raise ConsoleError("blind_locked")
        return (path / name).read_bytes(), name
