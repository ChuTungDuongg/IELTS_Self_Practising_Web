import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.main import app
from app.models.enums import UserRole
from app.schemas.preferences import PreferencesUpdate
from app.services.admin import AdminService
from app.services.preferences import PreferenceService

DEFAULTS = {"accent_color": "PURPLE", "appearance": "LIGHT", "locale": "EN"}


@asynccontextmanager
async def preferences_client(session, user=None):
    async def session_override():
        yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = session_override
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def stored_preferences(session, user_id):
    async with session.begin():
        return await session.scalar(
            select(models.UserPreference).where(models.UserPreference.user_id == user_id)
        )


async def test_guest_cannot_read_or_patch_preferences(db_session):
    async with preferences_client(db_session) as client:
        assert (await client.get("/api/v1/me/preferences")).status_code == 401
        assert (
            await client.patch("/api/v1/me/preferences", json={"accent_color": "BLUE"})
        ).status_code == 401


@pytest.mark.parametrize("role", list(UserRole))
async def test_missing_preferences_are_defaults_without_creating_row(db_session, test_user, role):
    async with db_session.begin():
        test_user.role = role
    async with preferences_client(db_session, test_user) as client:
        response = await client.get("/api/v1/me/preferences")
        assert response.status_code == 200
        assert response.json() == DEFAULTS
    assert await stored_preferences(db_session, test_user.id) is None


async def test_partial_patch_creates_one_row_and_preserves_other_values(db_session, test_user):
    async with preferences_client(db_session, test_user) as client:
        response = await client.patch("/api/v1/me/preferences", json={"accent_color": "BLUE"})
        assert response.status_code == 200
        assert response.json() == {**DEFAULTS, "accent_color": "BLUE"}
        for _ in range(2):
            response = await client.patch(
                "/api/v1/me/preferences", json={"appearance": "DARK", "locale": "VI"}
            )
            assert response.json() == {"accent_color": "BLUE", "appearance": "DARK", "locale": "VI"}
        assert (await client.get("/api/v1/me/preferences")).json() == response.json()
    row = await stored_preferences(db_session, test_user.id)
    assert row.created_at is not None and row.updated_at >= row.created_at
    async with db_session.begin():
        assert len((await db_session.scalars(select(models.UserPreference))).all()) == 1


@pytest.mark.parametrize(
    "invalid",
    [
        {"accent_color": "#123456"},
        {"accent_color": "blue"},
        {"accent_color": "CUSTOM"},
        {"appearance": "SYSTEM"},
        {"appearance": "dark"},
        {"locale": "FR"},
        {"locale": "vi"},
        {"accent_color": None},
        {"appearance": None},
        {"locale": None},
        {"accent_color": ["BLUE"]},
        {"user_id": "00000000-0000-0000-0000-000000000001"},
    ],
)
async def test_invalid_values_and_extra_identity_are_rejected_without_writes(
    db_session, test_user, invalid
):
    async with preferences_client(db_session, test_user) as client:
        response = await client.patch("/api/v1/me/preferences", json=invalid)
        assert response.status_code == 422
    assert await stored_preferences(db_session, test_user.id) is None


@pytest.mark.parametrize("role", list(UserRole))
async def test_role_does_not_allow_targeting_another_users_preferences(db_session, test_user, role):
    other = db_session.info["current_user_identity"]
    async with preferences_client(db_session, other) as client:
        response = await client.patch("/api/v1/me/preferences", json={"accent_color": "PINK"})
        assert response.status_code == 200
    async with db_session.begin():
        test_user.role = role
    async with preferences_client(db_session, test_user) as client:
        assert (await client.get(f"/api/v1/me/preferences?user_id={other.id}")).json() == DEFAULTS
        assert (
            await client.patch(
                "/api/v1/me/preferences", json={"user_id": str(other.id), "accent_color": "RED"}
            )
        ).status_code == 422
        assert (await client.get(f"/api/v1/users/{other.id}/preferences")).status_code == 404
    assert (await stored_preferences(db_session, other.id)).accent_color == "PINK"
    assert await stored_preferences(db_session, test_user.id) is None


async def test_existing_allowed_account_deletion_cascades_preferences(db_session, test_user):
    async with preferences_client(db_session, test_user) as client:
        assert (
            await client.patch("/api/v1/me/preferences", json={"locale": "VI"})
        ).status_code == 200
    async with db_session.begin():
        test_user.is_active = False
    await AdminService(db_session).delete_user(db_session.info["current_user_id"], test_user.id)
    assert await stored_preferences(db_session, test_user.id) is None


@pytest.mark.parametrize(
    "preset",
    ["PURPLE", "INDIGO", "BLUE", "CYAN", "EMERALD", "GREEN", "AMBER", "ORANGE", "RED", "PINK"],
)
async def test_all_supported_presets_round_trip(db_session, test_user, preset):
    async with preferences_client(db_session, test_user) as client:
        response = await client.patch("/api/v1/me/preferences", json={"accent_color": preset})
        assert response.status_code == 200
        assert response.json() == {**DEFAULTS, "accent_color": preset}
        assert (await client.get("/api/v1/me/preferences")).json() == response.json()


async def test_concurrent_first_partial_patches_compose_without_duplicate_row():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    try:
        async with sessions() as session, session.begin():
            session.add(
                models.User(
                    id=user_id,
                    email=f"preferences-{user_id}@example.com",
                    display_name="Concurrent preferences",
                    role=UserRole.USER,
                    is_active=True,
                )
            )

        async def patch(update):
            async with sessions() as session:
                return await PreferenceService(session, user_id).update(PreferencesUpdate(**update))

        await asyncio.gather(
            patch({"accent_color": "BLUE"}), patch({"appearance": "DARK", "locale": "VI"})
        )
        async with sessions() as session:
            result = await PreferenceService(session, user_id).get()
            assert result.model_dump() == {
                "accent_color": "BLUE",
                "appearance": "DARK",
                "locale": "VI",
            }
    finally:
        async with sessions() as session, session.begin():
            await session.execute(delete(models.User).where(models.User.id == user_id))
        await engine.dispose()
