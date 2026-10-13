"""One provenance boundary for human Writing and Speaking grading."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import AppError
from app.models import Attempt, ClassroomAssignment, TestSession, User
from app.models.enums import AttemptStatus, ModuleType, TestSessionStatus, UserRole
from app.schemas.grading import GradingCapabilities
from app.services.access_policy import AccessPolicy


def assignment_origin_clause(assignment_id: UUID) -> ColumnElement[bool]:
    return or_(
        Attempt.classroom_assignment_id == assignment_id,
        TestSession.classroom_assignment_id == assignment_id,
    )


def assignment_origin(attempt: Attempt) -> UUID | None:
    return attempt.classroom_assignment_id or (
        attempt.test_session.classroom_assignment_id if attempt.test_session else None
    )


def require_review_unlocked(attempt: Attempt) -> None:
    if attempt.status in {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}:
        raise AppError("ATTEMPT_NOT_FINALIZED", "Finalize the attempt before grading.", 409)
    if attempt.test_session and attempt.test_session.status == TestSessionStatus.IN_PROGRESS:
        raise AppError("FULL_MOCK_REVIEW_LOCKED", "Complete the Full Mock before grading.", 409)


class GradingPolicy:
    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor

    async def require_assignment_attempt(
        self, classroom_id: UUID, assignment_id: UUID, attempt_id: UUID
    ) -> UUID:
        assignment = await self.session.scalar(
            select(ClassroomAssignment).where(
                ClassroomAssignment.id == assignment_id,
                ClassroomAssignment.classroom_id == classroom_id,
            )
        )
        if assignment is None:
            raise AppError("ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found.", 404)
        await AccessPolicy(self.session, self.actor).require_assignment_view(assignment)
        owner = await self.session.scalar(
            select(Attempt.user_id)
            .outerjoin(TestSession, Attempt.test_session_id == TestSession.id)
            .where(Attempt.id == attempt_id, assignment_origin_clause(assignment_id))
        )
        if owner is None:
            raise AppError("ASSIGNMENT_ATTEMPT_NOT_FOUND", "Assignment attempt not found.", 404)
        return owner

    async def require_final(
        self, attempt: Attempt, *, assignment_scope: tuple[UUID, UUID] | None = None
    ) -> None:
        if assignment_scope is not None:
            await self.require_assignment_attempt(*assignment_scope, attempt.id)
        elif self.actor.role != UserRole.ADMIN:
            if attempt.user_id != self.actor.id:
                raise AppError("ATTEMPT_NOT_FOUND", "Attempt not found.", 404)
            if assignment_origin(attempt) is not None:
                raise AppError(
                    "CLASSROOM_TEACHER_GRADING_REQUIRED",
                    "The classroom teacher must assign final scores.",
                    403,
                )
        require_review_unlocked(attempt)

    def capabilities(
        self, attempt: Attempt, *, has_final: bool = False, assignment_authorized: bool = False
    ) -> GradingCapabilities:
        classroom = assignment_origin(attempt) is not None
        unlocked = attempt.status not in {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED} and (
            not attempt.test_session or attempt.test_session.status != TestSessionStatus.IN_PROGRESS
        )
        subjective = attempt.module_type in {ModuleType.WRITING, ModuleType.SPEAKING}
        allowed = (
            unlocked
            and subjective
            and (
                self.actor.role == UserRole.ADMIN
                or (assignment_authorized and classroom)
                or (not classroom and attempt.user_id == self.actor.id)
            )
        )
        return GradingCapabilities(
            context="CLASSROOM" if classroom else "PERSONAL",
            can_edit_final=allowed,
            can_copy_ai_to_final=allowed,
            waiting_for_teacher=classroom and subjective and not has_final,
        )
