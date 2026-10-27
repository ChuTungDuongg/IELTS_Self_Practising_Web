from datetime import datetime
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContentStatus = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]


class SectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    status: ContentStatus = "DRAFT"


class SectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    status: ContentStatus | None = None

    @model_validator(mode="after")
    def required_values(self) -> Self:
        if any(getattr(self, key) is None for key in self.model_fields_set & {"title", "status"}):
            raise ValueError("Title and status cannot be null")
        return self


class ResourceCreate(SectionCreate):
    kind: Literal["TEXT", "LINK"]
    body: str | None = Field(default=None, min_length=1, max_length=50000)
    url: str | None = Field(default=None, max_length=2048)
    section_id: UUID | None = None

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if value is not None:
            parts = urlsplit(value)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.username
                or parts.password
                or any(ord(c) < 32 for c in value)
            ):
                raise ValueError("Use an absolute HTTP or HTTPS URL without credentials")
        return value

    @model_validator(mode="after")
    def target(self) -> Self:
        if self.kind == "TEXT" and (not self.body or self.url is not None):
            raise ValueError("Text resources require only a body")
        if self.kind == "LINK" and (not self.url or self.body is not None):
            raise ValueError("Link resources require only a URL")
        return self


class ResourceUpdate(SectionUpdate):
    body: str | None = Field(default=None, min_length=1, max_length=50000)
    url: str | None = Field(default=None, max_length=2048)
    _safe_url = field_validator("url")(ResourceCreate.safe_url.__func__)


class SectionResponse(SectionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    classroom_id: UUID
    position: int
    created_at: datetime
    updated_at: datetime


class ResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    classroom_id: UUID
    title: str
    description: str | None
    kind: Literal["TEXT", "LINK", "FILE"]
    body: str | None
    url: str | None
    status: ContentStatus
    original_filename: str | None
    media_type: str | None
    size_bytes: int | None
    created_at: datetime
    updated_at: datetime


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    section_id: UUID | None
    resource_id: UUID | None
    assignment_id: UUID | None
    position: int


class ClassworkResponse(BaseModel):
    revision: int
    sections: list[SectionResponse]
    resources: list[ResourceResponse]
    items: list[ItemResponse]
    removed_assignment_ids: list[UUID] = Field(default_factory=list)


class ReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[UUID] = Field(max_length=500)
    expected_revision: int = Field(ge=0)

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Ordering must contain unique identifiers")
        return value


class ItemReorderRequest(ReorderRequest):
    section_id: UUID | None


class AssignmentPlacement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_id: UUID | None
    assignment_id: UUID
