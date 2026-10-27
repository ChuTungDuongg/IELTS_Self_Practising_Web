from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.assignment_targets import AssignmentTarget
from app.schemas.auth import ProfileUpdate

Skill = Literal["READING", "LISTENING", "WRITING", "SPEAKING"]


class LearningGoals(BaseModel):
    overall: Decimal | None = None
    reading: Decimal | None = None
    listening: Decimal | None = None
    writing: Decimal | None = None
    speaking: Decimal | None = None
    model_config = {"extra": "forbid"}

    @field_validator("overall", "reading", "listening", "writing", "speaking")
    @classmethod
    def valid_band(cls, value):
        return ProfileUpdate.validate_band(value)


class PlanTarget(BaseModel):
    assignment_id: UUID | None = None
    resource_id: UUID | None = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def one_target(self):
        if (self.assignment_id is None) == (self.resource_id is None):
            raise ValueError("Reference exactly one existing assignment or resource")
        return self


class PlanWrite(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    target_skill: Skill
    focus_area: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    status: Literal["ACTIVE", "COMPLETED", "ARCHIVED"] = "ACTIVE"
    items: list[PlanTarget] = Field(min_length=1, max_length=30)
    expected_revision: int | None = Field(default=None, ge=1)
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def unique_targets(self):
        if len({(item.assignment_id, item.resource_id) for item in self.items}) != len(self.items):
            raise ValueError("A learning plan cannot repeat an activity")
        return self


class PlanItemResponse(BaseModel):
    id: UUID
    assignment_id: UUID | None
    resource_id: UUID | None
    title: str
    available: bool
    completed: bool
    completion_source: Literal["ACCEPTED_ASSIGNMENT", "RESOURCE_MARKER", "NONE"]
    completed_at: datetime | None


class PlanResponse(BaseModel):
    id: UUID
    student_id: UUID
    created_by_user_id: UUID
    updated_by_user_id: UUID
    title: str
    target_skill: Skill
    focus_area: str
    description: str | None
    status: Literal["ACTIVE", "COMPLETED", "ARCHIVED"]
    revision: int
    created_at: datetime
    updated_at: datetime
    completed_items: int
    items: list[PlanItemResponse]


class PlanPage(BaseModel):
    items: list[PlanResponse]
    total: int


class SkillTrendPoint(BaseModel):
    attempt_id: UUID
    assignment_id: UUID
    at: datetime
    band: float


class SkillPerformance(BaseModel):
    skill: Skill
    sample_size: int
    independent_assessments: int
    recent_independent_assessments: int
    latest: float | None
    average: float | None
    recent_average: float | None
    trends: list[SkillTrendPoint]


class QuestionPerformance(BaseModel):
    skill: Skill
    category: str
    questions_attempted: int
    questions_correct: int
    unanswered: int
    sample_size: int
    repeated_exposures: int
    accuracy: float | None
    recent_accuracy: float | None
    historical_accuracy: float | None
    recent_sample_size: int
    trend: float | None
    confidence_level: Literal["INSUFFICIENT", "MEDIUM", "HIGH"]


class CriterionPerformance(BaseModel):
    skill: Skill
    context: str
    criterion: str
    sample_size: int
    recent_sample_size: int
    average: float
    recent_average: float | None
    historical_average: float | None
    trend: float | None


class Weakness(BaseModel):
    weakness_type: Literal["QUESTION_TYPE", "CRITERION", "SKILL_BAND"]
    skill: Skill
    category: str
    evidence: str
    sample_size: int
    severity: Literal["MODERATE", "HIGH"]
    confidence_level: Literal["MEDIUM", "HIGH"]
    recommendation_reason: str
    observed: float
    baseline: float


class Recommendation(BaseModel):
    target: AssignmentTarget | None = None
    assignment_id: UUID
    title: str
    skill: Skill
    category: str
    reason: str
    href: str


class CompletionActivity(BaseModel):
    target: AssignmentTarget | None = None
    assignment_id: UUID
    title: str
    counts: dict[str, int]


class AttentionStudent(BaseModel):
    student_id: UUID
    display_name: str
    missing: int
    pending_human: int


class LearningDashboard(BaseModel):
    start: datetime
    end: datetime
    active_students: int
    assigned_activities: int
    eligible_requirements: int
    completion_rate: float | None
    on_time_rate: float | None
    counts: dict[str, int]
    pending_human: int
    goals: LearningGoals | None
    skills: list[SkillPerformance]
    question_types: list[QuestionPerformance]
    criteria: list[CriterionPerformance]
    weaknesses: list[Weakness]
    recent_assessments: list["GradeScore"]
    completion_by_assignment: list[CompletionActivity]
    total_completion_activities: int
    attention_students: list[AttentionStudent]
    recommendations: list[Recommendation] = Field(default_factory=list)
    criteria_truncated: bool = False


from app.schemas.classroom_grades import GradeScore  # noqa: E402

LearningDashboard.model_rebuild()
