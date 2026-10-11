import pytest
from sqlalchemy import func, select
from teacher_helpers import api_client, make_user, make_version

from app.core.exceptions import AppError
from app.models import Attempt, Classroom, ClassroomMembership
from app.models import TestVersionModeration as Moderation
from app.models.enums import (
    ClassroomStatus,
    ModerationScope,
    ModerationStatus,
    ModuleType,
    UserRole,
    VersionStatus,
)
from app.models.enums import TestOrigin as Origin
from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
from app.services.classroom_assignments import ClassroomAssignmentService


async def add_objective_modules(session, version_id):
    """Small fictional objective fixtures exercise actual scoring/review services."""
    from uuid import uuid4

    from app.models import ListeningPart, Question, QuestionGroup, ReadingPassage
    from app.models import TestModule as Module

    question_ids = {}
    async with session.begin():
        for index, skill in enumerate([ModuleType.LISTENING, ModuleType.READING], start=1):
            module = Module(
                test_version_id=version_id,
                module_type=skill,
                order_index=index,
                recommended_duration_seconds=1800,
            )
            group = QuestionGroup(
                question_type="short_answer",
                instruction="Answer briefly.",
                config={},
                order_index=0,
            )
            for number, accepted in enumerate(["fixture", "second"], start=1):
                group.questions.append(
                    Question(
                        number=number,
                        prompt=f"Fictional question {number}",
                        config={"max_words": 2, "max_numbers": 0},
                        answer_key={"kind": "TEXT", "accepted": [accepted]},
                        order_index=number - 1,
                    )
                )
            module.question_groups.append(group)
            if skill == ModuleType.READING:
                passage = ReadingPassage(
                    title="Fictional passage",
                    order_index=0,
                    content_json=[
                        {
                            "id": str(uuid4()),
                            "type": "paragraph",
                            "label": "A",
                            "text": "Fictional passage text.",
                        }
                    ],
                    plain_text="Fictional passage text.",
                )
                passage.question_groups.append(group)
                module.passages.append(passage)
            else:
                part = ListeningPart(title="Fictional Section 1", order_index=0)
                part.question_groups.append(group)
                module.listening_parts.append(part)
            session.add(module)
            await session.flush()
            question_ids[skill] = [question.id for question in group.questions]
    return question_ids


async def classroom_fixture(session, *, approved=True, official=False):
    teacher = await make_user(session, UserRole.TEACHER)
    student = await make_user(session)
    test, version = await make_version(
        session,
        teacher,
        status=VersionStatus.PUBLISHED,
        origin=Origin.ADMIN if official else Origin.TEACHER,
    )
    async with session.begin():
        classroom = Classroom(teacher_id=teacher.id, name="Fictional classroom")
        session.add(classroom)
        await session.flush()
        session.add(ClassroomMembership(classroom_id=classroom.id, user_id=student.id))
        if approved:
            session.add(
                Moderation(
                    test_version_id=version.id,
                    scope=ModerationScope.CLASSROOM,
                    status=ModerationStatus.APPROVED,
                    submitted_by_user_id=teacher.id,
                )
            )
        await session.flush()
        classroom_id, version_id = classroom.id, version.id
    return teacher, student, classroom_id, version_id


@pytest.mark.parametrize("scope", [ModerationScope.CLASSROOM, ModerationScope.PUBLIC])
async def test_approved_assignment_retries_and_personal_start_privacy(db_session, scope):
    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    async with db_session.begin():
        moderation = await db_session.scalar(
            select(Moderation).where(Moderation.test_version_id == version_id)
        )
        moderation.scope = scope
    service = ClassroomAssignmentService(db_session, teacher)
    assignment = await service.create(classroom_id, AssignmentCreate(test_version_id=version_id))
    learner = ClassroomAssignmentService(db_session, student)
    body = AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
    first = await learner.start(assignment.id, body)
    second = await learner.start(assignment.id, body)
    assert first.attempt_id != second.attempt_id
    async with db_session.begin():
        attempts = list(
            await db_session.scalars(
                select(Attempt).where(Attempt.id.in_([first.attempt_id, second.attempt_id]))
            )
        )
        assert all(item.classroom_assignment_id == assignment.id for item in attempts)
    async with api_client(db_session, student) as client:
        forged = await client.post(
            "/api/v1/attempts",
            json={
                "test_version_id": str(version_id),
                "module": "WRITING",
                "timer": {"mode": "COUNT_UP"},
                "classroom_assignment_id": str(assignment.id),
            },
        )
        assert forged.status_code == 422
        if scope == ModerationScope.CLASSROOM:
            normal = await client.post(
                "/api/v1/attempts",
                json={
                    "test_version_id": str(version_id),
                    "module": "WRITING",
                    "timer": {"mode": "COUNT_UP"},
                },
            )
            assert normal.status_code in (403, 422)


async def test_unapproved_and_other_teacher_versions_cannot_be_assigned(db_session):
    teacher, _, classroom_id, version_id = await classroom_fixture(db_session, approved=False)
    other = await make_user(db_session, UserRole.TEACHER)
    service = ClassroomAssignmentService(db_session, teacher)
    with pytest.raises(AppError) as error:
        await service.create(classroom_id, AssignmentCreate(test_version_id=version_id))
    assert error.value.code == "VERSION_NOT_CLASSROOM_APPROVED"
    with pytest.raises(AppError):
        await ClassroomAssignmentService(db_session, other).create(
            classroom_id, AssignmentCreate(test_version_id=version_id)
        )


async def test_official_assignment_and_revocation_archive_membership_block_new_starts(db_session):
    teacher, student, classroom_id, version_id = await classroom_fixture(
        db_session, official=True, approved=False
    )
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    outsider = await make_user(db_session)
    with pytest.raises(AppError) as error:
        await ClassroomAssignmentService(db_session, outsider).start(
            assignment.id, AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
        )
    assert error.value.code == "ACTIVE_MEMBERSHIP_REQUIRED"
    await ClassroomAssignmentService(db_session, teacher).archive(classroom_id, assignment.id)
    with pytest.raises(AppError):
        await ClassroomAssignmentService(db_session, student).start(
            assignment.id, AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
        )
    async with db_session.begin():
        classroom = await db_session.get(Classroom, classroom_id)
        classroom.status = ClassroomStatus.ARCHIVED
    with pytest.raises(AppError) as error:
        await ClassroomAssignmentService(db_session, teacher).create(
            classroom_id, AssignmentCreate(test_version_id=version_id)
        )
    assert error.value.code == "CLASSROOM_ARCHIVED"


async def test_focused_start_and_revocation_preserve_prior_attempt(db_session):
    from app.models import WritingTask
    from app.models.enums import AttemptScope

    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    async with db_session.begin():
        task_id = await db_session.scalar(
            select(WritingTask.id)
            .join(WritingTask.module)
            .where(WritingTask.module.has(test_version_id=version_id))
        )
    body = AssignmentStart(
        mode="MODULE",
        module=ModuleType.WRITING,
        scope=AttemptScope.FOCUSED_UNIT,
        focused_unit={"kind": "WRITING_TASK", "id": task_id},
    )
    learner = ClassroomAssignmentService(db_session, student)
    started = await learner.start(assignment.id, body)
    async with db_session.begin():
        row = await db_session.get(Attempt, started.attempt_id)
        assert (
            row.focused_writing_task_id == task_id and row.classroom_assignment_id == assignment.id
        )
        approval = await db_session.scalar(
            select(Moderation).where(Moderation.test_version_id == version_id)
        )
        approval.status = ModerationStatus.REVOKED
    with pytest.raises(AppError) as error:
        await learner.start(assignment.id, body)
    assert error.value.code == "VERSION_NOT_CLASSROOM_APPROVED"
    async with db_session.begin():
        assert (
            await db_session.get(Attempt, started.attempt_id)
        ).classroom_assignment_id == assignment.id


async def test_full_mock_uses_session_provenance_without_duplicating_children(db_session):
    from app.models import TestModule as Module
    from app.models import TestSession as SessionModel

    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    async with db_session.begin():
        for order, module_type in enumerate([ModuleType.LISTENING, ModuleType.READING], start=1):
            db_session.add(
                Module(
                    test_version_id=version_id,
                    module_type=module_type,
                    order_index=order,
                    recommended_duration_seconds=1800,
                )
            )
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    started = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="FULL_MOCK")
    )
    async with db_session.begin():
        session = await db_session.get(SessionModel, started.test_session_id)
        attempt = await db_session.get(Attempt, started.attempt_id)
        assert session.classroom_assignment_id == assignment.id
        assert attempt.test_session_id == session.id and attempt.classroom_assignment_id is None
    async with api_client(db_session, student) as client:
        assert (
            await client.post(
                "/api/v1/test-sessions",
                json={
                    "test_version_id": str(version_id),
                    "classroom_assignment_id": str(assignment.id),
                },
            )
        ).status_code == 422
        assert (
            await client.post("/api/v1/test-sessions", json={"test_version_id": str(version_id)})
        ).status_code == 422


async def test_public_approval_does_not_let_teacher_assign_another_teachers_content(db_session):
    teacher, _, classroom_id, _ = await classroom_fixture(db_session)
    other = await make_user(db_session, UserRole.TEACHER)
    _, version = await make_version(db_session, other, status=VersionStatus.PUBLISHED)
    version_id = version.id
    async with db_session.begin():
        db_session.add(
            Moderation(
                test_version_id=version_id,
                scope=ModerationScope.PUBLIC,
                status=ModerationStatus.APPROVED,
                submitted_by_user_id=other.id,
            )
        )
    with pytest.raises(AppError) as error:
        await ClassroomAssignmentService(db_session, teacher).create(
            classroom_id, AssignmentCreate(test_version_id=version_id)
        )
    assert error.value.code == "TEST_OWNERSHIP_REQUIRED"


async def test_one_version_approval_can_be_assigned_to_multiple_owned_classrooms(db_session):
    teacher, _, classroom_id, version_id = await classroom_fixture(db_session)
    async with db_session.begin():
        second_classroom = Classroom(teacher_id=teacher.id, name="Another fictional classroom")
        db_session.add(second_classroom)
        await db_session.flush()
        second_id = second_classroom.id
    service = ClassroomAssignmentService(db_session, teacher)
    first = await service.create(classroom_id, AssignmentCreate(test_version_id=version_id))
    second = await service.create(second_id, AssignmentCreate(test_version_id=version_id))
    assert first.id != second.id and first.test_version_id == second.test_version_id
    async with db_session.begin():
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(Moderation)
                .where(Moderation.test_version_id == version_id)
            )
            == 1
        )


async def test_revoking_public_keeps_classroom_starts_until_final_approval_is_revoked(db_session):
    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    async with db_session.begin():
        public = Moderation(
            test_version_id=version_id,
            scope=ModerationScope.PUBLIC,
            status=ModerationStatus.APPROVED,
            submitted_by_user_id=teacher.id,
        )
        db_session.add(public)
        await db_session.flush()
        public_id = public.id
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    async with db_session.begin():
        public = await db_session.get(Moderation, public_id)
        public.status = ModerationStatus.REVOKED
    learner = ClassroomAssignmentService(db_session, student)
    body = AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
    first = await learner.start(assignment.id, body)
    async with db_session.begin():
        remaining = await db_session.scalar(
            select(Moderation).where(
                Moderation.test_version_id == version_id,
                Moderation.scope == ModerationScope.CLASSROOM,
            )
        )
        remaining.status = ModerationStatus.REVOKED
    with pytest.raises(AppError) as error:
        await learner.start(assignment.id, body)
    assert error.value.code == "VERSION_NOT_CLASSROOM_APPROVED"
    async with db_session.begin():
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(Attempt)
                .where(Attempt.classroom_assignment_id == assignment.id)
            )
            == 1
        )
        assert (await db_session.get(Attempt, first.attempt_id)).test_version_id == version_id


@pytest.mark.parametrize("disable", ["classroom", "version", "membership"])
async def test_archived_content_classroom_and_ended_membership_block_future_starts(
    db_session, disable
):
    from datetime import UTC, datetime

    from app.models import TestVersion as Version

    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    learner = ClassroomAssignmentService(db_session, student)
    body = AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
    previous = await learner.start(assignment.id, body)
    async with db_session.begin():
        if disable == "classroom":
            room = await db_session.get(Classroom, classroom_id)
            room.status = ClassroomStatus.ARCHIVED
        elif disable == "version":
            version = await db_session.get(Version, version_id)
            version.status = VersionStatus.ARCHIVED
        else:
            membership = await db_session.scalar(
                select(ClassroomMembership).where(
                    ClassroomMembership.classroom_id == classroom_id,
                    ClassroomMembership.user_id == student.id,
                )
            )
            membership.left_at = datetime.now(UTC)
    with pytest.raises(AppError) as error:
        await learner.start(assignment.id, body)
    assert (
        error.value.code
        == {
            "classroom": "CLASSROOM_ARCHIVED",
            "version": "VERSION_NOT_CLASSROOM_APPROVED",
            "membership": "ACTIVE_MEMBERSHIP_REQUIRED",
        }[disable]
    )
    async with db_session.begin():
        assert (
            await db_session.get(Attempt, previous.attempt_id)
        ).classroom_assignment_id == assignment.id
