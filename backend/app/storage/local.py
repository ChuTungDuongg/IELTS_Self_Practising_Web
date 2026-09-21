import shutil
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
        "audio/x-m4a": ".m4a",
        "audio/aac": ".aac",
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
        destination, relative_path = self._destination(
            category=category,
            mime_type=mime_type,
            original_name=original_name,
            size=len(content),
            max_bytes=max_bytes,
        )
        destination.write_bytes(content)
        return StoredAsset(relative_path=relative_path, size=len(content))

    def store_file(
        self,
        *,
        category: str,
        mime_type: str,
        original_name: str,
        source: Path,
        max_bytes: int,
    ) -> StoredAsset:
        size = source.stat().st_size
        destination, relative_path = self._destination(
            category=category,
            mime_type=mime_type,
            original_name=original_name,
            size=size,
            max_bytes=max_bytes,
        )
        try:
            with source.open("rb") as input_file, destination.open("xb") as output_file:
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return StoredAsset(relative_path=relative_path, size=size)

    def _destination(
        self, *, category: str, mime_type: str, original_name: str, size: int, max_bytes: int
    ) -> tuple[Path, str]:
        allowed = self.IMAGE_TYPES if category == "images" else self.AUDIO_TYPES
        extension = allowed.get(mime_type)
        supplied_extension = Path(original_name).suffix.lower()
        compatible_extensions = {extension} if extension != ".jpg" else {".jpg", ".jpeg"}
        if (
            extension is None
            or supplied_extension not in compatible_extensions
            or size <= 0
            or size > max_bytes
        ):
            raise AppError(
                "ASSET_UPLOAD_INVALID", "The uploaded file type or size is invalid.", 422
            )
        directory = (self.root / category).resolve()
        if self.root not in directory.parents:
            raise AppError("ASSET_UPLOAD_INVALID", "Invalid storage destination.", 422)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}{extension}"
        return directory / filename, f"{category}/{filename}"

    def resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if self.root not in candidate.parents or not candidate.is_file():
            raise AppError("ASSET_NOT_FOUND", "The asset file does not exist.", 404)
        return candidate

    def delete(self, relative_path: str) -> bool:
        candidate = (self.root / relative_path).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise AppError("ASSET_DELETE_INVALID", "Invalid storage path.", 422)
        if not candidate.exists():
            return False
        if not candidate.is_file():
            raise AppError("ASSET_DELETE_INVALID", "The storage path is not a file.", 422)
        candidate.unlink()
        return True
