import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock


def test_existing_dump_requires_verified_digest_before_any_upload(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/modal_database_snapshot.py"
    spec = importlib.util.spec_from_file_location("snapshot_setup_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        module, "load_configuration", lambda: ("postgresql://fictional@localhost/source", tmp_path)
    )
    dump = tmp_path / "synthetic.dump"
    dump.write_bytes(b"fictional custom dump")
    calls = []

    def command(*args):
        calls.append(args)
        if args[:2] == ("volume", "list"):
            return json.dumps([{"name": "new-staging-snapshots"}])
        if args[:2] == ("volume", "get"):
            Path(args[-1]).write_bytes(dump.read_bytes())
        return ""

    monkeypatch.setattr(module, "modal_command", command)
    monkeypatch.setattr(module, "schema_version", AsyncMock(return_value="revision"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "snapshot",
            "--volume",
            "new-staging-snapshots",
            "--dump-file",
            str(dump),
            "--expected-sha256",
            "wrong",
        ],
    )
    assert module.main() == 1
    assert not calls
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "snapshot",
            "--volume",
            "new-staging-snapshots",
            "--dump-file",
            str(dump),
            "--expected-sha256",
            hashlib.sha256(dump.read_bytes()).hexdigest(),
        ],
    )
    assert module.main() == 0
    assert sum(args[:2] == ("volume", "put") for args in calls) == 2
