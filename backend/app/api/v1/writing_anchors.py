"""Private administrator-only human anchor curation; no learner bank endpoints."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.writing_anchors import (
    AnchorCoverageResponse,
    AnchorDetail,
    AnchorPage,
    AnchorSetCreate,
    AnchorSetResponse,
    FrozenTaskPage,
    HumanAnchorInput,
)
from app.services.writing_anchors import WritingAnchorService

router = APIRouter(prefix="/admin/writing-anchors", tags=["admin-writing-anchors"])


@router.get("/sets", response_model=dict[str, list[AnchorSetResponse]])
async def sets(_: AdminUser, session: AsyncSession = Depends(get_session)):
    return {"items": await WritingAnchorService(session).list_sets()}


@router.post("/sets", response_model=AnchorSetResponse, status_code=201)
async def create_set(
    body: AnchorSetCreate, admin: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await WritingAnchorService(session).create_draft(admin.id, body.name)


@router.post("/sets/{set_id}/activate", response_model=AnchorSetResponse)
async def activate(set_id: UUID, admin: AdminUser, session: AsyncSession = Depends(get_session)):
    return await WritingAnchorService(session).activate(admin.id, set_id)


@router.get("/tasks", response_model=FrozenTaskPage)
async def tasks(
    _: AdminUser,
    search: str | None = Query(default=None, max_length=160),
    task_number: int | None = Query(default=None, ge=1, le=2),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await WritingAnchorService(session).list_tasks(
        search=search, task_number=task_number, offset=offset, limit=limit
    )


@router.get("/coverage", response_model=AnchorCoverageResponse)
async def coverage(_: AdminUser, session: AsyncSession = Depends(get_session)):
    return await WritingAnchorService(session).coverage(
        node_budget=get_settings().ai_writing_pairwise_max_tree_nodes
    )


@router.get("/anchors", response_model=AnchorPage)
async def anchors(
    _: AdminUser,
    set_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=160),
    task_number: int | None = Query(default=None, ge=1, le=2),
    writing_task_id: UUID | None = None,
    task_type: str | None = Query(default=None, max_length=64),
    status: Literal["DRAFT", "ACTIVE", "RETIRED"] | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await WritingAnchorService(session).list_anchors(
        set_id=set_id,
        search=search,
        task_number=task_number,
        writing_task_id=writing_task_id,
        task_type=task_type,
        status=status,
        offset=offset,
        limit=limit,
    )


@router.post("/sets/{set_id}/anchors", response_model=AnchorDetail, status_code=201)
async def create_anchor(
    set_id: UUID,
    body: HumanAnchorInput,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await WritingAnchorService(session).create_anchor(admin.id, set_id, body)


@router.get("/anchors/{anchor_id}", response_model=AnchorDetail)
async def anchor_detail(
    anchor_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await WritingAnchorService(session).get_anchor(anchor_id)


@router.patch("/anchors/{anchor_id}", response_model=AnchorDetail)
async def update_anchor(
    anchor_id: UUID,
    body: HumanAnchorInput,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await WritingAnchorService(session).update_anchor(admin.id, anchor_id, body)


@router.delete("/anchors/{anchor_id}", status_code=204)
async def delete_anchor(
    anchor_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
):
    await WritingAnchorService(session).delete_anchor(anchor_id)
