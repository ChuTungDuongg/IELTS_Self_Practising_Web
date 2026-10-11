from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser, CurrentUser
from app.core.database import get_session
from app.models.enums import ModerationStatus
from app.schemas.content_governance import ModerationDecision, ModerationDetail, ModerationSubmit
from app.services.content_governance import ContentGovernanceService

router = APIRouter(tags=["content-governance"])


@router.post(
    "/test-versions/{version_id}/moderation-requests",
    response_model=ModerationDetail,
    status_code=201,
)
async def submit(
    version_id: UUID,
    body: ModerationSubmit,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ContentGovernanceService(session, user).submit_moderation(
        version_id, body.scope, body.note
    )


@router.get(
    "/test-versions/{version_id}/moderation-requests", response_model=list[ModerationDetail]
)
async def version_requests(
    version_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ContentGovernanceService(session, user).list_requests(version_id=version_id)


@router.post("/test-moderation-requests/{request_id}/cancel", response_model=ModerationDetail)
async def cancel(request_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)):
    return await ContentGovernanceService(session, user).cancel_request(request_id)


@router.get("/admin/test-moderation-requests", response_model=list[ModerationDetail])
async def queue(
    user: AdminUser,
    status: ModerationStatus | None = ModerationStatus.PENDING,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await ContentGovernanceService(session, user).list_requests(
        status=status, limit=limit, offset=offset
    )


@router.get("/admin/test-moderation-requests/{request_id}", response_model=ModerationDetail)
async def detail(request_id: UUID, user: AdminUser, session: AsyncSession = Depends(get_session)):
    return await ContentGovernanceService(session, user).get_request(request_id)


@router.post(
    "/admin/test-moderation-requests/{request_id}/approve", response_model=ModerationDetail
)
async def approve(
    request_id: UUID,
    body: ModerationDecision,
    user: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await ContentGovernanceService(session, user).approve(request_id, body.note)


@router.post("/admin/test-moderation-requests/{request_id}/reject", response_model=ModerationDetail)
async def reject(
    request_id: UUID,
    body: ModerationDecision,
    user: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await ContentGovernanceService(session, user).reject(request_id, body.note)


@router.post("/admin/test-moderation-requests/{request_id}/revoke", response_model=ModerationDetail)
async def revoke(
    request_id: UUID,
    body: ModerationDecision,
    user: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await ContentGovernanceService(session, user).revoke(request_id, body.note)
