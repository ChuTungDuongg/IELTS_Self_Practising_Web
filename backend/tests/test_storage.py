from pathlib import Path

import pytest

from app.core.exceptions import AppError
from app.storage import LocalAssetStorage


def test_storage_generates_safe_name(tmp_path: Path) -> None:
    stored = LocalAssetStorage(tmp_path).store(
        category="images",
        mime_type="image/png",
        original_name="../../chart.png",
        content=b"not-a-real-image-but-safe-test-bytes",
        max_bytes=100,
    )
    assert stored.relative_path.startswith("images/")
    assert "chart" not in stored.relative_path
    assert (tmp_path / stored.relative_path).read_bytes().startswith(b"not-a-real")


def test_storage_rejects_mismatched_extension(tmp_path: Path) -> None:
    with pytest.raises(AppError) as caught:
        LocalAssetStorage(tmp_path).store(
            category="images",
            mime_type="image/png",
            original_name="malware.exe",
            content=b"payload",
            max_bytes=100,
        )
    assert caught.value.code == "ASSET_UPLOAD_INVALID"
