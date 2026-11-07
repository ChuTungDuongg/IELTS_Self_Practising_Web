"""Storage neutrality, interrupted upload cleanup and schema evidence."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, File, UploadFile
from sqlalchemy import select
from test_admin_speaking_benchmark import BYTES, fake_probe
from test_storage_configuration import cloud_settings
from test_storage_contract import FakeS3

from app.core.benchmark_upload_limit import BenchmarkUploadLimit
from app.core.config import Settings
from app.evaluation.speaking.diarization_backend import LocalDiarizer, model_identity
from app.models.speaking import SpeakingMediaCleanup
from app.schemas.speaking_benchmark import SampleMetadata
from app.services import speaking_benchmark as module
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_media import drain_media_cleanup
from app.storage.s3 import S3CompatibleStorage


@pytest.mark.parametrize("backend", ["s3", "r2"])
async def test_private_upload_materialization_and_retryable_deletion_use_storage_port(
    isolated_db_session, tmp_path, monkeypatch, backend
):
    client = FakeS3()
    settings = cloud_settings(backend)
    storage = S3CompatibleStorage(client=client, bucket="private-fixture")
    source = tmp_path / "source"
    source.write_bytes(BYTES)
    monkeypatch.setattr(module, "probe_audio", fake_probe)
    monkeypatch.setattr(LocalDiarizer, "audio_settings", lambda self, settings: settings)
    service = SpeakingBenchmarkService(
        isolated_db_session,
        isolated_db_session.info["current_user_id"],
        settings=settings,
        storage=storage,
    )
    sample = await service.upload(
        source,
        SampleMetadata(code="PRIVATE", source_note="Fictional permission", rights_confirmed=True),
    )
    key, mime = await service.audio(sample.id)
    assert mime == "audio/wav" and key.startswith("benchmark/speaking/")
    with storage.materialize(key, max_bytes=1000) as materialized:
        assert materialized.read_bytes() == BYTES
    await service.delete(sample.id, sample.revision)
    async with isolated_db_session.begin():
        pending = await isolated_db_session.scalar(
            select(SpeakingMediaCleanup).where(SpeakingMediaCleanup.storage_key == key)
        )
        pending.created_at = datetime.now(UTC) - timedelta(hours=2)
    real_delete = storage.delete

    def failed_delete(_):
        raise OSError("storage offline")

    monkeypatch.setattr(storage, "delete", failed_delete)
    with pytest.raises(OSError):
        await drain_media_cleanup(isolated_db_session, storage=storage)
    assert storage.exists(key)
    monkeypatch.setattr(storage, "delete", real_delete)
    await drain_media_cleanup(isolated_db_session, storage=storage)
    assert not storage.exists(key)


async def test_failed_object_write_retains_durable_cleanup_reservation(
    isolated_db_session, tmp_path, monkeypatch
):
    from app.storage.local import LocalAssetStorage

    storage = LocalAssetStorage(tmp_path)
    source = tmp_path / "source"
    source.write_bytes(BYTES)
    monkeypatch.setattr(module, "probe_audio", fake_probe)
    monkeypatch.setattr(LocalDiarizer, "audio_settings", lambda self, settings: settings)

    def fail(*args, **kwargs):
        raise OSError("Interrupted object write")

    monkeypatch.setattr(storage, "put_stream", fail)
    service = SpeakingBenchmarkService(
        isolated_db_session,
        isolated_db_session.info["current_user_id"],
        settings=Settings(_env_file=None),
        storage=storage,
    )
    with pytest.raises(OSError):
        await service.upload(
            source, SampleMetadata(code="FAIL", source_note="Fixture", rights_confirmed=True)
        )
    async with isolated_db_session.begin():
        pending = await isolated_db_session.scalar(select(SpeakingMediaCleanup))
        assert pending is not None and pending.storage_key.startswith("benchmark/speaking/")


async def test_chunked_multipart_limit_closes_partial_spooled_files(monkeypatch):
    from starlette import formparsers

    opened = []
    original = formparsers.SpooledTemporaryFile

    def spool(*args, **kwargs):
        result = original(*args, **kwargs)
        opened.append(result)
        return result

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", spool)
    app = FastAPI()

    @app.post("/api/v1/admin/speaking-benchmark/samples")
    async def endpoint(file: UploadFile = File()):
        pytest.fail("Oversized body must not reach upload handler")

    app.add_middleware(BenchmarkUploadLimit, max_bytes=100, prefix="/api/v1")

    async def chunks():
        yield b'--fixture\r\nContent-Disposition: form-data; name="file"; filename="x.wav"\r\nContent-Type: audio/wav\r\n\r\n'
        for _ in range(8):
            yield b"x" * 10000
        yield b"\r\n--fixture--\r\n"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/admin/speaking-benchmark/samples",
            content=chunks(),
            headers={"Content-Type": "multipart/form-data; boundary=fixture"},
        )
    assert (
        response.status_code == 413 and response.json()["code"] == "SPEAKING_BENCHMARK_UPLOAD_SIZE"
    )
    assert opened and all(file.closed for file in opened)


def test_packaged_identity_matches_existing_runtime_pin():
    root = Path(__file__).parents[2]
    assert model_identity() == json.loads(
        (root / "tools/speaking_diarization/model.json").read_text(encoding="utf-8")
    )
    image = (root / "deploy/Dockerfile.speaking-benchmark-worker").read_text()
    assert "benchmark-cpu" in image and "SPEAKING_BENCHMARK_EXECUTION=remote" in image
    assert "nvidia" not in image.lower() and "cuda" not in image.lower()
