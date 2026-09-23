from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ModuleType, UserRole
from app.schemas.analytics import AnalyticsDashboard
from app.schemas.attempts import AttemptList
from app.schemas.auth import ProfileFieldsResponse


class AdminUserListItem(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    attempt_count: int
    last_activity_at: datetime | None


class AdminUserList(BaseModel):
    items: list[AdminUserListItem] = Field(default_factory=list)
    total: int
    offset: int
    limit: int


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    users_with_attempts: int
    total_attempts: int
    active_attempts: int
    completed_attempts: int
    completed_full_mocks: int
    attempts_by_skill: dict[ModuleType, int]


class AdminUserDetail(BaseModel):
    user: ProfileFieldsResponse
    history: AttemptList
    analytics: AnalyticsDashboard


class AdminUserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def require_change(self) -> "AdminUserUpdate":
        if self.role is None and self.is_active is None:
            raise ValueError("At least one user property must be supplied")
        return self
