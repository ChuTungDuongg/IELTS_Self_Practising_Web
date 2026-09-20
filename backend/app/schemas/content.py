from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ModuleType, VersionStatus
from app.schemas.assets import AssetResponse
from app.schemas.attempts import AttemptResponse, AttemptReview, WritingReview


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
    instruction: str = Field(default="", max_length=4000)
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


class ListeningModuleAudioWrite(BaseModel):
    asset_id: UUID | None = None


class BuilderListeningPart(BaseModel):
    id: UUID
    title: str
    order_index: int
    question_groups: list[BuilderQuestionGroup]


class WritingTaskWrite(BaseModel):
    prompt: str = Field(default="", max_length=20_000)
    image_asset_id: UUID | None = None
    minimum_recommended_words: int | None = Field(default=None, ge=1, le=5000)
    recommended_duration_seconds: int | None = Field(default=None, ge=1, le=14_400)


class BuilderWritingTask(BaseModel):
    id: UUID
    task_number: int
    prompt: str
    image_asset_id: UUID | None = None
    image_asset: AssetResponse | None = None
    minimum_recommended_words: int | None
    recommended_duration_seconds: int | None
    order_index: int


class BuilderModule(BaseModel):
    id: UUID
    module_type: ModuleType
    title: str | None
    recommended_duration_seconds: int | None
    audio_asset: AssetResponse | None = None
    passages: list[BuilderPassage]
    listening_parts: list[BuilderListeningPart]
    writing_tasks: list[BuilderWritingTask] = Field(default_factory=list)


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
    question_groups: list[ExamQuestionGroup]


class ExamWritingTask(BaseModel):
    id: UUID
    task_number: int
    prompt: str
    image_asset_id: UUID | None = None
    image_asset: AssetResponse | None = None
    minimum_recommended_words: int | None
    recommended_duration_seconds: int | None
    order_index: int
    content: str
    word_count: int = Field(ge=0)


class HighlightResponse(BaseModel):
    id: UUID
    target_kind: Literal[
        "PASSAGE_BLOCK", "QUESTION_PROMPT", "TEXT_COMPLETION_SEGMENT", "QUESTION_GROUP_OPTION"
    ]
    target_id: UUID
    segment_id: UUID | None = None
    passage_id: UUID | None = None
    start_block_id: UUID | None = None
    start_offset: int
    end_block_id: UUID | None = None
    end_offset: int
    selected_text: str
    created_at: datetime


class HighlightCreate(BaseModel):
    target_kind: (
        Literal[
            "PASSAGE_BLOCK", "QUESTION_PROMPT", "TEXT_COMPLETION_SEGMENT", "QUESTION_GROUP_OPTION"
        ]
        | None
    ) = None
    target_id: UUID | None = None
    segment_id: UUID | None = None
    passage_id: UUID | None = None
    start_block_id: UUID | None = None
    start_offset: int = Field(ge=0)
    end_block_id: UUID | None = None
    end_offset: int = Field(ge=0)
    selected_text: str = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def normalize_target(self) -> "HighlightCreate":
        if self.target_kind is None and self.passage_id and self.start_block_id:
            if self.end_block_id and self.end_block_id != self.start_block_id:
                raise ValueError("A highlight cannot span separate logical targets")
            self.target_kind = "PASSAGE_BLOCK"
            self.target_id = self.passage_id
            self.segment_id = self.start_block_id
        if not self.target_kind or not self.target_id:
            raise ValueError("A highlight target is required")
        if (
            self.target_kind
            in {
                "PASSAGE_BLOCK",
                "TEXT_COMPLETION_SEGMENT",
                "QUESTION_GROUP_OPTION",
            }
            and not self.segment_id
        ):
            raise ValueError("This highlight target requires a segment ID")
        return self


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
    listening_audio_asset: AssetResponse | None = None
    listening_parts: list[ExamListeningPart] = Field(default_factory=list)
    writing_tasks: list[ExamWritingTask] = Field(default_factory=list)


class ReadingReview(BaseModel):
    review: AttemptReview
    passages: list[BuilderPassage]
    highlights: list[HighlightResponse] = Field(default_factory=list)


class ListeningReview(BaseModel):
    review: AttemptReview
    audio_asset: AssetResponse | None = None
    parts: list[BuilderListeningPart]


class WritingAttemptReview(BaseModel):
    review: AttemptReview
    tasks: list[WritingReview]
    task1_overall: float | None = None
    task2_overall: float | None = None
    weighted_overall: float | None = None
    band_score: float | None = None
