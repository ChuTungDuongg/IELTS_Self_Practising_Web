"""Internal image/reference audit; no chain of thought or public scoring changes."""

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.domains.scoring.writing import validate_writing_criterion_score
from app.schemas.writing_ai import StrictModel


class VisualConflict(StrictModel):
    kind: Literal["NUMERIC", "LABEL", "UNIT", "AXIS", "LEGEND", "COVERAGE", "MAP", "PROCESS"]
    component_id: str | None = Field(default=None, max_length=40)
    reference_excerpt: str = Field(min_length=1, max_length=160)
    image_observation: str = Field(min_length=1, max_length=160)


class Task1ImageAssessment(StrictModel):
    status: Literal["READY", "CONFLICT", "UNREADABLE", "INSUFFICIENT_EVIDENCE"]
    score: Decimal | None = Field(ge=0, le=9, allow_inf_nan=False)
    conflicts: list[VisualConflict] = Field(max_length=4)

    @field_validator("score")
    @classmethod
    def half_band(cls, value: Decimal | None) -> Decimal | None:
        return None if value is None else validate_writing_criterion_score(value)

    @model_validator(mode="after")
    def consistent_decision(self) -> Self:
        if (self.status == "READY") != (self.score is not None):
            raise ValueError("Only a ready assessment may supply a score")
        if (self.status == "CONFLICT") != bool(self.conflicts):
            raise ValueError("Conflicts require reconciliation before scoring")
        return self
