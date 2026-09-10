"""Strict public data contracts; null annotations never imply a human decision.

严格的数据契约模型：字段为 None 不代表人工已经作出决策（例如未完成的人工复核）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# QID：维基数据（Wikidata）实体 ID，形如 Q1、Q42
QID = Annotated[str, Field(pattern=r"^Q[1-9][0-9]*$")]
# Text：非空文本，长度上限 12000 字符
Text = Annotated[str, Field(min_length=1, max_length=12000)]
# Label：三元组的 NLI 三分类标签——蕴含 / 矛盾 / 信息不足
Label = Literal["entailed", "contradicted", "not_enough_information"]


class Model(BaseModel):
    """所有数据模型的基类：禁止多余字段、自动去除字符串首尾空白。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Triple(Model):
    """生成的三元组（主语—谓语—宾语）。

    object_type 用于区分宾语是实体还是字面量（literal）。
    """

    subject: Text
    predicate: Text
    object: Text
    object_type: Literal["entity", "literal"]


class SourceTriple(Model):
    """来源文本中的三元组（不带宾语类型标注）。"""

    subject: Text
    predicate: Text
    object: Text


class EntityCase(Model):
    """实体消歧/对齐的评测案例。

    case_type 区分两类案例：
    - homonym：同名异义（同一表面形式对应不同实体）；
    - synonym：同义异名（不同表面形式对应同一实体）。
    gold_* 是拟定答案；只有 human_verified 后才表示已由人工核对。
    """

    case_id: Text
    case_type: Literal["homonym", "synonym"]
    domain: Text
    group_id: Text
    surface_form: Text
    context: Text
    source_triple: SourceTriple
    gold_entity_id: QID
    gold_label: Text
    gold_description: Text
    source_url: Text
    retrieved_at: datetime | None = None
    verification_status: Literal["pending_human_review", "human_verified"]
    verified_by: str | None = None
    verified_at: datetime | None = None

    @model_validator(mode="after")
    def check_review(self) -> EntityCase:
        """已通过人工复核的案例必须包含复核人（verified_by）与复核时间（verified_at）。"""
        if self.verification_status == "human_verified":
            if not self.verified_by or self.verified_at is None:
                raise ValueError("Human verification requires reviewer and date")
        return self


class Candidate(Model):
    """候选实体（来自公开知识库，如 Wikidata）。"""

    entity_id: QID
    label: Text
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    source_url: Text
    retrieved_at: datetime | None = None


class StringCandidate(Model):
    """类型边界：baseline（纯字符串匹配）不能拿到描述和上下文。

    该类型刻意不包含 description/context 字段，防止信息泄露到基线方法中。
    """

    entity_id: QID
    label: Text
    aliases: list[str] = Field(default_factory=list)


class Resolution(Model):
    """实体消歧结果：选中的实体、置信度与简短理由。"""

    selected_entity_id: QID | None
    confidence: float = Field(ge=0, le=1)
    short_rationale: str = Field(max_length=600)


class Generation(Model):
    """模型生成的三元组列表（最多 15 条）。"""

    triples: list[Triple] = Field(max_length=15)


class Evidence(Model):
    """证据段落（如维基百科条目）。

    revision_id：来源的版本号，用于追溯；
    license：许可协议；
    synthetic：是否为合成数据（默认 False）。
    """

    passage_id: Text
    text: Text
    source_url: Text
    retrieved_at: datetime
    revision_id: str | None = None
    license: str
    synthetic: bool = False


class Judgment(Model):
    """模型对三元组的判定：标签、置信度、所依据的证据编号与理由。"""

    label: Label
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    short_rationale: str = Field(max_length=600)


class Annotation(Model):
    """人工标注：人类对三元组的标注结果。

    evidence_sha256 / triple_sha256：内容哈希，用于确保人工和模型比较的是相同三元组及证据。
    """

    triple_id: Text
    human_label: Label | None = None
    annotator_notes: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    annotator_id: str | None = None
    annotated_at: datetime | None = None
    evidence_sha256: str
    triple_sha256: str

    @model_validator(mode="after")
    def check_review(self) -> Annotation:
        """完成标注的约束：

        - 一旦给出 human_label，必须同时提供标注人（annotator_id）与标注时间（annotated_at）；
        - 蕴含/矛盾标签必须提供所依据的证据编号（信息不足除外）。
        """
        if self.human_label is not None:
            if not self.annotator_id or self.annotated_at is None:
                raise ValueError("A completed annotation needs annotator_id and annotated_at")
            if self.human_label != "not_enough_information" and not self.evidence_ids:
                raise ValueError("Entailed/contradicted annotations need evidence IDs")
        return self
