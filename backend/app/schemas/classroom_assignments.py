from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AssignmentStatus, AttemptScope, ModuleType, TimerMode
from app.schemas.attempts import FocusedUnit, TimerRequest
from app.schemas.tests import VersionDetail


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_version_id: UUID
    title: str | None = Field(default=None, max_length=240)
    note: str | None = Field(default=None, max_length=4000)


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    classroom_id: UUID
    test_version_id: UUID
    created_by_user_id: UUID
    title: str | None
    note: str | None
    status: AssignmentStatus
    created_at: datetime
    archived_at: datetime | None
    version: VersionDetail | None = None


class AssignmentStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["MODULE", "FULL_MOCK"]
    module: ModuleType | None = None
    scope: AttemptScope = AttemptScope.FULL_MODULE
    focused_unit: FocusedUnit | None = None
    timer: TimerRequest = Field(default_factory=lambda: TimerRequest(mode=TimerMode.COUNT_UP))

    @model_validator(mode="after")
    def valid_mode(self):
        if self.mode == "MODULE" and self.module is None:
            raise ValueError("A module is required")
        if self.mode == "FULL_MOCK" and (
            self.module or self.focused_unit or self.scope != AttemptScope.FULL_MODULE
        ):
            raise ValueError("Full Mock cannot select a module or focused unit")
        return self


class AssignmentStartResponse(BaseModel):
    attempt_id: UUID
    test_session_id: UUID | None = None
