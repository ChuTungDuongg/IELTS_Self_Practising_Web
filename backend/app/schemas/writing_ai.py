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
    model_validator,
)

from app.domains.scoring import validate_writing_criterion_score
from app.models.enums import WritingAIRunStatus
from app.providers.writing_llm.base import OutputFailureReason, SafeFinishReason

Trait = Literal["ta", "cc", "lr", "gra"]
TRAITS: tuple[Trait, ...] = ("ta", "cc", "lr", "gra")
ShortText = Annotated[str, Field(min_length=1, max_length=800)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(StrictModel):
    # Missing IDs are accepted only for persisted v1/v2 DTOs. Inference uses
    # EvidenceSelection below, where an ID is required and quote is forbidden.
    source_id: str | None = Field(default=None, max_length=32)
    quote: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=12000)]
    assessment: ShortText

    @field_validator("quote")
    @classmethod
    def non_blank_quote(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Quotation must not be blank")
        return value


class EvidenceResult(StrictModel):
    evidence: list[Evidence] = Field(max_length=6)


SourceID = Annotated[str, Field(min_length=4, max_length=32, pattern=r"^P[1-9][0-9]*S[1-9][0-9]*$")]


class EvidenceChoice(StrictModel):
    source_id: SourceID
    assessment: str = Field(
        min_length=1,
        max_length=320,
        description="Concise Vietnamese assessment, at most two sentences.",
    )
    focus: str | None = Field(
        default=None,
        max_length=160,
        description="Optional focus phrase; never used for identity or matching.",
    )


class EvidenceSelection(StrictModel):
    evidence: list[EvidenceChoice] = Field(max_length=4)


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


class BandSupport(StrictModel):
    source_id: SourceID
    assessment: str = Field(
        min_length=1, max_length=160, description="Vietnamese evidence of descriptor fit."
    )


class NextBandBlocker(BandSupport):
    severity: Literal["isolated", "recurring", "substantial"]


class BandComparison(StrictModel):
    support: list[BandSupport] = Field(max_length=3)
    next_band: Decimal | None = Field(ge=0, le=9)
    next_band_blockers: list[NextBandBlocker] = Field(max_length=2)
    comparison: str = Field(
        min_length=1,
        max_length=240,
        description="Vietnamese holistic comparison with adjacent official whole-band descriptors; half-bands interpolate.",
    )
    high_band_justification: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
        description="Vietnamese affirmative descriptor-fit justification for scores >= 7.5, otherwise null.",
    )

    @field_serializer("next_band", return_type=float | None)
    def serialize_next_band(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class ScoringOutput(TraitScore):
    # Bound new inference without rejecting historical results with older limits.
    feedback: str = Field(
        min_length=1,
        max_length=800,
        description="Vietnamese feedback explaining descriptor fit and the next higher level.",
    )
    strengths: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        max_length=3, description="Vietnamese strengths after selecting the score."
    )
    improvements: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        max_length=3, description="Vietnamese improvements relevant to this criterion."
    )
    calibration: BandComparison

    @model_validator(mode="after")
    def consistent_comparison(self):
        # Compare actual official descriptor levels, not an invented half-band
        # descriptor. Both 7 and 7.5 compare to whole-band descriptor 8.
        expected = Decimal(int(self.score) + 1) if self.score < 9 else None
        if self.calibration.next_band != expected:
            raise ValueError("Next-band comparison is inconsistent")
        if self.score < 9 and not self.calibration.next_band_blockers:
            raise ValueError("Explain which higher descriptor features are not consistently shown")
        if self.score == 9 and self.calibration.next_band_blockers:
            raise ValueError("There is no higher descriptor to block above band 9")
        if self.score >= Decimal("7.5") and (
            not self.calibration.support or not self.calibration.high_band_justification
        ):
            raise ValueError("High-band descriptor-fit justification is required")
        return self


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
    finish_reason: SafeFinishReason | None = None


class CriterionFailure(StrictModel):
    error_code: str = Field(max_length=80)
    error_message: str = Field(max_length=300)
    stage: AssessmentStage | None = None


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
    failures: dict[Trait, CriterionFailure] = Field(default_factory=dict)
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
    "criterion.failed",
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
