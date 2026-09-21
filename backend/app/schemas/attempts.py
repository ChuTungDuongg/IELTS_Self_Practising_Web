from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.scoring import validate_writing_criterion_score
from app.models.enums import (
    AttemptContext,
    AttemptStatus,
    FinishedReason,
    ModuleType,
    TestSessionStatus,
    TimerMode,
)
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


class NavigationRequest(BaseModel):
    kind: Literal["PASSAGE", "LISTENING_PART", "WRITING_TASK", "QUESTION"]
    target_id: UUID


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
    ta_feedback: str | None = Field(default=None, max_length=4000)
    cc_feedback: str | None = Field(default=None, max_length=4000)
    lr_feedback: str | None = Field(default=None, max_length=4000)
    gra_feedback: str | None = Field(default=None, max_length=4000)

    @field_validator("ta", "cc", "lr", "gra")
    @classmethod
    def validate_half_band(cls, value: Decimal) -> Decimal:
        return validate_writing_criterion_score(value)

    @field_validator("ta_feedback", "cc_feedback", "lr_feedback", "gra_feedback")
    @classmethod
    def normalize_feedback(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()


class WritingTaskScore(BaseModel):
    ta: float
    cc: float
    lr: float
    gra: float
    overall: float
    ta_feedback: str | None = None
    cc_feedback: str | None = None
    lr_feedback: str | None = None
    gra_feedback: str | None = None


class AttemptResponse(BaseModel):
    attempt_id: UUID
    test_version_id: UUID
    test_session_id: UUID | None = None
    attempt_context: AttemptContext = AttemptContext.STANDALONE
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
    test_session_id: UUID | None = None
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
    review_available: bool = True


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
    sessions: list["MockHistoryGroup"] = Field(default_factory=list)
    total: int = Field(ge=0)


class MockHistoryGroup(BaseModel):
    session_id: UUID
    test_version_id: UUID
    test_title: str
    version_number: int
    status: TestSessionStatus
    started_at: datetime
    finished_at: datetime | None
    reading: HistoryItem | None = None
    listening: HistoryItem | None = None
    writing: HistoryItem | None = None
    overall_band_score: float | None = None
