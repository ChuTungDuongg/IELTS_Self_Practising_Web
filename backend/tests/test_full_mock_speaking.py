"""Four-skill mock flow and frozen legacy sessions, using fictional content."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Attempt, SpeakingPart, SpeakingPrompt
from app.models import Test as ExamRecord
from app.models import TestModule as ModuleRecord
from app.models import TestSession as SessionRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import AttemptStatus, ModuleType, SpeakingPromptType, TimerMode, VersionStatus
from app.models.enums import TestSessionStatus as SessionStatus
from app.services.attempts import AttemptService
from app.services.speaking_attempts import SpeakingAttemptService
from app.services.test_sessions import TestSessionService as SessionService

FOUR_SKILLS = ["LISTENING", "READING", "WRITING", "SPEAKING"]
THREE_SKILLS = FOUR_SKILLS[:3]


def fictional_mock(*, speaking=True):
    test = ExamRecord(title="Fictional four-skill mock")
    version = VersionRecord(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(version)
    for index, kind in enumerate(FOUR_SKILLS if speaking else THREE_SKILLS):
        module = ModuleRecord(
            module_type=ModuleType(kind), order_index=index, recommended_duration_seconds=1200
        )
        version.modules.append(module)
        if kind == "SPEAKING":
            for part_number in (1, 2, 3):
                part = SpeakingPart(part_number=part_number, order_index=part_number - 1)
                part.prompts.append(
                    SpeakingPrompt(
                        order_index=0,
                        prompt_type=SpeakingPromptType.LONG_TURN
                        if part_number == 2
                        else SpeakingPromptType.SHORT_ANSWER,
                        prompt_text=f"Describe fictional topic {part_number}.",
                        preparation_seconds=1 if part_number == 2 else 0,
                        response_seconds=5,
                        config_json={"cue_points": ["One fictional detail"]}
                        if part_number == 2
                        else {},
                    )
                )
                module.speaking_parts.append(part)
    return test


async def seed_mock(session, *, speaking=True):
    test = fictional_mock(speaking=speaking)
    async with session.begin():
        session.add(test)
        await session.flush()
    return test


async def reach_writing(session):
    test = await seed_mock(session)
    service = SessionService(session)
    started = await service.start(test.versions[0].id)
    await AttemptService(session).submit(started.current_attempt.attempt_id)
    current = await service.advance(started.session.session_id)
    await AttemptService(session).submit(current.current_attempt.attempt_id)
    writing = await service.advance(started.session.session_id)
    return test, started.session.session_id, writing.current_attempt.attempt_id


async def test_new_full_mock_requires_speaking(db_session):
    test = await seed_mock(db_session, speaking=False)
    with pytest.raises(AppError) as caught:
        await SessionService(db_session).start(test.versions[0].id)
    assert caught.value.code == "FULL_MOCK_MODULES_MISSING"
    assert "Speaking" in caught.value.message


async def test_new_full_mock_requires_positive_speaking_recommended_duration(db_session):
    test = await seed_mock(db_session)
    async with db_session.begin():
        test.versions[0].modules[-1].recommended_duration_seconds = None
    with pytest.raises(AppError) as caught:
        await SessionService(db_session).start(test.versions[0].id)
    assert caught.value.code == "FULL_MOCK_DURATION_MISSING"


async def test_new_full_mock_freezes_four_module_order(db_session):
    test = await seed_mock(db_session)
    result = await SessionService(db_session).start(test.versions[0].id)
    assert result.session.module_order == FOUR_SKILLS
    async with db_session.begin():
        stored = await db_session.get(SessionRecord, result.session.session_id)
        assert stored.module_order_json == FOUR_SKILLS


async def test_writing_finish_keeps_mock_active_and_repeated_advance_creates_one_speaking(
    db_session,
):
    _, sid, writing_id = await reach_writing(db_session)
    await AttemptService(db_session).submit(writing_id)
    service = SessionService(db_session)
    pending = await service.get(sid)
    assert pending.status == SessionStatus.IN_PROGRESS and pending.finished_at is None
    assert pending.current_module == pending.next_module == ModuleType.SPEAKING
    speaking = await service.advance(sid)
    assert speaking.current_attempt.module == ModuleType.SPEAKING
    async with db_session.begin():
        attempt = await db_session.get(Attempt, speaking.current_attempt.attempt_id)
        assert attempt.speaking_mode == "EXAM"
        assert attempt.timer_mode == TimerMode.COUNT_UP and attempt.timer_limit_seconds is None
    with pytest.raises(AppError) as caught:
        await service.advance(sid)
    assert caught.value.code == "FULL_MOCK_MODULE_ACTIVE"
    async with db_session.begin():
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(Attempt)
                .where(
                    Attempt.test_session_id == sid,
                    Attempt.module_type == "SPEAKING",
                )
            )
            == 1
        )


async def test_speaking_prompt_timeout_ack_finishes_mock_without_promoting_ai(
    db_session, monkeypatch
):
    test, sid, writing_id = await reach_writing(db_session)
    await AttemptService(db_session).submit(writing_id)
    speaking = (await SessionService(db_session).advance(sid)).current_attempt
    now = TimerService.now()
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    runtime = SpeakingAttemptService(db_session)
    async with db_session.begin():
        version_id = (await db_session.get(Attempt, speaking.attempt_id)).test_version_id
        prompts = list(
            await db_session.scalars(
                select(SpeakingPrompt)
                .join(SpeakingPart)
                .join(ModuleRecord)
                .where(
                    ModuleRecord.test_version_id == version_id,
                )
                .order_by(SpeakingPart.part_number, SpeakingPrompt.order_index)
            )
        )
    for prompt in prompts:
        await runtime.begin_prompt(speaking.attempt_id, prompt.id)
        now += timedelta(seconds=prompt.preparation_seconds + 3 + prompt.response_seconds)
        state = await runtime.get_state(speaking.attempt_id)
        assert state.phase == "FINALIZING" and state.remaining_ms == 0
        # Expiry alone does not finalize a missing final audio acknowledgement.
        assert (await SessionService(db_session).get(sid)).status == SessionStatus.IN_PROGRESS
        await runtime.finish_current_response(speaking.attempt_id, prompt.id, 1, "TIMEOUT")
    completed = await SessionService(db_session).get(sid)
    assert completed.status == SessionStatus.COMPLETED and completed.finished_at is not None
    assert completed.current_module is None and len(completed.attempts) == 4
    assert completed.overall_band_score is None
    async with db_session.begin():
        attempt = await db_session.get(Attempt, speaking.attempt_id)
        assert attempt.status in {AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED}
        assert attempt.band_score is None


@pytest.mark.parametrize("missing", [None, "LISTENING", "READING", "WRITING", "SPEAKING"])
async def test_four_skill_overall_requires_all_official_attempt_bands(db_session, missing):
    test = await seed_mock(db_session)
    now = TimerService.now()
    async with db_session.begin():
        parent = SessionRecord(
            test_version=test.versions[0],
            module_order_json=FOUR_SKILLS,
            user_id=db_session.info["current_user_id"],
            started_at=now,
            finished_at=now,
            status=SessionStatus.COMPLETED,
        )
        parent.attempts.extend(
            Attempt(
                test_version=test.versions[0],
                user_id=parent.user_id,
                module_type=ModuleType(kind),
                status=AttemptStatus.SUBMITTED,
                timer_mode=TimerMode.COUNT_UP,
                started_at=now,
                last_active_at=now,
                finished_at=now,
                band_score=None if kind == missing else Decimal("7.0"),
            )
            for kind in FOUR_SKILLS
        )
        db_session.add(parent)
        await db_session.flush()
    result = await SessionService(db_session).get(parent.id)
    assert result.overall_band_score == (7 if missing is None else None)


@pytest.mark.parametrize("speaking_in_version", [False, True])
async def test_legacy_session_frozen_order_survives_version_module_coverage(
    db_session, speaking_in_version
):
    test = await seed_mock(db_session, speaking=speaking_in_version)
    now = TimerService.now()
    async with db_session.begin():
        parent = SessionRecord(
            test_version=test.versions[0],
            user_id=db_session.info["current_user_id"],
            started_at=now,
            status=SessionStatus.IN_PROGRESS,
        )
        parent.attempts.extend(
            Attempt(
                test_version=test.versions[0],
                user_id=parent.user_id,
                module_type=ModuleType(kind),
                status=AttemptStatus.SUBMITTED,
                timer_mode=TimerMode.COUNT_UP,
                started_at=now,
                last_active_at=now,
                finished_at=now,
                band_score=Decimal("7.0"),
            )
            for kind in THREE_SKILLS
        )
        db_session.add(parent)
        await db_session.flush()
        assert parent.module_order_json == THREE_SKILLS
    result = await SessionService(db_session).get(parent.id)
    assert result.module_order == THREE_SKILLS and result.status == SessionStatus.COMPLETED
    assert len(result.attempts) == 3 and result.overall_band_score == 7
    advanced = await SessionService(db_session).advance(parent.id)
    assert advanced.current_attempt is None and len(advanced.attempts) == 3


async def session_with_media(session, *, owner_id=None):
    from app.models.speaking import (
        SpeakingAudioChunk,
        SpeakingAudioSegment,
        SpeakingResponse,
        SpeakingResponseTake,
    )
    from app.models.speaking_transcript import SpeakingNormalizedAudio

    test = await seed_mock(session)
    now = TimerService.now()
    keys = [f"private/speaking/raw-{uuid4()}.webm", f"private/speaking/normalized-{uuid4()}.wav"]
    async with session.begin():
        parent = SessionRecord(
            test_version=test.versions[0],
            module_order_json=FOUR_SKILLS,
            user_id=owner_id or session.info["current_user_id"],
            started_at=now,
            finished_at=now,
            status=SessionStatus.COMPLETED,
        )
        attempt = Attempt(
            test_version=test.versions[0],
            test_session=parent,
            user_id=parent.user_id,
            module_type=ModuleType.SPEAKING,
            status=AttemptStatus.SUBMITTED,
            timer_mode=TimerMode.COUNT_UP,
            started_at=now,
            last_active_at=now,
            finished_at=now,
            speaking_mode="EXAM",
        )
        session.add(parent)
        await session.flush()
        response = SpeakingResponse(
            attempt_id=attempt.id,
            prompt_id=test.versions[0].modules[-1].speaking_parts[0].prompts[0].id,
            started_at=now,
            locked=True,
        )
        session.add(response)
        await session.flush()
        take = SpeakingResponseTake(
            response_id=response.id, take_number=1, started_at=now, status="COMMITTED"
        )
        session.add(take)
        await session.flush()
        segment = SpeakingAudioSegment(
            response_take_id=take.id, segment_index=0, mime_type="audio/webm", chunk_count=1
        )
        session.add(segment)
        await session.flush()
        session.add_all(
            [
                SpeakingAudioChunk(
                    segment_id=segment.id,
                    sequence=0,
                    storage_key=keys[0],
                    sha256="f" * 64,
                    byte_size=10,
                ),
                SpeakingNormalizedAudio(
                    response_id=response.id,
                    cache_key="f" * 64,
                    source_audio_fingerprint="e" * 64,
                    normalizer_version="pcm-v1",
                    storage_key=keys[1],
                    duration_ms=5000,
                ),
            ]
        )
        await session.flush()
    return parent.id, attempt.id, test.versions[0].id, keys


async def test_personal_full_mock_delete_queues_only_owned_raw_and_derived_media(
    db_session, test_user
):
    from app.models.speaking import SpeakingMediaCleanup, SpeakingResponse

    sid, aid, _, keys = await session_with_media(db_session)
    other_sid, other_aid, _, other_keys = await session_with_media(
        db_session, owner_id=test_user.id
    )
    await SessionService(db_session).delete(sid)
    async with db_session.begin():
        queued = set(await db_session.scalars(select(SpeakingMediaCleanup.storage_key)))
        assert set(keys) <= queued and not set(other_keys) & queued
        assert await db_session.get(SessionRecord, sid) is None
        assert (
            await db_session.scalar(
                select(func.count()).select_from(Attempt).where(Attempt.id == aid)
            )
            == 0
        )
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(SpeakingResponse)
                .where(
                    SpeakingResponse.attempt_id == aid,
                )
            )
            == 0
        )
        assert await db_session.get(SessionRecord, other_sid) is not None
        assert await db_session.get(Attempt, other_aid) is not None


@pytest.mark.parametrize("status", [SessionStatus.COMPLETED, SessionStatus.IN_PROGRESS])
async def test_assignment_full_mock_delete_retains_history_and_media(db_session, status):
    from app.models import Classroom, ClassroomAssignment
    from app.models.speaking import SpeakingAudioChunk, SpeakingMediaCleanup

    sid, aid, version_id, keys = await session_with_media(db_session)
    async with db_session.begin():
        classroom = Classroom(teacher_id=db_session.info["current_user_id"], name="Fictional class")
        db_session.add(classroom)
        await db_session.flush()
        assignment = ClassroomAssignment(
            classroom_id=classroom.id,
            test_version_id=version_id,
            created_by_user_id=db_session.info["current_user_id"],
        )
        db_session.add(assignment)
        await db_session.flush()
        # Full Mock assignment provenance is on its parent (the DB forbids child provenance).
        row = await db_session.get(SessionRecord, sid)
        row.classroom_assignment_id = assignment.id
        row.status = status
    with pytest.raises(AppError) as caught:
        await SessionService(db_session).delete(sid)
    assert caught.value.code == "ASSIGNMENT_HISTORY_RETAINED"
    async with db_session.begin():
        assert await db_session.get(SessionRecord, sid) is not None
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(SpeakingAudioChunk)
                .where(
                    SpeakingAudioChunk.storage_key == keys[0],
                )
            )
            == 1
        )
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(SpeakingMediaCleanup)
                .where(
                    SpeakingMediaCleanup.storage_key.in_(keys),
                )
            )
            == 0
        )


@pytest_asyncio.fixture
async def concurrent_mock():
    """Committed fictional rows and independently connected requests; exact-ID cleanup."""
    from app.models import User
    from app.models.enums import UserRole

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = test_id = sid = None
    try:
        async with factory() as session:
            async with session.begin():
                owner = User(
                    email=f"full-mock-race-{uuid4()}@example.com",
                    display_name="Race fixture",
                    role=UserRole.ADMIN,
                    is_active=True,
                    email_verified=True,
                )
                session.add(owner)
                await session.flush()
                owner_id = owner.id
            session.info["current_user_id"] = owner_id
            test = await seed_mock(session)
            test_id, version_id = test.id, test.versions[0].id
            service = SessionService(session, owner_id)
            start = await service.start(version_id)
            sid = start.session.session_id
            await AttemptService(session, owner_id).submit(start.current_attempt.attempt_id)
            reading = await service.advance(sid)
            await AttemptService(session, owner_id).submit(reading.current_attempt.attempt_id)
            writing = await service.advance(sid)
            await AttemptService(session, owner_id).submit(writing.current_attempt.attempt_id)
        yield factory, owner_id, sid
    finally:
        async with factory() as session, session.begin():
            if sid:
                await session.execute(delete(SessionRecord).where(SessionRecord.id == sid))
            if test_id:
                await session.execute(delete(ExamRecord).where(ExamRecord.id == test_id))
            if owner_id:
                await session.execute(delete(User).where(User.id == owner_id))
        await engine.dispose()


async def test_independent_duplicate_advances_create_exactly_one_speaking_attempt(concurrent_mock):
    factory, owner_id, sid = concurrent_mock

    async def advance():
        async with factory() as session:
            return await SessionService(session, owner_id).advance(sid)

    outcomes = await asyncio.wait_for(
        asyncio.gather(advance(), advance(), return_exceptions=True), 15
    )
    errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(errors) == 1 and isinstance(errors[0], AppError)
    assert errors[0].code == "FULL_MOCK_MODULE_ACTIVE"
    success = next(outcome for outcome in outcomes if not isinstance(outcome, Exception))
    assert success.current_attempt.module == ModuleType.SPEAKING
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Attempt)
                .where(
                    Attempt.test_session_id == sid,
                    Attempt.module_type == ModuleType.SPEAKING,
                )
            )
            == 1
        )


async def test_final_speaking_ack_racing_advance_completes_one_session(
    concurrent_mock, monkeypatch
):
    from app.models import SpeakingResponse

    factory, owner_id, sid = concurrent_mock
    now = TimerService.now()
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    async with factory() as session:
        response = await SessionService(session, owner_id).advance(sid)
        aid = response.current_attempt.attempt_id
        runtime = SpeakingAttemptService(session, owner_id)
        state = await runtime.get_state(aid)
        for index in range(3):
            prompt_id = state.current_prompt.id
            state = await runtime.begin_prompt(aid, prompt_id)
            if state.phase == "PREPARING":
                now = state.phase_deadline_at + timedelta(seconds=3)
                state = await runtime.get_state(aid)
            if index < 2:
                state = await runtime.finish_current_response(aid, prompt_id, 1, "USER_DONE")

    async def finish():
        async with factory() as session:
            return await SpeakingAttemptService(session, owner_id).finish_current_response(
                aid, prompt_id, 1, "USER_DONE"
            )

    async def advance():
        async with factory() as session:
            return await SessionService(session, owner_id).advance(sid)

    completed, advancing = await asyncio.wait_for(
        asyncio.gather(finish(), advance(), return_exceptions=True), 10
    )
    assert completed.phase == "COMPLETED"
    if isinstance(advancing, AppError):
        assert advancing.code == "FULL_MOCK_MODULE_ACTIVE"
    else:
        assert advancing.status == SessionStatus.COMPLETED
    async with factory() as session:
        mock = await session.get(SessionRecord, sid)
        attempt = await session.get(Attempt, aid)
        assert mock.status == SessionStatus.COMPLETED and mock.finished_at is not None
        assert attempt.status == AttemptStatus.SUBMITTED and attempt.band_score is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SpeakingResponse)
                .where(SpeakingResponse.attempt_id == aid, SpeakingResponse.locked.is_(True))
            )
            == 3
        )
