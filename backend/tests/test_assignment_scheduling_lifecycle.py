import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Attempt
from app.models import TestSession as SessionModel
from app.schemas.assignment_scheduling import ExtensionWrite
from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
from app.services.assignment_progress import AssignmentProgressService
from app.services.assignment_reminders import generate_reminders
from app.services.assignment_scheduling import AssignmentSchedulingService
from app.services.attempts import AttemptService
from app.services.classroom_assignments import ClassroomAssignmentService
from tests.test_assignment_scheduling import setup_assignment
from tests.test_classroom_assignments import add_objective_modules, classroom_fixture


async def test_reminders_deduplicate_and_follow_private_extensions(db_session):
    now = TimerService.now()
    teacher, student, room, assignment = await setup_assignment(
        db_session, due_at=now + timedelta(hours=12), cutoff_at=now + timedelta(days=3)
    )
    first = await generate_reminders(db_session, now=now)
    assert first["emitted"] >= 1
    again = await generate_reminders(db_session, now=now)
    assert again["emitted"] == 0
    await AssignmentSchedulingService(db_session, teacher).write_extension(
        room,
        assignment.id,
        student.id,
        ExtensionWrite(override_due=True, due_at_override=now + timedelta(days=2)),
    )
    assert (await generate_reminders(db_session, now=now))["emitted"] == 0


async def test_reminders_skip_satisfied_submissions(db_session):
    from app.models import Notification
    now = TimerService.now()
    teacher, student, room, assignment = await setup_assignment(db_session, due_at=now+timedelta(hours=12))
    result = await ClassroomAssignmentService(db_session, student).start(assignment.id, AssignmentStart(mode="MODULE", module="WRITING"))
    await AttemptService(db_session, student.id).submit(result.attempt_id)
    await generate_reminders(db_session, now=now)
    async with db_session.begin():
        assert await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == student.id, Notification.type == "ASSIGNMENT_DUE_SOON")) == 0


async def test_due_cutoff_crossing_preserves_exam_and_classifies_rejection(db_session, monkeypatch):
    now = TimerService.now()
    teacher, student, room, assignment = await setup_assignment(
        db_session, due_at=now + timedelta(hours=1), cutoff_at=now + timedelta(hours=2)
    )
    result = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now + timedelta(hours=3)))
    # Prevent AFK classification: a real user may have been typing throughout.
    async with db_session.begin():
        row = await db_session.get(Attempt, result.attempt_id)
        row.last_active_at = TimerService.now()
    submitted = await AttemptService(db_session, student.id).submit(result.attempt_id)
    assert submitted.status == "SUBMITTED"
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert progress.submission_status == "SUBMITTED_NOT_ACCEPTED" and not progress.accepted


async def test_full_mock_counts_once_and_requires_successful_all_modules(db_session):
    teacher, student, room, assignment = await setup_assignment(db_session)
    async with db_session.begin():
        session = SessionModel(
            classroom_assignment_id=assignment.id,
            user_id=student.id,
            test_version_id=assignment.test_version_id,
            module_order_json=["LISTENING", "READING", "WRITING"],
            status="IN_PROGRESS",
            started_at=TimerService.now(),
        )
        db_session.add(session)
        await db_session.flush()
        session_id = session.id
        child = Attempt(
            user_id=student.id,
            test_version_id=assignment.test_version_id,
            test_session_id=session_id,
            module_type="WRITING",
            status="SUBMITTED",
            started_at=TimerService.now(),
            finished_at=TimerService.now(),
            timer_mode="COUNT_UP",
            last_active_at=TimerService.now(),
        )
        db_session.add(child)
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert (
        progress.attempts_used == 1
        and progress.submission_status == "IN_PROGRESS"
        and not progress.accepted
    )
    async with db_session.begin():
        stored = await db_session.get(SessionModel, session_id)
        stored.status = "COMPLETED"
        stored.finished_at = TimerService.now()
        for module in ("LISTENING", "READING"):
            db_session.add(
                Attempt(
                    user_id=student.id,
                    test_version_id=assignment.test_version_id,
                    test_session_id=session_id,
                    module_type=module,
                    status="AUTO_SUBMITTED",
                    started_at=TimerService.now(),
                    finished_at=TimerService.now(),
                    timer_mode="COUNT_UP",
                    last_active_at=TimerService.now(),
                )
            )
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert (
        progress.attempts_used == 1
        and progress.submission_status == "SUBMITTED_ON_TIME"
        and progress.accepted
    )


async def test_personal_work_excluded_and_late_join_not_missed(db_session):
    now = TimerService.now()
    teacher, student, room, assignment = await setup_assignment(
        db_session, cutoff_at=now - timedelta(hours=1)
    )
    async with db_session.begin():
        db_session.add(
            Attempt(
                user_id=student.id,
                test_version_id=assignment.test_version_id,
                module_type="WRITING",
                status="SUBMITTED",
                started_at=now,
                finished_at=now,
                timer_mode="COUNT_UP",
                last_active_at=now,
            )
        )
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert progress.attempts_used == 0 and progress.submission_status == "NOT_STARTED"


async def test_concurrent_start_near_limit_is_serialized():
    # Separate committed test-only rows are necessary for genuine two-connection races.
    from sqlalchemy.engine import make_url

    assert "test" in make_url(get_settings().database_url).database
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            teacher, student, room, version = await classroom_fixture(session, official=True)
            assignment = await ClassroomAssignmentService(session, teacher).create(
                room, AssignmentCreate(test_version_id=version, max_attempts=1)
            )

        async def start():
            async with factory() as session:
                try:
                    return await ClassroomAssignmentService(session, student).start(
                        assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
                    )
                except AppError as error:
                    return error.code

        results = await asyncio.gather(start(), start())
        assert sum(result == "ASSIGNMENT_ATTEMPT_LIMIT" for result in results) == 1
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Attempt)
                    .where(Attempt.classroom_assignment_id == assignment.id)
                )
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "relative,allowed,late",
    [
        (-1, False, True),
        (0, True, True),
        (3601, True, True),
        (3601, False, False),
        (7200, True, True),
        (7201, False, True),
    ],
)
async def test_native_start_window_boundaries(db_session, monkeypatch, relative, allowed, late):
    anchor = TimerService.now() + timedelta(days=1)
    teacher, student, room, assignment = await setup_assignment(
        db_session,
        available_from=anchor,
        due_at=anchor + timedelta(hours=1),
        cutoff_at=anchor + timedelta(hours=2),
        allow_late_submission=late,
    )
    monkeypatch.setattr(
        TimerService, "now", staticmethod(lambda: anchor + timedelta(seconds=relative))
    )
    if allowed:
        assert (
            await ClassroomAssignmentService(db_session, student).start(
                assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
            )
        ).attempt_id
    else:
        with pytest.raises(AppError):
            await ClassroomAssignmentService(db_session, student).start(
                assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
            )


async def test_native_focused_auto_submission_and_speaking_completion(db_session, monkeypatch):
    teacher, student, room, assignment = await setup_assignment(db_session)
    await add_objective_modules(db_session, assignment.test_version_id)
    from app.models import ReadingPassage
    from app.models import TestModule as Module
    from app.schemas.attempts import TimerRequest

    async with db_session.begin():
        passage = await db_session.scalar(
            select(ReadingPassage)
            .join(Module)
            .where(Module.test_version_id == assignment.test_version_id)
        )
        passage_id = passage.id
    result = await ClassroomAssignmentService(db_session, student).start(
        assignment.id,
        AssignmentStart(
            mode="MODULE",
            module="READING",
            scope="FOCUSED_UNIT",
            focused_unit={"kind": "READING_PASSAGE", "id": passage_id},
            timer=TimerRequest(mode="COUNTDOWN", duration_seconds=1200),
        ),
    )
    now = TimerService.now() + timedelta(seconds=1201)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    assert (
        await AttemptService(db_session, student.id).get(result.attempt_id)
    ).status == "AUTO_SUBMITTED"
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert progress.accepted and progress.attempts_used == 1

    # The actual Speaking runtime finalizes through a separate native path.
    from app.services.speaking_attempts import SpeakingAttemptService
    from tests.test_speaking_attempts import speaking_content

    speaking_version, prompts = await speaking_content(db_session)
    speaking_assignment = await ClassroomAssignmentService(db_session, teacher).create(
        room, AssignmentCreate(test_version_id=speaking_version)
    )
    speaking = await ClassroomAssignmentService(db_session, student).start(
        speaking_assignment.id, AssignmentStart(mode="MODULE", module="SPEAKING")
    )
    runtime = SpeakingAttemptService(db_session, student.id)
    for prompt in prompts:
        state = await runtime.begin_prompt(speaking.attempt_id, prompt)
        if state.phase == "PREPARING":
            now += timedelta(seconds=64)
            await runtime.get_state(speaking.attempt_id)
        await runtime.finish_current_response(speaking.attempt_id, prompt, 1, "USER_DONE")
    page = await AssignmentProgressService(db_session, student).student(
        room, assignment_id=speaking_assignment.id
    )
    assert page.items[0].accepted and page.items[0].submission_status == "SUBMITTED_ON_TIME"


async def test_native_full_mock_and_standalone_share_limit(db_session):
    from app.models import TestModule as Module

    teacher, student, room, assignment = await setup_assignment(db_session, max_attempts=2)
    async with db_session.begin():
        for index, module in enumerate(["LISTENING", "READING", "SPEAKING"], 1):
            db_session.add(
                Module(
                    test_version_id=assignment.test_version_id,
                    module_type=module,
                    order_index=index,
                    recommended_duration_seconds=1800,
                )
            )
    service = ClassroomAssignmentService(db_session, student)
    await service.start(assignment.id, AssignmentStart(mode="MODULE", module="WRITING"))
    mock = await service.start(assignment.id, AssignmentStart(mode="FULL_MOCK"))
    progress = (await AssignmentProgressService(db_session, student).student(room)).items[0]
    assert progress.attempts_used == 2 and progress.resume_session_id == mock.test_session_id
    with pytest.raises(AppError) as error:
        await service.start(assignment.id, AssignmentStart(mode="FULL_MOCK"))
    assert error.value.code == "ASSIGNMENT_ATTEMPT_LIMIT"


async def test_completed_work_not_reclassified_by_extensions_and_former_member_retained(db_session):
    from app.services.classrooms import ClassroomService

    teacher, student, room, assignment = await setup_assignment(
        db_session, due_at=TimerService.now() - timedelta(hours=1)
    )
    result = await ClassroomAssignmentService(db_session, student).start(
        assignment.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    await AttemptService(db_session, student.id).submit(result.attempt_id)
    await AssignmentSchedulingService(db_session, teacher).write_extension(
        room,
        assignment.id,
        student.id,
        ExtensionWrite(override_due=True, due_at_override=TimerService.now() + timedelta(days=2)),
    )
    assert (await AssignmentProgressService(db_session, student).student(room)).items[
        0
    ].submission_status == "SUBMITTED_LATE"
    await ClassroomService(db_session, student).leave(room)
    monitor = await AssignmentProgressService(db_session, teacher).monitor(room, assignment.id)
    assert (
        monitor.total == 1
        and not monitor.items[0].active_member
        and monitor.items[0].progress.result_attempt_id == result.attempt_id
    )
    assert (await AssignmentProgressService(db_session, student).student(room)).items[0].accepted
