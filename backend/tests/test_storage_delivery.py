from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.exceptions import AppError
from app.storage.base import StoredObjectInfo
from app.storage.delivery import storage_response


class Storage:
    def __init__(self):
        self.closed = False

    def stat(self, key):
        if key == "missing":
            raise AppError("ASSET_NOT_FOUND", "Not found", 404)
        if key == "failure":
            raise RuntimeError("private provider diagnostic")
        return StoredObjectInfo(size=6)

    @contextmanager
    def open_reader(self, key, *, start=0, end=None):
        try:
            yield BytesIO(b"abcdef"[start : end + 1 if end is not None else None])
        finally:
            self.closed = True


def app_for(storage):
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle_error(_request, error):
        from fastapi.responses import JSONResponse

        return JSONResponse({"code": error.code}, status_code=error.status_code)

    @app.get("/{key}")
    async def get_file(request: Request, key: str):
        return await storage_response(
            request, storage, key, media_type="audio/mpeg", filename="recording.mp3"
        )

    return app


def test_streams_full_and_single_byte_ranges():
    storage = Storage()
    with TestClient(app_for(storage)) as client:
        full = client.get("/asset")
        assert full.status_code == 200 and full.content == b"abcdef"
        assert full.headers["content-length"] == "6"
        assert storage.closed
        ranged = client.get("/asset", headers={"Range": "bytes=1-3"})
        assert ranged.status_code == 206 and ranged.content == b"bcd"
        assert ranged.headers["content-range"] == "bytes 1-3/6"
        assert client.get("/asset", headers={"Range": "bytes=-2"}).content == b"ef"
        bad = client.get("/asset", headers={"Range": "bytes=8-9"})
        assert bad.status_code == 416 and bad.headers["content-range"] == "bytes */6"


def test_missing_and_provider_failure_do_not_expose_diagnostics():
    with TestClient(app_for(Storage())) as client:
        assert client.get("/missing").status_code == 404
        response = client.get("/failure")
        assert response.status_code == 503
        assert "private provider diagnostic" not in response.text


def test_concatenated_chunks_support_ranges_across_boundaries():
    from app.storage.delivery import ConcatenatedStorage

    class Chunks:
        def stat(self, key):
            return StoredObjectInfo(size=len({"a": b"abc", "b": b"def"}[key]))

        @contextmanager
        def open_reader(self, key, *, start=0, end=None):
            data = {"a": b"abc", "b": b"def"}[key]
            yield BytesIO(data[start : end + 1 if end is not None else None])

    storage = ConcatenatedStorage(Chunks(), [("a", 3), ("b", 3)])
    with TestClient(app_for(storage)) as client:
        response = client.get("/asset", headers={"Range": "bytes=2-4"})
        assert response.status_code == 206
        assert response.content == b"cde"
        assert response.headers["content-range"] == "bytes 2-4/6"


async def test_asset_authorization_runs_before_storage_access(monkeypatch):
    from app.api.v1 import assets
    from app.models.enums import UserRole

    class Session:
        async def scalar(self, _query):
            return SimpleNamespace(relative_path="images/private.png")

    async def deny(*_args, **_kwargs):
        return False

    def forbidden_storage(_settings):
        raise AssertionError("Storage must not be touched before authorization")

    monkeypatch.setattr(assets, "can_user_read_asset", deny)
    monkeypatch.setattr(assets, "get_asset_storage", forbidden_storage)
    with pytest.raises(AppError) as denied:
        await assets.get_asset_content(
            uuid4(), SimpleNamespace(), SimpleNamespace(role=UserRole.USER, id=uuid4()), Session()
        )
    assert denied.value.status_code == 404


async def test_classroom_authorization_precedes_storage_access(monkeypatch):
    from app.api.v1 import classroom_classwork

    class Service:
        def __init__(self, *_args):
            pass

        async def file(self, *_args):
            raise AppError("FORBIDDEN", "Forbidden", 403)

    def forbidden_storage(_settings):
        raise AssertionError("Storage must not be touched before authorization")

    monkeypatch.setattr(classroom_classwork, "ClassworkService", Service)
    monkeypatch.setattr(classroom_classwork, "get_asset_storage", forbidden_storage)
    with pytest.raises(AppError) as denied:
        await classroom_classwork.resource_file(
            uuid4(), uuid4(), object(), object(), False, object()
        )
    assert denied.value.status_code == 403


async def test_compensation_preserves_references_from_classroom_and_benchmark(monkeypatch):
    from unittest.mock import AsyncMock

    from app.services import asset_cleanup

    checked = []

    class Verification:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def scalars(self, statement):
            sql = str(statement)
            checked.append("classroom_resources" in sql and "writing_benchmark_samples" in sql)
            return ["images/shared.png"]

    monkeypatch.setattr(asset_cleanup, "AsyncSession", Verification)
    storage = SimpleNamespace(delete=AsyncMock())
    await asset_cleanup.compensate_files(
        SimpleNamespace(bind=object()), storage, ["images/shared.png"]
    )
    assert checked == [True]
    storage.delete.assert_not_called()
