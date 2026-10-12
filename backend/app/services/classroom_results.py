from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Attempt, ClassroomAssignment, TestSession, User, WritingAIGradingRun
from app.models.enums import AttemptStatus, ModuleType, TestSessionStatus
from app.repositories.attempts import AttemptRepository
from app.schemas.attempts import AnswerResponse
from app.schemas.classroom_results import AssignmentResultDetail, AssignmentResultSummary
from app.services.access_policy import AccessPolicy
from app.services.attempt_scope import AttemptScopeGuard
from app.services.attempts import AttemptService
from app.services.writing_ai import present_run


class ClassroomResultService:
    def __init__(self, session: AsyncSession, actor: User):
        self.session = session
        self.policy = AccessPolicy(session, actor)

    async def _authorize(self, classroom_id: UUID, assignment_id: UUID):
        assignment = await self.session.scalar(
            select(ClassroomAssignment).where(
                ClassroomAssignment.id == assignment_id,
                ClassroomAssignment.classroom_id == classroom_id,
            )
        )
        if assignment is None:
            raise AppError(
                "ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found in this classroom.", 404
            )
        await self.policy.require_assignment_view(assignment)
        return assignment

    @staticmethod
    def _origin(assignment_id):
        return or_(
            Attempt.classroom_assignment_id == assignment_id,
            TestSession.classroom_assignment_id == assignment_id,
        )

    async def list(self, classroom_id, assignment_id, *, student_id=None, limit=100, offset=0):
        await self._authorize(classroom_id, assignment_id)
        statement = (
            select(Attempt.id, User.id, User.display_name)
            .outerjoin(TestSession, Attempt.test_session_id == TestSession.id)
            .join(User, Attempt.user_id == User.id)
            .where(self._origin(assignment_id))
            .order_by(Attempt.started_at.desc(), Attempt.id)
            .limit(limit)
            .offset(offset)
        )
        if student_id:
            statement = statement.where(Attempt.user_id == student_id)
        rows = (await self.session.execute(statement)).all()
        result = []
        for attempt_id, user_id, name in rows:
            attempt = await AttemptRepository(self.session).get(attempt_id, user_id=user_id)
            result.append(
                AssignmentResultSummary(
                    student_id=user_id,
                    student_display_name=name,
                    attempt=AttemptService._to_response(attempt),
                    session_id=attempt.test_session_id,
                )
            )
        return result

    async def detail(self, classroom_id, assignment_id, attempt_id):
        await self._authorize(classroom_id, assignment_id)
        user_id = await self.session.scalar(
            select(Attempt.user_id)
            .outerjoin(TestSession, Attempt.test_session_id == TestSession.id)
            .where(Attempt.id == attempt_id, self._origin(assignment_id))
        )
        if user_id is None:
            raise AppError(
                "ASSIGNMENT_ATTEMPT_NOT_FOUND",
                "This attempt did not originate from this assignment.",
                404,
            )
        # The policy above is the only teacher authorization boundary. Reuse the
        # unchanged student-owned read services, never allow_any_user for teachers.
        attempt = await AttemptRepository(self.session).get(attempt_id, user_id=user_id)
        student = await self.session.get(User, user_id)
        service = AttemptService(self.session, user_id)
        result = AssignmentResultDetail(
            student_id=user_id,
            student_display_name=student.display_name,
            attempt=service._to_response(attempt),
            session_id=attempt.test_session_id,
        )
        result.submitted_answers = [
            AnswerResponse(
                question_id=answer.question_id,
                value=answer.value,
                is_correct=answer.is_correct,
                saved_at=answer.updated_at,
                revision=answer.revision,
            )
            for answer in attempt.answers
            if AttemptScopeGuard(attempt).allows_group(answer.question.question_group)
        ]
        if attempt.module_type == ModuleType.WRITING:
            module = next(
                (
                    item
                    for item in attempt.test_version.modules
                    if item.module_type == ModuleType.WRITING
                ),
                None,
            )
            responses = {row.writing_task_id: row for row in attempt.writing_responses}
            scores = {row.writing_task_id: row for row in attempt.writing_scores}
            result.writing_responses = (
                [
                    service._present_writing_review(
                        task, responses.get(task.id), scores.get(task.id)
                    )
                    for task in module.writing_tasks
                    if AttemptScopeGuard(attempt).allows_unit("WRITING_TASK", task.id)
                ]
                if module
                else []
            )
            runs = list(
                await self.session.scalars(
                    select(WritingAIGradingRun)
                    .where(WritingAIGradingRun.attempt_id == attempt_id)
                    .order_by(WritingAIGradingRun.created_at.desc())
                )
            )
            result.ai_runs = [present_run(run) for run in runs]
        finalized = attempt.status not in {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}
        mock_unlocked = (
            attempt.test_session is None
            or attempt.test_session.status != TestSessionStatus.IN_PROGRESS
        )
        if finalized and mock_unlocked:
            if attempt.module_type == ModuleType.SPEAKING:
                from app.core.config import get_settings
                from app.services.speaking_ai import SpeakingAIService
                from app.services.speaking_media import SpeakingMediaService

                result.speaking_review = await SpeakingMediaService(
                    self.session, self.policy.actor
                ).review(attempt_id)
                result.speaking_review.can_generate_transcript = False
                result.speaking_ai_run = await SpeakingAIService(
                    self.session, self.policy.actor, get_settings()
                ).latest(attempt_id)
                return result
            result.review = await service.review(attempt_id)
            if attempt.module_type == ModuleType.READING:
                result.reading_review = await service.reading_review(attempt_id)
            elif attempt.module_type == ModuleType.LISTENING:
                result.listening_review = await service.listening_review(attempt_id)
            else:
                result.writing_review = service._present_writing_attempt_review(result.review)
        return result
