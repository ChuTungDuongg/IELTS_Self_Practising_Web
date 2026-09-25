from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.writing.task_types import WritingTaskType
from app.models.enums import ModuleType, VersionStatus


class TestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    source_label: str | None = Field(default=None, max_length=160)
    test_number: int | None = Field(default=None, ge=1)
    create_initial_draft: bool = True

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Title must be text")
        title = value.strip()
        if not title:
            raise ValueError("Title cannot be blank")
        return title


class TestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)

    _validate_title = field_validator("title", mode="before")(TestCreate.validate_title.__func__)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Description must be text")
        return value.strip() or None


class VersionCreate(BaseModel):
    source_version_id: UUID | None = None


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    status: VersionStatus
    created_at: datetime
    published_at: datetime | None


class TestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    source_label: str | None
    test_number: int | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    versions: list[VersionSummary] = Field(default_factory=list)


class TestDeleteResult(BaseModel):
    test_id: UUID
    action: Literal["DELETED", "ARCHIVED"]


class ModuleSummary(BaseModel):
    id: UUID
    module_type: ModuleType
    title: str | None
    recommended_duration_seconds: int | None
    passage_count: int
    listening_part_count: int
    writing_task_count: int
    question_count: int
    reading_passages: list["ReadingPassageSummary"] = Field(default_factory=list)
    listening_sections: list["ListeningSectionSummary"] = Field(default_factory=list)
    writing_tasks: list["WritingTaskSummary"] = Field(default_factory=list)


class QuestionGroupSummary(BaseModel):
    question_type: str
    start_number: int
    end_number: int


class ReadingPassageSummary(BaseModel):
    title: str
    order_index: int
    question_groups: list[QuestionGroupSummary]


class ListeningSectionSummary(BaseModel):
    title: str | None
    order_index: int
    question_groups: list[QuestionGroupSummary]


class WritingTaskSummary(BaseModel):
    task_number: int
    task_type: WritingTaskType | None
    prompt_excerpt: str | None


class VersionDetail(VersionSummary):
    test_id: UUID
    test_title: str
    modules: list[ModuleSummary]
