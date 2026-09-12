"""阶段 7（evaluate）：汇总全部阶段产物与人工标注，计算各维度评测指标。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import Annotation
from ..storage import digest, read_jsonl
from .entity_metrics import candidate_metrics, entity_metrics, rate
from .error_analysis import errors
from .judge_metrics import agreement, factuality
from .operational_metrics import operational

if TYPE_CHECKING:
    from ..pipeline import Pipeline


def evaluate(p: Pipeline) -> dict[str, Any]:
    """评估一次运行的完整结果，返回多维度指标字典（写入 evaluate.json）。

    流程概览：
    1. 读取各阶段产物（候选、两种消歧、生成、判定、证据）与人工标注文件；
    2. 严格校验每一条人工标注（ID 唯一、哈希绑定版本、证据引用合法）；
    3. 分层计算指标：候选召回、实体消歧、生成质量、事实性、人机一致率、
       费用/调用次数、错误分析、分歧明细。
    """
    candidates = p.ensure("collect-candidates")
    predictions = {m: p.ensure("disambiguate-" + m) for m in ("string", "context")}
    generation = p.ensure("generate-triples")
    judgments = p.ensure("judge")
    evidence = p.ensure("retrieve-evidence")
    # 人工标注文件（可能不存在）；每行必须是合法的 Annotation 模型
    annotations = read_jsonl(p.cfg.annotations) if p.cfg.annotations.exists() else []
    human = {}
    seen = set()
    excluded = 0
    for raw in annotations:
        annotation = Annotation.model_validate(raw)
        if annotation.triple_id in seen:
            raise ValueError("Duplicate annotation triple ID")
        seen.add(annotation.triple_id)
        if annotation.human_label is None:
            continue  # 未完成的标注跳过，不参与指标计算
        tid = annotation.triple_id
        if tid not in judgments:
            excluded += 1  # 标注的三元组不在本次运行内，单独计数而非报错
            continue
        # 哈希校验：标注必须绑定到同一份三元组/证据快照，防止标的版本错位
        if annotation.triple_sha256 != digest(
            judgments[tid]["triple"]
        ) or annotation.evidence_sha256 != digest(judgments[tid]["supplied_evidence"]):
            raise ValueError("Annotation is bound to a different triple/evidence snapshot")
        # 标注引用的证据必须是盲评包实际提供的证据
        if not set(annotation.evidence_ids) <= {
            e["passage_id"] for e in judgments[tid]["supplied_evidence"]
        }:
            raise ValueError("Annotation cites unknown evidence")
        human[tid] = annotation.model_dump(mode="json")
    # 金标准标签 vs 模型判定标签（用于一致率）
    gold = [row["human_label"] for row in human.values()]
    pred = [
        judgments[tid]["judgment"]["label"] if judgments[tid]["judgment"] else None for tid in human
    ]
    # 全部判定的标签列表（用于整体事实性统计）
    labels = [r["judgment"]["label"] if r["judgment"] else None for r in judgments.values()]
    # 生成阶段的基础统计：重复三元组数、总数、成功的实体数
    duplicates = sum(r.get("duplicates", 0) for r in generation.values())
    total = sum(len(r["triples"]) for r in generation.values())
    valid = sum(r["status"] == "ok" for r in generation.values())
    per_method_factuality = {}
    for method, resolution in predictions.items():
        # 由该消歧方法间接产生的三元组（通过 resolution_links 追溯）
        linked = [
            (tid, row)
            for tid, row in judgments.items()
            if any(link["method"] == method for link in row["resolution_links"])
        ]
        method_labels = [row["judgment"]["label"] if row["judgment"] else None for _, row in linked]
        # 消歧选对实体的案例集合（对照金标准 gold_entity_id）
        correct_cases = {
            c.case_id
            for c in p.cases
            if resolution[c.case_id]["selected_entity_id"] == c.gold_entity_id
        }
        linked_claims = [
            (row, link)
            for _, row in linked
            for link in row["resolution_links"]
            if link["method"] == method
        ]
        # 联合指标：实体选对 且 三元组判定为"蕴含" 且 来自该方法的链接
        joint = sum(
            bool(
                row["judgment"]
                and row["judgment"]["label"] == "entailed"
                and link["case_id"] in correct_cases
            )
            for row, link in linked_claims
        )
        per_method_factuality[method] = {
            "canonical_unique_triples": factuality(method_labels),
            "joint_correct_entity_and_entailed_per_mention_triple": rate(joint, len(linked_claims)),
            "resolved_case_coverage": rate(
                sum(r["selected_entity_id"] is not None for r in resolution.values()), len(p.cases)
            ),
        }
    return {
        "mode": p.cfg.mode,
        # mock 是合成的软件自检；real 才构成研究性评测
        "interpretation": "Synthetic software check"
        if p.cfg.mode == "mock"
        else "Research evaluation; inspect human verification coverage",
        "human_verified_cases": rate(
            sum(c.verification_status == "human_verified" for c in p.cases), len(p.cases)
        ),
        "candidates": candidate_metrics(p.cases, candidates, p.cfg.candidate_k),
        "entity": {m: entity_metrics(p.cases, rows) for m, rows in predictions.items()},
        "generation": {
            "valid_entity_output_rate": rate(valid, len(generation)),
            "duplicate_triple_rate": rate(duplicates, total + duplicates),
            "mean_triples_per_seed": rate(total, len(generation)),
        },
        "factuality": factuality(labels),
        "factuality_by_method": per_method_factuality,
        "public_retrieval_operations": {
            "events": p.public.http.events if p.public else [],
            "n": len(p.public.http.events) if p.public else 0,
        },
        "judge_agreement": agreement(gold, pred),
        "annotation_coverage": rate(len(human), len(judgments)),
        "out_of_run_annotations": excluded,
        "operations_this_invocation": operational(p.client.events),
        "operations_by_task": {
            task: operational([e for e in p.client.events if e["task"] == task])
            for task in ("resolve", "generate", "judge")
        },
        "error_analysis": errors(p.cases, candidates, predictions, judgments, human, evidence),
        # 人机分歧明细：人工标签与模型判定不一致（或模型失败）的逐条记录
        "disagreements": [
            {
                "triple_id": tid,
                "human": human[tid]["human_label"],
                "judge": judgments[tid]["judgment"],
            }
            for tid in human
            if judgments[tid]["judgment"] is None
            or judgments[tid]["judgment"]["label"] != human[tid]["human_label"]
        ],
    }
