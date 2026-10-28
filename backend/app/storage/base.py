"""Provider-neutral operations on opaque, private asset keys.

These synchronous operations must be called from a worker thread by async callers.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class StoredObjectInfo:
    size: int
    content_type: str | None = None


class AssetStorage(Protocol):
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
