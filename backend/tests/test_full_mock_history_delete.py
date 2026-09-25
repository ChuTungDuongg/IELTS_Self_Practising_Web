from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AppError
from app.main import app
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    AttemptWritingResponse,
    AttemptWritingScore,
    Highlight,
    Question,
    QuestionFlag,
    QuestionGroup,
    WritingTask,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestSession as DomainSession
from app.models import TestVersion as DomainVersion
from app.models.enums import (
    AttemptStatus,
    EventType,
    ModuleType,
    TimerMode,
    VersionStatus,
)
from app.models.enums import (
    TestSessionStatus as SessionStatus,
)
from app.services.attempts import AttemptService
from app.services.test_sessions import TestSessionService as SessionService


async def _seed_history(session: AsyncSession, other_user_id: UUID) -> dict:
    owner_id = session.info["current_user_id"]
    base = datetime.now(UTC) - timedelta(days=5)
    test = DomainTest(title="Fictional Full Mock history")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    other_version = DomainVersion(version_number=2, status=VersionStatus.ARCHIVED)
    foreign_only_version = DomainVersion(version_number=3, status=VersionStatus.ARCHIVED)
    test.versions.extend([version, other_version, foreign_only_version])
    modules = {
        kind: DomainModule(module_type=kind, order_index=index)
        for index, kind in enumerate((ModuleType.LISTENING, ModuleType.READING, ModuleType.WRITING))
    }
    version.modules.extend(modules.values())
    question = Question(
        number=1,
        prompt="Fictional question",
        config={},
        answer_key={"kind": "TEXT", "accepted": ["fixture"]},
        order_index=0,
    )
    group = QuestionGroup(
        question_type="short_answer", instruction="Answer briefly.", config={}, order_index=0
    )
    group.questions.append(question)
    modules[ModuleType.READING].question_groups.append(group)
    task = WritingTask(task_number=1, prompt="Fictional writing prompt", order_index=0)
    modules[ModuleType.WRITING].writing_tasks.append(task)

    sessions = {
        "old": DomainSession(
            test_version=version,
            user_id=owner_id,
            status=SessionStatus.COMPLETED,
            started_at=base,
            finished_at=base + timedelta(hours=3),
        ),
        "new": DomainSession(
            test_version=version,
            user_id=owner_id,
            status=SessionStatus.COMPLETED,
            started_at=base + timedelta(days=1),
            finished_at=base + timedelta(days=1, hours=3),
        ),
        "active": DomainSession(
            test_version=version,
            user_id=owner_id,
            status=SessionStatus.IN_PROGRESS,
            started_at=base + timedelta(days=2),
        ),
        "other": DomainSession(
            test_version=version,
            user_id=other_user_id,
            status=SessionStatus.COMPLETED,
            started_at=base + timedelta(days=3),
            finished_at=base + timedelta(days=3, hours=3),
        ),
    }
    attempts: dict[str, dict[ModuleType, Attempt]] = {}
    for label, test_session in sessions.items():
        attempts[label] = {}
        kinds = (
            (ModuleType.LISTENING,)
            if label == "active"
            else (
                ModuleType.LISTENING,
                ModuleType.READING,
                ModuleType.WRITING,
            )
        )
        for index, kind in enumerate(kinds):
            started = test_session.started_at + timedelta(hours=index)
            active = label == "active"
            score = None if kind == ModuleType.WRITING and label == "new" else Decimal("7.0")
            attempt = Attempt(
                test_version=version,
                test_session=test_session,
                user_id=other_user_id if label == "other" else owner_id,
                module_type=kind,
                timer_mode=TimerMode.COUNT_UP,
                started_at=started,
                last_active_at=started,
                finished_at=None if active else started + timedelta(minutes=50),
                status=AttemptStatus.IN_PROGRESS if active else AttemptStatus.SUBMITTED,
                band_score=score,
            )
            attempts[label][kind] = attempt

    standalone: dict[ModuleType, Attempt] = {}
    for index, kind in enumerate((ModuleType.LISTENING, ModuleType.READING, ModuleType.WRITING)):
        started = base + timedelta(days=4, hours=index)
        standalone[kind] = Attempt(
            test_version=version,
            user_id=owner_id,
            module_type=kind,
            timer_mode=TimerMode.COUNT_UP,
            started_at=started,
            last_active_at=started,
            finished_at=started + timedelta(minutes=50),
            status=AttemptStatus.SUBMITTED,
            band_score=None if kind == ModuleType.WRITING else Decimal("9.0"),
        )
    older_reading = Attempt(
        test_version=version,
        user_id=owner_id,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=base + timedelta(days=3),
        last_active_at=base + timedelta(days=3),
        finished_at=base + timedelta(days=3, minutes=50),
        status=AttemptStatus.SUBMITTED,
        band_score=Decimal("6.0"),
    )
    other_version_attempt = Attempt(
        test_version=other_version,
        user_id=owner_id,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=base + timedelta(days=2),
        last_active_at=base + timedelta(days=2),
        finished_at=base + timedelta(days=2, minutes=50),
        status=AttemptStatus.SUBMITTED,
        band_score=Decimal("7.0"),
    )
    foreign_standalone = Attempt(
        test_version=version,
        user_id=other_user_id,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=base + timedelta(days=4),
        last_active_at=base + timedelta(days=4),
        finished_at=base + timedelta(days=4, minutes=50),
        status=AttemptStatus.SUBMITTED,
        band_score=Decimal("8.0"),
    )
    foreign_only_attempt = Attempt(
        test_version=foreign_only_version,
        user_id=other_user_id,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=base,
        last_active_at=base,
        finished_at=base + timedelta(minutes=50),
        status=AttemptStatus.SUBMITTED,
        band_score=Decimal("8.0"),
    )
    unfinished_reading = Attempt(
        test_version=version,
        user_id=owner_id,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=base + timedelta(days=5),
        last_active_at=base + timedelta(days=5),
        status=AttemptStatus.IN_PROGRESS,
    )

    async with session.begin():
        session.add_all(
            [
                test,
                *sessions.values(),
                *standalone.values(),
                older_reading,
                unfinished_reading,
                other_version_attempt,
                foreign_standalone,
                foreign_only_attempt,
            ]
        )
        await session.flush()
        reading_id = attempts["new"][ModuleType.READING].id
        writing_id = attempts["new"][ModuleType.WRITING].id
        session.add_all(
            [
                AttemptAnswer(
                    attempt_id=reading_id,
                    question_id=question.id,
                    value="fixture",
                    is_correct=True,
                ),
                Highlight(
                    attempt_id=reading_id,
                    target_kind="QUESTION",
                    target_id=question.id,
                    start_offset=0,
                    end_offset=1,
                    selected_text="F",
                ),
                QuestionFlag(attempt_id=reading_id, question_id=question.id, flagged=True),
                AttemptEvent(
                    attempt_id=reading_id,
                    event_type=EventType.ANSWER_CHANGED,
                    question_id=question.id,
                    event_metadata={},
                ),
                AttemptWritingResponse(
                    attempt_id=writing_id,
                    writing_task_id=task.id,
                    content="Fictional response.",
                    word_count=2,
                ),
                AttemptWritingScore(
                    attempt_id=attempts["old"][ModuleType.WRITING].id,
                    writing_task_id=task.id,
                    ta=Decimal("7.0"),
                    cc=Decimal("7.0"),
                    lr=Decimal("7.0"),
                    gra=Decimal("7.0"),
                ),
                AttemptAnswer(
                    attempt_id=standalone[ModuleType.READING].id,
                    question_id=question.id,
                    value="fixture",
                    is_correct=True,
                ),
                Highlight(
                    attempt_id=standalone[ModuleType.READING].id,
                    target_kind="QUESTION",
                    target_id=question.id,
                    start_offset=0,
                    end_offset=1,
                    selected_text="F",
                ),
                QuestionFlag(
                    attempt_id=standalone[ModuleType.READING].id,
                    question_id=question.id,
                    flagged=True,
                ),
                AttemptEvent(
                    attempt_id=older_reading.id,
                    event_type=EventType.ANSWER_CHANGED,
                    question_id=question.id,
                    event_metadata={},
                ),
                AttemptWritingResponse(
                    attempt_id=standalone[ModuleType.WRITING].id,
                    writing_task_id=task.id,
                    content="Fictional standalone response.",
                    word_count=3,
                ),
            ]
        )
        await session.flush()
    return {
        "test_id": test.id,
        "version_id": version.id,
        "other_version_id": other_version.id,
        "foreign_only_version_id": foreign_only_version.id,
        "question_id": question.id,
        "sessions": {label: row.id for label, row in sessions.items()},
        "attempts": {
            label: {kind: row.id for kind, row in rows.items()} for label, rows in attempts.items()
        },
        "standalone": {kind: row.id for kind, row in standalone.items()},
        "older_reading_id": older_reading.id,
        "unfinished_reading_id": unfinished_reading.id,
        "other_version_attempt_id": other_version_attempt.id,
        "foreign_standalone_id": foreign_standalone.id,
    }


async def _delete_endpoint(session: AsyncSession, session_id: UUID) -> httpx.Response:
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.delete(f"/api/v1/test-sessions/{session_id}")
    finally:
        app.dependency_overrides.pop(get_session, None)


async def _delete_standalone_endpoint(session: AsyncSession, version_id: UUID) -> httpx.Response:
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.delete(
                f"/api/v1/history/test-versions/{version_id}/standalone-attempts"
            )
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.integration
async def test_history_separates_standalone_group_from_full_mock_and_keeps_ungraded_writing(
    db_session: AsyncSession, test_user
) -> None:
    seeded = await _seed_history(db_session, test_user.id)
    history = await AttemptService(db_session).history()

    assert {row.session_id for row in history.sessions} == {
        seeded["sessions"]["old"],
        seeded["sessions"]["new"],
        seeded["sessions"]["active"],
    }
    assert {row.attempt_id for row in history.items}.issuperset(
        set(seeded["attempts"]["new"].values())
    )
    group = next(row for row in history.groups if row.test_version_id == seeded["version_id"])
    assert {row.test_version_id for row in history.groups} == {
        seeded["version_id"],
        seeded["other_version_id"],
    }
    assert {group.listening.attempt_id, group.reading.attempt_id, group.writing.attempt_id} == set(
        seeded["standalone"].values()
    )
    assert all(
        item.test_session_id is None for item in (group.listening, group.reading, group.writing)
    )
    assert group.writing.band_score is None
    assert group.writing.review_available
    assert group.overall_band_score is None
    assert group.reading.attempt_id != seeded["older_reading_id"]
    assert seeded["unfinished_reading_id"] in {item.attempt_id for item in history.items}
    assert (
        next(
            row for row in history.sessions if row.session_id == seeded["sessions"]["new"]
        ).writing.attempt_id
        == seeded["attempts"]["new"][ModuleType.WRITING]
    )
    assert (
        next(
            row for row in history.sessions if row.session_id == seeded["sessions"]["new"]
        ).writing.band_score
        is None
    )

    await db_session.rollback()
    await SessionService(db_session).delete(seeded["sessions"]["new"])
    remaining = await AttemptService(db_session).history()
    group = next(row for row in remaining.groups if row.test_version_id == seeded["version_id"])
    assert {group.listening.attempt_id, group.reading.attempt_id, group.writing.attempt_id} == set(
        seeded["standalone"].values()
    )
    assert seeded["sessions"]["new"] not in {row.session_id for row in remaining.sessions}
    assert not set(seeded["attempts"]["new"].values()) & {row.attempt_id for row in remaining.items}

    await db_session.rollback()
    await SessionService(db_session).delete(seeded["sessions"]["old"])
    fallback = await AttemptService(db_session).history()
    group = next(row for row in fallback.groups if row.test_version_id == seeded["version_id"])
    assert {group.listening.attempt_id, group.reading.attempt_id, group.writing.attempt_id} == set(
        seeded["standalone"].values()
    )


@pytest.mark.integration
async def test_delete_standalone_history_removes_all_version_attempts_and_dependents_only(
    db_session: AsyncSession, authenticated_admin, test_user
) -> None:
    seeded = await _seed_history(db_session, test_user.id)
    standalone_ids = {
        *seeded["standalone"].values(),
        seeded["older_reading_id"],
        seeded["unfinished_reading_id"],
    }
    response = await _delete_standalone_endpoint(db_session, seeded["version_id"])
    assert response.status_code == 204
    assert response.content == b""
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Attempt).where(Attempt.id.in_(standalone_ids))
        )
        == 0
    )
    for model in (
        AttemptAnswer,
        AttemptWritingResponse,
        AttemptWritingScore,
        Highlight,
        QuestionFlag,
        AttemptEvent,
    ):
        assert (
            await db_session.scalar(
                select(func.count()).select_from(model).where(model.attempt_id.in_(standalone_ids))
            )
            == 0
        )
    for surviving_id in (
        seeded["other_version_attempt_id"],
        seeded["foreign_standalone_id"],
        *seeded["attempts"]["new"].values(),
    ):
        assert await db_session.scalar(select(Attempt.id).where(Attempt.id == surviving_id))
    assert await db_session.scalar(
        select(DomainSession.id).where(DomainSession.id == seeded["sessions"]["new"])
    )
    assert await db_session.scalar(
        select(DomainVersion.id).where(DomainVersion.id == seeded["version_id"])
    )

    await db_session.rollback()
    history = await AttemptService(db_session).history()
    assert {group.test_version_id for group in history.groups} == {seeded["other_version_id"]}
    assert seeded["sessions"]["new"] in {row.session_id for row in history.sessions}
    assert set(seeded["attempts"]["new"].values()).issubset(
        {item.attempt_id for item in history.items}
    )


@pytest.mark.integration
async def test_full_mock_only_history_has_no_standalone_group(
    db_session: AsyncSession, test_user
) -> None:
    seeded = await _seed_history(db_session, test_user.id)
    await AttemptService(db_session).delete_standalone_history(seeded["version_id"])
    await AttemptService(db_session).delete_standalone_history(seeded["other_version_id"])
    history = await AttemptService(db_session).history()
    assert history.groups == []
    assert history.sessions
    assert any(item.test_session_id for item in history.items)


@pytest.mark.integration
async def test_delete_standalone_history_uses_ownership_safe_not_found(
    db_session: AsyncSession, authenticated_admin, test_user
) -> None:
    seeded = await _seed_history(db_session, test_user.id)
    for version_id in (seeded["foreign_only_version_id"], uuid4()):
        response = await _delete_standalone_endpoint(db_session, version_id)
        assert response.status_code == 404
        assert response.json()["code"] == "STANDALONE_HISTORY_NOT_FOUND"
        await db_session.rollback()
    assert await db_session.scalar(
        select(Attempt.id).where(Attempt.id == seeded["foreign_standalone_id"])
    )


@pytest.mark.integration
@pytest.mark.parametrize("session_label", ["new", "old", "active"])
async def test_delete_full_mock_endpoint_cascades_owned_rows_only(
    db_session: AsyncSession, authenticated_admin, test_user, session_label: str
) -> None:
    seeded = await _seed_history(db_session, test_user.id)
    session_id = seeded["sessions"][session_label]
    child_ids = set(seeded["attempts"][session_label].values())
    response = await _delete_endpoint(db_session, session_id)

    assert response.status_code == 204
    assert response.content == b""
    assert (
        await db_session.scalar(
            select(func.count()).select_from(DomainSession).where(DomainSession.id == session_id)
        )
        == 0
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Attempt).where(Attempt.id.in_(child_ids))
        )
        == 0
    )
    for model in (
        AttemptAnswer,
        AttemptWritingResponse,
        AttemptWritingScore,
        Highlight,
        QuestionFlag,
        AttemptEvent,
    ):
        assert (
            await db_session.scalar(
                select(func.count()).select_from(model).where(model.attempt_id.in_(child_ids))
            )
            == 0
        )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.id.in_(seeded["standalone"].values()))
        )
        == 3
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(DomainSession)
            .where(DomainSession.id == seeded["sessions"]["other"])
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(DomainVersion)
            .where(DomainVersion.id == seeded["version_id"])
        )
        == 1
    )
    await db_session.rollback()
    history = await AttemptService(db_session).history()
    assert session_id not in {row.session_id for row in history.sessions}


@pytest.mark.integration
async def test_full_mock_delete_is_owner_scoped_and_child_attempt_delete_is_rejected(
    db_session: AsyncSession, authenticated_admin, test_user
) -> None:
    seeded = await _seed_history(db_session, test_user.id)
    foreign_id = seeded["sessions"]["other"]
    denied = await _delete_endpoint(db_session, foreign_id)
    assert denied.status_code == 404
    assert denied.json()["code"] == "TEST_SESSION_NOT_FOUND"
    await db_session.rollback()
    with pytest.raises(AppError) as caught:
        await AttemptService(db_session).delete_attempt(
            seeded["attempts"]["new"][ModuleType.READING]
        )
    assert caught.value.code == "FULL_MOCK_ATTEMPT_DELETE_FORBIDDEN"
    await db_session.rollback()
    assert (
        await db_session.scalar(
            select(func.count()).select_from(DomainSession).where(DomainSession.id == foreign_id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.id == seeded["attempts"]["new"][ModuleType.READING])
        )
        == 1
    )
