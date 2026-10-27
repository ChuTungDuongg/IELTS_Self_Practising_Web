from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import WritingAIPracticeFeedback
from app.models.enums import AttemptScope, ModuleType, WritingAIRunStatus
from app.repositories.writing_ai import WritingAIRepository
from app.schemas.writing_ai import TRAITS, AIWritingResult, Task1WritingResult
from app.schemas.writing_ai_practice_feedback import PracticeFeedbackResponse
from app.services.classroom_capabilities import require_classroom_attempt_mutation


class WritingAIPracticeFeedbackService:
    def __init__(self, session: AsyncSession, user_id: UUID):
        self.session, self.user_id = session, user_id
        self.repository = WritingAIRepository(session)

    @staticmethod
    def require_focused(attempt, task_id):
        if (
            attempt.module_type != ModuleType.WRITING
            or attempt.scope != AttemptScope.FOCUSED_UNIT
            or attempt.focused_writing_task_id != task_id
            or attempt.test_session_id is not None
        ):
            raise AppError(
                "AI_PRACTICE_SCOPE_INVALID",
                "Chỉ lưu nhận xét cá nhân cho bài luyện Writing theo task.",
                422,
            )

    async def _eligible(self, attempt_id, task_id, *, lock=False):
        attempt = await self.repository.attempt(attempt_id, self.user_id, lock=lock)
        if attempt is None:
            raise AppError("ATTEMPT_NOT_FOUND", "Không tìm thấy bài làm.", 404)
        if lock:
            await require_classroom_attempt_mutation(self.session, self.user_id, attempt)
        self.require_focused(attempt, task_id)
        if await self.repository.task(task_id, attempt.test_version_id) is None:
            raise AppError("WRITING_TASK_NOT_FOUND", "Không tìm thấy task Writing.", 404)

    @staticmethod
    def validated_result(run):
        if (
            run is None
            or run.status != WritingAIRunStatus.COMPLETED
            or not isinstance(run.result_json, dict)
        ):
            raise AppError(
                "AI_PRACTICE_RUN_INVALID", "Cần một bài chấm AI hoàn tất với đủ bốn tiêu chí.", 422
            )
        try:
            schema = (
                Task1WritingResult if run.result_json.get("task_number") == 1 else AIWritingResult
            )
            return schema.model_validate(run.result_json)
        except ValidationError:
            raise AppError(
                "AI_PRACTICE_RESULT_INVALID", "Kết quả chấm AI chưa hợp lệ để lưu.", 422
            ) from None

    async def _present(self, row, result=None):
        if result is None:
            run = await self.repository.run(row.source_ai_run_id, user_id=self.user_id)
            result = self.validated_result(run)
        return PracticeFeedbackResponse(
            id=row.id,
            attempt_id=row.attempt_id,
            writing_task_id=row.writing_task_id,
            source_run_id=row.source_ai_run_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            criteria={
                trait: {
                    "score": getattr(row, f"{trait}_score"),
                    "feedback": getattr(row, f"{trait}_feedback"),
                }
                for trait in TRAITS
            },
            relevance=result.relevance,
        )

    async def get(self, attempt_id, task_id):
        async with self.session.begin():
            await self._eligible(attempt_id, task_id)
            row = await self.session.scalar(
                select(WritingAIPracticeFeedback).where(
                    WritingAIPracticeFeedback.user_id == self.user_id,
                    WritingAIPracticeFeedback.attempt_id == attempt_id,
                    WritingAIPracticeFeedback.writing_task_id == task_id,
                )
            )
            return await self._present(row) if row else None

    async def save(self, attempt_id, task_id, source_run_id):
        async with self.session.begin():
            await self._eligible(attempt_id, task_id, lock=True)
            run = await self.repository.run(source_run_id, user_id=self.user_id, lock=True)
            if run is None or run.attempt_id != attempt_id or run.writing_task_id != task_id:
                raise AppError(
                    "AI_PRACTICE_RUN_INVALID", "Bài chấm AI không thuộc bài luyện và task này.", 422
                )
            result = self.validated_result(run)
            values = {
                "source_ai_run_id": run.id,
                **{
                    f"{trait}_{field}": getattr(getattr(result.criteria, trait), field)
                    for trait in TRAITS
                    for field in ("score", "feedback")
                },
            }
            statement = insert(WritingAIPracticeFeedback).values(
                user_id=self.user_id, attempt_id=attempt_id, writing_task_id=task_id, **values
            )
            statement = (
                statement.on_conflict_do_update(
                    constraint="uq_writing_ai_practice_feedback_owner_task",
                    set_={**values, "updated_at": func.now()},
                )
                .returning(WritingAIPracticeFeedback)
                .execution_options(populate_existing=True)
            )
            row = await self.session.scalar(statement)
            return await self._present(row, result)
