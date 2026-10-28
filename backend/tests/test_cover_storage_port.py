import base64
from contextlib import contextmanager
from io import BytesIO

import pytest

from app.services.test_covers import validate_stored_cover

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=="
)


def test_cover_validation_reads_bounded_bytes_through_port():
    class Storage:
        @contextmanager
        def open_reader(self, key):
            assert key == "images/cover.png"
            yield BytesIO(PNG)

    validate_stored_cover(Storage(), "images/cover.png", "image/png", len(PNG))
    with pytest.raises(ValueError):
        validate_stored_cover(Storage(), "images/cover.png", "image/png", len(PNG) - 1)
