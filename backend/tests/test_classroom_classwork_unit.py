"""Database-free policy, query-boundary and ordering checks for Classwork."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import Column, MetaData, Table, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Classroom, ClassroomAssignment, ClassroomMembership, User
from app.models.base import Base
from app.models.classroom_classwork import (
    ClassroomContentItem,
    ClassroomResource,
    ClassroomSection,
)
from app.models.classroom_staff import ClassroomStaff
from app.models.enums import ClassroomStatus, UserRole
from app.repositories.classroom_classwork import ClassworkRepository
from app.schemas.classroom_classwork import (
    AssignmentPlacement,
    ItemReorderRequest,
    ReorderRequest,
    ResourceUpdate,
    SectionCreate,
)
from app.services.classroom_classwork import ClassworkService
from app.services.classroom_content_access import ContentAccess


@asynccontextmanager
async def transaction():
    yield


def session_double(*results):
    session = Mock(spec=AsyncSession)
    session.info = {}
    session.begin.side_effect = transaction
    session.scalar = AsyncMock(side_effect=list(results) if results else None)
    session.scalars = AsyncMock(return_value=[])
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def access_session(current, room, membership=None):
    session = session_double()
    rows = {User: current, Classroom: room, ClassroomMembership: membership, ClassroomStaff: None}

    async def scalar(statement):
        return rows[statement.column_descriptions[0]["entity"]]

    session.scalar.side_effect = scalar
    return session


def actor(role=UserRole.TEACHER):
    return User(id=uuid4(), role=role, is_active=True)


def classroom(owner, **values):
    return Classroom(
        id=uuid4(),
        teacher_id=owner.id,
        name="Fictional course",
        status=values.pop("status", ClassroomStatus.ACTIVE),
        content_revision=7,
        **values,
    )


def section(room, position, *, status="PUBLISHED"):
    return ClassroomSection(
        id=uuid4(),
        classroom_id=room.id,
        title=f"Fictional section {position}",
        description=None,
        status=status,
        position=position,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def item(room, section_id, position, **target):
    return ClassroomContentItem(
        id=uuid4(),
        classroom_id=room.id,
        section_id=section_id,
        position=position,
        **target,
    )


def ordering_service(room, owner, *, sections=(), items=(), scalar_results=()):
    session = session_double(*scalar_results)
    service = ClassworkService(session, owner)
    service.access.room = AsyncMock(return_value=room)
    service.repository.sections = AsyncMock(return_value=list(sections))
    service.repository.items = AsyncMock(return_value=list(items))
    service.repository.snapshot = AsyncMock(return_value=(list(sections), [], list(items)))
    return service


@pytest.mark.parametrize(
    "role,owns_room,has_history,allowed,staff",
    [
        (UserRole.TEACHER, True, False, True, True),
        (UserRole.ADMIN, False, False, True, True),
        (UserRole.USER, False, True, True, False),
        (UserRole.TEACHER, False, False, False, False),
        (UserRole.USER, False, False, False, False),
    ],
)
async def test_content_reads_require_owner_admin_or_membership_history(
    role,
    owns_room,
    has_history,
    allowed,
    staff,
):
    current = actor(role)
    room = classroom(current if owns_room else actor())
    history = (
        ClassroomMembership(
            id=uuid4(),
            classroom_id=room.id,
            user_id=current.id,
            joined_at=datetime.now(UTC),
            left_at=datetime.now(UTC),
        )
        if has_history
        else None
    )
    session = access_session(current, room, history)
    access = ContentAccess(session, current)
    if allowed:
        result = await access.room(room.id)
        assert result.id == room.id
        assert access.staff(result) is staff
    else:
        with pytest.raises(AppError) as error:
            await access.room(room.id)
        assert (error.value.code, error.value.status_code) == ("CLASSROOM_NOT_FOUND", 404)


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.USER])
async def test_content_authorship_excludes_admin_and_student_even_with_read_access(role):
    owner = actor()
    current = actor(role)
    room = classroom(owner)
    session = access_session(current, room, ClassroomMembership(user_id=current.id))
    with pytest.raises(AppError) as error:
        await ContentAccess(session, current).room(room.id, mutation=True, owner=True)
    expected = (
        "CLASSROOM_OBSERVER_READ_ONLY" if role == UserRole.ADMIN else "CLASSROOM_OWNERSHIP_REQUIRED"
    )
    assert (error.value.code, error.value.status_code) == (expected, 403)


async def test_content_mutation_reloads_role_before_authorizing_teacher_owner():
    stale_teacher = actor()
    demoted = User(id=stale_teacher.id, role=UserRole.USER, is_active=True)
    room = classroom(stale_teacher)
    session = access_session(demoted, room, ClassroomMembership(user_id=demoted.id))
    with pytest.raises(AppError) as error:
        await ContentAccess(session, stale_teacher).room(room.id, mutation=True, owner=True)
    assert error.value.code == "CLASSROOM_OWNERSHIP_REQUIRED"


@pytest.mark.parametrize("mutation,lock", [(False, "FOR SHARE"), (True, "FOR UPDATE")])
async def test_content_room_queries_serialize_reads_and_writes_with_room_lifecycle(mutation, lock):
    owner = actor()
    room = classroom(owner)
    session = session_double(owner, room)
    await ContentAccess(session, owner).room(room.id, mutation=mutation, owner=mutation)
    query = str(session.scalar.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert query.endswith(lock)


async def test_archived_content_remains_readable_but_owner_cannot_mutate():
    owner = actor()
    room = classroom(owner, status=ClassroomStatus.ARCHIVED)
    readable = ContentAccess(session_double(owner, room), owner)
    assert (await readable.room(room.id)).id == room.id
    with pytest.raises(AppError) as error:
        await ContentAccess(session_double(owner, room), owner).room(
            room.id,
            mutation=True,
            owner=True,
        )
    assert (error.value.code, error.value.status_code) == ("CLASSROOM_ARCHIVED", 409)


async def test_former_members_cannot_comment_and_membership_query_requires_active_period():
    student = actor(UserRole.USER)
    room = classroom(actor())
    session = session_double(None)
    with pytest.raises(AppError) as error:
        await ContentAccess(session, student).can_comment(room)
    assert error.value.code == "ACTIVE_MEMBERSHIP_REQUIRED"
    query = str(
        session.scalar.call_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "classroom_memberships.left_at IS NULL" in query
    assert str(room.id) in query and str(student.id) in query


async def test_section_reorder_rejects_stale_revision_without_changing_positions():
    owner = actor()
    room = classroom(owner)
    first, second = section(room, 0), section(room, 1)
    service = ordering_service(room, owner, sections=[first, second])
    with pytest.raises(AppError) as error:
        await service.reorder_sections(
            room.id,
            ReorderRequest(ids=[second.id, first.id], expected_revision=6),
        )
    assert (error.value.code, error.value.status_code) == ("CLASSWORK_CHANGED", 409)
    assert (first.position, second.position, room.content_revision) == (0, 1, 7)


@pytest.mark.parametrize("invalid", ["missing", "foreign"])
async def test_section_reorder_requires_exact_classroom_section_set(invalid):
    owner = actor()
    room = classroom(owner)
    first, second = section(room, 0), section(room, 1)
    ids = [first.id] if invalid == "missing" else [first.id, uuid4()]
    service = ordering_service(room, owner, sections=[first, second])
    with pytest.raises(AppError) as error:
        await service.reorder_sections(room.id, ReorderRequest(ids=ids, expected_revision=7))
    assert (error.value.code, error.value.status_code) == ("CLASSWORK_ORDER_INVALID", 422)
    assert (first.position, second.position, room.content_revision) == (0, 1, 7)


def test_reorder_payload_rejects_duplicate_ids():
    duplicate = uuid4()
    with pytest.raises(ValidationError):
        ItemReorderRequest(section_id=None, ids=[duplicate, duplicate], expected_revision=0)


async def test_section_reorder_normalizes_positions_and_advances_revision_once():
    owner = actor()
    room = classroom(owner)
    first, second = section(room, 4), section(room, 9)
    service = ordering_service(room, owner, sections=[first, second])
    result = await service.reorder_sections(
        room.id,
        ReorderRequest(ids=[second.id, first.id], expected_revision=7),
    )
    assert result.revision == 8
    assert {row.id: row.position for row in result.sections} == {first.id: 1, second.id: 0}


async def test_item_move_normalizes_source_and_target_without_changing_identity():
    owner = actor()
    room = classroom(owner)
    source, target = section(room, 0), section(room, 1)
    moving = item(room, source.id, 0, resource_id=uuid4())
    source_peer = item(room, source.id, 5, resource_id=uuid4())
    target_peer = item(room, target.id, 3, assignment_id=uuid4())
    rows = [moving, target_peer, source_peer]
    service = ordering_service(
        room,
        owner,
        sections=[source, target],
        items=rows,
        scalar_results=[target],
    )
    result = await service.reorder_items(
        room.id,
        ItemReorderRequest(
            section_id=target.id,
            ids=[target_peer.id, moving.id],
            expected_revision=7,
        ),
    )
    assert result.revision == 8
    assert {row.id: (row.section_id, row.position) for row in result.items} == {
        moving.id: (target.id, 1),
        source_peer.id: (source.id, 0),
        target_peer.id: (target.id, 0),
    }
    assert moving.resource_id is not None and target_peer.assignment_id is not None


@pytest.mark.parametrize("invalid", ["omit_target", "foreign_item", "stale"])
async def test_item_reorder_rejects_invalid_order_before_mutating_content(invalid):
    owner = actor()
    room = classroom(owner)
    target = section(room, 0)
    existing = item(room, target.id, 2, resource_id=uuid4())
    ids = [] if invalid == "omit_target" else [existing.id, uuid4()]
    revision = 6 if invalid == "stale" else 7
    service = ordering_service(room, owner, items=[existing], scalar_results=[target])
    with pytest.raises(AppError) as error:
        await service.reorder_items(
            room.id,
            ItemReorderRequest(
                section_id=target.id,
                ids=ids,
                expected_revision=revision,
            ),
        )
    expected = (
        ("CLASSWORK_CHANGED", 409) if invalid == "stale" else ("CLASSWORK_ORDER_INVALID", 422)
    )
    assert (error.value.code, error.value.status_code) == expected
    assert (existing.section_id, existing.position, room.content_revision) == (target.id, 2, 7)


async def test_repeated_assignment_placement_moves_existing_association_and_closes_source_gap():
    owner = actor()
    room = classroom(owner)
    source, target = section(room, 0), section(room, 1)
    assignment = ClassroomAssignment(id=uuid4(), classroom_id=room.id)
    existing = item(room, source.id, 0, assignment_id=assignment.id)
    source_peer = item(room, source.id, 6, resource_id=uuid4())
    target_peer = item(room, target.id, 8, resource_id=uuid4())
    service = ordering_service(
        room,
        owner,
        sections=[source, target],
        items=[existing, source_peer, target_peer],
        scalar_results=[target, assignment],
    )
    result = await service.place_assignment(
        room.id,
        AssignmentPlacement(section_id=target.id, assignment_id=assignment.id),
    )
    assert len(result.items) == 3
    assert [
        (row.id, row.section_id, row.position) for row in result.items if row.assignment_id
    ] == [
        (existing.id, target.id, 1),
    ]
    assert (source_peer.position, target_peer.position, result.revision) == (0, 0, 8)


async def test_cross_classroom_assignment_placement_cannot_create_association():
    owner = actor()
    room = classroom(owner)
    session = session_double(None)
    service = ClassworkService(session, owner)
    service.access.room = AsyncMock(return_value=room)
    with pytest.raises(AppError) as error:
        await service.place_assignment(
            room.id,
            AssignmentPlacement(section_id=None, assignment_id=uuid4()),
        )
    assert (error.value.code, error.value.status_code) == ("ASSIGNMENT_NOT_FOUND", 404)
    assert room.content_revision == 7
    query = str(
        session.scalar.call_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert f"classroom_assignments.classroom_id = '{room.id}'" in query


async def test_student_snapshot_query_hides_unpublished_sections_and_resource_targets():
    owner = actor()
    room = classroom(owner)
    published = section(room, 0)
    draft = section(room, 1, status="DRAFT")
    archived = section(room, 2, status="ARCHIVED")
    session = session_double()
    session.scalars.side_effect = [[published, draft, archived], [], []]
    sections, resources, items = await ClassworkRepository(session).snapshot(room.id, staff=False)
    assert [row.id for row in sections] == [published.id]
    assert resources == items == []
    query = str(
        session.scalars.call_args_list[1]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert (
        str(published.id) in query and str(draft.id) not in query and str(archived.id) not in query
    )
    assert "classroom_content_items.section_id IS NULL" in query
    assert "classroom_resources.status = 'PUBLISHED'" in query
    assert "classroom_assignments.status = 'ACTIVE'" in query
    assert f"classroom_content_items.classroom_id = '{room.id}'" in query


@pytest.mark.parametrize("staff", [False, True])
async def test_resource_query_scopes_room_and_hides_drafts_in_hidden_sections_for_students(staff):
    room_id, resource_id = uuid4(), uuid4()
    session = session_double(None)
    assert await ClassworkRepository(session).resource(room_id, resource_id, staff=staff) is None
    query = str(
        session.scalar.call_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert str(room_id) in query and str(resource_id) in query
    assert ("classroom_resources.status = 'PUBLISHED'" in query) is (not staff)
    assert ("classroom_sections.status = 'PUBLISHED'" in query) is (not staff)


async def test_resource_patch_revalidates_merged_target_as_domain_error():
    owner = actor()
    room = classroom(owner)
    resource = ClassroomResource(
        id=uuid4(),
        classroom_id=room.id,
        title="Fictional notes",
        description=None,
        kind="TEXT",
        status="PUBLISHED",
        body="Existing notes",
        url=None,
    )
    service = ordering_service(room, owner)
    service.repository.resource = AsyncMock(return_value=resource)
    with pytest.raises(AppError) as error:
        await service.update_resource(room.id, resource.id, ResourceUpdate(body=None))
    assert error.value.status_code == 422
    assert resource.body == "Existing notes" and room.content_revision == 7


@pytest.mark.parametrize("referenced", [False, True])
async def test_failed_upload_removes_only_unreferenced_file(tmp_path, monkeypatch, referenced):
    import app.services.classroom_classwork as module

    owner = actor()
    room = classroom(owner)
    service = ordering_service(room, owner)
    service.session.flush.side_effect = RuntimeError("simulated database write failure")
    service.session.scalar.return_value = uuid4() if referenced else None
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(resolved_storage_root=tmp_path)
    )
    upload = SimpleNamespace(
        filename="lesson.pdf",
        content_type="application/pdf",
        file=BytesIO(b"%PDF-1.7\nFictional lesson"),
    )
    with pytest.raises(RuntimeError, match="simulated database write failure"):
        await service.upload(room.id, upload, SectionCreate(title="Fictional lesson"))
    files = list(tmp_path.rglob("*.pdf"))
    assert len(files) == int(referenced)
    if referenced:
        assert files[0].read_bytes() == b"%PDF-1.7\nFictional lesson"


def workspace_migration():
    path = Path(__file__).parents[1] / "alembic/versions/20261027_0036_classroom_workspace.py"
    spec = spec_from_file_location("classroom_workspace_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_workspace_migration_emits_frozen_constraints_independent_of_future_models(monkeypatch):
    future_metadata = MetaData()
    Table("classroom_resources", future_metadata, Column("future_domain_field", Text))
    monkeypatch.setattr(Base, "metadata", future_metadata)
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        workspace_migration().upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE classroom_resources" in sql
    assert "CREATE TABLE classroom_content_items" in sql
    assert "future_domain_field" not in sql
    assert (
        "FOREIGN KEY(classroom_id, resource_id) REFERENCES classroom_resources (classroom_id, id) ON DELETE RESTRICT"
        in sql
    )
    assert (
        "FOREIGN KEY(classroom_id, assignment_id) REFERENCES classroom_assignments (classroom_id, id) ON DELETE RESTRICT"
        in sql
    )
    assert "CHECK ((resource_id IS NOT NULL)::int + (assignment_id IS NOT NULL)::int = 1)" in sql


@pytest.mark.parametrize("history_index", range(6))
def test_workspace_downgrade_refuses_content_or_notification_history_before_ddl(
    monkeypatch, history_index
):
    migration = workspace_migration()
    connection = SimpleNamespace(scalar=Mock(side_effect=[False] * history_index + [True]))

    def destructive_operation(*args, **kwargs):
        pytest.fail("Workspace history must be checked before any destructive DDL")

    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_bind=lambda: connection,
            drop_table=destructive_operation,
            drop_index=destructive_operation,
            drop_constraint=destructive_operation,
            drop_column=destructive_operation,
        ),
    )
    with pytest.raises(RuntimeError, match="history exists; downgrade refused"):
        migration.downgrade()
