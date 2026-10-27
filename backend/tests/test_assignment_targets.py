"""Teacher targets use frozen native modules and are enforced at start boundaries."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import Attempt, ReadingPassage
from app.models import TestModule as Module
from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
from app.services.classroom_assignments import ClassroomAssignmentService
from tests.teacher_helpers import api_client
from tests.test_classroom_assignments import add_objective_modules, classroom_fixture


async def setup(session):
    teacher, student, room, version = await classroom_fixture(session, official=True)
    await add_objective_modules(session, version)
    async with session.begin():
        passage = await session.scalar(
            select(ReadingPassage).join(Module).where(Module.test_version_id == version)
        )
    return teacher, student, room, version, passage.id


async def create_target(client, room, version, target):
    response = await client.post(
        f"/api/v1/classrooms/{room}/assignments",
        json={"test_version_id": str(version), "target": target},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_new_assignment_api_requires_explicit_target(db_session):
    teacher, _, room, version, _ = await setup(db_session)
    async with api_client(db_session, teacher) as client:
        response = await client.post(
            f"/api/v1/classrooms/{room}/assignments", json={"test_version_id": str(version)}
        )
        assert response.status_code == 422


async def test_full_module_target_rejects_unrelated_module_and_focused_scope(db_session):
    teacher, student, room, version, passage = await setup(db_session)
    async with api_client(db_session, teacher) as client:
        assigned = await create_target(
            client, room, version, {"mode": "MODULE", "module": "READING", "scope": "FULL_MODULE"}
        )
    async with api_client(db_session, student) as client:
        path = f"/api/v1/classroom-assignments/{assigned['id']}/start"
        for payload in (
            {"mode": "MODULE", "module": "WRITING"},
            {"mode": "FULL_MOCK"},
            {
                "mode": "MODULE",
                "module": "READING",
                "scope": "FOCUSED_UNIT",
                "focused_unit": {"kind": "READING_PASSAGE", "id": str(passage)},
            },
        ):
            rejected = await client.post(path, json=payload)
            assert (rejected.status_code, rejected.json()["code"]) == (
                409,
                "ASSIGNMENT_TARGET_MISMATCH",
            )
        assert (
            await client.post(path, json={"mode": "MODULE", "module": "READING"})
        ).status_code == 201


async def test_focused_passage_keeps_native_scope_and_rejects_wrong_unit(db_session):
    teacher, student, room, version, passage = await setup(db_session)
    target = {
        "mode": "MODULE",
        "module": "READING",
        "scope": "FOCUSED_UNIT",
        "focused_unit": {"kind": "READING_PASSAGE", "id": str(passage)},
    }
    async with api_client(db_session, teacher) as client:
        assigned = await create_target(client, room, version, target)
    async with api_client(db_session, student) as client:
        path = f"/api/v1/classroom-assignments/{assigned['id']}/start"
        wrong = await client.post(
            path, json={**target, "focused_unit": {"kind": "READING_PASSAGE", "id": str(uuid4())}}
        )
        assert wrong.status_code == 409
        started = await client.post(path, json=target)
        assert started.status_code == 201, started.text
    async with db_session.begin():
        attempt = await db_session.get(Attempt, UUID(started.json()["attempt_id"]))
        assert str(attempt.scope) == "FOCUSED_UNIT"
        assert attempt.focused_reading_passage_id == passage and attempt.test_version_id == version


@pytest.mark.parametrize(
    "target",
    [
        {
            "mode": "MODULE",
            "module": "READING",
            "scope": "FOCUSED_UNIT",
            "focused_unit": {"kind": "READING_PASSAGE", "id": str(uuid4())},
        },
        {"mode": "MODULE", "module": "SPEAKING", "scope": "FULL_MODULE"},
        {"mode": "FULL_MOCK"},
    ],
)
async def test_target_creation_checks_version_units_and_full_mock_eligibility(db_session, target):
    teacher, _, room, version, _ = await setup(db_session)
    async with api_client(db_session, teacher) as client:
        response = await client.post(
            f"/api/v1/classrooms/{room}/assignments",
            json={"test_version_id": str(version), "target": target},
        )
        assert response.status_code == 422


async def test_legacy_flexible_assignment_still_uses_its_original_version(db_session):
    teacher, student, room, version, _ = await setup(db_session)
    legacy = await ClassroomAssignmentService(db_session, teacher).create(
        room, AssignmentCreate(test_version_id=version)
    )
    assert legacy.target is None
    result = await ClassroomAssignmentService(db_session, student).start(
        legacy.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    assert result.attempt_id


@pytest.mark.parametrize(
    "skill,kind,model_name",
    [("LISTENING", "LISTENING_PART", "ListeningPart"), ("WRITING", "WRITING_TASK", "WritingTask")],
)
async def test_supported_focused_units_use_the_native_engine(db_session, skill, kind, model_name):
    from app import models

    teacher, student, room, version, _ = await setup(db_session)
    model = getattr(models, model_name)
    async with db_session.begin():
        unit = await db_session.scalar(
            select(model).join(Module).where(Module.test_version_id == version).limit(1)
        )
    target = {
        "mode": "MODULE",
        "module": skill,
        "scope": "FOCUSED_UNIT",
        "focused_unit": {"kind": kind, "id": str(unit.id)},
    }
    async with api_client(db_session, teacher) as client:
        assigned = await create_target(client, room, version, target)
    async with api_client(db_session, student) as client:
        response = await client.post(
            f"/api/v1/classroom-assignments/{assigned['id']}/start", json=target
        )
        assert response.status_code == 201, response.text


async def test_speaking_prompt_target_and_immutable_target_history(db_session):
    from sqlalchemy.exc import DBAPIError

    from app.models import ClassroomAssignment
    from tests.test_speaking_attempts import speaking_content

    teacher, student, room, _, _ = await setup(db_session)
    version, prompts = await speaking_content(db_session)
    target = {
        "mode": "MODULE",
        "module": "SPEAKING",
        "scope": "FOCUSED_UNIT",
        "focused_unit": {"kind": "SPEAKING_PROMPT", "id": str(prompts[0])},
    }
    async with api_client(db_session, teacher) as client:
        assigned = await create_target(client, room, version, target)
    async with api_client(db_session, student) as client:
        response = await client.post(
            f"/api/v1/classroom-assignments/{assigned['id']}/start", json=target
        )
        assert response.status_code == 201, response.text
    async with db_session.begin():
        row = await db_session.get(ClassroomAssignment, UUID(assigned["id"]))
        with pytest.raises(DBAPIError, match="immutable"):
            async with db_session.begin_nested():
                row.target = {"mode": "FULL_MOCK"}
                await db_session.flush()


async def test_targeted_full_mock_remains_one_root_and_one_start(db_session):
    from app.services.assignment_progress import AssignmentProgressService

    teacher, student, room, version, _ = await setup(db_session)
    async with db_session.begin():
        db_session.add(
            Module(
                test_version_id=version,
                module_type="SPEAKING",
                order_index=4,
                recommended_duration_seconds=900,
            )
        )
    async with api_client(db_session, teacher) as client:
        assigned = await create_target(client, room, version, {"mode": "FULL_MOCK"})
    async with api_client(db_session, student) as client:
        response = await client.post(
            f"/api/v1/classroom-assignments/{assigned['id']}/start", json={"mode": "FULL_MOCK"}
        )
        assert response.status_code == 201, response.text
        assert response.json()["test_session_id"]
    progress = await AssignmentProgressService(db_session, student).student(room)
    assert progress.items[0].attempts_used == 1


async def test_assignment_options_are_scoped_and_do_not_expose_answer_keys(db_session):
    teacher, student, room, version, _ = await setup(db_session)
    path = f"/api/v1/classrooms/{room}/assignment-versions/{version}"
    async with api_client(db_session, teacher) as client:
        response = await client.get(path)
        assert response.status_code == 200, response.text
        assert "answer_key" not in response.text
        assert response.json()["id"] == str(version)
    async with api_client(db_session, student) as client:
        assert (await client.get(path)).status_code == 403


async def test_recommendations_match_focused_units_and_writing_task_context(db_session):
    from app.models import Classroom, QuestionGroup, WritingTask
    from app.schemas.classroom_learning import Weakness
    from app.services.classroom_grades import ClassroomGradeService
    from app.services.classroom_learning import ClassroomLearningService

    teacher, student, room, version, passage = await setup(db_session)
    async with db_session.begin():
        category = await db_session.scalar(
            select(QuestionGroup.question_type).where(QuestionGroup.passage_id == passage)
        )
        task = await db_session.scalar(
            select(WritingTask).join(Module).where(Module.test_version_id == version).limit(1)
        )
    service = ClassroomAssignmentService(db_session, teacher)
    reading = await service.create(
        room,
        AssignmentCreate(
            test_version_id=version,
            target={
                "mode": "MODULE",
                "module": "READING",
                "scope": "FOCUSED_UNIT",
                "focused_unit": {"kind": "READING_PASSAGE", "id": passage},
            },
        ),
    )
    writing = await service.create(
        room,
        AssignmentCreate(
            test_version_id=version,
            target={
                "mode": "MODULE",
                "module": "WRITING",
                "scope": "FOCUSED_UNIT",
                "focused_unit": {"kind": "WRITING_TASK", "id": task.id},
            },
        ),
    )

    async def recommend(skill, kind, category):
        weakness = Weakness(
            weakness_type=kind,
            skill=skill,
            category=category,
            evidence="Fictional scored evidence",
            sample_size=10,
            severity="HIGH",
            confidence_level="MEDIUM",
            recommendation_reason="LOW_RECENT_ACCURACY"
            if kind == "QUESTION_TYPE"
            else "LOW_HUMAN_CRITERION",
            observed=3,
            baseline=6,
        )
        async with db_session.begin():
            return await ClassroomLearningService(db_session, student)._recommend(
                await db_session.get(Classroom, room), [weakness], student
            )

    assert [row.assignment_id for row in await recommend("READING", "QUESTION_TYPE", category)] == [
        reading.id
    ]
    assert await recommend("READING", "QUESTION_TYPE", "unrelated_category") == []
    assert [
        row.assignment_id
        for row in await recommend("WRITING", "CRITERION", f"TASK_{task.task_number}:ta")
    ] == [writing.id]
    assert await recommend("WRITING", "CRITERION", f"TASK_{3 - task.task_number}:ta") == []
    page = await ClassroomGradeService(db_session, teacher).page(room)
    assert next(row for row in page.assignments if row.id == writing.id).target == writing.target
