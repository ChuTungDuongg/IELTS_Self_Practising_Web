"""Authoritative storage selection; cloud errors never fall back to local."""

from functools import lru_cache

from app.core.config import Settings
from app.storage.base import AssetStorage
from app.storage.local import LocalAssetStorage


@lru_cache(maxsize=8)
def _cloud_storage(bucket, region, endpoint, prefix, access_key, secret_key, token):
    from app.storage.s3 import S3CompatibleStorage

    return S3CompatibleStorage.from_config(
        bucket=bucket,
        region=region,
        endpoint_url=endpoint or None,
        prefix=prefix,
        access_key_id=access_key,
        secret_access_key=secret_key,
        session_token=token,
    )


def get_asset_storage(settings: Settings) -> AssetStorage:
    backend = getattr(settings, "storage_backend", "local")
    if backend == "local":
        return LocalAssetStorage(settings.resolved_storage_root)
    if backend not in {"s3", "r2"}:
        raise ValueError("Unsupported STORAGE_BACKEND")
    # Validate even callers using model_construct/copy without normal Settings validation.
    validated = Settings.model_validate(settings.model_dump())
    credentials = [
        value.get_secret_value() if value and value.get_secret_value() else None
        for value in (
            validated.aws_access_key_id,
            validated.aws_secret_access_key,
            validated.aws_session_token,
        )
    ]
    return _cloud_storage(
        validated.s3_bucket,
        validated.s3_region,
        validated.s3_endpoint_url,
        validated.s3_key_prefix,
        *credentials,
    )


def initialize_asset_storage(settings: Settings) -> AssetStorage:
    storage = get_asset_storage(settings)
    if settings.storage_backend == "local":
        for directory in ("audio", "images"):
            (settings.resolved_storage_root / directory).mkdir(parents=True, exist_ok=True)
    return storage
