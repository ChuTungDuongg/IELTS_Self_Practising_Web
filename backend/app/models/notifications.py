import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import NotificationEntityType, NotificationType


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "type", "entity_type", "entity_id", name="uq_notification_event_recipient"
        ),
        Index("ix_notifications_recipient_unread", "user_id", "read_at", "created_at"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType, name="notification_type"))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    entity_type: Mapped[NotificationEntityType] = mapped_column(
        Enum(NotificationEntityType, name="notification_entity_type")
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
