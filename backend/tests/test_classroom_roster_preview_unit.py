"""Bounded roster previews preserve the existing roster authorization boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.v1.classrooms import router
from app.core.database import get_session
from app.core.exceptions import AppError
from app.repositories.classrooms import ClassroomRepository
from app.schemas.classrooms import MembershipList
from app.services.classrooms import ClassroomService
from tests.test_classroom_classwork_unit import actor, classroom, session_double


async def test_preview_query_filters_active_members_and_limits_in_database():
    session = session_double()
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    room_id = uuid4()
    await ClassroomRepository(session).members(room_id, limit=3, active_only=True)
    statement = session.execute.await_args.args[0]
    assert "classroom_memberships.left_at IS NULL" in str(statement)
    assert "users.role" in str(statement)
    assert statement.compile().params["param_1"] == 3


async def test_default_roster_query_remains_unbounded_and_includes_history():
    session = session_double()
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    await ClassroomRepository(session).members(uuid4())
    statement = session.execute.await_args.args[0]
    assert "classroom_memberships.left_at IS NULL" not in str(statement)
    assert statement._limit_clause is None


async def test_preview_requires_roster_capability():
    student = actor("USER")
    room = classroom(actor())
    service = ClassroomService(session_double(student, room, None), student)
    service.repository.members = AsyncMock()
    with pytest.raises(AppError) as error:
        await service.members(room.id, limit=3, active_only=True)
    assert error.value.status_code == 403
    service.repository.members.assert_not_awaited()


def test_route_validates_limit_and_passes_preview_options(monkeypatch):
    current = actor()
    handler = AsyncMock(return_value=MembershipList(items=[]))
    monkeypatch.setattr("app.api.v1.classrooms.ClassroomService.members", handler)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current
    app.dependency_overrides[get_session] = lambda: None
    with TestClient(app) as client:
        path = f"/classrooms/{uuid4()}/members"
        assert client.get(path, params={"limit": 0}).status_code == 422
        assert client.get(path, params={"limit": 11}).status_code == 422
        assert client.get(path, params={"limit": 3, "active_only": "true"}).status_code == 200
    assert handler.await_args.kwargs == {"limit": 3, "active_only": True}
