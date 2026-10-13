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
    module: (
        Literal[ModuleType.READING, ModuleType.LISTENING, ModuleType.WRITING, ModuleType.SPEAKING]
        | None
    ) = None
    speaking_mode: Literal["PRACTICE", "EXAM"] | None = None
    scope: AttemptScope = AttemptScope.FULL_MODULE
    focused_unit: FocusedUnit | None = None
    timer: TimerRequest = Field(default_factory=lambda: TimerRequest(mode=TimerMode.COUNT_UP))

    @model_validator(mode="after")
    def valid_mode(self):
        if self.focused_unit is not None and self.focused_unit.kind == "SPEAKING_PART":
            raise ValueError("Whole-Part Speaking practice is available only in Skill Practice")
        if self.mode == "MODULE" and self.module is None:
            raise ValueError("A module is required")
        if self.mode == "FULL_MOCK" and (
            self.module
            or self.focused_unit
            or self.speaking_mode
            or self.scope != AttemptScope.FULL_MODULE
        ):
            raise ValueError("Full Mock cannot select a module or focused unit")
        if self.module != ModuleType.SPEAKING and self.speaking_mode is not None:
            raise ValueError("Speaking mode is only available for Speaking")
        if self.module == ModuleType.SPEAKING:
            self.speaking_mode = self.speaking_mode or "PRACTICE"
            if self.timer.mode != TimerMode.COUNT_UP or (
                self.scope == AttemptScope.FOCUSED_UNIT and self.speaking_mode != "PRACTICE"
            ):
                raise ValueError(
                    "Speaking uses prompt deadlines; focused Speaking is practice only"
                )
        return self


class AssignmentStartResponse(BaseModel):
    attempt_id: UUID
    test_session_id: UUID | None = None
