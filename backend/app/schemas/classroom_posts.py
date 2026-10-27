from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.classroom_classwork import ResourceResponse

PostKind = Literal["ANNOUNCEMENT", "DISCUSSION"]
ContentStatus = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]


class PostCreate(BaseModel):
    kind: PostKind
    title: str | None = Field(default=None, max_length=240)
    body: str = Field(min_length=1, max_length=20000)
    resource_ids: list[UUID] = Field(default_factory=list, max_length=50)
    status: Literal["DRAFT", "PUBLISHED"] = "DRAFT"
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @field_validator("resource_ids")
    @classmethod
    def unique_resources(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Resource references must be unique")
        return values


class PostUpdate(BaseModel):
    kind: PostKind | None = None
    title: str | None = Field(default=None, max_length=240)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    resource_ids: list[UUID] | None = Field(default=None, max_length=50)
    status: ContentStatus | None = None
    pinned: bool | None = None
    locked: bool | None = None
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set - {"title"}
        ):
            raise ValueError("Supply a valid post property to change")
        if self.resource_ids is not None and len(self.resource_ids) != len(set(self.resource_ids)):
            raise ValueError("Resource references must be unique")
        return self


class PostPin(BaseModel):
    pinned: bool
    model_config = {"extra": "forbid"}


class FeedEntry(BaseModel):
    id: UUID
    kind: Literal["ANNOUNCEMENT", "DISCUSSION", "ASSIGNMENT_ACTIVITY", "RESOURCE_ACTIVITY"]
    title: str | None
    body: str
    status: ContentStatus
    pinned: bool
    locked: bool = False
    author_id: UUID
    author_name: str
    author_role: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    comment_count: int
    resource_ids: list[UUID]
    assignment_id: UUID | None = None
    resource: ResourceResponse | None = None
    resource_topic: str | None = None


class FeedPage(BaseModel):
    items: list[FeedEntry]
    next_cursor: str | None = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class CommentUpdate(CommentCreate):
    pass


class CommentResponse(BaseModel):
    id: UUID
    post_id: UUID
    author_id: UUID
    author_name: str
    body: str
    state: Literal["VISIBLE", "RETRACTED", "MODERATED"]
    created_at: datetime
    updated_at: datetime


class CommentPage(BaseModel):
    items: list[CommentResponse]
    next_cursor: str | None = None
