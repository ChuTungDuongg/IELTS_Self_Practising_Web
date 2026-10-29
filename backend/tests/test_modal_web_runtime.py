import hashlib
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

source = Path(__file__).resolve().parents[2] / "deploy/modal/web_runtime.py"
spec = importlib.util.spec_from_file_location("ielts_web_runtime", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_opt_in_nginx_timing_format_contains_no_private_request_data():
    source = (Path(__file__).resolve().parents[2] / "deploy/modal/nginx.conf").read_text()
    enabled = module.nginx_config_with_timings(source)
    assert "access_log off;" in source
    assert "access_log /dev/stdout timing;" in enabled
    assert "request_s=$request_time" in enabled
    assert "upstream_s=$upstream_response_time" in enabled
    assert "connect_s=$upstream_connect_time" in enabled
    assert all(
        field not in enabled
        for field in (
            "$request_uri",
            "$args",
            "$http_cookie",
            "$http_authorization",
            "$remote_addr",
        )
    )
    assert enabled.count("proxy_set_header X-Request-ID $request_id;") == 2
    restored = enabled.replace(
        enabled[enabled.index("    log_format timing") : enabled.index("    server {")],
        "    access_log off;\n",
    )
    restored = restored.replace("\n            proxy_set_header X-Request-ID $request_id;", "")
    assert restored == source


def test_timing_config_refuses_unexpected_source():
    with pytest.raises(RuntimeError):
        module.nginx_config_with_timings("http {}")


@pytest.fixture(autouse=True)
def isolated_runtime_environment():
    # Runtime helpers write os.environ directly, outside monkeypatch's bookkeeping.
    with patch.dict(os.environ):
        yield


def test_speaking_asr_uses_hydrated_backend_only_url_and_pinned_identity(monkeypatch):
    import os

    for name in (
        "SPEAKING_ASR_ENABLED",
        "SPEAKING_ASR_PROVIDER",
        "SPEAKING_ASR_BASE_URL",
        "SPEAKING_ASR_MODEL",
        "SPEAKING_ASR_MODEL_REVISION",
        "SPEAKING_ASR_VERSION",
        "SPEAKING_ASR_LANGUAGE",
        "SPEAKING_PROCESSING_TIMEOUT_SECONDS",
    ):
        monkeypatch.setenv(name, "__placeholder__")
    module.configure_speaking_asr_environment(
        True,
        "Systran/faster-whisper-large-v3",
        "pinned-revision",
        "service-v1",
        "https://fictional-asr.modal.run/",
    )
    assert os.environ["SPEAKING_ASR_PROVIDER"] == "modal"
    assert os.environ["SPEAKING_ASR_BASE_URL"] == "https://fictional-asr.modal.run"
    assert os.environ["SPEAKING_ASR_MODEL_REVISION"] == "pinned-revision"
    assert os.environ["SPEAKING_ASR_VERSION"] == "service-v1"
    assert os.environ["SPEAKING_ASR_LANGUAGE"] == "en"
    assert os.environ["SPEAKING_PROCESSING_TIMEOUT_SECONDS"] == "600"
    assert "AI_WRITING_MODAL_SECRET" not in os.environ["SPEAKING_ASR_BASE_URL"]
    module.configure_speaking_asr_environment(False, "unused", "unused", "unused", None)
    assert os.environ["SPEAKING_ASR_ENABLED"] == "false"


def test_chart_configuration_uses_hydrated_backend_only_url(monkeypatch):
    import os

    for key in [
        "AI_WRITING_CHART_SPECIALIST_ENABLED",
        "AI_WRITING_DEPLOT_MODEL",
        "AI_WRITING_DEPLOT_REVISION",
        "AI_WRITING_DEPLOT_BASE_URL",
        "AI_WRITING_CHART_SPECIALIST_PROVIDER",
    ]:
        monkeypatch.delenv(key, raising=False)
    module.configure_chart_environment(True, "google/deplot", "pinned", "https://chart.modal.run/")
    assert os.environ["AI_WRITING_DEPLOT_BASE_URL"] == "https://chart.modal.run"
    assert os.environ["AI_WRITING_DEPLOT_REVISION"] == "pinned"
    module.configure_chart_environment(False, "google/deplot", "pinned", None)
    assert os.environ["AI_WRITING_CHART_SPECIALIST_ENABLED"] == "false"


def runtime_at(tmp_path, monkeypatch, snapshot="seed/database.dump"):
    runtime = module.WebRuntime()
    runtime.database_root = tmp_path / "database"
    runtime.pgdata = runtime.database_root / "pgdata"
    runtime.snapshot_root = tmp_path / "snapshots"
    runtime.snapshot_root.mkdir()
    runtime.pgdata.mkdir(parents=True)
    monkeypatch.setenv("IELTS_SEED_SNAPSHOT", snapshot)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    calls = []

    def command(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "initdb":
            (runtime.pgdata / "PG_VERSION").write_text("17")
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


def test_snapshot_seed_never_overwrites_an_existing_database(tmp_path, monkeypatch):
    runtime, calls = runtime_at(tmp_path, monkeypatch)
    (runtime.pgdata / "PG_VERSION").write_text("17")
    write_snapshot(runtime.snapshot_root)
    with pytest.raises(RuntimeError, match="Refusing to seed an existing"):
        runtime.start_postgres()
    assert not any(args[0] in {"pg_restore", "initdb"} for args, _ in calls)


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
    assert os.environ["SPEAKING_AI_ENABLED"] == "false"
    module.configure_ai_environment(True, "bundled-model", "https://unused.example")
    assert os.environ["AI_WRITING_OPENAI_MODEL"] == "account-model"


def test_modal_ai_enables_speaking_on_shared_ministral_transport(monkeypatch):
    from app.core.config import Settings
    from app.providers.speaking_llm import create_provider, provider_identity
    from app.providers.writing_llm.vllm import VLLMProvider

    model = "mistralai/Ministral-3-8B-Instruct-2512"
    monkeypatch.setenv("AI_WRITING_PROVIDER", "vllm")
    monkeypatch.setenv("AI_WRITING_MODAL_KEY", "private-key")
    monkeypatch.setenv("AI_WRITING_MODAL_SECRET", "private-secret")
    monkeypatch.setenv("SPEAKING_AI_ENABLED", "false")  # Stale Secret must not disable it.
    monkeypatch.delenv("SPEAKING_AI_PROVIDER", raising=False)
    monkeypatch.delenv("SPEAKING_AI_MODEL", raising=False)
    module.configure_ai_environment(True, model, "https://fictional.modal.run")
    settings = Settings(_env_file=None)

    assert settings.ai_writing_enabled and settings.speaking_ai_enabled
    assert provider_identity(settings) == ("vllm", model)
    assert isinstance(create_provider(settings).delegate, VLLMProvider)
    assert settings.ai_writing_vllm_base_url == "https://fictional.modal.run/v1"
    summary = module.safe_ai_configuration()
    assert summary["speaking_ai_enabled"] and summary["speaking_ai_configured"]
    assert summary["speaking_provider"] == "vllm" and summary["speaking_model"] == model
    assert summary["writing_vllm_transport_url_configured"]
    assert "private-key" not in json.dumps(summary)
    assert "private-secret" not in json.dumps(summary)
    assert "fictional.modal.run" not in json.dumps(summary)


def test_modal_ai_overrides_and_asr_remain_independent(monkeypatch):
    from app.core.config import Settings
    from app.providers.speaking_llm import create_provider, provider_identity
    from app.providers.writing_llm.openai import OpenAIProvider

    monkeypatch.setenv("AI_WRITING_PROVIDER", "vllm")
    monkeypatch.setenv("SPEAKING_AI_PROVIDER", "openai")
    monkeypatch.setenv("SPEAKING_AI_MODEL", "independent-model")
    monkeypatch.setenv("AI_WRITING_OPENAI_API_KEY", "fixture-key")
    monkeypatch.setenv("SPEAKING_ASR_ENABLED", "true")
    monkeypatch.setenv("SPEAKING_ASR_PROVIDER", "modal")
    module.configure_ai_environment(True, "bundled-model", "https://fictional.modal.run")
    settings = Settings(_env_file=None)
    assert provider_identity(settings) == ("openai", "independent-model")
    assert isinstance(create_provider(settings).delegate, OpenAIProvider)
    assert settings.speaking_asr_enabled and settings.speaking_asr_provider == "modal"
    module.configure_ai_environment(False, "bundled-model", None)
    disabled = Settings(_env_file=None)
    assert not disabled.speaking_ai_enabled and disabled.speaking_asr_enabled


def test_safe_config_probe_failure_never_blocks_web_startup(monkeypatch):
    import subprocess

    def unavailable(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("python", 15)

    monkeypatch.setattr(module.subprocess, "run", unavailable)
    assert module.safe_ai_configuration() == {"inspection": "unavailable"}


def test_external_database_can_disable_automatic_migration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fictional/example")
    monkeypatch.setenv("IELTS_AUTO_MIGRATE", "false")
    monkeypatch.setenv("STORAGE_ROOT", "/operator-storage")
    runtime = module.WebRuntime()
    commands = []
    monkeypatch.setattr(
        runtime, "start_postgres", lambda: pytest.fail("must use external database")
    )
    monkeypatch.setattr(runtime, "command", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr(runtime, "wait_http", lambda _url: None)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: object())
    runtime.start()
    assert not any("alembic" in command for command in commands)
    assert os.environ["STORAGE_ROOT"] == "/operator-storage"
    assert os.environ["DATABASE_URL"] == "postgresql+asyncpg://fictional/example"


def test_invalid_migration_mode_fails_before_starting_processes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fictional/example")
    monkeypatch.setenv("IELTS_AUTO_MIGRATE", "unexpected")
    runtime = module.WebRuntime()
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("started")
    )
    with pytest.raises(RuntimeError, match="IELTS_AUTO_MIGRATE"):
        runtime.start()


def test_demo_keeps_automatic_migration_and_default_storage(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("IELTS_AUTO_MIGRATE", raising=False)
    monkeypatch.delenv("STORAGE_ROOT", raising=False)
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    runtime = module.WebRuntime()
    commands = []
    monkeypatch.setattr(runtime, "start_postgres", lambda: None)
    monkeypatch.setattr(runtime, "command", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr(runtime, "wait_http", lambda _url: None)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: object())
    runtime.start()
    assert ["python", "-m", "alembic", "upgrade", "head"] in commands
    assert os.environ["STORAGE_ROOT"] == "/storage"


def test_external_database_defaults_to_operator_controlled_migrations(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fictional/example")
    monkeypatch.delenv("IELTS_AUTO_MIGRATE", raising=False)
    runtime = module.WebRuntime()
    commands = []
    monkeypatch.setattr(runtime, "command", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr(runtime, "start_postgres", lambda: pytest.fail("started embedded database"))
    monkeypatch.setattr(runtime, "wait_http", lambda _url: None)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: object())
    runtime.start()
    assert not any("alembic" in command for command in commands)


@pytest.mark.parametrize("backend", ["s3", "r2"])
def test_cloud_runtime_preserves_storage_and_requires_no_local_database(backend, monkeypatch):
    from test_deployment_profiles import cloud_environment

    for name, value in cloud_environment(backend).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("IELTS_MODAL_STORAGE_BACKEND", backend)
    monkeypatch.setenv("IELTS_MODAL_DATABASE_MODE", "external")
    monkeypatch.setenv("STORAGE_ROOT", "/operator-unused-root")
    runtime = module.WebRuntime()
    commands, waited = [], []
    monkeypatch.setattr(runtime, "start_postgres", lambda: pytest.fail("started embedded database"))
    monkeypatch.setattr(runtime, "command", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr(runtime, "wait_http", waited.append)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: object())
    runtime.start()
    assert os.environ["STORAGE_BACKEND"] == backend
    assert os.environ["STORAGE_ROOT"] == "/operator-unused-root"
    assert not any("alembic" in command for command in commands)
    assert "http://127.0.0.1:9001/api/v1/ready" in waited


def test_cloud_runtime_rejects_topology_mismatch_before_any_command(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("IELTS_MODAL_STORAGE_BACKEND", "r2")
    runtime = module.WebRuntime()
    monkeypatch.setattr(runtime, "command", lambda *args, **kwargs: pytest.fail("ran a command"))
    with pytest.raises(RuntimeError, match="topology"):
        runtime.start()


def test_external_database_ca_is_temporary_and_never_contains_a_private_key(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fixture/database")
    monkeypatch.delenv("PGSSLROOTCERT", raising=False)
    monkeypatch.setenv(
        "IELTS_DATABASE_CA_PEM", "-----BEGIN CERTIFICATE-----\nfictional\n-----END CERTIFICATE-----"
    )
    runtime = module.WebRuntime()
    runtime.prepare_database_ca()
    path = runtime.database_ca_path
    assert path.read_text().startswith("-----BEGIN CERTIFICATE-----")
    assert os.environ["PGSSLROOTCERT"] == str(path)
    runtime.stop()
    assert not path.exists() and "PGSSLROOTCERT" not in os.environ
    monkeypatch.setenv("IELTS_DATABASE_CA_PEM", "-----BEGIN PRIVATE KEY-----")
    with pytest.raises(RuntimeError, match="public database CA"):
        runtime.prepare_database_ca()


def test_next_and_nginx_processes_do_not_inherit_backend_secrets(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fixture/database")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "private-cloud-secret")
    monkeypatch.setenv("JWT_SECRET", "private-jwt-secret")
    monkeypatch.setenv("AI_WRITING_MODAL_SECRET", "private-proxy-secret")
    runtime = module.WebRuntime()
    calls = []
    monkeypatch.setattr(runtime, "command", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime, "wait_http", lambda *args: None)
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs))
    )
    runtime.start()
    node = next(options for args, options in calls if args[0] == "node")
    nginx = next(options for args, options in calls if args[0] == "nginx")
    assert node["env"]["API_INTERNAL_BASE_URL"] == "http://127.0.0.1:9001/api/v1"
    assert node["env"]["NEXT_PUBLIC_API_BASE_URL"] == "/api/v1"
    assert "private-" not in str(node["env"]) + str(nginx["env"])
    assert not any(
        key in node["env"] for key in ("DATABASE_URL", "JWT_SECRET", "AWS_SECRET_ACCESS_KEY")
    )
