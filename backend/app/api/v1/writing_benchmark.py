from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.core.database import get_session
from app.schemas.writing_benchmark import (
    BenchmarkCompletionFailure,
    BenchmarkMutation,
    BenchmarkSampleCreate,
    BenchmarkSampleDetail,
    BenchmarkSampleListItem,
    BenchmarkSamplePatch,
)
from app.services.writing_benchmark import WritingBenchmarkService

router = APIRouter(prefix="/admin/writing-benchmark", tags=["admin-writing-benchmark"])


@router.get("/samples", response_model=list[BenchmarkSampleListItem])
async def samples(
    _: AdminUser, task: int = Query(ge=1, le=2), session: AsyncSession = Depends(get_session)
):
    return await WritingBenchmarkService(session).list(task)


@router.post("/samples", response_model=BenchmarkSampleDetail, status_code=201)
async def create_sample(
    body: BenchmarkSampleCreate, _: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await WritingBenchmarkService(session).create(body)


@router.get("/samples/{sample_id}", response_model=BenchmarkSampleDetail)
async def detail(sample_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)):
    return await WritingBenchmarkService(session).detail(sample_id)


@router.patch("/samples/{sample_id}", response_model=BenchmarkSampleDetail)
async def patch_sample(
    sample_id: UUID,
    body: BenchmarkSamplePatch,
    _: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await WritingBenchmarkService(session).patch(sample_id, body)


@router.post("/samples/{sample_id}/complete", response_model=BenchmarkSampleDetail)
async def complete(
    sample_id: UUID,
    body: BenchmarkMutation,
    _: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await WritingBenchmarkService(session).complete(sample_id, body)
    except BenchmarkCompletionFailure as error:
        return JSONResponse(
            status_code=422,
            content={
                "code": "BENCHMARK_INCOMPLETE",
                "message": "Required benchmark fields are incomplete.",
                "errors": [issue.model_dump() for issue in error.issues],
            },
        )


@router.delete("/samples/{sample_id}", status_code=204)
async def delete_sample(
    sample_id: UUID,
    _: AdminUser,
    expected_revision: int = Query(ge=0),
    session: AsyncSession = Depends(get_session),
):
    await WritingBenchmarkService(session).delete(
        sample_id, BenchmarkMutation(expected_revision=expected_revision)
    )
