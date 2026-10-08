import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

source = Path(__file__).resolve().parents[2] / "deploy/modal/web_runtime.py"
spec = importlib.util.spec_from_file_location("ielts_web_runtime", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def runtime_at(tmp_path, monkeypatch, snapshot="seed/database.dump"):
    runtime = module.WebRuntime()
    runtime.database_root = tmp_path / "database"
    runtime.pgdata = runtime.database_root / "pgdata"
    runtime.snapshot_root = tmp_path / "snapshots"
    runtime.snapshot_root.mkdir()
    runtime.pgdata.mkdir(parents=True)
    (runtime.pgdata / "PG_VERSION").write_text("17")
    monkeypatch.setenv("IELTS_SEED_SNAPSHOT", snapshot)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    calls = []

    def command(args, **kwargs):
        calls.append((args, kwargs))
        return "1" if args[0] == "psql" else ""

    monkeypatch.setattr(runtime, "command", command)
    return runtime, calls


def write_snapshot(root, checksum=None):
    directory = root / "seed"
    directory.mkdir()
    dump = directory / "database.dump"
    dump.write_bytes(b"fictional PostgreSQL snapshot")
    (directory / "manifest.json").write_text(
        json.dumps({"database_sha256": checksum or hashlib.sha256(dump.read_bytes()).hexdigest()})
    )
    return dump


def test_restore_chowns_pgdata_and_uses_private_log(tmp_path, monkeypatch):
    runtime, calls = runtime_at(tmp_path, monkeypatch)
    write_snapshot(runtime.snapshot_root)
    runtime.start_postgres()
    assert calls[0][0] == ["chown", "-R", "postgres:postgres", str(runtime.pgdata)]
    pg_ctl = next(args for args, _ in calls if args[0] == "pg_ctl")
    assert pg_ctl[pg_ctl.index("-l") + 1] == str(runtime.pgdata / "postgres.log")
    assert any(args[0] == "pg_restore" for args, _ in calls)
    assert (runtime.database_root / "snapshot-restored").exists()
    calls.clear()
    runtime.start_postgres()
    assert not any(args[0] == "pg_restore" for args, _ in calls)


def test_restore_resolves_modal_volume_symlink(tmp_path, monkeypatch):
    runtime, calls = runtime_at(tmp_path, monkeypatch)
    actual = tmp_path / "actual-volume"
    runtime.snapshot_root.rename(actual)
    try:
        runtime.snapshot_root.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit symlink creation")
    dump = write_snapshot(actual)
    runtime.start_postgres()
    restore = next(args for args, _ in calls if args[0] == "pg_restore")
    assert restore[-1] == str(dump.resolve())


def test_restore_rejects_checksum_mismatch(tmp_path, monkeypatch):
    runtime, calls = runtime_at(tmp_path, monkeypatch)
    write_snapshot(runtime.snapshot_root, checksum="invalid")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        runtime.start_postgres()
    assert not any(args[0] == "pg_restore" for args, _ in calls)
    assert not (runtime.database_root / "snapshot-restored").exists()


def test_restore_rejects_path_outside_snapshot_volume(tmp_path, monkeypatch):
    runtime, calls = runtime_at(tmp_path, monkeypatch, "../outside/database.dump")
    with pytest.raises(RuntimeError, match="Invalid snapshot path"):
        runtime.start_postgres()
    assert not any(args[0] == "pg_restore" for args, _ in calls)


def test_bundled_model_url_overrides_old_secret_without_copying_secrets(monkeypatch):
    monkeypatch.setenv("AI_WRITING_PROVIDER", "vllm")
    monkeypatch.setenv("AI_WRITING_VLLM_BASE_URL", "https://old.example/v1")
    monkeypatch.setenv("AI_WRITING_VLLM_MODEL", "old-model")
    monkeypatch.setenv("AI_WRITING_MODAL_SECRET", "private-token")
    model = "mistralai/Ministral-3-8B-Instruct-2512"
    module.configure_ai_environment(True, model, "https://app--serve-dev.modal.run")
    import os

    assert os.environ["AI_WRITING_VLLM_BASE_URL"] == "https://app--serve-dev.modal.run/v1"
    assert os.environ["AI_WRITING_VLLM_MODEL"] == model
    assert os.environ["AI_WRITING_MODAL_SECRET"] == "private-token"


def test_web_only_is_disabled_and_external_openai_selection_is_preserved(monkeypatch):
    import os

    monkeypatch.setenv("AI_WRITING_ENABLED", "true")
    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    monkeypatch.setenv("AI_WRITING_OPENAI_MODEL", "account-model")
    module.configure_ai_environment(False, "bundled-model", None)
    assert os.environ["AI_WRITING_ENABLED"] == "false"
    module.configure_ai_environment(True, "bundled-model", "https://unused.example")
    assert os.environ["AI_WRITING_OPENAI_MODEL"] == "account-model"
