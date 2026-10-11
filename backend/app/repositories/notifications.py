from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_once(self, **values) -> Notification:
        result = await self.session.scalar(
            insert(Notification)
            .values(id=uuid4(), **values)
            .on_conflict_do_nothing(constraint="uq_notification_event_recipient")
            .returning(Notification)
        )
        if result is not None:
            return result
        existing = await self.session.scalar(
            select(Notification).where(
                Notification.user_id == values["user_id"],
                Notification.type == values["type"],
                Notification.entity_type == values["entity_type"],
                Notification.entity_id == values["entity_id"],
            )
        )
        assert existing is not None
        return existing

    async def list(self, user_id: UUID, offset: int, limit: int):
        return list(
            await self.session.scalars(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id)
                .offset(offset)
                .limit(limit)
            )
        )

    async def unread_count(self, user_id: UUID) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            )
            or 0
        )

    async def owned(self, notification_id: UUID, user_id: UUID):
        return await self.session.scalar(
            select(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )

    async def mark_all_read(self, user_id: UUID):
        await self.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(UTC))
        )
