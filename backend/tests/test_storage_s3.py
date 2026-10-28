import asyncio
import threading
from io import BytesIO

import pytest
from botocore.exceptions import ReadTimeoutError
from botocore.response import StreamingBody
from botocore.stub import Stubber
from test_storage_contract import FakeS3, S3Failure

from app.core.exceptions import AppError
from app.storage.s3 import S3CompatibleStorage
from app.storage.tasks import storage_io


def sdk_storage():
    return S3CompatibleStorage.from_config(
        bucket="private-fixture",
        region="auto",
        endpoint_url="https://fixture.r2.cloudflarestorage.com",
        access_key_id="fictional",
        secret_access_key="fictional-secret",
        prefix="dev",
    )


def test_sdk_range_metadata_unicode_and_stream_closure():
    storage = sdk_storage()
    raw = BytesIO(b"cde")
    body = StreamingBody(raw, 3)
    key = "audio/bản ghi.webm"
    with Stubber(storage.client) as stubber:
        stubber.add_response(
            "head_object",
            {"ContentLength": 6, "ContentType": "audio/webm"},
            {"Bucket": "private-fixture", "Key": "dev/" + key},
        )
        stubber.add_response(
            "get_object",
            {"Body": body, "ContentLength": 3, "ContentRange": "bytes 2-4/6"},
            {"Bucket": "private-fixture", "Key": "dev/" + key, "Range": "bytes=2-4"},
        )
        assert storage.stat(key).content_type == "audio/webm"
        with storage.open_reader(key, start=2, end=4) as reader:
            assert reader.read(2) == b"cd"
            assert reader.read(2) == b"e"
        assert raw.closed
        stubber.assert_no_pending_responses()


@pytest.mark.parametrize("operation", ["head_object", "get_object", "delete_object"])
def test_sdk_permission_failures_are_sanitized_and_not_missing(operation):
    storage = sdk_storage()
    with Stubber(storage.client) as stubber:
        if operation == "delete_object":
            stubber.add_response("head_object", {"ContentLength": 6})
        stubber.add_client_error(
            operation, "AccessDenied", "PRIVATE_DIAGNOSTIC", http_status_code=403
        )
        with pytest.raises(AppError) as error:
            if operation == "head_object":
                storage.exists("audio/x.webm")
            elif operation == "get_object":
                with storage.open_reader("audio/x.webm"):
                    pass
            else:
                storage.delete("audio/x.webm")
        assert error.value.code == "ASSET_STORAGE_CONFIGURATION_INVALID"
        assert "PRIVATE" not in str(error.value)


def test_sdk_get_missing_and_delete_success():
    storage = sdk_storage()
    with Stubber(storage.client) as stubber:
        stubber.add_client_error("get_object", "NoSuchKey", http_status_code=404)
        with pytest.raises(AppError) as error:
            with storage.open_reader("audio/absent.webm"):
                pass
        assert error.value.code == "ASSET_NOT_FOUND"
        stubber.add_response("head_object", {"ContentLength": 6})
        stubber.add_response("delete_object", {})
        assert storage.delete("audio/existing.webm")


def test_sdk_timeout_and_truncated_download_close_stream_without_corrupt_cache_classification():
    class Broken(BytesIO):
        def read(self, *args):
            raise ReadTimeoutError(endpoint_url="https://private.invalid")

    raw = Broken(b"audio")
    storage = sdk_storage()
    with Stubber(storage.client) as stubber:
        stubber.add_response("get_object", {"Body": StreamingBody(raw, 5), "ContentLength": 5})
        with pytest.raises(AppError) as error:
            with storage.open_reader("audio/broken.webm") as reader:
                reader.read(1)
        assert error.value.code == "ASSET_STORAGE_UNAVAILABLE" and raw.closed


def test_bounded_upload_and_materialization_cleanup_on_consumer_error():
    class Bounded(BytesIO):
        def read(self, amount=-1):
            assert 0 < amount <= 1024 * 1024
            return super().read(amount)

    storage = S3CompatibleStorage(client=FakeS3(), bucket="private")
    storage.put_stream("audio/x.webm", Bounded(b"audio"), content_type="audio/webm", max_bytes=5)
    with pytest.raises(RuntimeError):
        with storage.materialize("audio/x.webm", max_bytes=5) as path:
            assert path.read_bytes() == b"audio"
            raise RuntimeError("consumer failed")
    assert not path.exists()
    with pytest.raises(ValueError):
        storage.put_stream(
            "audio/no.webm", BytesIO(b"audio"), content_type="audio/webm", max_bytes=0
        )


async def test_storage_thread_finishes_and_records_key_before_cancellation_returns():
    started, finish = threading.Event(), threading.Event()
    keys = []

    def write():
        started.set()
        assert finish.wait(5)
        keys.append("audio/owned.webm")

    task = asyncio.create_task(storage_io(write))
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert keys == ["audio/owned.webm"]


def test_retryable_provider_error_preserves_object_and_never_becomes_missing():
    class Unavailable(FakeS3):
        def delete_object(self, **kwargs):
            raise S3Failure("ServiceUnavailable")

    client = Unavailable()
    storage = S3CompatibleStorage(client=client, bucket="private")
    storage.put_stream("audio/x.webm", BytesIO(b"audio"), content_type="audio/webm", max_bytes=5)
    with pytest.raises(AppError) as error:
        storage.delete("audio/x.webm")
    assert error.value.code == "ASSET_STORAGE_UNAVAILABLE"
    assert storage.exists("audio/x.webm")


async def test_cancel_during_remote_stream_open_closes_finished_stream():
    from contextlib import contextmanager

    from starlette.requests import Request

    from app.storage.base import StoredObjectInfo
    from app.storage.delivery import storage_response

    started, finish = threading.Event(), threading.Event()
    reader = BytesIO(b"audio")

    class SlowStorage:
        def stat(self, key):
            return StoredObjectInfo(size=5)

        @contextmanager
        def open_reader(self, key, **kwargs):
            started.set()
            assert finish.wait(5)
            try:
                yield reader
            finally:
                reader.close()

    request = Request({"type": "http", "headers": []})
    task = asyncio.create_task(
        storage_response(request, SlowStorage(), "audio", media_type="audio/webm")
    )
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert reader.closed
