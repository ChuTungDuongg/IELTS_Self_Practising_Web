from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.speaking_benchmark_grading import StrictDTO


class ReportFilters(StrictDTO):
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=25, ge=1, le=100)
    split: Literal["DEV", "HOLDOUT"] | None = None
    configuration: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    model: str | None = Field(default=None, max_length=160)
    rubric_version: str | None = Field(default=None, max_length=100)
    prompt_version: str | None = Field(default=None, max_length=100)
    status: Literal["COMPLETED", "PARTIAL", "FAILED", "CANCELLED"] | None = None
    verified_only: bool = True
    uploaded_from: datetime | None = None
    uploaded_to: datetime | None = None
    human_label_kind: Literal["LEGACY", "INDEPENDENT", "ADJUDICATED"] | None = None
    human_label_id: UUID | None = None
    human_label_revision: int | None = Field(default=None, ge=1)

    @property
    def label_selection(self):
        return (
            dict(
                kind=self.human_label_kind,
                id=self.human_label_id,
                revision=self.human_label_revision,
            )
            if self.human_label_kind
            else None
        )

    @model_validator(mode="after")
    def dates(self):
        for value in (self.uploaded_from, self.uploaded_to):
            if value is not None and value.tzinfo is None:
                raise ValueError("Timezone-aware upload dates required")
        if self.uploaded_from and self.uploaded_to and self.uploaded_from > self.uploaded_to:
            raise ValueError("Reversed date range")
        return self
