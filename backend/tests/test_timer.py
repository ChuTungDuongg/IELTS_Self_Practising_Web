from datetime import UTC, datetime, timedelta

from app.domains.timers import AFK_TIMEOUT, TimerService
from app.models.enums import TimerMode


def test_countdown_uses_absolute_deadline() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    snapshot = TimerService.snapshot(
        mode=TimerMode.COUNTDOWN,
        started_at=started,
        limit_seconds=3600,
        now=started + timedelta(seconds=61),
    )
    assert snapshot.elapsed_seconds == 61
    assert snapshot.remaining_seconds == 3539
    assert snapshot.deadline_at == started + timedelta(hours=1)
    assert not snapshot.expired


def test_countdown_expiry_is_server_timestamp_based() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    snapshot = TimerService.snapshot(
        mode=TimerMode.COUNTDOWN,
        started_at=started,
        limit_seconds=40,
        now=started + timedelta(seconds=40),
    )
    assert snapshot.expired
    assert snapshot.remaining_seconds == 0


def test_count_up_has_no_deadline() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    snapshot = TimerService.snapshot(
        mode=TimerMode.COUNT_UP,
        started_at=started,
        limit_seconds=None,
        now=started + timedelta(hours=2, seconds=4),
    )
    assert snapshot.deadline_at is None
    assert snapshot.remaining_seconds is None
    assert snapshot.elapsed_seconds == 7204


def test_afk_threshold_is_five_minutes() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    assert not TimerService.is_afk(started, started + AFK_TIMEOUT - timedelta(microseconds=1))
    assert TimerService.is_afk(started, started + AFK_TIMEOUT)


def test_paused_countdown_freezes_active_time_and_remaining_time() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    paused_at = started + timedelta(minutes=10)
    snapshot = TimerService.snapshot(
        mode=TimerMode.COUNTDOWN,
        started_at=started,
        limit_seconds=3600,
        paused_at=paused_at,
        now=paused_at + timedelta(hours=3),
    )

    assert snapshot.elapsed_seconds == 600
    assert snapshot.remaining_seconds == 3000
    assert snapshot.deadline_at is None
    assert not snapshot.expired


def test_resumed_countdown_deadline_accounts_for_accumulated_pauses() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    snapshot = TimerService.snapshot(
        mode=TimerMode.COUNTDOWN,
        started_at=started,
        limit_seconds=3600,
        total_paused_seconds=3 * 3600,
        now=started + timedelta(hours=3, minutes=12),
    )

    assert snapshot.elapsed_seconds == 720
    assert snapshot.remaining_seconds == 2880
    assert snapshot.deadline_at == started + timedelta(hours=4)


def test_paused_count_up_excludes_wall_clock_pause_duration() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    paused_at = started + timedelta(minutes=17, seconds=42)
    snapshot = TimerService.snapshot(
        mode=TimerMode.COUNT_UP,
        started_at=started,
        limit_seconds=None,
        paused_at=paused_at,
        now=paused_at + timedelta(hours=2),
    )

    assert snapshot.elapsed_seconds == 1062
    assert snapshot.deadline_at is None
