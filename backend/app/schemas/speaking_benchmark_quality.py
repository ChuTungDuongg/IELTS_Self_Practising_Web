"""Bounded P4 quality/suite/gate commands; no writable AI result fields."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.speaking_benchmark_grading import StrictDTO

QUALITY_PROTOCOL = "speaking-dataset-quality-v1"
GATE_PROTOCOL = "speaking-regression-gate-v1"


class ApprovedSelection(StrictDTO):
    sample_id: UUID
    review_revision: int = Field(ge=1)


class LabelSelection(StrictDTO):
    kind: Literal["LEGACY", "INDEPENDENT", "ADJUDICATED"] = "ADJUDICATED"
    id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)
    rater_id: UUID | None = None


class QualityPolicy(StrictDTO):
    protocol: Literal["speaking-dataset-quality-v1"] = QUALITY_PROTOCOL
    require_human_label: bool = True
    require_adjudication: bool = False
    require_source_bound_labels: bool = True
    require_asr_references: bool = False
    require_all_parts: bool = True
    minimum_independent_candidates: int = Field(default=10, ge=1, le=10000)


class QualityRequest(StrictDTO):
    cohort: list[ApprovedSelection] = Field(min_length=1, max_length=100)
    label_selection: LabelSelection = Field(default_factory=LabelSelection)
    policy: QualityPolicy = Field(default_factory=QualityPolicy)

    @model_validator(mode="after")
    def unique(self):
        if len({c.sample_id for c in self.cohort}) != len(self.cohort):
            raise ValueError("Duplicate samples are not independent recordings")
        return self


class QualityIssue(StrictDTO):
    code: str
    severity: Literal["BLOCKED", "NEEDS_REVIEW", "INSUFFICIENT_DATA"]
    artifact: str
    artifact_id: str
    remediation: str


class QualityReport(StrictDTO):
    protocol: str
    evaluated_at: datetime
    status: Literal["READY", "NEEDS_REVIEW", "BLOCKED", "INSUFFICIENT_DATA"]
    issues: list[QualityIssue]
    samples: list[dict]
    issue_counts: dict[str, int]
    eligible_samples: int
    ineligible_samples: int
    independent_candidates: int
    fingerprint: str


class SuiteCreate(QualityRequest):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    family_id: UUID | None = None
    expected_revision: int = Field(default=0, ge=0)
    holdout_evaluation: bool = False


class SuiteDTO(StrictDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    family_id: UUID
    revision: int
    name: str
    description: str
    configuration: dict
    fingerprint: str
    frozen_at: datetime
    created_at: datetime


class PersistedSelection(StrictDTO):
    kind: Literal["EXPERIMENT", "GRADING"]
    id: UUID | None = None
    variant_key: str | None = Field(default=None, max_length=80)
    configuration_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def complete(self):
        if self.kind == "EXPERIMENT" and (
            not self.id or not self.variant_key or self.configuration_fingerprint
        ):
            raise ValueError("Select one experiment and exact variant")
        if self.kind == "GRADING" and (
            not self.configuration_fingerprint or self.id or self.variant_key
        ):
            raise ValueError("Select one grading configuration fingerprint")
        return self


MetricName = Literal[
    "wer",
    "cer",
    "filler_recall",
    "repetition_recall",
    "recognition_coverage",
    "failure_rate",
    "latency_ms",
    "real_time_factor",
    "overall_mae",
    "fc_mae",
    "lr_mae",
    "gra_mae",
    "pr_mae",
    "exact_agreement",
    "within_0_5",
    "signed_bias_abs",
    "score_coverage",
    "missing_overall_rate",
    "unknown_billing_attempts",
    "provider_audio_ms",
    "physical_requests",
    "cache_reuse_rate",
    "missing_artifact_count",
]


class MetricThreshold(StrictDTO):
    metric: MetricName
    max_regression: float = Field(ge=0, allow_inf_nan=False)


class GatePolicy(StrictDTO):
    protocol: Literal["speaking-regression-gate-v1"] = GATE_PROTOCOL
    comparison: Literal["CONFIGURATION", "LEXICAL_ASR"] = "CONFIGURATION"
    minimum_independent_candidates: int = Field(default=10, ge=1, le=10000)
    minimum_prediction_coverage: float = Field(default=1, gt=0, le=1, allow_inf_nan=False)
    minimum_reference_coverage: float = Field(default=1, gt=0, le=1, allow_inf_nan=False)
    thresholds: list[MetricThreshold] = Field(min_length=1, max_length=30)
    max_unknown_billing_attempts: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def unique(self):
        if len({t.metric for t in self.thresholds}) != len(self.thresholds):
            raise ValueError("Each metric has one explicit tolerable regression")
        return self


class GateCreate(StrictDTO):
    name: str = Field(min_length=1, max_length=160)
    suite_id: UUID
    baseline: PersistedSelection
    candidate: PersistedSelection
    policy: GatePolicy


class GateDTO(StrictDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    name: str
    suite_id: UUID
    baseline: PersistedSelection
    candidate: PersistedSelection
    policy: GatePolicy
    fingerprint: str
    created_at: datetime


class GateEvaluate(StrictDTO):
    holdout_evaluation: bool = False


class RegressionReportDTO(StrictDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    gate_id: UUID
    status: Literal["PASS", "FAIL", "INCONCLUSIVE", "INVALID"]
    protocol: str
    fingerprint: str
    report: dict
    created_at: datetime
