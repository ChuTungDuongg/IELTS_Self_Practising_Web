from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.classrooms import (
    ClassroomCreate,
    ClassroomList,
    ClassroomResponse,
    ClassroomUpdate,
    InvitationCreate,
    InvitationList,
    InvitationResponse,
    MembershipList,
    MembershipResponse,
)
from app.services.classrooms import ClassroomService

router = APIRouter(tags=["classrooms"])


@router.get("/classrooms", response_model=ClassroomList)
async def list_classrooms(actor: CurrentUser, session: AsyncSession = Depends(get_session)):
    return await ClassroomService(session, actor).list()


@router.post("/classrooms", response_model=ClassroomResponse, status_code=201)
async def create_classroom(
    body: ClassroomCreate, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).create(body)


@router.get("/classrooms/{classroom_id}", response_model=ClassroomResponse)
async def classroom_detail(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).get(classroom_id)


@router.patch("/classrooms/{classroom_id}", response_model=ClassroomResponse)
async def update_classroom(
    classroom_id: UUID,
    body: ClassroomUpdate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomService(session, actor).update(classroom_id, body)


@router.post("/classrooms/{classroom_id}/archive", response_model=ClassroomResponse)
async def archive_classroom(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).archive(classroom_id)


@router.post("/classrooms/{classroom_id}/restore", response_model=ClassroomResponse)
async def restore_classroom(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).restore(classroom_id)


@router.get("/classrooms/{classroom_id}/members", response_model=MembershipList)
async def members(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).members(classroom_id)


@router.post(
    "/classrooms/{classroom_id}/members/{user_id}/remove", response_model=MembershipResponse
)
async def remove_member(
    classroom_id: UUID,
    user_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomService(session, actor).remove_member(classroom_id, user_id)


@router.post("/classrooms/{classroom_id}/leave", response_model=MembershipResponse)
async def leave(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).leave(classroom_id)


@router.get("/classrooms/{classroom_id}/invitations", response_model=InvitationList)
async def invitations(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).invitations(classroom_id)


@router.post(
    "/classrooms/{classroom_id}/invitations", response_model=InvitationResponse, status_code=201
)
async def invite(
    classroom_id: UUID,
    body: InvitationCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomService(session, actor).invite(classroom_id, body)


@router.get("/me/classroom-invitations", response_model=InvitationList)
async def my_invitations(actor: CurrentUser, session: AsyncSession = Depends(get_session)):
    return await ClassroomService(session, actor).my_invitations()


@router.post("/classroom-invitations/{invitation_id}/cancel", response_model=InvitationResponse)
async def cancel_invitation(
    invitation_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).cancel(invitation_id)


@router.post("/classroom-invitations/{invitation_id}/accept", response_model=MembershipResponse)
async def accept_invitation(
    invitation_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).accept(invitation_id)


@router.post("/classroom-invitations/{invitation_id}/decline", response_model=InvitationResponse)
async def decline_invitation(
    invitation_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomService(session, actor).decline(invitation_id)
