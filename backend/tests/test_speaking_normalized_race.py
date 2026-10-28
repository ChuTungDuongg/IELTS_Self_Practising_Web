"""Durable normalized-audio races on isolated PostgreSQL."""

import asyncio

import pytest
from sqlalchemy import select
from test_speaking_attempts import concurrent_speaking as concurrent_speaking
from test_speaking_transcript import durable_transcript as durable_transcript
from test_speaking_transcript import fake_decode

from app.models.speaking_transcript import SpeakingNormalizedAudio
from app.services.speaking_audio import normalize_committed_take


async def test_concurrent_normalization_uses_one_referenced_object(durable_transcript):
    factory, _, _, response_ids, storage, settings = durable_transcript

    async def normalize():
        async with factory() as session:
            return await normalize_committed_take(
                session, response_ids[0], settings, storage=storage, executor=fake_decode
            )

    first, second = await asyncio.gather(normalize(), normalize())
    assert first.storage_key == second.storage_key
    async with factory() as session:
        rows = list(await session.scalars(select(SpeakingNormalizedAudio)))
    assert len(rows) == 1 and storage.exists(rows[0].storage_key)
    derived = storage.root / "speaking-derived"
    assert len(list(derived.iterdir())) == 1


async def test_normalized_lost_commit_acknowledgement_preserves_referenced_object(
    durable_transcript, monkeypatch
):
    factory, _, _, response_ids, storage, settings = durable_transcript
    async with factory() as session:
        begin = session.begin
        count = 0

        class LostAcknowledgement:
            async def __aenter__(self):
                nonlocal count
                count += 1
                self.number = count
                self.transaction = begin()
                return await self.transaction.__aenter__()

            async def __aexit__(self, *args):
                result = await self.transaction.__aexit__(*args)
                if self.number == 2 and args[0] is None:
                    raise RuntimeError("injected lost acknowledgement")
                return result

        monkeypatch.setattr(session, "begin", LostAcknowledgement)
        with pytest.raises(RuntimeError, match="lost acknowledgement"):
            await normalize_committed_take(
                session, response_ids[0], settings, storage=storage, executor=fake_decode
            )
    async with factory() as session:
        row = await session.scalar(select(SpeakingNormalizedAudio))
    assert row is not None and storage.exists(row.storage_key)


async def test_fake_s3_audio_runs_through_transcription_worker(durable_transcript):
    from io import BytesIO

    from test_speaking_transcript import FakeASR, create_durable
    from test_storage_contract import FakeS3

    from app.models.speaking import SpeakingAudioChunk
    from app.models.speaking_transcript import SpeakingTranscriptRun
    from app.services.speaking_transcript_worker import SpeakingTranscriptWorker
    from app.storage.s3 import S3CompatibleStorage

    factory, _, _, _, local_storage, settings = durable_transcript
    storage = S3CompatibleStorage(client=FakeS3(), bucket="private")
    async with factory() as session:
        chunks = list(await session.scalars(select(SpeakingAudioChunk)))
        for chunk in chunks:
            with local_storage.open_reader(chunk.storage_key) as reader:
                data = reader.read()
            storage.put_stream(
                chunk.storage_key, BytesIO(data), content_type="audio/webm", max_bytes=len(data)
            )
    run = await create_durable(durable_transcript)
    provider = FakeASR()
    await SpeakingTranscriptWorker(
        factory, settings, provider=provider, storage=storage, executor=fake_decode
    ).execute(run.run_id)
    async with factory() as session:
        row = await session.get(SpeakingTranscriptRun, run.run_id)
        normalized = list(await session.scalars(select(SpeakingNormalizedAudio)))
    assert row.status == "COMPLETED" and len(provider.calls) == 4
    assert len(normalized) == 4 and all(storage.exists(item.storage_key) for item in normalized)
