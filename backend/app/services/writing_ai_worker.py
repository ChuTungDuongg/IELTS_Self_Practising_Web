import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.scoring.mts_prompts import effective_prompt_version
from app.models.enums import WritingAIRunStatus
from app.providers.writing_llm import create_provider, provider_identity
from app.providers.writing_llm.base import LLMProvider, ProviderFailure
from app.repositories.writing_ai import ACTIVE, WritingAIRepository
from app.schemas.writing_ai import EventPayload, EventType, OutputDiagnostic
from app.services.mts_writing import MTSWritingScoringService
from app.services.writing_ai import WritingAIService, fail_run, input_fingerprint, persist_activity

_tasks: set[asyncio.Task] = set()


class RunStopped(Exception):
    pass


class WritingAIWorker:
    """Detached from HTTP/SSE; every checkpoint owns a short-lived DB session."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        provider: LLMProvider | None = None,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.provider = provider

    def launch(self, run_id: UUID) -> None:
        task = asyncio.create_task(self.execute(run_id), name=f"writing-ai-{run_id}")
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)

    async def execute(self, run_id: UUID) -> None:
        heartbeat = None
        mts = None
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
                    effective_prompt_version(self.settings.ai_writing_prompt_version),
                    provider,
                    model,
                )
                if fingerprint != run.input_fingerprint:
                    raise AppError(
                        "AI_CONFIGURATION_CHANGED", "AI configuration changed. Please regrade.", 409
                    )
                run.status = WritingAIRunStatus.RUNNING
                run.started_at = run.updated_at = datetime.now(UTC)
                persist_activity(run, "run.started", EventPayload())
                await repository.append_event(run, "run.started", EventPayload())
            provider_client = self.provider or create_provider(self.settings)
            mts = MTSWritingScoringService(provider_client)
            heartbeat = asyncio.create_task(self._heartbeat(run_id))
            await self._checkpoint(run_id, "provider.starting", EventPayload())
            await provider_client.ensure_ready()
            await self._checkpoint(run_id, "provider.ready", EventPayload())

            async def trace(event_type: EventType, payload: EventPayload) -> None:
                await self._checkpoint(run_id, event_type, payload, mts.usage, mts.diagnostics)

            result = await mts.assess(request, trace)
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
                }
                run.status = WritingAIRunStatus.COMPLETED
                run.completed_at = run.updated_at = datetime.now(UTC)
                persist_activity(run, "run.completed", EventPayload())
                await repository.append_event(run, "run.completed", EventPayload())
        except RunStopped:
            pass
        except asyncio.CancelledError:
            await self._fail(
                run_id, "RUN_INTERRUPTED", "AI grading was interrupted. Please regrade.", mts
            )
            raise
        except ProviderFailure as exc:
            await self._fail(run_id, exc.code, exc.message, mts)
        except AppError as exc:
            await self._fail(run_id, exc.code, exc.message, mts)
        except Exception:
            # Exception bodies can contain credentials/prompts. Never serialize/log them.
            await self._fail(
                run_id, "AI_GRADING_FAILED", "AI grading could not finish. Please regrade.", mts
            )
        finally:
            if heartbeat:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await heartbeat

    async def _checkpoint(
        self,
        run_id: UUID,
        event_type: EventType,
        payload: EventPayload,
        usage: list[dict[str, int]] | None = None,
        diagnostics: list[OutputDiagnostic] | None = None,
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
            persist_activity(run, event_type, payload)
            if payload.result and payload.criterion:
                run.result_json = {
                    "criteria": {
                        **(run.result_json or {}).get("criteria", {}),
                        payload.criterion: payload.result.model_dump(mode="json"),
                    }
                }
            await repository.append_event(run, event_type, payload)

    async def _heartbeat(self, run_id: UUID) -> None:
        while True:
            await asyncio.sleep(15)
            await self._checkpoint(run_id, "heartbeat", EventPayload())

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
                        }
                    await fail_run(
                        repository,
                        run,
                        code,
                        message,
                        criterion=mts.current_criterion if mts else None,
                        stage=mts.current_stage if mts else None,
                    )
        except Exception:
            pass


async def stop_writing_ai_workers() -> None:
    tasks = list(_tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
