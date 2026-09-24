"""A refresh token can create at most one successor across database connections."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models import RefreshSession, User
from app.models.enums import UserRole
from app.services.auth import AuthService


@pytest.mark.integration
async def test_concurrent_refresh_rotates_once(monkeypatch: pytest.MonkeyPatch) -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
    if "test" not in (make_url(url).database or "").lower():
        raise RuntimeError("TEST_DATABASE_URL must name a test database")

    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        database_url=url, jwt_secret="targeted-test-secret-value-with-32-characters"
    )
    user_id = None
    try:
        async with factory() as setup:
            async with setup.begin():
                user = User(
                    email=f"refresh-race-{uuid4()}@example.com",
                    display_name="Fictional learner",
                    role=UserRole.USER,
                    is_active=True,
                    email_verified=False,
                )
                setup.add(user)
                await setup.flush()
            user_id = user.id
            issued = await AuthService(setup, settings).issue_session(user)

        first_locked = asyncio.Event()
        second_waiting = asyncio.Event()
        release_first = asyncio.Event()
        async with factory() as first_session, factory() as second_session:
            first_scalar = first_session.scalar
            second_scalar = second_session.scalar

            async def hold_first(statement, *args, **kwargs):
                result = await first_scalar(statement, *args, **kwargs)
                if getattr(statement, "_for_update_arg", None) is not None:
                    first_locked.set()
                    await release_first.wait()
                return result

            async def observe_second(statement, *args, **kwargs):
                if getattr(statement, "_for_update_arg", None) is not None:
                    second_waiting.set()
                return await second_scalar(statement, *args, **kwargs)

            monkeypatch.setattr(first_session, "scalar", hold_first)
            monkeypatch.setattr(second_session, "scalar", observe_second)
            first_task = asyncio.create_task(
                AuthService(first_session, settings).rotate_refresh_token(issued.refresh_token)
            )
            second_task = None
            try:
                await asyncio.wait_for(first_locked.wait(), 10)
                second_task = asyncio.create_task(
                    AuthService(second_session, settings).rotate_refresh_token(issued.refresh_token)
                )
                await asyncio.wait_for(second_waiting.wait(), 10)
                assert not second_task.done()
                release_first.set()
                _, successor = await asyncio.wait_for(first_task, 10)
                assert successor.refresh_token != issued.refresh_token
                with pytest.raises(AppError) as losing:
                    await asyncio.wait_for(second_task, 10)
                assert (losing.value.code, losing.value.status_code) == (
                    "INVALID_REFRESH_TOKEN",
                    401,
                )
            finally:
                release_first.set()
                for task in (first_task, second_task):
                    if task is not None and not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

        async with factory() as verify:
            rows = list(
                await verify.scalars(
                    select(RefreshSession).where(RefreshSession.user_id == user_id)
                )
            )
            assert len(rows) == 2
            assert sum(row.revoked_at is not None for row in rows) == 1
            assert sum(row.revoked_at is None for row in rows) == 1
    finally:
        if user_id is not None:
            async with factory() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(delete(User).where(User.id == user_id))
        await engine.dispose()
