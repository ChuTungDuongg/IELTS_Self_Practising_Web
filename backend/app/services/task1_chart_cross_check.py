"""Optional, bounded second perception pass before deterministic facts."""

import asyncio
import logging
from typing import Literal

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

logger = logging.getLogger(__name__)


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
    except (ChartSpecialistFailure, DePlotParseError, TimeoutError) as exc:
        code = (
            "CHART_SPECIALIST_PARSE_FAILED"
            if isinstance(exc, DePlotParseError)
            or getattr(exc, "code", None) == "CHART_SPECIALIST_PARSE_FAILED"
            else "CHART_SPECIALIST_UNAVAILABLE"
        )
        await specialist_fallback(request, analysis, trace, code)
        return
    await trace(
        "chart_specialist.completed", EventPayload(criterion="ta", stage="chart_cross_check")
    )
    try:
        # A failed reconciliation must not mutate the primary perception result.
        reconciled, cross_check = reconcile_chart(
            analysis.reference.model_copy(deep=True), observation, identity
        )
    except Exception:
        # Only reconciliation is guarded here. Trace errors and cancellation
        # propagate, and exception messages/payloads never enter logs.
        await specialist_fallback(request, analysis, trace, "CHART_RECONCILIATION_FAILED")
        return
    analysis.reference, analysis.cross_check = reconciled, cross_check
    analysis.confidence = reconciled.confidence
    analysis.warnings.extend(cross_check.warnings)
    await trace(
        "chart_reconciliation.completed",
        EventPayload(criterion="ta", stage="chart_cross_check", task1_analysis=analysis),
    )


async def specialist_fallback(
    request: Task1ScoringRequest,
    analysis: Task1Analysis,
    trace: TraceCallback,
    code: Literal[
        "CHART_SPECIALIST_PARSE_FAILED",
        "CHART_SPECIALIST_UNAVAILABLE",
        "CHART_RECONCILIATION_FAILED",
    ],
) -> None:
    identity = request.chart_specialist
    logger.warning("Task1 specialist fallback: stage=chart_cross_check reason=%s", code)
    analysis.cross_check = ChartCrossCheckResult(
        specialist_used=False,
        specialist_model=identity.model,
        specialist_revision=identity.revision,
        status={
            "CHART_SPECIALIST_PARSE_FAILED": "PARSE_FAILED",
            "CHART_RECONCILIATION_FAILED": "RECONCILIATION_FAILED",
        }.get(code, "UNAVAILABLE"),
        warnings=[code],
    )
    analysis.warnings.append(code)
    await trace(
        "chart_specialist.failed",
        EventPayload(
            criterion="ta", stage="chart_cross_check", task1_analysis=analysis, error_code=code
        ),
    )
