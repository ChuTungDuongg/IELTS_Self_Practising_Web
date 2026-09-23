import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.dependencies import get_auth_session
from app.bootstrap_admin import bootstrap_admin
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.main import app
from app.models import OAuthAccount, RefreshSession, User
from app.models.enums import UserRole
from app.services.auth import AuthService, GoogleIdentity

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
    app.dependency_overrides[get_auth_session] = override_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_password_hashing_and_verification() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert encoded.startswith("scrypt$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_jwt_signature_expiration_and_claim_validation() -> None:
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    token = create_token(
        subject=user_id,
        token_type="access",
        secret=SECRET,
        issuer="issuer",
        audience="audience",
        lifetime=timedelta(minutes=5),
        role="USER",
        now=now,
    )
    claims = decode_token(
        token,
        expected_type="access",
        secret=SECRET,
        issuer="issuer",
        audience="audience",
        now=now,
    )
    assert claims.subject == user_id
    with pytest.raises(AppError, match="invalid"):
        decode_token(
            token,
            expected_type="access",
            secret=SECRET + "tampered",
            issuer="issuer",
            audience="audience",
            now=now,
        )
    with pytest.raises(AppError) as expired:
        decode_token(
            token,
            expected_type="access",
            secret=SECRET,
            issuer="issuer",
            audience="audience",
            now=now + timedelta(minutes=6),
        )
    assert expired.value.code == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_registration_login_me_refresh_and_logout(client, db_session) -> None:
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "Student@Example.com",
            "display_name": "Student",
            "password": "safe-password",
        },
    )
    assert registration.status_code == 201
    assert registration.json()["user"]["email"] == "student@example.com"
    assert registration.json()["user"]["role"] == "USER"
    assert "ielts_access" in registration.cookies
    assert "ielts_refresh" in registration.cookies

    user = await db_session.scalar(select(User).where(User.email == "student@example.com"))
    assert user is not None
    assert user.password_hash != "safe-password"
    assert verify_password("safe-password", user.password_hash)
    assert user.role.value == "USER"
    assert user.email_verified is False
    await db_session.commit()

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={"email": "STUDENT@example.com", "display_name": "Other", "password": "safe-password"},
    )
    assert duplicate.status_code == 409

    invalid = await client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "not-the-password"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "INVALID_CREDENTIALS"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "safe-password"},
    )
    assert login.status_code == 200
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)

    original_refresh = client.cookies.get("ielts_refresh")
    client.cookies.delete("ielts_access", path="/")
    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert client.cookies.get("ielts_refresh") != original_refresh
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    rotated_rows = list(
        await db_session.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id))
    )
    assert any(row.revoked_at is not None for row in rotated_rows)
    await db_session.commit()

    current_refresh = client.cookies.get("ielts_refresh")
    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    client.cookies.set("ielts_refresh", current_refresh, path="/")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


@pytest.mark.asyncio
async def test_registration_rejects_client_supplied_admin_role(client, db_session) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "role-injection@example.com",
            "display_name": "Role Injection",
            "password": "safe-password",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 422
    assert (
        await db_session.scalar(select(User.id).where(User.email == "role-injection@example.com"))
        is None
    )


@pytest.mark.asyncio
async def test_bootstrap_admin_is_hashed_and_idempotent(db_session) -> None:
    settings = Settings(
        jwt_secret=SECRET,
        initial_admin_email=" First.Admin@Example.com ",
        initial_admin_password="bootstrap-password",
        initial_admin_name="First Administrator",
    )
    first = await bootstrap_admin(db_session, settings)
    admin = await db_session.scalar(select(User).where(User.email == "first.admin@example.com"))
    assert first.created is True
    assert admin is not None
    assert admin.role.value == "ADMIN"
    assert admin.is_active is True
    assert admin.email_verified is True
    assert admin.password_hash != "bootstrap-password"
    assert verify_password("bootstrap-password", admin.password_hash)
    original_hash = admin.password_hash
    await db_session.commit()

    second = await bootstrap_admin(db_session, settings)
    assert second.created is False
    assert second.user_id == first.user_id
    rows = list(
        await db_session.scalars(select(User).where(User.email == "first.admin@example.com"))
    )
    assert len(rows) == 1
    assert rows[0].password_hash == original_hash


@pytest.mark.asyncio
async def test_bootstrap_requires_complete_config_and_never_promotes_existing_user(
    db_session,
) -> None:
    with pytest.raises(AppError) as missing:
        await bootstrap_admin(db_session, Settings(jwt_secret=SECRET))
    assert missing.value.code == "ADMIN_BOOTSTRAP_CONFIG_REQUIRED"

    async with db_session.begin():
        existing = User(
            email="existing-user@example.com",
            display_name="Existing User",
            password_hash=hash_password("existing-password"),
            role=UserRole.USER,
            is_active=True,
            email_verified=False,
        )
        db_session.add(existing)
    settings = Settings(
        jwt_secret=SECRET,
        initial_admin_email="existing-user@example.com",
        initial_admin_password="bootstrap-password",
        initial_admin_name="Existing User",
    )
    with pytest.raises(AppError) as conflict:
        await bootstrap_admin(db_session, settings)
    assert conflict.value.code == "ADMIN_BOOTSTRAP_USER_EXISTS"
    await db_session.refresh(existing)
    assert existing.role.value == "USER"


@pytest.mark.asyncio
async def test_invalid_refresh_credentials_are_rejected(client) -> None:
    missing = await client.post("/api/v1/auth/refresh")
    assert missing.status_code == 401
    assert missing.json()["code"] == "REFRESH_REQUIRED"
    client.cookies.set("ielts_refresh", "not-a-jwt", path="/")
    invalid = await client.post("/api/v1/auth/refresh")
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_invalid_and_expired_access_tokens_return_401(client) -> None:
    client.cookies.set("ielts_access", "not-a-jwt", path="/")
    invalid = await client.get("/api/v1/auth/me")
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "INVALID_TOKEN"

    expired = create_token(
        subject=uuid.uuid4(),
        token_type="access",
        secret=SECRET,
        issuer=get_settings().jwt_issuer,
        audience=get_settings().jwt_audience,
        lifetime=timedelta(seconds=1),
        now=datetime.now(UTC) - timedelta(minutes=1),
    )
    client.cookies.set("ielts_access", expired, path="/")
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_google_provider_response_and_stable_subject_linking(db_session, monkeypatch) -> None:
    settings = Settings(
        jwt_secret=SECRET,
        google_client_id="client",
        google_client_secret="secret",
        google_redirect_uri="http://test/callback",
    )

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse({"access_token": "provider-token"})

        async def get(self, *_args, **_kwargs):
            return FakeResponse(
                {
                    "sub": "google-subject",
                    "email": "oauth@example.com",
                    "email_verified": True,
                    "name": "OAuth User",
                }
            )

    monkeypatch.setattr("app.services.auth.httpx.AsyncClient", lambda **_kwargs: FakeClient())
    service = AuthService(db_session, settings)
    identity = await service.fetch_google_identity("code")
    first = await service.find_or_link_google(identity)
    assert first.role.value == "USER"
    assert first.email_verified is True
    async with db_session.begin():
        first.role = UserRole.ADMIN
    second = await service.find_or_link_google(
        GoogleIdentity("google-subject", "different@example.com", "Different", True)
    )
    assert first.id == second.id
    assert second.role.value == "ADMIN"
    accounts = list(
        await db_session.scalars(select(OAuthAccount).where(OAuthAccount.user_id == first.id))
    )
    assert len(accounts) == 1
    assert accounts[0].provider_subject == "google-subject"
    await db_session.commit()

    async with db_session.begin():
        oauth_admin = User(
            email="oauth-admin@example.com",
            display_name="OAuth Admin",
            password_hash=hash_password("existing-password"),
            role=UserRole.ADMIN,
            is_active=True,
            email_verified=True,
        )
        db_session.add(oauth_admin)
        await db_session.flush()
        oauth_admin_id = oauth_admin.id
    linked_admin = await service.find_or_link_google(
        GoogleIdentity("admin-google-subject", "oauth-admin@example.com", "OAuth Admin", True)
    )
    assert linked_admin.id == oauth_admin_id
    assert linked_admin.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_google_callback_validates_state_and_links_identity(
    client, db_session, monkeypatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://test/api/v1/auth/oauth/google/callback")
    get_settings.cache_clear()

    async def fake_identity(_service, _code):
        return GoogleIdentity("callback-subject", "callback@example.com", "Callback User", True)

    monkeypatch.setattr(AuthService, "fetch_google_identity", fake_identity)
    start = await client.get("/api/v1/auth/oauth/google/start")
    assert start.status_code == 302
    state = client.cookies.get("ielts_oauth_state")
    assert state

    invalid = await client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "mock-code", "state": "wrong-state"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "OAUTH_STATE_INVALID"

    callback = await client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "mock-code", "state": state},
    )
    assert callback.status_code == 302
    assert "ielts_access" in callback.cookies
    account = await db_session.scalar(
        select(OAuthAccount).where(OAuthAccount.provider_subject == "callback-subject")
    )
    assert account is not None
