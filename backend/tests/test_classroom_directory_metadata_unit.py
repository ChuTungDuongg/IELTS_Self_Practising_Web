"""Directory metadata is batched and reflects the established classroom policy."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.classroom_staff import ClassroomStaff
from app.services.classrooms import ClassroomService
from tests.test_classroom_classwork_unit import actor, classroom, session_double


@pytest.mark.parametrize("role", ["USER", "TEACHER", "ADMIN"])
async def test_list_enriches_metadata_in_constant_queries_and_keeps_historical_members(role):
    current = actor(role)
    owner = actor()
    active, historical = classroom(owner), classroom(owner)
    for room in (active, historical):
        room.created_at = room.updated_at = datetime.now(UTC)
    session = session_double(current)
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(all=lambda: [(owner.id, "Fictional teacher")]),
            SimpleNamespace(all=lambda: [(active.id, 2)]),
        ]
    )
    session.scalars = AsyncMock(side_effect=[[], [active.id]])
    service = ClassroomService(session, current)
    service.repository.list = AsyncMock(return_value=[active, historical])
    items = (await service.list()).items
    assert [item.teacher_name for item in items] == ["Fictional teacher"] * 2
    assert [item.active_member_count for item in items] == [2, 0]
    assert session.execute.await_count == 2 and session.scalars.await_count == 2
    # Every metadata query is scoped to the accessible room IDs returned by the repository.
    for call in [session.execute.await_args_list[1], *session.scalars.await_args_list]:
        parameters = call.args[0].compile().params.values()
        assert any(
            isinstance(value, (list, tuple)) and set(value) == {active.id, historical.id}
            for value in parameters
        )
    if role == "ADMIN":
        assert all(
            item.classroom_role == "ADMIN" and "classroom.manage" not in item.capabilities
            for item in items
        )
    else:
        assert [item.membership_active for item in items] == [True, False]


async def test_list_resolves_accepted_staff_capabilities():
    current, owner = actor("TEACHER"), actor()
    room = classroom(owner)
    room.created_at = room.updated_at = datetime.now(UTC)
    staff = ClassroomStaff(
        classroom_id=room.id, user_id=current.id, status="ACCEPTED", staff_role="CO_TEACHER"
    )
    session = session_double(current)
    session.execute = AsyncMock(
        side_effect=[SimpleNamespace(all=lambda: []), SimpleNamespace(all=lambda: [])]
    )
    session.scalars = AsyncMock(side_effect=[[staff], []])
    service = ClassroomService(session, current)
    service.repository.list = AsyncMock(return_value=[room])
    item = (await service.list()).items[0]
    assert item.classroom_role == "CO_TEACHER"
    assert "roster.view" in item.capabilities and "classroom.manage" not in item.capabilities
    assert item.membership_active is None


async def test_owner_receives_owner_capabilities():
    current = actor("TEACHER")
    room = classroom(current)
    room.created_at = room.updated_at = datetime.now(UTC)
    session = session_double(current)
    session.execute = AsyncMock(side_effect=[SimpleNamespace(all=lambda: []), SimpleNamespace(all=lambda: [])])
    session.scalars = AsyncMock(side_effect=[[], []])
    service = ClassroomService(session, current)
    service.repository.list = AsyncMock(return_value=[room])
    item = (await service.list()).items[0]
    assert item.classroom_role == "OWNER" and "classroom.manage" in item.capabilities
