import hashlib
import zipfile
from contextlib import contextmanager
from io import BytesIO
from uuid import UUID

import pytest

from app.core.exceptions import AppError
from app.services.transfer import TransferService


def test_zip_asset_is_read_via_port_and_named_by_content_digest(tmp_path):
    class Storage:
        @contextmanager
        def open_reader(self, key):
            assert key == "images/example.png"
            yield BytesIO(b"synthetic image")

    service = TransferService.__new__(TransferService)
    service.storage = Storage()
    asset_id = UUID("00000000-0000-0000-0000-000000000001")
    with zipfile.ZipFile(tmp_path / "bundle.zip", "w") as archive:
        name, size, digest = service._archive_asset(
            archive, "images/example.png", asset_id, ".png", 100
        )
    assert digest == hashlib.sha256(b"synthetic image").hexdigest()
    assert size == 15
    assert name == f"assets/{digest}-{asset_id.hex}.png"
    with zipfile.ZipFile(tmp_path / "bundle.zip") as archive:
        assert archive.read(name) == b"synthetic image"


def test_zip_asset_rejects_oversize_data(tmp_path):
    class Storage:
        @contextmanager
        def open_reader(self, _key):
            yield BytesIO(b"123456")

    service = TransferService.__new__(TransferService)
    service.storage = Storage()
    with zipfile.ZipFile(tmp_path / "bundle.zip", "w") as archive:
        with pytest.raises(AppError):
            service._archive_asset(archive, "images/example.png", UUID(int=1), ".png", 5)
        assert not archive.namelist()
