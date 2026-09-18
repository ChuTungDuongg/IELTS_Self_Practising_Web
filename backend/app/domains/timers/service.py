from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.enums import TimerMode

AFK_TIMEOUT = timedelta(minutes=5)
COUNTDOWN_PRESETS = frozenset({2400, 3000, 3600, 4200})


@dataclass(frozen=True, slots=True)
class TimerSnapshot:
    server_time: datetime
    deadline_at: datetime | None
    elapsed_seconds: int
    remaining_seconds: int | None
    expired: bool


class TimerService:
    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @classmethod
    def snapshot(
        cls,
        *,
        mode: TimerMode,
        started_at: datetime,
        limit_seconds: int | None,
        now: datetime | None = None,
    ) -> TimerSnapshot:
        server_time = now or cls.now()
        elapsed = max(0, int((server_time - started_at).total_seconds()))
        if mode == TimerMode.COUNT_UP:
            return TimerSnapshot(server_time, None, elapsed, None, False)
        if limit_seconds is None or limit_seconds <= 0:
            raise ValueError("Countdown attempts require a positive limit")
        deadline = started_at + timedelta(seconds=limit_seconds)
        remaining = max(0, int((deadline - server_time).total_seconds()))
        return TimerSnapshot(server_time, deadline, elapsed, remaining, server_time >= deadline)

    @staticmethod
    def is_afk(last_active_at: datetime, now: datetime | None = None) -> bool:
        server_time = now or TimerService.now()
        return server_time - last_active_at >= AFK_TIMEOUT
