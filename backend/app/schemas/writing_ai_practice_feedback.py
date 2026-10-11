from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_serializer, field_validator

from app.domains.scoring.writing import validate_writing_criterion_score
from app.schemas.writing_ai import StrictModel, WritingRelevanceResult


class SavePracticeFeedback(StrictModel):
    source_run_id: UUID


class PracticeCriterion(StrictModel):
    score: Decimal = Field(ge=0, le=9, allow_inf_nan=False)
    feedback: str = Field(min_length=1, max_length=2000)

    @field_validator("score")
    @classmethod
    def half_band(cls, value):
        return validate_writing_criterion_score(value)

    @field_serializer("score", return_type=float)
    def serialize_score(self, value):
        return float(value)


class PracticeCriteria(StrictModel):
    ta: PracticeCriterion
    cc: PracticeCriterion
    lr: PracticeCriterion
    gra: PracticeCriterion


class PracticeFeedbackResponse(StrictModel):
    id: UUID
    attempt_id: UUID
    writing_task_id: UUID
    source_run_id: UUID
    criteria: PracticeCriteria
    created_at: datetime
    updated_at: datetime
    relevance: WritingRelevanceResult | None = None
