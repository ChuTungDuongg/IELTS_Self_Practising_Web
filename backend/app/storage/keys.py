"""Validation for provider-independent object keys."""

from app.core.exceptions import AppError


def validate_key(key: str) -> str:
    if (
        not isinstance(key, str)
        or not key
        or len(key) > 1024
        or any(
            part in {"", ".", ".."}
            or any(not char.isprintable() or char in '<>:"\\|?*' for char in part)
            for part in key.split("/")
        )
    ):
        raise AppError("ASSET_PATH_INVALID", "Invalid storage key.", 422)
    return key
