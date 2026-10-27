from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.presenters import present_version
from app.core.exceptions import AppError
from app.models import Classroom, ClassroomAssignment, ClassroomMembership, TestVersion, User
from app.models.enums import AssignmentStatus, ClassroomStatus, TestOrigin, UserRole
from app.repositories.tests import version_detail_query
from app.schemas.attempts import AttemptCreate
from app.schemas.classroom_assignments import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentStart,
    AssignmentStartResponse,
)
from app.services.access_policy import AccessPolicy
from app.services.attempts import AttemptService
from app.services.test_sessions import TestSessionService


async def require_assignment_start(
    session: AsyncSession, user_id: UUID, assignment_id: UUID, version_id: UUID
):
    """Called only by the lifecycle services inside their creation transaction."""
    actor = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
        .with_for_update(key_share=True)
    )
    if actor is None or not actor.is_active:
        raise AppError("ACCOUNT_INACTIVE", "This account is inactive.", 403)
    policy = AccessPolicy(session, actor)
    version = await policy.lock_version(version_id)
    classroom_id = await session.scalar(
        select(ClassroomAssignment.classroom_id).where(ClassroomAssignment.id == assignment_id)
    )
    if classroom_id is None:
        raise AppError("ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found.", 404)
    classroom = await session.scalar(
        select(Classroom)
        .where(Classroom.id == classroom_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    assignment = await session.scalar(
        select(ClassroomAssignment)
        .where(ClassroomAssignment.id == assignment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if assignment.test_version_id != version_id or assignment.status != AssignmentStatus.ACTIVE:
        raise AppError(
            "ASSIGNMENT_NOT_ACCESSIBLE", "This assignment is not available for a new start.", 409
        )
    if classroom.status != ClassroomStatus.ACTIVE:
        raise AppError("CLASSROOM_ARCHIVED", "This classroom is archived.", 409)
    membership = await session.scalar(
        select(ClassroomMembership.id)
        .where(
            ClassroomMembership.classroom_id == classroom_id,
            ClassroomMembership.user_id == user_id,
            ClassroomMembership.left_at.is_(None),
        )
        .with_for_update()
    )
    if membership is None:
        raise AppError(
            "ACTIVE_MEMBERSHIP_REQUIRED", "Join this classroom before starting its assignment.", 403
        )
    if not await policy.version_access(version, classroom=True):
        raise AppError(
            "VERSION_NOT_CLASSROOM_APPROVED",
            "The version is no longer eligible for classroom use.",
            409,
        )
    from app.services.assignment_scheduling import enforce_schedule_start

    await enforce_schedule_start(session, assignment, user_id)
    return assignment


class ClassroomAssignmentService:
    def __init__(self, session: AsyncSession, actor: User):
        self.session, self.actor = session, actor
        self.actor_id = actor.id
        self.policy = AccessPolicy(session, actor)

    async def create(self, classroom_id: UUID, data: AssignmentCreate):
        async with self.session.begin():
            await self.policy.lock_actor()
            version = await self.policy.lock_version(data.test_version_id)
            classroom = await self._classroom(classroom_id, locked=True)
            await self.policy.require_classroom_manage(classroom)
            self._active(classroom)
            if (
                version.test.origin == TestOrigin.TEACHER
                and version.test.owner_user_id != classroom.teacher_id
            ):
                raise AppError(
                    "TEST_OWNERSHIP_REQUIRED",
                    "Assign your own approved content or official content.",
                    403,
                )
            if not await self.policy.version_access(version, classroom=True):
                raise AppError(
                    "VERSION_NOT_CLASSROOM_APPROVED",
                    "This version requires active classroom or public approval.",
                    409,
                )
            assignment = ClassroomAssignment(
                classroom_id=classroom_id,
                test_version_id=version.id,
                created_by_user_id=self.actor_id,
                title=data.title,
                note=data.note,
                **data.model_dump(
                    include={
                        "available_from",
                        "due_at",
                        "cutoff_at",
                        "max_attempts",
                        "allow_late_submission",
                    }
                ),
            )
            self.session.add(assignment)
            await self.session.flush()
            from app.services.assignment_scheduling import notify_assignment, policy_event

            event = await policy_event(self.session, assignment, self.actor_id, kind="CREATED")
            await notify_assignment(self.session, assignment, "ASSIGNMENT_CREATED", str(event.id))
            response = await self._present(assignment)
        return response

    async def list(self, classroom_id):
        classroom = await self._classroom(classroom_id)
        await self._read(classroom)
        rows = list(
            await self.session.scalars(
                select(ClassroomAssignment)
                .where(ClassroomAssignment.classroom_id == classroom_id)
                .order_by(ClassroomAssignment.created_at.desc())
            )
        )
        return [await self._present(row) for row in rows]

    async def get(self, classroom_id, assignment_id):
        classroom = await self._classroom(classroom_id)
        await self._read(classroom)
        assignment = await self._assignment(classroom_id, assignment_id)
        return await self._present(assignment)

    async def archive(self, classroom_id, assignment_id):
        async with self.session.begin():
            await self.policy.lock_actor()
            classroom = await self._classroom(classroom_id, locked=True)
            await self.policy.require_classroom_manage(classroom)
            self._active(classroom)
            assignment = await self._assignment(classroom_id, assignment_id, locked=True)
            assignment.status = AssignmentStatus.ARCHIVED
            assignment.archived_at = datetime.now(UTC)
            await self.session.flush()
            response = await self._present(assignment)
        return response

    async def start(self, assignment_id, data: AssignmentStart):
        # The lifecycle service repeats authorization under locks in its transaction.
        async with self.session.begin():
            version_id = await self.session.scalar(
                select(ClassroomAssignment.test_version_id).where(
                    ClassroomAssignment.id == assignment_id
                )
            )
            if version_id is None:
                raise AppError("ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found.", 404)
        if data.mode == "FULL_MOCK":
            result = await TestSessionService(self.session, self.actor_id).start(
                version_id, _classroom_assignment_id=assignment_id
            )
            return AssignmentStartResponse(
                attempt_id=result.current_attempt.attempt_id,
                test_session_id=result.session.session_id,
            )
        result = await AttemptService(self.session, self.actor_id).start(
            AttemptCreate(
                test_version_id=version_id,
                module=data.module,
                scope=data.scope,
                focused_unit=data.focused_unit,
                speaking_mode=data.speaking_mode,
                timer=data.timer,
            ),
            _classroom_assignment_id=assignment_id,
        )
        return AssignmentStartResponse(attempt_id=result.attempt_id)

    async def _classroom(self, classroom_id, *, locked=False):
        statement = (
            select(Classroom)
            .where(Classroom.id == classroom_id)
            .execution_options(populate_existing=True)
        )
        if locked:
            statement = statement.with_for_update()
        row = await self.session.scalar(statement)
        if row is None:
            raise AppError("CLASSROOM_NOT_FOUND", "Classroom not found.", 404)
        return row

    async def _read(self, classroom):
        if self.actor.role == UserRole.ADMIN or (
            self.actor.role == UserRole.TEACHER and classroom.teacher_id == self.actor_id
        ):
            return
        member = await self.session.scalar(
            select(ClassroomMembership.id)
            .where(
                ClassroomMembership.classroom_id == classroom.id,
                ClassroomMembership.user_id == self.actor_id,
            )
            .limit(1)
        )
        if member is None:
            raise AppError("ASSIGNMENT_NOT_ACCESSIBLE", "This classroom is not accessible.", 403)

    async def _assignment(self, classroom_id, assignment_id, *, locked=False):
        statement = select(ClassroomAssignment).where(
            ClassroomAssignment.id == assignment_id,
            ClassroomAssignment.classroom_id == classroom_id,
        )
        if locked:
            statement = statement.with_for_update()
        assignment = await self.session.scalar(statement)
        if assignment is None:
            raise AppError(
                "ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found in this classroom.", 404
            )
        return assignment

    @staticmethod
    def _active(classroom):
        if classroom.status != ClassroomStatus.ACTIVE:
            raise AppError("CLASSROOM_ARCHIVED", "This classroom is archived.", 409)

    async def _present(self, assignment):
        version = await self.session.scalar(
            version_detail_query().where(TestVersion.id == assignment.test_version_id)
        )
        return AssignmentResponse.model_validate(assignment).model_copy(
            update={"version": present_version(version)}
        )
