from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.notifications import (
    NotificationList,
    NotificationResponse,
    NotificationUnreadCount,
)
from app.services.notifications import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
async def list_notifications(
    actor: CurrentUser,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await NotificationService(session, actor).list(offset=offset, limit=limit)


@router.get("/unread-count", response_model=NotificationUnreadCount)
async def unread_count(actor: CurrentUser, session: AsyncSession = Depends(get_session)):
    return await NotificationService(session, actor).unread_count()


@router.post("/read-all", status_code=204)
async def mark_all_read(actor: CurrentUser, session: AsyncSession = Depends(get_session)) -> None:
    await NotificationService(session, actor).mark_all_read()


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await NotificationService(session, actor).mark_read(notification_id)
