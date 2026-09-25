"""External, human-friendly input for a new Builder draft."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.writing.task_types import WritingTaskType, validate_task_type


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportOption(ImportModel):
    key: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=500)


class ImportQuestion(ImportModel):
    number: int | None = Field(default=None, ge=1, le=40)
    end_number: int | None = Field(default=None, ge=1, le=40)
    prompt: str | None = Field(default=None, max_length=5000)
    answer: str | list[str] | None = None
    target: str | None = None
    options: list[ImportOption] | None = None
    min_selections: int | None = None
    max_selections: int | None = None
    max_words: int | None = None
    max_numbers: int | None = None
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    box: dict[str, float] | None = None
    arrow: dict[str, float] | None = None
    explanation: str | None = None


class ImportDiagramAnnotation(ImportModel):
    id: str | None = None
    kind: Literal["ARROW_LABEL", "NOTE"]
    text: str = Field(min_length=1, max_length=300)
    label_x: float = Field(ge=0, le=1)
    label_y: float = Field(ge=0, le=1)
    target_x: float | None = Field(default=None, ge=0, le=1)
    target_y: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_target(self) -> "ImportDiagramAnnotation":
        if not self.text.strip():
            raise ValueError("Diagram annotation text is required")
        if self.kind == "ARROW_LABEL" and (self.target_x is None or self.target_y is None):
            raise ValueError("Arrow labels require target coordinates")
        if self.kind == "NOTE" and (self.target_x is not None or self.target_y is not None):
            raise ValueError("Plain notes cannot have arrow targets")
        return self


class ImportGroup(ImportModel):
    question_type: str = Field(min_length=1, max_length=80)
    instruction: str = Field(default="", max_length=4000)
    options: list[ImportOption] | None = None
    questions: list[ImportQuestion] | None = None
    content: list[str] | list[list[str]] | None = None
    answers: list[str] | None = None
    numbers: list[int] | None = None
    columns: list[str] | None = None
    mode: Literal["SENTENCE", "PASSAGE"] = "SENTENCE"
    image: str | None = None
    allow_option_reuse: bool | None = None
    title: str | None = None
    annotations: list[ImportDiagramAnnotation] | None = None


class ImportBlock(ImportModel):
    type: Literal["heading", "paragraph"] = "paragraph"
    text: str = Field(min_length=1, max_length=20_000)
    label: str | None = Field(default=None, min_length=1, max_length=20)


class ImportPassage(ImportModel):
    title: str = Field(min_length=1, max_length=240)
    blocks: list[ImportBlock] = Field(min_length=1)
    question_groups: list[ImportGroup] = Field(default_factory=list)


class ImportSection(ImportModel):
    title: str = Field(min_length=1, max_length=240)
    question_groups: list[ImportGroup] = Field(default_factory=list)


class ImportWritingTask(ImportModel):
    task_number: Literal[1, 2]
    task_type: WritingTaskType | None = None
    prompt: str = Field(default="", max_length=20_000)
    minimum_recommended_words: int | None = Field(default=None, ge=1, le=5000)
    image: str | None = None

    @model_validator(mode="after")
    def validate_type(self) -> "ImportWritingTask":
        validate_task_type(self.task_number, self.task_type)
        return self


class ImportModule(ImportModel):
    type: Literal["READING", "LISTENING", "WRITING"]
    title: str | None = Field(default=None, max_length=240)
    recommended_duration_seconds: int | None = Field(default=None, ge=1, le=14_400)
    passages: list[ImportPassage] | None = None
    sections: list[ImportSection] | None = None
    tasks: list[ImportWritingTask] | None = None
    audio: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ImportModule":
        required = {"READING": "passages", "LISTENING": "sections", "WRITING": "tasks"}[self.type]
        if getattr(self, required) is None:
            raise ValueError(f"{self.type} requires {required}")
        if self.type != "READING" and self.passages is not None:
            raise ValueError("Only READING may contain passages")
        if self.type != "LISTENING" and (self.sections is not None or self.audio is not None):
            raise ValueError("Only LISTENING may contain sections or audio")
        if self.type != "WRITING" and self.tasks is not None:
            raise ValueError("Only WRITING may contain tasks")
        if self.sections is not None and len(self.sections) > 4:
            raise ValueError("Listening supports at most four sections")
        return self


class DraftImportManifest(ImportModel):
    format: Literal["ielts-draft-import-v1"]
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    allow_incomplete: bool = False
    modules: list[ImportModule] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_modules(self) -> "DraftImportManifest":
        types = [module.type for module in self.modules]
        if len(types) != len(set(types)):
            raise ValueError("Each module type may appear only once")
        return self
