"""Bounded research commands. No provider payload or prediction is client writable."""

import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.evaluation.speaking.asr_comparison import Annotation, WindowBinding
from app.evaluation.speaking.asr_normalization import NORMALIZATION, normalized_text
from app.evaluation.speaking.hybrid import _tokens
from app.schemas.speaking_benchmark_grading import LexicalProvider, StrictDTO

METRIC_PROTOCOL = "admin-speaking-research-v1"


class UncertainSpan(StrictDTO):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    kind: Literal["uncertain", "unintelligible", "questionable_reference"]


class ReferenceWrite(WindowBinding):
    review_revision: int = Field(ge=1)
    expected_revision: int = Field(ge=0)
    normalization: Literal["asr-research-nfc-casefold-words-v2"] = NORMALIZATION
    text: str = Field(max_length=30000)
    annotations: list[Annotation] = Field(default_factory=list, max_length=1000)
    uncertainty: list[UncertainSpan] = Field(default_factory=list, max_length=100)
    provenance: Literal["independent_human_transcriber", "ai_draft", "unverified"]
    source_reference: str = Field(max_length=1000)
    accent: str | None = Field(default=None, max_length=100)
    speaking_speed: Literal["slow", "typical", "fast"] | None = None
    response_length: Literal["short", "long"] | None = None
    voluntary_metadata: bool = False

    @model_validator(mode="after")
    def bounds(self):
        count = len(_tokens(normalized_text(self.text)))
        if self.end_ms <= self.start_ms or any(
            not a.start_token < a.end_token <= count for a in self.annotations
        ):
            raise ValueError("Invalid annotation token bounds")
        if any(not self.start_ms <= s.start_ms < s.end_ms <= self.end_ms for s in self.uncertainty):
            raise ValueError("Uncertainty must be inside the approved source window")
        if (self.accent or self.speaking_speed) and not self.voluntary_metadata:
            raise ValueError("Speaker metadata requires voluntary annotation confirmation")
        return self


class ReferenceVerify(StrictDTO):
    expected_revision: int = Field(ge=1)
    independently_reviewed: Literal[True]


class ReferenceDTO(StrictDTO):
    id: UUID
    sample_id: UUID
    review_revision: int
    source_sha256: str
    manifest_fingerprint: str
    segment_id: str
    start_ms: int
    end_ms: int
    revision: int
    normalization: str
    text: str
    annotations: list[Annotation]
    uncertainty: list[UncertainSpan]
    metadata_labels: dict
    status: str
    provenance: str
    source_reference: str
    author_id: UUID
    reviewer_id: UUID | None
    verified_at: datetime | None
    created_at: datetime


class CohortSelection(StrictDTO):
    sample_id: UUID
    review_revision: int = Field(ge=1)
    segment_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.segment_ids)) != len(self.segment_ids):
            raise ValueError("Duplicate windows")
        return self


class ProviderVariant(StrictDTO):
    key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    provider: LexicalProvider
    silence_ms: int | None = Field(default=None, ge=100, le=5000)

    @model_validator(mode="after")
    def options(self):
        if self.silence_ms is not None and not self.provider.startswith("azure_"):
            raise ValueError("Silence tuning is Azure-specific")
        return self


class ExperimentCreate(StrictDTO):
    submission_key: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    mode: Literal["ASR_ONLY", "PAIRED_GRADING"]
    cohort: list[CohortSelection] = Field(min_length=1, max_length=100)
    variants: list[ProviderVariant] = Field(min_length=1, max_length=8)
    split_policy: Literal["DEV", "HOLDOUT", "MIXED"] = "DEV"
    max_provider_audio_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    max_physical_requests: int = Field(ge=1, le=10000)

    @model_validator(mode="after")
    def unique(self):
        if not self.name.strip():
            raise ValueError("Experiment name must not be blank")
        if len({s.sample_id for s in self.cohort}) != len(self.cohort) or len(
            {v.key for v in self.variants}
        ) != len(self.variants):
            raise ValueError("Unique samples and variant keys required")
        if self.mode == "PAIRED_GRADING" and (
            len({v.provider for v in self.variants}) != len(self.variants)
            or any(v.silence_ms is not None for v in self.variants)
        ):
            raise ValueError(
                "Paired mode varies only lexical provider; use current fixed speech settings"
            )
        return self


class ResearchConsent(StrictDTO):
    provider_audio: Literal[True]
    llm_text: bool = False
    modal_gpu: bool = False
    holdout_evaluation: bool = False
    estimates_usd: dict[str, float]
    max_estimated_cost_usd: float = Field(gt=0, le=1000, allow_inf_nan=False)

    @model_validator(mode="after")
    def budget(self):
        if not self.estimates_usd or any(
            not math.isfinite(v) or v < 0 for v in self.estimates_usd.values()
        ):
            raise ValueError("Finite provider estimates required")
        if sum(self.estimates_usd.values()) > self.max_estimated_cost_usd:
            raise ValueError("Estimates exceed admission ceiling")
        return self


class ExperimentStart(StrictDTO):
    preflight_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    consent: ResearchConsent


class ReconcileRequest(ExperimentStart):
    observation_id: UUID
    reason: str = Field(min_length=10, max_length=1000)


class VariantDTO(StrictDTO):
    id: UUID
    sample_id: UUID
    review_revision: int
    provider_key: str
    configuration: dict
    fingerprint: str
    windows: list[dict]
    status: str
    error_code: str | None
    grading_run_id: UUID | None


class ExperimentDTO(StrictDTO):
    id: UUID
    name: str
    description: str
    mode: str
    configuration: dict
    fingerprint: str
    evaluation_selection: dict
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    holdout_executed_at: datetime | None
    variants: list[VariantDTO] = Field(default_factory=list)


class ExperimentSummary(StrictDTO):
    id: UUID
    name: str
    mode: str
    status: str
    created_at: datetime
    sample_count: int
    providers: list[str]
