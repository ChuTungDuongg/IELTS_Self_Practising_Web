from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.services.classroom_capabilities import Capability

StaffRole = Literal["CO_TEACHER", "TEACHING_ASSISTANT"]


class StaffPermissions(BaseModel):
    content_manage: bool = False
    discussion_moderate: bool = False
    analytics_view: bool = False
    learning_plans_manage: bool = False
    model_config = {"extra": "forbid", "from_attributes": True}


class StaffInvite(StaffPermissions):
    email: EmailStr
    staff_role: StaffRole


class StaffUpdate(StaffPermissions):
    staff_role: StaffRole


class StaffResponse(StaffPermissions):
    id: UUID
    classroom_id: UUID
    classroom_name: str
    user_id: UUID
    display_name: str
    email: str
    staff_role: StaffRole
    status: Literal["PENDING", "ACCEPTED", "DECLINED", "CANCELLED", "REVOKED"]
    invited_by_user_id: UUID
    created_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class ClassroomAccess(BaseModel):
    role: Literal["OWNER", "CO_TEACHER", "TEACHING_ASSISTANT", "STUDENT", "ADMIN"]
    capabilities: list[Capability] = Field(default_factory=list)
