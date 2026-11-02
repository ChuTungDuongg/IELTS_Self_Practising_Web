"""Controlled authentication component timing; no network or database access."""

import argparse
import asyncio
import json
import math
import os
import platform
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import Settings
from app.core.security import hash_password
from app.services import auth


class ControlledSession:
    def __init__(self, encoded):
        self.user = SimpleNamespace(
            id=uuid4(), password_hash=encoded, is_active=True, last_login_at=None
        )

    @asynccontextmanager
    async def begin(self):
        yield

    async def scalar(self, statement):
        return self.user

    async def flush(self):
        pass

    async def refresh(self, user):
        pass


async def no_invitations(user):
    pass


def percentile(values, quantile):
    return sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)]


async def measure():
    password = "fictional-component-password"
    encoded = hash_password(password)
    settings = Settings(_env_file=None)
    original = auth.verify_password
    lock = threading.Lock()
    active = peak = completed = 0
    thread_ids = set()

    def observed(*args):
        nonlocal active, peak, completed
        with lock:
            active += 1
            peak = max(peak, active)
            thread_ids.add(threading.get_ident())
        try:
            return original(*args)
        finally:
            with lock:
                active -= 1
                completed += 1

    auth.verify_password = observed
    lags = []
    stop = asyncio.Event()
    loop_thread = threading.get_ident()

    async def heartbeat():
        while not stop.is_set():
            expected = time.perf_counter() + 0.01
            await asyncio.sleep(0.01)
            lags.append(max(0.0, time.perf_counter() - expected) * 1000)

    async def authenticate():
        service = auth.AuthService(ControlledSession(encoded), settings)
        service._bind_classroom_invitations = no_invitations
        await service.authenticate("fictional@example.test", password)

    heart = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    start, cpu_start = time.perf_counter(), time.process_time()
    for _ in range(10):
        await asyncio.gather(*(authenticate() for _ in range(5)))
    wall, cpu = time.perf_counter() - start, time.process_time() - cpu_start
    stop.set()
    await heart
    auth.verify_password = original
    return {
        "scope": "AuthService.authenticate with real scrypt; controlled DB boundary; no HTTP/database/provider calls",
        "python": platform.python_version(),
        "platform": platform.system(),
        "process_cpu_count": getattr(os, "process_cpu_count", os.cpu_count)(),
        "total_calls": completed,
        "batch_concurrency": 5,
        "batches": 10,
        "heartbeat_interval_ms": 10,
        "scrypt": {"n": 16384, "r": 8, "p": 1, "dklen": 32},
        "wall_seconds": round(wall, 6),
        "process_cpu_seconds": round(cpu, 6),
        "peak_password_callbacks": peak,
        "password_callback_thread_count": len(thread_ids),
        "password_callback_on_event_loop": loop_thread in thread_ids,
        "heartbeat_samples": len(lags),
        "heartbeat_lag_p50_ms": round(percentile(lags, 0.50), 6),
        "heartbeat_lag_p95_ms": round(percentile(lags, 0.95), 6),
        "heartbeat_lag_max_ms": round(max(lags), 6),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = {"label": args.label, **asyncio.run(measure())}
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
