"""Optional, bounded second perception pass before deterministic facts."""

import asyncio

from app.domains.scoring.chart_reconciliation import reconcile_chart
from app.domains.scoring.deplot_parser import DePlotParseError
from app.domains.writing.visual_families import VisualFamily, visual_family
from app.providers.chart_derendering import ChartDerenderingProvider, ChartSpecialistFailure
from app.schemas.chart_cross_check import ChartCrossCheckResult
from app.schemas.task1_claims import Task1Analysis
from app.schemas.task1_visual import ChartTableVisualReference
from app.schemas.writing_ai import EventPayload
from app.services.mts_writing import TraceCallback
from app.services.task1_input import Task1ScoringRequest


async def cross_check_chart(
    request: Task1ScoringRequest,
    analysis: Task1Analysis,
    provider: ChartDerenderingProvider | None,
    trace: TraceCallback,
    budget_seconds: float,
) -> None:
    if (
        not request.chart_specialist.enabled
        or visual_family(request.task_type) != VisualFamily.CHART_TABLE
        or not isinstance(analysis.reference, ChartTableVisualReference)
        or analysis.confidence == "UNUSABLE"
    ):
        return
    identity = request.chart_specialist
    await trace("chart_specialist.started", EventPayload(criterion="ta", stage="chart_cross_check"))
    try:
        if provider is None or request.image is None:
            raise ChartSpecialistFailure()
        try:
            async with asyncio.timeout(budget_seconds):
                observation = await provider.extract(request.image)
        except (ChartSpecialistFailure, DePlotParseError):
            raise
        except Exception:
            # Provider exceptions can contain payloads/secrets; retain only a
            # safe fallback code. Cancellation still propagates (BaseException).
            raise ChartSpecialistFailure() from None
        await trace(
            "chart_specialist.completed", EventPayload(criterion="ta", stage="chart_cross_check")
        )
        analysis.reference, analysis.cross_check = reconcile_chart(
            analysis.reference, observation, identity
        )
        analysis.confidence = analysis.reference.confidence
        analysis.warnings.extend(analysis.cross_check.warnings)
        await trace(
            "chart_reconciliation.completed",
            EventPayload(criterion="ta", stage="chart_cross_check", task1_analysis=analysis),
        )
    except (ChartSpecialistFailure, DePlotParseError, TimeoutError) as exc:
        code = (
            "CHART_SPECIALIST_PARSE_FAILED"
            if isinstance(exc, DePlotParseError)
            or getattr(exc, "code", None) == "CHART_SPECIALIST_PARSE_FAILED"
            else "CHART_SPECIALIST_UNAVAILABLE"
        )
        analysis.cross_check = ChartCrossCheckResult(
            specialist_used=False,
            specialist_model=identity.model,
            specialist_revision=identity.revision,
            status="PARSE_FAILED" if code == "CHART_SPECIALIST_PARSE_FAILED" else "UNAVAILABLE",
            warnings=[code],
        )
        analysis.warnings.append(code)
        await trace(
            "chart_specialist.failed",
            EventPayload(
                criterion="ta", stage="chart_cross_check", task1_analysis=analysis, error_code=code
            ),
        )
