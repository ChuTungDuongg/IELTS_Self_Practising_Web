from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import ClassroomStatus, InvitationStatus


class ClassroomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class ClassroomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or ("name" in self.model_fields_set and self.name is None):
            raise ValueError("Supply a valid classroom property to change")
        return self


class ClassroomResponse(BaseModel):
    id: UUID
    teacher_id: UUID
    name: str
    description: str | None
    status: ClassroomStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    teacher_name: str | None = None
    active_member_count: int | None = None
    model_config = {"from_attributes": True}


class ClassroomList(BaseModel):
    items: list[ClassroomResponse]


class InvitationCreate(BaseModel):
    email: EmailStr
    model_config = {"extra": "forbid"}

    @field_validator("email", mode="before")
    @classmethod
    def strip_email(cls, value):
        return value.strip() if isinstance(value, str) else value


class InvitationResponse(BaseModel):
    id: UUID
    classroom_id: UUID
    classroom_name: str
    invited_email: str
    invited_email_normalized: str
    invited_user_id: UUID | None
    invited_by_user_id: UUID
    status: InvitationStatus
    created_at: datetime
    responded_at: datetime | None
    cancelled_at: datetime | None


class InvitationList(BaseModel):
    items: list[InvitationResponse]


class MembershipResponse(BaseModel):
    id: UUID
    classroom_id: UUID
    user_id: UUID
    display_name: str
    email: str
    joined_at: datetime
    left_at: datetime | None
    removed_by_user_id: UUID | None


class MembershipList(BaseModel):
    items: list[MembershipResponse]
