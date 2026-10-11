import asyncio
from datetime import timedelta

import pytest
from test_speaking_attempts import concurrent_speaking, started  # noqa: F401

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.services.speaking_attempts import SpeakingAttemptService


async def interrupted(session, monkeypatch):
    now = [TimerService.now()]
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now[0]))
    service, aid, prompts = await started(session)
    await service.begin_prompt(aid, prompts[0])
    now[0] += timedelta(seconds=29)
    await service.heartbeat(aid, prompts[0], 1, client_remaining_ms=60000)
    now[0] += timedelta(seconds=2)
    state = await service.interrupt(aid, prompts[0], 1, 0)
    assert state.phase == "INTERRUPTED" and state.remaining_ms == 31000
    return service, aid, prompts, now, state


async def test_31_seconds_one_grace_and_no_refresh_rewind(db_session, monkeypatch):
    service, aid, prompts, now, state = await interrupted(db_session, monkeypatch)
    restored = await service.resume(aid, prompts[0], 1, state.interruption_generation)
    assert restored.phase == "RECOVERY_GRACE" and restored.remaining_ms == 31000
    assert restored.recovery_grace_seconds == 7
    deadline = restored.recovery_grace_deadline_at
    now[0] += timedelta(seconds=4)
    repeat = await service.interrupt(aid, prompts[0], 1, state.interruption_generation)
    repeat = await service.resume(aid, prompts[0], 1, repeat.interruption_generation)
    assert repeat.recovery_grace_deadline_at == deadline and repeat.remaining_ms == 31000
    now[0] += timedelta(seconds=3)
    live = await service.get_state(aid)
    assert live.phase == "RECORDING" and live.remaining_ms == 31000
    now[0] += timedelta(seconds=6)
    repeat = await service.interrupt(aid, prompts[0], 1, state.interruption_generation)
    repeat = await service.resume(aid, prompts[0], 1, repeat.interruption_generation)
    assert repeat.remaining_ms == 25000 and repeat.phase == "RECORDING"
    now[0] += timedelta(seconds=25)
    finished = await service.finish_current_response(aid, prompts[0], 1, "TIMEOUT")
    assert finished.current_prompt.id == prompts[1]
    from sqlalchemy import select

    from app.models import SpeakingResponse

    async with db_session.begin():
        response = await db_session.scalar(
            select(SpeakingResponse).where(SpeakingResponse.attempt_id == aid)
        )
        assert response.duration_ms == 60000


async def test_stale_generation_late_recovery_and_finalized_fail_closed(db_session, monkeypatch):
    service, aid, prompts, now, state = await interrupted(db_session, monkeypatch)
    with pytest.raises(AppError):
        await service.resume(aid, prompts[0], 1, 0)
    now[0] += timedelta(seconds=46)
    with pytest.raises(AppError) as error:
        await service.resume(aid, prompts[0], 1, state.interruption_generation)
    assert error.value.code == "SPEAKING_RECOVERY_NOT_AVAILABLE"
    # A different already-finalized response cannot reopen.
    service, aid, prompts = await started(db_session)
    await service.begin_prompt(aid, prompts[0])
    await service.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    with pytest.raises(AppError):
        await service.interrupt(aid, prompts[0], 1, 0)


async def test_get_state_does_not_overwrite_last_ack_snapshot(db_session, monkeypatch):
    now = [TimerService.now()]
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now[0]))
    service, aid, prompts = await started(db_session)
    await service.begin_prompt(aid, prompts[0])
    now[0] += timedelta(seconds=29)
    await service.heartbeat(aid, prompts[0], 1)
    now[0] += timedelta(seconds=3)
    assert (await service.get_state(aid)).remaining_ms == 28000
    assert (await service.interrupt(aid, prompts[0], 1, 0)).remaining_ms == 31000


async def test_recovery_seals_old_container_and_uses_new_segment(db_session, monkeypatch, tmp_path):
    from test_speaking_media import recording

    now = [TimerService.now()]
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now[0]))
    service, media, aid, prompts, _, segment = await recording(db_session, tmp_path)
    now[0] += timedelta(seconds=29)
    await media.upload_chunk(aid, segment.id, 0, b"previous container")
    state = await service.interrupt(aid, prompts[0], 1, 0)
    assert state.remaining_ms == 31000 and state.next_segment_index == 1
    await service.resume(aid, prompts[0], 1, state.interruption_generation)
    now[0] += timedelta(seconds=7)
    await service.get_state(aid)
    new = await media.create_segment(aid, prompts[0], 1, 1, "audio/webm;codecs=opus")
    assert new.id != segment.id
    now[0] += timedelta(seconds=1)
    await media.upload_chunk(aid, new.id, 0, b"new container")
    state = await service.heartbeat(aid, prompts[0], 1, client_remaining_ms=60000)
    assert state.remaining_ms == 30000
    paths, _ = await media.playback(aid, segment.id)
    assert paths[0].read_bytes() == b"previous container"
    paths[0].unlink()
    for path in (await media.playback(aid, new.id))[0]:
        path.unlink()


async def test_exam_recovery_manifest_exposes_accepted_metadata_without_playback(
    db_session, monkeypatch, tmp_path
):
    from test_speaking_media import recording

    service, media, aid, prompts, state, segment = await recording(
        db_session, tmp_path, mode="EXAM"
    )
    await media.upload_chunk(aid, segment.id, 0, b"accepted private bytes")
    await service.interrupt(aid, prompts[0], 1, 0)
    manifest = await media.manifest(aid, state.response_id)
    assert manifest.segments[0].chunks[0].byte_size == 22
    assert manifest.segments[0].content_url is None
    with pytest.raises(AppError):
        await media.playback(aid, segment.id)
    for path in tmp_path.rglob("*.webm"):
        path.unlink()


@pytest.mark.parametrize("race", ["resume", "finalize"])
async def test_concurrent_recovery_never_reopens_finalization(concurrent_speaking, race):  # noqa: F811
    factory, owner, aid, prompts = concurrent_speaking
    if race == "resume":
        async with factory() as session:
            generation = (
                await SpeakingAttemptService(session, owner).interrupt(aid, prompts[0], 1, 0)
            ).interruption_generation
    else:
        generation = 0

    async def invoke(second):
        async with factory() as session:
            service = SpeakingAttemptService(session, owner)
            if race == "resume":
                return await service.resume(aid, prompts[0], 1, generation)
            if second:
                return await service.interrupt(aid, prompts[0], 1, generation)
            return await service.finish_current_response(aid, prompts[0], 1, "USER_DONE")

    results = await asyncio.gather(invoke(False), invoke(True), return_exceptions=True)
    assert all(not isinstance(r, Exception) or isinstance(r, AppError) for r in results)
    from sqlalchemy import select

    from app.models import SpeakingPromptProgress, SpeakingResponse, SpeakingResponseTake

    async with factory() as session:
        progress = await session.get(SpeakingPromptProgress, aid)
        responses = list(
            await session.scalars(
                select(SpeakingResponse).where(SpeakingResponse.attempt_id == aid)
            )
        )
        takes = list(
            await session.scalars(
                select(SpeakingResponseTake).where(
                    SpeakingResponseTake.response_id == responses[0].id
                )
            )
        )
        assert len(responses) == len(takes) == 1
        if race == "resume":
            assert progress.phase == "RECOVERY_GRACE" and progress.interruption_count == 1
            assert progress.recovery_grace_used and not responses[0].locked
            assert takes[0].status == "ACTIVE"
        elif responses[0].locked:
            assert progress.prompt_id == prompts[1] and progress.phase == "QUESTION_ENTER"
            assert takes[0].status == "COMMITTED"
            assert responses[0].completion_reason == "USER_DONE"
        else:
            assert progress.prompt_id == prompts[0] and progress.phase == "INTERRUPTED"
            assert takes[0].status == "ACTIVE"
    if race == "resume":
        assert results[0].recovery_grace_deadline_at == results[1].recovery_grace_deadline_at
    else:
        async with factory() as session:
            state = await SpeakingAttemptService(session, owner).get_state(aid)
            assert state.current_prompt.id == prompts[1] or state.phase == "INTERRUPTED"


async def test_many_reload_calls_remain_monotonic_and_finalized_generation_rejected(
    db_session, monkeypatch
):
    from sqlalchemy import select

    from app.models import SpeakingPromptProgress, SpeakingResponse, SpeakingResponseTake

    service, aid, prompts, now, first = await interrupted(db_session, monkeypatch)
    await service.resume(aid, prompts[0], 1, first.interruption_generation)
    for elapsed in [1, 2, 4]:
        now[0] += timedelta(seconds=elapsed)
        state = await service.resume(aid, prompts[0], 1, first.interruption_generation)
        assert state.remaining_ms == 31000
    previous = 31000
    for _ in range(4):
        now[0] += timedelta(seconds=1)
        state = await service.interrupt(aid, prompts[0], 1, first.interruption_generation)
        state = await service.resume(aid, prompts[0], 1, first.interruption_generation)
        assert state.remaining_ms == previous - 1000
        previous = state.remaining_ms
    await service.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    with pytest.raises(AppError) as error:
        await service.resume(aid, prompts[0], 1, first.interruption_generation)
    assert error.value.code == "SPEAKING_PREVIOUS_PROMPT_LOCKED"
    async with db_session.begin():
        progress = await db_session.get(SpeakingPromptProgress, aid)
        rows = list(
            await db_session.scalars(
                select(SpeakingResponse).where(SpeakingResponse.attempt_id == aid)
            )
        )
        takes = list(
            await db_session.scalars(
                select(SpeakingResponseTake).where(SpeakingResponseTake.response_id == rows[0].id)
            )
        )
        assert progress.interruption_count == 1 and progress.prompt_id == prompts[1]
        assert len(rows) == len(takes) == 1 and takes[0].status == "COMMITTED"


async def test_part2_prep_recovery_preserves_notes_and_original_31_seconds(
    db_session, monkeypatch, tmp_path
):
    from app.services.speaking_media import SpeakingMediaService
    from app.storage.local import LocalAssetStorage

    now = [TimerService.now()]
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now[0]))
    service, aid, prompts = await started(db_session, focused=1)
    await service.begin_prompt(aid, prompts[1])
    marker = "SPEAKING_PRIVATE_NOTE_SHOULD_NEVER_BE_GRADED"
    await service.save_notes(aid, prompts[1], marker)
    now[0] += timedelta(seconds=29)
    await service.heartbeat(aid, prompts[1], 1)
    now[0] += timedelta(seconds=1)
    interrupted_state = await service.interrupt(aid, prompts[1], 1, 0)
    assert interrupted_state.remaining_ms == 31000 and interrupted_state.scratch_notes == marker
    await service.resume(aid, prompts[1], 1, interrupted_state.interruption_generation)
    now[0] += timedelta(seconds=7)
    resumed = await service.get_state(aid)
    assert resumed.phase == "PREPARING" and resumed.remaining_ms == 31000
    media = SpeakingMediaService(
        db_session, db_session.info["current_user_identity"], storage=LocalAssetStorage(tmp_path)
    )
    manifest = await media.manifest(aid, resumed.response_id)
    assert (
        marker not in manifest.model_dump_json()
        and "scratch_notes" not in manifest.model_dump_json()
    )
    now[0] += timedelta(seconds=31)
    assert (await service.get_state(aid)).phase == "STARTING"
    now[0] += timedelta(seconds=3)
    assert (await service.get_state(aid)).remaining_ms == 120000


async def test_unconfirmed_tail_is_not_in_recovered_manifest(db_session, tmp_path):
    import hashlib

    from test_speaking_media import recording

    service, media, aid, prompts, state, segment = await recording(db_session, tmp_path)
    accepted = await media.upload_chunk(aid, segment.id, 0, b"accepted")
    unconfirmed = b"lost in memory"
    await service.interrupt(aid, prompts[0], 1, 0)
    manifest = await media.manifest(aid, state.response_id)
    assert manifest.segments[0].chunk_count == 1
    assert [c.sha256 for c in manifest.segments[0].chunks] == [accepted.sha256]
    assert hashlib.sha256(unconfirmed).hexdigest() not in manifest.model_dump_json()
    for path in tmp_path.rglob("*.webm"):
        path.unlink()


async def test_stale_first_reconnect_closes_speech_without_granting_time(db_session, monkeypatch):
    from sqlalchemy import select

    from app.models import SpeakingResponse

    now = [TimerService.now()]
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now[0]))
    service, aid, prompts = await started(db_session, focused=1)
    await service.begin_prompt(aid, prompts[1])
    now[0] += timedelta(seconds=63)
    await service.get_state(aid)
    now[0] += timedelta(seconds=10)
    await service.heartbeat(aid, prompts[1], 1)
    now[0] += timedelta(seconds=46)
    with pytest.raises(AppError) as error:
        await service.interrupt(aid, prompts[1], 1, 0)
    assert error.value.code == "SPEAKING_RECOVERY_NOT_AVAILABLE"
    state = await service.get_state(aid)
    assert state.phase == "FINALIZING" and state.remaining_ms == 0
    await service.finish_current_response(aid, prompts[1], 1, "TIMEOUT")
    async with db_session.begin():
        response = await db_session.scalar(
            select(SpeakingResponse).where(SpeakingResponse.attempt_id == aid)
        )
        assert response.completion_reason == "INTERRUPTED" and response.duration_ms == 10000
