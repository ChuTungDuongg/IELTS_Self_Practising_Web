from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.scoring.mts_prompts import effective_prompt_version
from app.domains.scoring.writing import WritingScoringRequest
from app.models import TestSession, WritingAIGradingRun
from app.models.enums import AttemptStatus, ModuleType, TestSessionStatus, WritingAIRunStatus
from app.providers.writing_llm import create_provider, is_configured, provider_identity
from app.repositories.writing_ai import ACTIVE, WritingAIRepository
from app.schemas.writing_ai import (
    AIWritingResult,
    AssessmentStage,
    CreateRunResponse,
    CriterionFailure,
    CriterionResult,
    EventPayload,
    EventResponse,
    EventType,
    RunActivity,
    RunListResponse,
    RunResponse,
    Trait,
)


def persist_activity(run: WritingAIGradingRun, event: EventType, payload: EventPayload) -> None:
    phases = {
        "run.started": "preparing",
        "provider.starting": "starting_model",
        "provider.ready": "preparing",
        "criterion.started": "preparing",
        "evidence.request.started": "collecting_evidence",
        "evidence.validation.started": "validating_evidence",
        "criterion.evidence.completed": "evidence_collected",
        "criterion.scoring.started": "scoring",
        "criterion.scoring.validation.started": "validating_score",
        "criterion.retrying": "retrying",
        "criterion.completed": "completed",
        "criterion.failed": "failed",
        "run.completed": "completed",
        "run.failed": "failed",
    }
    if event in phases:
        activity = RunActivity(
            phase=phases[event],
            criterion=payload.criterion,
            stage=payload.stage,
            started_at=run.updated_at,
        )
        run.usage_json = {**(run.usage_json or {}), "activity": activity.model_dump(mode="json")}


def input_fingerprint(
    request: WritingScoringRequest, prompt_version: str, provider: str, model: str
) -> str:
    canonical = json.dumps(
        {
            "prompt": request.prompt,
            "essay": request.response,
            "prompt_version": prompt_version,
            "provider": provider,
            "model": model,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def present_run(run: WritingAIGradingRun) -> RunResponse:
    stored = run.result_json or {}
    return RunResponse(
        id=run.id,
        attempt_id=run.attempt_id,
        writing_task_id=run.writing_task_id,
        status=run.status,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        result=AIWritingResult.model_validate(stored)
        if run.status == WritingAIRunStatus.COMPLETED
        else None,
        progress={
            key: CriterionResult.model_validate(value)
            for key, value in stored.get("criteria", {}).items()
        },
        failures={
            key: CriterionFailure.model_validate(value)
            for key, value in stored.get("failures", {}).items()
        },
        error_code=run.error_code,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        activity=RunActivity.model_validate(run.usage_json["activity"])
        if run.usage_json and run.usage_json.get("activity")
        else None,
    )


async def fail_run(
    repository: WritingAIRepository,
    run: WritingAIGradingRun,
    code: str,
    message: str,
    *,
    criterion: Trait | None = None,
    stage: AssessmentStage | None = None,
) -> None:
    if run.status not in ACTIVE:
        return
    run.status = WritingAIRunStatus.FAILED
    run.error_code = code
    run.error_message = message
    run.completed_at = run.updated_at = datetime.now(UTC)
    previous = (run.usage_json or {}).get("activity", {})
    payload = EventPayload(
        error_code=code,
        error_message=message,
        criterion=criterion or previous.get("criterion"),
        stage=stage or previous.get("stage"),
    )
    stored = run.result_json or {}
    if (
        payload.criterion
        and payload.criterion not in stored.get("criteria", {})
        and payload.criterion not in stored.get("failures", {})
    ):
        # Shutdown/stale recovery can interrupt a later criterion after an
        # earlier local failure. Preserve both; never mark a completed one failed.
        failure = CriterionFailure(
            error_code=code, error_message="Không thể hoàn tất tiêu chí này.", stage=payload.stage
        )
        run.result_json = {
            **stored,
            "failures": {
                **stored.get("failures", {}),
                payload.criterion: failure.model_dump(mode="json"),
            },
        }
        await repository.append_event(
            run,
            "criterion.failed",
            EventPayload(criterion=payload.criterion, **failure.model_dump()),
        )
    persist_activity(run, "run.failed", payload)
    await repository.append_event(run, "run.failed", payload)


class WritingAIService:
    def __init__(self, session: AsyncSession, user_id: UUID, settings: Settings) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.repository = WritingAIRepository(session)

    async def input(
        self, attempt_id: UUID, task_id: UUID, *, lock: bool = False, require_essay: bool = True
    ) -> WritingScoringRequest:
        attempt = await self.repository.attempt(attempt_id, self.user_id, lock=lock)
        if attempt is None:
            raise AppError("ATTEMPT_NOT_FOUND", "Không tìm thấy lượt làm bài này.", 404)
        if attempt.module_type != ModuleType.WRITING:
            raise AppError(
                "WRITING_ATTEMPT_REQUIRED", "Chấm AI yêu cầu một lượt làm bài Writing.", 422
            )
        if (
            attempt.status in {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}
            or attempt.finished_at is None
        ):
            raise AppError(
                "ATTEMPT_NOT_FINALIZED", "Hãy hoàn tất lượt làm bài trước khi chấm AI.", 409
            )
        if attempt.test_session_id:
            mock = await self.session.get(TestSession, attempt.test_session_id)
            if mock and mock.status == TestSessionStatus.IN_PROGRESS:
                raise AppError(
                    "FULL_MOCK_REVIEW_LOCKED",
                    "Hãy hoàn tất bài thi Full Mock trước khi chấm AI.",
                    409,
                )
        task = await self.repository.task(task_id, attempt.test_version_id)
        if task is None:
            raise AppError("INVALID_WRITING_TASK", "Bài Writing không thuộc lượt làm bài này.", 422)
        if task.task_number != 2:
            raise AppError("AI_TASK_TWO_ONLY", "Chấm AI chỉ hỗ trợ Writing Task 2.", 422)
        essay = await self.repository.essay(attempt_id, task_id)
        if require_essay and not essay.strip():
            raise AppError(
                "AI_EMPTY_ESSAY", "Hãy lưu câu trả lời Task 2 có nội dung trước khi chấm AI.", 422
            )
        # Never truncate a saved response silently to fit the GPU's context budget.
        if require_essay and (len(essay) > 12_000 or len(task.prompt) > 4000):
            raise AppError("AI_INPUT_TOO_LONG", "Câu trả lời hoặc đề bài quá dài để chấm AI.", 422)
        return WritingScoringRequest(
            attempt_id=attempt_id, writing_task_id=task_id, prompt=task.prompt, response=essay
        )

    async def recover_stale(self, run: WritingAIGradingRun) -> None:
        if run.status in ACTIVE and run.updated_at < datetime.now(UTC) - timedelta(
            seconds=self.settings.ai_writing_stale_after_seconds
        ):
            await fail_run(
                self.repository,
                run,
                "STALE_RUN",
                "Chấm AI bị gián đoạn. Bạn có thể thử chấm lại.",
            )

    async def create(self, attempt_id: UUID, task_id: UUID, *, force: bool) -> CreateRunResponse:
        async with self.session.begin():
            # PostgreSQL serializes duplicate clicks across API processes. This lock
            # never writes the attempt or its official scores.
            request = await self.input(attempt_id, task_id, lock=True)
            provider, model = provider_identity(self.settings)
            prompt_version = effective_prompt_version(self.settings.ai_writing_prompt_version)
            fingerprint = input_fingerprint(request, prompt_version, provider, model)
            for run in await self.repository.runs(attempt_id, task_id, lock=True, limit=None):
                await self.recover_stale(run)
            if not force:
                cached = await self.repository.equivalent(
                    attempt_id, task_id, fingerprint, (WritingAIRunStatus.COMPLETED,)
                )
                if cached:
                    return CreateRunResponse(
                        run_id=cached.id, cache_hit=True, existing_active=False
                    )
                active = await self.repository.equivalent(attempt_id, task_id, fingerprint, ACTIVE)
                if active:
                    return CreateRunResponse(
                        run_id=active.id, cache_hit=False, existing_active=True
                    )
            create_provider(self.settings)  # Fail before inserting an unserviceable run.
            run = WritingAIGradingRun(
                attempt_id=attempt_id,
                writing_task_id=task_id,
                requested_by_user_id=self.user_id,
                status=WritingAIRunStatus.PENDING,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                input_fingerprint=fingerprint,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            self.session.add(run)
            await self.session.flush()
            return CreateRunResponse(run_id=run.id, cache_hit=False, existing_active=False)

    async def list(self, attempt_id: UUID, task_id: UUID) -> RunListResponse:
        async with self.session.begin():
            await self.input(attempt_id, task_id, require_essay=False)
            runs = await self.repository.runs(attempt_id, task_id, lock=True)
            for run in runs:
                await self.recover_stale(run)
            return RunListResponse(
                configured=is_configured(self.settings), items=[present_run(run) for run in runs]
            )

    async def get(self, run_id: UUID) -> RunResponse:
        run, _ = await self.snapshot(run_id, after=0, include_events=False)
        return run

    async def snapshot(
        self, run_id: UUID, after: int, *, include_events: bool = True
    ) -> tuple[RunResponse, list[EventResponse]]:
        async with self.session.begin():
            run = await self.repository.run(run_id, user_id=self.user_id, lock=True)
            if run is None:
                raise AppError("AI_RUN_NOT_FOUND", "Không tìm thấy bài đánh giá AI này.", 404)
            await self.recover_stale(run)
            events = await self.repository.events(run_id, after) if include_events else []
            return present_run(run), [
                EventResponse(
                    sequence=event.sequence,
                    event_type=event.event_type,
                    payload=EventPayload.model_validate(event.payload),
                    created_at=event.created_at,
                )
                for event in events
            ]
