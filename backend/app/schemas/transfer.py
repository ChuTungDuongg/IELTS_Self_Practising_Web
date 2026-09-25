import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.writing.task_types import WritingTaskType, validate_task_type
from app.models.enums import AssetType, ModuleType, VersionStatus

TRANSFER_FORMAT = "devweblocalforielts-test-bundle"
TRANSFER_SCHEMA_VERSION = 1


class PortableQuestion(BaseModel):
    id: UUID
    number: int = Field(ge=1)
    prompt: str = Field(min_length=1, max_length=5000)
    config: dict[str, Any]
    answer_key: dict[str, Any]
    explanation: str | None = None
    order_index: int = Field(ge=0)


class PortableQuestionGroup(BaseModel):
    id: UUID
    passage_id: UUID | None = None
    listening_part_id: UUID | None = None
    image_asset_id: UUID | None = None
    section_reference: str | None = Field(default=None, max_length=120)
    question_type: str = Field(min_length=1, max_length=80)
    instruction: str = Field(max_length=4000)
    config: dict[str, Any]
    order_index: int = Field(ge=0)
    questions: list[PortableQuestion]

    @model_validator(mode="after")
    def validate_questions(self) -> "PortableQuestionGroup":
        numbers = [question.number for question in self.questions]
        orders = [question.order_index for question in self.questions]
        if (
            not self.questions
            or len(numbers) != len(set(numbers))
            or len(orders) != len(set(orders))
        ):
            raise ValueError("Question numbers and order indexes must be unique within a group")
        return self


class PortablePassage(BaseModel):
    id: UUID
    title: str = Field(min_length=1, max_length=240)
    order_index: int = Field(ge=0)
    content_json: list[dict[str, Any]]
    plain_text: str


class PortableListeningPart(BaseModel):
    id: UUID
    title: str = Field(min_length=1, max_length=240)
    order_index: int = Field(ge=0)


class PortableWritingTask(BaseModel):
    id: UUID
    task_number: int = Field(ge=1)
    task_type: WritingTaskType | None = None
    prompt: str = Field(max_length=20_000)
    image_asset_id: UUID | None = None
    minimum_recommended_words: int | None = Field(default=None, ge=1, le=5000)
    recommended_duration_seconds: int | None = Field(default=None, ge=1, le=14_400)
    order_index: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_type(self) -> "PortableWritingTask":
        validate_task_type(self.task_number, self.task_type)
        return self


class PortableModule(BaseModel):
    id: UUID
    module_type: ModuleType
    title: str | None = Field(default=None, max_length=240)
    recommended_duration_seconds: int | None = Field(default=None, ge=1)
    order_index: int = Field(ge=0)
    audio_asset_id: UUID | None = None
    passages: list[PortablePassage] = Field(default_factory=list)
    listening_parts: list[PortableListeningPart] = Field(default_factory=list)
    writing_tasks: list[PortableWritingTask] = Field(default_factory=list)
    question_groups: list[PortableQuestionGroup] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_child_ordering(self) -> "PortableModule":
        for label, values in (
            ("passage", [item.order_index for item in self.passages]),
            ("Listening part", [item.order_index for item in self.listening_parts]),
            ("Writing task", [item.order_index for item in self.writing_tasks]),
            ("question group", [item.order_index for item in self.question_groups]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} order indexes must be unique within a module")
        task_numbers = [item.task_number for item in self.writing_tasks]
        if len(task_numbers) != len(set(task_numbers)):
            raise ValueError("Writing task numbers must be unique within a module")
        return self


class PortableVersion(BaseModel):
    id: UUID
    version_number: int = Field(ge=1)
    status: VersionStatus
    published_at: datetime | None = None
    modules: list[PortableModule]

    @model_validator(mode="after")
    def validate_modules(self) -> "PortableVersion":
        module_types = [module.module_type for module in self.modules]
        module_orders = [module.order_index for module in self.modules]
        if len(module_types) != len(set(module_types)) or len(module_orders) != len(
            set(module_orders)
        ):
            raise ValueError("A transferred version contains duplicate module types or ordering")
        return self


class PortableTest(BaseModel):
    id: UUID
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    source_label: str | None = Field(default=None, max_length=160)
    test_number: int | None = Field(default=None, ge=1)
    archived_at: datetime | None = None
    versions: list[PortableVersion]

    @model_validator(mode="after")
    def validate_version_lifecycle(self) -> "PortableTest":
        numbers = [version.version_number for version in self.versions]
        if len(numbers) != len(set(numbers)):
            raise ValueError("A transferred test contains duplicate version numbers")
        for state in (VersionStatus.DRAFT, VersionStatus.PUBLISHED):
            if sum(version.status == state for version in self.versions) > 1:
                raise ValueError(f"A transferred test contains more than one {state.value} version")
        for version in self.versions:
            if version.status == VersionStatus.PUBLISHED and version.published_at is None:
                raise ValueError("Published versions must include published_at")
        return self


class ManifestTest(BaseModel):
    source_id: UUID
    path: str
    title: str


class ManifestAsset(BaseModel):
    source_id: UUID
    source_version_id: UUID
    path: str
    asset_type: AssetType
    mime_type: str
    original_filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("original_filename")
    @classmethod
    def safe_original_filename(cls, value: str) -> str:
        if "/" in value or "\\" in value or re.match(r"^[A-Za-z]:", value):
            raise ValueError("Asset original filenames must not contain paths")
        return value


class TransferManifest(BaseModel):
    format: Literal[TRANSFER_FORMAT] = TRANSFER_FORMAT
    schema_version: Literal[TRANSFER_SCHEMA_VERSION] = TRANSFER_SCHEMA_VERSION
    exported_at: datetime
    tests: list[ManifestTest] = Field(min_length=1)
    assets: list[ManifestAsset] = Field(default_factory=list)


class TransferExportRequest(BaseModel):
    test_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> "TransferExportRequest":
        if len(self.test_ids) != len(set(self.test_ids)):
            raise ValueError("test_ids must be unique")
        return self


class ImportedTest(BaseModel):
    test_id: UUID
    title: str


class TransferImportResult(BaseModel):
    imported_tests: list[ImportedTest]
    version_count: int
    asset_count: int
