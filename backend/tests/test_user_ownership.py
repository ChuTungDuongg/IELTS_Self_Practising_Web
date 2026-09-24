from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.main import app
from app.models import (
    Test as IeltsTest,
)
from app.models import (
    TestModule as IeltsModule,
)
from app.models import (
    TestSession as FullMockSession,
)
from app.models import (
    TestVersion as VersionRecord,
)
from app.models import (
    User,
)
from app.models.enums import (
    ModuleType,
    UserRole,
    VersionStatus,
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


@pytest.mark.asyncio
async def test_attempt_history_analytics_and_session_access_are_user_scoped(
    client, db_session
) -> None:
    async with db_session.begin():
        owner = User(
            email="owner@example.com",
            display_name="Owner",
            role=UserRole.USER,
            is_active=True,
        )
        other = User(
            email="other@example.com",
            display_name="Other",
            role=UserRole.USER,
            is_active=True,
        )
        test = IeltsTest(title="Owner's test")
        version = VersionRecord(
            version_number=1,
            status=VersionStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        version.modules.append(
            IeltsModule(module_type=ModuleType.READING, title="Reading", order_index=0)
        )
        test.versions.append(version)
        other_test = IeltsTest(title="Other user's test")
        other_version = VersionRecord(
            version_number=1,
            status=VersionStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        other_test.versions.append(other_version)
        db_session.add_all((owner, other, test, other_test))
        await db_session.flush()
        owner_id = owner.id
        other_id = other.id
        version_id = version.id
        test_session = FullMockSession(
            user_id=owner.id,
            test_version_id=version_id,
            status=SessionStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
        )
        other_session = FullMockSession(
            user_id=other.id,
            test_version_id=other_version.id,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        db_session.add_all((test_session, other_session))
        await db_session.flush()
        session_id = test_session.id
        other_session_id = other_session.id

    owner_identity = User(
        id=owner_id,
        email="owner@example.com",
        display_name="Owner",
        role=UserRole.USER,
        is_active=True,
    )
    other_identity = User(
        id=other_id,
        email="other@example.com",
        display_name="Other",
        role=UserRole.USER,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: owner_identity
    started = await client.post(
        "/api/v1/attempts",
        json={
            "test_version_id": str(version_id),
            "module": "READING",
            "timer": {"mode": "COUNT_UP"},
        },
    )
    assert started.status_code == 201
    attempt_id = started.json()["attempt_id"]
    owner_history = await client.get("/api/v1/history")
    assert owner_history.status_code == 200
    assert [item["attempt_id"] for item in owner_history.json()["items"]] == [attempt_id]
    assert [item["session_id"] for item in owner_history.json()["sessions"]] == [str(session_id)]
    assert owner_history.json()["sessions"][0]["test_title"] == "Owner's test"
    assert owner_history.json()["sessions"][0]["status"] == "IN_PROGRESS"
    assert str(other_session_id) not in str(owner_history.json())
    assert "Other user's test" not in str(owner_history.json())

    app.dependency_overrides[get_current_user] = lambda: other_identity
    assert (await client.get(f"/api/v1/attempts/{attempt_id}")).status_code == 404
    assert (await client.get(f"/api/v1/test-sessions/{session_id}")).status_code == 404
    other_history = await client.get("/api/v1/history")
    assert other_history.status_code == 200
    assert other_history.json()["items"] == []
    assert [item["session_id"] for item in other_history.json()["sessions"]] == [
        str(other_session_id)
    ]
    assert other_history.json()["sessions"][0]["test_title"] == "Other user's test"
    assert other_history.json()["sessions"][0]["status"] == "COMPLETED"
    assert str(session_id) not in str(other_history.json())
    assert "Owner's test" not in str(other_history.json())
    other_analytics = await client.get("/api/v1/analytics")
    assert other_analytics.status_code == 200
    assert other_analytics.json()["attempts"] == []
