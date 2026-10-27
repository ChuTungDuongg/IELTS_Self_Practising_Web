from datetime import timedelta

import pytest
from sqlalchemy import select

from app.domains.timers import TimerService
from app.models import ClassroomMembership
from app.models.enums import UserRole
from app.schemas.assignment_scheduling import AssignmentScheduleUpdate, ExtensionWrite
from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
from app.services.assignment_progress import AssignmentProgressService
from app.services.assignment_scheduling import AssignmentSchedulingService
from app.services.attempts import AttemptService
from app.services.classroom_assignments import ClassroomAssignmentService
from tests.teacher_helpers import api_client, make_user
from tests.test_classroom_assignments import classroom_fixture


async def setup_assignment(session, **policy):
    teacher, student, room, version = await classroom_fixture(session, official=True)
    assignment = await ClassroomAssignmentService(session, teacher).create(
        room, AssignmentCreate(test_version_id=version, **policy)
    )
    return teacher, student, room, assignment


async def test_schedule_and_extension_noops_are_idempotent_and_history_is_private(db_session):
    from app.models import Notification

    teacher, student, room, assignment = await setup_assignment(db_session)
    service = AssignmentSchedulingService(db_session, teacher)
    first = await service.update(
        room, assignment.id, AssignmentScheduleUpdate(max_attempts=2, expected_revision=1)
    )
    again = await service.update(
        room,
        assignment.id,
        AssignmentScheduleUpdate(max_attempts=2, expected_revision=first.policy_revision),
    )
    assert again.policy_revision == first.policy_revision
    await service.write_extension(
        room, assignment.id, student.id, ExtensionWrite(additional_attempts=1)
    )
    await service.write_extension(
        room, assignment.id, student.id, ExtensionWrite(additional_attempts=1)
    )
    assert len(await service.history(room, assignment.id)) == 3
    async with db_session.begin():
        rows = list(
            await db_session.scalars(select(Notification).where(Notification.user_id == student.id))
        )
        assert len(rows) == 3
    outsider = await make_user(db_session, UserRole.TEACHER)
    for actor in (student, outsider):
        async with api_client(db_session, actor) as client:
            base = f"/api/v1/classrooms/{room}/assignments/{assignment.id}"
            assert (await client.get(base + "/schedule-history")).status_code in {403, 404}
            assert (await client.get(base + "/monitoring")).status_code in {403, 404}
    async with api_client(db_session, teacher) as client:
        assert (
            await client.get(
                f"/api/v1/classrooms/{room}/assignments/{assignment.id}/schedule-history"
            )
        ).status_code == 200


async def test_effective_extension_validation_and_cross_classroom_isolation(db_session):
    teacher, student, room, assignment = await setup_assignment(
        db_session,
        due_at=TimerService.now() + timedelta(days=1),
        cutoff_at=TimerService.now() + timedelta(days=2),
    )
    other_teacher, other_student, other_room, other_assignment = await setup_assignment(db_session)
    async with api_client(db_session, teacher) as client:
        base = f"/api/v1/classrooms/{room}/assignments/{assignment.id}"
        assert (
            await client.put(
                base + f"/extensions/{student.id}",
                json={
                    "override_due": True,
                    "due_at_override": (TimerService.now() + timedelta(days=3)).isoformat(),
                },
            )
        ).status_code == 422
        assert (
            await client.put(
                base + f"/extensions/{other_student.id}", json={"additional_attempts": 1}
            )
        ).status_code == 422
        assert (
            await client.put(
                f"/api/v1/classrooms/{room}/assignments/{other_assignment.id}/extensions/{student.id}",
                json={"additional_attempts": 1},
            )
        ).status_code == 404
        assert (
            await client.get(
                f"/api/v1/classrooms/{other_room}/assignment-calendar",
                params={
                    "start": TimerService.now().isoformat(),
                    "end": (TimerService.now() + timedelta(days=1)).isoformat(),
                },
            )
        ).status_code == 404
    async with api_client(db_session, student) as client:
        response = await client.get(
            f"/api/v1/classrooms/{room}/assignment-progress",
            params={"student_id": str(other_student.id)},
        )
        assert response.status_code == 200 and all(
            row["attempts_used"] == 0 for row in response.json()["items"]
        )


async def test_monitoring_query_count_is_constant_and_pages_students(db_session):
    from sqlalchemy import event

    teacher, student, room, assignment = await setup_assignment(db_session)
    for _ in range(12):
        extra = await make_user(db_session)
        async with db_session.begin():
            db_session.add(ClassroomMembership(classroom_id=room, user_id=extra.id))
    statements = []

    def capture(*args):
        if args[2].lstrip().upper().startswith("SELECT"):
            statements.append(args[2])

    bind = db_session.sync_session.bind
    event.listen(bind, "before_cursor_execute", capture)
    try:
        page = await AssignmentProgressService(db_session, teacher).monitor(
            room, assignment.id, limit=5, offset=5
        )
        assert page.total == 13 and len(page.items) == 5
        assert len(statements) <= 8
    finally:
        event.remove(bind, "before_cursor_execute", capture)


async def test_policy_history_database_is_append_only(db_session):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    teacher, student, room, assignment = await setup_assignment(db_session)
    with pytest.raises(DBAPIError, match="history is immutable"):
        async with db_session.begin():
            await db_session.execute(
                text(
                    "UPDATE classroom_assignment_policy_events SET reason='overwrite' WHERE assignment_id=:id"
                ),
                {"id": assignment.id},
            )


async def test_calendar_range_validation_and_legacy_assignment_defaults(db_session):
    teacher, student, room, assignment = await setup_assignment(db_session)
    now = TimerService.now()
    async with api_client(db_session, student) as client:
        response = await client.get(
            f"/api/v1/classrooms/{room}/assignment-calendar",
            params={"start": now.isoformat(), "end": (now + timedelta(days=94)).isoformat()},
        )
        assert response.status_code == 422
    assert (
        assignment.available_from
        is assignment.due_at
        is assignment.cutoff_at
        is assignment.max_attempts
        is None
    )
    assert assignment.allow_late_submission is True


async def test_legacy_progress_and_shared_limit(db_session):
    teacher, student, room, assignment = await setup_assignment(db_session, max_attempts=1)
    service = AssignmentProgressService(db_session, student)
    before = (await service.student(room)).items[0]
    assert (
        before.can_start and before.attempts_used == 0 and before.submission_status == "NOT_STARTED"
    )
    first = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    progress = (await service.student(room)).items[0]
    assert progress.attempts_used == 1 and not progress.can_start
    assert progress.can_resume and progress.resume_attempt_id == first.attempt_id
    async with api_client(db_session, student) as client:
        blocked = await client.post(
            f"/api/v1/classroom-assignments/{assignment.id}/start",
            json={"mode": "MODULE", "module": "WRITING"},
        )
        assert blocked.status_code == 409 and blocked.json()["code"] == "ASSIGNMENT_ATTEMPT_LIMIT"
    monitor = await AssignmentProgressService(db_session, teacher).monitor(room, assignment.id)
    assert monitor.total == 1 and monitor.items[0].progress.submission_status == "IN_PROGRESS"


async def test_late_completion_history_survives_policy_edits(db_session):
    now = TimerService.now()
    teacher, student, room, assignment = await setup_assignment(
        db_session, due_at=now - timedelta(hours=1), cutoff_at=now + timedelta(hours=1)
    )
    attempt = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    await AttemptService(db_session, student.id).submit(attempt.attempt_id)
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert progress.submission_status == "SUBMITTED_LATE" and progress.accepted
    await AssignmentSchedulingService(db_session, teacher).update(
        room,
        assignment.id,
        AssignmentScheduleUpdate(allow_late_submission=False, expected_revision=1),
    )
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert progress.submission_status == "SUBMITTED_LATE" and progress.accepted
    monitor = await AssignmentProgressService(db_session, teacher).monitor(
        room, assignment.id, status="SUBMITTED"
    )
    assert monitor.total == 1 and monitor.summary["SUBMITTED_LATE"] == 1


async def test_extension_private_policy_calendar_and_permissions(db_session):
    now = TimerService.now()
    teacher, student, room, assignment = await setup_assignment(
        db_session,
        due_at=now - timedelta(hours=1),
        cutoff_at=now + timedelta(hours=1),
        max_attempts=1,
    )
    other = await make_user(db_session)
    async with db_session.begin():
        db_session.add(ClassroomMembership(classroom_id=room, user_id=other.id))
    data = ExtensionWrite(
        override_due=True,
        due_at_override=now + timedelta(minutes=30),
        additional_attempts=1,
        reason="Fictional extension",
    )
    extension = await AssignmentSchedulingService(db_session, teacher).write_extension(
        room, assignment.id, student.id, data
    )
    assert extension.additional_attempts == 1
    for actor in (student, other):
        async with api_client(db_session, actor) as client:
            response = await client.put(
                f"/api/v1/classrooms/{room}/assignments/{assignment.id}/extensions/{student.id}",
                json=data.model_dump(mode="json"),
            )
            assert response.status_code == 403
    own = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    peer = (await AssignmentProgressService(db_session, other).student(room)).items[0]
    assert (
        own.max_attempts == 2
        and own.effective_due_at == data.due_at_override
        and peer.max_attempts == 1
    )
    agenda = await AssignmentProgressService(db_session, student).calendar(
        room, now - timedelta(days=1), now + timedelta(days=1)
    )
    due = next(event for event in agenda.items if event.kind == "DUE")
    assert due.at == data.due_at_override and due.progress.max_attempts == 2
    await AssignmentSchedulingService(db_session, teacher).write_extension(
        room, assignment.id, student.id, None
    )
    assert (await AssignmentProgressService(db_session, student).student(room)).items[
        0
    ].max_attempts == 1


async def test_archived_classroom_blocks_policy_writes_but_not_history(db_session):
    from app.services.classrooms import ClassroomService

    teacher, student, room, assignment = await setup_assignment(db_session)
    await ClassroomService(db_session, teacher).archive(room)
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert progress.availability_status == "ARCHIVED" and not progress.can_start
    async with api_client(db_session, teacher) as client:
        response = await client.patch(
            f"/api/v1/classrooms/{room}/assignments/{assignment.id}",
            json={"max_attempts": 2, "expected_revision": 1},
        )
        assert response.status_code == 409 and response.json()["code"] == "CLASSROOM_ARCHIVED"


async def test_validation_and_immutable_provenance(db_session):
    teacher, student, room, assignment = await setup_assignment(db_session)
    async with api_client(db_session, teacher) as client:
        base = f"/api/v1/classrooms/{room}/assignments/{assignment.id}"
        assert (
            await client.patch(
                base,
                json={"test_version_id": str(assignment.test_version_id), "expected_revision": 1},
            )
        ).status_code == 422
        assert (
            await client.patch(base, json={"due_at": "2026-11-07T12:00:00", "expected_revision": 1})
        ).status_code == 422
        assert (
            await client.patch(base, json={"max_attempts": 0, "expected_revision": 1})
        ).status_code == 422
