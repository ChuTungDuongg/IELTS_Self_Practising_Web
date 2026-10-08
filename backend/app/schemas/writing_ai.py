from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
    field_serializer,
    field_validator,
)

from app.domains.scoring import validate_writing_criterion_score
from app.models.enums import WritingAIRunStatus
from app.providers.writing_llm.base import (
    CalibrationDiagnosticReason,
    OutputFailureReason,
    PresentationDiagnosticReason,
    SafeFinishReason,
)
from app.schemas.task1_claims import Task1Analysis

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
    """Optional, sanitized explanation; never determines IELTS score validity."""

    support: list[BandSupport] = Field(default_factory=list, max_length=3)
    next_band: Decimal | None = Field(default=None, ge=0, le=9)
    next_band_blockers: list[NextBandBlocker] = Field(default_factory=list, max_length=2)
    comparison: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
        description="Vietnamese holistic comparison with adjacent official whole-band descriptors; half-bands interpolate.",
    )
    high_band_justification: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
        description="Optional concise Vietnamese descriptor-fit justification.",
    )

    @field_serializer("next_band", return_type=float | None)
    def serialize_next_band(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class RawScoringOutput(TraitScore):
    """Semantic provider contract, independent of display lengths/item counts."""

    feedback: str = Field(strict=True, min_length=1)
    strengths: list[StrictStr] = Field(strict=True)
    improvements: list[StrictStr] = Field(strict=True)
    # Known legacy metadata remains best-effort, excluded from schema/repr/DTOs.
    calibration: Any = Field(default=None, exclude=True, repr=False)


class ScoringOutput(RawScoringOutput):
    # Bounded display output. RawScoringOutput is validated before normalization;
    # historical DTO limits in TraitScore remain unchanged.
    feedback: str = Field(
        strict=True,
        min_length=1,
        max_length=800,
        description="Vietnamese feedback explaining descriptor fit and the next higher level.",
    )
    strengths: list[Annotated[StrictStr, Field(min_length=1, max_length=240)]] = Field(
        strict=True, max_length=3, description="Vietnamese strengths after selecting the score."
    )
    improvements: list[Annotated[StrictStr, Field(min_length=1, max_length=240)]] = Field(
        strict=True, max_length=3, description="Vietnamese improvements relevant to this criterion."
    )


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


class Task1WritingResult(AIWritingResult):
    task_number: Literal[1] = 1
    task1_analysis: Task1Analysis


class CreateRunRequest(StrictModel):
    force: bool = False


class CreateRunResponse(BaseModel):
    run_id: UUID
    cache_hit: bool
    existing_active: bool


AssessmentStage = Literal[
    "evidence",
    "scoring",
    "visual_grounding",
    "claim_extraction",
    "claim_verification",
    "chart_cross_check",
]
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
    "visual_grounding",
    "visual_grounded",
    "chart_cross_check",
    "chart_read",
    "chart_fallback",
    "chart_reconciled",
    "deriving_facts",
    "extracting_claims",
    "claims_extracted",
    "verifying_claims",
    "claims_verified",
    "claim_extraction_failed",
    "claim_verification_failed",
]


class RunActivity(StrictModel):
    phase: ActivityPhase
    criterion: Trait | None = None
    stage: AssessmentStage | None = None
    started_at: datetime


class ValidationIssue(StrictModel):
    # Produced only by safe_validation_issues; never include input or messages.
    field: str = Field(min_length=1, max_length=120)
    validation_type: str = Field(min_length=1, max_length=80)


class OutputDiagnostic(StrictModel):
    stage: AssessmentStage
    criterion: Trait
    reason: OutputFailureReason | CalibrationDiagnosticReason | PresentationDiagnosticReason
    attempt: int = Field(ge=1, le=2)
    finish_reason: SafeFinishReason | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list, max_length=8)


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
    result: Task1WritingResult | AIWritingResult | None
    task_number: Literal[1, 2] = 2
    task1_analysis: Task1Analysis | None = None
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
    "visual_grounding.started",
    "visual_grounding.completed",
    "visual_grounding.failed",
    "chart_specialist.started",
    "chart_specialist.completed",
    "chart_specialist.failed",
    "chart_reconciliation.completed",
    "derived_facts.completed",
    "claim_extraction.started",
    "claim_extraction.completed",
    "claim_extraction.failed",
    "claim_verification.started",
    "claim_verification.completed",
    "claim_verification.failed",
]


class EventPayload(StrictModel):
    criterion: Trait | None = None
    stage: AssessmentStage | None = None
    evidence: list[Evidence] | None = Field(default=None, max_length=6)
    result: CriterionResult | None = None
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=300)
    task1_analysis: Task1Analysis | None = None


class EventResponse(BaseModel):
    sequence: int = Field(ge=1)
    event_type: EventType
    payload: EventPayload
    created_at: datetime | None = None
