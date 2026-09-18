from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.exceptions import AppError


@dataclass(frozen=True, slots=True)
class StoredAsset:
    relative_path: str
    size: int


class LocalAssetStorage:
    IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
    AUDIO_TYPES = {
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/ogg": ".ogg",
    }

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def store(
        self,
        *,
        category: str,
        mime_type: str,
        original_name: str,
        content: bytes,
        max_bytes: int,
    ) -> StoredAsset:
        allowed = self.IMAGE_TYPES if category == "images" else self.AUDIO_TYPES
        extension = allowed.get(mime_type)
        supplied_extension = Path(original_name).suffix.lower()
        compatible_extensions = {extension} if extension != ".jpg" else {".jpg", ".jpeg"}
        if (
            extension is None
            or supplied_extension not in compatible_extensions
            or not content
            or len(content) > max_bytes
        ):
            raise AppError(
                "ASSET_UPLOAD_INVALID", "The uploaded file type or size is invalid.", 422
            )
        directory = (self.root / category).resolve()
        if self.root not in directory.parents:
            raise AppError("ASSET_UPLOAD_INVALID", "Invalid storage destination.", 422)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}{extension}"
        destination = directory / filename
        destination.write_bytes(content)
        return StoredAsset(relative_path=f"{category}/{filename}", size=len(content))
