from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from app.models.enums import AssetType
from app.services import task1_input


async def test_task1_image_reads_through_storage_port(monkeypatch):
    version_id = uuid4()
    content = b"\x89PNG\r\n\x1a\nfictional-chart"
    asset = SimpleNamespace(
        test_version_id=version_id,
        asset_type=AssetType.WRITING_TASK_IMAGE,
        mime_type="image/png",
        file_size=len(content),
        relative_path="images/chart.png",
    )

    class Session:
        async def get(self, _model, _id):
            return asset

    class Port:
        @contextmanager
        def open_reader(self, key):
            assert key == "images/chart.png"
            yield BytesIO(content)

    monkeypatch.setattr(task1_input, "get_asset_storage", lambda _settings: Port())
    image = await task1_input.load_task1_image(
        Session(),
        SimpleNamespace(image_asset_id=uuid4()),
        version_id,
        SimpleNamespace(max_image_upload_mb=10),
    )
    assert image.data == content
    assert image.mime_type == "image/png"
