import asyncio

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from teacher_helpers import make_user, make_version

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import Notification, User
from app.models import Test as ContentTest
from app.models import TestVersion as Version
from app.models import TestVersionModeration as Moderation
from app.models.enums import ModerationScope, ModerationStatus, UserRole, VersionStatus
from app.services.content_governance import ContentGovernanceService


async def test_two_independent_approval_transactions_publish_once():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    teacher = admin = None
    test_id = None
    try:
        async with factory() as session:
            teacher = await make_user(session, UserRole.TEACHER)
            admin = await make_user(session, UserRole.ADMIN)
            test, version = await make_version(session, teacher)
            test_id, version_id = test.id, version.id
            request = await ContentGovernanceService(session, teacher).submit_moderation(
                version_id, ModerationScope.PUBLIC, None
            )

        async def approve():
            async with factory() as session:
                try:
                    return await ContentGovernanceService(session, admin).approve(request.id, None)
                except AppError as error:
                    return error

        results = await asyncio.gather(approve(), approve())
        assert sum(isinstance(result, AppError) for result in results) == 1
        assert (
            next(result for result in results if isinstance(result, AppError)).code
            == "MODERATION_ALREADY_RESOLVED"
        )
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count(Version.id)).where(
                        Version.test_id == test_id, Version.status == VersionStatus.PUBLISHED
                    )
                )
                == 1
            )
            assert (await session.get(Moderation, request.id)).status == ModerationStatus.APPROVED
            assert (
                await session.scalar(
                    select(func.count(Notification.id)).where(Notification.user_id == teacher.id)
                )
                == 1
            )
    finally:
        async with factory() as session, session.begin():
            if teacher:
                await session.execute(
                    delete(Notification).where(Notification.user_id == teacher.id)
                )
                await session.execute(
                    delete(Moderation).where(Moderation.submitted_by_user_id == teacher.id)
                )
            if test_id:
                await session.execute(delete(ContentTest).where(ContentTest.id == test_id))
            ids = [user.id for user in [teacher, admin] if user]
            if ids:
                await session.execute(delete(User).where(User.id.in_(ids)))
        await engine.dispose()
