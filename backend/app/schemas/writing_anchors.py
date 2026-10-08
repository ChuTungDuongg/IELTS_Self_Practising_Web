from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.domains.scoring.writing import validate_writing_criterion_score
from app.domains.writing.task_types import WritingTaskType, validate_task_type

LanguageTrait = Literal["cc", "lr", "gra"]
LANGUAGE_TRAITS: tuple[LanguageTrait, ...] = ("cc", "lr", "gra")
Band = Annotated[Decimal, Field(ge=0, le=9, allow_inf_nan=False)]


class AnchorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class HumanAnchorScores(AnchorModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ta: Band
    cc: Band
    lr: Band
    gra: Band

    @field_validator("ta", "cc", "lr", "gra")
    @classmethod
    def valid_band(cls, value: Decimal) -> Decimal:
        return validate_writing_criterion_score(value)

    @field_serializer("ta", "cc", "lr", "gra", return_type=float)
    def band_number(self, value: Decimal) -> float:
        return float(value)


class HumanAnchorInput(AnchorModel):
    source_kind: Literal["BUILDER_TASK", "CUSTOM_TASK"] = "BUILDER_TASK"
    writing_task_id: UUID | None = None
    task_number: Literal[1, 2] | None = None
    custom_prompt: str | None = Field(default=None, min_length=1, max_length=100000)
    custom_task_type: WritingTaskType | None = None
    response_text: str = Field(min_length=1, max_length=100000)
    human_scores: HumanAnchorScores
    admin_note: str | None = Field(default=None, max_length=2000)
    provenance: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def coherent_source(self):
        if self.source_kind == "BUILDER_TASK":
            if self.writing_task_id is None or any(
                value is not None
                for value in (self.task_number, self.custom_prompt, self.custom_task_type)
            ):
                raise ValueError("Builder source requires only a frozen task reference")
        else:
            if self.writing_task_id is not None or self.task_number is None:
                raise ValueError("Custom source requires a task number and no Builder reference")
            if not self.custom_prompt or not self.custom_prompt.strip():
                raise ValueError("Custom prompt is required")
            validate_task_type(self.task_number, self.custom_task_type)
        return self

    @field_validator("response_text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Response must not be blank")
        return value


class AnchorSetCreate(AnchorModel):
    name: str = Field(default="Human-labelled Writing anchors", min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


class AnchorSetResponse(AnchorModel):
    id: UUID
    name: str
    version: int
    status: Literal["DRAFT", "ACTIVE", "RETIRED"]
    created_at: datetime
    activated_at: datetime | None
    retired_at: datetime | None


class AnchorTask(AnchorModel):
    id: UUID | None
    test_version_id: UUID | None
    test_title: str
    version_number: int | None
    task_number: Literal[1, 2]
    task_type: str | None
    prompt_preview: str


class FrozenWritingTask(AnchorTask):
    id: UUID
    test_version_id: UUID
    version_number: int


class AnchorSummary(AnchorModel):
    id: UUID
    anchor_set_id: UUID
    source_kind: Literal["BUILDER_TASK", "CUSTOM_TASK"]
    task: AnchorTask
    word_count: int
    human_scores: HumanAnchorScores
    created_at: datetime


class AnchorDetail(AnchorSummary):
    custom_prompt: str | None
    response_text: str
    admin_note: str | None
    provenance: str | None


class AnchorPage(AnchorModel):
    items: list[AnchorSummary]
    total: int
    offset: int = 0
    limit: int = 25


class FrozenTaskPage(AnchorModel):
    items: list[FrozenWritingTask]
    total: int
    offset: int = 0
    limit: int = 25


class AnchorRecord(AnchorModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    source_kind: Literal["BUILDER_TASK", "CUSTOM_TASK"] = "BUILDER_TASK"
    writing_task_id: UUID | None = None
    test_version_id: UUID | None = None
    task_number: Literal[1, 2]
    task_type: str | None
    prompt: str = Field(repr=False)
    response_text: str = Field(repr=False)
    human_scores: HumanAnchorScores = Field(repr=False)


class AnchorSnapshot(AnchorModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID | None = None
    version: int | None = None
    anchors: tuple[AnchorRecord, ...] = Field(default=(), repr=False)

    def language_anchors(
        self, task_number: Literal[1, 2], criterion: LanguageTrait
    ) -> tuple[AnchorRecord, ...]:
        if criterion not in LANGUAGE_TRAITS:
            raise ValueError("Production anchors support language traits only")
        return tuple(anchor for anchor in self.anchors if anchor.task_number == task_number)


class CriterionCoverage(AnchorModel):
    criterion: Literal["ta", "cc", "lr", "gra"]
    counts: dict[str, int]
    ladder: list[int]
    readiness: Literal["EMPTY", "PARTIAL", "PAIRWISE_USABLE", "RECOMMENDED_COVERAGE"]
    pilot_complete: bool


class ResearchTaskCoverage(CriterionCoverage):
    source_id: UUID
    task: AnchorTask


class AnchorBankState(AnchorModel):
    current: AnchorSetResponse | None
    working: AnchorSetResponse | None
    current_count: int
    working_count: int


class AnchorCoverageResponse(AnchorModel):
    active_set: AnchorSetResponse | None
    evaluated_set: AnchorSetResponse | None = None
    production_task1: list[CriterionCoverage]
    research_task1_ta: list[ResearchTaskCoverage]
    research_task2: list[CriterionCoverage]
    recommendations: list[str]
    node_budget: int = 2
