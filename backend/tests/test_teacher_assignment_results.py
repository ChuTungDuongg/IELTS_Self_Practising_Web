from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from teacher_helpers import api_client, make_user
from test_classroom_assignments import add_objective_modules, classroom_fixture

from app.core.exceptions import AppError
from app.models import (
    Attempt,
    AttemptWritingScore,
    Classroom,
    ClassroomMembership,
    SpeakingPart,
    SpeakingPrompt,
    WritingAIGradingRun,
    WritingTask,
)
from app.models import TestModule as Module
from app.models.enums import (
    AttemptStatus,
    ClassroomStatus,
    ModerationStatus,
    ModuleType,
    SpeakingPromptType,
    UserRole,
    WritingAIRunStatus,
)
from app.models.enums import (
    TestSessionStatus as SessionStatus,
)
from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
from app.services.attempts import AttemptService
from app.services.classroom_assignments import ClassroomAssignmentService
from app.services.classroom_results import ClassroomResultService
from app.services.speaking_attempts import SpeakingAttemptService
from app.services.test_sessions import TestSessionService as SessionService


async def test_teacher_reads_assignment_after_leave_but_never_same_test_personal_work(db_session):
    teacher, student, classroom_id, version_id = await classroom_fixture(db_session, official=True)
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    started = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
    )
    from app.schemas.attempts import AttemptCreate

    personal = await AttemptService(db_session, student.id).start(
        AttemptCreate(
            test_version_id=version_id, module=ModuleType.WRITING, timer={"mode": "COUNT_UP"}
        )
    )
    await AttemptService(db_session, student.id).submit(started.attempt_id)
    async with db_session.begin():
        member = await db_session.scalar(
            select(ClassroomMembership).where(
                ClassroomMembership.classroom_id == classroom_id,
                ClassroomMembership.user_id == student.id,
            )
        )
        member.left_at = datetime.now(UTC)
    service = ClassroomResultService(db_session, teacher)
    result = await service.detail(classroom_id, assignment.id, started.attempt_id)
    assert result.attempt.attempt_id == started.attempt_id
    assert result.writing_review is not None
    await db_session.rollback()
    with pytest.raises(AppError) as error:
        await service.detail(classroom_id, assignment.id, personal.attempt_id)
    assert error.value.status_code == 404
    await db_session.rollback()
    rows = await service.list(classroom_id, assignment.id)
    assert [row.attempt.attempt_id for row in rows] == [started.attempt_id]


async def test_other_teacher_student_and_grading_mutations_stay_forbidden(db_session):
    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    started = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
    )
    other = await make_user(db_session, UserRole.TEACHER)
    for actor in [other, student]:
        with pytest.raises(AppError):
            await ClassroomResultService(db_session, actor).detail(
                classroom_id, assignment.id, started.attempt_id
            )
        await db_session.rollback()
    async with api_client(db_session, teacher) as client:
        response = await client.put(
            f"/api/v1/attempts/{started.attempt_id}/writing-scores/00000000-0000-4000-8000-000000000001",
            json={"ta": 6, "cc": 6, "lr": 6, "gra": 6},
        )
        assert response.status_code == 404
        assert (await client.delete(f"/api/v1/attempts/{started.attempt_id}")).status_code == 404


async def test_full_mock_all_child_results_derive_session_origin_and_keep_personal_mock_private(
    db_session,
):
    teacher, student, classroom_id, version_id = await classroom_fixture(db_session, official=True)
    await add_objective_modules(db_session, version_id)
    async with db_session.begin():
        prompt = SpeakingPrompt(
            order_index=0,
            prompt_type=SpeakingPromptType.SHORT_ANSWER,
            prompt_text="Describe a fictional classroom activity.",
            preparation_seconds=0,
            response_seconds=5,
            config_json={},
        )
        module = Module(
            test_version_id=version_id,
            module_type=ModuleType.SPEAKING,
            order_index=3,
            recommended_duration_seconds=1200,
            speaking_parts=[
                SpeakingPart(part_number=1, order_index=0, prompts=[prompt]),
            ],
        )
        db_session.add(module)
        await db_session.flush()
        speaking_prompt_id = prompt.id
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    learner = ClassroomAssignmentService(db_session, student)
    assigned = await learner.start(assignment.id, AssignmentStart(mode="FULL_MOCK"))
    retry = await learner.start(assignment.id, AssignmentStart(mode="FULL_MOCK"))
    personal = await SessionService(db_session, student.id).start(version_id)
    assert assigned.test_session_id != retry.test_session_id
    await AttemptService(db_session, student.id).submit(assigned.attempt_id)
    result = await ClassroomResultService(db_session, teacher).detail(
        classroom_id, assignment.id, assigned.attempt_id
    )
    assert result.session_id == assigned.test_session_id and result.review is None
    await db_session.rollback()
    reading = await SessionService(db_session, student.id).advance(assigned.test_session_id)
    await AttemptService(db_session, student.id).submit(reading.current_attempt.attempt_id)
    writing = await SessionService(db_session, student.id).advance(assigned.test_session_id)
    await AttemptService(db_session, student.id).submit(writing.current_attempt.attempt_id)
    speaking = await SessionService(db_session, student.id).advance(assigned.test_session_id)
    runtime = SpeakingAttemptService(db_session, student.id)
    await runtime.begin_prompt(speaking.current_attempt.attempt_id, speaking_prompt_id)
    await runtime.finish_current_response(
        speaking.current_attempt.attempt_id, speaking_prompt_id, 1, "USER_DONE"
    )
    completed = await SessionService(db_session, student.id).get(assigned.test_session_id)
    assert completed.status == SessionStatus.COMPLETED and len(completed.attempts) == 4
    async with db_session.begin():
        member = await db_session.scalar(
            select(ClassroomMembership).where(
                ClassroomMembership.classroom_id == classroom_id,
                ClassroomMembership.user_id == student.id,
            )
        )
        member.left_at = datetime.now(UTC)
    service = ClassroomResultService(db_session, teacher)
    results = await service.list(classroom_id, assignment.id)
    assert {row.attempt.attempt_id for row in results} == {
        assigned.attempt_id,
        retry.attempt_id,
        reading.current_attempt.attempt_id,
        writing.current_attempt.attempt_id,
        speaking.current_attempt.attempt_id,
    }
    for attempt_id in [
        assigned.attempt_id,
        reading.current_attempt.attempt_id,
        writing.current_attempt.attempt_id,
        speaking.current_attempt.attempt_id,
    ]:
        stored = await db_session.get(Attempt, attempt_id)
        before = (stored.status, stored.finished_at, stored.last_active_at, stored.updated_at)
        result = await service.detail(classroom_id, assignment.id, attempt_id)
        assert result.session_id == assigned.test_session_id
        if result.attempt.module == ModuleType.SPEAKING:
            assert result.speaking_review is not None
            assert result.speaking_review.can_generate_transcript is False
            assert result.speaking_ai_run is None
        else:
            assert result.review is not None
        await db_session.refresh(stored)
        assert (
            stored.status,
            stored.finished_at,
            stored.last_active_at,
            stored.updated_at,
        ) == before
        assert stored.classroom_assignment_id is None
        assert stored.test_session_id == assigned.test_session_id
    await db_session.rollback()
    with pytest.raises(AppError) as error:
        await service.detail(classroom_id, assignment.id, personal.current_attempt.attempt_id)
    assert error.value.status_code == 404


@pytest.mark.parametrize("skill", [ModuleType.READING, ModuleType.LISTENING])
async def test_teacher_objective_result_exposes_submitted_answers_actual_correctness_and_review(
    db_session, skill
):
    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    question_ids = (await add_objective_modules(db_session, version_id))[skill]
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    started = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module=skill)
    )
    student_service = AttemptService(db_session, student.id)
    await student_service.save_answer(started.attempt_id, question_ids[0], "fixture", 0)
    await student_service.save_answer(started.attempt_id, question_ids[1], "incorrect", 0)
    await student_service.submit(started.attempt_id)
    result = await ClassroomResultService(db_session, teacher).detail(
        classroom_id, assignment.id, started.attempt_id
    )
    assert result.attempt.raw_score == 1 and result.attempt.max_score == 2
    answers = {answer.question_id: answer for answer in result.submitted_answers}
    assert answers[question_ids[0]].value == "fixture" and answers[question_ids[0]].is_correct
    assert (
        answers[question_ids[1]].value == "incorrect"
        and answers[question_ids[1]].is_correct is False
    )
    review = result.reading_review if skill == ModuleType.READING else result.listening_review
    assert review is not None and review.review.answers[0].answer_key["accepted"] == ["fixture"]


async def test_teacher_writing_result_keeps_existing_text_manual_score_and_ai_result_read_only(
    db_session,
):
    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    started = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
    )
    async with db_session.begin():
        task_id = await db_session.scalar(
            select(WritingTask.id)
            .join(WritingTask.module)
            .where(WritingTask.module.has(test_version_id=version_id))
        )
    essay = "Fictional classroom essay remains the student's unchanged writing."
    student_service = AttemptService(db_session, student.id)
    await student_service.save_writing_response(started.attempt_id, task_id, essay, 0)
    await student_service.submit(started.attempt_id)
    criteria = {
        trait: {
            "score": 6.5,
            "feedback": "Fictional advisory feedback.",
            "strengths": [],
            "improvements": [],
            "evidence": [],
        }
        for trait in ["ta", "cc", "lr", "gra"]
    }
    async with db_session.begin():
        manual = AttemptWritingScore(
            attempt_id=started.attempt_id,
            writing_task_id=task_id,
            ta=6,
            cc=7,
            lr=6,
            gra=7,
            ta_feedback="Existing official feedback.",
        )
        ai = WritingAIGradingRun(
            attempt_id=started.attempt_id,
            writing_task_id=task_id,
            requested_by_user_id=student.id,
            status=WritingAIRunStatus.COMPLETED,
            provider="fixture",
            model="fixture",
            prompt_version="mts-task2-v8",
            input_fingerprint="a" * 64,
            raw_mean=Decimal("6.5"),
            overall_band=Decimal("6.5"),
            result_json={"criteria": criteria, "raw_mean": 6.5, "overall_band": 6.5},
        )
        db_session.add_all([manual, ai])
        await db_session.flush()
        score_id, run_id = manual.id, ai.id
        attempt = await db_session.get(Attempt, started.attempt_id)
        before = (
            attempt.status,
            attempt.finished_at,
            attempt.last_active_at,
            attempt.band_score,
            manual.updated_at,
            ai.updated_at,
        )
    async with api_client(db_session, teacher) as client:
        response = await client.get(
            f"/api/v1/classrooms/{classroom_id}/assignments/{assignment.id}/attempts/{started.attempt_id}"
        )
        assert response.status_code == 200
        result = response.json()
        assert result["writing_responses"][0]["content"] == essay
        assert result["writing_responses"][0]["score"]["ta"] == 6
        assert (
            result["writing_responses"][0]["score"]["ta_feedback"] == "Existing official feedback."
        )
        assert result["ai_runs"][0]["id"] == str(run_id)
        assert (
            result["ai_runs"][0]["result"]["criteria"]["cc"]["feedback"]
            == "Fictional advisory feedback."
        )
    async with db_session.begin():
        attempt = await db_session.get(Attempt, started.attempt_id)
        manual = await db_session.get(AttemptWritingScore, score_id)
        ai = await db_session.get(WritingAIGradingRun, run_id)
        assert (
            attempt.status,
            attempt.finished_at,
            attempt.last_active_at,
            attempt.band_score,
            manual.updated_at,
            ai.updated_at,
        ) == before


@pytest.mark.parametrize("change", ["classroom", "revocation"])
async def test_future_access_revocation_or_archive_never_hides_historical_assignment_result(
    db_session, change
):
    from app.models import TestVersionModeration as Moderation

    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    assignment = await ClassroomAssignmentService(db_session, teacher).create(
        classroom_id, AssignmentCreate(test_version_id=version_id)
    )
    learner = ClassroomAssignmentService(db_session, student)
    body = AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
    started = await learner.start(assignment.id, body)
    await AttemptService(db_session, student.id).submit(started.attempt_id)
    async with db_session.begin():
        if change == "classroom":
            room = await db_session.get(Classroom, classroom_id)
            room.status = ClassroomStatus.ARCHIVED
        else:
            approval = await db_session.scalar(
                select(Moderation).where(Moderation.test_version_id == version_id)
            )
            approval.status = ModerationStatus.REVOKED
    with pytest.raises(AppError):
        await learner.start(assignment.id, body)
    result = await ClassroomResultService(db_session, teacher).detail(
        classroom_id, assignment.id, started.attempt_id
    )
    assert result.attempt.status == AttemptStatus.SUBMITTED and result.writing_review is not None


async def test_result_paths_scope_assignment_classroom_and_student_without_cross_resource_leaks(
    db_session,
):
    teacher, student, classroom_id, version_id = await classroom_fixture(db_session)
    other_student = await make_user(db_session)
    service = ClassroomAssignmentService(db_session, teacher)
    first = await service.create(classroom_id, AssignmentCreate(test_version_id=version_id))
    second = await service.create(classroom_id, AssignmentCreate(test_version_id=version_id))
    started = await ClassroomAssignmentService(db_session, student).start(
        first.id, AssignmentStart(mode="MODULE", module=ModuleType.WRITING)
    )
    async with api_client(db_session, teacher) as client:
        wrong_assignment = await client.get(
            f"/api/v1/classrooms/{classroom_id}/assignments/{second.id}/attempts/{started.attempt_id}"
        )
        wrong_classroom = await client.get(
            f"/api/v1/classrooms/{uuid4()}/assignments/{first.id}/attempts/{started.attempt_id}"
        )
        assert wrong_assignment.status_code == wrong_classroom.status_code == 404
        students = await client.get(
            f"/api/v1/classrooms/{classroom_id}/assignments/{first.id}/students/{other_student.id}/attempts"
        )
        assert students.status_code == 200 and students.json() == []
        mine = await client.get(
            f"/api/v1/classrooms/{classroom_id}/assignments/{first.id}/students/{student.id}/attempts"
        )
        assert mine.status_code == 200 and [
            row["attempt"]["attempt_id"] for row in mine.json()
        ] == [str(started.attempt_id)]
