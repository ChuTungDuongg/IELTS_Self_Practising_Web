import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.main import app
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    AttemptWritingResponse,
    AttemptWritingScore,
    Highlight,
    OAuthAccount,
    Question,
    QuestionFlag,
    QuestionGroup,
    ReadingPassage,
    RefreshSession,
    User,
    WritingTask,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestSession as FullMockSession
from app.models import TestVersion as DomainVersion
from app.models.enums import (
    AttemptStatus,
    EventType,
    FinishedReason,
    ModuleType,
    OAuthProvider,
    TimerMode,
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
    assert (await client.delete(f"/api/v1/admin/users/{user.id}")).status_code == 403


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
        city="Fictional City",
        target_band=7.5,
        bio="Optional profile note",
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
    assert detail.json()["user"]["city"] == "Fictional City"
    assert detail.json()["user"]["target_band"] in ("7.5", 7.5)
    assert detail.json()["user"]["bio"] == "Optional profile note"
    assert "has_password" not in detail.json()["user"]
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


@pytest.mark.asyncio
async def test_user_list_filters_active_state_with_search_and_pagination(client, db_session) -> None:
    admin = current_user(UserRole.ADMIN, "filter-admin@example.com")
    app.dependency_overrides[get_current_user] = lambda: admin
    async with db_session.begin():
        db_session.add_all(
            [
                User(email="match-active@example.com", display_name="Match", is_active=True),
                User(email="match-inactive-a@example.com", display_name="Match", is_active=False),
                User(email="match-inactive-b@example.com", display_name="Match", is_active=False),
            ]
        )

    response = await client.get(
        "/api/v1/admin/users",
        params={"search": "MATCH-", "is_active": "false", "offset": 1, "limit": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["offset"] == 1
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["is_active"] is False
    assert payload["items"][0]["email"] in {
        "match-inactive-a@example.com",
        "match-inactive-b@example.com",
    }

    active = await client.get(
        "/api/v1/admin/users", params={"search": "MATCH-", "is_active": "true"}
    )
    assert active.status_code == 200
    assert active.json()["total"] == 1
    assert [item["email"] for item in active.json()["items"]] == ["match-active@example.com"]


@pytest.mark.asyncio
async def test_delete_user_rejects_missing_active_and_self(client, db_session) -> None:
    actor = db_session.info["current_user_identity"]
    app.dependency_overrides[get_current_user] = lambda: actor
    async with db_session.begin():
        active_user = User(
            email="delete-active@example.com", display_name="Active", is_active=True
        )
        db_session.add(active_user)
        await db_session.flush()
        active_user_id = active_user.id

    missing = await client.delete(f"/api/v1/admin/users/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "USER_NOT_FOUND"

    active = await client.delete(f"/api/v1/admin/users/{active_user_id}")
    assert active.status_code == 409
    assert active.json()["code"] == "USER_DELETE_REQUIRES_DEACTIVATION"

    self_delete = await client.delete(f"/api/v1/admin/users/{actor.id}")
    assert self_delete.status_code == 409
    assert self_delete.json()["code"] == "CANNOT_DELETE_SELF"
    assert await db_session.get(User, active_user_id) is not None
    assert await db_session.get(User, actor.id) is not None


@pytest.mark.asyncio
async def test_delete_inactive_user_without_history_updates_admin_stats(client, db_session) -> None:
    actor = db_session.info["current_user_identity"]
    app.dependency_overrides[get_current_user] = lambda: actor
    async with db_session.begin():
        target = User(
            email="delete-no-history@example.com", display_name="No History", is_active=False
        )
        db_session.add(target)
        await db_session.flush()
        target_id = target.id

    before = (await client.get("/api/v1/admin/stats")).json()
    response = await client.delete(f"/api/v1/admin/users/{target_id}")
    after = (await client.get("/api/v1/admin/stats")).json()

    assert response.status_code == 204
    assert await db_session.get(User, target_id) is None
    assert after["total_users"] == before["total_users"] - 1
    assert after["active_users"] == before["active_users"]


@pytest.mark.asyncio
async def test_delete_inactive_user_removes_owned_records_and_preserves_test_content(
    client, db_session, caplog
) -> None:
    actor = db_session.info["current_user_identity"]
    app.dependency_overrides[get_current_user] = lambda: actor
    caplog.set_level(logging.INFO, logger="app.services.admin")
    now = datetime.now(UTC)
    async with db_session.begin():
        target = User(
            email="delete-target@example.com", display_name="Target", is_active=False
        )
        survivor = User(
            email="delete-survivor@example.com", display_name="Survivor", is_active=True
        )
        test = DomainTest(title="Fictional retained test")
        version = DomainVersion(
            version_number=1, status=VersionStatus.PUBLISHED, published_at=now
        )
        test.versions.append(version)
        reading_module = DomainModule(module_type=ModuleType.READING, order_index=0)
        writing_module = DomainModule(module_type=ModuleType.WRITING, order_index=1)
        passage = ReadingPassage(
            title="Fictional passage",
            order_index=0,
            content_json=[{"id": str(uuid4()), "type": "paragraph", "text": "Sample text."}],
            plain_text="Sample text.",
        )
        group = QuestionGroup(
            question_type="short_answer", instruction="Answer briefly.", config={}, order_index=0
        )
        question = Question(
            number=1,
            prompt="Fictional question",
            config={},
            answer_key={"kind": "TEXT", "accepted": ["sample"]},
            order_index=0,
        )
        writing_task = WritingTask(
            task_number=1, prompt="Write about a fictional topic.", order_index=0
        )
        version.modules.extend([reading_module, writing_module])
        reading_module.passages.append(passage)
        reading_module.question_groups.append(group)
        group.passage = passage
        group.questions.append(question)
        writing_module.writing_tasks.append(writing_task)
        db_session.add_all([target, survivor, test])
        await db_session.flush()
        target_id, survivor_id, test_id, version_id = (
            target.id,
            survivor.id,
            test.id,
            version.id,
        )
        full_session = FullMockSession(
            user_id=target_id,
            test_version_id=version_id,
            status=SessionStatus.COMPLETED,
            started_at=now,
            finished_at=now,
        )
        db_session.add(full_session)
        await db_session.flush()
        target_attempt = Attempt(
            user_id=target_id,
            test_version_id=version_id,
            test_session_id=full_session.id,
            module_type=ModuleType.READING,
            timer_mode=TimerMode.COUNT_UP,
            started_at=now,
            last_active_at=now,
            status=AttemptStatus.SUBMITTED,
        )
        survivor_attempt = Attempt(
            user_id=survivor_id,
            test_version_id=version_id,
            module_type=ModuleType.READING,
            timer_mode=TimerMode.COUNT_UP,
            started_at=now,
            last_active_at=now,
            status=AttemptStatus.IN_PROGRESS,
        )
        db_session.add_all([target_attempt, survivor_attempt])
        await db_session.flush()
        attempt_id, survivor_attempt_id, session_id = (
            target_attempt.id,
            survivor_attempt.id,
            full_session.id,
        )
        db_session.add_all(
            [
                AttemptAnswer(
                    attempt_id=attempt_id,
                    question_id=question.id,
                    value="sample",
                    is_correct=True,
                ),
                AttemptWritingResponse(
                    attempt_id=attempt_id,
                    writing_task_id=writing_task.id,
                    content="Fictional response.",
                    word_count=2,
                ),
                AttemptWritingScore(
                    attempt_id=attempt_id,
                    writing_task_id=writing_task.id,
                    ta=Decimal("7.0"),
                    cc=Decimal("7.0"),
                    lr=Decimal("7.0"),
                    gra=Decimal("7.0"),
                ),
                QuestionFlag(attempt_id=attempt_id, question_id=question.id, flagged=True),
                Highlight(
                    attempt_id=attempt_id,
                    target_kind="PASSAGE",
                    target_id=passage.id,
                    passage_id=passage.id,
                    start_offset=0,
                    end_offset=6,
                    selected_text="Sample",
                ),
                AttemptEvent(
                    attempt_id=attempt_id,
                    event_type=EventType.SUBMITTED,
                    event_metadata={},
                ),
                OAuthAccount(
                    user_id=target_id,
                    provider=OAuthProvider.GOOGLE,
                    provider_subject="fictional-subject",
                ),
                RefreshSession(
                    user_id=target_id,
                    token_hash="f" * 64,
                    expires_at=now + timedelta(days=1),
                ),
            ]
        )

    response = await client.delete(f"/api/v1/admin/users/{target_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert await db_session.get(User, target_id) is None
    assert await db_session.get(Attempt, attempt_id) is None
    assert await db_session.get(FullMockSession, session_id) is None
    assert await db_session.get(User, survivor_id) is not None
    assert await db_session.get(Attempt, survivor_attempt_id) is not None
    assert await db_session.get(DomainTest, test_id) is not None
    assert await db_session.get(DomainVersion, version_id) is not None
    assert await db_session.get(Question, question.id) is not None
    assert await db_session.get(WritingTask, writing_task.id) is not None
    for model in (
        AttemptAnswer,
        AttemptWritingResponse,
        AttemptWritingScore,
        QuestionFlag,
        Highlight,
        AttemptEvent,
    ):
        assert await db_session.scalar(
            select(func.count()).select_from(model).where(model.attempt_id == attempt_id)
        ) == 0
    for model in (OAuthAccount, RefreshSession):
        assert await db_session.scalar(
            select(func.count()).select_from(model).where(model.user_id == target_id)
        ) == 0
    audit_records = [record.message for record in caplog.records if "admin_user_deleted" in record.message]
    assert len(audit_records) == 1
    assert str(actor.id) in audit_records[0]
    assert str(target_id) in audit_records[0]
    assert "attempts=1" in audit_records[0]
    assert "test_sessions=1" in audit_records[0]
    assert "oauth_accounts=1" in audit_records[0]
    assert "refresh_sessions=1" in audit_records[0]
    assert "fictional-subject" not in audit_records[0]
    assert "f" * 64 not in audit_records[0]
