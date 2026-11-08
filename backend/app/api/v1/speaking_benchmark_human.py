"""Owner-only human annotation and assignment-scoped blind ADMIN assessment."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.api.v1.speaking_benchmark import mutation_origin
from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.speaking_benchmark_human import (
    AdjudicationCreate,
    AdjudicationDTO,
    AdjudicationPage,
    AssessmentDTO,
    AssessmentPage,
    AssessmentSubmit,
    AssignmentCreate,
    AssignmentDTO,
    AssignmentPage,
    AssignmentRevoke,
    BlindAssessmentDTO,
    ExternalAssessmentSubmit,
    RaterCreate,
    RaterDTO,
    RaterPage,
)
from app.services import speaking_benchmark_human as human
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.storage.delivery import storage_response

router = APIRouter(
    prefix="/admin/speaking-benchmark",
    tags=["admin-speaking-benchmark-human"],
    dependencies=[Depends(mutation_origin)],
)


@router.get("/human-raters", response_model=RaterPage)
async def raters(
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await human.list_raters(SpeakingBenchmarkService(session, actor.id), offset, limit)


@router.post("/human-raters", response_model=RaterDTO, status_code=201)
async def create_rater(
    body: RaterCreate, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await human.create_rater(SpeakingBenchmarkService(session, actor.id), body)


@router.get("/samples/{sample_id}/rater-assignments", response_model=AssignmentPage)
async def assignments(
    sample_id: UUID,
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await human.list_assignments(
        SpeakingBenchmarkService(session, actor.id), sample_id, offset, limit
    )


@router.post(
    "/samples/{sample_id}/rater-assignments", response_model=AssignmentDTO, status_code=201
)
async def assign(
    sample_id: UUID,
    body: AssignmentCreate,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await human.create_assignment(
        SpeakingBenchmarkService(session, actor.id), sample_id, body
    )


@router.post(
    "/samples/{sample_id}/rater-assignments/{assignment_id}/revoke", response_model=AssignmentDTO
)
async def revoke(
    sample_id: UUID,
    assignment_id: UUID,
    body: AssignmentRevoke,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await human.revoke_assignment(
        SpeakingBenchmarkService(session, actor.id), sample_id, assignment_id, body
    )


@router.get("/samples/{sample_id}/human-assessments", response_model=AssessmentPage)
async def assessments(
    sample_id: UUID,
    actor: AdminUser,
    review_revision: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await human.list_assessments(
        SpeakingBenchmarkService(session, actor.id), sample_id, review_revision, offset, limit
    )


@router.post(
    "/samples/{sample_id}/human-assessments", response_model=AssessmentDTO, status_code=201
)
async def external_assessment(
    sample_id: UUID,
    body: ExternalAssessmentSubmit,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await human.submit_assessment(
        session, actor.id, body.assignment_id, body, owner_id=actor.id, sample_id=sample_id
    )


@router.get("/human-assessments/agreement")
async def agreement(
    actor: AdminUser,
    sample_id: UUID | None = None,
    review_revision: int | None = Query(None, ge=1),
    session: AsyncSession = Depends(get_session),
):
    return await human.human_agreement(
        SpeakingBenchmarkService(session, actor.id), sample_id, review_revision
    )


@router.get("/samples/{sample_id}/adjudications", response_model=AdjudicationPage)
async def adjudications(
    sample_id: UUID,
    actor: AdminUser,
    review_revision: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await human.list_adjudications(
        SpeakingBenchmarkService(session, actor.id), sample_id, review_revision, offset, limit
    )


@router.post("/samples/{sample_id}/adjudications", response_model=AdjudicationDTO, status_code=201)
async def adjudicate(
    sample_id: UUID,
    body: AdjudicationCreate,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await human.create_adjudication(
        SpeakingBenchmarkService(session, actor.id), sample_id, body
    )


@router.get("/reviewer-assignments", response_model=AssignmentPage)
async def reviewer_assignments(
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await human.reviewer_assignments(session, actor.id, offset, limit)


@router.get("/reviewer-assignments/{assignment_id}", response_model=BlindAssessmentDTO)
async def blind_assignment(
    assignment_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await human.blind_detail(session, actor.id, assignment_id)


@router.get("/reviewer-assignments/{assignment_id}/audio")
async def blind_audio(
    assignment_id: UUID,
    request: Request,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    key, mime = await human.blind_audio(session, actor.id, assignment_id)
    # Storage choice is independent of ownership; the grant was checked above.
    from app.storage.factory import get_asset_storage

    return await storage_response(
        request,
        get_asset_storage(get_settings()),
        key,
        media_type=mime,
        filename="recording.wav" if mime == "audio/wav" else "recording.mp3",
    )


@router.post(
    "/reviewer-assignments/{assignment_id}/assessments",
    response_model=AssessmentDTO,
    status_code=201,
)
async def blind_submit(
    assignment_id: UUID,
    body: AssessmentSubmit,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await human.submit_assessment(session, actor.id, assignment_id, body)
