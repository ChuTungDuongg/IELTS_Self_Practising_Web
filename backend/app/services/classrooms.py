from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Classroom, ClassroomInvitation, ClassroomMembership, User
from app.models.enums import (
    ClassroomStatus,
    InvitationStatus,
    NotificationEntityType,
    NotificationType,
    UserRole,
)
from app.repositories.classrooms import ClassroomRepository
from app.schemas.classrooms import (
    ClassroomCreate,
    ClassroomList,
    ClassroomResponse,
    ClassroomUpdate,
    InvitationCreate,
    InvitationList,
    InvitationResponse,
    MembershipList,
    MembershipResponse,
)
from app.services.access_policy import AccessPolicy
from app.services.auth import normalize_email
from app.services.notifications import NotificationService


class ClassroomService:
    def __init__(self, session: AsyncSession, actor: User):
        self.session = session
        self.actor = actor
        self.actor_id = actor.id
        self.policy = AccessPolicy(session, actor)
        self.repository = ClassroomRepository(session)
        self.notifications = NotificationService(session)

    async def _lock_actor(self):
        self.actor = await self.policy.lock_actor()

    async def _load_actor(self):
        actor = await self.session.scalar(
            select(User).where(User.id == self.actor_id).execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active:
            raise AppError("ACCOUNT_INACTIVE", "This account is inactive.", 403)
        self.actor = self.policy.actor = actor

    async def _classroom(self, classroom_id: UUID, *, lock=False, read_lock=False):
        room = await self.repository.classroom(classroom_id, lock=lock, read_lock=read_lock)
        if room is None:
            raise AppError("CLASSROOM_NOT_FOUND", "The classroom does not exist.", 404)
        return room

    @staticmethod
    def _active(room: Classroom):
        if room.status != ClassroomStatus.ACTIVE:
            raise AppError("CLASSROOM_ARCHIVED", "This classroom is archived and read-only.", 409)

    async def _readable(self, room: Classroom):
        if self.actor.role == UserRole.ADMIN or (
            self.actor.role == UserRole.TEACHER and room.teacher_id == self.actor.id
        ):
            return
        if await self.repository.membership(room.id, self.actor.id, active=False) is None:
            raise AppError("CLASSROOM_NOT_FOUND", "The classroom does not exist.", 404)

    async def create(self, data: ClassroomCreate) -> ClassroomResponse:
        async with self.session.begin():
            await self._lock_actor()
            if self.actor.role != UserRole.TEACHER:
                raise AppError("TEACHER_REQUIRED", "Only a teacher may own a classroom.", 403)
            room = Classroom(teacher_id=self.actor.id, name=data.name, description=data.description)
            self.session.add(room)
            await self.session.flush()
            return ClassroomResponse.model_validate(room)

    async def list(self) -> ClassroomList:
        async with self.session.begin():
            await self._load_actor()
            return ClassroomList(
                items=[
                    ClassroomResponse.model_validate(room)
                    for room in await self.repository.list(self.actor)
                ]
            )

    async def get(self, classroom_id: UUID) -> ClassroomResponse:
        async with self.session.begin():
            await self._load_actor()
            room = await self._classroom(classroom_id)
            await self._readable(room)
            teacher = await self.session.get(User, room.teacher_id)
            member_count = await self.session.scalar(
                select(func.count()).select_from(ClassroomMembership).where(
                    ClassroomMembership.classroom_id == room.id,
                    ClassroomMembership.left_at.is_(None),
                )
            )
            response = ClassroomResponse.model_validate(room)
            response.teacher_name = teacher.display_name if teacher else None
            response.active_member_count = member_count or 0
            return response

    async def update(self, classroom_id: UUID, data: ClassroomUpdate) -> ClassroomResponse:
        async with self.session.begin():
            await self._lock_actor()
            room = await self._classroom(classroom_id, lock=True)
            await self.policy.require_classroom_manage(room)
            self._active(room)
            for key, value in data.model_dump(exclude_unset=True).items():
                setattr(room, key, value)
            await self.session.flush()
            await self.session.refresh(room)
            return ClassroomResponse.model_validate(room)

    async def archive(self, classroom_id: UUID) -> ClassroomResponse:
        async with self.session.begin():
            await self._lock_actor()
            room = await self._classroom(classroom_id, lock=True)
            await self.policy.require_classroom_manage(room)
            if room.status == ClassroomStatus.ACTIVE:
                room.status = ClassroomStatus.ARCHIVED
                room.archived_at = datetime.now(UTC)
                members = await self.repository.members(room.id)
                recipients = {member.user_id for member, _ in members if member.left_at is None} | {
                    room.teacher_id
                }
                for recipient in sorted(recipients):
                    await self.notifications.create_once(
                        user_id=recipient,
                        type=NotificationType.CLASSROOM_ARCHIVED,
                        entity_type=NotificationEntityType.CLASSROOM,
                        entity_id=room.id,
                        payload={"classroom_name": room.name},
                    )
            await self.session.flush()
            await self.session.refresh(room)
            return ClassroomResponse.model_validate(room)

    async def restore(self, classroom_id: UUID) -> ClassroomResponse:
        async with self.session.begin():
            await self._lock_actor()
            await self.policy.require_admin_moderation()
            teacher_id = await self.session.scalar(
                select(Classroom.teacher_id).where(Classroom.id == classroom_id)
            )
            if teacher_id is None:
                raise AppError("CLASSROOM_NOT_FOUND", "The classroom does not exist.", 404)
            teacher = await self.session.scalar(
                select(User)
                .where(User.id == teacher_id)
                .execution_options(populate_existing=True)
                .with_for_update(key_share=True)
            )
            room = await self._classroom(classroom_id, lock=True)
            if teacher is None or teacher.role != UserRole.TEACHER or not teacher.is_active:
                raise AppError("TEACHER_REQUIRED", "Restore requires an active teacher owner.", 409)
            room.status = ClassroomStatus.ACTIVE
            room.archived_at = None
            await self.session.flush()
            await self.session.refresh(room)
            return ClassroomResponse.model_validate(room)

    async def members(self, classroom_id: UUID) -> MembershipList:
        async with self.session.begin():
            await self._load_actor()
            room = await self._classroom(classroom_id)
            await self.policy.require_classroom_manage(room)
            return MembershipList(
                items=[
                    self._membership_response(member, user)
                    for member, user in await self.repository.members(room.id)
                ]
            )

    async def _invitation_response(
        self, invitation: ClassroomInvitation, room: Classroom | None = None
    ):
        room = room or await self._classroom(invitation.classroom_id)
        return InvitationResponse(
            **{
                field: getattr(invitation, field)
                for field in InvitationResponse.model_fields
                if field != "classroom_name"
            },
            classroom_name=room.name,
        )

    @staticmethod
    def _membership_response(member: ClassroomMembership, user: User):
        return MembershipResponse(
            **{
                field: getattr(member, field)
                for field in MembershipResponse.model_fields
                if field not in {"display_name", "email"}
            },
            display_name=user.display_name,
            email=user.email,
        )

    async def _invited_notification(self, invitation: ClassroomInvitation, room: Classroom):
        if invitation.invited_user_id is not None:
            await self.notifications.create_once(
                user_id=invitation.invited_user_id,
                type=NotificationType.CLASSROOM_INVITED,
                entity_type=NotificationEntityType.INVITATION,
                entity_id=invitation.id,
                payload={"classroom_name": room.name},
            )

    async def invite(self, classroom_id: UUID, data: InvitationCreate) -> InvitationResponse:
        async with self.session.begin():
            await self._lock_actor()
            room = await self._classroom(classroom_id, lock=True)
            await self.policy.require_classroom_manage(room)
            self._active(room)
            email = normalize_email(str(data.email))
            recipient = await self.session.scalar(select(User).where(User.email == email))
            if recipient is not None and recipient.id == room.teacher_id:
                raise AppError(
                    "CLASSROOM_OWNER_INVITATION", "The owner cannot join their own classroom.", 409
                )
            if recipient is not None and await self.repository.membership(room.id, recipient.id):
                raise AppError(
                    "ACTIVE_MEMBERSHIP_EXISTS", "This user is already an active member.", 409
                )
            pending = await self.session.scalar(
                select(ClassroomInvitation.id).where(
                    ClassroomInvitation.classroom_id == room.id,
                    ClassroomInvitation.invited_email_normalized == email,
                    ClassroomInvitation.status == InvitationStatus.PENDING,
                )
            )
            if pending:
                raise AppError(
                    "INVITATION_ALREADY_PENDING",
                    "This email already has a pending invitation.",
                    409,
                )
            invitation = ClassroomInvitation(
                classroom_id=room.id,
                invited_email=str(data.email),
                invited_email_normalized=email,
                invited_user_id=recipient.id if recipient else None,
                invited_by_user_id=self.actor.id,
            )
            self.session.add(invitation)
            await self.session.flush()
            await self._invited_notification(invitation, room)
            return await self._invitation_response(invitation, room)

    async def invitations(self, classroom_id: UUID) -> InvitationList:
        async with self.session.begin():
            await self._load_actor()
            room = await self._classroom(classroom_id)
            await self.policy.require_classroom_manage(room)
            return InvitationList(
                items=[
                    await self._invitation_response(invitation, room)
                    for invitation in await self.repository.invitations(room.id)
                ]
            )

    async def my_invitations(self) -> InvitationList:
        async with self.session.begin():
            await self._load_actor()
            invitations = await self.repository.my_invitations(
                self.actor, normalize_email(self.actor.email)
            )
            return InvitationList(
                items=[await self._invitation_response(invitation) for invitation in invitations]
            )

    async def _lock_invitation(self, invitation_id: UUID):
        classroom_id = await self.session.scalar(
            select(ClassroomInvitation.classroom_id).where(ClassroomInvitation.id == invitation_id)
        )
        if classroom_id is None:
            raise AppError("INVITATION_NOT_FOUND", "The invitation does not exist.", 404)
        room = await self._classroom(classroom_id, lock=True)
        invitation = await self.repository.invitation(invitation_id, lock=True)
        if invitation is None:
            raise AppError("INVITATION_NOT_FOUND", "The invitation does not exist.", 404)
        return room, invitation

    @staticmethod
    def _pending(invitation: ClassroomInvitation):
        if invitation.status != InvitationStatus.PENDING:
            raise AppError(
                "INVITATION_ALREADY_RESOLVED", "This invitation has already been resolved.", 409
            )

    def _recipient(self, invitation: ClassroomInvitation):
        if invitation.invited_email_normalized != normalize_email(self.actor.email) or (
            invitation.invited_user_id is not None and invitation.invited_user_id != self.actor.id
        ):
            raise AppError(
                "INVITATION_EMAIL_MISMATCH", "Only the invited account may respond.", 403
            )

    async def cancel(self, invitation_id: UUID) -> InvitationResponse:
        async with self.session.begin():
            await self._lock_actor()
            room, invitation = await self._lock_invitation(invitation_id)
            await self.policy.require_classroom_manage(room)
            self._active(room)
            self._pending(invitation)
            invitation.status = InvitationStatus.CANCELLED
            invitation.cancelled_at = datetime.now(UTC)
            await self.session.flush()
            return await self._invitation_response(invitation, room)

    async def _respond(self, invitation_id: UUID, *, accept: bool):
        async with self.session.begin():
            await self._lock_actor()
            room, invitation = await self._lock_invitation(invitation_id)
            self._recipient(invitation)
            self._active(room)
            self._pending(invitation)
            member = None
            if accept:
                if room.teacher_id == self.actor.id:
                    raise AppError(
                        "CLASSROOM_OWNER_INVITATION",
                        "The owner cannot join their own classroom.",
                        409,
                    )
                if await self.repository.membership(room.id, self.actor.id):
                    raise AppError(
                        "ACTIVE_MEMBERSHIP_EXISTS", "An active membership already exists.", 409
                    )
                member = ClassroomMembership(classroom_id=room.id, user_id=self.actor.id)
                self.session.add(member)
            invitation.invited_user_id = self.actor.id
            invitation.status = InvitationStatus.ACCEPTED if accept else InvitationStatus.DECLINED
            invitation.responded_at = datetime.now(UTC)
            await self.session.flush()
            await self.notifications.create_once(
                user_id=room.teacher_id,
                type=NotificationType.CLASSROOM_INVITATION_ACCEPTED
                if accept
                else NotificationType.CLASSROOM_INVITATION_DECLINED,
                entity_type=NotificationEntityType.INVITATION,
                entity_id=invitation.id,
                payload={"classroom_name": room.name, "student_name": self.actor.display_name},
            )
            return (
                self._membership_response(member, self.actor)
                if member
                else await self._invitation_response(invitation, room)
            )

    async def accept(self, invitation_id: UUID) -> MembershipResponse:
        return await self._respond(invitation_id, accept=True)

    async def decline(self, invitation_id: UUID) -> InvitationResponse:
        return await self._respond(invitation_id, accept=False)

    async def _end_membership(self, classroom_id: UUID, user_id: UUID, *, remove: bool):
        async with self.session.begin():
            await self._lock_actor()
            room = await self._classroom(classroom_id, lock=True)
            if remove:
                await self.policy.require_classroom_manage(room)
            self._active(room)
            member = await self.repository.membership(room.id, user_id)
            if member is None:
                raise AppError(
                    "ACTIVE_MEMBERSHIP_REQUIRED", "An active membership is required.", 409
                )
            member.left_at = datetime.now(UTC)
            member.removed_by_user_id = self.actor.id if remove else None
            user = await self.session.get(User, user_id)
            assert user is not None
            await self.session.flush()
            return self._membership_response(member, user)

    async def remove_member(self, classroom_id: UUID, user_id: UUID) -> MembershipResponse:
        return await self._end_membership(classroom_id, user_id, remove=True)

    async def leave(self, classroom_id: UUID) -> MembershipResponse:
        return await self._end_membership(classroom_id, self.actor_id, remove=False)

    async def bind_pending_invitations(self, user: User):
        """Bind known-email invitations without joining, inside authentication's transaction."""
        if not self.session.in_transaction():
            raise RuntimeError("Invitation binding requires the caller's transaction")
        await self._lock_actor()
        ids = (
            await self.session.execute(
                select(ClassroomInvitation.id, ClassroomInvitation.classroom_id)
                .where(
                    ClassroomInvitation.invited_email_normalized == normalize_email(user.email),
                    ClassroomInvitation.status == InvitationStatus.PENDING,
                )
                .order_by(ClassroomInvitation.classroom_id, ClassroomInvitation.id)
            )
        ).all()
        for invitation_id, _ in ids:
            room, invitation = await self._lock_invitation(invitation_id)
            if invitation.status != InvitationStatus.PENDING or invitation.invited_user_id not in {
                None,
                user.id,
            }:
                continue
            invitation.invited_user_id = user.id
            await self._invited_notification(invitation, room)
        await self.session.flush()
