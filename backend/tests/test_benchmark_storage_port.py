from contextlib import contextmanager
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.services.writing_benchmark import load_owned_image


def test_benchmark_image_is_loaded_from_bounded_materialization(tmp_path):
    sample = uuid4()
    key = f"benchmark/writing/task1/{sample}/{'a' * 32}.png"
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfictional")

    class Port:
        @contextmanager
        def materialize(self, requested, *, max_bytes):
            assert requested == key and max_bytes == 10 * 1024 * 1024
            yield path

    assert load_owned_image(Port(), sample, key).mime_type == "image/png"
    with pytest.raises(AppError):
        load_owned_image(Port(), uuid4(), key)
