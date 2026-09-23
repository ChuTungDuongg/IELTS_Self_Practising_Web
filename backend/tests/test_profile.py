from datetime import date, timedelta

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.main import app
from app.models import User
from app.schemas.auth import RegisterRequest
from app.services.auth import AuthService


@pytest.mark.asyncio
async def test_registration_still_needs_only_account_fields(db_session):
    request = RegisterRequest(
        email="profile-example@example.com",
        display_name="Profile Example",
        password="safe-password",
    )
    account = await AuthService(db_session, get_settings()).register(request)
    assert account.phone_number is None
    assert account.target_band is None
    assert account.bio is None
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="extra@example.com",
            display_name="Extra",
            password="safe-password",
            city="Nowhere",
        )


@pytest.mark.asyncio
async def test_profile_requires_authentication(db_session):
    async def session_override():
        yield db_session

    app.dependency_overrides[get_session] = session_override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/v1/auth/profile")).status_code == 401
            assert (
                await client.patch("/api/v1/auth/profile", json={"city": "Nowhere"})
            ).status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_profile_patch_partial_clear_and_security(db_session, test_user):
    async def session_override():
        yield db_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            initial = await client.get("/api/v1/auth/profile")
            assert initial.status_code == 200
            assert initial.json()["city"] is None
            assert initial.json()["email"] == test_user.email
            assert initial.json()["has_password"] is False
            assert "password_hash" not in initial.json()
            update = await client.patch(
                "/api/v1/auth/profile",
                json={
                    "display_name": "  New Name  ",
                    "phone_number": "  +84 123  ",
                    "date_of_birth": "2000-01-01",
                    "country": "Vietnam",
                    "city": "Ho Chi Minh City",
                    "occupation": "Student",
                    "institution": "Fictional University",
                    "target_band": 7.5,
                    "target_test_date": "2027-01-01",
                    "bio": "  Preparing for a test.  ",
                },
            )
            assert update.status_code == 200, update.text
            assert update.json()["display_name"] == "New Name"
            assert update.json()["target_band"] in ("7.5", 7.5)
            assert update.json()["bio"] == "Preparing for a test."
            patch = await client.patch("/api/v1/auth/profile", json={"city": "Hanoi"})
            assert patch.status_code == 200
            assert patch.json()["country"] == "Vietnam"
            cleared = await client.patch("/api/v1/auth/profile", json={"bio": None})
            assert cleared.status_code == 200
            assert cleared.json()["bio"] is None
            for field, value in (
                ("email", "changed@example.com"),
                ("role", "ADMIN"),
                ("is_active", False),
                ("id", str(test_user.id)),
                ("password_hash", "unsafe"),
                ("has_password", True),
            ):
                response = await client.patch("/api/v1/auth/profile", json={field: value})
                assert response.status_code == 422
            invalid_band = await client.patch("/api/v1/auth/profile", json={"target_band": 7.3})
            assert invalid_band.status_code == 422
            future = await client.patch(
                "/api/v1/auth/profile",
                json={"date_of_birth": str(date.today() + timedelta(days=1))},
            )
            assert future.status_code == 422
    finally:
        app.dependency_overrides.clear()
    saved = await db_session.scalar(select(User).where(User.id == test_user.id))
    assert saved.city == "Hanoi"
    assert saved.country == "Vietnam"
    assert saved.email == test_user.email
