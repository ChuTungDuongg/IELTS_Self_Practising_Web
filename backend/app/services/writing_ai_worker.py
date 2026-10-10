import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.scoring.mts_prompts import effective_prompt_version
from app.domains.writing.visual_families import VisualFamily, visual_family
from app.models.enums import WritingAIRunStatus
from app.providers.chart_derendering import ChartDerenderingProvider
from app.providers.chart_derendering.deplot import DePlotChartDerenderingProvider
from app.providers.writing_llm import create_provider, provider_identity
from app.providers.writing_llm.base import LLMProvider, ProviderFailure
from app.repositories.writing_ai import ACTIVE, WritingAIRepository
from app.schemas.writing_ai import (
    TRAITS,
    CriterionFailure,
    EventPayload,
    EventType,
    OutputDiagnostic,
)
from app.services.mts_writing import MTSWritingScoringService
from app.services.task1_input import TASK1_PROMPT_VERSION, Task1ScoringRequest
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_ai import WritingAIService, fail_run, input_fingerprint, persist_activity
from app.services.writing_execution import TraceFailure, WritingLatencyMetrics, durable_checkpoint

_tasks: dict[UUID, asyncio.Task] = {}
logger = logging.getLogger(__name__)


class RunStopped(TraceFailure):
    pass


class WritingAIWorker:
    """Detached from HTTP/SSE; every checkpoint owns a short-lived DB session."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        provider: LLMProvider | None = None,
        chart_derenderer: ChartDerenderingProvider | None = None,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.provider = provider
        self.chart_derenderer = chart_derenderer

    def launch(self, run_id: UUID) -> None:
        if run_id in _tasks and not _tasks[run_id].done():
            return
        task = asyncio.create_task(self.execute(run_id), name=f"writing-ai-{run_id}")
        _tasks[run_id] = task

        def discard(done: asyncio.Task) -> None:
            if _tasks.get(run_id) is done:
                _tasks.pop(run_id)

        task.add_done_callback(discard)

    def cancel(self, run_id: UUID) -> None:
        task = _tasks.get(run_id)
        if task and not task.done():
            logger.info("AI grading worker cancellation: source=explicit_user")
            task.cancel()

    async def execute(self, run_id: UUID) -> None:
        heartbeat = None
        mts = None
        latency = WritingLatencyMetrics()
        checkpoint_lock = asyncio.Lock()

        async def checkpoint(event_type, payload):
            # Short DB checkpoints are serial per run. Provider work never holds this lock.
            async with checkpoint_lock:
                await durable_checkpoint(
                    self._checkpoint(
                        run_id,
                        event_type,
                        payload,
                        mts.usage,
                        mts.diagnostics,
                        mts.latency_summary(),
                    )
                )

        async def fail(code, message):
            latency.finish()
            async with checkpoint_lock:
                await durable_checkpoint(self._fail(run_id, code, message, mts))

        try:
            async with self.sessions() as session, session.begin():
                repository = WritingAIRepository(session)
                run = await repository.run(run_id, lock=True)
                if run is None or run.status != WritingAIRunStatus.PENDING:
                    return
                request = await WritingAIService(
                    session, run.requested_by_user_id, self.settings
                ).input(run.attempt_id, run.writing_task_id)
                provider, model = provider_identity(self.settings)
                fingerprint = input_fingerprint(
                    request,
                    TASK1_PROMPT_VERSION
                    if isinstance(request, Task1ScoringRequest)
                    else effective_prompt_version(self.settings.ai_writing_prompt_version),
                    provider,
                    model,
                )
                if fingerprint != run.input_fingerprint:
                    raise AppError(
                        "AI_CONFIGURATION_CHANGED",
                        "Cấu hình AI đã thay đổi. Bạn có thể thử chấm lại.",
                        409,
                    )
                run.status = WritingAIRunStatus.RUNNING
                run.started_at = run.updated_at = datetime.now(UTC)
                persist_activity(run, "run.started", EventPayload())
                await repository.append_event(run, "run.started", EventPayload())
            provider_client = self.provider or create_provider(self.settings)
            mts = (
                Task1WritingScoringService(
                    provider_client,
                    (self.chart_derenderer or DePlotChartDerenderingProvider(self.settings))
                    if request.chart_specialist.enabled
                    and visual_family(request.task_type) == VisualFamily.CHART_TABLE
                    else None,
                    self.settings.ai_writing_chart_specialist_timeout_seconds,
                    max_concurrent_requests=self.settings.ai_writing_max_concurrent_llm_requests,
                    latency=latency,
                )
                if isinstance(request, Task1ScoringRequest)
                else MTSWritingScoringService(
                    provider_client,
                    max_concurrent_requests=self.settings.ai_writing_max_concurrent_llm_requests,
                    latency=latency,
                )
            )
            heartbeat = asyncio.create_task(self._heartbeat(checkpoint))
            await checkpoint("provider.starting", EventPayload())
            with latency.stage("provider_ready"):
                await provider_client.ensure_ready()
            await checkpoint("provider.ready", EventPayload())

            async def trace(event_type: EventType, payload: EventPayload) -> None:
                await checkpoint(event_type, payload)

            result = await mts.assess(request, trace)
            if result is None:
                # All traits have now been attempted. Each successful checkpoint
                # stays available; no partial mean/overall is ever calculated.
                failure = next(iter(mts.failures.values()))
                await fail(
                    failure.error_code,
                    "Một số tiêu chí chưa thể chấm xong. Các kết quả đã hoàn tất được giữ lại; bạn có thể thử chấm lại.",
                )
                return
            latency.finish()
            async with checkpoint_lock:
                await durable_checkpoint(self._complete(run_id, result, mts))
        except RunStopped:
            logger.info("AI grading worker stopped: source=terminal_state")
        except asyncio.CancelledError:
            # _fail holds the row lock and only updates ACTIVE runs. A committed
            # user cancellation always wins over this shutdown/interruption path.
            await fail("RUN_INTERRUPTED", "Chấm AI bị gián đoạn. Bạn có thể thử chấm lại.")
            raise
        except ProviderFailure as exc:
            await fail(exc.code, exc.message)
        except AppError as exc:
            await fail(exc.code, exc.message)
        except Exception:
            # Exception bodies can contain credentials/prompts. Never serialize/log them.
            await fail(
                "AI_GRADING_FAILED",
                "AI chưa thể hoàn tất bài chấm. Bạn có thể thử chấm lại.",
            )
        finally:
            latency.finish()
            if heartbeat:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await heartbeat

    async def _complete(self, run_id, result, mts):
        async with self.sessions() as session, session.begin():
            repository = WritingAIRepository(session)
            run = await repository.run(run_id, lock=True)
            if run is None or run.status not in ACTIVE:
                return
            run.result_json = result.model_dump(mode="json")
            run.raw_mean = result.raw_mean
            run.overall_band = result.overall_band
            run.usage_json = {
                "calls": mts.usage,
                "diagnostics": [item.model_dump() for item in mts.diagnostics],
                "latency": mts.latency_summary(),
            }
            run.status = WritingAIRunStatus.COMPLETED
            run.completed_at = run.updated_at = datetime.now(UTC)
            persist_activity(run, "run.completed", EventPayload())
            await repository.append_event(run, "run.completed", EventPayload())

    async def _checkpoint(
        self,
        run_id: UUID,
        event_type: EventType,
        payload: EventPayload,
        usage: list[dict[str, int]] | None = None,
        diagnostics: list[OutputDiagnostic] | None = None,
        latency: dict | None = None,
    ) -> None:
        async with self.sessions() as session, session.begin():
            repository = WritingAIRepository(session)
            run = await repository.run(run_id, lock=True)
            if run is None or run.status not in ACTIVE:
                raise RunStopped
            run.updated_at = datetime.now(UTC)
            if usage is not None:
                run.usage_json = {**(run.usage_json or {}), "calls": list(usage)}
            if diagnostics is not None:
                run.usage_json = {
                    **(run.usage_json or {}),
                    "diagnostics": [item.model_dump() for item in diagnostics],
                }
            if latency is not None:
                run.usage_json = {**(run.usage_json or {}), "latency": latency}
            persist_activity(run, event_type, payload)
            if payload.task1_analysis:
                run.result_json = {
                    **(run.result_json or {}),
                    "task_number": 1,
                    "task1_analysis": payload.task1_analysis.model_dump(mode="json"),
                }
            if payload.result and payload.criterion:
                run.result_json = {
                    **(run.result_json or {}),
                    "criteria": {
                        **(run.result_json or {}).get("criteria", {}),
                        payload.criterion: payload.result.model_dump(mode="json"),
                    },
                }
            if event_type == "criterion.failed" and payload.criterion:
                run.result_json = {
                    **(run.result_json or {}),
                    "failures": {
                        **(run.result_json or {}).get("failures", {}),
                        payload.criterion: {
                            "error_code": payload.error_code,
                            "error_message": payload.error_message,
                            "stage": payload.stage,
                        },
                    },
                }
            if run.result_json:
                for key in ("criteria", "failures"):
                    if key in run.result_json:
                        values = run.result_json[key]
                        run.result_json = {
                            **run.result_json,
                            key: {trait: values[trait] for trait in TRAITS if trait in values},
                        }
            await repository.append_event(run, event_type, payload)

    async def _heartbeat(self, checkpoint) -> None:
        while True:
            await asyncio.sleep(15)
            await checkpoint("heartbeat", EventPayload())

    async def _fail(
        self, run_id: UUID, code: str, message: str, mts: MTSWritingScoringService | None
    ) -> None:
        # A database outage is recovered by the persisted lease on the next read.
        try:
            async with self.sessions() as session, session.begin():
                repository = WritingAIRepository(session)
                run = await repository.run(run_id, lock=True)
                if run:
                    if mts and run.status in ACTIVE:
                        run.usage_json = {
                            **(run.usage_json or {}),
                            "calls": mts.usage,
                            "diagnostics": [item.model_dump() for item in mts.diagnostics],
                            "latency": mts.latency_summary(),
                        }
                        if code == "RUN_INTERRUPTED":
                            stored = run.result_json or {}
                            failures = dict(stored.get("failures", {}))
                            for trait in TRAITS:
                                if (
                                    trait not in stored.get("criteria", {})
                                    and trait not in failures
                                ):
                                    failure = CriterionFailure(
                                        error_code=code,
                                        error_message="Không thể hoàn tất tiêu chí này.",
                                        stage=mts.states[trait].stage,
                                    )
                                    failures[trait] = failure.model_dump(mode="json")
                                    await repository.append_event(
                                        run,
                                        "criterion.failed",
                                        EventPayload(criterion=trait, **failure.model_dump()),
                                    )
                            run.result_json = {
                                **stored,
                                "failures": {
                                    trait: failures[trait] for trait in TRAITS if trait in failures
                                },
                            }
                    await fail_run(
                        repository,
                        run,
                        code,
                        message,
                        criterion=mts.failure_context[0] if mts else None,
                        stage=mts.failure_context[1] if mts else None,
                    )
        except Exception:
            pass


async def stop_writing_ai_workers() -> None:
    tasks = list(_tasks.values())
    if tasks:
        logger.info("AI grading worker cancellation: source=shutdown")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
