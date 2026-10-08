from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.domains.scoring.writing import validate_writing_criterion_score

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
    writing_task_id: UUID
    response_text: str = Field(min_length=1, max_length=100000)
    human_scores: HumanAnchorScores
    admin_note: str | None = Field(default=None, max_length=2000)
    provenance: str | None = Field(default=None, max_length=2000)

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


class FrozenWritingTask(AnchorModel):
    id: UUID
    test_version_id: UUID
    test_title: str
    version_number: int
    task_number: Literal[1, 2]
    task_type: str | None
    prompt_preview: str


class AnchorSummary(AnchorModel):
    id: UUID
    anchor_set_id: UUID
    task: FrozenWritingTask
    word_count: int
    human_scores: HumanAnchorScores
    created_at: datetime


class AnchorDetail(AnchorSummary):
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
    writing_task_id: UUID
    test_version_id: UUID
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
    task: FrozenWritingTask


class AnchorCoverageResponse(AnchorModel):
    active_set: AnchorSetResponse | None
    production_task1: list[CriterionCoverage]
    research_task1_ta: list[ResearchTaskCoverage]
    research_task2: list[CriterionCoverage]
    recommendations: list[str]
    node_budget: int = 2
