"""Strict submission DTOs; predictions are exclusively worker-authored."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

LexicalProvider = Literal["azure_pa", "azure_stt", "faster_whisper_local", "faster_whisper_modal"]


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PreflightRequest(StrictDTO):
    review_revision: int = Field(ge=1)
    lexical_provider: LexicalProvider = "azure_pa"


class Consent(StrictDTO):
    azure_audio: Literal[True]
    llm_text: Literal[True]
    independent_provider: bool = False
    estimates_usd: dict[str, float]
    max_estimated_cost_usd: float = Field(gt=0, le=1000, allow_inf_nan=False)

    @model_validator(mode="after")
    def finite_estimates(self):
        import math

        if not self.estimates_usd or any(
            not math.isfinite(v) or v <= 0 for v in self.estimates_usd.values()
        ):
            raise ValueError("Each selected provider needs a positive finite admission estimate")
        if sum(self.estimates_usd.values()) > self.max_estimated_cost_usd:
            raise ValueError("Admission estimates exceed the authorized ceiling")
        return self


class RunSubmit(PreflightRequest):
    preflight_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    submission_key: UUID
    consent: Consent


class RetryRequest(StrictDTO):
    checkpoint_id: UUID
    reconciliation: str = Field(min_length=10, max_length=1000)
    consent: Consent


class RunDTO(StrictDTO):
    id: UUID
    sample_id: UUID
    review_revision: int
    config_fingerprint: str
    configuration: dict
    candidate_ms: int
    window_count: int
    status: str
    stage: str
    progress: int
    error_code: str | None
    prediction: dict | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    requests: list[dict] = Field(default_factory=list)
    checkpointed_scores: dict[str, float] = Field(default_factory=dict)
