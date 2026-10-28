from contextlib import contextmanager
from io import BytesIO

import pytest
from sqlalchemy import select
from test_speaking_transcript import completed, fake_decode
from test_storage_contract import FakeS3

from app.core.config import Settings
from app.models.speaking import SpeakingAudioChunk
from app.services.speaking_audio import normalize_committed_take, stage_normalized_audio
from app.storage.s3 import S3CompatibleStorage


@pytest.mark.parametrize("backend", ["local", "s3"])
async def test_normalized_audio_cache_is_storage_backed_and_stage_is_temporary(
    isolated_db_session, tmp_path, backend
):
    session = isolated_db_session
    _aid, response_id, media = await completed(session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    storage = media.storage
    if backend == "s3":
        storage = S3CompatibleStorage(client=FakeS3(), bucket="private")
        chunks = list(await session.scalars(select(SpeakingAudioChunk)))
        for chunk in chunks:
            content = media.storage.resolve(chunk.storage_key).read_bytes()
            storage.put_stream(
                chunk.storage_key,
                BytesIO(content),
                content_type="audio/webm",
                max_bytes=len(content),
            )
        await session.rollback()
    calls = []

    def decode(args, timeout):
        calls.append(1)
        fake_decode(args, timeout)

    first = await normalize_committed_take(
        session, response_id, settings, storage=storage, executor=decode
    )
    second = await normalize_committed_take(
        session, response_id, settings, storage=storage, executor=decode
    )
    assert first.storage_key == second.storage_key
    assert first.storage_key.startswith("speaking-derived/")
    assert calls == [1]
    async with stage_normalized_audio(
        storage, first, settings.speaking_max_decoded_seconds
    ) as audio:
        path = audio.path
        assert path.exists() and audio.duration_ms == 1000
    assert not path.exists()

    @contextmanager
    def unavailable(_key, **_kwargs):
        raise RuntimeError("temporary provider failure")
        yield

    original_open_reader = storage.open_reader
    storage.open_reader = unavailable
    with pytest.raises(RuntimeError, match="temporary provider failure"):
        await normalize_committed_take(
            session, response_id, settings, storage=storage, executor=decode
        )
    storage.open_reader = original_open_reader
    third = await normalize_committed_take(
        session, response_id, settings, storage=storage, executor=decode
    )
    assert third.storage_key == first.storage_key and calls == [1]
