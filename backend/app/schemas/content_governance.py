from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ModerationScope, ModerationStatus


class ModerationSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: ModerationScope
    note: str | None = Field(default=None, max_length=2000)


class ModerationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=2000)


class ModerationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    test_version_id: UUID
    scope: ModerationScope
    status: ModerationStatus
    submitted_by_user_id: UUID
    reviewed_by_user_id: UUID | None
    submit_note: str | None
    review_note: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    cancelled_at: datetime | None
    revoked_at: datetime | None
    revoked_by_user_id: UUID | None
    revoke_reason: str | None
    test_id: UUID | None = None
    test_title: str | None = None
    version_number: int | None = None
