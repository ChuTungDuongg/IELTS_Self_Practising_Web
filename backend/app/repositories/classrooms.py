from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Classroom, ClassroomInvitation, ClassroomMembership, User
from app.models.enums import UserRole


class ClassroomRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def classroom(self, classroom_id: UUID, *, lock: bool = False, read_lock: bool = False):
        query = select(Classroom).where(Classroom.id == classroom_id)
        if lock or read_lock:
            query = query.execution_options(populate_existing=True).with_for_update(read=read_lock)
        return await self.session.scalar(query)

    async def list(self, actor: User):
        query = select(Classroom)
        if actor.role != UserRole.ADMIN:
            member_ids = select(ClassroomMembership.classroom_id).where(
                ClassroomMembership.user_id == actor.id
            )
            query = query.where(or_(Classroom.teacher_id == actor.id, Classroom.id.in_(member_ids)))
        return list(
            await self.session.scalars(query.order_by(Classroom.created_at.desc(), Classroom.id))
        )

    async def membership(self, classroom_id: UUID, user_id: UUID, *, active: bool = True):
        query = select(ClassroomMembership).where(
            ClassroomMembership.classroom_id == classroom_id,
            ClassroomMembership.user_id == user_id,
        )
        if active:
            query = query.where(ClassroomMembership.left_at.is_(None))
        return await self.session.scalar(
            query.order_by(ClassroomMembership.joined_at.desc()).limit(1)
        )

    async def members(self, classroom_id: UUID):
        return (
            await self.session.execute(
                select(ClassroomMembership, User)
                .join(User, User.id == ClassroomMembership.user_id)
                .where(ClassroomMembership.classroom_id == classroom_id)
                .order_by(ClassroomMembership.joined_at, ClassroomMembership.id)
            )
        ).all()

    async def invitation(self, invitation_id: UUID, *, lock: bool = False):
        query = select(ClassroomInvitation).where(ClassroomInvitation.id == invitation_id)
        if lock:
            query = query.execution_options(populate_existing=True).with_for_update()
        return await self.session.scalar(query)

    async def invitations(self, classroom_id: UUID):
        return list(
            await self.session.scalars(
                select(ClassroomInvitation)
                .where(ClassroomInvitation.classroom_id == classroom_id)
                .order_by(ClassroomInvitation.created_at.desc(), ClassroomInvitation.id)
            )
        )

    async def my_invitations(self, user: User, normalized_email: str):
        return list(
            await self.session.scalars(
                select(ClassroomInvitation)
                .where(
                    ClassroomInvitation.invited_email_normalized == normalized_email,
                    or_(
                        ClassroomInvitation.invited_user_id.is_(None),
                        ClassroomInvitation.invited_user_id == user.id,
                    ),
                )
                .order_by(ClassroomInvitation.created_at.desc(), ClassroomInvitation.id)
            )
        )
