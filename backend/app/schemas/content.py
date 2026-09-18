from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ModuleType, VersionStatus
from app.schemas.attempts import AttemptResponse, AttemptReview


class TextBlock(BaseModel):
    id: UUID
    type: Literal["paragraph", "heading"] = "paragraph"
    text: str = Field(min_length=1, max_length=20_000)


class ModuleCreate(BaseModel):
    module_type: ModuleType
    title: str | None = Field(default=None, max_length=240)
    recommended_duration_seconds: int | None = Field(default=None, ge=1)


class PassageWrite(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    order_index: int = Field(ge=0)
    blocks: list[TextBlock] = Field(min_length=1)


class QuestionWrite(BaseModel):
    id: UUID | None = None
    number: int = Field(ge=1)
    prompt: str = Field(min_length=1, max_length=5000)
    config: dict[str, Any] = Field(default_factory=dict)
    answer_key: dict[str, Any]
    explanation: str | None = None
    order_index: int = Field(ge=0)


class QuestionGroupWrite(BaseModel):
    question_type: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=4000)
    config: dict[str, Any] = Field(default_factory=dict)
    order_index: int = Field(ge=0)
    questions: list[QuestionWrite] = Field(min_length=1)


class BuilderQuestion(BaseModel):
    id: UUID
    number: int
    prompt: str
    config: dict[str, Any]
    answer_key: dict[str, Any]
    explanation: str | None
    order_index: int


class BuilderQuestionGroup(BaseModel):
    id: UUID
    question_type: str
    instruction: str
    config: dict[str, Any]
    order_index: int
    questions: list[BuilderQuestion]


class BuilderPassage(BaseModel):
    id: UUID
    title: str
    order_index: int
    blocks: list[TextBlock]
    question_groups: list[BuilderQuestionGroup]


class BuilderModule(BaseModel):
    id: UUID
    module_type: ModuleType
    title: str | None
    recommended_duration_seconds: int | None
    passages: list[BuilderPassage]


class BuilderVersion(BaseModel):
    id: UUID
    test_id: UUID
    test_title: str
    version_number: int
    status: VersionStatus
    modules: list[BuilderModule]


class ExamQuestion(BaseModel):
    id: UUID
    number: int
    prompt: str
    config: dict[str, Any]
    order_index: int
    value: Any | None = None
    flagged: bool = False


class ExamQuestionGroup(BaseModel):
    id: UUID
    question_type: str
    instruction: str
    config: dict[str, Any]
    order_index: int
    questions: list[ExamQuestion]


class ExamPassage(BaseModel):
    id: UUID
    title: str
    order_index: int
    blocks: list[TextBlock]
    question_groups: list[ExamQuestionGroup]


class HighlightResponse(BaseModel):
    id: UUID
    passage_id: UUID
    start_block_id: UUID
    start_offset: int
    end_block_id: UUID
    end_offset: int
    selected_text: str
    created_at: datetime


class HighlightCreate(BaseModel):
    passage_id: UUID
    start_block_id: UUID
    start_offset: int = Field(ge=0)
    end_block_id: UUID
    end_offset: int = Field(ge=0)
    selected_text: str = Field(min_length=1, max_length=10_000)


class FlagUpdate(BaseModel):
    flagged: bool


class FlagResponse(BaseModel):
    question_id: UUID
    flagged: bool


class AttemptExam(BaseModel):
    attempt: AttemptResponse
    test_title: str
    passages: list[ExamPassage]
    highlights: list[HighlightResponse]


class ReadingReview(BaseModel):
    review: AttemptReview
    passages: list[BuilderPassage]
