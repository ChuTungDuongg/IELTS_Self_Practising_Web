"""Private owner-scoped Question Assistant; opening pages never submits audio."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.api.v1.speaking_benchmark import mutation_origin
from app.core.database import get_session
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionJob as Job
from app.schemas.speaking_benchmark_questions import (
    QuestionDecisions,
    QuestionJobCreate,
    QuestionJobDTO,
    QuestionPreflight,
    QuestionReconcile,
    QuestionStart,
)
from app.services import speaking_benchmark_questions as questions
from app.services.speaking_benchmark import SpeakingBenchmarkService

router = APIRouter(
    prefix="/admin/speaking-benchmark",
    tags=["admin-speaking-questions"],
    dependencies=[Depends(mutation_origin)],
)


@router.get("/samples/{sample_id}/question-suggestions", response_model=list[QuestionJobDTO])
async def history(
    sample_id: UUID,
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    service = SpeakingBenchmarkService(session, actor.id)
    async with session.begin():
        await service.owned(sample_id)
        rows = await session.scalars(
            select(Job)
            .where(Job.sample_id == sample_id, Job.owner_id == actor.id)
            .order_by(Job.created_at.desc(), Job.id)
            .offset(offset)
            .limit(limit)
        )
        return [await questions.dto(session, row) for row in rows]


@router.post(
    "/samples/{sample_id}/question-suggestions", response_model=QuestionJobDTO, status_code=201
)
async def create(
    sample_id: UUID,
    body: QuestionJobCreate,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await questions.create_job(SpeakingBenchmarkService(session, actor.id), sample_id, body)


@router.get("/samples/{sample_id}/question-suggestions/{job_id}", response_model=QuestionJobDTO)
async def detail(
    sample_id: UUID, job_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    service = SpeakingBenchmarkService(session, actor.id)
    async with session.begin():
        return await questions.dto(session, await questions.owned_job(service, sample_id, job_id))


@router.post(
    "/samples/{sample_id}/question-suggestions/{job_id}/preflight", response_model=QuestionPreflight
)
async def preflight(
    sample_id: UUID, job_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await questions.preflight(SpeakingBenchmarkService(session, actor.id), sample_id, job_id)


@router.post(
    "/samples/{sample_id}/question-suggestions/{job_id}/start",
    response_model=QuestionJobDTO,
    status_code=202,
)
async def start(
    sample_id: UUID,
    job_id: UUID,
    body: QuestionStart,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await questions.start_job(
        SpeakingBenchmarkService(session, actor.id), sample_id, job_id, body
    )


@router.post(
    "/samples/{sample_id}/question-suggestions/{job_id}/cancel", response_model=QuestionJobDTO
)
async def cancel(
    sample_id: UUID, job_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await questions.cancel_job(
        SpeakingBenchmarkService(session, actor.id), sample_id, job_id
    )


@router.post(
    "/samples/{sample_id}/question-suggestions/{job_id}/reconcile", response_model=QuestionJobDTO
)
async def reconcile(
    sample_id: UUID,
    job_id: UUID,
    body: QuestionReconcile,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await questions.reconcile_job(
        SpeakingBenchmarkService(session, actor.id), sample_id, job_id, body
    )


@router.post(
    "/samples/{sample_id}/question-suggestions/{job_id}/decisions", response_model=QuestionJobDTO
)
async def decisions(
    sample_id: UUID,
    job_id: UUID,
    body: QuestionDecisions,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await questions.decide(
        SpeakingBenchmarkService(session, actor.id), sample_id, job_id, body
    )
