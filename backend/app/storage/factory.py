"""Storage selection remains local until every asset workflow is integrated."""

from app.core.config import Settings
from app.storage.local import LocalAssetStorage


def get_asset_storage(settings: Settings) -> LocalAssetStorage:
    if getattr(settings, "storage_backend", "local") != "local":
        raise ValueError("Cloud storage is not yet enabled for persistent asset workflows")
    return LocalAssetStorage(settings.resolved_storage_root)
