from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Trait = Literal["fc", "lr", "gra", "pr"]
Stage = Literal[
    "PENDING",
    "QUALITY_CHECK",
    "TRANSCRIBING",
    "ANALYSING_AUDIO",
    "BUILDING_EVIDENCE",
    "SCORING",
    "GENERATING_FEEDBACK",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]


class SpeakingCriterionProgress(BaseModel):
    status: Literal["WAITING", "SCORING", "SCORED", "COMPLETED", "FAILED", "UNAVAILABLE"] = (
        "WAITING"
    )
    score: float | None = Field(default=None, ge=0, le=9, allow_inf_nan=False)
    feedback_status: Literal["PENDING", "READY", "FALLBACK"] = "PENDING"
    feedback: str | None = Field(default=None, max_length=1200)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    improvements: list[str] = Field(default_factory=list, max_length=6)
    error_code: str | None = None
    evidence_summary: dict[str, int | float | str | None] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def half_band(cls, score):
        if score is not None and score * 2 != int(score * 2):
            raise ValueError("Invalid half band")
        return score


class SpeakingAIRunData(BaseModel):
    run_id: UUID
    attempt_id: UUID
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    stage: Stage
    cache_key: str
    last_sequence: int
    created_at: datetime
    advisory: Literal[True] = True
    raw_mean: float | None = None
    overall_band: float | None = None
    criteria: dict[Trait, SpeakingCriterionProgress]
    summary: dict = Field(default_factory=lambda: {"responses": []})
    error_code: str | None = None


class SpeakingAICreated(BaseModel):
    run_id: UUID
    cache_hit: bool
    existing_active: bool


class SpeakingAIEventData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sequence: int
    event_type: str
    payload: dict[str, str | float]


class SpeakingAIRunList(BaseModel):
    run: SpeakingAIRunData | None
