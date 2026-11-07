"""Private admin grading lifecycle. No provider construction in routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.api.v1.speaking_benchmark import mutation_origin
from app.core.config import get_settings
from app.core.database import get_session
from app.models.speaking_benchmark import SpeakingBenchmarkReview
from app.schemas.speaking_benchmark_grading import PreflightRequest, RetryRequest, RunDTO, RunSubmit
from app.services import speaking_benchmark_grading as grading
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_benchmark_preflight import grading_availability, preflight

router = APIRouter(
    prefix="/admin/speaking-benchmark",
    tags=["admin-speaking-benchmark-evaluation"],
    dependencies=[Depends(mutation_origin)],
)


@router.get("/grading-availability")
async def availability(actor: AdminUser):
    return grading_availability(get_settings())


@router.get("/samples/{sample_id}/grading-reviews")
async def approved_reviews(
    sample_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        await SpeakingBenchmarkService(session, actor.id).owned(sample_id)
        rows = await session.scalars(
            select(SpeakingBenchmarkReview)
            .where(
                SpeakingBenchmarkReview.sample_id == sample_id,
                SpeakingBenchmarkReview.approved_at.is_not(None),
            )
            .order_by(SpeakingBenchmarkReview.revision.desc())
            .limit(100)
        )
        return [{"revision": r.revision, "approved_at": r.approved_at} for r in rows]


@router.post("/samples/{sample_id}/grading/preflight")
async def prepare(
    sample_id: UUID,
    body: PreflightRequest,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await preflight(SpeakingBenchmarkService(session, actor.id), sample_id, body)


@router.post("/samples/{sample_id}/grading-runs", response_model=RunDTO, status_code=202)
async def submit(
    sample_id: UUID, body: RunSubmit, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await grading.submit(SpeakingBenchmarkService(session, actor.id), sample_id, body)


@router.get("/samples/{sample_id}/grading-runs", response_model=list[RunDTO])
async def runs(
    sample_id: UUID,
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    return await grading.list_runs(
        SpeakingBenchmarkService(session, actor.id), sample_id, offset, limit
    )


@router.get("/samples/{sample_id}/grading-runs/{run_id}", response_model=RunDTO)
async def detail(
    sample_id: UUID, run_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await grading.detail(SpeakingBenchmarkService(session, actor.id), sample_id, run_id)


@router.post("/samples/{sample_id}/grading-runs/{run_id}/cancel", response_model=RunDTO)
async def cancel(
    sample_id: UUID, run_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await grading.cancel(SpeakingBenchmarkService(session, actor.id), sample_id, run_id)


@router.post("/samples/{sample_id}/grading-runs/{run_id}/retry-interrupted", response_model=RunDTO)
async def retry(
    sample_id: UUID,
    run_id: UUID,
    body: RetryRequest,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await grading.retry_interrupted(
        SpeakingBenchmarkService(session, actor.id), sample_id, run_id, body
    )
