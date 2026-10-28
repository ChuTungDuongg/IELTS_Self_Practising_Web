"""Provider-neutral operations on opaque, private asset keys.

These synchronous operations must be called from a worker thread by async callers.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from app.storage.local import StoredAsset


@dataclass(frozen=True, slots=True)
class StoredObjectInfo:
    size: int
    content_type: str | None = None


class AssetStorage(Protocol):
    def store_stream(
        self, *, category: str, mime_type: str, original_name: str, source: BinaryIO, max_bytes: int
    ) -> StoredAsset: ...

    def store_file(
        self, *, category: str, mime_type: str, original_name: str, source: Path, max_bytes: int
    ) -> StoredAsset: ...

    def store_private_speaking(
        self, content: bytes, mime_type: str, max_bytes: int
    ) -> StoredAsset: ...

    def store_benchmark_writing_image(
        self, sample_id: UUID, mime_type: str, original_name: str, content: bytes, max_bytes: int
    ) -> StoredAsset: ...

    def put_stream(
        self, key: str, source: BinaryIO, *, content_type: str, max_bytes: int
    ) -> int: ...

    def open_reader(
        self, key: str, *, start: int = 0, end: int | None = None
    ) -> AbstractContextManager[BinaryIO]: ...

    def stat(self, key: str) -> StoredObjectInfo: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> bool: ...

    def materialize(self, key: str, *, max_bytes: int) -> AbstractContextManager[Path]: ...
