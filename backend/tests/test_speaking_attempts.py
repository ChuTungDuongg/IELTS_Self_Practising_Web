"""Speaking runtime contracts using fictional content and real PostgreSQL state."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.main import app
from app.models import SpeakingPart, SpeakingPrompt
from app.models import Test as ExamRecord
from app.models import TestModule as ModuleRecord
from app.models import TestVersion as VersionRecord
from app.schemas.attempts import AttemptCreate
from app.services.attempts import AttemptService


def test_speaking_start_contract_supports_focused_prompt():
    body = AttemptCreate(
        test_version_id=uuid4(),
        module="SPEAKING",
        timer={"mode": "COUNT_UP"},
        scope="FOCUSED_UNIT",
        focused_unit={"kind": "SPEAKING_PROMPT", "id": uuid4()},
        speaking_mode="PRACTICE",
    )
    assert body.focused_unit.kind == "SPEAKING_PROMPT"


def test_runtime_routes_are_exposed():
    paths = app.openapi()["paths"]
    for path, method in [
        ("state", "get"),
        ("begin", "post"),
        ("heartbeat", "post"),
        ("finish", "post"),
        ("retry", "post"),
        ("notes", "put"),
    ]:
        assert f"/api/v1/speaking-attempts/{{attempt_id}}/{path}" in paths
        assert method in paths[f"/api/v1/speaking-attempts/{{attempt_id}}/{path}"]


async def speaking_content(session):
    test = ExamRecord(title="Fictional speaking runtime")
    version = VersionRecord(version_number=1, status="PUBLISHED")
    module = ModuleRecord(module_type="SPEAKING", order_index=0)
    test.versions.append(version)
    version.modules.append(module)
    prompts = []
    for part_number, types in [
        (1, ["SHORT_ANSWER"]),
        (2, ["LONG_TURN", "FOLLOW_UP"]),
        (3, ["SHORT_ANSWER"]),
    ]:
        part = SpeakingPart(part_number=part_number, order_index=part_number - 1)
        module.speaking_parts.append(part)
        for index, kind in enumerate(types):
            prompt = SpeakingPrompt(
                order_index=index,
                prompt_type=kind,
                prompt_text=f"Fictional {kind} {part_number}",
                preparation_seconds=60 if kind == "LONG_TURN" else 0,
                response_seconds=120 if kind == "LONG_TURN" else 60,
                config_json={"cue_points": ["A fictional point"]} if kind == "LONG_TURN" else {},
            )
            part.prompts.append(prompt)
            prompts.append(prompt)
    async with session.begin():
        session.add(test)
        await session.flush()
    session.info["speaking_fixture_test_id"] = test.id
    return version.id, [p.id for p in prompts]


async def started(session, *, mode="PRACTICE", focused=None):
    version, prompts = await speaking_content(session)
    body = dict(
        test_version_id=version, module="SPEAKING", timer={"mode": "COUNT_UP"}, speaking_mode=mode
    )
    if focused is not None:
        body.update(
            scope="FOCUSED_UNIT", focused_unit={"kind": "SPEAKING_PROMPT", "id": prompts[focused]}
        )
    attempt = await AttemptService(session).start(AttemptCreate(**body))
    from app.services.speaking_attempts import SpeakingAttemptService

    return SpeakingAttemptService(session), attempt.attempt_id, prompts


@pytest.mark.asyncio
async def test_ordered_flow_and_current_prompt_only(db_session, monkeypatch):
    now = TimerService.now()
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    service, attempt_id, prompts = await started(db_session)
    state = await service.get_state(attempt_id)
    assert state.phase == "QUESTION_ENTER"
    assert state.current_prompt.id == prompts[0]
    assert str(prompts[1]) not in state.model_dump_json()
    assert state.phase_deadline_at is None
    for index, prompt_id in enumerate(prompts):
        state = await service.begin_prompt(attempt_id, prompt_id)
        if index == 1:
            assert state.phase == "PREPARING"
            now += timedelta(seconds=60)
            state = await service.get_state(attempt_id)
            assert state.phase == "STARTING" and state.remaining_ms == 3000
            now += timedelta(seconds=3)
            state = await service.get_state(attempt_id)
        assert state.phase == "RECORDING"
        state = await service.finish_current_response(attempt_id, prompt_id, 1, "USER_DONE")
        assert state.phase == ("COMPLETED" if index == 3 else "QUESTION_ENTER")
    assert (await AttemptService(db_session).get(attempt_id)).status == "SUBMITTED"


@pytest.mark.asyncio
async def test_timeout_and_duplicate_done_commit_once(db_session, monkeypatch):
    now = TimerService.now()
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    service, attempt_id, prompts = await started(db_session)
    await service.begin_prompt(attempt_id, prompts[0])
    now += timedelta(seconds=61)
    state = await service.finish_current_response(attempt_id, prompts[0], 1, "USER_DONE")
    assert state.current_prompt.id == prompts[1]
    state = await service.finish_current_response(attempt_id, prompts[0], 1, "USER_DONE")
    assert state.current_prompt.id == prompts[1]
    from app.models.speaking import SpeakingResponse

    async with db_session.begin():
        rows = list(
            await db_session.scalars(
                select(SpeakingResponse).where(SpeakingResponse.attempt_id == attempt_id)
            )
        )
        assert len(rows) == 1
        assert rows[0].locked and rows[0].completion_reason == "TIMEOUT"
        assert rows[0].duration_ms == 60000
    with pytest.raises(AppError, match="locked"):
        await service.begin_prompt(attempt_id, prompts[0])


@pytest.mark.asyncio
async def test_expiry_stops_speech_but_waits_for_final_upload_ack(db_session, monkeypatch):
    now = TimerService.now()
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    service, attempt_id, prompts = await started(db_session)
    original = await service.begin_prompt(attempt_id, prompts[0])
    now += timedelta(seconds=61)
    state = await service.get_state(attempt_id)
    assert state.phase == "FINALIZING" and state.remaining_ms == 0
    assert state.response_id == original.response_id
    assert state.current_prompt.id == prompts[0]
    assert not state.can_retry and not state.can_replay
    with pytest.raises(AppError):
        await service.retry_current_response(attempt_id, prompts[0], 1)
    state = await service.finish_current_response(attempt_id, prompts[0], 1, "TIMEOUT")
    assert state.current_prompt.id == prompts[1]


@pytest.mark.asyncio
async def test_heartbeat_cannot_rewind_and_prep_deadline_is_authoritative(db_session, monkeypatch):
    now = TimerService.now()
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    service, attempt_id, prompts = await started(db_session, focused=1)
    await service.begin_prompt(attempt_id, prompts[1])
    now += timedelta(seconds=29)
    state = await service.heartbeat(attempt_id, prompts[1], 1, client_remaining_ms=60000)
    assert state.remaining_ms == 31000
    state = await service.heartbeat(attempt_id, prompts[1], 1, client_remaining_ms=0)
    assert state.remaining_ms == 31000
    now += timedelta(seconds=36)
    state = await service.get_state(attempt_id)
    assert state.phase == "RECORDING" and state.remaining_ms == 118000


@pytest.mark.asyncio
async def test_practice_retry_supersedes_only_current_take(db_session):
    service, attempt_id, prompts = await started(db_session)
    await service.begin_prompt(attempt_id, prompts[0])
    state = await service.retry_current_response(attempt_id, prompts[0], 1)
    assert state.take_number == 2
    state = await service.retry_current_response(attempt_id, prompts[0], 1)
    assert state.take_number == 2
    with pytest.raises(AppError):
        await service.finish_current_response(attempt_id, prompts[0], 1, "USER_DONE")
    await service.finish_current_response(attempt_id, prompts[0], 2, "USER_DONE")
    with pytest.raises(AppError):
        await service.retry_current_response(attempt_id, prompts[0], 2)
    from app.models.speaking import SpeakingResponseTake

    async with db_session.begin():
        rows = list(
            await db_session.scalars(
                select(SpeakingResponseTake)
                .where(SpeakingResponseTake.response_id == state.response_id)
                .order_by(SpeakingResponseTake.take_number)
            )
        )
        assert [row.status for row in rows] == ["SUPERSEDED", "COMMITTED"]


@pytest.mark.asyncio
@pytest.mark.parametrize("full_mock", [False, True])
async def test_exam_and_full_mock_forbid_retry_and_replay(db_session, full_mock):
    service, attempt_id, prompts = await started(db_session, mode="EXAM")
    if full_mock:
        from app.models import Attempt, TestSession

        async with db_session.begin():
            attempt = await db_session.get(Attempt, attempt_id)
            parent = TestSession(
                test_version_id=attempt.test_version_id,
                started_at=TimerService.now(),
                status="IN_PROGRESS",
                user_id=attempt.user_id,
            )
            db_session.add(parent)
            await db_session.flush()
            attempt.test_session_id = parent.id
            attempt.speaking_mode = "PRACTICE"
    state = await service.begin_prompt(attempt_id, prompts[0])
    assert not state.can_retry and not state.can_replay
    with pytest.raises(AppError) as error:
        await service.retry_current_response(attempt_id, prompts[0], 1)
    assert error.value.code == "SPEAKING_RETRY_NOT_ALLOWED"
    with pytest.raises(AppError):
        await service.authorize_current_replay(attempt_id, prompts[0], 1)


@pytest.mark.asyncio
async def test_notes_are_private_and_not_response_data(db_session):
    service, attempt_id, prompts = await started(db_session, focused=1)
    await service.begin_prompt(attempt_id, prompts[1])
    marker = "SPEAKING_PRIVATE_NOTE_SHOULD_NEVER_BE_GRADED"
    state = await service.save_notes(attempt_id, prompts[1], marker)
    assert state.scratch_notes == marker
    from app.models.speaking import SpeakingResponse
    from app.schemas.speaking import SpeakingResponseData

    async with db_session.begin():
        response = await db_session.get(SpeakingResponse, state.response_id)
        assert marker not in SpeakingResponseData.model_validate(response).model_dump_json()
    from app.services.speaking_attempts import SpeakingAttemptService

    with pytest.raises(AppError) as error:
        await SpeakingAttemptService(db_session, user_id=uuid4()).get_state(attempt_id)
    assert error.value.code == "ATTEMPT_NOT_FOUND"


@pytest.mark.asyncio
async def test_focused_target_and_generic_controls_cannot_bypass_runtime(db_session):
    service, attempt_id, prompts = await started(db_session, focused=2)
    generic = await AttemptService(db_session).get(attempt_id)
    assert generic.focused_unit.kind == "SPEAKING_PROMPT"
    assert generic.focused_unit.id == prompts[2]
    with pytest.raises(AppError):
        await service.begin_prompt(attempt_id, prompts[0])
    with pytest.raises(AppError):
        await AttemptService(db_session).pause(attempt_id)
    with pytest.raises(AppError):
        await AttemptService(db_session).submit(attempt_id)
    await service.begin_prompt(attempt_id, prompts[2])
    state = await service.finish_current_response(attempt_id, prompts[2], 1, "USER_DONE")
    assert state.phase == "COMPLETED" and state.current_prompt is None


@pytest.mark.asyncio
async def test_foreign_focused_prompt_is_rejected(db_session):
    version, _ = await speaking_content(db_session)
    _, foreign = await speaking_content(db_session)
    body = AttemptCreate(
        test_version_id=version,
        module="SPEAKING",
        timer={"mode": "COUNT_UP"},
        scope="FOCUSED_UNIT",
        focused_unit={"kind": "SPEAKING_PROMPT", "id": foreign[0]},
    )
    with pytest.raises(AppError) as error:
        await AttemptService(db_session).start(body)
    assert error.value.code == "FOCUSED_UNIT_INVALID"


@pytest.mark.asyncio
async def test_runtime_api_accepts_learner_owner_and_never_leaks_future_prompt(db_session):
    import httpx

    from app.api.dependencies import get_current_user
    from app.core.database import get_session
    from app.models import User

    _, attempt_id, prompts = await started(db_session)
    identity = db_session.info["current_user_identity"]
    learner = User(
        id=identity.id,
        email=identity.email,
        display_name="Fictional learner",
        role="USER",
        is_active=True,
        email_verified=True,
    )

    async def database_override():
        yield db_session

    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: learner
    app.dependency_overrides[get_session] = database_override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            state = await client.get(f"/api/v1/speaking-attempts/{attempt_id}/state")
            assert state.status_code == 200
            assert str(prompts[0]) in state.text and str(prompts[1]) not in state.text
            begun = await client.post(
                f"/api/v1/speaking-attempts/{attempt_id}/begin", json={"prompt_id": str(prompts[0])}
            )
            assert begun.status_code == 200 and begun.json()["phase"] == "RECORDING"
            invalid = await client.post(
                f"/api/v1/speaking-attempts/{attempt_id}/finish",
                json={
                    "prompt_id": str(prompts[1]),
                    "take_number": 1,
                    "completion_reason": "USER_DONE",
                },
            )
            assert invalid.status_code == 409
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


@pytest.mark.asyncio
async def test_timeout_requires_server_deadline_and_early_prep_done_is_rejected(db_session):
    service, attempt_id, prompts = await started(db_session, focused=1)
    await service.begin_prompt(attempt_id, prompts[1])
    for reason in ["TIMEOUT", "USER_DONE"]:
        with pytest.raises(AppError):
            await service.finish_current_response(attempt_id, prompts[1], 1, reason)
    state = await service.get_state(attempt_id)
    assert state.phase == "PREPARING"


@pytest_asyncio.fixture
async def concurrent_speaking():
    """Committed fictional rows, independently connected clients, exact-ID cleanup."""
    from app.models import Attempt, User

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = test_id = None
    try:
        async with factory() as session:
            async with session.begin():
                owner = User(
                    email=f"speaking-race-{uuid4()}@example.com",
                    display_name="Race fixture",
                    role="ADMIN",
                    is_active=True,
                    email_verified=True,
                )
                session.add(owner)
                await session.flush()
                owner_id = owner.id
            session.info["current_user_id"] = owner_id
            service, attempt_id, prompts = await started(session)
            await service.begin_prompt(attempt_id, prompts[0])
            async with session.begin():
                test_id = await session.scalar(
                    select(ExamRecord.id)
                    .join(VersionRecord)
                    .join(Attempt, Attempt.test_version_id == VersionRecord.id)
                    .where(Attempt.id == attempt_id)
                )
        yield factory, owner_id, attempt_id, prompts
    finally:
        test_id = test_id or session.info.get("speaking_fixture_test_id")
        async with factory() as session, session.begin():
            if owner_id is not None:
                await session.execute(delete(Attempt).where(Attempt.user_id == owner_id))
            if test_id is not None:
                await session.execute(delete(ExamRecord).where(ExamRecord.id == test_id))
            if owner_id is not None:
                await session.execute(delete(User).where(User.id == owner_id))
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("race", ["duplicate", "timeout", "retry"])
async def test_independent_requests_serialize_one_commit(concurrent_speaking, monkeypatch, race):
    from app.models.speaking import SpeakingResponse, SpeakingResponseTake
    from app.services.speaking_attempts import SpeakingAttemptService

    factory, owner, attempt_id, prompts = concurrent_speaking
    if race == "timeout":
        now = TimerService.now() + timedelta(seconds=61)
        monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))

    async def invoke(second):
        async with factory() as session:
            service = SpeakingAttemptService(session, user_id=owner)
            if second and race == "retry":
                return await service.retry_current_response(attempt_id, prompts[0], 1)
            if second and race == "timeout":
                return await service.get_state(attempt_id)
            return await service.finish_current_response(attempt_id, prompts[0], 1, "USER_DONE")

    outcomes = await asyncio.gather(invoke(False), invoke(True), return_exceptions=True)
    assert all(
        not isinstance(outcome, Exception) or isinstance(outcome, AppError) for outcome in outcomes
    )
    async with factory() as session:
        response = await session.scalar(
            select(SpeakingResponse).where(SpeakingResponse.attempt_id == attempt_id)
        )
        takes = list(
            await session.scalars(
                select(SpeakingResponseTake).where(SpeakingResponseTake.response_id == response.id)
            )
        )
        if response.locked:
            assert sum(t.status == "COMMITTED" for t in takes) == 1
            assert len(takes) == 1  # retry cannot supersede after the winning finalization
        else:
            assert race == "retry" and response.active_take_number == 2
            assert [t.status for t in sorted(takes, key=lambda t: t.take_number)] == [
                "SUPERSEDED",
                "ACTIVE",
            ]
            assert sum(isinstance(outcome, AppError) for outcome in outcomes) == 1
