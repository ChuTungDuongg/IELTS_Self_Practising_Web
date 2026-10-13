"""Strict local file-format and content-free Task 2 evaluation contracts."""

import hashlib
import json
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from app.domains.scoring.writing import validate_writing_criterion_score
from app.evaluation.writing.metrics import overall_score

BENCHMARK_CONTRACT_VERSION = "task2-benchmark-v1"
TRAITS = ("tr", "cc", "lr", "gra")
Trait = Literal["tr", "cc", "lr", "gra"]
Split = Literal["dev", "holdout"]
Band = Annotated[Decimal, Field(ge=0, le=9, allow_inf_nan=False)]


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HumanScores(Model):
    tr: Band
    cc: Band
    lr: Band
    gra: Band

    @field_validator("tr", "cc", "lr", "gra", mode="before")
    @classmethod
    def not_boolean(cls, value):
        if type(value) is bool:
            raise ValueError("Numeric half bands are required")
        return value

    @field_validator("tr", "cc", "lr", "gra")
    @classmethod
    def half_band(cls, value):
        return validate_writing_criterion_score(value)

    def scores(self) -> dict[Trait, Decimal]:
        return {trait: getattr(self, trait) for trait in TRAITS}


class BenchmarkSample(Model):
    schema_version: Literal[1]
    id: StrictStr = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    split: Split
    prompt: StrictStr = Field(min_length=1, max_length=20000, repr=False)
    essay: StrictStr = Field(min_length=1, max_length=100000, repr=False)
    human_scores: HumanScores
    raters: Literal[1] = 1
    provenance: StrictStr = Field(min_length=1, max_length=2000, repr=False)
    redistributable: bool = Field(strict=True)

    @field_validator("schema_version", "raters", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("An integer file-format field is required")
        return value

    @field_validator("prompt", "essay", "provenance")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Content must not be blank")
        return value

    @property
    def human_overall(self):
        return overall_score(self.human_scores.scores(), traits=TRAITS)


class BenchmarkConfig(Model):
    label: str = Field(max_length=160)
    provider: Literal["vllm", "openai"]
    model: str = Field(max_length=160)
    endpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_version: str = Field(max_length=160)
    max_concurrent_llm_requests: int = Field(default=2, ge=1, le=4)
    request_timeout_seconds: float = Field(gt=0)
    startup_timeout_seconds: float = Field(gt=0)
    relevance_enabled: bool = True
    paragraph_mode: Literal["textarea"] = "textarea"
    benchmark_version: str = BENCHMARK_CONTRACT_VERSION
    implementation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def key(self):
        return digest(self.model_dump(mode="json", exclude={"label"}))


class EvaluationRecord(Model):
    sample_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    split: Split
    config_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    cache_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    cache_hit: bool = False
    status: Literal["COMPLETED", "FAILED"]
    target: dict[Trait, Band]
    predicted: dict[Trait, Band]
    target_overall: Band
    predicted_overall: Band | None
    wall_clock_seconds: float = Field(ge=0, allow_inf_nan=False)
    provider_calls: int = Field(ge=0)
    token_usage: dict[str, int]
    failures: dict[str, str]

    @field_validator("target", "predicted")
    @classmethod
    def valid_bands(cls, values):
        return {trait: validate_writing_criterion_score(value) for trait, value in values.items()}

    @field_validator("token_usage")
    @classmethod
    def safe_usage(cls, values):
        if any(
            key not in {"prompt_tokens", "completion_tokens", "total_tokens"} or value < 0
            for key, value in values.items()
        ):
            raise ValueError("Unsafe usage counters")
        return values

    @model_validator(mode="after")
    def consistent(self):
        if set(self.target) != set(TRAITS):
            raise ValueError("Incomplete benchmark target")
        if self.status == "COMPLETED" and (set(self.predicted) != set(TRAITS) or self.failures):
            raise ValueError("Incomplete completed benchmark prediction")
        if self.status == "FAILED" and not self.failures:
            raise ValueError("Failed samples must retain a failure")
        if self.target_overall != overall_score(
            self.target, traits=TRAITS
        ) or self.predicted_overall != overall_score(self.predicted, traits=TRAITS):
            raise ValueError("Inconsistent benchmark overall")
        return self
