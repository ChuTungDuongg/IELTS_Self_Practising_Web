import logging
import uuid

from sqlalchemy import delete, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Attempt, OAuthAccount, RefreshSession, TestSession, User
from app.models.enums import AttemptStatus, ModuleType, TestSessionStatus, UserRole
from app.schemas.admin import (
    AdminStats,
    AdminUserDetail,
    AdminUserList,
    AdminUserListItem,
    AdminUserUpdate,
)
from app.schemas.auth import UserResponse
from app.services.analytics import AnalyticsService
from app.services.attempts import AttemptService

ACTIVE_ATTEMPT_STATUSES = {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}
COMPLETED_ATTEMPT_STATUSES = {AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED}
logger = logging.getLogger(__name__)


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def stats(self) -> AdminStats:
        total_users = int(await self.session.scalar(select(func.count(User.id))) or 0)
        active_users = int(
            await self.session.scalar(select(func.count(User.id)).where(User.is_active.is_(True)))
            or 0
        )
        users_with_attempts = int(
            await self.session.scalar(select(func.count(distinct(Attempt.user_id)))) or 0
        )
        total_attempts = int(await self.session.scalar(select(func.count(Attempt.id))) or 0)
        active_attempts = int(
            await self.session.scalar(
                select(func.count(Attempt.id)).where(Attempt.status.in_(ACTIVE_ATTEMPT_STATUSES))
            )
            or 0
        )
        completed_attempts = int(
            await self.session.scalar(
                select(func.count(Attempt.id)).where(Attempt.status.in_(COMPLETED_ATTEMPT_STATUSES))
            )
            or 0
        )
        skill_rows = (
            await self.session.execute(
                select(Attempt.module_type, func.count(Attempt.id)).group_by(Attempt.module_type)
            )
        ).all()
        completed_full_mocks = int(
            await self.session.scalar(
                select(func.count(TestSession.id)).where(
                    TestSession.status == TestSessionStatus.COMPLETED
                )
            )
            or 0
        )
        by_skill = {module: 0 for module in ModuleType}
        by_skill.update({module: int(count) for module, count in skill_rows})
        return AdminStats(
            total_users=total_users,
            active_users=active_users,
            users_with_attempts=users_with_attempts,
            total_attempts=total_attempts,
            active_attempts=active_attempts,
            completed_attempts=completed_attempts,
            completed_full_mocks=completed_full_mocks,
            attempts_by_skill=by_skill,
        )

    async def users(
        self, *, search: str | None, is_active: bool | None, offset: int, limit: int
    ) -> AdminUserList:
        normalized = search.strip().casefold() if search else None
        filters = []
        if normalized:
            pattern = f"%{normalized}%"
            filters.append(
                or_(
                    func.lower(User.email).like(pattern),
                    func.lower(User.display_name).like(pattern),
                )
            )
        if is_active is not None:
            filters.append(User.is_active.is_(is_active))
        count_statement = select(func.count(User.id))
        if filters:
            count_statement = count_statement.where(*filters)
        total = int(await self.session.scalar(count_statement) or 0)
        statement = (
            select(
                User,
                func.count(Attempt.id).label("attempt_count"),
                func.max(Attempt.last_active_at).label("last_activity_at"),
            )
            .outerjoin(Attempt, Attempt.user_id == User.id)
            .group_by(User.id)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if filters:
            statement = statement.where(*filters)
        rows = (await self.session.execute(statement)).all()
        return AdminUserList(
            items=[
                AdminUserListItem(
                    id=user.id,
                    email=user.email,
                    display_name=user.display_name,
                    role=user.role,
                    is_active=user.is_active,
                    created_at=user.created_at,
                    last_login_at=user.last_login_at,
                    attempt_count=int(attempt_count),
                    last_activity_at=last_activity_at,
                )
                for user, attempt_count, last_activity_at in rows
            ],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def user_detail(self, user_id: uuid.UUID) -> AdminUserDetail:
        user = await self.session.get(User, user_id)
        if user is None:
            raise AppError("USER_NOT_FOUND", "The requested user does not exist.", 404)
        return AdminUserDetail(
            user=UserResponse.model_validate(user),
            history=await AttemptService(self.session, user.id).history(),
            analytics=await AnalyticsService(self.session, user.id).dashboard(),
        )

    async def update_user(
        self, actor_id: uuid.UUID, user_id: uuid.UUID, data: AdminUserUpdate
    ) -> UserResponse:
        async with self.session.begin():
            active_admin_ids = list(
                await self.session.scalars(
                    select(User.id)
                    .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
                    .order_by(User.id)
                    .with_for_update()
                )
            )
            user = await self.session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None:
                raise AppError("USER_NOT_FOUND", "The requested user does not exist.", 404)

            next_role = data.role if data.role is not None else user.role
            next_active = data.is_active if data.is_active is not None else user.is_active
            removes_active_admin = (
                user.role == UserRole.ADMIN
                and user.is_active
                and (next_role != UserRole.ADMIN or not next_active)
            )
            if removes_active_admin:
                if len(active_admin_ids) <= 1:
                    raise AppError(
                        "LAST_ACTIVE_ADMIN",
                        "The last active administrator cannot be demoted or deactivated.",
                        409,
                    )

            previous_role = user.role
            previous_active = user.is_active
            user.role = next_role
            user.is_active = next_active
            await self.session.flush()
            await self.session.refresh(user)
            response = UserResponse.model_validate(user)

        logger.info(
            "admin_user_updated actor_id=%s target_id=%s role=%s->%s active=%s->%s",
            actor_id,
            user_id,
            previous_role.value,
            next_role.value,
            previous_active,
            next_active,
        )
        return response

    async def delete_user(self, actor_id: uuid.UUID, user_id: uuid.UUID) -> None:
        async with self.session.begin():
            user = await self.session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None:
                raise AppError("USER_NOT_FOUND", "The requested user does not exist.", 404)
            if user.id == actor_id:
                raise AppError("CANNOT_DELETE_SELF", "You cannot delete your own account.", 409)
            if user.is_active:
                raise AppError(
                    "USER_DELETE_REQUIRES_DEACTIVATION",
                    "Deactivate this user before deleting the account.",
                    409,
                )

            oauth_count = int(
                await self.session.scalar(
                    select(func.count(OAuthAccount.id)).where(OAuthAccount.user_id == user_id)
                )
                or 0
            )
            refresh_count = int(
                await self.session.scalar(
                    select(func.count(RefreshSession.id)).where(RefreshSession.user_id == user_id)
                )
                or 0
            )
            attempts = await self.session.execute(
                delete(Attempt).where(Attempt.user_id == user_id).returning(Attempt.id)
            )
            attempt_count = len(attempts.scalars().all())
            test_sessions = await self.session.execute(
                delete(TestSession).where(TestSession.user_id == user_id).returning(TestSession.id)
            )
            test_session_count = len(test_sessions.scalars().all())
            await self.session.delete(user)
            await self.session.flush()

        logger.info(
            "admin_user_deleted actor_id=%s target_id=%s attempts=%s test_sessions=%s "
            "oauth_accounts=%s refresh_sessions=%s",
            actor_id,
            user_id,
            attempt_count,
            test_session_count,
            oauth_count,
            refresh_count,
        )
