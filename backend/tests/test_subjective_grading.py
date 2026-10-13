"""Provenance-aware final grading; fictional fixtures and no live providers."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from teacher_helpers import api_client, make_user
from test_classroom_assignments import classroom_fixture
from test_speaking_history_classroom import assigned
from test_speaking_transcript import completed
from test_writing_attempts import _persist_writing_test

from app.models import Attempt, ClassroomMembership, WritingTask
from app.models import TestSession as SessionRecord
from app.models.speaking import AttemptSpeakingScore
from app.schemas.attempts import AttemptCreate
from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
from app.services.attempts import AttemptService
from app.services.classroom_assignments import ClassroomAssignmentService
from app.services.speaking_scorer import speaking_overall

WRITING = {"ta": 6, "cc": 6.5, "lr": 7, "gra": 6, "ta_feedback": "Human feedback"}
SPEAKING = {"fc": 6, "lr": 6.5, "gra": 7, "pr": 6, "pr_feedback": "Human pronunciation feedback"}


def personal_url(aid, task=None):
    return (
        f"/api/v1/attempts/{aid}/writing-scores/{task}"
        if task
        else f"/api/v1/speaking-attempts/{aid}/final-score"
    )


def teacher_url(room, assignment, aid, task=None):
    suffix = f"writing-scores/{task}" if task else "speaking-score"
    return f"/api/v1/classrooms/{room}/assignments/{assignment}/attempts/{aid}/{suffix}"


async def writing_personal(session, actor, *, focused=False, finalize=True):
    version, task, _, _ = await _persist_writing_test(session)
    data = {"test_version_id": version, "module": "WRITING", "timer": {"mode": "COUNT_UP"}}
    if focused:
        data.update(scope="FOCUSED_UNIT", focused_unit={"kind": "WRITING_TASK", "id": task})
    attempt = await AttemptService(session, actor.id).start(AttemptCreate.model_validate(data))
    if finalize:
        await AttemptService(session, actor.id).submit(attempt.attempt_id)
    return attempt.attempt_id, task


@pytest.mark.parametrize("role", ["USER", "TEACHER", "ADMIN"])
async def test_personal_writing_owner_saves_and_revises(db_session, role):
    actor = await make_user(db_session, role)
    aid, task = await writing_personal(db_session, actor)
    async with api_client(db_session, actor) as client:
        response = await client.put(personal_url(aid, task), json=WRITING)
        assert response.status_code == 200, response.text
        assert response.json()["grading"]["can_edit_final"] is True
        assert response.json()["tasks"][0]["score"]["ta"] == 6
        response = await client.put(personal_url(aid, task), json={**WRITING, "ta": 7})
        assert response.status_code == 200
        assert response.json()["tasks"][0]["score"]["ta"] == 7


async def test_writing_active_and_unrelated_rejected(db_session):
    actor = await make_user(db_session)
    other = await make_user(db_session)
    aid, task = await writing_personal(db_session, actor, finalize=False)
    async with api_client(db_session, actor) as client:
        assert (await client.put(personal_url(aid, task), json=WRITING)).status_code == 409
    async with api_client(db_session, other) as client:
        assert (await client.put(personal_url(aid, task), json=WRITING)).status_code == 404


async def writing_assignment(session):
    teacher, student, room, version = await classroom_fixture(session, official=True)
    assignment = await ClassroomAssignmentService(session, teacher).create(
        room, AssignmentCreate(test_version_id=version)
    )
    attempt = await ClassroomAssignmentService(session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    await AttemptService(session, student.id).submit(attempt.attempt_id)
    task = await session.scalar(
        select(WritingTask.id)
        .join(WritingTask.module)
        .where(WritingTask.module.has(test_version_id=version))
    )
    await session.rollback()
    return teacher, student, room, assignment.id, attempt.attempt_id, task, version


async def test_classroom_writing_teacher_scope_student_denied_and_membership_independent(
    db_session,
):
    teacher, student, room, assignment, aid, task, version = await writing_assignment(db_session)
    other = await make_user(db_session, "TEACHER")
    async with api_client(db_session, student) as client:
        assert (await client.put(personal_url(aid, task), json=WRITING)).status_code == 403
        review = (await client.get(f"/api/v1/attempts/{aid}/writing-review")).json()
        assert review["grading"] == {
            "context": "CLASSROOM",
            "can_edit_final": False,
            "can_copy_ai_to_final": False,
            "waiting_for_teacher": True,
        }
    async with db_session.begin():
        member = await db_session.scalar(
            select(ClassroomMembership).where(
                ClassroomMembership.classroom_id == room, ClassroomMembership.user_id == student.id
            )
        )
        member.left_at = datetime.now(UTC)
    async with api_client(db_session, teacher) as client:
        response = await client.put(teacher_url(room, assignment, aid, task), json=WRITING)
        assert response.status_code == 200, response.text
        assert response.json()["grading"]["can_edit_final"] is True
        assert (await client.put(personal_url(aid, task), json=WRITING)).status_code == 404
    async with api_client(db_session, student) as client:
        assert (
            await client.put(personal_url(aid, task), json={**WRITING, "ta": 9})
        ).status_code == 403
    async with api_client(db_session, other) as client:
        assert (
            await client.put(teacher_url(room, assignment, aid, task), json=WRITING)
        ).status_code in {403, 404}
    personal = await AttemptService(db_session, student.id).start(
        AttemptCreate(test_version_id=version, module="WRITING", timer={"mode": "COUNT_UP"})
    )
    await AttemptService(db_session, student.id).submit(personal.attempt_id)
    async with api_client(db_session, teacher) as client:
        assert (
            await client.put(teacher_url(room, assignment, personal.attempt_id, task), json=WRITING)
        ).status_code == 404
        assert (
            await client.put(teacher_url(uuid4(), assignment, aid, task), json=WRITING)
        ).status_code == 404
    admin = db_session.info["current_user_identity"]
    async with api_client(db_session, admin) as client:
        assert (await client.put(personal_url(aid, task), json=WRITING)).status_code == 200


async def attach_mock(session, actor, aid, assignment=None, status="IN_PROGRESS"):
    async with session.begin():
        attempt = await session.get(Attempt, aid)
        mock = SessionRecord(
            user_id=actor.id,
            test_version_id=attempt.test_version_id,
            started_at=datetime.now(UTC),
            classroom_assignment_id=assignment,
            status=status,
            module_order_json=["LISTENING", "READING", "WRITING", "SPEAKING"],
        )
        session.add(mock)
        await session.flush()
        attempt.classroom_assignment_id = None
        attempt.scope, attempt.focused_speaking_prompt_id = "FULL_MODULE", None
        attempt.test_session_id = mock.id
        return mock.id


async def test_writing_parent_assignment_provenance_and_mock_lock(db_session):
    teacher, student, room, assignment, aid, task, _ = await writing_assignment(db_session)
    sid = await attach_mock(db_session, student, aid, assignment)
    async with api_client(db_session, student) as client:
        assert (await client.put(personal_url(aid, task), json=WRITING)).status_code == 403
    async with api_client(db_session, teacher) as client:
        assert (
            await client.put(teacher_url(room, assignment, aid, task), json=WRITING)
        ).status_code == 409
    async with db_session.begin():
        (await db_session.get(SessionRecord, sid)).status = "COMPLETED"
    async with api_client(db_session, teacher) as client:
        assert (
            await client.put(teacher_url(room, assignment, aid, task), json=WRITING)
        ).status_code == 200


async def test_personal_mock_writing_review_lock(db_session):
    actor = await make_user(db_session)
    aid, task = await writing_personal(db_session, actor)
    await attach_mock(db_session, actor, aid)
    async with api_client(db_session, actor) as client:
        assert (await client.put(personal_url(aid, task), json=WRITING)).status_code == 409


async def test_focused_writing_keeps_module_band_empty(db_session):
    actor = await make_user(db_session)
    aid, task = await writing_personal(db_session, actor, focused=True)
    async with api_client(db_session, actor) as client:
        response = await client.put(personal_url(aid, task), json=WRITING)
        assert response.status_code == 200, response.text
        assert response.json()["band_score"] is None
        assert response.json()["task1_overall"] is not None


async def speaking_personal(session, tmp_path):
    actor = await make_user(session)
    session.info.update(current_user_id=actor.id, current_user_identity=actor)
    aid, rid, media = await completed(session, tmp_path)
    return actor, aid, rid, media


@pytest.mark.parametrize("focused", [True, False])
async def test_personal_speaking_human_score_and_existing_rounding(db_session, tmp_path, focused):
    actor, aid, _, _ = await speaking_personal(db_session, tmp_path)
    if not focused:
        async with db_session.begin():
            attempt = await db_session.get(Attempt, aid)
            attempt.scope, attempt.focused_speaking_prompt_id = "FULL_MODULE", None
    async with api_client(db_session, actor) as client:
        response = await client.put(personal_url(aid), json=SPEAKING)
        assert response.status_code == 200, response.text
        assert response.json()["final_score"]["overall_band"] == speaking_overall(SPEAKING)[1]
        assert response.json()["grading"]["can_edit_final"] is True
        response = await client.put(personal_url(aid), json={**SPEAKING, "fc": 7.5})
        assert response.status_code == 200
        assert response.json()["final_score"]["fc"] == 7.5
    attempt = await db_session.get(Attempt, aid)
    assert attempt.band_score == (
        None if focused else Decimal(str(speaking_overall({**SPEAKING, "fc": 7.5})[1]))
    )
    await db_session.rollback()


async def test_classroom_speaking_human_scope_edit_and_same_version_privacy(db_session, tmp_path):
    student, aid, _, _ = await speaking_personal(db_session, tmp_path)
    teacher, room, assignment, membership = await assigned(db_session, student, aid)
    other = await make_user(db_session, "TEACHER")
    async with api_client(db_session, student) as client:
        assert (await client.put(personal_url(aid), json=SPEAKING)).status_code == 403
    async with db_session.begin():
        (await db_session.get(ClassroomMembership, membership.id)).left_at = datetime.now(UTC)
    async with api_client(db_session, teacher) as client:
        url = teacher_url(room.id, assignment.id, aid)
        response = await client.put(url, json=SPEAKING)
        assert response.status_code == 200, response.text
        assert response.json()["final_score"]["pr_feedback"] == SPEAKING["pr_feedback"]
        assert response.json()["grading"]["can_edit_final"] is True
        response = await client.put(url, json={**SPEAKING, "pr": 8})
        assert response.status_code == 200 and response.json()["final_score"]["pr"] == 8
    async with api_client(db_session, student) as client:
        assert (await client.put(personal_url(aid), json=SPEAKING)).status_code == 403
    async with api_client(db_session, other) as client:
        assert (await client.put(url, json=SPEAKING)).status_code in {403, 404}
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        attempt.classroom_assignment_id = None
    async with api_client(db_session, teacher) as client:
        assert (await client.put(url, json=SPEAKING)).status_code == 404


async def test_speaking_parent_provenance_and_full_mock_lock(db_session, tmp_path):
    student, aid, _, _ = await speaking_personal(db_session, tmp_path)
    teacher, room, assignment, _ = await assigned(db_session, student, aid)
    sid = await attach_mock(db_session, student, aid, assignment.id)
    async with api_client(db_session, student) as client:
        assert (await client.put(personal_url(aid), json=SPEAKING)).status_code == 403
    async with api_client(db_session, teacher) as client:
        assert (
            await client.put(teacher_url(room.id, assignment.id, aid), json=SPEAKING)
        ).status_code == 409
    async with db_session.begin():
        (await db_session.get(SessionRecord, sid)).status = "COMPLETED"
    async with api_client(db_session, teacher) as client:
        assert (
            await client.put(teacher_url(room.id, assignment.id, aid), json=SPEAKING)
        ).status_code == 200


@pytest.mark.parametrize("field", ["fc", "lr", "gra", "pr"])
@pytest.mark.parametrize("value", [-0.5, 9.5, 6.25, float("nan"), float("inf")])
def test_speaking_final_scores_validate_half_bands(field, value):
    from app.schemas.grading import SpeakingScoreUpdate

    with pytest.raises(ValidationError):
        SpeakingScoreUpdate.model_validate({**SPEAKING, field: value})


async def test_admin_speaking_grades_unrelated_response_bearing_personal_attempt(
    db_session, tmp_path
):
    admin = db_session.info["current_user_identity"]
    student, aid, _, _ = await speaking_personal(db_session, tmp_path)
    async with api_client(db_session, admin) as client:
        response = await client.put(personal_url(aid), json=SPEAKING)
        assert response.status_code == 200, response.text
        assert response.json()["parts"][0]["responses"]
        assert response.json()["final_score"]["overall_band"] == speaking_overall(SPEAKING)[1]


async def test_focused_teacher_speaking_saved_score_stops_waiting(db_session, tmp_path):
    student, aid, _, _ = await speaking_personal(db_session, tmp_path)
    teacher, room, assignment, _ = await assigned(db_session, student, aid)
    async with api_client(db_session, teacher) as client:
        assert (
            await client.put(teacher_url(room.id, assignment.id, aid), json=SPEAKING)
        ).status_code == 200
        result = await client.get(
            f"/api/v1/classrooms/{room.id}/assignments/{assignment.id}/attempts/{aid}"
        )
        assert result.status_code == 200, result.text
        assert result.json()["attempt"]["band_score"] is None
        assert result.json()["grading"]["waiting_for_teacher"] is False


async def test_speaking_personal_active_and_mock_review_lock_then_unlock(db_session, tmp_path):
    actor, aid, _, _ = await speaking_personal(db_session, tmp_path)
    async with db_session.begin():
        (await db_session.get(Attempt, aid)).status = "IN_PROGRESS"
    async with api_client(db_session, actor) as client:
        assert (await client.put(personal_url(aid), json=SPEAKING)).status_code == 409
    async with db_session.begin():
        (await db_session.get(Attempt, aid)).status = "SUBMITTED"
    sid = await attach_mock(db_session, actor, aid)
    async with api_client(db_session, actor) as client:
        response = await client.put(personal_url(aid), json=SPEAKING)
        assert response.status_code == 409
        assert response.json()["code"] == "FULL_MOCK_REVIEW_LOCKED"
    async with db_session.begin():
        (await db_session.get(SessionRecord, sid)).status = "COMPLETED"
    async with api_client(db_session, actor) as client:
        response = await client.put(personal_url(aid), json=SPEAKING)
        assert response.status_code == 200, response.text
        assert response.json()["grading"]["context"] == "PERSONAL"


async def test_completed_ai_adoption_is_explicit_and_human_table_independent(
    db_session, tmp_path, monkeypatch
):
    from test_speaking_history_classroom import graded

    from app.models.speaking_ai import SpeakingAIGradingRun

    actor, aid, _, _, run_id = await graded(db_session, tmp_path, monkeypatch)
    run = await db_session.get(SpeakingAIGradingRun, run_id)
    assert run.status == "COMPLETED"
    snapshot = dict(run.criteria_json)
    assert await db_session.get(AttemptSpeakingScore, aid) is None
    scores = {key: snapshot[key]["score"] for key in ("fc", "lr", "gra", "pr")}
    await db_session.rollback()
    async with api_client(db_session, actor) as client:
        response = await client.put(personal_url(aid), json=scores)
        assert response.status_code == 200, response.text
        assert response.json()["final_score"]["overall_band"] == speaking_overall(scores)[1]
    run = await db_session.get(SpeakingAIGradingRun, run_id)
    assert run.criteria_json == snapshot
    assert await db_session.get(AttemptSpeakingScore, aid) is not None
    await db_session.rollback()
