import asyncio
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.dependencies import AdminUser
from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.writing_benchmark import (
    BenchmarkBankSummary,
    BenchmarkCompletionFailure,
    BenchmarkMutation,
    BenchmarkSampleCreate,
    BenchmarkSampleDetail,
    BenchmarkSampleListItem,
    BenchmarkSamplePatch,
)
from app.services.writing_benchmark import WritingBenchmarkService
from app.services.writing_benchmark_export import WritingBenchmarkExportService

router = APIRouter(prefix="/admin/writing-benchmark", tags=["admin-writing-benchmark"])


@router.get("/summary", response_model=BenchmarkBankSummary)
async def summary(_: AdminUser, session: AsyncSession = Depends(get_session)):
    return await WritingBenchmarkService(session).summary()


@router.get("/export", response_class=FileResponse)
async def export(_: AdminUser, session: AsyncSession = Depends(get_session)):
    handle = tempfile.NamedTemporaryFile(prefix="writing-benchmark-", suffix=".zip", delete=False)
    path = Path(handle.name)
    handle.close()
    try:
        await WritingBenchmarkExportService(session).export(path)
    except BaseException:
        await asyncio.to_thread(path.unlink, missing_ok=True)
        raise
    return FileResponse(
        path,
        media_type="application/zip",
        filename="writing-benchmark.zip",
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


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


@router.post("/samples/{sample_id}/image", response_model=BenchmarkSampleDetail)
async def upload_image(
    sample_id: UUID,
    _: AdminUser,
    expected_revision: int = Form(ge=0),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
):
    maximum = min(get_settings().max_image_upload_mb, 10) * 1024 * 1024
    try:
        content = await file.read(maximum + 1)
        return await WritingBenchmarkService(session).replace_image(
            sample_id,
            BenchmarkMutation(expected_revision=expected_revision),
            file.content_type or "",
            file.filename or "",
            content,
        )
    finally:
        await file.close()


@router.get("/samples/{sample_id}/image")
async def image(sample_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)):
    content, mime_type, filename = await WritingBenchmarkService(session).image_content(sample_id)
    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/samples/{sample_id}/image", response_model=BenchmarkSampleDetail)
async def remove_image(
    sample_id: UUID,
    _: AdminUser,
    expected_revision: int = Query(ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await WritingBenchmarkService(session).remove_image(
        sample_id, BenchmarkMutation(expected_revision=expected_revision)
    )
