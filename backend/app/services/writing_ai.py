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
from app.domains.writing.task_types import TASK_ONE_TYPES, WritingTaskType
from app.domains.writing.visual_families import VisualFamily, visual_family
from app.models import TestSession, WritingAIGradingRun
from app.models.enums import AttemptStatus, ModuleType, TestSessionStatus, WritingAIRunStatus
from app.providers.writing_llm import create_provider, is_configured, provider_identity
from app.repositories.writing_ai import ACTIVE, WritingAIRepository
from app.schemas.chart_cross_check import ChartSpecialistIdentity
from app.schemas.task1_claims import Task1Analysis
from app.schemas.writing_ai import (
    TRAITS,
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
    Task1WritingResult,
    Trait,
)
from app.schemas.writing_anchors import AnchorSnapshot
from app.services.task1_input import Task1ScoringRequest, load_task1_image
from app.services.task1_scorer import Task1ExecutionConfig
from app.services.writing_anchors import WritingAnchorService


def persist_activity(run: WritingAIGradingRun, event: EventType, payload: EventPayload) -> None:
    phases = {
        "anchor.search.started": "anchor_search",
        "anchor.node.started": "anchor_comparing",
        "anchor.forward.completed": "anchor_comparing",
        "anchor.reverse.completed": "anchor_comparing",
        "anchor.node.completed": "anchor_compared",
        "anchor.bracket.completed": "anchor_bracketed",
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
        "visual_grounding.started": "visual_grounding",
        "visual_grounding.completed": "visual_grounded",
        "visual_grounding.failed": "failed",
        "chart_specialist.started": "chart_cross_check",
        "chart_specialist.completed": "chart_read",
        "chart_specialist.failed": "chart_fallback",
        "chart_reconciliation.completed": "chart_reconciled",
        "derived_facts.completed": "deriving_facts",
        "derived_facts.failed": "derived_facts_failed",
        "claim_extraction.started": "extracting_claims",
        "claim_extraction.completed": "claims_extracted",
        "claim_extraction.failed": "claim_extraction_failed",
        "claim_verification.started": "verifying_claims",
        "claim_verification.completed": "claims_verified",
        "claim_verification.failed": "claim_verification_failed",
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
    request: WritingScoringRequest,
    prompt_version: str,
    provider: str,
    model: str,
    *,
    execution: Task1ExecutionConfig | None = None,
) -> str:
    inputs = {
        "prompt": request.prompt,
        "essay": request.response,
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
    }
    if isinstance(request, Task1ScoringRequest):
        if execution is not None:
            inputs["execution"] = execution.model_dump(mode="json")
            inputs["writing_task_id"] = str(request.writing_task_id)
        inputs.update(
            task_number=1,
            task_type=request.task_type.value,
            image_sha256=request.image_checksum,
            image_mime=request.image.mime_type if request.image else None,
        )
        if visual_family(request.task_type) == VisualFamily.CHART_TABLE:
            inputs["chart_specialist"] = request.chart_specialist.model_dump(mode="json")
    canonical = json.dumps(
        inputs,
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
        result=(
            Task1WritingResult if stored.get("task_number") == 1 else AIWritingResult
        ).model_validate(stored)
        if run.status == WritingAIRunStatus.COMPLETED
        else None,
        progress={
            trait: CriterionResult.model_validate(stored["criteria"][trait])
            for trait in TRAITS
            if trait in stored.get("criteria", {})
        },
        failures={
            trait: CriterionFailure.model_validate(stored["failures"][trait])
            for trait in TRAITS
            if trait in stored.get("failures", {})
        },
        error_code=run.error_code,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        activity=RunActivity.model_validate(run.usage_json["activity"])
        if run.usage_json and run.usage_json.get("activity")
        else None,
        task_number=1
        if stored.get("task_number") == 1 or run.prompt_version.startswith(("mts-task1-", "task1-"))
        else 2,
        task1_analysis=Task1Analysis.model_validate(stored["task1_analysis"])
        if stored.get("task1_analysis")
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
        if task.task_number not in {1, 2}:
            raise AppError("AI_INVALID_TASK", "Chấm AI hỗ trợ Writing Task 1 và Task 2.", 422)
        essay = await self.repository.essay(attempt_id, task_id)
        if require_essay and not essay.strip():
            raise AppError(
                "AI_EMPTY_ESSAY",
                f"Hãy lưu câu trả lời Task {task.task_number} có nội dung trước khi chấm AI.",
                422,
            )
        # Never truncate a saved response silently to fit the GPU's context budget.
        if require_essay and (len(essay) > 12_000 or len(task.prompt) > 4000):
            raise AppError("AI_INPUT_TOO_LONG", "Câu trả lời hoặc đề bài quá dài để chấm AI.", 422)
        if task.task_number == 1:
            try:
                task_type = (
                    WritingTaskType(task.task_type)
                    if task.task_type
                    else WritingTaskType.OTHER_VISUAL
                )
                if task_type not in TASK_ONE_TYPES:
                    raise ValueError
            except ValueError:
                raise AppError(
                    "AI_INVALID_TASK_TYPE", "Loại đề Task 1 không hợp lệ.", 422
                ) from None
            image = (
                await load_task1_image(self.session, task, attempt.test_version_id, self.settings)
                if require_essay
                else None
            )
            return Task1ScoringRequest(
                attempt_id=attempt_id,
                writing_task_id=task_id,
                prompt=task.prompt,
                response=essay,
                task_type=task_type,
                image=image,
                chart_specialist=ChartSpecialistIdentity(
                    enabled=self.settings.ai_writing_chart_specialist_enabled,
                    provider=self.settings.ai_writing_chart_specialist_provider,
                    model=self.settings.ai_writing_deplot_model,
                    revision=self.settings.ai_writing_deplot_revision,
                ),
            )
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
            execution = None
            if isinstance(request, Task1ScoringRequest):
                snapshot = (
                    await WritingAnchorService(self.session).active_snapshot()
                    if self.settings.ai_writing_task1_scorer == "anchor_pairwise"
                    else AnchorSnapshot()
                )
                execution = Task1ExecutionConfig.pin(
                    self.settings.ai_writing_task1_scorer,
                    snapshot,
                    self.settings.ai_writing_pairwise_max_tree_nodes,
                )
            prompt_version = (
                execution.prompt_version
                if isinstance(request, Task1ScoringRequest)
                else effective_prompt_version(self.settings.ai_writing_prompt_version)
            )
            fingerprint = input_fingerprint(
                request, prompt_version, provider, model, execution=execution
            )
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
                scoring_architecture=execution.architecture if execution else None,
                anchor_set_id=execution.anchor_set_id if execution else None,
                execution_config_json=execution.model_dump(mode="json") if execution else None,
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
