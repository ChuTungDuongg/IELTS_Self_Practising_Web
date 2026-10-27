"""Bounded directory contracts; these tests never open a database connection."""

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models.enums import UserRole
from app.repositories.admin_directory import AdminDirectoryRepository


class RecordingSession:
    def __init__(self, rows=(), total=0):
        self.rows = rows
        self.total = total
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.total

    async def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.rows))


def sql(statement):
    return str(statement.compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize("role", [UserRole.TEACHER, UserRole.USER])
async def test_people_queries_are_role_scoped_bounded_and_minimal(role):
    session = RecordingSession()
    await AdminDirectoryRepository(session).people(
        role=role, search="  Ada%  ", offset=25, limit=25
    )
    assert len(session.statements) == 2
    count, page = session.statements
    assert count.compile().params["role_1"] == role
    assert page.compile().params["role_1"] == role
    assert page.compile().params["param_1"] == 25
    assert page.compile().params["param_2"] == 25
    assert "LIMIT" in sql(page) and "OFFSET" in sql(page)
    assert "users.email" not in sql(page)
    assert "users.phone_number" not in sql(page)
    assert "classroom_count" in sql(page)
    assert "%ada\\%%" in page.compile().params.values()
    if role == UserRole.USER:
        assert "classroom_memberships.left_at IS NULL" in sql(page)


async def test_classroom_queries_filter_on_server_and_count_only_current_students():
    teacher_id, student_id = uuid4(), uuid4()
    session = RecordingSession()
    await AdminDirectoryRepository(session).classrooms(
        teacher_id=teacher_id, student_id=student_id, search="Reading", offset=50, limit=25
    )
    assert len(session.statements) == 2
    count, page = session.statements
    for statement in (count, page):
        query = sql(statement)
        assert "classrooms.teacher_id =" in query
        assert "EXISTS" in query
        assert "classroom_memberships.left_at IS NULL" in query
        assert teacher_id in statement.compile().params.values()
        assert student_id in statement.compile().params.values()
    page_sql = sql(page)
    assert "enrolled_student_count" in page_sql
    assert "users.role !=" in page_sql
    assert "LIMIT" in page_sql and "OFFSET" in page_sql
    assert "users.email" not in page_sql
    assert "ORDER BY classrooms.created_at DESC, classrooms.id" in page_sql


@pytest.mark.parametrize("with_student_filter", [False, True])
async def test_enrollment_includes_teacher_students_but_excludes_legacy_admin_memberships(
    with_student_filter,
):
    session = RecordingSession()
    await AdminDirectoryRepository(session).classrooms(
        teacher_id=None,
        student_id=uuid4() if with_student_filter else None,
        search=None,
        offset=0,
        limit=25,
    )
    count, page = session.statements
    # Global TEACHER accounts can legitimately enroll in another teacher's class.
    # Only platform ADMIN memberships must be omitted from enrollment/selection.
    for statement in (count, page):
        role_filters = {
            name: value
            for name, value in statement.compile().params.items()
            if name.startswith("role_")
        }
        assert all(value == UserRole.ADMIN for value in role_filters.values())
        if role_filters:
            query = sql(statement)
            assert query.count("users.role !=") == len(role_filters)
            assert "classroom_memberships.left_at IS NULL" in query
    assert len({name for name in page.compile().params if name.startswith("role_")}) == (
        2 if with_student_filter else 1
    )


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.TEACHER])
async def test_directory_requires_platform_admin_without_loading_database(role):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=role)
    app.dependency_overrides[get_session] = lambda: None
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for path in ("/admin/directory/people", "/admin/directory/classrooms"):
                response = await client.get(f"/api/v1{path}")
                assert response.status_code == 403
                assert response.json()["code"] == "ADMIN_REQUIRED"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_session, None)


async def test_directory_rejects_unbounded_pages_and_admin_as_person_role():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=UserRole.ADMIN)
    app.dependency_overrides[get_session] = lambda: None
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for query in ("role=ADMIN", "limit=101", "limit=0", "offset=-1"):
                response = await client.get(f"/api/v1/admin/directory/people?{query}")
                assert response.status_code == 422
            response = await client.get("/api/v1/admin/directory/classrooms?limit=101")
            assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_session, None)


async def test_admin_directory_serializes_real_query_rows_without_private_fields(monkeypatch):
    teacher_id, classroom_id = uuid4(), uuid4()
    person = {
        "id": teacher_id,
        "display_name": "Fictional Teacher",
        "role": "TEACHER",
        "is_active": True,
        "classroom_count": 1,
        "email": "private@example.com",
    }

    async def people(_self, **filters):
        assert filters == {"role": "TEACHER", "search": "Teacher", "offset": 25, "limit": 25}
        return 26, [person]

    async def classrooms(_self, **filters):
        assert filters["teacher_id"] == teacher_id
        return 1, [
            {
                "id": classroom_id,
                "name": "Fictional Reading Class",
                "status": "ARCHIVED",
                "teacher_id": teacher_id,
                "teacher_name": person["display_name"],
                "enrolled_student_count": 2,
            }
        ]

    async def selected_person(_self, person_id, *, role):
        assert person_id == teacher_id and role == "TEACHER"
        return person

    monkeypatch.setattr(AdminDirectoryRepository, "people", people)
    monkeypatch.setattr(AdminDirectoryRepository, "classrooms", classrooms)
    monkeypatch.setattr(AdminDirectoryRepository, "person", selected_person)
    monkeypatch.setitem(
        app.dependency_overrides, get_current_user, lambda: SimpleNamespace(role=UserRole.ADMIN)
    )
    monkeypatch.setitem(app.dependency_overrides, get_session, lambda: None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/admin/directory/people?role=TEACHER&search=Teacher&offset=25&limit=25"
        )
        assert response.status_code == 200
        assert response.json()["total"] == 26
        assert response.json()["items"][0]["classroom_count"] == 1
        assert "email" not in response.json()["items"][0]
        response = await client.get(f"/api/v1/admin/directory/people/{teacher_id}")
        assert response.status_code == 200
        assert "email" not in response.json()
        response = await client.get(f"/api/v1/admin/directory/classrooms?teacher_id={teacher_id}")
        assert response.status_code == 200
        assert response.json()["items"] == [
            {
                "id": str(classroom_id),
                "name": "Fictional Reading Class",
                "status": "ARCHIVED",
                "teacher": {"id": str(teacher_id), "display_name": person["display_name"]},
                "enrolled_student_count": 2,
            }
        ]
