"""Classroom authorization regressions without connecting to a database."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models import Attempt, ClassroomMembership, User
from app.models.classroom_staff import ClassroomStaff
from app.schemas.classroom_assignments import AssignmentCreate
from app.services.access_policy import AccessPolicy
from app.services.attempts import AttemptService
from app.services.classroom_assignments import ClassroomAssignmentService, require_assignment_start
from app.services.classroom_capabilities import require_capability, resolve_capabilities
from app.services.classroom_content_access import ContentAccess
from app.services.classrooms import ClassroomService
from app.services.grading_policy import GradingPolicy
from app.services.speaking_attempts import SpeakingAttemptService
from app.services.speaking_transcript import SpeakingTranscriptService
from app.services.test_sessions import TestSessionService as MockSessionService
from app.services.writing_ai import WritingAIService
from app.services.writing_ai_practice_feedback import WritingAIPracticeFeedbackService
from tests.test_classroom_classwork_unit import actor, classroom, session_double


@pytest.mark.parametrize("legacy_role", [None, "CO_TEACHER", "TEACHING_ASSISTANT"])
async def test_admin_has_read_only_capabilities_even_with_legacy_staff_or_ownership(legacy_role):
    admin = actor("ADMIN")
    room = classroom(admin)
    session = session_double(ClassroomStaff(staff_role=legacy_role) if legacy_role else None)
    role, capabilities = await resolve_capabilities(session, admin, room)
    assert role == "ADMIN"
    assert set(capabilities) == {"roster.view", "grades.view", "analytics.view"}
    for operation in ("classroom.manage", "members.manage", "grades.edit", "assignments.manage"):
        with pytest.raises(AppError) as error:
            await require_capability(session, admin, room, operation)
        assert error.value.status_code == 403


async def test_admin_cannot_use_classroom_owner_policy():
    admin = actor("ADMIN")
    with pytest.raises(AppError) as error:
        await AccessPolicy(session_double(), admin).require_classroom_manage(classroom(admin))
    assert error.value.status_code == 403


async def test_admin_cannot_create_assignment_through_role_bypass(monkeypatch):
    admin = actor("ADMIN")
    room = classroom(actor())
    session = session_double(admin, room)
    service = ClassroomAssignmentService(session, admin)
    version = SimpleNamespace(id=uuid4(), test=SimpleNamespace(origin="ADMIN"))
    service.policy.lock_version = AsyncMock(return_value=version)
    service.policy.version_access = AsyncMock(return_value=True)
    service._present = AsyncMock(return_value="assignment-created")
    monkeypatch.setattr("app.services.assignment_scheduling.policy_event", AsyncMock(return_value=SimpleNamespace(id=uuid4())))
    monkeypatch.setattr("app.services.assignment_scheduling.notify_assignment", AsyncMock())
    with pytest.raises(AppError) as error:
        await service.create(room.id, AssignmentCreate(test_version_id=version.id))
    assert error.value.status_code == 403
    session.add.assert_not_called()


async def test_admin_cannot_comment_with_legacy_active_membership():
    admin = actor("ADMIN")
    room = classroom(actor())
    access = ContentAccess(session_double(), admin)
    access.classrooms.repository.membership = AsyncMock(
        return_value=ClassroomMembership(classroom_id=room.id, user_id=admin.id)
    )
    with pytest.raises(AppError) as error:
        await access.can_comment(room)
    assert error.value.status_code == 403


async def test_admin_cannot_enter_participant_mutation_boundary():
    admin = actor("ADMIN")
    room = classroom(actor())
    access = ContentAccess(session_double(admin, room), admin)
    with pytest.raises(AppError) as error:
        await access.room(room.id, mutation=True)
    assert error.value.status_code == 403


@pytest.mark.parametrize("module", ["WRITING", "SPEAKING"])
@pytest.mark.parametrize("parent_origin", [False, True])
async def test_admin_personal_final_grading_cannot_bypass_classroom_provenance(module, parent_origin):
    admin = actor("ADMIN")
    origin = uuid4()
    attempt = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), module_type=module, status="SUBMITTED",
        classroom_assignment_id=None if parent_origin else origin,
        test_session=SimpleNamespace(classroom_assignment_id=origin, status="COMPLETED")
        if parent_origin else None,
    )
    policy = GradingPolicy(session_double(), admin)
    flags = policy.capabilities(attempt, assignment_authorized=True)
    assert flags.context == "CLASSROOM"
    assert not flags.can_edit_final and not flags.can_copy_ai_to_final
    with pytest.raises(AppError) as error:
        await policy.require_final(attempt)
    assert error.value.status_code == 403


async def test_admin_personal_grading_keeps_separate_platform_authority():
    admin = actor("ADMIN")
    attempt = SimpleNamespace(
        user_id=uuid4(), module_type="SPEAKING", status="SUBMITTED",
        classroom_assignment_id=None, test_session=None,
    )
    policy = GradingPolicy(session_double(), admin)
    assert policy.capabilities(attempt).can_edit_final
    await policy.require_final(attempt)


async def test_admin_cannot_start_assignment_with_legacy_membership(monkeypatch):
    admin = actor("ADMIN")
    room = classroom(actor())
    version_id = uuid4()
    assignment = SimpleNamespace(test_version_id=version_id, status="ACTIVE", target=None)
    session = session_double(admin, room.id, room, assignment, uuid4())
    monkeypatch.setattr(AccessPolicy, "lock_version", AsyncMock(return_value=SimpleNamespace(id=version_id)))
    monkeypatch.setattr(AccessPolicy, "version_access", AsyncMock(return_value=True))
    monkeypatch.setattr("app.services.assignment_scheduling.enforce_schedule_start", AsyncMock())
    with pytest.raises(AppError) as error:
        await require_assignment_start(session, admin.id, uuid4(), version_id)
    assert error.value.status_code == 403


async def test_admin_can_read_roster_without_members_manage():
    admin = actor("ADMIN")
    room = classroom(actor())
    service = ClassroomService(session_double(admin, room), admin)
    service.repository.members = AsyncMock(return_value=[])
    assert (await service.members(room.id)).items == []


async def test_active_member_count_excludes_admin_without_excluding_teacher_students():
    admin = actor("ADMIN")
    room = classroom(actor())
    room.created_at = room.updated_at = datetime.now(UTC)
    session = session_double(admin, room, 1)
    session.get = AsyncMock(return_value=User(display_name="Fictional Teacher"))
    result = await ClassroomService(session, admin).get(room.id)
    assert result.active_member_count == 1
    statement = session.scalar.call_args.args[0]
    sql = str(statement)
    assert "JOIN users" in sql
    assert "users.role !=" in sql
    assert "ADMIN" in statement.compile().params.values()
    assert "TEACHER" not in statement.compile().params.values()


async def test_teacher_owner_can_restore_archived_classroom():
    owner = actor()
    room = classroom(owner, status="ARCHIVED")
    room.created_at = room.updated_at = datetime.now(UTC)
    service = ClassroomService(session_double(owner, owner.id, owner, room), owner)
    result = await service.restore(room.id)
    assert result.status == "ACTIVE" and room.archived_at is None


@pytest.mark.parametrize("engine", ["attempt", "full_mock", "speaking"])
async def test_legacy_admin_enrolment_cannot_mutate_existing_assignment_attempt(engine):
    admin = actor("ADMIN")
    attempt = Attempt(
        id=uuid4(), user_id=admin.id, classroom_assignment_id=uuid4(),
        module_type="SPEAKING", status="IN_PROGRESS",
    )
    session = session_double(attempt)
    session.get = AsyncMock(return_value=admin)
    if engine == "attempt":
        service = AttemptService(session, admin.id)
        service.repository.get = AsyncMock(return_value=attempt)
        operation = service._require(attempt.id, for_update=True)
    elif engine == "full_mock":
        operation = MockSessionService(session, admin.id)._require(attempt.id, for_update=True)
    else:
        service = SpeakingAttemptService(session, admin.id)
        service.repository.lock_attempt = AsyncMock(return_value=attempt)
        service.repository.prompts = AsyncMock(return_value=[SimpleNamespace(id=uuid4())])
        service.repository.progress = AsyncMock(return_value=SimpleNamespace())
        operation = service._load(attempt.id)
    with pytest.raises(AppError) as error:
        await operation
    assert error.value.status_code == 403


@pytest.mark.parametrize("engine", ["writing_ai", "writing_feedback", "speaking_ai"])
async def test_admin_cannot_trigger_or_save_ai_for_legacy_classroom_attempt(engine):
    admin = actor("ADMIN")
    attempt = Attempt(
        id=uuid4(), user_id=admin.id, classroom_assignment_id=uuid4(),
        module_type="SPEAKING" if engine == "speaking_ai" else "WRITING",
        status="IN_PROGRESS",
    )
    session = session_double(attempt)
    session.get = AsyncMock(return_value=admin)
    if engine == "writing_ai":
        service = WritingAIService(session, admin.id, Settings(_env_file=None))
        operation = service.input(attempt.id, uuid4(), lock=True)
    elif engine == "writing_feedback":
        operation = WritingAIPracticeFeedbackService(session, admin.id)._eligible(
            attempt.id, uuid4(), lock=True
        )
    else:
        operation = SpeakingTranscriptService(
            session, admin, Settings(_env_file=None), identity={"provider": "fictional"}
        ).authorized(attempt.id, mutate=True)
    with pytest.raises(AppError) as error:
        await operation
    assert error.value.status_code == 403


async def test_admin_cannot_cancel_legacy_owned_classroom_writing_ai_run(monkeypatch):
    admin = actor("ADMIN")
    run = SimpleNamespace(id=uuid4(), attempt_id=uuid4())
    attempt = Attempt(id=run.attempt_id, user_id=admin.id, classroom_assignment_id=uuid4())
    session = session_double(run, attempt)
    session.get = AsyncMock(return_value=admin)
    monkeypatch.setattr("app.services.writing_ai.fail_run", AsyncMock())
    monkeypatch.setattr("app.services.writing_ai.present_run", lambda row: row)
    with pytest.raises(AppError) as error:
        await WritingAIService(session, admin.id, Settings(_env_file=None)).cancel(run.id)
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    "role,staff,permitted,denied",
    [
        ("TEACHER", "CO_TEACHER", ["roster.view", "members.manage", "assignments.manage", "grades.edit"], ["classroom.manage", "staff.manage"]),
        ("USER", "TEACHING_ASSISTANT", ["grades.view", "grades.edit", "content.manage"], ["members.manage", "assignments.manage", "staff.manage"]),
        ("USER", None, [], ["members.manage", "grades.edit", "assignments.manage", "roster.view"]),
        ("TEACHER", None, [], ["members.manage", "grades.edit", "assignments.manage", "roster.view"]),
    ],
)
async def test_staff_capabilities_remain_scoped_and_students_cannot_escalate(role, staff, permitted, denied):
    current = actor(role)
    room = classroom(actor())
    member = ClassroomStaff(
        classroom_id=room.id, user_id=current.id, staff_role=staff, status="ACCEPTED",
        content_manage=True, discussion_moderate=False, analytics_view=False,
        learning_plans_manage=False,
    ) if staff else None
    session = session_double(member)
    _, capabilities = await resolve_capabilities(session, current, room)
    assert set(permitted) <= capabilities
    assert not set(denied) & capabilities
    params = session.scalar.call_args.args[0].compile().params
    assert room.id in params.values() and current.id in params.values()
