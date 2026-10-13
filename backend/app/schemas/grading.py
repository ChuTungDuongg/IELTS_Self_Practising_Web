"""Explicit subjective-grading capabilities and human Speaking scores."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GradingCapabilities(BaseModel):
    context: Literal["PERSONAL", "CLASSROOM"] = "PERSONAL"
    can_edit_final: bool = False
    can_copy_ai_to_final: bool = False
    waiting_for_teacher: bool = False


class SpeakingScoreUpdate(BaseModel):
    fc: float = Field(ge=0, le=9, multiple_of=0.5)
    lr: float = Field(ge=0, le=9, multiple_of=0.5)
    gra: float = Field(ge=0, le=9, multiple_of=0.5)
    pr: float = Field(ge=0, le=9, multiple_of=0.5)
    fc_feedback: str | None = Field(default=None, max_length=10000)
    lr_feedback: str | None = Field(default=None, max_length=10000)
    gra_feedback: str | None = Field(default=None, max_length=10000)
    pr_feedback: str | None = Field(default=None, max_length=10000)


class SpeakingFinalScore(SpeakingScoreUpdate):
    model_config = ConfigDict(from_attributes=True)
    overall_band: float
