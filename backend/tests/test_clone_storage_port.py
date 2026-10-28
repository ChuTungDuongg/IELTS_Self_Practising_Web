from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from app.models import TestVersion as DomainVersion
from app.models.enums import AssetType
from app.services import tests as service_module
from app.storage.local import StoredAsset


def test_clone_referenced_audio_uses_storage_port(monkeypatch):
    source_id = uuid4()
    asset = SimpleNamespace(
        id=source_id,
        asset_type=AssetType.LISTENING_AUDIO,
        relative_path="audio/source.mp3",
        mime_type="audio/mpeg",
        original_name="source.mp3",
    )
    module = SimpleNamespace(audio_asset=asset, writing_tasks=[], question_groups=[])
    source = SimpleNamespace(modules=[module])
    target = DomainVersion()

    class Port:
        @contextmanager
        def open_reader(self, key):
            assert key == "audio/source.mp3"
            yield BytesIO(b"fictional")

        def store_stream(self, **kwargs):
            assert kwargs["source"].read() == b"fictional"
            return StoredAsset("audio/copy.mp3", 9)

    monkeypatch.setattr(
        service_module, "get_settings", lambda: SimpleNamespace(max_audio_upload_mb=1)
    )
    monkeypatch.setattr(service_module, "get_asset_storage", lambda settings: Port())
    created = []
    result = service_module.TestService._clone_referenced_assets(source, target, created)
    assert result[source_id].relative_path == "audio/copy.mp3"
    assert created == ["audio/copy.mp3"]
