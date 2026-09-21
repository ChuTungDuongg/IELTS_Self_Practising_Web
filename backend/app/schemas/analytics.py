from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ModuleType


class SkillBandSummary(BaseModel):
    latest: float | None = None
    best: float | None = None
    average: float | None = None


class BandTrendPoint(BaseModel):
    attempt_id: UUID
    skill: ModuleType
    band_score: float
    attempted_at: datetime
    test_title: str
    version_number: int


class QuestionTypeAccuracy(BaseModel):
    question_type: str
    attempted: int = Field(ge=0)
    correct: int = Field(ge=0)
    incorrect: int = Field(ge=0)
    accuracy: float | None


class AnalyticsAttemptOption(BaseModel):
    attempt_id: UUID
    skill: ModuleType
    label: str
    band_score: float | None
    finished_at: datetime


class ContentTiming(BaseModel):
    attempt_id: UUID
    kind: str
    target_id: UUID
    active_seconds: int = Field(ge=0)


class LatestMockSummary(BaseModel):
    session_id: UUID
    test_title: str
    finished_at: datetime
    reading_band: float | None
    listening_band: float | None
    writing_band: float | None
    overall_band: float | None


class AnalyticsDashboard(BaseModel):
    total_finalized_attempts: int = Field(ge=0)
    total_active_seconds: int = Field(ge=0)
    average_attempt_seconds: float | None
    bands: dict[str, SkillBandSummary]
    completed_full_mocks: int = Field(ge=0)
    latest_project_overall: float | None
    latest_full_mock: LatestMockSummary | None
    trends: list[BandTrendPoint]
    question_types: list[QuestionTypeAccuracy]
    weak_areas: list[QuestionTypeAccuracy]
    attempts: list[AnalyticsAttemptOption]
    content_timing: list[ContentTiming]


class WritingCriteriaComparison(BaseModel):
    task1_overall: float | None = None
    task2_overall: float | None = None
    ta: float | None = None
    cc: float | None = None
    lr: float | None = None
    gra: float | None = None


class AttemptComparisonSide(BaseModel):
    attempt_id: UUID
    skill: ModuleType
    test_title: str
    version_number: int
    band_score: float | None
    raw_score: int | None
    max_score: int | None
    elapsed_seconds: int | None
    accuracy: float | None
    question_types: list[QuestionTypeAccuracy]
    writing: WritingCriteriaComparison | None = None


class AttemptComparison(BaseModel):
    same_skill: bool
    same_test_version: bool
    left: AttemptComparisonSide
    right: AttemptComparisonSide
