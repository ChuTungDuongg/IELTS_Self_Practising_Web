from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.exceptions import AppError
from app.models import ClassroomMembership, User
from app.models.classroom_staff import ClassroomStaff, ClassroomStaffEvent
from app.schemas.classroom_staff import StaffPermissions, StaffResponse
from app.services.auth import normalize_email
from app.services.classroom_capabilities import Capability, active_staff_clause, require_capability
from app.services.classrooms import ClassroomService


class ClassroomStaffService:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.rooms = ClassroomService(session, actor)

    async def _room(self, classroom_id, *, mutation=False):
        if mutation:
            await self.rooms._lock_actor()
        else:
            await self.rooms._load_actor()
        self.actor = self.rooms.actor
        room = await self.rooms._classroom(classroom_id, lock=mutation, read_lock=not mutation)
        if mutation:
            self.rooms._active(room)
        return room

    async def _present(self, row, room, user=None):
        user = user or await self.session.get(User, row.user_id)
        return StaffResponse(**{key: getattr(row, key) for key in StaffResponse.model_fields
                               if key not in {"display_name", "email", "classroom_name"}},
                             display_name=user.display_name, email=user.email, classroom_name=room.name)

    def _event(self, row):
        self.session.add(ClassroomStaffEvent(
            staff_id=row.id, actor_id=self.actor.id, staff_role=row.staff_role, status=row.status,
            **StaffPermissions.model_validate(row).model_dump(),
        ))

    @staticmethod
    def _eligible(user, role):
        if not user or not user.is_active or user.role not in (
            {"TEACHER"} if role == "CO_TEACHER" else {"USER", "TEACHER"}
        ):
            raise AppError("STAFF_ACCOUNT_INELIGIBLE", "Staff role requires an eligible active account.", 422)

    async def list(self, classroom_id):
        async with self.session.begin():
            room = await self._room(classroom_id)
            await require_capability(self.session, self.actor, room, Capability.GRADES_VIEW)
            rows = (await self.session.execute(select(ClassroomStaff, User).join(User, User.id == ClassroomStaff.user_id)
                    .where(ClassroomStaff.classroom_id == room.id)
                    .order_by(ClassroomStaff.created_at.desc(), ClassroomStaff.id).limit(500))).all()
            return [await self._present(row, room, user) for row, user in rows]

    async def mine(self):
        from app.models import Classroom
        async with self.session.begin():
            await self.rooms._load_actor()
            rows = (await self.session.execute(select(ClassroomStaff, Classroom)
                    .join(Classroom, Classroom.id == ClassroomStaff.classroom_id)
                    .where(ClassroomStaff.user_id == self.actor.id)
                    .order_by(ClassroomStaff.created_at.desc(), ClassroomStaff.id).limit(100))).all()
            return [await self._present(row, room, self.actor) for row, room in rows]

    async def invite(self, classroom_id, data):
        async with self.session.begin():
            await self.rooms._lock_actor()
            user = await self.session.scalar(select(User).where(User.email == normalize_email(str(data.email)))
                                            .with_for_update(read=True))
            self._eligible(user, data.staff_role)
            room = await self.rooms._classroom(classroom_id, lock=True)
            self.rooms._active(room)
            await require_capability(self.session, self.actor, room, Capability.STAFF)
            if user.id == room.teacher_id:
                raise AppError("STAFF_OWNER_IMMUTABLE", "The owner cannot be a staff membership.", 409)
            current = await self.session.scalar(select(ClassroomStaff.id).where(
                ClassroomStaff.classroom_id == room.id, ClassroomStaff.user_id == user.id,
                ClassroomStaff.status.in_(["PENDING", "ACCEPTED"])))
            if current:
                raise AppError("STAFF_ALREADY_EXISTS", "An invitation or staff membership already exists.", 409)
            row = ClassroomStaff(classroom_id=room.id, user_id=user.id, invited_by_user_id=self.actor.id,
                                 **data.model_dump(exclude={"email"}))
            self.session.add(row)
            await self.session.flush()
            self._event(row)
            from app.models.enums import NotificationEntityType, NotificationType
            from app.services.notifications import NotificationService
            await NotificationService(self.session).create_once(
                user_id=user.id, type=NotificationType.CLASSROOM_INVITED,
                entity_type=NotificationEntityType.INVITATION, entity_id=row.id,
                payload={"classroom_name": room.name, "staff_role": row.staff_role},
            )
            return await self._present(row, room, user)

    async def change(self, classroom_id, staff_id, *, data=None, response=None, revoke=False):
        async with self.session.begin():
            # Account role/deactivation and staff changes share actor -> target -> room order.
            # FOR SHARE conflicts with the administrator's FOR NO KEY UPDATE demotion lock.
            await self.rooms._lock_actor()
            target_id = await self.session.scalar(select(ClassroomStaff.user_id).where(
                ClassroomStaff.id == staff_id, ClassroomStaff.classroom_id == classroom_id))
            if target_id is None:
                raise AppError("STAFF_NOT_FOUND", "Staff invitation not found.", 404)
            target = await self.session.scalar(select(User).where(User.id == target_id)
                .with_for_update(read=True).execution_options(populate_existing=True))
            room = await self._room(classroom_id, mutation=True)
            row = await self.session.scalar(select(ClassroomStaff).where(
                ClassroomStaff.id == staff_id, ClassroomStaff.classroom_id == room.id
            ).with_for_update().execution_options(populate_existing=True))
            if not row:
                raise AppError("STAFF_NOT_FOUND", "Staff invitation not found.", 404)
            if response is not None:
                if row.user_id != self.actor.id:
                    raise AppError("STAFF_INVITATION_PRIVATE", "Only the invited account may respond.", 403)
                if row.status != "PENDING":
                    raise AppError("STAFF_ALREADY_RESOLVED", "Invitation already resolved.", 409)
                self._eligible(self.actor, row.staff_role)
                row.status = "ACCEPTED" if response else "DECLINED"
                if response:
                    row.accepted_at = datetime.now(UTC)
                    # A staff member is no longer an ordinary active student; history is retained.
                    await self.session.execute(update(ClassroomMembership).where(
                        ClassroomMembership.classroom_id == room.id, ClassroomMembership.user_id == row.user_id,
                        ClassroomMembership.left_at.is_(None),
                    ).values(left_at=datetime.now(UTC), removed_by_user_id=self.actor.id))
            else:
                await require_capability(self.session, self.actor, room, Capability.STAFF)
                if row.status not in {"ACCEPTED", "PENDING"}:
                    raise AppError("STAFF_ALREADY_RESOLVED", "Staff membership is already closed.", 409)
                if revoke:
                    row.status = "CANCELLED" if row.status == "PENDING" else "REVOKED"
                    row.revoked_at = datetime.now(UTC)
                else:
                    self._eligible(target, data.staff_role)
                    for key, value in data.model_dump().items():
                        setattr(row, key, value)
            self._event(row)
            await self.session.flush()
            return await self._present(row, room)


async def require_not_staff(session, classroom_id, user_id):
    if await session.scalar(select(active_staff_clause(classroom_id, user_id))):
        raise AppError("CLASSROOM_STAFF_NOT_STUDENT", "Remove staff access before enrolling as a student.", 409)
