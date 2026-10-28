"""Private, provider-neutral byte streaming after the caller authorizes access."""

import asyncio
import re
from contextlib import contextmanager
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from app.core.exceptions import AppError
from app.storage.base import StoredObjectInfo


class ConcatenatedStorage:
    """Read an authorized sequence of chunks as one bounded logical object."""

    def __init__(self, storage, chunks):
        self.storage, self.chunks = storage, chunks

    def stat(self, _key):
        for key, expected_size in self.chunks:
            if self.storage.stat(key).size != expected_size:
                raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "Recording data is invalid.", 409)
        return StoredObjectInfo(size=sum(size for _, size in self.chunks))

    @contextmanager
    def open_reader(self, _key, *, start=0, end=None):
        reader = _ChunkReader(self.storage, self.chunks, start, end)
        try:
            yield reader
        finally:
            reader.close()


class _ChunkReader:
    def __init__(self, storage, chunks, start, end):
        self.storage = storage
        self.remaining = []
        self.manager = self.source = None
        self.segment_left = 0
        offset = 0
        for key, size in chunks:
            lo = max(0, start - offset)
            hi = min(size - 1, end - offset) if end is not None else size - 1
            if lo <= hi:
                self.remaining.append((key, lo, hi))
            offset += size

    def read(self, maximum):
        result = bytearray()
        while len(result) < maximum:
            if self.source is None:
                if not self.remaining:
                    break
                key, start, end = self.remaining.pop(0)
                self.manager = self.storage.open_reader(key, start=start, end=end)
                self.source = self.manager.__enter__()
                self.segment_left = end - start + 1
            block = self.source.read(min(maximum - len(result), self.segment_left))
            if not block:
                raise OSError("Recording chunk ended unexpectedly")
            result.extend(block)
            self.segment_left -= len(block)
            if not self.segment_left:
                self.manager.__exit__(None, None, None)
                self.manager = self.source = None
        return bytes(result)

    def close(self):
        if self.manager is not None:
            self.manager.__exit__(None, None, None)
            self.manager = self.source = None


def _range(value: str, size: int):
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or not size:
        return None
    first, last = match.groups()
    if not first:
        if not last or int(last) <= 0:
            return None
        return max(0, size - int(last)), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        return None
    return start, end


async def storage_response(
    request: Request,
    storage,
    key: str,
    *,
    media_type: str,
    filename: str | None = None,
    disposition: str = "inline",
    headers: dict[str, str] | None = None,
):
    try:
        info = await asyncio.to_thread(storage.stat, key)
    except AppError as error:
        if error.code == "ASSET_NOT_FOUND":
            raise
        raise AppError("ASSET_STORAGE_UNAVAILABLE", "Asset storage is unavailable.", 503) from None
    except Exception:
        raise AppError("ASSET_STORAGE_UNAVAILABLE", "Asset storage is unavailable.", 503) from None
    output_headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        **(headers or {}),
    }
    if filename:
        output_headers["Content-Disposition"] = (
            f"{disposition}; filename*=utf-8''{quote(filename, safe='')}"
        )
    range_header = request.headers.get("range")
    selected = _range(range_header, info.size) if range_header else None
    if range_header and selected is None:
        return Response(
            status_code=416, headers={**output_headers, "Content-Range": f"bytes */{info.size}"}
        )
    start, end = selected if selected is not None else (0, None)
    length = end - start + 1 if end is not None else info.size
    output_headers["Content-Length"] = str(length)
    if selected is not None:
        output_headers["Content-Range"] = f"bytes {start}-{end}/{info.size}"
    manager = storage.open_reader(key, start=start, end=end)
    opening = asyncio.create_task(asyncio.to_thread(manager.__enter__))
    try:
        reader = await asyncio.shield(opening)
    except asyncio.CancelledError:
        outcome = (await asyncio.gather(opening, return_exceptions=True))[0]
        if not isinstance(outcome, BaseException):
            await asyncio.to_thread(manager.__exit__, None, None, None)
        raise
    except AppError as error:
        if error.code == "ASSET_NOT_FOUND":
            raise
        raise AppError("ASSET_STORAGE_UNAVAILABLE", "Asset storage is unavailable.", 503) from None
    except Exception:
        raise AppError("ASSET_STORAGE_UNAVAILABLE", "Asset storage is unavailable.", 503) from None
    closed = False

    def close():
        nonlocal closed
        if not closed:
            closed = True
            manager.__exit__(None, None, None)

    def content():
        try:
            remaining = length
            while remaining:
                data = reader.read(min(64 * 1024, remaining))
                if not data:
                    raise OSError("Asset stream ended before its declared size")
                remaining -= len(data)
                yield data
        finally:
            close()

    return StreamingResponse(
        content(),
        media_type=media_type,
        status_code=206 if selected else 200,
        headers=output_headers,
        background=BackgroundTask(close),
    )
