"""Shared content access inside the calling service's transaction."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Classroom, User
from app.models.enums import UserRole
from app.services.classrooms import ClassroomService


class ContentAccess:
    def __init__(self, session: AsyncSession, actor: User):
        self.session = session
        self.actor = actor
        self.classrooms = ClassroomService(session, actor)

    def staff(self, room: Classroom) -> bool:
        return self.actor.role == UserRole.ADMIN or (
            self.actor.role == UserRole.TEACHER and room.teacher_id == self.actor.id
        )

    async def room(self, classroom_id: UUID, *, mutation=False, owner=False) -> Classroom:
        if mutation:
            await self.classrooms._lock_actor()
        else:
            await self.classrooms._load_actor()
        self.actor = self.classrooms.actor
        # Hold a shared room lock across multi-query reads, so publication and
        # membership changes cannot race a resource or feed authorization check.
        room = await self.classrooms._classroom(classroom_id, lock=mutation, read_lock=not mutation)
        await self.classrooms._readable(room)
        if owner and not (self.actor.role == UserRole.TEACHER and room.teacher_id == self.actor.id):
            raise AppError(
                "CLASSROOM_OWNERSHIP_REQUIRED",
                "Only the teacher owner may author classroom content.",
                403,
            )
        if mutation:
            self.classrooms._active(room)
        return room

    async def can_comment(self, room: Classroom) -> None:
        if self.actor.role == UserRole.TEACHER and room.teacher_id == self.actor.id:
            return
        if await self.classrooms.repository.membership(room.id, self.actor.id) is None:
            raise AppError(
                "ACTIVE_MEMBERSHIP_REQUIRED", "An active classroom membership is required.", 403
            )
