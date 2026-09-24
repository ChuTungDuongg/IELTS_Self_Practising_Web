import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.backup_restore import (
    APPLICATION,
    BackupError,
    archive_storage,
    create_backup,
    extract_validated_archive,
    normalize_database_url,
    read_manifest,
    restore_backup,
    sha256_file,
    validated_archive_members,
    verify_backup_files,
)


def fixture_backup(root: Path) -> Path:
    root.mkdir()
    (root / "database.dump").write_bytes(b"fictional database dump")
    with tarfile.open(root / "storage.tar.gz", "w:gz") as archive:
        content = b"fictional audio"
        entry = tarfile.TarInfo("audio/fictional.mp3")
        entry.size = len(content)
        archive.addfile(entry, io.BytesIO(content))
    manifest = {
        "format_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "database_file": "database.dump",
        "storage_file": "storage.tar.gz",
        "database_sha256": sha256_file(root / "database.dump"),
        "storage_sha256": sha256_file(root / "storage.tar.gz"),
        "application": APPLICATION,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_asyncpg_url_normalizes_without_changing_credentials_or_database() -> None:
    url = "postgresql+asyncpg://fictional:p%40ss@localhost:5433/example?sslmode=require"
    assert normalize_database_url(url) == (
        "postgresql://fictional:p%40ss@localhost:5433/example?sslmode=require"
    )
    assert normalize_database_url("postgresql://fictional@localhost/example") == (
        "postgresql://fictional@localhost/example"
    )
    with pytest.raises(BackupError, match="PostgreSQL URL"):
        normalize_database_url("sqlite:///example.db")


def test_manifest_and_both_checksums_are_verified(tmp_path: Path) -> None:
    backup = fixture_backup(tmp_path / "backup")
    manifest = read_manifest(backup)
    verify_backup_files(backup, manifest)
    (backup / "database.dump").write_bytes(b"changed")
    with pytest.raises(BackupError, match="Checksum mismatch: database.dump"):
        verify_backup_files(backup, manifest)
    (backup / "database.dump").write_bytes(b"fictional database dump")
    (backup / "storage.tar.gz").write_bytes(b"changed")
    with pytest.raises(BackupError, match="Checksum mismatch: storage.tar.gz"):
        verify_backup_files(backup, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("format_version", 99),
        ("format_version", True),
        ("database_file", "../outside.dump"),
        ("database_sha256", "wrong"),
        ("created_at", "not-a-date"),
        ("application", "unknown"),
    ],
)
def test_malformed_manifest_is_rejected(tmp_path: Path, field: str, value: object) -> None:
    backup = fixture_backup(tmp_path / "backup")
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    manifest[field] = value
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BackupError, match="manifest"):
        read_manifest(backup)


def test_invalid_manifest_json_is_rejected(tmp_path: Path) -> None:
    backup = fixture_backup(tmp_path / "backup")
    (backup / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(BackupError, match="manifest"):
        read_manifest(backup)


@pytest.mark.parametrize(
    "name",
    ["../outside", "audio/../../outside", "/absolute/path", "C:\\absolute\\path", "audio\\bad"],
)
def test_unsafe_tar_paths_are_rejected(tmp_path: Path, name: str) -> None:
    path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo(name)
        entry.size = 1
        archive.addfile(entry, io.BytesIO(b"x"))
    with tarfile.open(path, "r:gz") as archive:
        with pytest.raises(BackupError, match="Unsafe archive entry"):
            validated_archive_members(archive)


def test_tar_link_and_duplicate_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "link.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        link = tarfile.TarInfo("audio/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        archive.addfile(link)
    with tarfile.open(path, "r:gz") as archive:
        with pytest.raises(BackupError, match="Unsafe archive entry"):
            validated_archive_members(archive)

    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(tarfile.TarInfo("audio"))
        archive.addfile(tarfile.TarInfo("AUDIO"))
    with tarfile.open(path, "r:gz") as archive:
        with pytest.raises(BackupError, match="Duplicate archive entry"):
            validated_archive_members(archive)


def test_storage_archive_round_trip_keeps_relative_content(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    (storage / "audio").mkdir(parents=True)
    (storage / "audio" / "fictional.mp3").write_bytes(b"fictional audio")
    archive_path = tmp_path / "storage.tar.gz"
    archive_storage(storage, archive_path)
    stage = tmp_path / "stage"
    stage.mkdir()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = validated_archive_members(archive)
        assert {member.name for member in members} == {"audio", "audio/fictional.mp3"}
        extract_validated_archive(archive, members, stage)
    assert (stage / "audio" / "fictional.mp3").read_bytes() == b"fictional audio"


def test_storage_symlink_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = storage / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        link.write_text("link placeholder", encoding="utf-8")
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == link or original(path))
    with pytest.raises(BackupError, match="symlink"):
        archive_storage(storage, tmp_path / "storage.tar.gz")


def test_restore_requires_explicit_confirmation_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = fixture_backup(tmp_path / "backup")
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "existing.txt").write_text("keep", encoding="utf-8")
    called = []
    monkeypatch.setattr("app.backup_restore.run_postgres_tool", lambda *args: called.append(args))
    with pytest.raises(BackupError, match="--confirm-destructive"):
        restore_backup(backup, "postgresql://fictional@localhost/example", storage, False)
    assert called == []
    assert (storage / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_corrupt_backup_never_starts_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = fixture_backup(tmp_path / "backup")
    storage = tmp_path / "storage"
    storage.mkdir()
    (backup / "database.dump").write_bytes(b"corrupt")
    called = []
    monkeypatch.setattr("app.backup_restore.run_postgres_tool", lambda *args: called.append(args))
    with pytest.raises(BackupError, match="Checksum mismatch"):
        restore_backup(backup, "postgresql://fictional@localhost/example", storage, True)
    assert called == []


def test_unsafe_archive_never_starts_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = fixture_backup(tmp_path / "backup")
    with tarfile.open(backup / "storage.tar.gz", "w:gz") as archive:
        entry = tarfile.TarInfo("../outside")
        entry.size = 1
        archive.addfile(entry, io.BytesIO(b"x"))
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    manifest["storage_sha256"] = sha256_file(backup / "storage.tar.gz")
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    called = []
    monkeypatch.setattr("app.backup_restore.run_postgres_tool", lambda *args: called.append(args))
    with pytest.raises(BackupError, match="Unsafe archive entry"):
        restore_backup(
            backup, "postgresql://fictional@localhost/example", tmp_path / "storage", True
        )
    assert called == []


def test_failed_backup_leaves_no_completed_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    destination = tmp_path / "backups"

    def fail_dump(*_args: object) -> None:
        raise BackupError("pg_dump failed")

    monkeypatch.setattr("app.backup_restore.run_postgres_tool", fail_dump)
    with pytest.raises(BackupError, match="pg_dump failed"):
        create_backup("postgresql://fictional@localhost/example", storage, destination)
    assert list(destination.iterdir()) == []
