import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.main import app
from app.models import Attempt, User
from app.models import TestSession as FullMockSession
from app.models.enums import (
    AttemptStatus,
    FinishedReason,
    ModuleType,
    TimerMode,
    UserRole,
)
from app.models.enums import (
    TestSessionStatus as SessionStatus,
)

SECRET = "targeted-test-secret-value-with-32-characters"


@pytest_asyncio.fixture
async def client(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    get_settings.cache_clear()

    async def override_session():
        yield db_session
        if db_session.in_transaction():
            await db_session.rollback()

    app.dependency_overrides[get_session] = override_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as value:
        yield value
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def current_user(role: UserRole, email: str) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email=email,
        display_name=email.split("@")[0],
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_user_is_forbidden_from_admin_and_builder_apis(client) -> None:
    user = current_user(UserRole.USER, "ordinary@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    assert (await client.get("/api/v1/admin/users")).status_code == 403
    assert (
        await client.get("/api/v1/test-versions/00000000-0000-4000-8000-000000000001/builder")
    ).status_code == 403
    assert (await client.post("/api/v1/tests", json={"title": "Forbidden"})).status_code == 403
    assert (
        await client.patch(f"/api/v1/admin/users/{user.id}", json={"role": "ADMIN"})
    ).status_code == 403
    assert (
        await client.patch(
            "/api/v1/admin/users/00000000-0000-4000-8000-000000000002",
            json={"role": "ADMIN"},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_admin_can_access_admin_and_builder_boundaries_without_secret_fields(
    client, db_session, caplog
) -> None:
    admin = current_user(UserRole.ADMIN, "admin@example.com")
    async with db_session.begin():
        db_session.add(
            User(
                id=admin.id,
                email=admin.email,
                display_name=admin.display_name,
                role=UserRole.ADMIN,
                is_active=True,
                email_verified=True,
            )
        )
    app.dependency_overrides[get_current_user] = lambda: admin
    caplog.set_level(logging.INFO, logger="app.services.admin")

    users = await client.get("/api/v1/admin/users")
    assert users.status_code == 200
    serialized = str(users.json()).lower()
    assert "password_hash" not in serialized
    assert "refresh" not in serialized
    assert "token" not in serialized

    stats = await client.get("/api/v1/admin/stats")
    assert stats.status_code == 200
    assert stats.json()["total_users"] >= 1

    created = await client.post("/api/v1/tests", json={"title": "Admin-created test"})
    assert created.status_code == 201
    version_id = created.json()["versions"][0]["id"]
    builder = await client.get(f"/api/v1/test-versions/{version_id}/builder")
    assert builder.status_code == 200

    baseline = stats.json()
    now = datetime.now(UTC)
    learner = User(
        email="learner@example.com",
        display_name="Learner",
        role=UserRole.USER,
        is_active=True,
    )
    inactive = User(
        email="inactive@example.com",
        display_name="Inactive",
        role=UserRole.USER,
        is_active=False,
    )
    async with db_session.begin():
        db_session.add_all((learner, inactive))
        await db_session.flush()
        learner_id = learner.id
        db_session.add_all(
            (
                Attempt(
                    user_id=learner.id,
                    test_version_id=UUID(version_id),
                    module_type=ModuleType.READING,
                    timer_mode=TimerMode.COUNT_UP,
                    started_at=now,
                    last_active_at=now,
                    finished_at=now,
                    elapsed_seconds=60,
                    status=AttemptStatus.SUBMITTED,
                    finished_reason=FinishedReason.USER_SUBMIT,
                ),
                Attempt(
                    user_id=learner.id,
                    test_version_id=UUID(version_id),
                    module_type=ModuleType.LISTENING,
                    timer_mode=TimerMode.COUNT_UP,
                    started_at=now,
                    last_active_at=now,
                    status=AttemptStatus.IN_PROGRESS,
                ),
                FullMockSession(
                    user_id=learner.id,
                    test_version_id=UUID(version_id),
                    status=SessionStatus.COMPLETED,
                    started_at=now,
                    finished_at=now,
                ),
            )
        )

    updated = (await client.get("/api/v1/admin/stats")).json()
    assert updated["total_users"] == baseline["total_users"] + 2
    assert updated["total_attempts"] == baseline["total_attempts"] + 2
    assert updated["active_attempts"] == baseline["active_attempts"] + 1
    assert updated["completed_attempts"] == baseline["completed_attempts"] + 1
    assert updated["completed_full_mocks"] == baseline["completed_full_mocks"] + 1

    searched = await client.get("/api/v1/admin/users", params={"search": "learner"})
    assert searched.status_code == 200
    assert [item["email"] for item in searched.json()["items"]] == ["learner@example.com"]
    detail = await client.get(f"/api/v1/admin/users/{learner_id}")
    assert detail.status_code == 200
    assert detail.json()["history"]["total"] == 2
    assert detail.json()["analytics"]["total_finalized_attempts"] == 1
    sensitive = str(detail.json()).lower()
    assert "password_hash" not in sensitive
    assert "token" not in sensitive

    promoted = await client.patch(f"/api/v1/admin/users/{learner_id}", json={"role": "ADMIN"})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "ADMIN"
    demoted = await client.patch(f"/api/v1/admin/users/{learner_id}", json={"role": "USER"})
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "USER"
    assert any(
        "admin_user_updated" in record.message
        and str(learner_id) in record.message
        and "password" not in record.message.lower()
        and "token" not in record.message.lower()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_demoted_or_deactivated(client, db_session) -> None:
    actor = current_user(UserRole.ADMIN, "actor@example.com")
    app.dependency_overrides[get_current_user] = lambda: actor
    async with db_session.begin():
        existing_admins = list(
            await db_session.scalars(
                select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
            )
        )
        for existing in existing_admins:
            existing.role = UserRole.USER
        last_admin = User(
            email="last-admin@example.com",
            display_name="Last Admin",
            role=UserRole.ADMIN,
            is_active=True,
            email_verified=True,
        )
        db_session.add(last_admin)
        await db_session.flush()
        last_admin_id = last_admin.id

    demotion = await client.patch(f"/api/v1/admin/users/{last_admin_id}", json={"role": "USER"})
    assert demotion.status_code == 409
    assert demotion.json()["code"] == "LAST_ACTIVE_ADMIN"
    deactivation = await client.patch(
        f"/api/v1/admin/users/{last_admin_id}", json={"is_active": False}
    )
    assert deactivation.status_code == 409
    assert deactivation.json()["code"] == "LAST_ACTIVE_ADMIN"
