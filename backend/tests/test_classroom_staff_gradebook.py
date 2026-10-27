from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Attempt, ClassroomMembership, User
from app.models.enums import UserRole
from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
from app.schemas.classroom_grades import GradePolicyUpdate
from app.schemas.classroom_staff import StaffInvite, StaffUpdate
from app.services.classroom_assignments import ClassroomAssignmentService
from app.services.classroom_grades import ClassroomGradeService, csv_safe
from app.services.classroom_staff import ClassroomStaffService
from app.services.classrooms import ClassroomService
from tests.teacher_helpers import api_client, make_user
from tests.test_classroom_assignments import add_objective_modules, classroom_fixture


async def staff_setup(session, role="CO_TEACHER"):
    owner, student, room, version = await classroom_fixture(session, official=True)
    staff = await make_user(session, UserRole.TEACHER if role == "CO_TEACHER" else UserRole.USER)
    invitation = await ClassroomStaffService(session, owner).invite(
        room, StaffInvite(email=staff.email, staff_role=role)
    )
    await ClassroomStaffService(session, staff).change(room, invitation.id, response=True)
    return owner, student, room, version, staff, invitation


async def test_staff_lifecycle_capabilities_and_immediate_revocation(db_session):
    owner, student, room, version, co, invitation = await staff_setup(db_session)
    details = await ClassroomService(db_session, co).get(room)
    assert details.classroom_role == "CO_TEACHER"
    assert "assignments.manage" in details.capabilities
    assert "staff.manage" not in details.capabilities
    async with api_client(db_session, co) as client:
        base = f"/api/v1/classrooms/{room}"
        assert (await client.get(base + "/gradebook")).status_code == 200
        assert (await client.patch(base, json={"name": "Unauthorized"})).status_code == 403
        assert (
            await client.post(
                base + "/staff", json={"email": student.email, "staff_role": "TEACHING_ASSISTANT"}
            )
        ).status_code == 403
        assert (
            await client.post(base + "/sections", json={"title": "Co-teacher section"})
        ).status_code == 201
    await ClassroomStaffService(db_session, owner).change(room, invitation.id, revoke=True)
    async with api_client(db_session, co) as client:
        assert (await client.get(f"/api/v1/classrooms/{room}/gradebook")).status_code in {403, 404}


async def test_ta_transition_and_no_global_teacher_privileges(db_session):
    owner, student, room, version = await classroom_fixture(db_session)
    row = await ClassroomStaffService(db_session, owner).invite(
        room, StaffInvite(email=student.email, staff_role="TEACHING_ASSISTANT")
    )
    await ClassroomStaffService(db_session, student).change(room, row.id, response=True)
    details = await ClassroomService(db_session, student).get(room)
    assert set(details.capabilities) == {"grades.view", "grades.edit"}
    assert student.role == UserRole.USER
    async with db_session.begin():
        member = await db_session.scalar(
            select(ClassroomMembership).where(ClassroomMembership.classroom_id == room)
        )
        assert member.left_at is not None
    async with api_client(db_session, student) as client:
        base = f"/api/v1/classrooms/{room}"
        assert (await client.get(base + "/gradebook")).status_code == 200
        assert (await client.post(base + "/sections", json={"title": "Denied"})).status_code == 403
        assert (
            await client.post(base + "/assignments", json={"test_version_id": str(version)})
        ).status_code == 403
        assert (await client.post("/api/v1/tests", json={"title": "Denied"})).status_code == 403
    await ClassroomStaffService(db_session, owner).change(
        room, row.id, data=StaffUpdate(staff_role="TEACHING_ASSISTANT", content_manage=True)
    )
    async with api_client(db_session, student) as client:
        assert (
            await client.post(f"/api/v1/classrooms/{room}/sections", json={"title": "Allowed"})
        ).status_code == 201


async def test_staff_invitation_is_private_duplicate_safe_and_owner_immutable(db_session):
    owner, student, room, version = await classroom_fixture(db_session)
    service = ClassroomStaffService(db_session, owner)
    with pytest.raises(AppError):
        await service.invite(room, StaffInvite(email=owner.email, staff_role="CO_TEACHER"))
    with pytest.raises(AppError):
        await service.invite(room, StaffInvite(email=student.email, staff_role="CO_TEACHER"))
    row = await service.invite(
        room, StaffInvite(email=student.email, staff_role="TEACHING_ASSISTANT")
    )
    with pytest.raises(AppError) as error:
        await service.invite(
            room, StaffInvite(email=student.email, staff_role="TEACHING_ASSISTANT")
        )
    assert error.value.code == "STAFF_ALREADY_EXISTS"
    outsider = await make_user(db_session)
    with pytest.raises(AppError):
        await ClassroomStaffService(db_session, outsider).change(room, row.id, response=True)
    declined = await ClassroomStaffService(db_session, student).change(room, row.id, response=False)
    assert declined.status == "DECLINED"
    again = await service.invite(
        room, StaffInvite(email=student.email, staff_role="TEACHING_ASSISTANT")
    )
    assert (await service.change(room, again.id, revoke=True)).status == "CANCELLED"


async def graded_assignment(session):
    owner, student, room, version = await classroom_fixture(session, official=True)
    await add_objective_modules(session, version)
    assignment = await ClassroomAssignmentService(session, owner).create(
        room, AssignmentCreate(test_version_id=version)
    )
    root_ids = []
    for index, band in enumerate([Decimal("7"), Decimal("6")]):
        started = await ClassroomAssignmentService(session, student).start(
            assignment.id, AssignmentStart(mode="MODULE", module="READING")
        )
        async with session.begin():
            attempt = await session.get(Attempt, started.attempt_id)
            attempt.status = "SUBMITTED"
            attempt.finished_at = TimerService.now() + timedelta(seconds=index)
            attempt.band_score, attempt.raw_score, attempt.max_score = band, 30, 40
        root_ids.append(started.attempt_id)
    return owner, student, room, assignment, root_ids


async def test_gradebook_native_scores_selection_history_and_csv(db_session):
    owner, student, room, assignment, roots = await graded_assignment(db_session)
    service = ClassroomGradeService(db_session, owner)
    page = await service.page(room)
    score = page.students[0].cells[0].score
    assert score.band == 6 and score.root_id == roots[1] and score.provenance == "OBJECTIVE"
    policy = await service.policy(
        room,
        assignment.id,
        GradePolicyUpdate(grade_selection="FIRST_ACCEPTED", expected_revision=1),
    )
    assert (await service.page(room)).students[0].cells[0].score.root_id == roots[0]
    await service.policy(
        room,
        assignment.id,
        GradePolicyUpdate(
            grade_selection="BEST_ACCEPTED", expected_revision=policy.policy_revision
        ),
    )
    assert (await service.page(room)).students[0].cells[0].score.band == 7
    profile = await service.profile(room, student.id)
    assert profile.total_history == 2 and len(profile.history) == 2
    async with db_session.begin():
        user = await db_session.get(User, student.id)
        user.display_name = '=HYPERLINK("bad")'
    csv_text = await service.export(room)
    assert "'=" in csv_text and "BEST_ACCEPTED" in csv_text and csv_text.startswith("\ufeff")
    async with api_client(db_session, student) as client:
        assert (await client.get(f"/api/v1/classrooms/{room}/gradebook/export")).status_code == 403


async def test_mixed_mode_best_falls_back_and_pending_human_is_never_ai(db_session):
    owner, student, room, assignment, roots = await graded_assignment(db_session)
    result = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    async with db_session.begin():
        attempt = await db_session.get(Attempt, result.attempt_id)
        attempt.status, attempt.finished_at = "SUBMITTED", TimerService.now() + timedelta(seconds=3)
        # Even a preexisting/advisory-looking aggregate cannot override missing human records.
        attempt.band_score = Decimal("9")
    service = ClassroomGradeService(db_session, owner)
    await service.policy(
        room, assignment.id, GradePolicyUpdate(grade_selection="BEST_ACCEPTED", expected_revision=1)
    )
    page = await service.page(room)
    score = page.students[0].cells[0].score
    assert score.root_id == result.attempt_id and score.mixed_context_fallback
    assert score.band is None and score.provenance == "PENDING_HUMAN"
    filtered = await service.page(room, skill="READING")
    assert filtered.students[0].cells[0].score.root_id == roots[0]
    async with api_client(db_session, owner) as client:
        response = await client.get(f"/api/v1/classrooms/{room}/gradebook")
        assert response.status_code == 200 and "answer_key" not in response.text


async def test_gradebook_excludes_personal_and_retains_former_student(db_session):
    owner, student, room, assignment, roots = await graded_assignment(db_session)
    async with db_session.begin():
        sample = await db_session.get(Attempt, roots[0])
        sample.classroom_assignment_id = None
        sample.band_score = Decimal("9")
        member = await db_session.scalar(
            select(ClassroomMembership).where(ClassroomMembership.classroom_id == room)
        )
        member.left_at = TimerService.now()
    page = await ClassroomGradeService(db_session, owner).page(room)
    assert len(page.students) == 1 and not page.students[0].active_member
    assert page.students[0].cells[0].score.band == 6
    outsider = await make_user(db_session, UserRole.TEACHER)
    with pytest.raises(AppError):
        await ClassroomGradeService(db_session, outsider).page(room)


async def test_co_teacher_demotion_is_blocked_and_archival_preserves_reads(db_session):
    from app.schemas.admin import AdminUserUpdate
    from app.services.admin import AdminService

    owner, student, room, version, co, invitation = await staff_setup(db_session)
    async with db_session.begin():
        admin = await make_user_inline(db_session, UserRole.ADMIN)
    with pytest.raises(AppError) as error:
        await AdminService(db_session).update_user(admin.id, co.id, AdminUserUpdate(role="USER"))
    assert error.value.code == "TEACHER_HAS_ACTIVE_RESOURCES"
    await ClassroomService(db_session, owner).archive(room)
    assert (await ClassroomGradeService(db_session, co).page(room)).total_students == 1
    with pytest.raises(AppError):
        await ClassroomStaffService(db_session, owner).change(room, invitation.id, revoke=True)


async def make_user_inline(session, role):
    from uuid import uuid4

    user = User(
        email=f"fictional-inline-{uuid4()}@example.com",
        display_name="Fictional admin",
        role=role,
        is_active=True,
        email_verified=True,
    )
    session.add(user)
    await session.flush()
    return user


async def test_concurrent_staff_invitations_are_serialized():
    import asyncio

    from tests.classroom_concurrency_helpers import isolated_staff_database

    # Staff audit is append-only. Keep committed race fixtures out of the shared
    # suite database instead of deleting or disabling their immutable history.
    async with isolated_staff_database() as sessions:
        async with sessions() as session:
            owner, student, room, _ = await classroom_fixture(session)

        async def invite():
            async with sessions() as session:
                try:
                    await ClassroomStaffService(session, owner).invite(
                        room, StaffInvite(email=student.email, staff_role="TEACHING_ASSISTANT")
                    )
                    return "INVITED"
                except AppError as error:
                    return error.code

        assert sorted(await asyncio.gather(invite(), invite())) == [
            "INVITED",
            "STAFF_ALREADY_EXISTS",
        ]


@pytest.mark.parametrize("value", ["=x", "  +x", "-x", "@x", "\tx", "\rx", "\nx"])
def test_csv_formula_injection(value):
    assert csv_safe(value).startswith("'")
