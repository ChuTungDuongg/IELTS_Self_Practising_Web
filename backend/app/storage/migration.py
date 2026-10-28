"""Safe, explicit copy primitives. Never delete source or replace destination objects."""

import hashlib
import json
import mimetypes
import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import literal, select, union_all

from app.core.exceptions import AppError
from app.models import Asset, TestCover
from app.models.classroom_classwork import ClassroomResource
from app.models.speaking import SpeakingAudioChunk, SpeakingAudioSegment, SpeakingMediaCleanup
from app.models.speaking_transcript import SpeakingNormalizedAudio
from app.models.writing_benchmark import WritingBenchmarkSample
from app.storage.base import AssetStorage
from app.storage.keys import validate_key


@dataclass(frozen=True, slots=True)
class CopyResult:
    key: str
    status: str
    detail: str = ""
    size: int | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class AssetReference:
    key: str
    category: str
    size: int | None = None
    sha256: str | None = None
    content_type: str | None = None


async def inventory_references(session) -> list[AssetReference]:
    """All rows, including archived versions, inactive takes and historical media.

    Rows in the cleanup outbox are diagnostics, never live references. Asset rows
    intentionally include unused builder uploads: they still belong to a version.
    """
    statements = (
        select(
            Asset.relative_path,
            literal("test_asset"),
            Asset.file_size,
            literal(None),
            Asset.mime_type,
        ),
        select(
            TestCover.relative_path,
            literal("test_cover"),
            TestCover.file_size,
            literal(None),
            TestCover.mime_type,
        ),
        select(
            ClassroomResource.storage_key,
            literal("classroom"),
            ClassroomResource.size_bytes,
            literal(None),
            ClassroomResource.media_type,
        ).where(ClassroomResource.storage_key.is_not(None)),
        select(
            SpeakingAudioChunk.storage_key,
            literal("speaking_chunk"),
            SpeakingAudioChunk.byte_size,
            SpeakingAudioChunk.sha256,
            SpeakingAudioSegment.mime_type,
        ).join(SpeakingAudioSegment, SpeakingAudioChunk.segment_id == SpeakingAudioSegment.id),
        select(
            SpeakingNormalizedAudio.storage_key,
            literal("speaking_normalized"),
            literal(None),
            literal(None),
            literal("audio/wav"),
        ),
        select(
            WritingBenchmarkSample.task1_image_key,
            literal("writing_benchmark"),
            literal(None),
            literal(None),
            literal(None),
        ).where(WritingBenchmarkSample.task1_image_key.is_not(None)),
    )
    return [AssetReference(*row) for row in await session.execute(union_all(*statements))]


async def inventory_cleanup(session) -> list[str]:
    # The outbox has no failed/success flag: report pending work, never invent one.
    return sorted(await session.scalars(select(SpeakingMediaCleanup.storage_key)))


def reference_map(references):
    result = {}
    for item in references:
        validate_key(item.key)
        previous = result.get(item.key)
        if previous and any(
            a is not None and b is not None and a != b
            for a, b in ((previous.size, item.size), (previous.sha256, item.sha256))
        ):
            raise ValueError("Conflicting database asset metadata")
        result[item.key] = (
            item
            if previous is None
            else AssetReference(
                item.key,
                previous.category,
                previous.size if previous.size is not None else item.size,
                previous.sha256 or item.sha256,
                previous.content_type or item.content_type,
            )
        )
    return result


async def inventory_referenced_keys(session) -> list[str]:
    """Inventory only referenced objects; cleanup-outbox rows are not live references."""
    columns = (
        Asset.relative_path,
        TestCover.relative_path,
        ClassroomResource.storage_key,
        SpeakingAudioChunk.storage_key,
        SpeakingNormalizedAudio.storage_key,
        WritingBenchmarkSample.task1_image_key,
    )
    result = await session.scalars(union_all(*(select(column) for column in columns)))
    return sorted({key for key in result if key is not None})


def _fingerprint(
    storage: AssetStorage, key: str, *, max_bytes: int | None = None
) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with storage.open_reader(key) as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise ValueError("Object exceeds expected size")
            digest.update(chunk)
    return size, digest.hexdigest()


def _copy_one(
    source: AssetStorage,
    destination: AssetStorage,
    key: str,
    dry_run: bool,
    reference: AssetReference | None = None,
) -> CopyResult:
    try:
        validate_key(key)
        try:
            info = source.stat(key)
        except AppError as error:
            if error.code == "ASSET_NOT_FOUND":
                return CopyResult(key, "missing_source")
            raise
        if not 0 < info.size <= 5 * 1024**3:
            return CopyResult(
                key, "error", "Object size outside the supported 1 byte to 5 GiB range"
            )
        expected = _fingerprint(source, key, max_bytes=info.size)
        if expected[0] != info.size:
            return CopyResult(key, "error", "Source changed during inventory")
        if reference and (
            (reference.size is not None and reference.size != expected[0])
            or (reference.sha256 is not None and reference.sha256 != expected[1])
        ):
            return CopyResult(key, "source_integrity_failed", size=expected[0], sha256=expected[1])
        if destination.exists(key):
            return CopyResult(
                key,
                "identical" if fingerprint_matches(destination, key, expected) else "conflict",
                size=expected[0],
                sha256=expected[1],
            )
        if dry_run:
            return CopyResult(key, "would_copy", size=expected[0], sha256=expected[1])
        mime = (
            (reference.content_type if reference else None)
            or info.content_type
            or mimetypes.guess_type(key)[0]
            or "application/octet-stream"
        )
        try:
            with source.open_reader(key) as reader:
                destination.put_stream(key, reader, content_type=mime, max_bytes=info.size)
        except FileExistsError:
            return CopyResult(
                key,
                "identical" if fingerprint_matches(destination, key, expected) else "conflict",
                size=expected[0],
                sha256=expected[1],
            )
        return CopyResult(
            key,
            "copied" if fingerprint_matches(destination, key, expected) else "verification_failed",
            size=expected[0],
            sha256=expected[1],
        )
    except Exception as error:
        # Do not include provider exception text: it can contain endpoint or credentials.
        return CopyResult(key, "error", getattr(error, "code", type(error).__name__))


def fingerprint_matches(storage, key, expected):
    if storage.stat(key).size != expected[0]:
        return False
    return _fingerprint(storage, key, max_bytes=expected[0]) == expected


def write_report(path: Path, report):
    """Atomic, private checkpoint; its content is never trusted to skip checksums."""
    import tempfile

    path = Path(path)
    if path.is_symlink():
        raise ValueError("Report must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".storage-report-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


SUCCESS = {"copied", "identical", "verified"}


def copy_keys(
    source: AssetStorage,
    destination: AssetStorage,
    keys,
    *,
    dry_run=True,
    workers=1,
    references=None,
    progress=None,
):
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    keys = iter(sorted(set(keys)))
    references = references or {}
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Bound queued work too, not just active threads, for large inventories.
        pending = set()

        def submit():
            key = next(keys, None)
            if key is not None:
                pending.add(
                    pool.submit(_copy_one, source, destination, key, dry_run, references.get(key))
                )

        for _ in range(workers):
            submit()
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                row = future.result()
                results.append(row)
                if progress:
                    progress([asdict(item) for item in sorted(results, key=lambda x: x.key)])
                submit()
    return sorted(results, key=lambda x: x.key)


def reconcile(storage, references, *, expected=None):
    """Read-only, checks all references without aborting on one invalid key."""
    rows = []
    for reference in references:
        try:
            validate_key(reference.key)
            info = storage.stat(reference.key)
            size, digest = _fingerprint(storage, reference.key, max_bytes=info.size)
            wanted = (expected or {}).get(reference.key)
            valid = (
                size == info.size
                and (reference.size is None or reference.size == size)
                and (reference.sha256 is None or reference.sha256 == digest)
                and (not wanted or (size == wanted["size"] and digest == wanted["sha256"]))
            )
            rows.append(
                CopyResult(
                    reference.key,
                    "verified" if valid else "integrity_failed",
                    size=size,
                    sha256=digest,
                )
            )
        except Exception as error:
            code = getattr(error, "code", type(error).__name__)
            rows.append(CopyResult(reference.key, "error", code))
    return rows


def iter_object_keys(storage):
    """Explicit operational listing only; never used by request handlers."""
    from app.storage.local import LocalAssetStorage
    from app.storage.s3 import S3CompatibleStorage

    if isinstance(storage, LocalAssetStorage):
        for base, directories, files in os.walk(storage.root, followlinks=False):
            for name in [*directories, *files]:
                path = Path(base) / name
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise ValueError("Symlink/junction in storage inventory")
            for name in files:
                yield (Path(base) / name).relative_to(storage.root).as_posix()
    elif isinstance(storage, S3CompatibleStorage):
        pages = storage.client.get_paginator("list_objects_v2").paginate(
            Bucket=storage.bucket,
            Prefix=storage.prefix,
            PaginationConfig={"PageSize": 1000},
        )
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.startswith(storage.prefix):
                    raise ValueError("Provider returned an out-of-namespace object")
                yield key[len(storage.prefix) :]
    else:
        raise ValueError("Unsupported operational storage listing")
