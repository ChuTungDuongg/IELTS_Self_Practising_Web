"""Offline PostgreSQL and local-asset backup for the MVP."""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings

APPLICATION = "DevWebLocalforIELTS"
DATABASE_FILE = "database.dump"
STORAGE_FILE = "storage.tar.gz"
MANIFEST_FILE = "manifest.json"
FORMAT_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class BackupError(Exception):
    """An operator-facing backup or restore failure."""


def normalize_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://") :]
    if url.startswith("postgresql://"):
        return url
    raise BackupError("DATABASE_URL must be a PostgreSQL URL.")


def load_configuration() -> tuple[str, Path]:
    env_file = REPO_ROOT / "backend" / ".env"
    configured = "DATABASE_URL" in os.environ
    if not configured and env_file.is_file():
        configured = any(
            re.match(r"\s*DATABASE_URL\s*=", line)
            for line in env_file.read_text(encoding="utf-8").splitlines()
        )
    if not configured:
        raise BackupError("DATABASE_URL missing; set it in the environment or backend/.env.")
    try:
        settings = Settings(_env_file=env_file)
        configured_storage = settings.storage_root
        if not configured_storage.is_absolute():
            configured_storage = REPO_ROOT / "backend" / configured_storage
        if configured_storage.is_symlink():
            raise BackupError("STORAGE_ROOT symlinks are not supported.")
        return normalize_database_url(settings.database_url), settings.resolved_storage_root
    except BackupError:
        raise
    except (ValueError, OSError) as error:
        raise BackupError("Backend environment configuration is invalid.") from error


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_direct_child(path: Path, parent: Path) -> None:
    if path.resolve().parent != parent.resolve():
        raise BackupError(f"Filesystem target is outside the configured directory: {path}.")


def run_postgres_tool(tool: str, arguments: list[str]) -> None:
    if shutil.which(tool) is None:
        raise BackupError(f"{tool} not found on PATH; install PostgreSQL client tools.")
    try:
        completed = subprocess.run([tool, *arguments], capture_output=True, text=True, check=False)
    except OSError as error:
        raise BackupError(f"Could not start {tool}; check PostgreSQL client tools.") from error
    if completed.returncode != 0:
        # PostgreSQL diagnostics can echo connection strings. Never print them here.
        raise BackupError(
            f"{tool} failed (exit {completed.returncode}); check the database connection "
            "and PostgreSQL client/server compatibility."
        )


def archive_storage(storage_root: Path, destination: Path) -> None:
    if not storage_root.is_dir() or storage_root.is_symlink():
        raise BackupError("STORAGE_ROOT missing or invalid; configure an existing directory.")
    with tarfile.open(destination, "w:gz") as archive:
        for base, dirs, files in os.walk(storage_root, followlinks=False):
            dirs.sort()
            for name in sorted([*dirs, *files]):
                path = Path(base) / name
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise BackupError(
                        f"Storage symlink/junction rejected: {path.relative_to(storage_root)}"
                    )
                if not (path.is_dir() or path.is_file()):
                    raise BackupError(
                        f"Unsupported storage entry: {path.relative_to(storage_root)}"
                    )
                if not path.resolve().is_relative_to(storage_root):
                    raise BackupError("Storage entry resolves outside STORAGE_ROOT.")
                archive.add(
                    path, arcname=path.relative_to(storage_root).as_posix(), recursive=False
                )


def create_backup(database_url: str, storage_root: Path, backup_root: Path) -> Path:
    backup_root = backup_root.resolve()
    if storage_root.is_symlink():
        raise BackupError("STORAGE_ROOT symlinks are not supported.")
    storage_root = storage_root.resolve()
    if backup_root.is_relative_to(storage_root):
        raise BackupError("Backup directory must be outside STORAGE_ROOT.")
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix=".backup-incomplete-", dir=backup_root))
    try:
        run_postgres_tool(
            "pg_dump",
            ["--format=custom", f"--file={stage / DATABASE_FILE}", f"--dbname={database_url}"],
        )
        archive_storage(storage_root, stage / STORAGE_FILE)
        created_at = datetime.now(UTC)
        manifest = {
            "format_version": FORMAT_VERSION,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "database_file": DATABASE_FILE,
            "storage_file": STORAGE_FILE,
            "database_sha256": sha256_file(stage / DATABASE_FILE),
            "storage_sha256": sha256_file(stage / STORAGE_FILE),
            "application": APPLICATION,
        }
        (stage / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        name = created_at.strftime("%Y-%m-%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        final = backup_root / name
        require_direct_child(stage, backup_root)
        require_direct_child(final, backup_root)
        stage.rename(final)
        return final
    finally:
        if stage.exists():
            require_direct_child(stage, backup_root)
            shutil.rmtree(stage)


def read_manifest(backup_dir: Path) -> dict[str, str | int]:
    path = backup_dir / MANIFEST_FILE
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise BackupError("Backup manifest invalid or missing.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BackupError("Backup manifest invalid or unreadable.") from error
    if not isinstance(manifest, dict):
        raise BackupError("Backup manifest invalid: expected an object.")
    if (
        type(manifest.get("format_version")) is not int
        or manifest["format_version"] != FORMAT_VERSION
    ):
        raise BackupError("Backup manifest format_version is unsupported.")
    if manifest.get("application") != APPLICATION:
        raise BackupError("Backup manifest application is invalid.")
    if (
        manifest.get("database_file") != DATABASE_FILE
        or manifest.get("storage_file") != STORAGE_FILE
    ):
        raise BackupError("Backup manifest file names are invalid.")
    for key in ("database_sha256", "storage_sha256"):
        if not isinstance(manifest.get(key), str) or not SHA256.fullmatch(manifest[key]):
            raise BackupError(f"Backup manifest {key} is invalid.")
    created_at = manifest.get("created_at")
    try:
        if not isinstance(created_at, str) or not created_at.endswith("Z"):
            raise ValueError("not UTC")
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise BackupError("Backup manifest created_at is invalid.") from error
    return manifest


def verify_backup_files(backup_dir: Path, manifest: dict[str, str | int]) -> None:
    for file_key, hash_key in (
        ("database_file", "database_sha256"),
        ("storage_file", "storage_sha256"),
    ):
        path = backup_dir / str(manifest[file_key])
        if path.is_symlink() or not path.is_file():
            raise BackupError(f"Backup file missing or invalid: {manifest[file_key]}.")
        if sha256_file(path) != manifest[hash_key]:
            raise BackupError(f"Checksum mismatch: {manifest[file_key]}; restore aborted.")


def validated_archive_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    seen: set[str] = set()
    kinds: dict[str, bool] = {}
    for member in members:
        name = member.name
        parts = name.rstrip("/").split("/")
        if (
            not name
            or name.startswith("/")
            or "\\" in name
            or any(part in {"", ".", ".."} or ":" in part for part in parts)
            or (name.endswith("/") and not member.isdir())
            or not (member.isfile() or member.isdir())
        ):
            raise BackupError(f"Unsafe archive entry rejected: {name!r}.")
        folded = "/".join(parts).casefold()
        if folded in seen:
            raise BackupError(f"Duplicate archive entry rejected: {name!r}.")
        seen.add(folded)
        kinds[folded] = member.isdir()
    for member in members:
        parts = member.name.rstrip("/").split("/")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index]).casefold()
            if parent in kinds and not kinds[parent]:
                raise BackupError(f"Unsafe archive entry rejected: {member.name!r}.")
    return members


def extract_validated_archive(
    archive: tarfile.TarFile, members: list[tarfile.TarInfo], stage: Path
) -> None:
    for member in members:
        destination = stage.joinpath(*member.name.rstrip("/").split("/"))
        if not destination.resolve().is_relative_to(stage):
            raise BackupError(f"Unsafe archive entry rejected: {member.name!r}.")
        if member.isdir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(member)
        if source is None:
            raise BackupError(f"Cannot read archive entry: {member.name!r}.")
        with source, destination.open("xb") as output:
            shutil.copyfileobj(source, output)


async def alembic_revision(database_url: str) -> str:
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url)
    try:
        async with engine.connect() as connection:
            revisions = (
                (await connection.execute(text("SELECT version_num FROM alembic_version")))
                .scalars()
                .all()
            )
        if not revisions:
            raise BackupError("Restored database has an empty alembic_version table.")
        return ", ".join(revisions)
    except BackupError:
        raise
    except Exception as error:
        raise BackupError("Restored database has no readable alembic_version table.") from error
    finally:
        await engine.dispose()


def replace_storage(stage: Path, storage_root: Path) -> Path | None:
    previous = storage_root.with_name(f".{storage_root.name}.before-restore-{uuid4().hex[:8]}")
    for path in (stage, storage_root, previous):
        require_direct_child(path, storage_root.parent)
    had_existing = storage_root.exists()
    if had_existing:
        storage_root.rename(previous)
    try:
        stage.rename(storage_root)
    except OSError as error:
        if had_existing:
            try:
                previous.rename(storage_root)
            except OSError as rollback_error:
                raise BackupError(
                    f"Storage replacement and rollback failed; old storage is at {previous}. "
                    "Keep application writes stopped."
                ) from rollback_error
        raise BackupError(
            "Storage replacement failed after database restore; inspect backup and storage paths."
        ) from error
    if had_existing:
        try:
            require_direct_child(previous, storage_root.parent)
            shutil.rmtree(previous)
        except OSError:
            return previous
    return None


def restore_backup(backup_dir: Path, database_url: str, storage_root: Path, confirmed: bool) -> str:
    backup_dir = backup_dir.resolve()
    manifest = read_manifest(backup_dir)
    verify_backup_files(backup_dir, manifest)
    if not confirmed:
        raise BackupError(
            f"Restore would replace database and STORAGE_ROOT ({storage_root}); "
            "pass --confirm-destructive after stopping application writes."
        )
    if storage_root.is_symlink():
        raise BackupError("STORAGE_ROOT symlinks are not supported.")
    storage_root = storage_root.resolve()
    if backup_dir.is_relative_to(storage_root):
        raise BackupError(
            "Backup directory must be outside STORAGE_ROOT; storage symlinks are rejected."
        )
    storage_root.parent.mkdir(parents=True, exist_ok=True)
    stage: Path | None = None
    database_restored = False
    try:
        with tarfile.open(backup_dir / STORAGE_FILE, "r:gz") as archive:
            members = validated_archive_members(archive)
            stage = Path(tempfile.mkdtemp(prefix=".storage-restore-", dir=storage_root.parent))
            extract_validated_archive(archive, members, stage)
        run_postgres_tool(
            "pg_restore",
            [
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "--single-transaction",
                "--exit-on-error",
                f"--dbname={database_url}",
                str(backup_dir / DATABASE_FILE),
            ],
        )
        database_restored = True
        try:
            revision = asyncio.run(alembic_revision(database_url))
        except BackupError as error:
            raise BackupError(
                f"{error} Database restore completed but storage was not replaced; "
                "keep application writes stopped and inspect the backup."
            ) from error
        leftover = replace_storage(stage, storage_root)
        stage = None
        if leftover:
            return f"Restored Alembic revision {revision}. Old storage remains at {leftover}; remove it after inspection."
        return f"Restored Alembic revision {revision}."
    except (tarfile.TarError, OSError) as error:
        if database_restored:
            raise BackupError(
                "Storage restore failed after database restore; retry offline from the same backup."
            ) from error
        raise BackupError("Storage archive invalid or unreadable; restore aborted.") from error
    finally:
        if stage is not None and stage.exists():
            require_direct_child(stage, storage_root.parent)
            shutil.rmtree(stage)


def backup_main() -> int:
    parser = argparse.ArgumentParser(description="Back up PostgreSQL and local binary storage.")
    parser.add_argument("--backup-root", type=Path, default=REPO_ROOT / "backups")
    args = parser.parse_args()
    try:
        database_url, storage_root = load_configuration()
        print("Maintenance backup: stop FastAPI and prevent writes until this command completes.")
        destination = create_backup(database_url, storage_root, args.backup_root)
        print(f"Backup complete: {destination}")
        return 0
    except BackupError as error:
        parser.exit(1, f"Backup failed: {error}\n")
    except (OSError, UnicodeError, tarfile.TarError):
        parser.exit(
            1,
            "Backup failed: filesystem or archive operation failed; check paths and permissions.\n",
        )


def restore_main() -> int:
    parser = argparse.ArgumentParser(description="Restore PostgreSQL and local binary storage.")
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--confirm-destructive", action="store_true")
    args = parser.parse_args()
    try:
        database_url, storage_root = load_configuration()
        print("Maintenance restore: stop FastAPI and prevent writes until this command completes.")
        print(restore_backup(args.backup_dir, database_url, storage_root, args.confirm_destructive))
        return 0
    except BackupError as error:
        parser.exit(1, f"Restore failed: {error}\n")
    except (OSError, UnicodeError, tarfile.TarError):
        parser.exit(
            1,
            "Restore failed: filesystem or archive operation failed; check paths and permissions.\n",
        )
