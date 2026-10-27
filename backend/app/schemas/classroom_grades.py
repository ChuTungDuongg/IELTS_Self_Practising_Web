from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.assignment_targets import AssignmentTarget

Selection = Literal["LATEST_ACCEPTED", "FIRST_ACCEPTED", "BEST_ACCEPTED"]


class GradePolicyUpdate(BaseModel):
    grade_selection: Selection
    expected_revision: int = Field(ge=0)
    model_config = {"extra": "forbid"}


class GradeScore(BaseModel):
    assignment_id: UUID
    root_id: UUID
    kind: Literal["ATTEMPT", "SESSION"]
    result_attempt_id: UUID | None
    skill: str
    scope: str
    context: str
    band: float | None
    raw_score: int | None
    max_score: int | None
    provenance: Literal["OBJECTIVE", "HUMAN_FINAL", "PENDING_HUMAN", "UNAVAILABLE"]
    finished_at: datetime
    accepted: bool
    late: bool
    submission_status: str
    mixed_context_fallback: bool = False
    breakdown: list["GradeComponent"] = Field(default_factory=list)


class GradeComponent(BaseModel):
    attempt_id: UUID
    skill: str
    band: float | None
    raw_score: int | None
    max_score: int | None
    provenance: str
    task_score: float | None = None


class GradeColumn(BaseModel):
    target: AssignmentTarget | None = None
    id: UUID
    title: str
    grade_selection: Selection
    policy_revision: int


class GradeCell(BaseModel):
    assignment_id: UUID
    submission_status: str
    attempts_used: int
    eligible: bool
    score: GradeScore | None


class GradeStudent(BaseModel):
    student_id: UUID
    display_name: str
    active_member: bool
    cells: list[GradeCell]


class GradebookPage(BaseModel):
    assignments: list[GradeColumn]
    students: list[GradeStudent]
    total_students: int
    total_assignments: int


class AcademicProfile(BaseModel):
    student_id: UUID
    display_name: str
    active_member: bool
    counts: dict[str, int]
    assignments: list[GradeCell]
    history: list[GradeScore]
    total_assignments: int
    total_history: int
    assignment_offset: int
    history_offset: int
