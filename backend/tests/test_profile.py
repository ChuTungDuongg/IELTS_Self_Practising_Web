from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.domains.profile_targets import calculate_profile_target_band
from app.main import app
from app.models import User
from app.schemas.auth import RegisterRequest
from app.services.auth import AuthService


@pytest.mark.parametrize(
    ("targets", "expected"),
    [
        (("6.0", "6.5", "7.5", "8.5"), "7.0"),
        (("7.5", "7.5", "7.5", "7.5"), "7.5"),
        (("7.0", "7.0", "7.0", "8.0"), "7.5"),
        (("7.5", "7.5", "7.5", "8.5"), "8.0"),
        ((None, "7.5", "7.0", "8.0"), None),
        (("7.5", None, "7.0", "8.0"), None),
        (("7.5", "7.0", None, "8.0"), None),
        (("7.5", "7.0", "8.0", None), None),
    ],
)
def test_profile_target_requires_four_skills_and_rounds_half_up(targets, expected):
    values = tuple(Decimal(target) if target is not None else None for target in targets)
    result = calculate_profile_target_band(*values)
    assert result == (Decimal(expected) if expected is not None else None)


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
    for field in (
        "target_listening_band",
        "target_reading_band",
        "target_writing_band",
        "target_speaking_band",
    ):
        assert getattr(account, field) is None
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
            for field in (
                "target_listening_band",
                "target_reading_band",
                "target_writing_band",
                "target_speaking_band",
            ):
                assert initial.json()[field] is None
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
                    "target_listening_band": 8.0,
                    "target_reading_band": 7.5,
                    "target_writing_band": 7.0,
                    "target_speaking_band": 7.0,
                    "target_test_date": "2027-01-01",
                    "bio": "  Preparing for a test.  ",
                },
            )
            assert update.status_code == 200, update.text
            assert update.json()["display_name"] == "New Name"
            assert update.json()["target_band"] in ("7.5", 7.5)
            for field, expected in (
                ("target_listening_band", 8.0),
                ("target_reading_band", 7.5),
                ("target_writing_band", 7.0),
                ("target_speaking_band", 7.0),
            ):
                assert float(update.json()[field]) == expected
            assert update.json()["bio"] == "Preparing for a test."
            patch = await client.patch("/api/v1/auth/profile", json={"city": "Hanoi"})
            assert patch.status_code == 200
            assert patch.json()["country"] == "Vietnam"
            assert float(patch.json()["target_listening_band"]) == 8.0
            assert float(patch.json()["target_speaking_band"]) == 7.0
            changed_skill = await client.patch(
                "/api/v1/auth/profile", json={"target_speaking_band": 9.0}
            )
            assert changed_skill.status_code == 200
            assert float(changed_skill.json()["target_band"]) == 8.0
            assert test_user.target_band == Decimal("8.0")
            cleared_skill = await client.patch(
                "/api/v1/auth/profile", json={"target_listening_band": None}
            )
            assert cleared_skill.status_code == 200
            assert cleared_skill.json()["target_listening_band"] is None
            assert cleared_skill.json()["target_band"] is None
            assert test_user.target_band is None
            assert float(cleared_skill.json()["target_reading_band"]) == 7.5
            restored_skill = await client.patch(
                "/api/v1/auth/profile", json={"target_listening_band": 8.0}
            )
            assert restored_skill.status_code == 200
            assert float(restored_skill.json()["target_band"]) == 8.0
            assert test_user.target_band == Decimal("8.0")
            cleared_skills = await client.patch(
                "/api/v1/auth/profile",
                json={
                    field: None
                    for field in (
                        "target_listening_band",
                        "target_reading_band",
                        "target_writing_band",
                        "target_speaking_band",
                    )
                },
            )
            assert cleared_skills.status_code == 200
            for field in (
                "target_listening_band",
                "target_reading_band",
                "target_writing_band",
                "target_speaking_band",
            ):
                assert cleared_skills.json()[field] is None
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
            direct_overall = await client.patch("/api/v1/auth/profile", json={"target_band": 8.0})
            assert direct_overall.status_code == 422
            for field in (
                "target_listening_band",
                "target_reading_band",
                "target_writing_band",
                "target_speaking_band",
            ):
                for invalid in (7.3, -1, 9.5):
                    invalid_band = await client.patch("/api/v1/auth/profile", json={field: invalid})
                    assert invalid_band.status_code == 422, (field, invalid)
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
    assert saved.target_band is None


@pytest.mark.asyncio
async def test_profile_get_derives_overall_from_stale_stored_row(db_session, test_user):
    async with db_session.begin():
        test_user.target_listening_band = Decimal("6.0")
        test_user.target_reading_band = Decimal("6.5")
        test_user.target_writing_band = Decimal("7.5")
        test_user.target_speaking_band = Decimal("8.5")
        test_user.target_band = None
        await db_session.flush()
        await db_session.refresh(test_user)

    async def session_override():
        yield db_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            profile = await client.get("/api/v1/auth/profile")
            assert profile.status_code == 200
            assert float(profile.json()["target_band"]) == 7.0
            assert float(profile.json()["target_speaking_band"]) == 8.5
            assert "password_hash" not in profile.json()
    finally:
        app.dependency_overrides.clear()
    assert test_user.target_band is None
