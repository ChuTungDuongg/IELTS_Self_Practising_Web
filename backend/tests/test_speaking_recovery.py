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
    if race == "resume":
        assert results[0].recovery_grace_deadline_at == results[1].recovery_grace_deadline_at
    else:
        async with factory() as session:
            state = await SpeakingAttemptService(session, owner).get_state(aid)
            assert state.current_prompt.id == prompts[1] or state.phase == "INTERRUPTED"
