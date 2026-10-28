from contextlib import asynccontextmanager, contextmanager
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from starlette.requests import Request

from app.api.v1 import speaking
from app.storage.base import StoredObjectInfo


async def test_speaking_api_streams_authorized_chunk_keys(monkeypatch):
    class Port:
        def stat(self, key):
            return StoredObjectInfo(size=3)

        @contextmanager
        def open_reader(self, key, *, start=0, end=None):
            data = {"speaking-private/a.webm": b"abc", "speaking-private/b.webm": b"def"}[key]
            yield BytesIO(data[start : end + 1 if end is not None else None])

    class Service:
        def __init__(self, _session, _user):
            self.storage = Port()
            self.playback = AsyncMock(
                return_value=(
                    [("speaking-private/a.webm", 3), ("speaking-private/b.webm", 3)],
                    "audio/webm",
                )
            )

    monkeypatch.setattr(speaking, "SpeakingMediaService", Service)
    request = Request({"type": "http", "headers": []})
    response = await speaking.get_recording(uuid4(), uuid4(), request, object(), object())
    data = b"".join([chunk async for chunk in response.body_iterator])
    assert data == b"abcdef"
    assert response.headers["cache-control"] == "private, no-store"


async def test_speaking_playback_checks_keys_after_authorization(monkeypatch):
    from app.services import speaking_media

    @asynccontextmanager
    async def transaction():
        yield

    class Port:
        def __init__(self):
            self.visited = []

        def stat(self, key):
            self.visited.append(key)

    class Session:
        def begin(self):
            return transaction()

        async def get(self, _model, _id):
            return SimpleNamespace(user_id=uuid4())

    key = "speaking-private/a.webm"
    port = Port()
    service = speaking_media.SpeakingMediaService.__new__(speaking_media.SpeakingMediaService)
    service.session, service.storage = Session(), port
    service.actor = SimpleNamespace(id=uuid4())
    service._segment = AsyncMock(
        return_value=(
            SimpleNamespace(id=uuid4(), mime_type="audio/webm"),
            SimpleNamespace(take_number=1, status="COMMITTED"),
            SimpleNamespace(id=uuid4(), active_take_number=1),
        )
    )
    service._read_access = AsyncMock()
    service.runtime = SimpleNamespace(
        repository=SimpleNamespace(progress=AsyncMock(return_value=None))
    )
    monkeypatch.setattr(
        speaking_media,
        "ordered_chunks",
        AsyncMock(return_value=[SimpleNamespace(storage_key=key, byte_size=3)]),
    )
    keys, mime = await service.playback(uuid4(), uuid4())
    assert keys == [(key, 3)] and mime == "audio/webm" and port.visited == []
    service._read_access.assert_awaited_once()
