from uuid import uuid4

import pytest
from sqlalchemy import select
from test_speaking_attempts import started

from app.core.exceptions import AppError
from app.models import User
from app.services.attempts import AttemptService
from app.services.speaking_media import SpeakingMediaService
from app.storage.local import LocalAssetStorage


async def recording(session, tmp_path, *, mode="PRACTICE", focused=None):
    runtime, attempt_id, prompts = await started(session, mode=mode, focused=focused)
    state = await runtime.begin_prompt(attempt_id, prompts[0])
    actor = session.info["current_user_identity"]
    media = SpeakingMediaService(session, actor, storage=LocalAssetStorage(tmp_path))
    segment = await media.create_segment(attempt_id, prompts[0], 1, 0, "audio/webm;codecs=opus")
    return runtime, media, attempt_id, prompts, state, segment


async def test_chunks_idempotent_conflict_order_and_fingerprint(db_session, tmp_path):
    runtime, media, attempt_id, prompts, state, segment = await recording(
        db_session, tmp_path, focused=0
    )
    late = await media.upload_chunk(attempt_id, segment.id, 1, b"second")
    first = await media.upload_chunk(attempt_id, segment.id, 0, b"first")
    duplicate = await media.upload_chunk(attempt_id, segment.id, 0, b"first")
    assert duplicate.id == first.id
    with pytest.raises(AppError) as error:
        await media.upload_chunk(attempt_id, segment.id, 0, b"changed")
    assert error.value.code == "SPEAKING_CHUNK_SEQUENCE_CONFLICT"
    await media.close_segment(attempt_id, segment.id, 2)
    await runtime.finish_current_response(attempt_id, prompts[0], 1, "USER_DONE")
    manifest = await media.manifest(attempt_id, state.response_id)
    assert [c.sha256 for c in manifest.segments[0].chunks] == [first.sha256, late.sha256]
    assert manifest.response.committed_audio_fingerprint
    assert manifest == await media.manifest(attempt_id, state.response_id)
    assert "storage_key" not in manifest.model_dump_json()
    paths, mime = await media.playback(attempt_id, segment.id)
    assert b"".join(path.read_bytes() for path in paths) == b"firstsecond"
    assert mime == "audio/webm;codecs=opus"
    assert duplicate == await media.upload_chunk(attempt_id, segment.id, 0, b"first")


async def test_finalization_requires_closed_contiguous_manifest(db_session, tmp_path):
    runtime, media, aid, prompts, _, seg = await recording(db_session, tmp_path)
    await media.upload_chunk(aid, seg.id, 1, b"second")
    with pytest.raises(AppError):
        await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    with pytest.raises(AppError):
        await media.close_segment(aid, seg.id, 2)
    await media.upload_chunk(aid, seg.id, 0, b"first")
    await media.close_segment(aid, seg.id, 2)
    assert (
        await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    ).current_prompt.id == prompts[1]


async def test_private_playback_exam_and_superseded_take(db_session, tmp_path):
    runtime, media, aid, prompts, state, seg = await recording(db_session, tmp_path, mode="EXAM")
    await media.upload_chunk(aid, seg.id, 0, b"private")
    with pytest.raises(AppError):
        await media.playback(aid, seg.id)
    await media.close_segment(aid, seg.id, 1)
    await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    outsider = User(id=uuid4(), role="TEACHER", is_active=True)
    with pytest.raises(AppError):
        await SpeakingMediaService(db_session, outsider, storage=media.storage).playback(
            aid, seg.id
        )
    # Exam committed recordings unlock only after the whole attempt is finalized.
    with pytest.raises(AppError):
        await media.playback(aid, seg.id)
    runtime, media, aid, prompts, state, seg = await recording(db_session, tmp_path)
    await media.upload_chunk(aid, seg.id, 0, b"old")
    await runtime.retry_current_response(aid, prompts[0], 1)
    with pytest.raises(AppError):
        await media.playback(aid, seg.id)
    with pytest.raises(AppError):
        await media.upload_chunk(aid, seg.id, 1, b"new")


@pytest.mark.parametrize("mime", ["text/plain", "audio/wav", "video/webm"])
async def test_mime_and_chunk_limits(db_session, tmp_path, mime):
    runtime, media, aid, prompts, _, seg = await recording(db_session, tmp_path)
    with pytest.raises(AppError):
        await media.create_segment(aid, prompts[0], 1, 1, mime)
    with pytest.raises(AppError):
        await media.upload_chunk(aid, seg.id, 0, b"")
    media.max_chunk_bytes = 5
    with pytest.raises(AppError):
        await media.upload_chunk(aid, seg.id, 0, b"123456")


async def test_deletion_queues_owned_media_and_preserves_sibling(db_session, tmp_path):
    from app.models.speaking import SpeakingMediaCleanup
    from app.services.speaking_media import drain_media_cleanup

    _, media, aid, _, _, seg = await recording(db_session, tmp_path)
    await media.upload_chunk(aid, seg.id, 0, b"private")
    _, sibling_media, sibling, _, _, sibling_seg = await recording(db_session, tmp_path)
    await sibling_media.upload_chunk(sibling, sibling_seg.id, 0, b"retained")
    await AttemptService(db_session).delete_attempt(aid)
    async with db_session.begin():
        assert len(list(await db_session.scalars(select(SpeakingMediaCleanup)))) == 1
    await drain_media_cleanup(db_session, storage=media.storage)
    assert len(list(tmp_path.rglob("*.webm"))) == 1
    assert (await sibling_media.playback(sibling, sibling_seg.id))[0][0].read_bytes() == b"retained"


async def test_assignment_teacher_provenance_and_retention(db_session, tmp_path):
    from teacher_helpers import make_user

    from app.models import Attempt, Classroom, ClassroomAssignment

    teacher = await make_user(db_session, "TEACHER")
    other = await make_user(db_session, "TEACHER")
    runtime, media, aid, prompts, _, seg = await recording(db_session, tmp_path, focused=0)
    await media.upload_chunk(aid, seg.id, 0, b"assignment")
    await media.close_segment(aid, seg.id, 1)
    await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        classroom = Classroom(teacher_id=teacher.id, name="Fictional classroom")
        db_session.add(classroom)
        await db_session.flush()
        assignment = ClassroomAssignment(
            classroom_id=classroom.id,
            test_version_id=attempt.test_version_id,
            created_by_user_id=teacher.id,
        )
        db_session.add(assignment)
        await db_session.flush()
        attempt.classroom_assignment_id = assignment.id
    teacher_media = SpeakingMediaService(db_session, teacher, storage=media.storage)
    assert (await teacher_media.playback(aid, seg.id))[0][0].read_bytes() == b"assignment"
    with pytest.raises(AppError):
        await SpeakingMediaService(db_session, other, storage=media.storage).playback(aid, seg.id)
    with pytest.raises(AppError) as error:
        await AttemptService(db_session).delete_attempt(aid)
    assert error.value.code == "ASSIGNMENT_HISTORY_RETAINED"
    assert len(list(tmp_path.rglob("*.webm"))) == 1
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        attempt.classroom_assignment_id = None
    with pytest.raises(AppError):
        await teacher_media.playback(aid, seg.id)
