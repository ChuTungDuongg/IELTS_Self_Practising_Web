from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.core.database import get_session
from app.schemas.admin import AdminStats, AdminUserDetail, AdminUserList, AdminUserUpdate
from app.schemas.auth import UserResponse
from app.services.admin import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStats)
async def stats(_: AdminUser, session: AsyncSession = Depends(get_session)) -> AdminStats:
    return await AdminService(session).stats()


@router.get("/users", response_model=AdminUserList)
async def users(
    _: AdminUser,
    search: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> AdminUserList:
    return await AdminService(session).users(search=search, offset=offset, limit=limit)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def user_detail(
    user_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
) -> AdminUserDetail:
    return await AdminService(session).user_detail(user_id)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: AdminUserUpdate,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    return await AdminService(session).update_user(admin.id, user_id, body)
