"""Private owner-scoped research APIs. No requests execute in this module."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.api.v1.speaking_benchmark import mutation_origin
from app.core.database import get_session
from app.models.speaking_benchmark import SpeakingBenchmarkReview as Review
from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperiment as Experiment
from app.schemas.speaking_benchmark_research import (
    ExperimentCreate,
    ExperimentDTO,
    ExperimentStart,
    ExperimentSummary,
    ReconcileRequest,
    ReferenceDTO,
    ReferenceVerify,
    ReferenceWrite,
)
from app.services import speaking_benchmark_references as references
from app.services import speaking_benchmark_research as research
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_benchmark_research_reports import research_export, research_report

router = APIRouter(
    prefix="/admin/speaking-benchmark",
    tags=["admin-speaking-research"],
    dependencies=[Depends(mutation_origin)],
)


@router.get("/samples/{sample_id}/asr-references", response_model=list[ReferenceDTO])
async def history(
    sample_id: UUID,
    actor: AdminUser,
    review_revision: int = Query(ge=1),
    segment_id: str | None = Query(None, max_length=100),
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await references.reference_history(
        SpeakingBenchmarkService(session, actor.id),
        sample_id,
        review_revision,
        segment_id=segment_id,
        offset=offset,
        limit=limit,
    )


@router.post("/samples/{sample_id}/asr-references", response_model=ReferenceDTO, status_code=201)
async def write_reference(
    sample_id: UUID,
    body: ReferenceWrite,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await references.write_reference(
        SpeakingBenchmarkService(session, actor.id), sample_id, body
    )


@router.post(
    "/samples/{sample_id}/asr-references/{reference_id}/verify", response_model=ReferenceDTO
)
async def verify_reference(
    sample_id: UUID,
    reference_id: UUID,
    body: ReferenceVerify,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await references.verify_reference(
        SpeakingBenchmarkService(session, actor.id), sample_id, reference_id, body
    )


@router.get("/research/cohort")
async def cohort(
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=50),
    split: str | None = Query(None, pattern="^(DEV|HOLDOUT)$"),
    sample_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        query = (
            select(Review, Sample)
            .join(Sample)
            .where(
                Sample.owner_id == actor.id,
                Sample.deletion_pending_at.is_(None),
                Review.approved_at.is_not(None),
            )
        )
        if split:
            query = query.where(Sample.split == split)
        if sample_id:
            await SpeakingBenchmarkService(session, actor.id).owned(sample_id)
            query = query.where(Sample.id == sample_id)
        rows = await session.execute(
            query.order_by(Sample.created_at.desc(), Sample.id, Review.revision.desc())
            .offset(offset)
            .limit(limit)
        )
        return [
            {
                "sample_id": str(s.id),
                "code": s.code,
                "candidate_id": s.candidate_id,
                "split": s.split,
                "source_sha256": s.source_sha256,
                "review_revision": r.revision,
                "manifest_fingerprint": r.fingerprint,
                "windows": [
                    {k: w[k] for k in ("id", "start_ms", "end_ms", "part_number")}
                    for w in r.manifest["segments"]
                ],
            }
            for r, s in rows
        ]


@router.post("/research/experiments", response_model=ExperimentDTO, status_code=201)
async def create(
    body: ExperimentCreate, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await research.create_experiment(SpeakingBenchmarkService(session, actor.id), body)


@router.get("/research/experiments", response_model=list[ExperimentSummary])
async def experiments(
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        rows = await session.scalars(
            select(Experiment)
            .where(Experiment.owner_id == actor.id)
            .order_by(Experiment.created_at.desc(), Experiment.id)
            .offset(offset)
            .limit(limit)
        )
        return [
            ExperimentSummary(
                id=r.id,
                name=r.name,
                mode=r.mode,
                status=r.status,
                created_at=r.created_at,
                sample_count=len(r.configuration["cohort"]),
                providers=[v["key"] for v in r.configuration["variants"]],
            )
            for r in rows
        ]


@router.get("/research/experiments/{experiment_id}", response_model=ExperimentDTO)
async def detail(
    experiment_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    service = SpeakingBenchmarkService(session, actor.id)
    async with session.begin():
        return await research.dto(session, await research.owned_experiment(service, experiment_id))


@router.post("/research/experiments/{experiment_id}/preflight")
async def preflight(
    experiment_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await research.experiment_preflight(
        SpeakingBenchmarkService(session, actor.id), experiment_id
    )


@router.post(
    "/research/experiments/{experiment_id}/start", response_model=ExperimentDTO, status_code=202
)
async def start(
    experiment_id: UUID,
    body: ExperimentStart,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await research.start_experiment(
        SpeakingBenchmarkService(session, actor.id), experiment_id, body
    )


@router.post("/research/experiments/{experiment_id}/cancel", response_model=ExperimentDTO)
async def cancel(
    experiment_id: UUID, actor: AdminUser, session: AsyncSession = Depends(get_session)
):
    return await research.cancel_experiment(
        SpeakingBenchmarkService(session, actor.id), experiment_id
    )


@router.post("/research/experiments/{experiment_id}/reconcile", response_model=ExperimentDTO)
async def reconcile(
    experiment_id: UUID,
    body: ReconcileRequest,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await research.reconcile_experiment(
        SpeakingBenchmarkService(session, actor.id), experiment_id, body
    )


@router.post("/research/experiments/{experiment_id}/resume-paired", response_model=ExperimentDTO)
async def resume(
    experiment_id: UUID,
    body: ExperimentStart,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await research.resume_paired(
        SpeakingBenchmarkService(session, actor.id), experiment_id, body
    )


def report_filters(
    latest_references: bool = False,
    split: str | None = Query(None, pattern="^(DEV|HOLDOUT)$"),
    part: int | None = Query(None, ge=1, le=3),
    provider_key: str | None = Query(None, max_length=80),
    min_duration_ms: int | None = Query(None, ge=0),
    max_duration_ms: int | None = Query(None, ge=1),
    accent: str | None = Query(None, max_length=100),
    speaking_speed: str | None = Query(None, pattern="^(slow|typical|fast)$"),
    response_length: str | None = Query(None, pattern="^(short|long)$"),
    human_overall: float | None = Query(None, ge=0, le=9),
    sample_id: UUID | None = None,
    segment_id: str | None = Query(None, max_length=100),
    human_label_kind: Literal["LEGACY", "INDEPENDENT", "ADJUDICATED"] | None = None,
    human_label_id: UUID | None = None,
    human_label_revision: int | None = Query(None, ge=1),
):
    return dict(
        latest_references=latest_references,
        label_selection=dict(
            kind=human_label_kind, id=human_label_id, revision=human_label_revision
        )
        if human_label_kind
        else None,
        split=split,
        part=part,
        provider_key=provider_key,
        min_duration_ms=min_duration_ms,
        max_duration_ms=max_duration_ms,
        accent=accent,
        speaking_speed=speaking_speed,
        response_length=response_length,
        human_overall=human_overall,
        sample_id_filter=sample_id,
        segment_id=segment_id,
    )


@router.get("/research/experiments/{experiment_id}/results")
async def results(
    experiment_id: UUID,
    actor: AdminUser,
    filters: dict = Depends(report_filters),
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    report = await research_report(
        SpeakingBenchmarkService(session, actor.id),
        experiment_id,
        **filters,
    )
    total = len(report["rows"])
    report["rows"] = report["rows"][offset : offset + limit]
    return report | {"total": total, "offset": offset, "limit": limit}


@router.get("/research/experiments/{experiment_id}/export.{format}")
async def export(
    experiment_id: UUID,
    format: str,
    actor: AdminUser,
    filters: dict = Depends(report_filters),
    session: AsyncSession = Depends(get_session),
):
    from app.services.speaking_benchmark import failure

    if format not in {"csv", "json"}:
        raise failure("SPEAKING_RESEARCH_EXPORT_FORMAT")
    report = await research_report(
        SpeakingBenchmarkService(session, actor.id),
        experiment_id,
        **filters,
    )
    return Response(
        research_export(report, format),
        media_type="text/csv; charset=utf-8" if format == "csv" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="speaking-research-{experiment_id}.{format}"',
            "Cache-Control": "private, no-store",
        },
    )
