"""Exercise assignable-test HTTP serialization without a database or server."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.v1.classroom_lms import router
from app.core.database import get_session
from app.core.exceptions import AppError, app_error_handler
from app.models import Test as DomainTest
from app.models import TestVersion as DomainVersion
from app.models import User
from app.models.enums import TestOrigin as Origin
from app.models.enums import UserRole, VersionStatus
from app.services.classroom_capabilities import Capability
from app.services.classroom_grades import ClassroomGradeService


@asynccontextmanager
async def transaction():
    yield


def endpoint(monkeypatch, role=UserRole.TEACHER):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(AppError, app_error_handler)
    session = Mock(spec=AsyncSession)
    session.begin.side_effect = transaction
    session.scalars = AsyncMock(return_value=[])
    user = User(id=uuid4(), role=role, is_active=True)
    room = SimpleNamespace(id=uuid4(), teacher_id=uuid4())
    authorize = AsyncMock(return_value=room)
    monkeypatch.setattr(ClassroomGradeService, "authorize", authorize)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: session
    return app, session, user, room, authorize


@pytest.mark.parametrize("role", [UserRole.TEACHER, UserRole.ADMIN])
async def test_assignable_tests_handles_catalog_only_fields_and_groups_selected_versions(
    monkeypatch, role
):
    app, session, user, room, authorize = endpoint(monkeypatch, role)
    now = datetime.now(UTC)
    record = DomainTest(
        id=uuid4(),
        owner_user_id=room.teacher_id,
        origin=Origin.TEACHER,
        title="Fictional classroom assignment",
        description=None,
        source_label=None,
        test_number=None,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    versions = [
        DomainVersion(
            id=uuid4(),
            test=record,
            version_number=number,
            status=VersionStatus.PUBLISHED,
            created_at=now,
            published_at=now,
        )
        for number in (1, 2)
    ]
    # An unrelated ORM relationship must not replace the authorized query result.
    DomainVersion(id=uuid4(), test=record, version_number=3, status=VersionStatus.DRAFT)
    session.scalars.return_value = versions
    assert not hasattr(record, "published_detail")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/classrooms/{room.id}/assignable-tests")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["id"] == str(record.id)
    assert rows[0]["title"] == record.title
    assert rows[0]["published_detail"] is None
    assert [version["id"] for version in rows[0]["versions"]] == [str(v.id) for v in versions]
    assert "answer_key" not in response.text
    authorize.assert_awaited_once_with(
        room.id, Capability.CLASSROOM if user.role == UserRole.ADMIN else Capability.ASSIGNMENTS
    )
    session.scalars.assert_awaited_once()


async def test_assignable_tests_keeps_an_empty_catalog_valid(monkeypatch):
    app, _, _, room, _ = endpoint(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/classrooms/{room.id}/assignable-tests")
    assert response.status_code == 200
    assert response.json() == []


async def test_assignable_tests_authorizes_before_loading_content(monkeypatch):
    app, session, _, room, authorize = endpoint(monkeypatch)
    authorize.side_effect = AppError("CLASSROOM_CAPABILITY_REQUIRED", "Not allowed.", 403)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/classrooms/{room.id}/assignable-tests")
    assert response.status_code == 403
    assert response.json()["code"] == "CLASSROOM_CAPABILITY_REQUIRED"
    session.scalars.assert_not_awaited()
