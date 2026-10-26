import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_speaking_attempts import concurrent_speaking as concurrent_speaking
from test_speaking_attempts import started

from app.core.exceptions import AppError
from app.models import User
from app.services.attempts import AttemptService
from app.services.speaking_media import SpeakingMediaService
from app.storage.local import LocalAssetStorage


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_private_chunk_rollback_compensates_cancellation(
    concurrent_speaking, tmp_path, monkeypatch, failure
):
    from app.models.speaking import SpeakingAudioChunk

    factory, owner, aid, prompts = concurrent_speaking
    actor = User(id=owner, role="ADMIN", is_active=True)
    storage = LocalAssetStorage(tmp_path)
    async with factory() as setup:
        segment = await SpeakingMediaService(setup, actor, storage=storage).create_segment(
            aid, prompts[0], 1, 0, "audio/webm"
        )
    async with factory() as session:
        original_flush = session.flush

        async def fail_chunk_flush(*args, **kwargs):
            if any(isinstance(row, SpeakingAudioChunk) for row in session.new):
                raise failure("injected chunk flush failure")
            return await original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", fail_chunk_flush)
        with pytest.raises(failure):
            await SpeakingMediaService(session, actor, storage=storage).upload_chunk(
                aid, segment.id, 0, b"fictional-chunk"
            )
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


async def test_private_chunk_lost_commit_acknowledgement_keeps_committed_media(
    concurrent_speaking, tmp_path, monkeypatch
):
    from sqlalchemy import select

    from app.models.speaking import SpeakingAudioChunk

    factory, owner, aid, prompts = concurrent_speaking
    actor = User(id=owner, role="ADMIN", is_active=True)
    storage = LocalAssetStorage(tmp_path)
    async with factory() as setup:
        segment = await SpeakingMediaService(setup, actor, storage=storage).create_segment(
            aid, prompts[0], 1, 0, "audio/webm"
        )
    async with factory() as session:
        begin = session.begin

        class LostAcknowledgement:
            async def __aenter__(self):
                self.transaction = begin()
                return await self.transaction.__aenter__()

            async def __aexit__(self, *args):
                await self.transaction.__aexit__(*args)
                raise RuntimeError("injected lost commit acknowledgement")

        monkeypatch.setattr(session, "begin", LostAcknowledgement)
        with pytest.raises(RuntimeError):
            await SpeakingMediaService(session, actor, storage=storage).upload_chunk(
                aid, segment.id, 0, b"fictional-chunk"
            )
    async with factory() as verify:
        chunk = await verify.scalar(
            select(SpeakingAudioChunk).where(SpeakingAudioChunk.segment_id == segment.id)
        )
        assert chunk is not None
        assert storage.resolve(chunk.storage_key).read_bytes() == b"fictional-chunk"


@pytest.fixture(autouse=True)
def cleanup_test_media(tmp_path):
    yield
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.unlink()


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
        from app.models.speaking import SpeakingAudioChunk, SpeakingAudioSegment

        assert await db_session.get(SpeakingAudioSegment, seg.id) is None
        assert not list(
            await db_session.scalars(
                select(SpeakingAudioChunk).where(SpeakingAudioChunk.segment_id == seg.id)
            )
        )
    await drain_media_cleanup(db_session, storage=media.storage)
    assert len(list(tmp_path.rglob("*.webm"))) == 1
    assert (await sibling_media.playback(sibling, sibling_seg.id))[0][0].read_bytes() == b"retained"


async def test_assignment_teacher_provenance_and_retention(db_session, tmp_path):
    from teacher_helpers import make_user

    from app.models import Attempt, Classroom, ClassroomAssignment

    teacher = await make_user(db_session, "TEACHER")
    other = await make_user(db_session, "TEACHER")
    runtime, media, aid, prompts, state, seg = await recording(db_session, tmp_path, focused=0)
    await media.upload_chunk(aid, seg.id, 0, b"assignment")
    await media.close_segment(aid, seg.id, 1)
    await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        version_id = attempt.test_version_id
        classroom = Classroom(teacher_id=teacher.id, name="Fictional classroom")
        db_session.add(classroom)
        await db_session.flush()
        other_classroom = Classroom(teacher_id=other.id, name="Another owned classroom")
        db_session.add(other_classroom)
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
    with pytest.raises(AppError) as mutation_error:
        await teacher_media.upload_chunk(aid, seg.id, 0, b"assignment")
    assert mutation_error.value.code == "ATTEMPT_NOT_FOUND"
    with pytest.raises(AppError):
        await SpeakingMediaService(db_session, other, storage=media.storage).playback(aid, seg.id)
    with pytest.raises(AppError) as error:
        await AttemptService(db_session).delete_attempt(aid)
    assert error.value.code == "ASSIGNMENT_HISTORY_RETAINED"
    assert len(list(tmp_path.rglob("*.webm"))) == 1
    await AttemptService(db_session).delete_standalone_history(version_id)
    assert (await media.manifest(aid, state.response_id)).response.locked
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        attempt.classroom_assignment_id = None
    with pytest.raises(AppError):
        await teacher_media.playback(aid, seg.id)


async def test_review_committed_take_and_authored_prompt_without_notes(db_session, tmp_path):
    runtime, media, aid, prompts, state, seg = await recording(db_session, tmp_path, focused=0)
    with pytest.raises(AppError):
        await media.review(aid)
    await media.upload_chunk(aid, seg.id, 0, b"final recording")
    await media.close_segment(aid, seg.id, 1)
    await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    review = await media.review(aid)
    assert review.parts[0].responses[0].prompt.id == prompts[0]
    assert review.parts[0].responses[0].response.locked
    assert "scratch_notes" not in review.model_dump_json()


async def test_runtime_validation_never_echoes_private_notes(db_session):
    from teacher_helpers import api_client

    runtime, aid, prompts = await started(db_session, focused=1)
    await runtime.begin_prompt(aid, prompts[1])
    marker = "PRIVATE_NOTE_REDACTION_MARKER"
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        response = await client.put(
            f"/api/v1/speaking-attempts/{aid}/notes",
            json={"prompt_id": str(prompts[1]), "scratch_notes": marker * 1000},
        )
    assert response.status_code == 422
    assert marker not in response.text
    assert response.json()["code"] == "SPEAKING_REQUEST_INVALID"


async def test_out_of_order_201_http_retries_and_path_headers_are_safe(
    db_session, tmp_path, monkeypatch
):
    from hashlib import sha256

    from sqlalchemy import func
    from teacher_helpers import api_client

    from app.core.config import get_settings
    from app.models.speaking import SpeakingAudioChunk

    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    _, media, aid, _, state, seg = await recording(db_session, tmp_path)
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        for sequence, content in [(2, b"two"), (0, b"zero"), (1, b"one")]:
            path = f"/api/v1/speaking-attempts/{aid}/segments/{seg.id}/chunks/{sequence}"
            response = await client.put(
                path,
                content=content,
                headers={"Content-Disposition": 'attachment; filename="../../outside.webm"'},
            )
            assert response.status_code == 200
            duplicate = await client.put(path, content=content)
            assert duplicate.json()["id"] == response.json()["id"]
        conflict = await client.put(path, content=b"different")
        assert (
            conflict.status_code == 409
            and conflict.json()["code"] == "SPEAKING_CHUNK_SEQUENCE_CONFLICT"
        )
        assert "storage_key" not in response.text and str(tmp_path) not in response.text
    manifest = await media.manifest(aid, state.response_id)
    assert [c.sequence for c in manifest.segments[0].chunks] == [0, 1, 2]
    assert [c.sha256 for c in manifest.segments[0].chunks] == [
        sha256(b"zero").hexdigest(),
        sha256(b"one").hexdigest(),
        sha256(b"two").hexdigest(),
    ]
    async with db_session.begin():
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(SpeakingAudioChunk)
                .where(SpeakingAudioChunk.segment_id == seg.id)
            )
            == 3
        )
    assert (
        len(list(tmp_path.rglob("*.webm"))) == 3 and not (tmp_path.parent / "outside.webm").exists()
    )


async def test_cross_attempt_and_unrelated_users_cannot_read_or_mutate(db_session, tmp_path):
    from teacher_helpers import make_user

    _, media, aid, _, state, seg = await recording(db_session, tmp_path)
    await media.upload_chunk(aid, seg.id, 0, b"private body")
    _, _, sibling, _, _, _ = await recording(db_session, tmp_path)
    for role in ("USER", "TEACHER"):
        actor = await make_user(db_session, role)
        outsider = SpeakingMediaService(db_session, actor, storage=media.storage)
        for read in (
            lambda outsider=outsider: outsider.playback(aid, seg.id),
            lambda outsider=outsider: outsider.manifest(aid, state.response_id),
        ):
            with pytest.raises(AppError) as error:
                await read()
            assert error.value.status_code in {403, 404}
    for action in (
        lambda: media.playback(sibling, seg.id),
        lambda: media.manifest(sibling, state.response_id),
        lambda: media.upload_chunk(sibling, seg.id, 1, b"invalid"),
    ):
        with pytest.raises(AppError) as error:
            await action()
        assert error.value.code == "SPEAKING_MEDIA_NOT_FOUND"


async def test_oversized_http_body_rejected_before_storage(db_session, tmp_path, monkeypatch):
    from teacher_helpers import api_client

    from app.core.config import get_settings

    _, _, aid, _, _, seg = await recording(db_session, tmp_path)
    monkeypatch.setattr(get_settings(), "speaking_max_chunk_bytes", 1024)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        response = await client.put(
            f"/api/v1/speaking-attempts/{aid}/segments/{seg.id}/chunks/0", content=b"x" * 1025
        )
    assert response.status_code == 422 and response.json()["code"] == "SPEAKING_UPLOAD_INVALID"
    assert list(tmp_path.rglob("*.webm")) == []


async def test_superseded_audio_retained_until_deletion_and_fingerprint_changes(
    db_session, tmp_path
):
    from app.models import SpeakingResponseTake
    from app.services.speaking_media import committed_fingerprint, drain_media_cleanup

    runtime, media, aid, prompts, state, first = await recording(db_session, tmp_path, focused=0)
    await media.upload_chunk(aid, first.id, 0, b"old source")
    await media.close_segment(aid, first.id, 1)
    async with db_session.begin():
        old_take = await runtime.repository.take(state.response_id, 1)
        old_fingerprint = await committed_fingerprint(db_session, old_take)
    await runtime.retry_current_response(aid, prompts[0], 1)
    second = await media.create_segment(aid, prompts[0], 2, 0, "audio/webm;codecs=opus")
    await media.upload_chunk(aid, second.id, 0, b"new source")
    await media.close_segment(aid, second.id, 1)
    await runtime.finish_current_response(aid, prompts[0], 2, "USER_DONE")
    manifest = await media.manifest(aid, state.response_id)
    assert [s.id for s in manifest.segments] == [second.id]
    assert manifest.response.committed_audio_fingerprint != old_fingerprint
    async with db_session.begin():
        assert (await db_session.get(SpeakingResponseTake, old_take.id)).status == "SUPERSEDED"
    with pytest.raises(AppError):
        await media.playback(aid, first.id)
    assert len(list(tmp_path.rglob("*.webm"))) == 2
    await AttemptService(db_session).delete_attempt(aid)
    await drain_media_cleanup(db_session, storage=media.storage)
    assert list(tmp_path.rglob("*.webm")) == []


async def test_cleanup_keeps_shared_reference_and_failed_jobs(db_session, tmp_path, monkeypatch):
    from app.models.speaking import SpeakingAudioChunk, SpeakingMediaCleanup
    from app.services.speaking_media import drain_media_cleanup

    _, media, aid, _, _, seg = await recording(db_session, tmp_path)
    chunk = await media.upload_chunk(aid, seg.id, 0, b"shared source")
    _, _, sibling, _, _, other = await recording(db_session, tmp_path)
    async with db_session.begin():
        key = (await db_session.get(SpeakingAudioChunk, chunk.id)).storage_key
        db_session.add(
            SpeakingAudioChunk(
                segment_id=other.id,
                sequence=0,
                storage_key=key,
                sha256=chunk.sha256,
                byte_size=chunk.byte_size,
            )
        )
    await AttemptService(db_session).delete_attempt(aid)
    await drain_media_cleanup(db_session, storage=media.storage)
    assert media.storage.resolve(key).read_bytes() == b"shared source"
    await AttemptService(db_session).delete_attempt(sibling)
    delete_file = media.storage.delete
    monkeypatch.setattr(
        media.storage, "delete", lambda _: (_ for _ in ()).throw(OSError("private path"))
    )
    with pytest.raises(OSError):
        await drain_media_cleanup(db_session, storage=media.storage)
    async with db_session.begin():
        assert (await db_session.scalar(select(SpeakingMediaCleanup))).storage_key == key
    monkeypatch.setattr(media.storage, "delete", delete_file)
    await drain_media_cleanup(db_session, storage=media.storage)
    assert list(tmp_path.rglob("*.webm")) == []


@pytest.mark.parametrize("different", [False, True])
async def test_independent_chunk_uploads_create_one_row_and_file(
    concurrent_speaking,  # noqa: F811
    tmp_path,
    different,
):
    import asyncio

    from app.models.speaking import SpeakingAudioChunk

    factory, owner, aid, prompts = concurrent_speaking
    storage = LocalAssetStorage(tmp_path)
    async with factory() as session:
        async with session.begin():
            actor = await session.get(User, owner)
        segment = await SpeakingMediaService(session, actor, storage=storage).create_segment(
            aid, prompts[0], 1, 0, "audio/webm;codecs=opus"
        )

    async def upload(content):
        async with factory() as session:
            return await SpeakingMediaService(session, actor, storage=storage).upload_chunk(
                aid, segment.id, 0, content
            )

    results = await asyncio.gather(
        upload(b"original"),
        upload(b"changed" if different else b"original"),
        return_exceptions=True,
    )
    if different:
        errors = [r for r in results if isinstance(r, AppError)]
        assert len(errors) == 1 and errors[0].code == "SPEAKING_CHUNK_SEQUENCE_CONFLICT"
    else:
        assert results[0].id == results[1].id
    async with factory() as session:
        rows = list(
            await session.scalars(
                select(SpeakingAudioChunk).where(SpeakingAudioChunk.segment_id == segment.id)
            )
        )
        assert len(rows) == 1
    assert len(list(tmp_path.rglob("*.webm"))) == 1
