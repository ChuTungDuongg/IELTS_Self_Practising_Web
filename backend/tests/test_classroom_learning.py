from decimal import Decimal

import pytest

from app.core.exceptions import AppError
from app.schemas.classroom_learning import LearningGoals, PlanTarget, PlanWrite
from app.services.classroom_grades import ClassroomGradeService
from app.services.classroom_learning import ClassroomLearningService
from app.services.classroom_learning_plans import LearningPlanService
from app.services.learning_goals import LearningGoalService
from tests.teacher_helpers import api_client, make_user
from tests.test_classroom_assignments import classroom_fixture
from tests.test_classroom_staff_gradebook import graded_assignment


async def age_roots(session, roots):
    from datetime import timedelta

    from app.domains.timers import TimerService
    from app.models import Attempt

    async with session.begin():
        for index, root in enumerate(roots):
            attempt = await session.get(Attempt, root)
            attempt.finished_at = TimerService.now() - timedelta(seconds=20 - index)


async def finish_attempt(session, attempt_id, *, band=None, objective=False):
    from app.domains.timers import TimerService
    from app.models import Attempt

    async with session.begin():
        attempt = await session.get(Attempt, attempt_id)
        attempt.status, attempt.finished_at = "SUBMITTED", TimerService.now()
        attempt.band_score = band
        if objective:
            attempt.raw_score, attempt.max_score = 1, 2


async def test_learning_dashboard_uses_gradebook_selected_scores(db_session):
    owner, student, room, assignment, roots = await graded_assignment(db_session)
    teacher = await ClassroomLearningService(db_session, owner).dashboard(room)
    own = await ClassroomLearningService(db_session, student).dashboard(room, own=True)
    reading = next(item for item in own.skills if item.skill == "READING")
    assert reading.latest == 6 and reading.sample_size == 1
    assert own.completion_rate == 100 and teacher.active_students == 1
    grade = (await ClassroomGradeService(db_session, owner).page(room)).students[0].cells[0].score
    assert reading.latest == grade.band and own.recent_assessments[0].root_id == grade.root_id
    assert own.weaknesses == [] and own.recommendations == []
    async with api_client(db_session, student) as client:
        assert (await client.get(f"/api/v1/classrooms/{room}/analytics")).status_code == 403
        response = await client.get(f"/api/v1/classrooms/{room}/my-progress")
        assert response.status_code == 200 and "answer_key" not in response.text


async def test_learning_goals_reuse_existing_profile_metadata(db_session):
    _, student, room, _ = await classroom_fixture(db_session)
    goals = LearningGoals(overall=7, reading=7.5, listening=7.5, writing=6.5, speaking=6.5)
    saved = await LearningGoalService(db_session, student).save(goals)
    assert saved == goals
    from app.models import User

    async with db_session.begin():
        user = await db_session.get(User, student.id)
        assert user.target_band == Decimal("7") and user.target_reading_band == Decimal("7.5")
    with pytest.raises(ValueError):
        LearningGoals(overall=7.1)
    with pytest.raises(ValueError):
        LearningGoals(reading=10)


async def test_learning_plan_tracks_real_acceptance_and_prevents_manual_exam_completion(db_session):
    owner, student, room, assignment, roots = await graded_assignment(db_session)
    service = LearningPlanService(db_session, owner)
    plan = await service.write(
        room,
        student.id,
        PlanWrite(
            title="Reading focus",
            target_skill="READING",
            focus_area="Short answers",
            items=[PlanTarget(assignment_id=assignment.id)],
        ),
    )
    assert plan.completed_items == 1 and plan.items[0].completion_source == "ACCEPTED_ASSIGNMENT"
    with pytest.raises(AppError):
        await LearningPlanService(db_session, student).complete_resource(
            room, plan.id, plan.items[0].id
        )
    updated = await service.write(
        room,
        student.id,
        PlanWrite(
            title=plan.title,
            target_skill=plan.target_skill,
            focus_area=plan.focus_area,
            status="COMPLETED",
            expected_revision=plan.revision,
            items=[PlanTarget(assignment_id=assignment.id)],
        ),
        plan_id=plan.id,
    )
    assert updated.status == "COMPLETED"
    with pytest.raises(AppError):
        await LearningPlanService(db_session, student).write(
            room,
            student.id,
            PlanWrite(
                title="Forbidden",
                target_skill="READING",
                focus_area="No",
                items=[PlanTarget(assignment_id=assignment.id)],
            ),
        )


async def test_empty_learning_data_is_not_zero_bands_and_is_private(db_session):
    owner, student, room, _ = await classroom_fixture(db_session)
    data = await ClassroomLearningService(db_session, student).dashboard(room, own=True)
    assert data.completion_rate is None and all(skill.latest is None for skill in data.skills)
    outsider = await make_user(db_session)
    async with api_client(db_session, student) as client:
        assert (
            await client.get(f"/api/v1/classrooms/{room}/learning-plans?student_id={outsider.id}")
        ).status_code == 403
    with pytest.raises(AppError):
        await ClassroomLearningService(db_session, owner).dashboard(room, student_id=outsider.id)


async def test_question_accuracy_deduplicates_repeated_classroom_questions(db_session):
    from sqlalchemy import select

    from app.models import AttemptAnswer, Question, QuestionGroup, TestModule
    from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
    from app.services.classroom_assignments import ClassroomAssignmentService

    owner, student, room, assignment, roots = await graded_assignment(db_session)
    await age_roots(db_session, roots)
    second = await ClassroomAssignmentService(db_session, owner).create(
        room, AssignmentCreate(test_version_id=assignment.test_version_id)
    )
    started = await ClassroomAssignmentService(db_session, student).start(
        second.id, AssignmentStart(mode="MODULE", module="READING")
    )
    await finish_attempt(db_session, started.attempt_id, band=5, objective=True)
    async with db_session.begin():
        questions = list(
            await db_session.scalars(
                select(Question.id)
                .join(QuestionGroup)
                .join(TestModule)
                .where(
                    TestModule.test_version_id == assignment.test_version_id,
                    TestModule.module_type == "READING",
                )
                .order_by(Question.number)
            )
        )
        db_session.add_all(
            [
                AttemptAnswer(
                    attempt_id=roots[1],
                    question_id=questions[0],
                    value={"text": "fixture"},
                    is_correct=True,
                ),
                AttemptAnswer(
                    attempt_id=started.attempt_id,
                    question_id=questions[0],
                    value={"text": "wrong"},
                    is_correct=False,
                ),
            ]
        )
    own = await ClassroomLearningService(db_session, student).dashboard(room, own=True)
    reading = next(row for row in own.question_types if row.skill == "READING")
    assert reading.sample_size == 2 and reading.repeated_exposures == 2
    assert reading.questions_correct == 0 and reading.unanswered == 1 and reading.accuracy == 0
    assert reading.confidence_level == "INSUFFICIENT" and own.weaknesses == []


async def test_unscored_response_is_excluded_and_focused_practice_has_no_module_band(db_session):
    from sqlalchemy import select

    from app.models import AttemptAnswer, ReadingPassage, TestModule
    from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
    from app.services.classroom_assignments import ClassroomAssignmentService
    from tests.test_classroom_assignments import add_objective_modules

    owner, student, room, version = await classroom_fixture(db_session, official=True)
    ids = await add_objective_modules(db_session, version)
    assignment = await ClassroomAssignmentService(db_session, owner).create(
        room, AssignmentCreate(test_version_id=version)
    )
    async with db_session.begin():
        passage = await db_session.scalar(
            select(ReadingPassage.id).join(TestModule).where(TestModule.test_version_id == version)
        )
    started = await ClassroomAssignmentService(db_session, student).start(
        assignment.id,
        AssignmentStart(
            mode="MODULE",
            module="READING",
            scope="FOCUSED_UNIT",
            focused_unit={"kind": "READING_PASSAGE", "id": passage},
        ),
    )
    await finish_attempt(db_session, started.attempt_id, band=8, objective=True)
    async with db_session.begin():
        db_session.add(
            AttemptAnswer(
                attempt_id=started.attempt_id,
                question_id=ids["READING"][0],
                value={"text": "unscored"},
                is_correct=None,
            )
        )
    data = await ClassroomLearningService(db_session, student).dashboard(room, own=True)
    assert next(row for row in data.skills if row.skill == "READING").sample_size == 0
    assert data.question_types[0].sample_size == 1 and data.question_types[0].unanswered == 1
    assert data.recent_assessments[0].band is None


async def test_writing_task_criteria_are_human_only_without_fabricated_module_band(db_session):
    from sqlalchemy import select

    from app.models import Attempt, AttemptWritingScore, TestModule, WritingTask
    from app.schemas.classroom_assignments import AssignmentStart
    from app.services.classroom_assignments import ClassroomAssignmentService

    owner, student, room, assignment, roots = await graded_assignment(db_session)
    await age_roots(db_session, roots)
    started = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    await finish_attempt(db_session, started.attempt_id, band=9)
    before = await ClassroomLearningService(db_session, student).dashboard(room, own=True)
    assert before.criteria == [] and before.pending_human == 1
    async with db_session.begin():
        task = await db_session.scalar(
            select(WritingTask.id)
            .join(TestModule)
            .where(TestModule.test_version_id == assignment.test_version_id)
        )
        db_session.add(
            AttemptWritingScore(
                attempt_id=started.attempt_id, writing_task_id=task, ta=6, cc=6.5, lr=5.5, gra=5
            )
        )
    after = await ClassroomLearningService(db_session, student).dashboard(room, own=True)
    assert {row.context for row in after.criteria} == {"TASK_2"}
    assert {row.criterion: row.average for row in after.criteria} == {
        "ta": 6,
        "cc": 6.5,
        "lr": 5.5,
        "gra": 5,
    }
    assert after.skills[2].latest is None and after.weaknesses == []
    async with db_session.begin():
        attempt = await db_session.get(Attempt, started.attempt_id)
        attempt.classroom_assignment_id = None
    private = await ClassroomLearningService(db_session, owner).dashboard(room)
    assert private.criteria == []


async def test_learning_plan_resource_markers_conflicts_and_hidden_targets(db_session):
    from app.schemas.classroom_classwork import ResourceCreate, ResourceUpdate
    from app.services.classroom_classwork import ClassworkService

    owner, student, room, _ = await classroom_fixture(db_session)
    content = ClassworkService(db_session, owner)
    resource = await content.create_resource(
        room,
        ResourceCreate(
            title="Fictional strategy", kind="TEXT", body="Read the strategy.", status="PUBLISHED"
        ),
    )
    body = PlanWrite(
        title="Strategy plan",
        target_skill="READING",
        focus_area="Review",
        items=[PlanTarget(resource_id=resource.id)],
    )
    service = LearningPlanService(db_session, owner)
    plan = await service.write(room, student.id, body)
    assert not plan.items[0].completed
    marked = await LearningPlanService(db_session, student).complete_resource(
        room, plan.id, plan.items[0].id
    )
    assert marked.items[0].completion_source == "RESOURCE_MARKER"
    with pytest.raises(AppError) as stale:
        await service.write(room, student.id, body, plan_id=plan.id)
    assert stale.value.code == "LEARNING_PLAN_CHANGED"
    await content.update_resource(room, resource.id, ResourceUpdate(status="DRAFT"))
    hidden = (await LearningPlanService(db_session, student).list(room)).items[0].items[0]
    assert hidden.available is False and resource.title not in hidden.title
    with pytest.raises(AppError):
        await service.write(room, student.id, body)
    _, _, other_room, _ = await classroom_fixture(db_session)
    with pytest.raises(AppError):
        await service.write(other_room, student.id, body)


async def test_analytics_optional_staff_permission_and_revocation(db_session):
    from app.schemas.classroom_staff import StaffUpdate
    from app.services.classroom_staff import ClassroomStaffService
    from tests.test_classroom_staff_gradebook import staff_setup

    owner, _, room, _, staff, invitation = await staff_setup(db_session, "TEACHING_ASSISTANT")
    with pytest.raises(AppError):
        await ClassroomLearningService(db_session, staff).dashboard(room)
    await ClassroomStaffService(db_session, owner).change(
        room, invitation.id, data=StaffUpdate(staff_role="TEACHING_ASSISTANT", analytics_view=True)
    )
    assert (await ClassroomLearningService(db_session, staff).dashboard(room)).active_students == 1
    await ClassroomStaffService(db_session, owner).change(room, invitation.id, revoke=True)
    with pytest.raises(AppError):
        await ClassroomLearningService(db_session, staff).dashboard(room)


async def test_learning_range_is_validated_and_selected_roots_stay_within_range(db_session):
    from datetime import timedelta

    from app.domains.timers import TimerService

    owner, student, room, _, _ = await graded_assignment(db_session)
    now = TimerService.now()
    empty = await ClassroomLearningService(db_session, student).dashboard(
        room, own=True, start=now - timedelta(days=60), end=now - timedelta(days=1)
    )
    assert empty.recent_assessments == [] and all(row.latest is None for row in empty.skills)
    for start, end in [(now, now), (now - timedelta(days=367), now)]:
        with pytest.raises(AppError) as error:
            await ClassroomLearningService(db_session, owner).dashboard(room, start=start, end=end)
        assert error.value.code == "ANALYTICS_RANGE_INVALID"


def test_weakness_evidence_thresholds_and_stable_order():
    from types import SimpleNamespace as Row

    from app.services.classroom_learning import weakness_rules

    question = dict(
        skill="READING",
        category="short_answer",
        sample_size=10,
        recent_sample_size=5,
        recent_accuracy=30,
        confidence_level="MEDIUM",
    )
    assert weakness_rules([Row(**{**question, "sample_size": 9})], [], []) == []
    assert weakness_rules([Row(**{**question, "recent_sample_size": 4})], [], []) == []
    criterion = Row(
        skill="WRITING",
        context="TASK_2",
        criterion="gra",
        recent_sample_size=3,
        sample_size=3,
        recent_average=5,
    )
    values = weakness_rules([Row(**question)], [criterion], [])
    assert [row.skill for row in values] == ["READING", "WRITING"]
    assert values == weakness_rules([Row(**question)], [criterion], [])
    assert weakness_rules([], [criterion], [], LearningGoals(writing=0)) == []


async def test_recommendations_respect_availability_and_completed_version_priority(db_session):
    from app.models import Classroom
    from app.models.enums import TestOrigin, VersionStatus
    from app.schemas.classroom_assignments import AssignmentCreate
    from app.schemas.classroom_learning import Weakness
    from app.services.classroom_assignments import ClassroomAssignmentService
    from tests.teacher_helpers import make_version
    from tests.test_classroom_assignments import add_objective_modules

    owner, student, room, existing, _ = await graded_assignment(db_session)
    repeated = await ClassroomAssignmentService(db_session, owner).create(
        room, AssignmentCreate(test_version_id=existing.test_version_id)
    )
    _, version = await make_version(
        db_session, owner, status=VersionStatus.PUBLISHED, origin=TestOrigin.ADMIN
    )
    await add_objective_modules(db_session, version.id)
    fresh = await ClassroomAssignmentService(db_session, owner).create(
        room, AssignmentCreate(test_version_id=version.id)
    )
    weakness = Weakness(
        weakness_type="QUESTION_TYPE",
        skill="READING",
        category="short_answer",
        evidence="10 scored questions",
        sample_size=10,
        severity="HIGH",
        confidence_level="MEDIUM",
        recommendation_reason="LOW_RECENT_ACCURACY",
        observed=30,
        baseline=60,
    )
    async with db_session.begin():
        classroom = await db_session.get(Classroom, room)
        rows = await ClassroomLearningService(db_session, student)._recommend(
            classroom, [weakness], student
        )
    assert [row.assignment_id for row in rows] == [fresh.id, repeated.id]
    assert all(row.assignment_id != existing.id for row in rows)
    await ClassroomAssignmentService(db_session, owner).archive(room, fresh.id)
    async with db_session.begin():
        rows = await ClassroomLearningService(db_session, student)._recommend(
            await db_session.get(Classroom, room), [weakness], student
        )
    assert [row.assignment_id for row in rows] == [repeated.id]


async def test_full_mock_is_one_root_with_four_skills_and_pending_human_is_not_zero(db_session):
    from sqlalchemy import select

    from app.domains.timers import TimerService
    from app.models import (
        Attempt,
        AttemptSpeakingScore,
        AttemptWritingScore,
        TestModule,
        WritingTask,
    )
    from app.models import TestSession as SessionRecord

    owner, student, room, assignment, roots = await graded_assignment(db_session)
    await age_roots(db_session, roots)
    now = TimerService.now()
    async with db_session.begin():
        writing_module = await db_session.scalar(
            select(TestModule.id).where(
                TestModule.test_version_id == assignment.test_version_id,
                TestModule.module_type == "WRITING",
            )
        )
        first_task = WritingTask(
            module_id=writing_module,
            task_number=1,
            order_index=0,
            task_type="REPORT",
            prompt="Describe a fictional chart.",
            minimum_recommended_words=150,
            recommended_duration_seconds=1200,
        )
        db_session.add(first_task)
        db_session.add(
            TestModule(
                test_version_id=assignment.test_version_id,
                module_type="SPEAKING",
                order_index=3,
                recommended_duration_seconds=900,
            )
        )
        mock = SessionRecord(
            user_id=student.id,
            test_version_id=assignment.test_version_id,
            classroom_assignment_id=assignment.id,
            status="COMPLETED",
            started_at=now,
            finished_at=now,
            module_order_json=["LISTENING", "READING", "WRITING", "SPEAKING"],
        )
        db_session.add(mock)
        await db_session.flush()
        children = {}
        for skill in ("LISTENING", "READING", "WRITING", "SPEAKING"):
            child = Attempt(
                user_id=student.id,
                test_version_id=assignment.test_version_id,
                test_session_id=mock.id,
                module_type=skill,
                scope="FULL_MODULE",
                timer_mode="COUNT_UP",
                status="SUBMITTED",
                started_at=now,
                last_active_at=now,
                finished_at=now,
                band_score=5 if skill == "SPEAKING" else 7,
                raw_score=30 if skill in {"READING", "LISTENING"} else None,
                max_score=40 if skill in {"READING", "LISTENING"} else None,
            )
            db_session.add(child)
            children[skill] = child
        await db_session.flush()
        task_ids = list(
            await db_session.scalars(
                select(WritingTask.id).where(WritingTask.module_id == writing_module)
            )
        )
        for task in task_ids:
            db_session.add(
                AttemptWritingScore(
                    attempt_id=children["WRITING"].id, writing_task_id=task, ta=7, cc=7, lr=7, gra=7
                )
            )
    before = await ClassroomLearningService(db_session, student).dashboard(room, own=True)
    assert len(before.recent_assessments) == 1 and before.recent_assessments[0].root_id == mock.id
    assert before.recent_assessments[0].band is None and before.pending_human == 1
    assert before.counts["SUBMITTED_ON_TIME"] == 1 and before.skills[3].sample_size == 0
    async with db_session.begin():
        db_session.add(
            AttemptSpeakingScore(attempt_id=children["SPEAKING"].id, fc=5, lr=5, gra=5, pr=5)
        )
    after = await ClassroomLearningService(db_session, student).dashboard(room, own=True)
    grade = (await ClassroomGradeService(db_session, owner).page(room)).students[0].cells[0].score
    assert after.recent_assessments[0].band == grade.band == 6.5
    assert len(grade.breakdown) == 4 and all(row.sample_size == 1 for row in after.skills)
    assert {row.criterion for row in after.criteria if row.skill == "SPEAKING"} == {
        "fc",
        "lr",
        "gra",
        "pr",
    }


async def test_learning_dashboard_queries_do_not_grow_per_student(db_session):
    from uuid import uuid4

    from sqlalchemy import event

    from app.models import ClassroomMembership, User

    owner, _, room, _, _ = await graded_assignment(db_session)
    statements = []

    def capture(*args):
        if args[2].lstrip().upper().startswith("SELECT"):
            statements.append(args[2])

    bind = db_session.sync_session.bind
    event.listen(bind, "before_cursor_execute", capture)
    try:
        await ClassroomLearningService(db_session, owner).dashboard(room)
        baseline = len(statements)
        async with db_session.begin():
            people = []
            for index in range(12):
                user = User(
                    id=uuid4(),
                    email=f"analytics-{uuid4()}@example.com",
                    display_name=f"Fictional learner {index}",
                    role="USER",
                    is_active=True,
                    email_verified=True,
                )
                db_session.add(user)
                people.append(user)
            await db_session.flush()
            db_session.add_all(
                [ClassroomMembership(classroom_id=room, user_id=user.id) for user in people]
            )
        statements.clear()
        data = await ClassroomLearningService(db_session, owner).dashboard(room)
        assert data.active_students == 13 and len(statements) == baseline
        assert len(statements) < 30
    finally:
        event.remove(bind, "before_cursor_execute", capture)
