import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.backup_restore import (
    APPLICATION,
    BackupError,
    PostgresToolSelection,
    archive_storage,
    create_backup,
    extract_validated_archive,
    normalize_database_url,
    read_manifest,
    resolve_postgres_tool_mode,
    restore_backup,
    run_pg_dump,
    run_pg_restore,
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
    monkeypatch.setattr("app.backup_restore.run_pg_restore", lambda *args: called.append(args))
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
    monkeypatch.setattr("app.backup_restore.run_pg_restore", lambda *args: called.append(args))
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
    monkeypatch.setattr("app.backup_restore.run_pg_restore", lambda *args: called.append(args))
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

    monkeypatch.setattr("app.backup_restore.run_pg_dump", fail_dump)
    with pytest.raises(BackupError, match="pg_dump failed"):
        create_backup("postgresql://fictional@localhost/example", storage, destination)
    assert list(destination.iterdir()) == []


def test_host_tool_is_preferred(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr("app.backup_restore.shutil.which", lambda tool: f"/tools/{tool}")
    monkeypatch.setattr(
        "app.backup_restore.run_postgres_tool",
        lambda tool, args: calls.append((tool, args)),
    )
    url = "postgresql://fictional:private@localhost:5433/example"
    assert resolve_postgres_tool_mode("pg_dump", url).mode == "HOST"
    run_pg_dump(url, tmp_path / "database.dump")
    assert calls == [
        (
            "pg_dump",
            ["--format=custom", f"--file={tmp_path / 'database.dump'}", f"--dbname={url}"],
        )
    ]


def mock_running_compose(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "app.backup_restore.shutil.which",
        lambda tool: "/tools/docker" if tool == "docker" else None,
    )

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if "config" in command:
            output = json.dumps(
                {
                    "services": {
                        "postgres": {
                            "environment": {"POSTGRES_USER": "ielts", "POSTGRES_DB": "ielts"},
                            "ports": [{"target": 5432, "published": "5433", "protocol": "tcp"}],
                        }
                    }
                }
            )
        elif "ps" in command:
            output = "postgres\n"
        else:
            output = "Docker version\n"
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr("app.backup_restore.subprocess.run", run)
    return commands


def test_missing_host_tool_selects_running_local_compose(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = mock_running_compose(monkeypatch)
    selection = resolve_postgres_tool_mode(
        "pg_dump", "postgresql://ielts:private@localhost:5433/fictional_smoke"
    )
    assert selection.mode == "DOCKER_COMPOSE"
    assert selection.username == "ielts"
    assert selection.database == "fictional_smoke"
    assert any("config" in command for command in commands)
    assert any("ps" in command for command in commands)


def test_no_host_tools_or_docker_gives_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.backup_restore.shutil.which", lambda _tool: None)
    with pytest.raises(BackupError, match="Docker Compose is unavailable"):
        resolve_postgres_tool_mode("pg_dump", "postgresql://ielts@localhost:5433/ielts")
    with pytest.raises(BackupError, match="other servers"):
        resolve_postgres_tool_mode("pg_dump", "postgresql://ielts@db.example.test/ielts")


def test_stopped_compose_postgres_gives_start_command(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_running_compose(monkeypatch)
    monkeypatch.setattr(
        "app.backup_restore.docker_text_command",
        lambda args: (
            ""
            if "ps" in args
            else json.dumps(
                {
                    "services": {
                        "postgres": {
                            "environment": {"POSTGRES_USER": "ielts", "POSTGRES_DB": "ielts"},
                            "ports": [{"target": 5432, "published": "5433", "protocol": "tcp"}],
                        }
                    }
                }
            )
        ),
    )
    with pytest.raises(BackupError, match="docker compose up -d postgres"):
        resolve_postgres_tool_mode("pg_dump", "postgresql://ielts@localhost:5433/ielts")


def test_docker_dump_streams_binary_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.backup_restore.resolve_postgres_tool_mode",
        lambda *_args: PostgresToolSelection("DOCKER_COMPOSE", "ielts", "ielts"),
    )
    payload = b"PGDMP\x00\xff\x80fictional"

    def stream(command: list[str], **kwargs: object) -> SimpleNamespace:
        assert command[:2] == ["docker", "compose"]
        assert all("private" not in token for token in command)
        assert command[command.index("exec") + 1 : command.index("exec") + 4] == [
            "-T",
            "postgres",
            "pg_dump",
        ]
        assert "--format=custom" in command
        assert "--dbname=ielts" in command
        output = kwargs["stdout"]
        output.write(payload)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("app.backup_restore.subprocess.run", stream)
    destination = tmp_path / "database.dump"
    run_pg_dump("postgresql://ielts:private@localhost:5433/ielts", destination)
    assert destination.read_bytes() == payload


def test_docker_restore_streams_binary_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.backup_restore.resolve_postgres_tool_mode",
        lambda *_args: PostgresToolSelection("DOCKER_COMPOSE", "ielts", "ielts"),
    )
    payload = b"PGDMP\x00\xff\x80fictional"
    source = tmp_path / "database.dump"
    source.write_bytes(payload)

    def stream(command: list[str], **kwargs: object) -> SimpleNamespace:
        assert command[command.index("exec") + 1 : command.index("exec") + 4] == [
            "-T",
            "postgres",
            "pg_restore",
        ]
        assert "--clean" in command
        assert "--single-transaction" in command
        assert kwargs["stdin"].read() == payload
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("app.backup_restore.subprocess.run", stream)
    run_pg_restore("postgresql://ielts:private@localhost:5433/ielts", source)


def test_docker_failure_never_leaks_database_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.backup_restore.resolve_postgres_tool_mode",
        lambda *_args: PostgresToolSelection("DOCKER_COMPOSE", "ielts", "ielts"),
    )

    def fail(_command: list[str], **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stderr=b"postgresql://ielts:private@localhost")

    monkeypatch.setattr("app.backup_restore.subprocess.run", fail)
    with pytest.raises(BackupError) as caught:
        run_pg_dump("postgresql://ielts:private@localhost:5433/ielts", tmp_path / "database.dump")
    assert "private" not in str(caught.value)
    assert "postgresql://" not in str(caught.value)
