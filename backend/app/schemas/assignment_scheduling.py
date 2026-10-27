from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

SubmissionStatus = Literal[
    "NOT_STARTED",
    "IN_PROGRESS",
    "SUBMITTED_ON_TIME",
    "SUBMITTED_LATE",
    "SUBMITTED_NOT_ACCEPTED",
    "MISSED",
]


class SchedulePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    available_from: AwareDatetime | None = None
    due_at: AwareDatetime | None = None
    cutoff_at: AwareDatetime | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=10000, strict=True)
    allow_late_submission: bool = True

    @field_validator("available_from", "due_at", "cutoff_at", mode="before")
    @classmethod
    def explicit_datetime(cls, value):
        if isinstance(value, (int, float)) or (
            isinstance(value, str) and "T" not in value and " " not in value
        ):
            raise ValueError("Supply an explicit timezone-aware datetime")
        return value

    @field_validator("available_from", "due_at", "cutoff_at")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC) if value else None

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.available_from and self.due_at and self.available_from >= self.due_at:
            raise ValueError("Availability must precede the due date")
        if self.due_at and self.cutoff_at and self.due_at > self.cutoff_at:
            raise ValueError("Due date must not follow cut-off")
        if self.available_from and self.cutoff_at and self.available_from >= self.cutoff_at:
            raise ValueError("Availability must precede cut-off")
        return self


class AssignmentScheduleUpdate(SchedulePolicy):
    title: str | None = Field(default=None, max_length=240)
    note: str | None = Field(default=None, max_length=4000)
    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=2000)


class ExtensionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    override_due: bool = False
    due_at_override: AwareDatetime | None = None
    override_cutoff: bool = False
    cutoff_at_override: AwareDatetime | None = None
    additional_attempts: int = Field(default=0, ge=0, le=10000, strict=True)
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("due_at_override", "cutoff_at_override", mode="before")
    @classmethod
    def explicit_datetime(cls, value):
        return SchedulePolicy.explicit_datetime(value)

    @field_validator("due_at_override", "cutoff_at_override")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC) if value else None

    @model_validator(mode="after")
    def explicit(self) -> Self:
        if self.due_at_override is not None and not self.override_due:
            raise ValueError("Enable due override to set its date")
        if self.cutoff_at_override is not None and not self.override_cutoff:
            raise ValueError("Enable cut-off override to set its date")
        return self


class ExtensionResponse(ExtensionWrite):
    id: UUID
    assignment_id: UUID
    student_id: UUID
    revision: int
    revoked: bool
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class AssignmentProgress(BaseModel):
    assignment_id: UUID
    availability_status: Literal["SCHEDULED", "OPEN", "OVERDUE", "CLOSED", "ARCHIVED"]
    submission_status: SubmissionStatus
    available_from: datetime | None
    effective_due_at: datetime | None
    effective_cutoff_at: datetime | None
    max_attempts: int | None
    attempts_used: int
    attempts_remaining: int | None
    can_start: bool
    start_blocked_reason: str | None
    can_resume: bool
    latest_attempt_id: UUID | None
    latest_session_id: UUID | None
    resume_attempt_id: UUID | None
    resume_session_id: UUID | None
    result_attempt_id: UUID | None
    completed_at: datetime | None
    late: bool
    accepted: bool
    historical: bool = False


class ProgressPage(BaseModel):
    items: list[AssignmentProgress]
    total: int


class MonitoringStudent(BaseModel):
    student_id: UUID
    display_name: str
    joined_at: datetime | None
    active_member: bool
    progress: AssignmentProgress
    extension: ExtensionResponse | None


class MonitoringPage(BaseModel):
    items: list[MonitoringStudent]
    total: int
    summary: dict[str, int]


class CalendarEvent(BaseModel):
    assignment_id: UUID
    title: str
    kind: Literal["AVAILABLE", "DUE", "CUTOFF"]
    at: datetime
    progress: AssignmentProgress | None = None


class CalendarPage(BaseModel):
    items: list[CalendarEvent]
    total: int


class PolicyHistoryEntry(BaseModel):
    id: UUID
    revision: int
    student_id: UUID | None
    actor_id: UUID
    kind: str
    effective_at: datetime
    reason: str | None
    policy: SchedulePolicy
    override_due: bool
    override_cutoff: bool
    additional_attempts: int
    revoked: bool


class PolicyHistoryPage(BaseModel):
    items: list[PolicyHistoryEntry]
