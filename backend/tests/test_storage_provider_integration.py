import tempfile
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import select
from test_speaking_attempts import concurrent_speaking as concurrent_speaking
from test_speaking_transcript import FakeASR, create_durable, fake_decode
from test_speaking_transcript import durable_transcript as durable_transcript
from test_storage_configuration import clean_storage_cache as clean_storage_cache
from test_storage_configuration import cloud_settings
from test_storage_contract import FakeS3, S3Failure
from test_transfer import _portable_fixture

from app.core.exceptions import AppError
from app.models import Asset
from app.models import TestVersion as VersionRecord
from app.models.speaking import SpeakingAudioChunk, SpeakingMediaCleanup
from app.models.speaking_transcript import SpeakingNormalizedAudio, SpeakingTranscriptRun
from app.services.speaking_media import drain_media_cleanup
from app.services.speaking_transcript_worker import SpeakingTranscriptWorker
from app.services.transfer import TransferService
from app.storage.factory import get_asset_storage


@pytest.mark.parametrize("backend", ["s3", "r2"])
async def test_configured_provider_is_used_by_real_transfer_service(
    isolated_db_session, tmp_path, monkeypatch, backend
):
    import boto3

    session = isolated_db_session
    test, _, assets = await _portable_fixture(session, tmp_path / "seed")
    original_id = test.id
    client = FakeS3()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    source_settings = cloud_settings(
        backend, s3_bucket="source-fixture", storage_root=tmp_path / "unused"
    )
    source = get_asset_storage(source_settings)
    for asset in assets.values():
        data = (tmp_path / "seed" / asset.relative_path).read_bytes()
        source.put_stream(
            asset.relative_path, BytesIO(data), content_type=asset.mime_type, max_bytes=len(data)
        )
    archive = tmp_path / "provider.zip"
    await TransferService(session, source_settings).export([original_id], archive)
    await session.rollback()
    destination_settings = cloud_settings(
        backend, s3_bucket="destination-fixture", storage_root=tmp_path / "unused"
    )
    service = TransferService(session, destination_settings)
    with tempfile.TemporaryDirectory(dir=tmp_path) as directory:
        package = service.validate_archive(archive, Path(directory))
        result = await service.import_package(package)
    version = await session.scalar(
        select(VersionRecord).where(VersionRecord.test_id == result.imported_tests[0].test_id)
    )
    imported = list(await session.scalars(select(Asset).where(Asset.test_version_id == version.id)))
    assert len(imported) == 3
    for asset in imported:
        with get_asset_storage(destination_settings).open_reader(asset.relative_path) as reader:
            assert len(reader.read()) == asset.file_size
    assert not destination_settings.storage_root.exists()


@pytest.mark.parametrize("backend", ["s3", "r2"])
async def test_configured_provider_normalizes_transcribes_and_keeps_referenced_media(
    durable_transcript, monkeypatch, backend
):
    import boto3

    from app.services import speaking_media

    factory, _, _, _, local_storage, _ = durable_transcript
    settings = cloud_settings(backend)
    client = FakeS3()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    storage = get_asset_storage(settings)
    async with factory() as session:
        for chunk in await session.scalars(select(SpeakingAudioChunk)):
            with local_storage.open_reader(chunk.storage_key) as reader:
                data = reader.read()
            storage.put_stream(
                chunk.storage_key, BytesIO(data), content_type="audio/webm", max_bytes=len(data)
            )
    run = await create_durable(durable_transcript)
    provider = FakeASR()
    # identity uses the same non-storage settings; storage changes are infrastructure only.
    await SpeakingTranscriptWorker(
        factory, settings, provider=provider, executor=fake_decode
    ).execute(run.run_id)
    async with factory() as session:
        row = await session.get(SpeakingTranscriptRun, run.run_id)
        normalized = list(await session.scalars(select(SpeakingNormalizedAudio)))
        keys = [item.storage_key for item in normalized]
    assert row.status == "COMPLETED" and len(provider.calls) == 4 and len(keys) == 4
    monkeypatch.setattr(speaking_media, "get_settings", lambda: settings)
    async with factory() as session, session.begin():
        session.add(SpeakingMediaCleanup(storage_key=keys[0]))
    async with factory() as session:
        await drain_media_cleanup(session)
    assert storage.exists(keys[0])


async def test_configured_provider_cleanup_outage_retains_job_and_object(
    isolated_db_session, monkeypatch
):
    import boto3

    from app.services import speaking_media

    class FailedDeletion(FakeS3):
        def delete_object(self, **kwargs):
            raise S3Failure("ServiceUnavailable")

    session = isolated_db_session
    client = FailedDeletion()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    settings = cloud_settings()
    monkeypatch.setattr(speaking_media, "get_settings", lambda: settings)
    storage = get_asset_storage(settings)
    key = "speaking-derived/unreferenced.wav"
    storage.put_stream(key, BytesIO(b"fictional"), content_type="audio/wav", max_bytes=9)
    async with session.begin():
        session.add(SpeakingMediaCleanup(storage_key=key))
    with pytest.raises(AppError):
        await drain_media_cleanup(session)
    assert storage.exists(key)
    assert (
        await session.scalar(
            select(SpeakingMediaCleanup).where(SpeakingMediaCleanup.storage_key == key)
        )
        is not None
    )
