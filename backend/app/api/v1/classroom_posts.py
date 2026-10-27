from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.classroom_posts import (
    CommentCreate,
    CommentPage,
    CommentResponse,
    CommentUpdate,
    ContentStatus,
    FeedEntry,
    FeedPage,
    PostCreate,
    PostPin,
    PostUpdate,
)
from app.services.classroom_posts import ClassroomPostService

router = APIRouter(prefix="/classrooms/{classroom_id}", tags=["classroom-feed"])


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    classroom_id: UUID,
    post_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    await ClassroomPostService(session, actor).delete(classroom_id, post_id)


@router.get("/feed", response_model=FeedPage)
async def feed(
    classroom_id: UUID,
    actor: CurrentUser,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=20, ge=1, le=100),
    status: ContentStatus | None = None,
    content_kind: Literal["ANNOUNCEMENT", "DISCUSSION", "ASSIGNMENT_ACTIVITY", "RESOURCE_ACTIVITY"]
    | None = None,
    search: str | None = Query(default=None, max_length=200),
    pinned_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).feed(
        classroom_id,
        cursor=cursor,
        limit=limit,
        status=status,
        content_kind=content_kind,
        search=search,
        pinned_only=pinned_only,
    )


@router.post("/posts", response_model=FeedEntry, status_code=201)
async def create_post(
    classroom_id: UUID,
    body: PostCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).create(classroom_id, body)


@router.get("/posts/{post_id}", response_model=FeedEntry)
async def post_detail(
    classroom_id: UUID,
    post_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).get(classroom_id, post_id)


@router.patch("/posts/{post_id}", response_model=FeedEntry)
async def update_post(
    classroom_id: UUID,
    post_id: UUID,
    body: PostUpdate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).update(classroom_id, post_id, body)


@router.post("/posts/{post_id}/publish", response_model=FeedEntry)
async def publish_post(
    classroom_id: UUID,
    post_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).publish(classroom_id, post_id)


@router.post("/posts/{post_id}/archive", response_model=FeedEntry)
async def archive_post(
    classroom_id: UUID,
    post_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).archive(classroom_id, post_id)


@router.post("/posts/{post_id}/pin", response_model=FeedEntry)
async def pin_post(
    classroom_id: UUID,
    post_id: UUID,
    body: PostPin,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).update(
        classroom_id, post_id, PostUpdate(pinned=body.pinned)
    )


@router.get("/posts/{post_id}/comments", response_model=CommentPage)
async def comments(
    classroom_id: UUID,
    post_id: UUID,
    actor: CurrentUser,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).comments(
        classroom_id, post_id, cursor=cursor, limit=limit
    )


@router.post("/posts/{post_id}/comments", response_model=CommentResponse, status_code=201)
async def create_comment(
    classroom_id: UUID,
    post_id: UUID,
    body: CommentCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).create_comment(classroom_id, post_id, body)


@router.patch("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    classroom_id: UUID,
    comment_id: UUID,
    body: CommentUpdate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).update_comment(classroom_id, comment_id, body)


@router.delete("/comments/{comment_id}", response_model=CommentResponse)
async def delete_comment(
    classroom_id: UUID,
    comment_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomPostService(session, actor).delete_comment(classroom_id, comment_id)
