import importlib.util
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "migrate_asset_storage.py"
    spec = importlib.util.spec_from_file_location("storage_migration_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_explicit_local_storage_configuration_and_overlap(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("SOURCE_ENVIRONMENT", "development")
    monkeypatch.setenv("DESTINATION_ENVIRONMENT", "recovery")
    monkeypatch.setenv("SOURCE_STORAGE_ROOT", str(tmp_path / "source"))
    monkeypatch.setenv("DESTINATION_STORAGE_ROOT", str(tmp_path / "source" / "nested"))
    source = module.storage_from_environment("SOURCE", "local")
    destination = module.storage_from_environment("DESTINATION", "local")
    with pytest.raises(ValueError, match="overlap"):
        module.validate_distinct(source, destination)


def test_r2_configuration_requires_endpoint(monkeypatch):
    module = _module()
    monkeypatch.setenv("SOURCE_ENVIRONMENT", "development")
    monkeypatch.setenv("SOURCE_S3_BUCKET", "fixture")
    monkeypatch.setenv("SOURCE_S3_REGION", "auto")
    monkeypatch.delenv("SOURCE_S3_ENDPOINT_URL", raising=False)
    with pytest.raises(ValueError, match="endpoint"):
        module.storage_from_environment("SOURCE", "r2")
