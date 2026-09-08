"""Strict public data contracts; null annotations never imply a human decision."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QID = Annotated[str, Field(pattern=r"^Q[1-9][0-9]*$")]
Text = Annotated[str, Field(min_length=1, max_length=12000)]
Label = Literal["entailed", "contradicted", "not_enough_information"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Triple(Model):
    subject: Text
    predicate: Text
    object: Text
    object_type: Literal["entity", "literal"]


class SourceTriple(Model):
    subject: Text
    predicate: Text
    object: Text


class EntityCase(Model):
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
        if self.verification_status == "human_verified":
            if not self.verified_by or self.verified_at is None:
                raise ValueError("Human verification requires reviewer and date")
        return self


class Candidate(Model):
    entity_id: QID
    label: Text
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    source_url: Text
    retrieved_at: datetime | None = None


class StringCandidate(Model):
    """Type boundary: the baseline cannot receive descriptions or context."""

    entity_id: QID
    label: Text
    aliases: list[str] = Field(default_factory=list)


class Resolution(Model):
    selected_entity_id: QID | None
    confidence: float = Field(ge=0, le=1)
    short_rationale: str = Field(max_length=600)


class Generation(Model):
    triples: list[Triple] = Field(max_length=15)


class Evidence(Model):
    passage_id: Text
    text: Text
    source_url: Text
    retrieved_at: datetime
    revision_id: str | None = None
    license: str
    synthetic: bool = False


class Judgment(Model):
    label: Label
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    short_rationale: str = Field(max_length=600)


class Annotation(Model):
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
        if self.human_label is not None:
            if not self.annotator_id or self.annotated_at is None:
                raise ValueError("A completed annotation needs annotator_id and annotated_at")
            if self.human_label != "not_enough_information" and not self.evidence_ids:
                raise ValueError("Entailed/contradicted annotations need evidence IDs")
        return self
