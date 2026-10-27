"""Database-free lifecycle, scoped authorization and reference-preservation checks."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from app.api.dependencies import get_current_user
from app.api.v1.classroom_assignments import router as assignment_router
from app.api.v1.classroom_classwork import router as classwork_router
from app.core.database import get_session
from app.core.exceptions import AppError, app_error_handler
from app.models import Attempt, Classroom, ClassroomAssignment, Notification, User
from app.models import TestSession as DomainSession
from app.models.assignment_scheduling import AssignmentPolicyEvent, ClassroomAssignmentExtension
from app.models.classroom_classwork import ClassroomResource, ClassroomSection
from app.models.classroom_learning import ClassroomLearningPlanItem
from app.models.classroom_staff import ClassroomStaff
from app.models.enums import AssignmentStatus, ClassroomStatus, UserRole
from app.schemas.classroom_classwork import ResourceUpdate, SectionUpdate
from app.services.classroom_assignments import ClassroomAssignmentService
from app.services.classroom_classwork import ClassworkService
from tests.test_classroom_classwork_unit import actor, classroom, section, session_double


def assignment(room, **values):
    now = datetime.now(UTC)
    return ClassroomAssignment(
        id=uuid4(),
        classroom_id=room.id,
        created_by_user_id=room.teacher_id,
        test_version_id=uuid4(),
        title="Fictional archived homework",
        note=None,
        created_at=now,
        classwork_hidden=values.pop("classwork_hidden", False),
        status=AssignmentStatus.ARCHIVED,
        archived_at=now,
        available_from=now - timedelta(days=5),
        due_at=now - timedelta(days=3),
        cutoff_at=now - timedelta(days=1),
        max_attempts=2,
        allow_late_submission=False,
        policy_revision=7,
        grade_selection="BEST_ACCEPTED",
        target={
            "mode": "MODULE",
            "module": "READING",
            "scope": "FOCUSED_UNIT",
            "focused_unit": {"kind": "READING_PASSAGE", "id": str(uuid4())},
        },
        **values,
    )


def services(current, room, assigned, *, staff=None, protected=None):
    session = session_double()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    rows = {User: current, Classroom: room, ClassroomAssignment: assigned, ClassroomStaff: staff}

    async def scalar(statement):
        model = statement.column_descriptions[0]["entity"]
        if model == protected:
            return assigned.id
        return rows.get(model)

    session.scalar.side_effect = scalar
    service = ClassroomAssignmentService(session, current)
    service._present = AsyncMock(side_effect=lambda row: row)
    return service, session


@pytest.mark.parametrize("hidden", [False, True])
async def test_restore_preserves_expired_schedule_frozen_target_hidden_state_and_history(hidden):
    owner = actor()
    room = classroom(owner)
    row = assignment(room, classwork_hidden=hidden)
    before = {
        column.key: getattr(row, column.key)
        for column in row.__table__.columns
        if column.key not in {"status", "archived_at"}
    }
    service, session = services(owner, room, row)
    assert await service.restore(room.id, row.id) is row
    assert row.status == "ACTIVE" and row.archived_at is None
    assert before == {key: getattr(row, key) for key in before}
    assert room.content_revision == 8
    await service.restore(room.id, row.id)
    assert room.content_revision == 8
    session.flush.assert_awaited_once()
    session.delete.assert_not_awaited()
    session.execute.assert_not_awaited()
    statement = next(
        call.args[0]
        for call in session.scalar.call_args_list
        if call.args[0].column_descriptions[0]["entity"] == ClassroomAssignment
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert str(room.id) in sql and str(row.id) in sql and "FOR UPDATE" in sql


@pytest.mark.parametrize(
    "role,staff_role,allowed",
    [
        ("ADMIN", None, False),
        ("USER", None, False),
        ("TEACHER", None, False),
        ("TEACHER", "CO_TEACHER", True),
        ("USER", "TEACHING_ASSISTANT", False),
    ],
)
async def test_restore_requires_assignment_capability(role, staff_role, allowed):
    owner = actor()
    room = classroom(owner)
    current = actor(UserRole(role))
    row = assignment(room)
    staff = (
        ClassroomStaff(staff_role=staff_role, status="ACCEPTED", content_manage=True)
        if staff_role
        else None
    )
    service, session = services(current, room, row, staff=staff)
    if allowed:
        await service.restore(room.id, row.id)
        assert row.status == "ACTIVE"
    else:
        with pytest.raises(AppError) as error:
            await service.restore(room.id, row.id)
        assert error.value.code == "CLASSROOM_CAPABILITY_REQUIRED"
        assert row.status == "ARCHIVED"
        session.flush.assert_not_awaited()


async def test_restore_in_archived_room_is_rejected_before_assignment_mutation():
    owner = actor()
    room = classroom(owner, status=ClassroomStatus.ARCHIVED)
    row = assignment(room)
    service, session = services(owner, room, row)
    with pytest.raises(AppError) as error:
        await service.restore(room.id, row.id)
    assert error.value.code == "CLASSROOM_ARCHIVED"
    assert row.status == "ARCHIVED"
    session.flush.assert_not_awaited()


async def test_missing_or_cross_classroom_assignment_cannot_be_restored():
    owner = actor()
    room = classroom(owner)
    service, session = services(owner, room, None)
    foreign_id = uuid4()
    with pytest.raises(AppError) as error:
        await service.restore(room.id, foreign_id)
    assert error.value.code == "ASSIGNMENT_NOT_ACCESSIBLE"
    statement = session.scalar.call_args.args[0]
    assert set(statement.compile().params.values()) == {room.id, foreign_id}
    session.flush.assert_not_awaited()


@pytest.mark.parametrize(
    "protected",
    [
        Attempt,
        DomainSession,
        AssignmentPolicyEvent,
        ClassroomAssignmentExtension,
        ClassroomLearningPlanItem,
        Notification,
    ],
)
async def test_history_references_no_longer_block_authorized_permanent_deletion(protected):
    owner = actor()
    room = classroom(owner)
    row = assignment(room)
    service, session = services(owner, room, row, protected=protected)
    await service.delete(room.id, row.id)
    session.delete.assert_awaited_once_with(row)
    assert room.content_revision == 8


async def test_safe_removal_without_a_placement_retains_canonical_assignment():
    owner = actor()
    room = classroom(owner)
    row = assignment(room, classwork_hidden=False)
    _, session = services(owner, room, row)
    service = ClassworkService(session, owner)
    service._snapshot = AsyncMock(return_value="snapshot")
    assert await service.remove_assignment_reference(room.id, row.id, 7) == "snapshot"
    assert row.classwork_hidden and row.status == "ARCHIVED"
    session.delete.assert_not_awaited()
    deletion = str(
        session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert deletion.startswith("DELETE FROM classroom_content_items")
    assert str(room.id) in deletion and str(row.id) in deletion


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.USER, UserRole.TEACHER])
async def test_safe_removal_rejects_admin_student_and_unrelated_teacher(role):
    owner = actor()
    room = classroom(owner)
    current = actor(role)
    row = assignment(room)
    _, session = services(current, room, row)
    with pytest.raises(AppError) as error:
        await ClassworkService(session, current).remove_assignment_reference(room.id, row.id)
    assert error.value.status_code in {403, 404}
    assert not row.classwork_hidden
    session.execute.assert_not_awaited()


async def test_safe_removal_checks_revision_and_archived_classroom():
    owner = actor()
    room = classroom(owner)
    row = assignment(room)
    _, session = services(owner, room, row)
    with pytest.raises(AppError) as error:
        await ClassworkService(session, owner).remove_assignment_reference(room.id, row.id, 6)
    assert error.value.code == "CLASSWORK_CHANGED"
    room.status = ClassroomStatus.ARCHIVED
    with pytest.raises(AppError) as error:
        await ClassworkService(session, owner).remove_assignment_reference(room.id, row.id)
    assert error.value.code == "CLASSROOM_ARCHIVED"
    assert not row.classwork_hidden
    session.execute.assert_not_awaited()


async def test_admin_cannot_archive_an_assignment_through_legacy_override():
    owner = actor()
    room = classroom(owner)
    row = assignment(room)
    service, session = services(actor(UserRole.ADMIN), room, row)
    with pytest.raises(AppError) as error:
        await service.archive(room.id, row.id)
    assert error.value.code == "CLASSROOM_CAPABILITY_REQUIRED"
    session.flush.assert_not_awaited()


@pytest.mark.parametrize("kind", ["TEXT", "LINK", "FILE"])
async def test_resource_restore_to_draft_preserves_id_and_immutable_file_reference(kind):
    owner = actor()
    room = classroom(owner)
    now = datetime.now(UTC)
    row = ClassroomResource(
        id=uuid4(),
        classroom_id=room.id,
        title="Fictional archived lesson",
        description=None,
        kind=kind,
        body="Fictional notes" if kind == "TEXT" else None,
        url="https://example.com/lesson" if kind == "LINK" else None,
        status="ARCHIVED",
        storage_key="retained-file" if kind == "FILE" else None,
        original_filename=None,
        media_type=None,
        size_bytes=None,
        created_at=now,
        updated_at=now,
    )
    _, session = services(owner, room, None)
    service = ClassworkService(session, owner)
    service.repository.resource = AsyncMock(return_value=row)
    result = await service.update_resource(room.id, row.id, ResourceUpdate(status="DRAFT"))
    assert result.id == row.id and result.status == "DRAFT"
    assert row.storage_key == ("retained-file" if kind == "FILE" else None)
    session.add.assert_not_called()
    session.delete.assert_not_awaited()


async def test_topic_restore_does_not_publish_or_modify_children():
    owner = actor()
    room = classroom(owner)
    row = section(room, 0, status="ARCHIVED")
    _, session = services(owner, room, None)
    original = session.scalar.side_effect

    async def scalar(statement):
        if statement.column_descriptions[0]["entity"] == ClassroomSection:
            return row
        return await original(statement)

    session.scalar.side_effect = scalar
    result = await ClassworkService(session, owner).update_section(
        room.id, row.id, SectionUpdate(status="DRAFT")
    )
    assert result.status == "DRAFT" and result.id == row.id
    session.execute.assert_not_awaited()
    session.add.assert_not_called()


async def test_http_restore_and_canonical_removal_use_validated_contracts(monkeypatch):
    owner = actor()
    room = classroom(owner)
    row = assignment(room)
    _, session = services(owner, room, row)
    monkeypatch.setattr(ClassroomAssignmentService, "_present", AsyncMock(return_value=row))
    monkeypatch.setattr(
        ClassworkService,
        "_snapshot",
        AsyncMock(
            return_value={
                "revision": 9,
                "sections": [],
                "resources": [],
                "items": [],
                "removed_assignment_ids": [row.id],
            }
        ),
    )
    app = FastAPI()
    app.include_router(assignment_router)
    app.include_router(classwork_router)
    app.add_exception_handler(AppError, app_error_handler)
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_session] = lambda: session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/classrooms/{room.id}/assignments/{row.id}"
        restored = await client.post(path + "/restore")
        assert restored.status_code == 200, restored.text
        assert restored.json()["status"] == "ACTIVE"
        assert restored.json()["test_version_id"] == str(row.test_version_id)
        assert restored.json()["target"] == row.target
        assert "answer_key" not in restored.text
        removed = await client.delete(path + "/classwork")
        assert removed.status_code == 200, removed.text
        assert removed.json()["removed_assignment_ids"] == [str(row.id)]
        assert row.classwork_hidden and row.status == "ACTIVE"
