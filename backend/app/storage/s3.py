"""Private, S3-compatible primitives. Client injection permits offline tests."""

import tempfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.exceptions import AppError
from app.providers.writing_llm.base import ImagePart
from app.storage.base import StoredObjectInfo
from app.storage.keys import validate_key
from app.storage.local import LocalAssetStorage, StoredAsset


def _error_code(error: Exception) -> str:
    response = getattr(error, "response", {})
    return str(response.get("Error", {}).get("Code", ""))


class S3CompatibleStorage:
    def __init__(self, *, client, bucket: str, prefix: str = "") -> None:
        if not bucket or not bucket.strip():
            raise ValueError("S3 bucket is required")
        self.client = client
        self.bucket = bucket
        self.prefix = validate_key(prefix) + "/" if prefix else ""

    @classmethod
    def from_config(
        cls,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        prefix: str = "",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
    ):
        if not bucket or not region:
            raise ValueError("S3 bucket and region are required")
        if bool(access_key_id) != bool(secret_access_key) or (session_token and not access_key_id):
            raise ValueError("Explicit S3 credentials must include both access and secret keys")
        # Client construction does not contact an object bucket. If explicit credentials
        # are absent boto3 uses the standard AWS provider chain, including IAM roles.
        import boto3
        from botocore.config import Config

        kwargs = {
            "region_name": region,
            "endpoint_url": endpoint_url,
            "config": Config(
                connect_timeout=5, read_timeout=60, retries={"mode": "standard", "max_attempts": 3}
            ),
        }
        if access_key_id:
            kwargs.update(
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                aws_session_token=session_token,
            )
        return cls(client=boto3.client("s3", **kwargs), bucket=bucket, prefix=prefix)

    def _key(self, key: str) -> str:
        return self.prefix + validate_key(key)

    def put_stream(self, key: str, source: BinaryIO, *, content_type: str, max_bytes: int) -> int:
        object_key = self._key(key)
        size = 0
        # A seekable, disk-backed body permits bounded uploads without buffering audio in RAM.
        with tempfile.TemporaryFile(mode="w+b") as staged:
            while chunk := source.read(min(1024 * 1024, max_bytes - size + 1)):
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(
                        "ASSET_UPLOAD_INVALID", "The uploaded file size is invalid.", 422
                    )
                staged.write(chunk)
            if not size:
                raise AppError("ASSET_UPLOAD_INVALID", "The uploaded file size is invalid.", 422)
            staged.seek(0)
            try:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=object_key,
                    Body=staged,
                    ContentType=content_type,
                    IfNoneMatch="*",
                )
            except Exception as error:
                if _error_code(error) in {
                    "PreconditionFailed",
                    "412",
                    "ConditionalRequestConflict",
                    "409",
                }:
                    raise FileExistsError(key) from error
                raise
        return size

    def store_stream(self, *, category, mime_type, original_name, source, max_bytes):
        if category not in {"images", "audio"}:
            raise AppError("ASSET_UPLOAD_INVALID", "Invalid storage destination.", 422)
        allowed = (
            LocalAssetStorage.IMAGE_TYPES if category == "images" else LocalAssetStorage.AUDIO_TYPES
        )
        extension = LocalAssetStorage._validate_upload(
            allowed, mime_type, original_name, 1, max_bytes
        )
        key = f"{category}/{uuid4().hex}{extension}"
        size = self.put_stream(key, source, content_type=mime_type, max_bytes=max_bytes)
        return StoredAsset(relative_path=key, size=size)

    def store_file(self, *, category, mime_type, original_name, source, max_bytes):
        with source.open("rb") as reader:
            return self.store_stream(
                category=category,
                mime_type=mime_type,
                original_name=original_name,
                source=reader,
                max_bytes=max_bytes,
            )

    def store_private_speaking(self, content: bytes, mime_type: str, max_bytes: int):
        extension = {
            "audio/webm": ".webm",
            "audio/webm;codecs=opus": ".webm",
            "audio/mp4": ".m4a",
            "audio/ogg;codecs=opus": ".ogg",
        }.get(mime_type)
        if extension is None or not 0 < len(content) <= max_bytes:
            raise AppError("SPEAKING_UPLOAD_INVALID", "Invalid recording type or size.", 422)
        key = f"speaking-private/{uuid4().hex}{extension}"
        size = self.put_stream(key, BytesIO(content), content_type=mime_type, max_bytes=max_bytes)
        return StoredAsset(relative_path=key, size=size)

    def store_benchmark_writing_image(
        self, sample_id, mime_type, original_name, content, max_bytes
    ):
        maximum = min(max_bytes, 10 * 1024 * 1024)
        extension = LocalAssetStorage._validate_upload(
            LocalAssetStorage.IMAGE_TYPES, mime_type, original_name, len(content), maximum
        )
        try:
            ImagePart(mime_type, content)
        except ValueError:
            raise AppError(
                "ASSET_UPLOAD_INVALID", "The uploaded image signature is invalid.", 422
            ) from None
        key = f"benchmark/writing/task1/{sample_id}/{uuid4().hex}{extension}"
        size = self.put_stream(key, BytesIO(content), content_type=mime_type, max_bytes=maximum)
        return StoredAsset(relative_path=key, size=size)

    def stat(self, key: str) -> StoredObjectInfo:
        try:
            result = self.client.head_object(Bucket=self.bucket, Key=self._key(key))
        except Exception as error:
            if _error_code(error) in {"404", "NoSuchKey", "NotFound"}:
                raise AppError("ASSET_NOT_FOUND", "The asset file does not exist.", 404) from error
            raise
        return StoredObjectInfo(
            size=result["ContentLength"], content_type=result.get("ContentType")
        )

    def exists(self, key: str) -> bool:
        try:
            self.stat(key)
        except AppError as error:
            if error.code == "ASSET_NOT_FOUND":
                return False
            raise
        return True

    @contextmanager
    def open_reader(self, key: str, *, start: int = 0, end: int | None = None):
        if start < 0 or (end is not None and end < start):
            raise ValueError("Invalid byte range")
        kwargs = {"Bucket": self.bucket, "Key": self._key(key)}
        if start or end is not None:
            kwargs["Range"] = f"bytes={start}-{end if end is not None else ''}"
        try:
            result = self.client.get_object(**kwargs)
        except Exception as error:
            if _error_code(error) in {"404", "NoSuchKey", "NotFound"}:
                raise AppError("ASSET_NOT_FOUND", "The asset file does not exist.", 404) from error
            raise
        try:
            yield result["Body"]
        finally:
            result["Body"].close()

    def delete(self, key: str) -> bool:
        if not self.exists(key):
            return False
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))
        return True

    @contextmanager
    def materialize(self, key: str, *, max_bytes: int):
        if self.stat(key).size > max_bytes:
            raise AppError("ASSET_SIZE_INVALID", "The asset exceeds the allowed size.", 422)
        with tempfile.TemporaryDirectory(prefix="bandpilot-asset-") as directory:
            path = Path(directory) / "asset"
            size = 0
            with self.open_reader(key) as source, path.open("xb") as output:
                while chunk := source.read(min(1024 * 1024, max_bytes - size + 1)):
                    size += len(chunk)
                    if size > max_bytes:
                        raise AppError(
                            "ASSET_SIZE_INVALID", "The asset exceeds the allowed size.", 422
                        )
                    output.write(chunk)
            yield path
