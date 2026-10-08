from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)

from app.domains.scoring import validate_writing_criterion_score
from app.models.enums import WritingAIRunStatus
from app.providers.writing_llm.base import OutputFailureReason

Trait = Literal["ta", "cc", "lr", "gra"]
TRAITS: tuple[Trait, ...] = ("ta", "cc", "lr", "gra")
ShortText = Annotated[str, Field(min_length=1, max_length=800)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(StrictModel):
    quote: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=600)]
    assessment: ShortText

    @field_validator("quote")
    @classmethod
    def non_blank_quote(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Quotation must not be blank")
        return value


class EvidenceResult(StrictModel):
    evidence: list[Evidence] = Field(max_length=6)


class TraitScore(StrictModel):
    score: Decimal = Field(ge=0, le=9, allow_inf_nan=False)
    feedback: str = Field(min_length=1, max_length=2000)
    strengths: list[ShortText] = Field(max_length=5)
    improvements: list[ShortText] = Field(max_length=5)

    @field_validator("score")
    @classmethod
    def half_band(cls, value: Decimal) -> Decimal:
        return validate_writing_criterion_score(value)

    @field_serializer("score", return_type=float)
    def serialize_score(self, value: Decimal) -> float:
        return float(value)


class CriterionResult(TraitScore):
    evidence: list[Evidence] = Field(max_length=6)


class Criteria(StrictModel):
    ta: CriterionResult
    cc: CriterionResult
    lr: CriterionResult
    gra: CriterionResult


class AIWritingResult(StrictModel):
    criteria: Criteria
    raw_mean: Decimal = Field(ge=0, le=9, allow_inf_nan=False)
    overall_band: Decimal = Field(ge=0, le=9, allow_inf_nan=False)

    @field_serializer("raw_mean", "overall_band", return_type=float)
    def serialize_band(self, value: Decimal) -> float:
        return float(value)


class CreateRunRequest(StrictModel):
    force: bool = False


class CreateRunResponse(BaseModel):
    run_id: UUID
    cache_hit: bool
    existing_active: bool


AssessmentStage = Literal["evidence", "scoring"]
ActivityPhase = Literal[
    "preparing",
    "starting_model",
    "collecting_evidence",
    "validating_evidence",
    "evidence_collected",
    "scoring",
    "validating_score",
    "retrying",
    "completed",
    "failed",
]


class RunActivity(StrictModel):
    phase: ActivityPhase
    criterion: Trait | None = None
    stage: AssessmentStage | None = None
    started_at: datetime


class OutputDiagnostic(StrictModel):
    stage: AssessmentStage
    criterion: Trait
    reason: OutputFailureReason
    attempt: int = Field(ge=1, le=2)


class RunResponse(BaseModel):
    id: UUID
    attempt_id: UUID
    writing_task_id: UUID
    status: WritingAIRunStatus
    provider: str
    model: str
    prompt_version: str
    result: AIWritingResult | None
    progress: dict[Trait, CriterionResult]
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    activity: RunActivity | None = None


class RunListResponse(BaseModel):
    configured: bool
    items: list[RunResponse]


EventType = Literal[
    "run.started",
    "provider.starting",
    "provider.ready",
    "criterion.started",
    "evidence.request.started",
    "evidence.validation.started",
    "criterion.evidence.completed",
    "criterion.scoring.started",
    "criterion.scoring.validation.started",
    "criterion.retrying",
    "criterion.completed",
    "run.completed",
    "run.failed",
    "heartbeat",
]


class EventPayload(StrictModel):
    criterion: Trait | None = None
    stage: AssessmentStage | None = None
    evidence: list[Evidence] | None = Field(default=None, max_length=6)
    result: CriterionResult | None = None
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=300)


class EventResponse(BaseModel):
    sequence: int = Field(ge=1)
    event_type: EventType
    payload: EventPayload
    created_at: datetime | None = None
