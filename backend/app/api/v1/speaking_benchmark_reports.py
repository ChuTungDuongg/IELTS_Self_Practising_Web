"""Read-only owner reports and private exports. No provider constructors."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.core.database import get_session
from app.schemas.speaking_benchmark_reports import ReportFilters
from app.services.speaking_benchmark import SpeakingBenchmarkService, failure
from app.services.speaking_benchmark_reports import (
    VERSION,
    comparison,
    csv_export,
    export_rows,
    report,
)

router = APIRouter(prefix="/admin/speaking-benchmark", tags=["admin-speaking-benchmark-reports"])


@router.get("/samples/{sample_id}/grading-runs/{run_id}/comparison")
async def compare(
    sample_id: UUID,
    run_id: UUID,
    actor: AdminUser,
    label_revision: int | None = Query(None, ge=1),
    session: AsyncSession = Depends(get_session),
):
    return await comparison(
        SpeakingBenchmarkService(session, actor.id), sample_id, run_id, label_revision
    )


@router.get("/reports/summary")
async def summary(
    actor: AdminUser,
    filters: Annotated[ReportFilters, Query()],
    session: AsyncSession = Depends(get_session),
):
    value, _ = await report(SpeakingBenchmarkService(session, actor.id), filters)
    return value


@router.get("/reports/samples")
async def samples(
    actor: AdminUser,
    filters: Annotated[ReportFilters, Query()],
    session: AsyncSession = Depends(get_session),
):
    summary, rows = await report(SpeakingBenchmarkService(session, actor.id), filters)
    offset, limit = filters.offset, filters.limit
    paired = [r for r in rows if r.get("differences", {}).get("overall") is not None]
    outliers = sorted(paired, key=lambda r: abs(r["differences"]["overall"]), reverse=True)[:10]
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "configuration": summary["configuration"],
        "chart_points": rows[:500],
        "chart_limit": 500,
        "chart_sampled": len(rows) > 500,
        "outliers": outliers,
    }


async def exporting(actor, filters, session):
    summary, rows = await report(SpeakingBenchmarkService(session, actor.id), filters)
    if summary["requires_configuration"]:
        raise failure("SPEAKING_BENCHMARK_REPORT_CONFIGURATION_REQUIRED", 409)
    return summary, rows


@router.get("/reports/export.csv")
async def export_csv(
    actor: AdminUser,
    filters: Annotated[ReportFilters, Query()],
    session: AsyncSession = Depends(get_session),
):
    _, rows = await exporting(actor, filters, session)
    return Response(
        csv_export(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="speaking-benchmark.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/reports/export.json")
async def export_json(
    actor: AdminUser,
    filters: Annotated[ReportFilters, Query()],
    session: AsyncSession = Depends(get_session),
):
    summary, rows = await exporting(actor, filters, session)
    return Response(
        json.dumps(
            {
                "schema_version": VERSION,
                "filters": filters.model_dump(mode="json"),
                "summary": summary,
                "samples": export_rows(rows),
            },
            ensure_ascii=False,
        ),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="speaking-benchmark.json"',
            "Cache-Control": "no-store",
        },
    )
