from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ModuleType, TestSessionStatus
from app.schemas.attempts import AttemptResponse


class TestSessionCreate(BaseModel):
    test_version_id: UUID


class SessionAttemptSummary(BaseModel):
    attempt_id: UUID
    module: ModuleType
    status: str
    band_score: float | None
    raw_score: int | None
    max_score: int | None
    elapsed_seconds: int | None


class TestSessionResponse(BaseModel):
    session_id: UUID
    test_version_id: UUID
    test_title: str
    version_number: int
    status: TestSessionStatus
    started_at: datetime
    finished_at: datetime | None
    current_module: ModuleType | None
    next_module: ModuleType | None
    current_attempt: AttemptResponse | None
    attempts: list[SessionAttemptSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    overall_band_score: float | None = None


class TestSessionStartResponse(BaseModel):
    session: TestSessionResponse
    current_attempt: AttemptResponse
