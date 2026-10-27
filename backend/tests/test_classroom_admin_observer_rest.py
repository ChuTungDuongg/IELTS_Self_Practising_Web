"""Handcrafted requests exercise real routers and service authorization with DB doubles."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.dependencies import get_current_user
from app.api.v1.assignment_scheduling import router as scheduling_router
from app.api.v1.attempts import router as attempt_router
from app.api.v1.classroom_assignments import router as assignment_router
from app.api.v1.classroom_classwork import router as classwork_router
from app.api.v1.classroom_learning import router as learning_router
from app.api.v1.classroom_lms import router as lms_router
from app.api.v1.classroom_posts import router as post_router
from app.api.v1.classrooms import router as classroom_router
from app.api.v1.speaking import runtime_router as speaking_router
from app.core.database import get_session
from app.core.exceptions import AppError, app_error_handler
from app.models import Attempt, Classroom, ClassroomAssignment, User
from app.repositories.attempts import AttemptRepository
from app.services.access_policy import AccessPolicy
from tests.test_classroom_archive_unit import assignment
from tests.test_classroom_classwork_unit import actor, classroom, session_double

WRITING = {"ta": 6, "cc": 6, "lr": 6, "gra": 6}
SPEAKING = {"fc": 6, "lr": 6, "gra": 6, "pr": 6}
MUTATIONS = [
    ("PATCH", "/classrooms/{room}", {"name": "Forbidden change"}),
    ("POST", "/classrooms/{room}/archive", None),
    ("POST", "/classrooms/{room}/restore", None),
    ("POST", "/classrooms/{room}/members/{student}/remove", None),
    ("POST", "/classrooms/{room}/leave", None),
    ("POST", "/classrooms/{room}/invitations", {"email": "fictional@example.com"}),
    ("POST", "/classroom-invitations/{item}/cancel", None),
    ("POST", "/classroom-invitations/{item}/accept", None),
    ("POST", "/classroom-invitations/{item}/decline", None),
    (
        "POST",
        "/classrooms/{room}/assignments",
        {
            "test_version_id": "{version}",
            "target": {"mode": "MODULE", "module": "READING", "scope": "FULL_MODULE"},
        },
    ),
    ("POST", "/classrooms/{room}/assignments/{assignment}/archive", None),
    ("POST", "/classrooms/{room}/assignments/{assignment}/restore", None),
    ("DELETE", "/classrooms/{room}/assignments/{assignment}", None),
    ("DELETE", "/classrooms/{room}/assignments/{assignment}/classwork", None),
    ("PATCH", "/classrooms/{room}/assignments/{assignment}", {"expected_revision": 7}),
    ("PUT", "/classrooms/{room}/assignments/{assignment}/extensions/{student}", {}),
    ("DELETE", "/classrooms/{room}/assignments/{assignment}/extensions/{student}", None),
    (
        "PATCH",
        "/classrooms/{room}/assignments/{assignment}/grade-policy",
        {"grade_selection": "BEST_ACCEPTED", "expected_revision": 7},
    ),
    ("POST", "/classrooms/{room}/sections", {"title": "Forbidden topic"}),
    ("PATCH", "/classrooms/{room}/sections/{item}", {"status": "PUBLISHED"}),
    ("DELETE", "/classrooms/{room}/sections/{item}", None),
    ("POST", "/classrooms/{room}/sections/reorder", {"ids": [], "expected_revision": 7}),
    (
        "POST",
        "/classrooms/{room}/resources",
        {"title": "Forbidden lesson", "kind": "TEXT", "body": "Fictional"},
    ),
    ("PATCH", "/classrooms/{room}/resources/{item}", {"status": "PUBLISHED"}),
    ("PATCH", "/classrooms/{room}/resources/{item}", {"status": "ARCHIVED"}),
    ("PATCH", "/classrooms/{room}/resources/{item}", {"status": "DRAFT"}),
    ("DELETE", "/classrooms/{room}/resources/{item}", None),
    ("POST", "/classrooms/{room}/items", {"section_id": None, "assignment_id": "{assignment}"}),
    (
        "POST",
        "/classrooms/{room}/items/reorder",
        {"section_id": None, "ids": [], "expected_revision": 7},
    ),
    ("DELETE", "/classrooms/{room}/items/{item}", None),
    ("POST", "/classrooms/{room}/posts", {"kind": "ANNOUNCEMENT", "body": "Forbidden"}),
    ("PATCH", "/classrooms/{room}/posts/{item}", {"body": "Forbidden"}),
    ("DELETE", "/classrooms/{room}/posts/{item}", None),
    ("POST", "/classrooms/{room}/posts/{item}/publish", None),
    ("POST", "/classrooms/{room}/posts/{item}/archive", None),
    ("POST", "/classrooms/{room}/posts/{item}/pin", {"pinned": True}),
    ("POST", "/classrooms/{room}/posts/{item}/comments", {"body": "Forbidden"}),
    ("PATCH", "/classrooms/{room}/comments/{item}", {"body": "Forbidden"}),
    ("DELETE", "/classrooms/{room}/comments/{item}", None),
    (
        "POST",
        "/classrooms/{room}/staff",
        {"email": "fictional@example.com", "staff_role": "CO_TEACHER"},
    ),
    ("PATCH", "/classrooms/{room}/staff/{item}", {"staff_role": "CO_TEACHER"}),
    ("DELETE", "/classrooms/{room}/staff/{item}", None),
    ("POST", "/classrooms/{room}/staff/{item}/accept", None),
    ("POST", "/classrooms/{room}/staff/{item}/decline", None),
    (
        "POST",
        "/classrooms/{room}/students/{student}/learning-plans",
        {
            "title": "Forbidden",
            "target_skill": "READING",
            "focus_area": "Fictional",
            "items": [{"resource_id": "{item}"}],
        },
    ),
    (
        "PUT",
        "/classrooms/{room}/students/{student}/learning-plans/{item}",
        {
            "title": "Forbidden",
            "target_skill": "READING",
            "focus_area": "Fictional",
            "items": [{"resource_id": "{item}"}],
        },
    ),
    ("POST", "/classrooms/{room}/learning-plans/{item}/items/{item}/complete-resource", None),
    (
        "PUT",
        "/classrooms/{room}/assignments/{assignment}/attempts/{attempt}/writing-scores/{item}",
        WRITING,
    ),
    (
        "PUT",
        "/classrooms/{room}/assignments/{assignment}/attempts/{attempt}/speaking-score",
        SPEAKING,
    ),
    ("PUT", "/attempts/{attempt}/writing-scores/{item}", WRITING),
    ("PUT", "/speaking-attempts/{attempt}/final-score", SPEAKING),
]


def substitute(value, ids):
    if isinstance(value, dict):
        return {key: substitute(item, ids) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, ids) for item in value]
    return value.format(**ids) if isinstance(value, str) else value


@pytest.mark.parametrize("method,path,body", MUTATIONS, ids=[f"{m} {p}" for m, p, _ in MUTATIONS])
async def test_admin_crafted_mutation_is_403_before_any_database_write(
    method, path, body, monkeypatch
):
    admin = actor("ADMIN")
    room = classroom(actor())
    assigned = assignment(room)
    attempt = Attempt(
        id=uuid4(),
        user_id=uuid4(),
        classroom_assignment_id=assigned.id,
        module_type="WRITING",
        status="SUBMITTED",
        test_session=None,
    )
    ids = dict(
        room=room.id,
        assignment=assigned.id,
        version=assigned.test_version_id,
        attempt=attempt.id,
        student=attempt.user_id,
        item=uuid4(),
    )
    session = session_double()
    session.execute = AsyncMock()
    session.delete = AsyncMock()

    async def scalar(statement):
        description = statement.column_descriptions[0]
        if description["entity"] == Attempt:
            return attempt.user_id if description["name"] == "user_id" else attempt
        return {User: admin, Classroom: room, ClassroomAssignment: assigned}.get(
            description["entity"]
        )

    async def get(model, _identity, **_kwargs):
        return {User: admin, Classroom: room, ClassroomAssignment: assigned}.get(model)

    session.scalar.side_effect = scalar
    session.get = AsyncMock(side_effect=get)
    monkeypatch.setattr(AttemptRepository, "get", AsyncMock(return_value=attempt))
    monkeypatch.setattr(
        AccessPolicy,
        "lock_version",
        AsyncMock(return_value=SimpleNamespace(id=assigned.test_version_id)),
    )
    before = {
        model: {column.key: getattr(model, column.key) for column in model.__table__.columns}
        for model in (room, assigned, attempt)
    }
    api = FastAPI()
    for router in (
        classroom_router,
        assignment_router,
        classwork_router,
        post_router,
        scheduling_router,
        lms_router,
        learning_router,
        attempt_router,
        speaking_router,
    ):
        api.include_router(router)
    api.add_exception_handler(AppError, app_error_handler)
    api.dependency_overrides[get_current_user] = lambda: admin
    api.dependency_overrides[get_session] = lambda: session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.request(method, path.format(**ids), json=substitute(body, ids))
    assert response.status_code == 403, response.text
    assert response.json()["code"] in {
        "CLASSROOM_OBSERVER_READ_ONLY",
        "CLASSROOM_CAPABILITY_REQUIRED",
    }
    for model, values in before.items():
        assert values == {key: getattr(model, key) for key in values}
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
    session.delete.assert_not_awaited()
    session.execute.assert_not_awaited()
