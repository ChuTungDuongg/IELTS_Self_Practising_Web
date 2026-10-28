from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from test_storage_contract import FakeS3

from app.core.config import Settings
from app.storage import factory
from app.storage.local import LocalAssetStorage
from app.storage.s3 import S3CompatibleStorage


def cloud_settings(backend="s3", **overrides):
    values = dict(
        storage_backend=backend,
        s3_bucket="private-fixture",
        s3_region="us-east-1" if backend == "s3" else "auto",
        s3_endpoint_url="" if backend == "s3" else "https://fixture.r2.cloudflarestorage.com",
        aws_access_key_id="fixture-access",
        aws_secret_access_key="fixture-secret",
    )
    return Settings(_env_file=None, **(values | overrides))


@pytest.fixture(autouse=True)
def clean_storage_cache(monkeypatch):
    factory._cloud_storage.cache_clear()
    yield
    factory._cloud_storage.cache_clear()


@pytest.mark.parametrize("backend", ["s3", "r2"])
def test_cloud_factory_selects_adapter_and_reuses_client(backend, monkeypatch, tmp_path):
    import boto3

    calls = []

    def client(service, **kwargs):
        calls.append((service, kwargs))
        return FakeS3()

    monkeypatch.setattr(boto3, "client", client)
    settings = cloud_settings(backend, storage_root=tmp_path / "unused")
    first = factory.get_asset_storage(settings)
    assert isinstance(first, S3CompatibleStorage)
    assert first is factory.get_asset_storage(settings)
    assert len(calls) == 1 and not settings.storage_root.exists()
    config = calls[0][1]["config"]
    assert config.connect_timeout == 5 and config.read_timeout == 60
    assert config.retries == {"mode": "standard", "total_max_attempts": 4}
    assert config.request_checksum_calculation == "when_required"
    assert config.signature_version == "s3v4"


def test_local_factory_never_constructs_cloud_client(monkeypatch, tmp_path):
    import boto3

    def forbidden(*args, **kwargs):
        pytest.fail("Local mode must not construct a cloud client")

    monkeypatch.setattr(boto3, "client", forbidden)
    settings = Settings(_env_file=None, storage_root=tmp_path)
    assert isinstance(factory.initialize_asset_storage(settings), LocalAssetStorage)
    assert (tmp_path / "audio").is_dir() and (tmp_path / "images").is_dir()


def test_aws_iam_chain_is_not_replaced_by_empty_credentials(monkeypatch):
    import boto3

    captured = {}

    def client(service, **kwargs):
        captured.update(kwargs)
        return FakeS3()

    monkeypatch.setattr(boto3, "client", client)
    factory.get_asset_storage(cloud_settings(aws_access_key_id=None, aws_secret_access_key=None))
    assert not any(name.startswith("aws_") for name in captured)


@pytest.mark.parametrize(
    "overrides",
    [
        {"s3_bucket": ""},
        {"s3_bucket": "bucket/path"},
        {"s3_region": ""},
        {"s3_region": "auto"},
        {"s3_endpoint_url": "http://example.invalid"},
        {"s3_endpoint_url": "https://user:password@example.invalid"},
        {"s3_endpoint_url": "https://example.invalid/path"},
        {"s3_endpoint_url": "https://example.invalid?query=x"},
        {"s3_key_prefix": "../production"},
        {"s3_key_prefix": "dev\\media"},
        {"aws_access_key_id": None},
        {"aws_access_key_id": None, "aws_secret_access_key": None, "aws_session_token": "token"},
    ],
)
def test_incomplete_or_unsafe_cloud_configuration_fails_before_sdk(overrides):
    with pytest.raises(ValidationError):
        cloud_settings(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"s3_endpoint_url": ""},
        {"s3_endpoint_url": "https://example.invalid"},
        {"s3_region": "us-east-1"},
        {"aws_access_key_id": None, "aws_secret_access_key": None},
    ],
)
def test_r2_requires_endpoint_auto_region_and_scoped_credentials(overrides):
    with pytest.raises(ValidationError):
        cloud_settings("r2", **overrides)


def test_secrets_are_redacted_and_client_initialization_fails_closed(monkeypatch):
    import boto3

    settings = cloud_settings()
    assert "fixture-secret" not in repr(settings)
    assert "fixture-secret" not in settings.model_dump_json()

    def failed_client(*args, **kwargs):
        raise RuntimeError("private credential fixture-secret")

    monkeypatch.setattr(boto3, "client", failed_client)
    with pytest.raises(ValueError) as failure:
        factory.get_asset_storage(settings)
    assert "fixture-secret" not in str(failure.value)
    with pytest.raises(ValidationError) as invalid:
        cloud_settings(s3_bucket="")
    assert "fixture-secret" not in str(invalid.value)


@pytest.mark.parametrize("backend", ["s3", "r2"])
def test_configured_provider_delivers_private_ranges(backend, monkeypatch):
    from io import BytesIO

    import boto3
    from fastapi.testclient import TestClient
    from test_storage_delivery import app_for

    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeS3())
    storage = factory.get_asset_storage(cloud_settings(backend))
    storage.put_stream("asset", BytesIO(b"abcdef"), content_type="audio/mpeg", max_bytes=6)
    with TestClient(app_for(storage)) as client:
        response = client.get("/asset", headers={"Range": "bytes=2-4"})
    assert response.status_code == 206 and response.content == b"cde"
    assert response.headers["content-range"] == "bytes 2-4/6"
    assert response.headers["content-length"] == "3"
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("backend", ["s3", "r2"])
async def test_cloud_lifespan_does_not_create_local_asset_directory(backend, monkeypatch, tmp_path):
    import boto3

    from app import main
    from app.services import speaking_media

    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeS3())
    settings = cloud_settings(backend, storage_root=tmp_path / "must-not-be-created")
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(speaking_media, "cleanup_private_media", AsyncMock())
    monkeypatch.setattr(main.SpeakingTranscriptWorker, "recover", AsyncMock())
    monkeypatch.setattr(main.SpeakingAIWorker, "recover", AsyncMock())
    monkeypatch.setattr(main, "stop_speaking_ai_workers", AsyncMock())
    monkeypatch.setattr(main, "stop_speaking_transcript_workers", AsyncMock())
    monkeypatch.setattr(main, "stop_writing_ai_workers", AsyncMock())
    async with main.lifespan(main.app):
        assert not settings.storage_root.exists()
    assert not settings.storage_root.exists()


@pytest.mark.parametrize("backend", ["s3", "r2"])
@pytest.mark.parametrize("command", ["backup", "restore"])
def test_cloud_backup_and_restore_refuse_before_any_operation(
    backend, command, monkeypatch, tmp_path, capsys
):
    from app import backup_restore

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fictional@localhost/unused_test")
    monkeypatch.setattr(backup_restore, "Settings", lambda **kwargs: cloud_settings(backend))

    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported cloud backup/restore must not start database or file operations")

    monkeypatch.setattr(backup_restore, "create_backup", forbidden)
    monkeypatch.setattr(backup_restore, "restore_backup", forbidden)
    arguments = (
        ["backup", "--backup-root", str(tmp_path)]
        if command == "backup"
        else ["restore", str(tmp_path), "--confirm-destructive"]
    )
    monkeypatch.setattr("sys.argv", arguments)
    with pytest.raises(SystemExit) as result:
        (backup_restore.backup_main if command == "backup" else backup_restore.restore_main)()
    assert result.value.code != 0
    assert "STORAGE_BACKEND=local only" in capsys.readouterr().err
