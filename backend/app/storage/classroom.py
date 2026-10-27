"""Private, bounded lesson files using the existing local storage abstraction."""

import zipfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from app.core.exceptions import AppError
from app.storage.local import LocalAssetStorage, StoredAsset

MAX_RESOURCE_BYTES = 20 * 1024 * 1024
RESOURCE_TYPES = {
    **LocalAssetStorage.IMAGE_TYPES,
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


class ClassroomResourceStorage(LocalAssetStorage):
    def store_resource(
        self, source, filename: str, media_type: str, *, max_bytes=MAX_RESOURCE_BYTES
    ) -> StoredAsset:
        if (
            not filename
            or len(filename) > 255
            or any(c in filename for c in "/\\:")
            or filename in {".", ".."}
            or any(ord(c) < 32 for c in filename)
        ):
            raise AppError("RESOURCE_UPLOAD_INVALID", "Invalid filename.", 422)
        content = source.read(max_bytes + 1)
        extension = self._validate_upload(
            RESOURCE_TYPES, media_type, filename, len(content), max_bytes
        )
        self._signature(content, media_type)
        key = f"classroom-resources/{uuid4().hex}{extension}"
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise AppError("RESOURCE_UPLOAD_INVALID", "Invalid storage destination.", 422)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A collision never removes someone else's file.
        output = path.open("xb")
        try:
            with output:
                output.write(content)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return StoredAsset(relative_path=key, size=len(content))

    @staticmethod
    def _signature(content, media_type):
        try:
            if media_type.startswith("image/"):
                signatures = {
                    "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
                    "image/jpeg": content.startswith(b"\xff\xd8\xff"),
                    "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
                }
                if not signatures.get(media_type):
                    raise ValueError("Invalid image signature")
            elif media_type == "application/pdf":
                if not content.startswith(b"%PDF-"):
                    raise ValueError("Invalid PDF")
            elif media_type == "text/plain":
                if b"\x00" in content:
                    raise ValueError("Binary text")
                content.decode("utf-8")
            else:
                with zipfile.ZipFile(BytesIO(content)) as archive:
                    entries = archive.infolist()
                    names = {entry.filename for entry in entries}
                    if (
                        len(entries) > 2000
                        or sum(entry.file_size for entry in entries) > 50 * 1024 * 1024
                        or not {"[Content_Types].xml", "word/document.xml"} <= names
                    ):
                        raise ValueError("Invalid document")
                    if any(
                        "vba" in name.lower()
                        or ".." in Path(name).parts
                        or name.startswith(("/", "\\"))
                        for name in names
                    ):
                        raise ValueError("Unsafe document")
        except (ValueError, zipfile.BadZipFile, UnicodeDecodeError) as error:
            raise AppError(
                "RESOURCE_UPLOAD_INVALID", "The file content does not match a supported type.", 422
            ) from error
