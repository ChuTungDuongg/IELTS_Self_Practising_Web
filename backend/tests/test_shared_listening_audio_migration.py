import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest


def load_migration_module():
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260919_0004_shared_listening_audio.py"
    )
    spec = importlib.util.spec_from_file_location("shared_listening_audio_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_audio_migration_resolves_null_one_and_repeated_assets() -> None:
    migration = load_migration_module()
    audio_id = uuid4()

    assert migration._resolve_legacy_audio_ids([None, None, None, None]) is None
    assert migration._resolve_legacy_audio_ids([None, audio_id, None, None]) == audio_id
    assert migration._resolve_legacy_audio_ids([audio_id, audio_id, None, audio_id]) == audio_id


def test_legacy_audio_migration_rejects_conflicting_assets() -> None:
    migration = load_migration_module()

    with pytest.raises(RuntimeError, match="multiple distinct audio assets"):
        migration._resolve_legacy_audio_ids([uuid4(), uuid4()])
