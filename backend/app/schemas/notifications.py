from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import NotificationEntityType, NotificationType


class NotificationResponse(BaseModel):
    id: UUID
    type: NotificationType
    payload_json: dict[str, Any]
    entity_type: NotificationEntityType
    entity_id: UUID
    read_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class NotificationList(BaseModel):
    items: list[NotificationResponse]


class NotificationUnreadCount(BaseModel):
    unread_count: int
