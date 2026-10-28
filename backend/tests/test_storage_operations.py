"""Bounded offline operator workflows, using the real S3 adapter boundary."""

import hashlib
import importlib.util
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_storage_contract import FakeS3

from app.core.exceptions import AppError
from app.storage.local import LocalAssetStorage
from app.storage.migration import AssetReference, copy_keys, iter_object_keys, reconcile
from app.storage.operations import (
    StorageTarget,
    require_write_confirmation,
    storage_target,
    validate_distinct,
)
from app.storage.recovery import (
    create_portable_backup,
    reconcile_restored_database,
    restore_objects,
    verify_portable_backup,
)
from app.storage.s3 import S3CompatibleStorage

URL = "postgresql+asyncpg://fixture:private-secret@127.0.0.1:5437/ielts_p5_test"
DATA = {
    "images/biểu đồ.png": b"fictional image",
    "audio/listening.mp3": b"fictional listening" * 1000,
    "speaking-private/chunk.webm": b"private recording",
    "speaking-derived/normalized.wav": b"normalized recording",
    "classroom-resources/worksheet.pdf": b"worksheet",
    "benchmark/writing/task1/sample/image.png": b"benchmark image",
}


def storage(kind, root, *, bucket="fixtures"):
    if kind == "local":
        return LocalAssetStorage(root)
    client = FakeS3()
    client.meta = SimpleNamespace(
        endpoint_url="https://account.r2.cloudflarestorage.com"
        if kind == "r2"
        else "https://s3.us-east-1.amazonaws.com"
    )
    return S3CompatibleStorage(client=client, bucket=bucket, prefix="environment/media")


def populate(store):
    for key, data in DATA.items():
        store.put_stream(
            key, BytesIO(data), content_type="application/octet-stream", max_bytes=len(data)
        )
    return [
        AssetReference(key, "fixture", len(data), hashlib.sha256(data).hexdigest())
        for key, data in DATA.items()
    ]


@pytest.mark.parametrize(
    "source_kind,destination_kind",
    [
        ("local", "local"),
        ("local", "s3"),
        ("local", "r2"),
        ("s3", "local"),
        ("r2", "local"),
        ("s3", "r2"),
        ("r2", "s3"),
        ("s3", "s3"),
    ],
)
def test_migration_matrix_dry_run_hashes_resume_source_preserved(
    tmp_path, source_kind, destination_kind
):
    source = storage(source_kind, tmp_path / "source", bucket="source")
    destination = storage(destination_kind, tmp_path / "destination", bucket="destination")
    refs = {item.key: item for item in populate(source)}
    assert all(row.status == "would_copy" for row in copy_keys(source, destination, refs))
    assert not any(destination.exists(key) for key in refs)
    checkpoints = []
    results = copy_keys(
        source,
        destination,
        refs,
        references=refs,
        dry_run=False,
        workers=3,
        progress=checkpoints.append,
    )
    assert len(checkpoints) == len(refs)
    assert all(
        row.status == "copied"
        and row.sha256 == refs[row.key].sha256
        and row.size == refs[row.key].size
        for row in results
    )
    assert all(
        row.status == "identical" for row in copy_keys(source, destination, refs, dry_run=False)
    )
    for store in (source, destination):
        for key, data in DATA.items():
            with store.open_reader(key) as reader:
                assert reader.read() == data


def test_interrupted_copy_checkpoint_is_not_trusted_resume_rehashes(tmp_path):
    source, destination = storage("local", tmp_path / "s"), storage("s3", tmp_path / "d")
    refs = populate(source)
    progress = []

    def interrupt(rows):
        progress.append(rows)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        copy_keys(source, destination, [r.key for r in refs], dry_run=False, progress=interrupt)
    assert len(progress[0]) == 1
    first = progress[0][0]["key"]
    destination.client.objects[destination.bucket, destination._key(first)] = (
        b"corrupt",
        "text/plain",
    )
    rows = copy_keys(source, destination, [r.key for r in refs], dry_run=False)
    assert next(row for row in rows if row.key == first).status == "conflict"
    assert all(source.exists(row.key) for row in rows)


def test_source_metadata_corruption_missing_invalid_and_bounded_reads(tmp_path):
    source = storage("s3", tmp_path)
    dest = storage("local", tmp_path / "d")
    refs = populate(source)
    wrong = replace(refs[0], sha256="0" * 64)
    assert (
        copy_keys(source, dest, [wrong.key], references={wrong.key: wrong}, dry_run=False)[0].status
        == "source_integrity_failed"
    )
    rows = copy_keys(source, dest, ["audio/missing.mp3", "../escape"], dry_run=False)
    assert {row.status for row in rows} == {"error", "missing_source"}
    original = source.client.get_object

    class Bounded(BytesIO):
        def read(self, count=-1):
            assert 0 <= count <= 1024 * 1024
            return super().read(count)

    def get(**kwargs):
        return {"Body": Bounded(original(**kwargs)["Body"].read())}

    source.client.get_object = get
    assert copy_keys(source, dest, [refs[1].key], dry_run=False)[0].status == "copied"


@pytest.fixture
def mocked_inventory(monkeypatch):
    from app.storage import recovery

    calls = []
    refs = []

    @asynccontextmanager
    async def inventory(url, *, snapshot=False):
        assert url == URL
        calls.append(("open", snapshot))
        yield (
            refs,
            ["speaking-private/pending-cleanup.webm"],
            "snapshot-token" if snapshot else None,
        )
        calls.append(("close", snapshot))

    monkeypatch.setattr(recovery, "database_inventory", inventory)
    return refs, calls


async def bundle(tmp_path, monkeypatch, mocked_inventory, kind="s3"):
    refs, calls = mocked_inventory
    source = storage(kind, tmp_path / "source")
    refs[:] = populate(source)
    target = StorageTarget(source, kind, "development", "source-fixture")

    def dump(tool, url, path, *, snapshot):
        assert tool == "pg_dump" and snapshot == "snapshot-token"
        assert calls[-1] == ("open", True)
        path.write_bytes(b"fictional pg custom dump")

    result = await create_portable_backup(
        URL, target, tmp_path / "backups", maintenance=True, tool=dump
    )
    return result, source


@pytest.mark.parametrize(
    "source_kind,destination_kind",
    [("local", "local"), ("s3", "local"), ("r2", "s3"), ("s3", "r2")],
)
async def test_portable_backup_restore_actual_cloud_bytes_and_reconcile(
    tmp_path, monkeypatch, mocked_inventory, source_kind, destination_kind
):
    path, source = await bundle(tmp_path, monkeypatch, mocked_inventory, source_kind)
    manifest = verify_portable_backup(path)
    assert manifest["complete"] and len(manifest["objects"]) == len(DATA)
    assert "private-secret" not in (path / "manifest.json").read_text()
    destination = storage(destination_kind, tmp_path / "restored")
    _, preview = restore_objects(path, destination)
    assert all(row["status"] == "would_copy" for row in preview)
    _, rows = restore_objects(path, destination, execute=True)
    assert all(row["status"] == "copied" for row in rows)
    _, resumed = restore_objects(path, destination, execute=True)
    assert all(row["status"] == "identical" for row in resumed)
    result = await reconcile_restored_database(URL, destination, manifest)
    assert result["verified"]
    for key in DATA:
        with destination.open_reader(key) as reader:
            assert reader.read() == DATA[key]
        assert source.exists(key)


async def test_backup_failure_never_complete_missing_asset_and_dump_failure(
    tmp_path, monkeypatch, mocked_inventory
):
    refs, _ = mocked_inventory
    source = storage("s3", tmp_path)
    refs[:] = populate(source)
    source.delete(refs[0].key)
    target = StorageTarget(source, "s3", "development", "fixture")

    def dump(tool, url, path, **kwargs):
        path.write_bytes(b"dump")

    with pytest.raises(AppError, match="asset file does not exist"):
        await create_portable_backup(URL, target, tmp_path / "backups", maintenance=True, tool=dump)
    directories = list((tmp_path / "backups").iterdir())
    assert len(directories) == 1 and directories[0].name.startswith(".backup-incomplete-")
    assert json.loads((directories[0] / "manifest.json").read_text())["complete"] is False
    with pytest.raises(ValueError, match="incomplete"):
        verify_portable_backup(directories[0])

    def failed(*args, **kwargs):
        raise RuntimeError("private-secret")

    with pytest.raises(RuntimeError):
        await create_portable_backup(
            URL, target, tmp_path / "backups", maintenance=True, tool=failed
        )
    assert all(
        "private-secret" not in (d / "manifest.json").read_text()
        for d in (tmp_path / "backups").iterdir()
    )


@pytest.mark.parametrize("tamper", ["archive", "database", "manifest", "missing"])
async def test_tampered_backup_rejected_before_destination_writes(
    tmp_path, monkeypatch, mocked_inventory, tamper
):
    path, _ = await bundle(tmp_path, monkeypatch, mocked_inventory)
    if tamper in {"archive", "database"}:
        (path / ("storage.tar.gz" if tamper == "archive" else "database.dump")).write_bytes(
            b"tampered"
        )
    elif tamper == "missing":
        (path / "storage.tar.gz").unlink()
    else:
        manifest = json.loads((path / "manifest.json").read_text())
        manifest["objects"][0]["key"] = "../outside"
        (path / "manifest.json").write_text(json.dumps(manifest))
    destination = storage("s3", tmp_path)
    with pytest.raises((ValueError, AppError)):
        restore_objects(path, destination, execute=True)
    assert destination.client.objects == {}


async def test_restore_conflict_prevents_all_writes_and_db_reference_mismatch(
    tmp_path, monkeypatch, mocked_inventory
):
    path, _ = await bundle(tmp_path, monkeypatch, mocked_inventory)
    dest = storage("s3", tmp_path)
    key = next(iter(DATA))
    dest.put_stream(key, BytesIO(b"different"), content_type="text/plain", max_bytes=9)
    _, rows = restore_objects(path, dest, execute=True)
    assert any(row["status"] == "conflict" for row in rows)
    assert len(dest.client.objects) == 1
    mocked_inventory[0].append(AssetReference("images/not-in-backup.png", "test"))
    with pytest.raises(ValueError, match="references"):
        await reconcile_restored_database(URL, dest, verify_portable_backup(path))


def test_reconcile_reports_corruption_missing_invalid_and_paginated_orphans(tmp_path):
    store = storage("s3", tmp_path)
    refs = populate(store)
    refs[0] = replace(refs[0], size=1)
    rows = reconcile(
        store,
        refs + [AssetReference("../invalid", "test"), AssetReference("images/missing.png", "test")],
    )
    assert {row.status for row in rows} == {"integrity_failed", "verified", "error"}
    calls = []

    class Paginator:
        def paginate(self, **kwargs):
            calls.append(kwargs)
            yield {"Contents": [{"Key": store._key("audio/a.mp3")}]}
            yield {"Contents": [{"Key": store._key("orphan.tmp")}]}

    store.client.get_paginator = lambda kind: Paginator()
    assert list(iter_object_keys(store)) == ["audio/a.mp3", "orphan.tmp"]
    assert calls[0]["PaginationConfig"] == {"PageSize": 1000}


def test_operator_config_explicit_independent_and_overlap_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_ENVIRONMENT", "development")
    monkeypatch.setenv("SOURCE_STORAGE_ROOT", str(tmp_path))
    target = storage_target("SOURCE", "local")
    with pytest.raises(ValueError, match="confirm-target"):
        require_write_confirmation(target, "wrong", True)
    with pytest.raises(ValueError, match="maintenance"):
        require_write_confirmation(target, target.target_id, False)
    with pytest.raises(ValueError, match="Cross-environment"):
        require_write_confirmation(target, target.target_id, True, source_environment="production")
    source = storage("s3", tmp_path, bucket="same")
    dest = storage("s3", tmp_path, bucket="same")
    dest.client.meta.endpoint_url = "https://s3.amazonaws.com"
    with pytest.raises(ValueError, match="overlap"):
        validate_distinct(source, dest)


@pytest.mark.parametrize("backend", ["s3", "r2"])
def test_independent_cloud_config_reuses_factory_without_ambient_secrets(monkeypatch, backend):
    import boto3

    from app.storage import factory

    factory._cloud_storage.cache_clear()
    calls = []

    def client(service, **kwargs):
        calls.append(kwargs)
        fake = FakeS3()
        fake.meta = SimpleNamespace(
            endpoint_url=kwargs.get("endpoint_url") or "https://s3.amazonaws.com"
        )
        return fake

    monkeypatch.setattr(boto3, "client", client)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ambient-must-not-leak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "ambient-must-not-leak")
    for side in ("SOURCE", "DESTINATION"):
        monkeypatch.setenv(f"{side}_ENVIRONMENT", "development")
        monkeypatch.setenv(f"{side}_S3_BUCKET", f"{side.lower()}-fixture")
        monkeypatch.setenv(f"{side}_S3_REGION", "auto" if backend == "r2" else "us-east-1")
        monkeypatch.setenv(f"{side}_S3_KEY_PREFIX", "development/media")
        monkeypatch.setenv(f"{side}_AWS_ACCESS_KEY_ID", f"{side}-fixture-access")
        monkeypatch.setenv(f"{side}_AWS_SECRET_ACCESS_KEY", f"{side}-fixture-secret")
        if backend == "r2":
            monkeypatch.setenv(
                f"{side}_S3_ENDPOINT_URL", "https://fixture.r2.cloudflarestorage.com"
            )
    try:
        source, dest = storage_target("SOURCE", backend), storage_target("DESTINATION", backend)
        assert calls[0]["aws_access_key_id"] == "SOURCE-fixture-access"
        assert calls[1]["aws_access_key_id"] == "DESTINATION-fixture-access"
        assert source.target_id != dest.target_id
        assert "fixture-secret" not in json.dumps(source.description())
        monkeypatch.setenv("SOURCE_S3_KEY_PREFIX", "../escape")
        with pytest.raises(ValueError):
            storage_target("SOURCE", backend)
    finally:
        factory._cloud_storage.cache_clear()


def test_iam_chain_is_explicit_and_does_not_require_static_credentials(monkeypatch):
    import boto3

    from app.storage import factory

    factory._cloud_storage.cache_clear()
    monkeypatch.setenv("SOURCE_ENVIRONMENT", "development")
    monkeypatch.setenv("SOURCE_S3_BUCKET", "iam-fixture")
    monkeypatch.setenv("SOURCE_S3_REGION", "us-east-1")
    monkeypatch.delenv("SOURCE_USE_AWS_CHAIN", raising=False)
    with pytest.raises(ValueError, match="USE_AWS_CHAIN"):
        storage_target("SOURCE", "s3")
    calls = []

    def client(service, **kwargs):
        calls.append(kwargs)
        return FakeS3()

    monkeypatch.setattr(boto3, "client", client)
    monkeypatch.setenv("SOURCE_USE_AWS_CHAIN", "true")
    try:
        assert storage_target("SOURCE", "s3").backend == "s3"
        assert "aws_access_key_id" not in calls[0]
    finally:
        factory._cloud_storage.cache_clear()


def cli_module():
    path = Path(__file__).resolve().parents[2] / "scripts/migrate_asset_storage.py"
    spec = importlib.util.spec_from_file_location("p5_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_cli_exit_checkpoint_no_credentials(tmp_path, monkeypatch):
    module = cli_module()
    source = storage("local", tmp_path / "s")
    refs = populate(source)
    dest = storage("local", tmp_path / "d")
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(module, "load_inventory", AsyncMock(return_value=(refs, [])))
    targets = {
        "SOURCE": StorageTarget(source, "local", "development", "source"),
        "DESTINATION": StorageTarget(dest, "local", "development", "destination"),
    }
    monkeypatch.setattr(module, "storage_target", lambda prefix, backend: targets[prefix])
    report = tmp_path / "migration.json"
    args = ["--source", "local", "--destination", "local", "--report", str(report)]
    assert module.main(args) == 0
    assert not json.loads(report.read_text())["complete"]
    assert module.main(args + ["--copy"]) == 1
    assert (
        module.main(args + ["--copy", "--confirm-target", "destination", "--maintenance-window"])
        == 0
    )
    assert json.loads(report.read_text())["complete"]
    assert "private-secret" not in report.read_text()
    source.delete(refs[0].key)
    assert module.main(args) == 1


def test_report_cannot_overwrite_source_assets(tmp_path, monkeypatch):
    from app.storage.operations import validate_report_path

    monkeypatch.setenv("SOURCE_STORAGE_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="outside"):
        validate_report_path(tmp_path / "asset.json")


def test_pg_tool_never_puts_credentials_on_commandline(monkeypatch, tmp_path):
    from app.storage import operations

    captured = []

    def run(args, **kwargs):
        captured.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(operations.subprocess, "run", run)
    operations.postgres_tool("pg_dump", URL, tmp_path / "dump", snapshot="snapshot-token")
    operations.postgres_tool("pg_restore", URL, tmp_path / "dump")
    assert all("private-secret" not in str(args) for args, _ in captured)
    assert captured[0][1]["env"]["PGPASSWORD"] == "private-secret"
    assert "--snapshot=snapshot-token" in captured[0][0]
    assert "--clean" not in captured[1][0] and "--create" not in captured[1][0]


@pytest.mark.parametrize(
    "defect", ["missing-member", "extra-member", "bad-checksum", "link", "oversize-pax"]
)
async def test_bundle_member_integrity_not_only_outer_archive_hash(
    tmp_path, monkeypatch, mocked_inventory, defect
):
    import tarfile

    from app.backup_restore import sha256_file

    path, _ = await bundle(tmp_path, monkeypatch, mocked_inventory)
    manifest = json.loads((path / "manifest.json").read_text())
    with tarfile.open(path / "storage.tar.gz", "w:gz") as archive:
        if defect == "oversize-pax":
            member = tarfile.TarInfo("metadata")
            member.type, member.size = tarfile.XHDTYPE, 65537
            archive.addfile(member, BytesIO(b"x" * member.size))
        for index, (key, data) in enumerate(DATA.items()):
            if defect == "missing-member" and index == 0:
                continue
            member = tarfile.TarInfo(key)
            if defect == "link" and index == 0:
                member.type, member.linkname = tarfile.SYMTYPE, "../escape"
                archive.addfile(member)
                continue
            if defect == "bad-checksum" and index == 0:
                data = b"x" * len(data)
            member.size = len(data)
            archive.addfile(member, BytesIO(data))
        if defect == "extra-member":
            member = tarfile.TarInfo("images/unlisted.png")
            member.size = 1
            archive.addfile(member, BytesIO(b"x"))
    manifest["storage_sha256"] = sha256_file(path / "storage.tar.gz")
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_portable_backup(path)


async def test_restore_failed_upload_preserves_source_and_can_resume(
    tmp_path, monkeypatch, mocked_inventory
):
    path, _ = await bundle(tmp_path, monkeypatch, mocked_inventory)
    destination = storage("s3", tmp_path)
    original = destination.client.put_object

    def fail(**kwargs):
        if len(destination.client.objects) == 1:
            raise RuntimeError("private-secret endpoint credentials")
        return original(**kwargs)

    destination.client.put_object = fail
    checkpoints = []
    with pytest.raises(AppError, match="storage is unavailable"):
        restore_objects(
            path, destination, execute=True, progress=lambda rows: checkpoints.append(list(rows))
        )
    assert len(destination.client.objects) == 1
    assert verify_portable_backup(path)["complete"]
    destination.client.put_object = original
    _, rows = restore_objects(path, destination, execute=True)
    assert {row["status"] for row in rows} == {"identical", "copied"}


async def test_backup_cancel_joins_dump_before_releasing_snapshot(
    tmp_path, monkeypatch, mocked_inventory
):
    import asyncio
    import threading

    refs, calls = mocked_inventory
    source = storage("s3", tmp_path)
    refs[:] = populate(source)
    started, release = threading.Event(), threading.Event()

    def dump(tool, url, path, **kwargs):
        started.set()
        assert release.wait(5)
        assert calls[-1] == ("open", True)
        path.write_bytes(b"dump")

    task = asyncio.create_task(
        create_portable_backup(
            URL,
            StorageTarget(source, "s3", "development", "fixture"),
            tmp_path / "backups",
            maintenance=True,
            tool=dump,
        )
    )
    await asyncio.to_thread(started.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    directory = next((tmp_path / "backups").iterdir())
    assert json.loads((directory / "manifest.json").read_text())["complete"] is False


@pytest.mark.parametrize(
    "environment,name",
    [("production", "ielts_recovery"), ("recovery", "ielts"), ("recovery", "production")],
)
async def test_database_restore_unsafe_names_refused_without_connecting(
    monkeypatch, environment, name
):
    from app.storage import operations

    monkeypatch.setenv("RESTORE_ENVIRONMENT", environment)

    def forbidden(*args, **kwargs):
        raise AssertionError("Unsafe database must never be contacted")

    monkeypatch.setattr(operations, "create_async_engine", forbidden)
    with pytest.raises(ValueError, match="Restore requires"):
        await operations.check_restore_database(
            f"postgresql+asyncpg://fixture@127.0.0.1/{name}", source_id="source"
        )


async def test_recovery_cli_requires_confirmations_and_keeps_incomplete_status(
    tmp_path, monkeypatch, mocked_inventory
):
    from app.backup_restore import sha256_file
    from app.storage import recovery_cli

    path, _ = await bundle(tmp_path, monkeypatch, mocked_inventory)
    dest = storage("s3", tmp_path)
    monkeypatch.setattr(
        recovery_cli,
        "storage_target",
        lambda *args: StorageTarget(dest, "s3", "recovery", "recovery-target"),
    )
    monkeypatch.setattr(recovery_cli, "probe_target", lambda *args: None)
    report = tmp_path / "restore.json"
    args = [str(path), "--destination", "s3", "--report", str(report)]
    assert recovery_cli.restore_main(args) == 0
    assert dest.client.objects == {}
    assert recovery_cli.restore_main(args + ["--restore-objects"]) == 1
    assert (
        recovery_cli.restore_main(
            args
            + [
                "--restore-objects",
                "--confirm-target",
                "recovery-target",
                "--confirm-backup",
                sha256_file(path / "manifest.json"),
                "--maintenance-window",
                "--allow-cross-environment",
            ]
        )
        == 0
    )
    report_data = json.loads(report.read_text())
    assert report_data["objects_verified"] is True and report_data["complete"] is False
    assert "private-secret" not in report.read_text()


def test_backup_cli_failure_cannot_claim_success(tmp_path, monkeypatch):
    from app.storage import recovery_cli

    monkeypatch.setattr(
        recovery_cli,
        "storage_target",
        lambda *args: StorageTarget(storage("s3", tmp_path), "s3", "development", "fixture"),
    )
    monkeypatch.setattr(recovery_cli, "probe_target", lambda *args: None)
    monkeypatch.setattr(
        recovery_cli,
        "create_portable_backup",
        AsyncMock(side_effect=RuntimeError("private-secret")),
    )
    report = tmp_path / "backup-report.json"
    assert (
        recovery_cli.backup_main(
            [
                "--source",
                "s3",
                "--backup-root",
                str(tmp_path / "backups"),
                "--report",
                str(report),
                "--maintenance-window",
            ]
        )
        == 1
    )
    assert json.loads(report.read_text())["complete"] is False
    assert "private-secret" not in report.read_text()
