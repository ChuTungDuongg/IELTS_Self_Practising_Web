from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ModuleType, VersionStatus
from app.schemas.assets import AssetResponse
from app.schemas.attempts import AttemptResponse, AttemptReview


class TextBlock(BaseModel):
    id: UUID
    type: Literal["paragraph", "heading"] = "paragraph"
    label: str | None = Field(default=None, min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=20_000)


class ModuleCreate(BaseModel):
    module_type: ModuleType
    title: str | None = Field(default=None, max_length=240)
    recommended_duration_seconds: int | None = Field(default=None, ge=1)


class PassageWrite(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    order_index: int = Field(ge=0)
    blocks: list[TextBlock] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_block_identity(self) -> "PassageWrite":
        ids = [block.id for block in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("Passage block IDs must be unique")
        labels = [
            block.label.casefold()
            for block in self.blocks
            if block.type == "paragraph" and block.label
        ]
        if len(labels) != len(set(labels)):
            raise ValueError("Paragraph labels must be unique")
        return self


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
    image_asset_id: UUID | None = None

    @model_validator(mode="after")
    def validate_question_identity_and_order(self) -> "QuestionGroupWrite":
        question_ids = [question.id for question in self.questions if question.id is not None]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Question IDs must be unique")
        order_indexes = [question.order_index for question in self.questions]
        if len(order_indexes) != len(set(order_indexes)):
            raise ValueError("Question order indexes must be unique")
        return self


class QuestionGroupOrderWrite(BaseModel):
    group_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "QuestionGroupOrderWrite":
        if len(self.group_ids) != len(set(self.group_ids)):
            raise ValueError("Question group IDs must be unique")
        return self


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
    image_asset_id: UUID | None = None
    image_asset: AssetResponse | None = None


class BuilderPassage(BaseModel):
    id: UUID
    title: str
    order_index: int
    blocks: list[TextBlock]
    question_groups: list[BuilderQuestionGroup]


class ListeningPartWrite(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    order_index: int = Field(ge=0, le=3)


class ListeningPartAudioWrite(BaseModel):
    asset_id: UUID | None = None


class BuilderListeningPart(BaseModel):
    id: UUID
    title: str
    order_index: int
    audio_asset: AssetResponse | None
    question_groups: list[BuilderQuestionGroup]


class BuilderModule(BaseModel):
    id: UUID
    module_type: ModuleType
    title: str | None
    recommended_duration_seconds: int | None
    passages: list[BuilderPassage]
    listening_parts: list[BuilderListeningPart]


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


class ExamListeningPart(BaseModel):
    id: UUID
    title: str
    order_index: int
    audio_asset: AssetResponse | None
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
    listening_parts: list[ExamListeningPart] = Field(default_factory=list)


class ReadingReview(BaseModel):
    review: AttemptReview
    passages: list[BuilderPassage]


class ListeningReview(BaseModel):
    review: AttemptReview
    parts: list[BuilderListeningPart]
