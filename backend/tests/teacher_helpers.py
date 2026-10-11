from contextlib import asynccontextmanager
from uuid import uuid4

import httpx

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import Test as TestModel
from app.models import TestModule as ModuleModel
from app.models import TestVersion as VersionModel
from app.models import User, WritingTask
from app.models.enums import ModuleType, TestOrigin, UserRole, VersionStatus


async def make_user(session, role=UserRole.USER):
    async with session.begin():
        user = User(
            email=f"fictional-{uuid4()}@example.com",
            display_name="Fictional learner",
            role=role,
            is_active=True,
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        session.expunge(user)
    return user


async def make_version(session, owner, *, status=VersionStatus.DRAFT, origin=TestOrigin.TEACHER):
    async with session.begin():
        test = TestModel(title="Fictional classroom content", owner_user_id=owner.id, origin=origin)
        version = VersionModel(version_number=1, status=status)
        test.versions.append(version)
        module = ModuleModel(
            module_type=ModuleType.WRITING, order_index=0, recommended_duration_seconds=3600
        )
        version.modules.append(module)
        module.writing_tasks.append(
            WritingTask(
                task_number=2,
                order_index=1,
                task_type="DISCUSS_BOTH_VIEWS_AND_OPINION",
                prompt="Discuss fictional learning approaches.",
                minimum_recommended_words=250,
                recommended_duration_seconds=2400,
            )
        )
        session.add(test)
        await session.flush()
    return test, version


@asynccontextmanager
async def api_client(session, actor):
    previous = app.dependency_overrides.copy()

    async def override_session():
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
