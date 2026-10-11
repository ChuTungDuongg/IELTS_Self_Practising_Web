from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.enums import NotificationEntityType, NotificationType
from app.repositories.notifications import NotificationRepository
from app.schemas.notifications import (
    NotificationList,
    NotificationResponse,
    NotificationUnreadCount,
)


class NotificationService:
    def __init__(self, session: AsyncSession, actor: User | None = None):
        self.session = session
        self.actor = actor
        self.repository = NotificationRepository(session)

    async def create_once(
        self,
        *,
        user_id: UUID,
        type: NotificationType,
        entity_type: NotificationEntityType,
        entity_id: UUID,
        payload: dict[str, Any],
    ):
        """Stage an idempotent event in the domain operation's transaction."""
        if not self.session.in_transaction():
            raise RuntimeError("Notification creation requires the caller's transaction")
        return await self.repository.create_once(
            user_id=user_id,
            type=type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload,
        )

    def _recipient(self) -> UUID:
        if self.actor is None:
            raise ValueError("Notification reads require an authenticated recipient")
        return self.actor.id

    async def list(self, *, offset: int = 0, limit: int = 100) -> NotificationList:
        async with self.session.begin():
            items = await self.repository.list(self._recipient(), offset, limit)
            return NotificationList(
                items=[NotificationResponse.model_validate(item) for item in items]
            )

    async def unread_count(self) -> NotificationUnreadCount:
        async with self.session.begin():
            return NotificationUnreadCount(
                unread_count=await self.repository.unread_count(self._recipient())
            )

    async def mark_read(self, notification_id: UUID) -> NotificationResponse:
        async with self.session.begin():
            notification = await self.repository.owned(notification_id, self._recipient())
            if notification is None:
                raise AppError("NOTIFICATION_NOT_FOUND", "The notification does not exist.", 404)
            if notification.read_at is None:
                notification.read_at = datetime.now(UTC)
            await self.session.flush()
            return NotificationResponse.model_validate(notification)

    async def mark_all_read(self):
        async with self.session.begin():
            await self.repository.mark_all_read(self._recipient())
