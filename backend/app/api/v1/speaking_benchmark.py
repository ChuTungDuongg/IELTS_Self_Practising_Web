"""Admin-only, owner-scoped benchmark preparation. CPU inference is a separate worker."""

import asyncio
import json
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.speaking_benchmark import (
    JobDTO,
    LabAvailability,
    LabelsDTO,
    LabelsPut,
    Mutation,
    ReviewDraft,
    ReviewDTO,
    ReviewPatch,
    SampleDTO,
    SampleMetadata,
    SamplePage,
    SamplePatch,
)
from app.services.speaking_benchmark import SpeakingBenchmarkService, failure
from app.services.speaking_benchmark_jobs import availability, cancel_job, enqueue
from app.storage.delivery import storage_response


async def mutation_origin(request: Request):
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin is not None
        and origin
        not in {get_settings().frontend_origin.rstrip("/"), str(request.base_url).rstrip("/")}
    ):
        raise failure("SPEAKING_BENCHMARK_ORIGIN_FORBIDDEN", 403)


router = APIRouter(
    prefix="/admin/speaking-benchmark",
    tags=["admin-speaking-benchmark"],
    dependencies=[Depends(mutation_origin)],
)


@router.get("/availability", response_model=LabAvailability)
async def worker_availability(_: AdminUser):
    return availability(get_settings())


@router.get("/samples", response_model=SamplePage)
async def samples(
    actor: AdminUser,
    offset: int = Query(default=0, ge=0, le=100000),
    limit: int = Query(default=25, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBenchmarkService(session, actor.id).list(offset, limit)


@router.post("/samples", response_model=SampleDTO, status_code=201)
async def upload(
    actor: AdminUser,
    metadata: str = Form(max_length=5000),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    try:
        body = SampleMetadata.model_validate(json.loads(metadata))
    except (ValueError, ValidationError):
        await file.close()
        raise failure("SPEAKING_BENCHMARK_METADATA_INVALID") from None
    maximum = settings.speaking_benchmark_max_upload_mb * 1024**2
    if file.size is not None and not 0 < file.size <= maximum:
        await file.close()
        raise failure("SPEAKING_BENCHMARK_UPLOAD_SIZE", 413 if file.size else 422)
    # UploadFile is disk-spooled by Starlette; copy in bounded chunks to a private temp
    # file whose extension is never trusted for media detection.
    try:
        with tempfile.TemporaryDirectory(prefix="benchmark-upload-") as directory:
            path = Path(directory) / "source"
            size = 0
            with path.open("wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > maximum:
                        raise failure("SPEAKING_BENCHMARK_UPLOAD_SIZE", 413)
                    await asyncio.to_thread(destination.write, chunk)
            return await SpeakingBenchmarkService(session, actor.id).upload(path, body)
    finally:
        await file.close()


@router.get("/samples/{sample_id}", response_model=SampleDTO)
async def detail(sample_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)):
    return await SpeakingBenchmarkService(session, actor.id).detail(sample_id)


@router.patch("/samples/{sample_id}", response_model=SampleDTO)
async def patch_sample(
    sample_id: UUID,
    body: SamplePatch,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBenchmarkService(session, actor.id).patch(sample_id, body)


@router.delete("/samples/{sample_id}", status_code=204)
async def delete(
    sample_id: UUID,
    actor: AdminUser,
    expected_revision: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
):
    await SpeakingBenchmarkService(session, actor.id).delete(sample_id, expected_revision)


@router.get("/samples/{sample_id}/audio")
async def audio(
    sample_id: UUID,
    request: Request,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    service = SpeakingBenchmarkService(session, actor.id)
    key, mime = await service.audio(sample_id)
    return await storage_response(
        request,
        service.storage,
        key,
        media_type=mime,
        filename="recording.wav" if mime == "audio/wav" else "recording.mp3",
    )


@router.post("/samples/{sample_id}/diarize", response_model=JobDTO, status_code=202)
async def diarize(sample_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)):
    return await enqueue(SpeakingBenchmarkService(session, actor.id), sample_id)


@router.get("/samples/{sample_id}/jobs", response_model=list[JobDTO])
async def jobs(sample_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)):
    return await SpeakingBenchmarkService(session, actor.id).jobs(sample_id)


@router.post("/samples/{sample_id}/jobs/{job_id}/cancel", response_model=JobDTO)
async def cancel(
    sample_id: UUID, job_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await cancel_job(SpeakingBenchmarkService(session, actor.id), sample_id, job_id)


@router.get("/samples/{sample_id}/review", response_model=ReviewDTO)
async def review(
    sample_id: UUID,
    actor: AdminUser,
    revision: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBenchmarkService(session, actor.id).review(sample_id, revision)


@router.patch("/samples/{sample_id}/review", response_model=ReviewDTO)
async def patch_review(
    sample_id: UUID,
    body: ReviewPatch,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBenchmarkService(session, actor.id).save_review(sample_id, body)


@router.post("/samples/{sample_id}/review/suggest", response_model=ReviewDraft)
async def suggest(
    sample_id: UUID,
    body: ReviewPatch,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBenchmarkService(session, actor.id).save_review(
        sample_id, body, suggestions=True
    )


@router.post("/samples/{sample_id}/approve", response_model=ReviewDTO)
async def approve(
    sample_id: UUID, body: Mutation, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await SpeakingBenchmarkService(session, actor.id).approve(
        sample_id, body.expected_revision
    )


@router.get("/samples/{sample_id}/human-labels", response_model=LabelsDTO)
async def labels(sample_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)):
    return await SpeakingBenchmarkService(session, actor.id).labels(sample_id)


@router.put("/samples/{sample_id}/human-labels", response_model=LabelsDTO)
async def put_labels(
    sample_id: UUID, body: LabelsPut, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await SpeakingBenchmarkService(session, actor.id).save_labels(sample_id, body)
