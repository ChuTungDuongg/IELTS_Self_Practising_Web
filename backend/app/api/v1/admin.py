from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.core.database import get_session
from app.schemas.admin import AdminStats, AdminUserDetail, AdminUserList, AdminUserUpdate
from app.schemas.admin_directory import (
    DirectoryClassroomsPage,
    DirectoryPeoplePage,
    DirectoryPerson,
    DirectoryRole,
)
from app.schemas.auth import UserResponse
from app.services.admin import AdminService
from app.services.admin_directory import AdminDirectoryService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/directory/people", response_model=DirectoryPeoplePage)
async def directory_people(
    _: AdminUser,
    role: DirectoryRole = Query(default="TEACHER"),
    search: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> DirectoryPeoplePage:
    return await AdminDirectoryService(session).people(
        role=role, search=search, offset=offset, limit=limit
    )


@router.get("/directory/people/{person_id}", response_model=DirectoryPerson)
async def directory_person(
    person_id: UUID,
    _: AdminUser,
    role: DirectoryRole = Query(default="TEACHER"),
    session: AsyncSession = Depends(get_session),
) -> DirectoryPerson:
    return await AdminDirectoryService(session).person(person_id, role=role)


@router.get("/directory/classrooms", response_model=DirectoryClassroomsPage)
async def directory_classrooms(
    _: AdminUser,
    teacher_id: UUID | None = Query(default=None),
    student_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> DirectoryClassroomsPage:
    return await AdminDirectoryService(session).classrooms(
        teacher_id=teacher_id, student_id=student_id, search=search, offset=offset, limit=limit
    )


@router.get("/stats", response_model=AdminStats)
async def stats(_: AdminUser, session: AsyncSession = Depends(get_session)) -> AdminStats:
    return await AdminService(session).stats()


@router.get("/users", response_model=AdminUserList)
async def users(
    _: AdminUser,
    search: str | None = Query(default=None, max_length=160),
    is_active: bool | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> AdminUserList:
    return await AdminService(session).users(
        search=search, is_active=is_active, offset=offset, limit=limit
    )


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


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID, admin: AdminUser, session: AsyncSession = Depends(get_session)
) -> None:
    await AdminService(session).delete_user(admin.id, user_id)
