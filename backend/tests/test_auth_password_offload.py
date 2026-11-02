"""Password CPU work leaves the event loop; session operations stay on it."""

import asyncio
import threading
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import RegisterRequest
from app.services import auth

PASSWORD = "fictional-password"
SECRET = "fictional-password-offload-test-secret"


class SessionBoundary:
    """No database I/O; fail if a session operation moves into a worker thread."""

    def __init__(self, user=None):
        self.user = user
        self.loop_thread = threading.get_ident()
        self.active = False
        self.added = []
        self.flushed = False

    @asynccontextmanager
    async def begin(self):
        assert threading.get_ident() == self.loop_thread
        self.active = True
        try:
            yield
        finally:
            self.active = False

    def check_session_thread(self):
        assert threading.get_ident() == self.loop_thread
        assert self.active

    async def scalar(self, statement):
        self.check_session_thread()
        return self.user

    def add(self, value):
        self.check_session_thread()
        self.added.append(value)

    async def flush(self):
        self.check_session_thread()
        self.flushed = True

    async def refresh(self, user):
        self.check_session_thread()

    async def execute(self, statement):
        self.check_session_thread()


@pytest.fixture
def user():
    return User(
        id=uuid4(),
        email="fictional@example.com",
        display_name="Fictional learner",
        password_hash=hash_password(PASSWORD),
        role=UserRole.USER,
        is_active=True,
        email_verified=False,
    )


@pytest.fixture(autouse=True)
def no_external_invitation_queries(monkeypatch):
    async def bind(service, user):
        service.session.check_session_thread()

    monkeypatch.setattr(auth.AuthService, "_bind_classroom_invitations", bind)


@pytest.mark.parametrize("operation", ["register", "authenticate", "change_password"])
async def test_password_operations_run_off_loop_without_moving_session(
    operation, monkeypatch, user
):
    loop_thread = threading.get_ident()
    calls = []

    def observe(function, kind):
        def run(*args):
            assert threading.get_ident() != loop_thread, "scrypt ran on the event-loop thread"
            calls.append(kind)
            return function(*args)

        return run

    monkeypatch.setattr(auth, "hash_password", observe(hash_password, "hash"))
    monkeypatch.setattr(auth, "verify_password", observe(verify_password, "verify"))
    session = SessionBoundary(None if operation == "register" else user)
    service = auth.AuthService(session, Settings(_env_file=None, jwt_secret=SECRET))
    if operation == "register":
        result = await service.register(
            RegisterRequest(
                email="fictional@example.com",
                display_name="Fictional learner",
                password=PASSWORD,
            )
        )
        assert calls == ["hash"]
        assert verify_password(PASSWORD, result.password_hash)
    elif operation == "authenticate":
        assert await service.authenticate(user.email, PASSWORD) is user
        assert calls == ["verify"]
        assert user.last_login_at is not None
    else:
        result, issued = await service.change_password(user.id, PASSWORD, "replacement-password")
        assert result is user and issued.access_token and issued.refresh_token
        assert calls == ["verify", "hash"]
        assert verify_password("replacement-password", user.password_hash)
    assert session.flushed and not session.active


@pytest.mark.parametrize(
    "operation,password,active,expected",
    [
        ("authenticate", "wrong-password", True, ("INVALID_CREDENTIALS", 401)),
        ("authenticate", PASSWORD, False, ("ACCOUNT_INACTIVE", 403)),
        ("change_password", "wrong-password", True, ("CURRENT_PASSWORD_INVALID", 400)),
        ("change_password", PASSWORD, True, ("PASSWORD_UNCHANGED", 400)),
    ],
)
async def test_offloaded_password_checks_preserve_auth_failures(
    operation, password, active, expected, user
):
    user.is_active = active
    session = SessionBoundary(user)
    service = auth.AuthService(session, Settings(_env_file=None, jwt_secret=SECRET))
    with pytest.raises(AppError) as failure:
        if operation == "authenticate":
            await service.authenticate(user.email, password)
        else:
            await service.change_password(user.id, password, PASSWORD)
    assert (failure.value.code, failure.value.status_code) == expected
    assert not session.flushed and not session.active


def test_password_limit_works_across_fresh_event_loops(user):
    async def run_batch():
        settings = Settings(_env_file=None)
        return await asyncio.gather(
            *(
                auth.AuthService(SessionBoundary(user), settings).authenticate(user.email, PASSWORD)
                for _ in range(3)
            )
        )

    for _ in range(2):
        assert asyncio.run(run_batch()) == [user, user, user]


async def test_password_offload_keeps_limit_until_cancelled_thread_finishes(monkeypatch, user):
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    two_started = asyncio.Event()
    release = threading.Event()
    lock = threading.Lock()
    active = peak = entered = 0

    def controlled_verify(*args):
        nonlocal active, peak, entered
        assert threading.get_ident() != loop_thread, "scrypt ran on the event-loop thread"
        with lock:
            active += 1
            entered += 1
            peak = max(peak, active)
            if entered == 2:
                loop.call_soon_threadsafe(two_started.set)
        try:
            assert release.wait(timeout=5), "test did not release password work"
            return verify_password(*args)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(auth, "verify_password", controlled_verify)
    settings = Settings(_env_file=None)

    async def authenticate():
        return await auth.AuthService(SessionBoundary(user), settings).authenticate(
            user.email, PASSWORD
        )

    tasks = [asyncio.create_task(authenticate()) for _ in range(6)]
    try:
        await asyncio.wait_for(two_started.wait(), timeout=2)
        # Cancellation cannot terminate scrypt; its slot must remain occupied.
        tasks[0].cancel()
        tasks[1].cancel()
        for _ in range(10):
            await asyncio.sleep(0)
        tasks[0].cancel()
        tasks[1].cancel()
        for _ in range(10):
            await asyncio.sleep(0)
        with lock:
            assert entered == 2 and active == 2
        assert not tasks[0].done() and not tasks[1].done()
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
        assert sum(isinstance(result, asyncio.CancelledError) for result in results) == 2
        assert all(result is user for result in results[2:])
        assert peak == 2
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
