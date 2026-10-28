"""Real TransferService round trips against a separately provisioned test database."""

import hashlib
import json
import tempfile
import zipfile

import pytest
from sqlalchemy import select
from test_storage_contract import FakeS3
from test_test_covers import PNG
from test_transfer import _portable_fixture

from app.core.config import Settings
from app.models import Asset
from app.models import TestCover as CoverRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import VersionStatus
from app.services.transfer import TransferService
from app.storage.local import LocalAssetStorage
from app.storage.s3 import S3CompatibleStorage


@pytest.mark.parametrize("source_kind", ["local", "s3"])
@pytest.mark.parametrize("destination_kind", ["local", "s3"])
@pytest.mark.parametrize("with_cover", [False, True])
async def test_real_transfer_cross_storage_roundtrip(
    isolated_db_session, tmp_path, source_kind, destination_kind, with_cover
):
    session = isolated_db_session
    settings = Settings(storage_root=tmp_path / "source")
    test, version, source_assets = await _portable_fixture(session, settings.resolved_storage_root)
    test_id, version_id = test.id, version.id
    original_ids = {kind: asset.id for kind, asset in source_assets.items()}
    original_types = {kind: asset.asset_type for kind, asset in source_assets.items()}
    original_mimes = {kind: asset.mime_type for kind, asset in source_assets.items()}
    expected = {
        kind: (settings.resolved_storage_root / asset.relative_path).read_bytes()
        for kind, asset in source_assets.items()
    }
    if with_cover:
        cover_key = "images/fictional-cover.png"
        cover_path = settings.resolved_storage_root / cover_key
        cover_path.write_bytes(PNG)
        async with session.begin():
            cover = CoverRecord(
                test_id=test_id,
                relative_path=cover_key,
                mime_type="image/png",
                original_name="cover.png",
                file_size=len(PNG),
            )
            session.add(cover)
            await session.flush()
            original_cover_id = cover.id
    else:
        original_cover_id = None

    source = LocalAssetStorage(settings.resolved_storage_root)
    if source_kind == "s3":
        source = S3CompatibleStorage(client=FakeS3(), bucket="source")
        paths = [
            (asset.relative_path, expected[kind], asset.mime_type)
            for kind, asset in source_assets.items()
        ]
        if with_cover:
            paths.append((cover_key, PNG, "image/png"))
        from io import BytesIO

        for key, data, mime in paths:
            source.put_stream(key, BytesIO(data), content_type=mime, max_bytes=len(data))
    from io import BytesIO

    source.put_stream(
        "speaking-private/unrelated.webm",
        BytesIO(b"private-secret"),
        content_type="audio/webm",
        max_bytes=14,
    )
    destination = (
        LocalAssetStorage(tmp_path / "destination")
        if destination_kind == "local"
        else S3CompatibleStorage(client=FakeS3(), bucket="destination")
    )
    archive_path = tmp_path / "transfer.zip"
    await TransferService(session, settings, storage=source).export([test_id], archive_path)
    await session.rollback()
    with zipfile.ZipFile(archive_path) as archive:
        assert all(b"private-secret" not in archive.read(name) for name in archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == (2 if with_cover else 1)
        for item in manifest["assets"] + manifest.get("covers", []):
            data = archive.read(item["path"])
            assert len(data) == item["size"]
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
            assert "speaking-private" not in item["path"]
    with tempfile.TemporaryDirectory(dir=tmp_path) as directory:
        from pathlib import Path

        stage = Path(directory)
        service = TransferService(session, settings, storage=destination)
        package = service.validate_archive(archive_path, stage)
        imported = await service.import_package(package)
    assert not stage.exists()  # noqa: ASYNC240
    new_test_id = imported.imported_tests[0].test_id
    assert new_test_id != test_id
    new_version = await session.scalar(
        select(VersionRecord).where(VersionRecord.test_id == new_test_id)
    )
    assert new_version.id != version_id and new_version.status == VersionStatus.PUBLISHED
    new_assets = list(
        await session.scalars(select(Asset).where(Asset.test_version_id == new_version.id))
    )
    assert len(new_assets) == 3
    for asset in new_assets:
        kind = next(
            kind for kind, asset_type in original_types.items() if asset_type == asset.asset_type
        )
        assert asset.id != original_ids[kind]
        assert asset.mime_type == original_mimes[kind]
        assert asset.file_size == len(expected[kind])
        with destination.open_reader(asset.relative_path) as reader:
            assert reader.read() == expected[kind]
    original_version = await session.get(VersionRecord, version_id)
    assert original_version.status == VersionStatus.PUBLISHED
    if with_cover:
        cover = await session.scalar(select(CoverRecord).where(CoverRecord.test_id == new_test_id))
        assert cover.id != original_cover_id
        with destination.open_reader(cover.relative_path) as reader:
            assert reader.read() == PNG


async def test_transfer_storage_failure_rolls_back_and_compensates(isolated_db_session, tmp_path):
    from sqlalchemy import func

    from app.models import Test as DomainTest

    class FailingS3(FakeS3):
        def put_object(self, **kwargs):
            if self.objects:
                raise RuntimeError("simulated storage outage")
            return super().put_object(**kwargs)

    session = isolated_db_session
    settings = Settings(storage_root=tmp_path / "source")
    test, _, _ = await _portable_fixture(session, settings.resolved_storage_root)
    source_id = test.id
    path = tmp_path / "bundle.zip"
    await TransferService(session, settings).export([source_id], path)
    await session.rollback()
    client = FailingS3()
    destination = S3CompatibleStorage(client=client, bucket="destination")
    service = TransferService(session, settings, storage=destination)
    with tempfile.TemporaryDirectory(dir=tmp_path) as folder:
        from pathlib import Path

        package = service.validate_archive(path, Path(folder))
        with pytest.raises(RuntimeError, match="simulated storage outage"):
            await service.import_package(package)
    assert client.objects == {}
    assert await session.scalar(select(func.count()).select_from(DomainTest)) == 1


async def test_fake_s3_database_failure_compensates_all_objects(
    isolated_db_session, tmp_path, monkeypatch
):
    from pathlib import Path

    from sqlalchemy import func

    from app.models import Test as DomainTest

    session = isolated_db_session
    settings = Settings(storage_root=tmp_path / "source")
    test, _, _ = await _portable_fixture(session, settings.resolved_storage_root)
    archive = tmp_path / "flush-failure.zip"
    await TransferService(session, settings).export([test.id], archive)
    await session.rollback()
    client = FakeS3()
    service = TransferService(
        session, settings, storage=S3CompatibleStorage(client=client, bucket="destination")
    )
    with tempfile.TemporaryDirectory(dir=tmp_path) as folder:
        package = service.validate_archive(archive, Path(folder))

        async def failed_flush(*args, **kwargs):
            raise RuntimeError("simulated flush failure")

        with monkeypatch.context() as patch:
            patch.setattr(session, "flush", failed_flush)
            with pytest.raises(RuntimeError, match="simulated flush failure"):
                await service.import_package(package)
    assert client.objects == {}
    assert await session.scalar(select(func.count()).select_from(DomainTest)) == 1


async def test_fake_s3_repeat_import_remaps_objects_and_preserves_owner(
    isolated_db_session, tmp_path
):
    from pathlib import Path

    from app.models import Test as DomainTest

    session = isolated_db_session
    settings = Settings(storage_root=tmp_path / "source")
    original, _, _ = await _portable_fixture(session, settings.resolved_storage_root)
    archive = tmp_path / "repeat.zip"
    await TransferService(session, settings).export([original.id], archive)
    await session.rollback()
    client = FakeS3()
    service = TransferService(
        session, settings, storage=S3CompatibleStorage(client=client, bucket="destination")
    )
    with tempfile.TemporaryDirectory(dir=tmp_path) as folder:
        package = service.validate_archive(archive, Path(folder))
        first = await service.import_package(package)
        second = await service.import_package(package)
    first_id, second_id = first.imported_tests[0].test_id, second.imported_tests[0].test_id
    assert first_id != second_id
    rows = list(
        await session.scalars(select(DomainTest).where(DomainTest.id.in_([first_id, second_id])))
    )
    assert len(rows) == 2 and all(
        row.owner_user_id == session.info["current_user_id"] for row in rows
    )
    assert len(client.objects) == 6


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
async def test_export_from_fake_s3_rejects_missing_or_corrupt_media(
    isolated_db_session, tmp_path, failure
):
    from io import BytesIO
    from pathlib import Path

    from app.core.exceptions import AppError

    session = isolated_db_session
    settings = Settings(storage_root=tmp_path / "source")
    original, _, assets = await _portable_fixture(session, settings.resolved_storage_root)
    source_id = original.id
    client = FakeS3()
    storage = S3CompatibleStorage(client=client, bucket="source")
    for asset in assets.values():
        data = (settings.resolved_storage_root / asset.relative_path).read_bytes()
        storage.put_stream(
            asset.relative_path, BytesIO(data), content_type=asset.mime_type, max_bytes=len(data)
        )
    key = next(iter(client.objects))
    if failure == "missing":
        del client.objects[key]
    else:
        _, mime = client.objects[key]
        client.objects[key] = (b"corrupt-content", mime)
    archive = tmp_path / "damaged.zip"
    service = TransferService(session, settings, storage=storage)
    if failure == "missing":
        with pytest.raises(AppError):
            await service.export([source_id], archive)
    else:
        await service.export([source_id], archive)
        with tempfile.TemporaryDirectory(dir=tmp_path) as folder:
            with pytest.raises(AppError):
                service.validate_archive(archive, Path(folder))
