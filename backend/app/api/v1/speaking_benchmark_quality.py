"""Owner-scoped dataset quality, evaluation suites, regression gates and release reports."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.api.v1.speaking_benchmark import mutation_origin
from app.core.database import get_session
from app.models.speaking_benchmark_quality import (
    SpeakingBenchmarkEvaluationSuite as Suite,
)
from app.models.speaking_benchmark_quality import (
    SpeakingBenchmarkQualitySnapshot as Snapshot,
)
from app.schemas.speaking_benchmark_quality import (
    GateCreate,
    GateDTO,
    GateEvaluate,
    QualityReport,
    QualityRequest,
    RegressionReportDTO,
    SuiteCreate,
    SuiteDTO,
)
from app.services import speaking_benchmark_quality as quality
from app.services.speaking_benchmark import SpeakingBenchmarkService

router = APIRouter(
    prefix="/admin/speaking-benchmark",
    tags=["admin-speaking-quality"],
    dependencies=[Depends(mutation_origin)],
)


@router.post("/quality", response_model=QualityReport)
async def evaluate_quality(
    body: QualityRequest,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await quality.quality_report(SpeakingBenchmarkService(session, actor.id), body)


@router.post("/quality/snapshots", status_code=201)
async def create_snapshot(
    body: QualityRequest,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await quality.create_snapshot(SpeakingBenchmarkService(session, actor.id), body)


@router.get("/quality/snapshots")
async def list_snapshots(
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await quality.list_artifacts(
        SpeakingBenchmarkService(session, actor.id), Snapshot, offset, limit
    )


@router.get("/quality/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id: UUID,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    service = SpeakingBenchmarkService(session, actor.id)
    async with session.begin():
        row = await quality.owned_artifact(service, Snapshot, snapshot_id)
        return quality.snapshot_dto(row)


@router.get("/evaluation-suites")
async def list_suites(
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await quality.list_artifacts(
        SpeakingBenchmarkService(session, actor.id), Suite, offset, limit
    )


@router.post("/evaluation-suites", response_model=SuiteDTO, status_code=201)
async def create_suite(
    body: SuiteCreate,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await quality.create_suite(SpeakingBenchmarkService(session, actor.id), body)


@router.get("/evaluation-suites/{suite_id}", response_model=SuiteDTO)
async def get_suite(
    suite_id: UUID,
    actor: AdminUser,
    holdout_evaluation: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    return await quality.get_suite(
        SpeakingBenchmarkService(session, actor.id), suite_id, holdout_evaluation
    )


@router.get("/evaluation-suites/{suite_id}/audits")
async def suite_audits(
    suite_id: UUID,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await quality.suite_audits(SpeakingBenchmarkService(session, actor.id), suite_id)


@router.get("/regression-gates", response_model=list[GateDTO])
async def list_gates(
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await quality.list_gates(SpeakingBenchmarkService(session, actor.id), offset, limit)


@router.post("/regression-gates", response_model=GateDTO, status_code=201)
async def create_gate(
    body: GateCreate,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await quality.create_gate(SpeakingBenchmarkService(session, actor.id), body)


@router.get("/regression-gates/{gate_id}", response_model=GateDTO)
async def get_gate(
    gate_id: UUID,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await quality.get_gate(SpeakingBenchmarkService(session, actor.id), gate_id)


@router.post(
    "/regression-gates/{gate_id}/evaluate",
    response_model=RegressionReportDTO,
    status_code=201,
)
async def evaluate_gate(
    gate_id: UUID,
    body: GateEvaluate,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    return await quality.evaluate_gate(SpeakingBenchmarkService(session, actor.id), gate_id, body)


@router.get(
    "/regression-gates/{gate_id}/reports",
    response_model=list[RegressionReportDTO],
)
async def list_reports(
    gate_id: UUID,
    actor: AdminUser,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await quality.list_gate_reports(
        SpeakingBenchmarkService(session, actor.id), gate_id, offset, limit
    )


@router.get("/regression-reports/{report_id}", response_model=RegressionReportDTO)
async def get_report(
    report_id: UUID,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    dto, _ = await quality.get_report(SpeakingBenchmarkService(session, actor.id), report_id)
    return dto


@router.get("/regression-reports/{report_id}/export.csv")
async def export_csv(
    report_id: UUID,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    _, report_data = await quality.get_report(
        SpeakingBenchmarkService(session, actor.id), report_id
    )
    csv_content = quality.export_report_csv(report_data)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="regression-report-{report_id}.csv"'
        },
    )


@router.get("/regression-reports/{report_id}/export.json")
async def export_json(
    report_id: UUID,
    actor: AdminUser,
    session: AsyncSession = Depends(get_session),
):
    dto, _ = await quality.get_report(SpeakingBenchmarkService(session, actor.id), report_id)
    return JSONResponse(content=dto.model_dump(mode="json"))
