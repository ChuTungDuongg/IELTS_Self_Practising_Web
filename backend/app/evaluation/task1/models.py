"""Versioned local benchmark input and content-free output contracts."""

import hashlib
import json
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.scoring.writing import validate_writing_criterion_score
from app.domains.writing.task_types import WritingTaskType, validate_task_type
from app.domains.writing.visual_families import visual_family
from app.evaluation.task1.metrics import overall_score
from app.schemas.chart_cross_check import ChartSpecialistIdentity
from app.schemas.task1_visual import GroundingConfidence, VisualReference
from app.schemas.writing_ai import TRAITS, Trait

BENCHMARK_CONTRACT_VERSION = "task1-benchmark-v1"
Split = Literal["dev", "holdout"]
Band = Annotated[Decimal, Field(ge=0, le=9, allow_inf_nan=False)]


def digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HumanScores(Model):
    """Supplied agreed/reference bands; raters is metadata, never model supervision."""

    ta: Band
    cc: Band
    lr: Band
    gra: Band

    @field_validator("ta", "cc", "lr", "gra")
    @classmethod
    def half_band(cls, value: Decimal) -> Decimal:
        return validate_writing_criterion_score(value)

    def scores(self) -> dict[Trait, Decimal]:
        return {trait: getattr(self, trait) for trait in TRAITS}


class BenchmarkSample(Model):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    split: Split
    task_type: WritingTaskType
    prompt: str = Field(min_length=1, max_length=20000, repr=False)
    image_path: str = Field(min_length=1, max_length=4096, repr=False)
    essay: str = Field(min_length=1, max_length=100000, repr=False)
    human_scores: HumanScores
    raters: int = Field(default=1, ge=1, le=100, strict=True)
    provenance: str = Field(min_length=1, max_length=2000, repr=False)
    redistributable: bool = Field(strict=True)
    visual_truth: VisualReference | None = Field(default=None, repr=False)

    @field_validator("task_type")
    @classmethod
    def task_one(cls, value: WritingTaskType) -> WritingTaskType:
        validate_task_type(1, value)
        return value

    @field_validator("image_path")
    @classmethod
    def local_path(cls, value: str) -> str:
        if "://" in value or value.lower().startswith(("data:", "file:", "http:", "https:")):
            raise ValueError("Only local image paths are supported")
        return value

    @field_validator("prompt", "essay", "provenance")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content must not be blank")
        return value

    @model_validator(mode="after")
    def truth_family(self):
        if self.visual_truth and self.visual_truth.visual_family != visual_family(self.task_type):
            raise ValueError("Visual truth does not match the task family")
        return self


class BenchmarkConfig(Model):
    max_concurrent_llm_requests: int = Field(default=2, ge=1, le=4)
    label: str = Field(max_length=160)
    scoring_version: Literal["v3", "v5", "v6"]
    prompt_version: str
    visual_contract_version: str
    scoring_prompt_version: str
    provider: Literal["vllm", "openai"]
    model: str = Field(max_length=160)
    endpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    specialist_endpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    specialist: ChartSpecialistIdentity
    request_timeout_seconds: float
    startup_timeout_seconds: float
    specialist_timeout_seconds: float
    benchmark_version: str = BENCHMARK_CONTRACT_VERSION
    implementation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def key(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"label"}))


class EvaluationRecord(Model):
    sample_id: str
    split: Split
    task_type: WritingTaskType
    visual_family: str
    config_key: str
    input_hash: str
    image_hash: str
    cache_key: str
    cache_hit: bool = False
    status: Literal["COMPLETED", "FAILED"]
    target: dict[Trait, Band]
    predicted: dict[Trait, Band]
    target_overall: Band
    predicted_overall: Band | None
    confidence: GroundingConfidence
    perception: dict[str, Any]
    specialist_status: str | None
    specialist_disagreements: int = 0
    decomposition: Literal[
        "PERCEPTION_OK_SCORE_OK",
        "PERCEPTION_OK_SCORE_HIGH",
        "PERCEPTION_OK_SCORE_LOW",
        "PERCEPTION_OK_SCORE_MIXED",
        "PERCEPTION_ERROR",
        "SPECIALIST_DISAGREEMENT",
        "UNUSABLE",
        "PERCEPTION_UNANNOTATED_SCORE_OK",
        "PERCEPTION_UNANNOTATED_SCORE_HIGH",
        "PERCEPTION_UNANNOTATED_SCORE_LOW",
        "PERCEPTION_UNANNOTATED_SCORE_MIXED",
    ]
    wall_clock_seconds: float = Field(ge=0)
    provider_calls: int = Field(ge=0)
    token_usage: dict[str, int]
    specialist_calls: int = Field(ge=0)
    specialist_latency_seconds: float = Field(ge=0)
    failures: dict[str, str]

    @field_validator("target", "predicted")
    @classmethod
    def valid_bands(cls, values):
        return {trait: validate_writing_criterion_score(value) for trait, value in values.items()}

    @model_validator(mode="after")
    def complete_consistent_scores(self):
        if set(self.target) != set(TRAITS):
            raise ValueError("Incomplete benchmark target")
        if self.status == "COMPLETED" and (
            set(self.predicted) != set(TRAITS) or self.failures or self.confidence == "UNUSABLE"
        ):
            raise ValueError("Incomplete completed benchmark prediction")
        if self.target_overall != overall_score(self.target):
            raise ValueError("Inconsistent benchmark target overall")
        if self.predicted_overall != overall_score(self.predicted):
            raise ValueError("Inconsistent benchmark prediction overall")
        return self
