"""Shared content access inside the calling service's transaction."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Classroom, User
from app.models.enums import UserRole
from app.services.classroom_capabilities import Capability, resolve_capabilities
from app.services.classrooms import ClassroomService


class ContentAccess:
    def __init__(self, session: AsyncSession, actor: User):
        self.session = session
        self.actor = actor
        self.classrooms = ClassroomService(session, actor)
        self.capabilities = frozenset()

    def staff(self, room: Classroom) -> bool:
        return Capability.GRADES_VIEW in self.capabilities

    async def room(self, classroom_id: UUID, *, mutation=False, owner=False, capability=Capability.CONTENT) -> Classroom:
        if mutation:
            await self.classrooms._lock_actor()
        else:
            await self.classrooms._load_actor()
        self.actor = self.classrooms.actor
        # Hold a shared room lock across multi-query reads, so publication and
        # membership changes cannot race a resource or feed authorization check.
        room = await self.classrooms._classroom(classroom_id, lock=mutation, read_lock=not mutation)
        await self.classrooms._readable(room)
        _, self.capabilities = await resolve_capabilities(self.session, self.actor, room)
        if owner and capability not in self.capabilities:
            raise AppError(
                "CLASSROOM_OWNERSHIP_REQUIRED",
                "The required classroom capability is missing.",
                403,
            )
        if mutation:
            self.classrooms._active(room)
        return room

    async def can_comment(self, room: Classroom) -> None:
        if self.staff(room) and self.actor.role != UserRole.ADMIN:
            return
        if await self.classrooms.repository.membership(room.id, self.actor.id) is None:
            raise AppError(
                "ACTIVE_MEMBERSHIP_REQUIRED", "An active classroom membership is required.", 403
            )
