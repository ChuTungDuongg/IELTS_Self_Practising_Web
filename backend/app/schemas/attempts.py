from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.scoring import validate_writing_criterion_score
from app.models.enums import AttemptStatus, FinishedReason, ModuleType, TimerMode
from app.schemas.assets import AssetResponse


class TimerRequest(BaseModel):
    mode: TimerMode
    duration_seconds: int | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> "TimerRequest":
        presets = {2400, 3000, 3600, 4200}
        if self.mode == TimerMode.COUNTDOWN and self.duration_seconds not in presets:
            raise ValueError("Countdown duration must be 40, 50, 60, or 70 minutes")
        if self.mode == TimerMode.COUNT_UP and self.duration_seconds is not None:
            raise ValueError("Count-up mode does not accept a duration")
        return self


class AttemptCreate(BaseModel):
    test_version_id: UUID
    module: ModuleType
    timer: TimerRequest


class ActivityRequest(BaseModel):
    client_observed_at: datetime | None = None


class AnswerUpdate(BaseModel):
    value: str | list[str] | dict[str, str]


class AnswerResponse(BaseModel):
    question_id: UUID
    value: Any
    is_correct: bool | None
    saved_at: datetime


class WritingResponseUpdate(BaseModel):
    content: str = Field(max_length=100_000)


class WritingResponse(BaseModel):
    writing_task_id: UUID
    content: str
    word_count: int = Field(ge=0)
    saved_at: datetime


class WritingTaskScoreUpdate(BaseModel):
    ta: Decimal
    cc: Decimal
    lr: Decimal
    gra: Decimal

    @field_validator("ta", "cc", "lr", "gra")
    @classmethod
    def validate_half_band(cls, value: Decimal) -> Decimal:
        return validate_writing_criterion_score(value)


class WritingTaskScore(BaseModel):
    ta: float
    cc: float
    lr: float
    gra: float
    overall: float


class AttemptResponse(BaseModel):
    attempt_id: UUID
    test_version_id: UUID
    module: ModuleType
    status: AttemptStatus
    finished_reason: FinishedReason | None
    timer_mode: TimerMode
    timer_limit_seconds: int | None
    started_at: datetime
    paused_at: datetime | None
    total_paused_seconds: int = Field(ge=0)
    deadline_at: datetime | None
    last_active_at: datetime
    finished_at: datetime | None
    elapsed_seconds: int
    remaining_seconds: int | None
    raw_score: int | None
    max_score: int | None
    band_score: float | None
    server_time: datetime


class ReviewAnswer(BaseModel):
    question_id: UUID
    question_number: int
    prompt: str
    value: Any
    answer_key: dict[str, Any]
    is_correct: bool | None
    explanation: str | None


class WritingReview(BaseModel):
    writing_task_id: UUID
    task_number: int
    prompt: str
    image_asset_id: UUID | None = None
    image_asset: AssetResponse | None = None
    minimum_recommended_words: int | None
    recommended_duration_seconds: int | None
    content: str
    word_count: int
    score: WritingTaskScore | None = None


class AttemptReview(BaseModel):
    attempt: AttemptResponse
    test_title: str
    answers: list[ReviewAnswer]
    writing_responses: list[WritingReview]
    highlights: list[dict[str, Any]]
    flags: list[dict[str, Any]]


class HistoryItem(BaseModel):
    attempt_id: UUID
    test_id: UUID
    test_version_id: UUID
    test_title: str
    version_number: int
    module: ModuleType
    status: AttemptStatus
    started_at: datetime
    finished_at: datetime | None
    elapsed_seconds: int | None
    timer_mode: TimerMode
    timer_limit_seconds: int | None
    remaining_seconds: int | None
    raw_score: int | None
    max_score: int | None
    band_score: float | None


class HistoryGroup(BaseModel):
    test_id: UUID
    test_version_id: UUID
    test_title: str
    version_number: int
    reading: HistoryItem | None = None
    listening: HistoryItem | None = None
    writing: HistoryItem | None = None
    overall_band_score: float | None = None


class AttemptList(BaseModel):
    items: list[HistoryItem]
    groups: list[HistoryGroup]
    total: int = Field(ge=0)
