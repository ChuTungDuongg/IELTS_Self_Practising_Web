from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.main import app
from app.models import Attempt, TestSession, User
from app.models.enums import UserRole


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    test_engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with session_factory() as session:
            default_user = User(
                email=f"default-{uuid4()}@example.com",
                display_name="Default Test Administrator",
                role=UserRole.ADMIN,
                is_active=True,
                email_verified=True,
            )
            async with session.begin():
                session.add(default_user)
                await session.flush()
            session.info["current_user_id"] = default_user.id
            now = datetime.now(UTC)
            session.info["current_user_identity"] = User(
                id=default_user.id,
                email=default_user.email,
                display_name=default_user.display_name,
                role=UserRole.ADMIN,
                is_active=True,
                email_verified=True,
                created_at=now,
                updated_at=now,
            )

            @event.listens_for(session.sync_session, "before_flush")
            def assign_default_owner(sync_session, _flush_context, _instances):
                for instance in sync_session.new:
                    if isinstance(instance, (Attempt, TestSession)) and instance.user_id is None:
                        instance.user_id = default_user.id

            yield session
        await transaction.rollback()
    await test_engine.dispose()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"test-{uuid4()}@example.com",
        display_name="Test User",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
    )
    async with db_session.begin():
        db_session.add(user)
        await db_session.flush()
    return user


@pytest_asyncio.fixture
async def authenticated_admin(db_session: AsyncSession) -> AsyncIterator[User]:
    identity = db_session.info["current_user_identity"]
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: identity
    try:
        yield identity
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
