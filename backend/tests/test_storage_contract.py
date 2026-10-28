from io import BytesIO

import pytest

from app.core.exceptions import AppError
from app.storage import LocalAssetStorage


def test_local_port_stream_ranges_and_safe_duplicate(tmp_path):
    storage = LocalAssetStorage(tmp_path)
    storage.put_stream(
        "images/example.png", BytesIO(b"abcdef"), content_type="image/png", max_bytes=6
    )
    assert storage.stat("images/example.png").size == 6
    with storage.open_reader("images/example.png", start=2, end=4) as source:
        assert source.read() == b"cde"
    with pytest.raises(FileExistsError):
        storage.put_stream(
            "images/example.png", BytesIO(b"replacement"), content_type="image/png", max_bytes=20
        )
    with storage.open_reader("images/example.png") as source:
        assert source.read() == b"abcdef"
    assert storage.delete("images/example.png") is True
    assert storage.delete("images/example.png") is False


@pytest.mark.parametrize(
    "key",
    ["../escape", "/absolute", "images/../escape", "images\\escape", "images//x", "C:/outside"],
)
def test_local_port_rejects_unsafe_keys(tmp_path, key):
    storage = LocalAssetStorage(tmp_path)
    with pytest.raises(AppError):
        storage.put_stream(key, BytesIO(b"x"), content_type="image/png", max_bytes=10)


def test_local_port_removes_incomplete_upload(tmp_path):
    storage = LocalAssetStorage(tmp_path)
    with pytest.raises(AppError):
        storage.put_stream(
            "images/example.png", BytesIO(b"123456"), content_type="image/png", max_bytes=5
        )
    assert not (tmp_path / "images" / "example.png").exists()


def test_local_reader_preserves_existing_unicode_asset_names(tmp_path):
    path = tmp_path / "images" / "biểu đồ.png"
    path.parent.mkdir()
    path.write_bytes(b"chart")
    with LocalAssetStorage(tmp_path).open_reader("images/biểu đồ.png") as reader:
        assert reader.read() == b"chart"


class S3Failure(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, ContentType, ContentLength, IfNoneMatch):
        assert IfNoneMatch == "*"
        if (Bucket, Key) in self.objects:
            raise S3Failure("PreconditionFailed")
        data = Body.read()
        assert len(data) == ContentLength
        self.objects[Bucket, Key] = (data, ContentType)

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise S3Failure("404")
        data, mime = self.objects[Bucket, Key]
        return {"ContentLength": len(data), "ContentType": mime}

    def get_object(self, *, Bucket, Key, **kwargs):
        self.head_object(Bucket=Bucket, Key=Key)
        data = self.objects[Bucket, Key][0]
        if "Range" in kwargs:
            start, end = kwargs["Range"].removeprefix("bytes=").split("-")
            data = data[int(start) : int(end) + 1 if end else None]
        return {"Body": BytesIO(data)}

    def delete_object(self, *, Bucket, Key):
        del self.objects[Bucket, Key]


def test_s3_adapter_round_trip_and_range_without_cloud():
    from app.storage.s3 import S3CompatibleStorage

    storage = S3CompatibleStorage(client=FakeS3(), bucket="test", prefix="project")
    storage.put_stream("audio/test.mp3", BytesIO(b"abcdef"), content_type="audio/mpeg", max_bytes=6)
    assert storage.stat("audio/test.mp3").content_type == "audio/mpeg"
    with storage.open_reader("audio/test.mp3", start=1, end=3) as source:
        assert source.read() == b"bcd"
    with pytest.raises(FileExistsError):
        storage.put_stream(
            "audio/test.mp3", BytesIO(b"other"), content_type="audio/mpeg", max_bytes=6
        )
    assert storage.delete("audio/test.mp3") is True
    assert storage.delete("audio/test.mp3") is False


def test_s3_adapter_rejects_unsafe_and_oversize_without_upload():
    from app.storage.s3 import S3CompatibleStorage

    client = FakeS3()
    storage = S3CompatibleStorage(client=client, bucket="test")
    with pytest.raises(AppError):
        storage.put_stream("../escape", BytesIO(b"x"), content_type="image/png", max_bytes=1)
    with pytest.raises(AppError):
        storage.put_stream("images/x.png", BytesIO(b"large"), content_type="image/png", max_bytes=2)
    assert client.objects == {}


def test_materialized_s3_file_is_removed_after_use():
    from app.storage.s3 import S3CompatibleStorage

    storage = S3CompatibleStorage(client=FakeS3(), bucket="test")
    storage.put_stream("audio/test.mp3", BytesIO(b"abcdef"), content_type="audio/mpeg", max_bytes=6)
    with storage.materialize("audio/test.mp3", max_bytes=6) as path:
        assert path.read_bytes() == b"abcdef"
    assert not path.exists()
    with pytest.raises(AppError):
        with storage.materialize("audio/test.mp3", max_bytes=5):
            pass


def test_incomplete_cloud_backend_does_not_silently_use_local():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, storage_backend="s3")


def test_s3_missing_and_provider_failure_are_distinct():
    from app.storage.s3 import S3CompatibleStorage

    class UnavailableS3(FakeS3):
        def head_object(self, *, Bucket, Key):
            raise S3Failure("ServiceUnavailable")

    storage = S3CompatibleStorage(client=FakeS3(), bucket="test")
    assert not storage.exists("images/missing.png")
    with pytest.raises(AppError) as missing:
        storage.stat("images/missing.png")
    assert missing.value.code == "ASSET_NOT_FOUND"
    unavailable = S3CompatibleStorage(client=UnavailableS3(), bucket="test")
    with pytest.raises(AppError) as failure:
        unavailable.delete("images/missing.png")
    assert failure.value.code == "ASSET_STORAGE_UNAVAILABLE"


def test_s3_adapter_uses_sdk_and_propagates_private_object_metadata():
    from botocore.stub import ANY, Stubber

    from app.storage.s3 import S3CompatibleStorage

    storage = S3CompatibleStorage.from_config(
        bucket="fixture-bucket",
        region="auto",
        endpoint_url="https://example.invalid",
        access_key_id="fixture",
        secret_access_key="fixture-secret",
        prefix="development",
    )
    with Stubber(storage.client) as stubber:
        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": "fixture-bucket",
                "Key": "development/audio/example.mp3",
                "Body": ANY,
                "ContentType": "audio/mpeg",
                "ContentLength": 6,
                "IfNoneMatch": "*",
            },
        )
        stubber.add_response(
            "head_object",
            {"ContentLength": 6, "ContentType": "audio/mpeg"},
            {"Bucket": "fixture-bucket", "Key": "development/audio/example.mp3"},
        )
        assert (
            storage.put_stream(
                "audio/example.mp3", BytesIO(b"abcdef"), content_type="audio/mpeg", max_bytes=6
            )
            == 6
        )
        info = storage.stat("audio/example.mp3")
    assert info.size == 6
    assert info.content_type == "audio/mpeg"


def test_s3_adapter_rejects_partial_explicit_credentials():
    from app.storage.s3 import S3CompatibleStorage

    with pytest.raises(ValueError, match="credential"):
        S3CompatibleStorage.from_config(bucket="fixture", region="auto", access_key_id="fixture")


def test_s3_asset_upload_uses_existing_mime_validation_and_generated_key():
    from app.storage.s3 import S3CompatibleStorage

    storage = S3CompatibleStorage(client=FakeS3(), bucket="test")
    stored = storage.store_stream(
        category="images",
        mime_type="image/png",
        original_name="chart.png",
        source=BytesIO(b"fictional"),
        max_bytes=10,
    )
    assert stored.relative_path.startswith("images/")
    assert stored.size == 9
    with storage.open_reader(stored.relative_path) as reader:
        assert reader.read() == b"fictional"
    with pytest.raises(AppError):
        storage.store_stream(
            category="images",
            mime_type="image/png",
            original_name="malware.exe",
            source=BytesIO(b"fictional"),
            max_bytes=10,
        )


def test_s3_private_speaking_recording_is_stored_with_private_key():
    from app.storage.s3 import S3CompatibleStorage

    client = FakeS3()
    storage = S3CompatibleStorage(client=client, bucket="private")
    item = storage.store_private_speaking(b"chunk", "audio/webm", 10)
    assert item.relative_path.startswith("speaking-private/")
    with storage.open_reader(item.relative_path) as source:
        assert source.read() == b"chunk"
    with pytest.raises(AppError):
        storage.store_private_speaking(b"chunk", "text/plain", 10)


def test_s3_writing_benchmark_image_preserves_sample_namespace():
    from uuid import uuid4

    from app.storage.s3 import S3CompatibleStorage

    sample = uuid4()
    storage = S3CompatibleStorage(client=FakeS3(), bucket="private")
    content = b"\x89PNG\r\n\x1a\nfictional"
    item = storage.store_benchmark_writing_image(sample, "image/png", "chart.png", content, 100)
    assert item.relative_path.startswith(f"benchmark/writing/task1/{sample}/")
    with storage.open_reader(item.relative_path) as source:
        assert source.read() == content
