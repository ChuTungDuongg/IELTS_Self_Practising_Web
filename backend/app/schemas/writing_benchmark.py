"""Strict admin authoring contracts; server identity/storage are never writable."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.domains.scoring.writing import validate_writing_criterion_score
from app.domains.writing.task_types import TASK_ONE_TYPES, WritingTaskType
from app.models.enums import WritingBenchmarkSplit, WritingBenchmarkStatus


def half_band(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("A finite half band is required.")
    return validate_writing_criterion_score(value)


Score = Annotated[Decimal, AfterValidator(half_band)]
Criterion = Literal["ta", "tr", "cc", "lr", "gra"]


class BenchmarkSampleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_number: StrictInt = Field(ge=1, le=2)


class BenchmarkMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: StrictInt = Field(ge=0)


class BenchmarkSamplePatch(BenchmarkMutation):
    prompt: StrictStr | None = Field(default=None, max_length=20000)
    essay: StrictStr | None = Field(default=None, max_length=100000)
    split: WritingBenchmarkSplit | None = None
    task1_task_type: WritingTaskType | None = None
    human_scores: dict[Criterion, Score | None] | None = None
    source_note: StrictStr | None = Field(default=None, max_length=2000)
    redistributable: StrictBool | None = None

    @field_validator("task1_task_type")
    @classmethod
    def task_one_type(cls, value):
        if value is not None and value not in TASK_ONE_TYPES:
            raise ValueError("A production Task 1 type is required.")
        return value

    @field_validator("human_scores", mode="before")
    @classmethod
    def numeric_scores(cls, value):
        if isinstance(value, dict) and any(type(score) is bool for score in value.values()):
            raise ValueError("Numeric half bands are required.")
        return value

    @model_validator(mode="after")
    def nonnullable_edits(self):
        for field in ("prompt", "essay", "split", "redistributable", "human_scores"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("Use an empty value instead of null for this field.")
        return self


class BenchmarkSampleListItem(BaseModel):
    id: UUID
    code: str
    task_number: Literal[1, 2]
    sequence_number: int
    status: WritingBenchmarkStatus
    split: WritingBenchmarkSplit
    human_scores: dict[str, float | None]
    human_overall: float | None
    has_image: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class BenchmarkSampleDetail(BenchmarkSampleListItem):
    prompt: str
    essay: str
    task1_task_type: WritingTaskType | None
    source_note: str | None
    redistributable: bool


class BenchmarkFieldIssue(BaseModel):
    path: str
    message: str


class BenchmarkCompletionFailure(Exception):
    def __init__(self, issues: list[BenchmarkFieldIssue]):
        self.issues = issues
        super().__init__("Required benchmark fields are incomplete.")


class BenchmarkBandCount(BaseModel):
    band: float
    actual: int
    suggested: int | None


class BenchmarkTaskSummary(BaseModel):
    task_number: Literal[1, 2]
    capacity: Literal[100] = 100
    total: int = 0
    draft: int = 0
    complete: int = 0
    split_counts: dict[str, int]
    split_targets: dict[str, int]
    overall_distribution: list[BenchmarkBandCount]


class BenchmarkBankSummary(BaseModel):
    tasks: list[BenchmarkTaskSummary]
