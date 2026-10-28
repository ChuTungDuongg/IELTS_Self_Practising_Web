"""Portable v2 backup bundles and non-destructive isolated recovery.

The existing local v1 backup remains readable by app.backup_restore. This format
does not alter Test Transfer ZIP v1/v2. All object I/O is bounded and streaming.
"""

import asyncio
import hashlib
import json
import tarfile
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.backup_restore import APPLICATION, DATABASE_FILE, MANIFEST_FILE, STORAGE_FILE, sha256_file
from app.storage.keys import validate_key
from app.storage.migration import SUCCESS, reconcile, reference_map, write_report
from app.storage.operations import database_id, database_inventory, postgres_tool
from app.storage.tasks import storage_io

MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_OBJECT_BYTES = 5 * 1024**3  # Same bounded single-object contract as the adapter.


class BoundedTarInfo(tarfile.TarInfo):
    @classmethod
    def frombuf(cls, buf, encoding, errors):
        member = super().frombuf(buf, encoding, errors)
        # tarfile reads PAX/GNU metadata into RAM before yielding a member.
        # Bound that header too, not only ordinary object bodies.
        if (
            member.type
            in {
                tarfile.XHDTYPE,
                tarfile.XGLTYPE,
                tarfile.GNUTYPE_LONGNAME,
                tarfile.GNUTYPE_LONGLINK,
            }
            and member.size > 64 * 1024
        ):
            raise ValueError("Oversized archive metadata")
        if member.size > MAX_OBJECT_BYTES:
            raise ValueError("Oversized archive entry")
        return member


class DigestReader:
    def __init__(self, source):
        self.source = source
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, count):
        if count < 0:
            raise ValueError("Unbounded recovery read rejected")
        chunk = self.source.read(min(count, 1024 * 1024))
        self.size += len(chunk)
        self.digest.update(chunk)
        return chunk


def archive_objects(storage, references, destination):
    entries = []
    with tarfile.open(destination, "w:gz") as archive:
        for reference in sorted(reference_map(references).values(), key=lambda x: x.key):
            info = storage.stat(reference.key)
            if not 0 < info.size <= MAX_OBJECT_BYTES or (
                reference.size is not None and reference.size != info.size
            ):
                raise ValueError("Source object size disagrees with database or upload limit")
            member = tarfile.TarInfo(reference.key)
            member.size, member.mode = info.size, 0o600
            with storage.open_reader(reference.key) as source:
                reader = DigestReader(source)
                archive.addfile(member, reader)
                if reader.size != info.size or source.read(1):
                    raise ValueError("Source object changed during backup")
            digest = reader.digest.hexdigest()
            if reference.sha256 and reference.sha256 != digest:
                raise ValueError("Source object checksum disagrees with database")
            if storage.stat(reference.key).size != info.size:
                raise ValueError("Source object changed during backup")
            entries.append(
                {
                    "key": reference.key,
                    "size": info.size,
                    "sha256": digest,
                    "content_type": reference.content_type
                    or info.content_type
                    or "application/octet-stream",
                    "category": reference.category,
                    "verified": True,
                }
            )
    return entries


def read_portable_manifest(backup_dir):
    backup_dir = Path(backup_dir)
    path = backup_dir / MANIFEST_FILE
    if (
        backup_dir.is_symlink()
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_MANIFEST_BYTES
    ):
        raise ValueError("Invalid portable backup manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("format_version") != 2
        or manifest.get("application") != APPLICATION
    ):
        raise ValueError("Unsupported portable backup; use legacy restore for local v1")
    if (
        manifest.get("complete") is not True
        or manifest.get("consistency") != "operator-maintenance-window"
    ):
        raise ValueError("Backup is incomplete or consistency was not acknowledged")
    if (
        manifest.get("database_file") != DATABASE_FILE
        or manifest.get("storage_file") != STORAGE_FILE
    ):
        raise ValueError("Invalid backup file names")
    entries = manifest.get("objects")
    if not isinstance(entries, list) or len(entries) > 250_000:
        raise ValueError("Invalid or oversized object manifest")
    seen = set()
    for entry in entries:
        key = validate_key(entry["key"])
        folded = key.casefold()
        if folded in seen:
            raise ValueError("Duplicate/case-colliding manifest key")
        seen.add(folded)
        if (
            type(entry.get("size")) is not int
            or not 0 < entry["size"] <= MAX_OBJECT_BYTES
            or entry.get("verified") is not True
        ):
            raise ValueError("Invalid object size/verification")
        check_digest(entry.get("sha256"))
        if not isinstance(entry.get("content_type"), str) or not entry["content_type"]:
            raise ValueError("Invalid object Content-Type")
    for name in ("database_sha256", "storage_sha256"):
        check_digest(manifest.get(name))
    if not isinstance(manifest.get("source_database_id"), str):
        raise ValueError("Backup database identity missing")
    source = manifest.get("source")
    if (
        not isinstance(source, dict)
        or source.get("backend") not in {"local", "s3", "r2"}
        or source.get("environment") not in {"development", "staging", "production", "recovery"}
    ):
        raise ValueError("Backup source metadata missing")
    return manifest


def check_digest(value):
    import re

    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("Invalid SHA-256")


def walk_archive(backup_dir, manifest, visitor=None):
    expected = {item["key"]: item for item in manifest["objects"]}
    seen = set()
    # No extraction, links or paths from an archive ever reach the filesystem.
    try:
        with tarfile.open(
            Path(backup_dir) / STORAGE_FILE, "r|gz", tarinfo=BoundedTarInfo
        ) as archive:
            for member in archive:
                key = validate_key(member.name)
                if not member.isfile() or member.issparse() or key not in expected or key in seen:
                    raise ValueError("Unexpected, unsafe or duplicate backup member")
                entry = expected[key]
                if member.size != entry["size"]:
                    raise ValueError("Backup member size mismatch")
                with archive.extractfile(member) as source:
                    reader = DigestReader(source)
                    if visitor:
                        visitor(entry, reader)
                    while reader.read(1024 * 1024):
                        pass
                    if reader.size != entry["size"] or reader.digest.hexdigest() != entry["sha256"]:
                        raise ValueError("Backup object checksum mismatch")
                seen.add(key)
    except tarfile.TarError as error:
        raise ValueError("Invalid backup storage archive") from error
    if seen != set(expected):
        raise ValueError("Required backup object is missing")


def verify_portable_backup(backup_dir):
    manifest = read_portable_manifest(backup_dir)
    for filename, digest in ((DATABASE_FILE, "database_sha256"), (STORAGE_FILE, "storage_sha256")):
        path = Path(backup_dir) / filename
        if path.is_symlink() or not path.is_file() or sha256_file(path) != manifest[digest]:
            raise ValueError("Backup file missing or checksum mismatch")
    walk_archive(backup_dir, manifest)
    return manifest


async def create_portable_backup(
    url, source, backup_root, *, maintenance=False, tool=postgres_tool
):
    if not maintenance:
        raise ValueError("Backup requires --maintenance-window and all background writers stopped")
    backup_root = await asyncio.to_thread(Path(backup_root).resolve)
    from app.storage.local import LocalAssetStorage

    if isinstance(source.storage, LocalAssetStorage) and backup_root.is_relative_to(
        source.storage.root
    ):
        raise ValueError("Backup output must be outside source storage")
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix=".backup-incomplete-", dir=backup_root))
    manifest = {
        "application": APPLICATION,
        "format_version": 2,
        "complete": False,
        "consistency": "operator-maintenance-window",
        "source": source.description(),
        "source_database_id": database_id(url),
        "database_file": DATABASE_FILE,
        "storage_file": STORAGE_FILE,
        "created_at": datetime.now(UTC).isoformat(),
        "objects": [],
    }
    final = None
    try:
        async with database_inventory(url, snapshot=True) as (references, cleanup, snapshot):
            reference_map(references)  # Validate before dumping or reading any objects.
            await storage_io(tool, "pg_dump", url, stage / DATABASE_FILE, snapshot=snapshot)
            manifest["objects"] = await storage_io(
                archive_objects, source.storage, references, stage / STORAGE_FILE
            )
            manifest["pending_cleanup_keys"] = cleanup
        async with database_inventory(url) as (after, _, _):
            if sorted(map(repr, references)) != sorted(map(repr, after)):
                raise ValueError(
                    "Database references changed: maintenance window was not effective"
                )
        manifest.update(
            database_sha256=await asyncio.to_thread(sha256_file, stage / DATABASE_FILE),
            storage_sha256=await asyncio.to_thread(sha256_file, stage / STORAGE_FILE),
            complete=True,
        )
        write_report(stage / MANIFEST_FILE, manifest)
        await asyncio.to_thread(verify_portable_backup, stage)
        final = backup_root / (
            datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        )
        await storage_io(stage.rename, final)
        return final
    except BaseException as error:
        # Keep private incomplete bytes for investigation, never a completed bundle.
        manifest.update(complete=False, failure=type(error).__name__)
        failure_dir = final if final is not None and final.exists() else stage
        write_report(failure_dir / MANIFEST_FILE, manifest)
        raise


def restore_objects(backup_dir, destination, *, execute=False, progress=None):
    manifest = verify_portable_backup(backup_dir)
    expected = {item["key"]: item for item in manifest["objects"]}
    rows = []
    # Check every conflict before performing even the first write.
    from app.storage.migration import fingerprint_matches

    for entry in expected.values():
        key = entry["key"]
        if destination.exists(key):
            matches = fingerprint_matches(destination, key, (entry["size"], entry["sha256"]))
            rows.append(
                {
                    "key": key,
                    "status": "identical" if matches else "conflict",
                    "size": entry["size"],
                    "sha256": entry["sha256"],
                }
            )
        else:
            rows.append(
                {
                    "key": key,
                    "status": "would_copy",
                    "size": entry["size"],
                    "sha256": entry["sha256"],
                }
            )
    if not execute or any(row["status"] == "conflict" for row in rows):
        return manifest, rows
    by_key = {row["key"]: row for row in rows}

    def visitor(entry, reader):
        row = by_key[entry["key"]]
        if row["status"] == "identical":
            return
        try:
            destination.put_stream(
                entry["key"], reader, content_type=entry["content_type"], max_bytes=entry["size"]
            )
        except FileExistsError:
            pass  # Another operator won; verify instead of replacing it.
        row["status"] = (
            "copied"
            if fingerprint_matches(destination, entry["key"], (entry["size"], entry["sha256"]))
            else "verification_failed"
        )
        if progress:
            progress(rows)

    walk_archive(backup_dir, manifest, visitor)
    return manifest, rows


async def reconcile_restored_database(url, destination, manifest):
    async with database_inventory(url) as (references, cleanup, _):
        actual = reference_map(references)
    expected = {item["key"]: item for item in manifest["objects"]}
    if set(actual) != set(expected):
        raise ValueError("Restored database references differ from backup inventory")
    rows = await asyncio.to_thread(reconcile, destination, actual.values(), expected=expected)
    if any(row.status not in SUCCESS for row in rows):
        raise ValueError("Restored database objects failed integrity reconciliation")
    return {
        "verified": True,
        "results": [asdict(row) for row in rows],
        "pending_cleanup_keys": cleanup,
    }
