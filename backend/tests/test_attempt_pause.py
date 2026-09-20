from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.main import app
from app.models import Attempt, AttemptWritingResponse, WritingTask
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AttemptStatus, ModuleType, TimerMode, VersionStatus
from app.services.attempts import AttemptService


async def _persist_attempt(
    session: AsyncSession,
    *,
    started_at: datetime,
    last_active_at: datetime,
    mode: TimerMode = TimerMode.COUNTDOWN,
    limit_seconds: int | None = 3600,
    module_type: ModuleType = ModuleType.READING,
) -> Attempt:
    test = DomainTest(title="Fictional paused attempt")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    version.modules.append(DomainModule(module_type=module_type, order_index=0))
    test.versions.append(version)
    attempt = Attempt(
        test_version=version,
        module_type=module_type,
        timer_mode=mode,
        timer_limit_seconds=limit_seconds,
        started_at=started_at,
        last_active_at=last_active_at,
        status=AttemptStatus.IN_PROGRESS,
    )
    async with session.begin():
        session.add_all([test, attempt])
        await session.flush()
    return attempt


@pytest.mark.integration
async def test_countdown_pause_resume_cycles_freeze_and_accumulate(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = datetime(2026, 9, 20, tzinfo=UTC)
    first_pause = started + timedelta(minutes=10)
    attempt = await _persist_attempt(
        db_session,
        started_at=started,
        last_active_at=first_pause,
    )
    service = AttemptService(db_session)

    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: first_pause))
    paused = await service.pause(attempt.id)
    assert paused.attempt_id == attempt.id
    assert paused.status == AttemptStatus.PAUSED
    assert paused.paused_at == first_pause
    assert paused.elapsed_seconds == 600
    assert paused.remaining_seconds == 3000
    assert paused.deadline_at is None
    assert paused.finished_at is None
    assert paused.finished_reason is None
    assert paused.raw_score is None
    assert paused.max_score is None
    assert paused.band_score is None

    first_resume = first_pause + timedelta(hours=3)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: first_resume))
    still_paused = await service.get(attempt.id)
    assert still_paused.status == AttemptStatus.PAUSED
    assert still_paused.elapsed_seconds == 600
    assert still_paused.remaining_seconds == 3000

    resumed = await service.resume(attempt.id)
    assert resumed.attempt_id == attempt.id
    assert resumed.status == AttemptStatus.IN_PROGRESS
    assert resumed.paused_at is None
    assert resumed.total_paused_seconds == 3 * 3600
    assert resumed.remaining_seconds == 3000
    assert resumed.deadline_at == started + timedelta(hours=4)

    second_pause = first_resume + timedelta(minutes=4)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: second_pause))
    paused_again = await service.pause(attempt.id)
    assert paused_again.elapsed_seconds == 840
    assert paused_again.remaining_seconds == 2760

    second_resume = second_pause + timedelta(hours=1)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: second_resume))
    resumed_again = await service.resume(attempt.id)
    assert resumed_again.total_paused_seconds == 4 * 3600
    assert resumed_again.elapsed_seconds == 840
    assert resumed_again.remaining_seconds == 2760


@pytest.mark.integration
async def test_paused_count_up_does_not_expire_or_afk(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = datetime(2026, 9, 20, tzinfo=UTC)
    pause_time = started + timedelta(minutes=17, seconds=42)
    attempt = await _persist_attempt(
        db_session,
        started_at=started,
        last_active_at=pause_time,
        mode=TimerMode.COUNT_UP,
        limit_seconds=None,
    )
    service = AttemptService(db_session)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: pause_time))
    await service.pause(attempt.id)

    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: pause_time + timedelta(days=3)))
    response = await service.get(attempt.id)

    assert response.status == AttemptStatus.PAUSED
    assert response.elapsed_seconds == 1062
    assert response.remaining_seconds is None
    assert response.finished_at is None


@pytest.mark.integration
async def test_expired_countdown_auto_submits_before_pause(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 20, 2, tzinfo=UTC)
    attempt = await _persist_attempt(
        db_session,
        started_at=now - timedelta(seconds=3601),
        last_active_at=now,
    )
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))

    response = await AttemptService(db_session).pause(attempt.id)

    assert response.status == AttemptStatus.AUTO_SUBMITTED
    assert response.paused_at is None
    assert response.finished_at == now


@pytest.mark.integration
async def test_paused_attempt_rejects_activity_submit_and_review(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    attempt = await _persist_attempt(db_session, started_at=now, last_active_at=now)
    attempt_id = attempt.id
    service = AttemptService(db_session)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now + timedelta(minutes=1)))
    await service.pause(attempt_id)

    with pytest.raises(AppError) as activity_error:
        await service.record_activity(attempt_id)
    assert activity_error.value.code == "ATTEMPT_PAUSED"

    with pytest.raises(AppError) as submit_error:
        await service.submit(attempt_id)
    assert submit_error.value.code == "ATTEMPT_PAUSED"

    with pytest.raises(AppError) as review_error:
        await service.review(attempt_id)
    assert review_error.value.code == "ATTEMPT_NOT_FINALIZED"


@pytest.mark.integration
async def test_pause_retains_writing_response_and_history_uses_frozen_timer(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = datetime(2026, 9, 20, tzinfo=UTC)
    pause_time = started + timedelta(minutes=18, seconds=42)
    test = DomainTest(title="Fictional paused Writing")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    task = WritingTask(task_number=1, prompt="Write.", order_index=0)
    module.writing_tasks.append(task)
    version.modules.append(module)
    test.versions.append(version)
    attempt = Attempt(
        test_version=version,
        module_type=ModuleType.WRITING,
        timer_mode=TimerMode.COUNTDOWN,
        timer_limit_seconds=3600,
        started_at=started,
        last_active_at=pause_time,
        status=AttemptStatus.IN_PROGRESS,
    )
    attempt.writing_responses.append(
        AttemptWritingResponse(writing_task=task, content="Saved before pause", word_count=3)
    )
    async with db_session.begin():
        db_session.add_all([test, attempt])
        await db_session.flush()

    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: pause_time))
    await AttemptService(db_session).pause(attempt.id)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: pause_time + timedelta(days=1)))

    exam = await AttemptService(db_session).exam(attempt.id)
    history = await AttemptService(db_session).history()
    history_item = next(item for item in history.items if item.attempt_id == attempt.id)

    assert exam.attempt.status == AttemptStatus.PAUSED
    assert exam.writing_tasks[0].content == "Saved before pause"
    assert history_item.status == AttemptStatus.PAUSED
    assert history_item.elapsed_seconds == 1122
    assert history_item.remaining_seconds == 2478
    assert all(group.writing is None for group in history.groups if group.test_id == test.id)


@pytest.mark.integration
async def test_pause_and_resume_reject_finalized_attempt(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    attempt = await _persist_attempt(db_session, started_at=now, last_active_at=now)
    attempt_id = attempt.id
    service = AttemptService(db_session)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now + timedelta(minutes=1)))
    await service.submit(attempt_id)

    for action in (service.pause, service.resume):
        with pytest.raises(AppError) as caught:
            await action(attempt_id)
        assert caught.value.code == "INVALID_ATTEMPT_TRANSITION"


@pytest.mark.integration
async def test_pause_and_resume_endpoints_keep_the_same_attempt_id(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    attempt = await _persist_attempt(db_session, started_at=now, last_active_at=now)
    attempt_id = attempt.id
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now + timedelta(minutes=2)))

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            paused = await client.post(f"/api/v1/attempts/{attempt_id}/pause")
            resumed = await client.post(f"/api/v1/attempts/{attempt_id}/resume")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert paused.status_code == 200
    assert paused.json()["attempt_id"] == str(attempt_id)
    assert paused.json()["status"] == "PAUSED"
    assert resumed.status_code == 200
    assert resumed.json()["attempt_id"] == str(attempt_id)
    assert resumed.json()["status"] == "IN_PROGRESS"
