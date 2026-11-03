"""Launch the existing Modal entry point with private, isolated AI configuration."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def setup_launcher(monkeypatch, tmp_path, *, credentials=True):
    path = ROOT / "scripts/modal_start.py"
    assert path.is_file(), "The one-command Modal launcher has not been implemented"
    spec = importlib.util.spec_from_file_location("modal_launcher_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "Settings",
        lambda **kwargs: SimpleNamespace(
            ai_writing_modal_key="fictional-proxy-key" if credentials else "",
            ai_writing_modal_secret="fictional-proxy-secret" if credentials else "",
        ),
    )
    monkeypatch.setattr(module.shutil, "which", lambda name: sys.executable)
    config = tmp_path / ".env.modal"
    config.write_text(
        "MODAL_PROFILE=tungduong156glis\n"
        "MODAL_ENVIRONMENT=main\n"
        "IELTS_MODAL_MODE=dev\n"
        "IELTS_MODAL_STORAGE_BACKEND=local\n"
        "IELTS_MODAL_DATABASE_MODE=embedded\n"
        "IELTS_MODAL_DATABASE_VOLUME=fictional-staging-database\n"
        "IELTS_MODAL_ASSETS_VOLUME=fictional-staging-assets\n"
        "IELTS_MODAL_SNAPSHOTS_VOLUME=fictional-staging-snapshots\n"
        "IELTS_MODAL_CONFIG_SECRET=fictional-staging-config\n",
        encoding="utf-8",
    )
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    return module, config, calls


def test_single_command_deploy_uses_isolated_resources_and_enables_private_ai(
    monkeypatch, tmp_path
):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path)
    monkeypatch.setenv("MODAL_PROFILE", "unrelated-profile")
    monkeypatch.setenv("IELTS_MODAL_MODE", "production")
    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    monkeypatch.setenv("AI_WRITING_OPENAI_API_KEY", "unrelated-private-key")
    assert launcher.main(["--config", str(config), "--deploy"]) == 0
    command, options = calls[0]
    assert command[1:] == ["deploy", "deploy/modal/app.py", "--strategy", "recreate"]
    environment = options["env"]
    assert environment["MODAL_PROFILE"] == "tungduong156glis"
    assert environment["IELTS_MODAL_MODE"] == "dev"
    assert environment["IELTS_MODAL_DATABASE_VOLUME"] == "fictional-staging-database"
    assert environment["IELTS_MODAL_ASSETS_VOLUME"] == "fictional-staging-assets"
    assert environment["IELTS_MODAL_CONFIG_SECRET"] == "fictional-staging-config"
    assert environment["IELTS_WEB_AI_ENABLED"] == "true"
    assert environment["IELTS_WEB_SPEAKING_ASR_ENABLED"] == "true"
    assert environment["AI_WRITING_PROVIDER"] == "vllm"
    assert environment["AI_WRITING_MODAL_SECRET"] == "fictional-proxy-secret"
    assert "AI_WRITING_OPENAI_API_KEY" not in environment
    assert environment["IELTS_WRITING_LLM_SCALEDOWN_SECONDS"] == "60"
    assert len(calls) == 1  # No inference/readiness request or profile mutation.


def test_check_is_offline_and_does_not_print_credentials(monkeypatch, tmp_path, capsys):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path)
    assert launcher.main(["--config", str(config), "--check"]) == 0
    assert calls == []
    output = capsys.readouterr().out
    assert "tungduong156glis" in output and "AI enabled" in output
    assert "fictional-proxy" not in output


def test_missing_proxy_credentials_fail_before_deployment(monkeypatch, tmp_path, capsys):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path, credentials=False)
    assert launcher.main(["--config", str(config)]) == 1
    assert calls == []
    assert "AI_WRITING_MODAL_KEY" in capsys.readouterr().err


@pytest.mark.parametrize(
    "old,new",
    [
        ("IELTS_MODAL_MODE=dev", "IELTS_MODAL_MODE=production"),
        ("fictional-staging-assets", "ielts-web-assets"),
        ("fictional-staging-database", "ielts-web-postgres"),
        ("fictional-staging-config", "ielts-web-config"),
    ],
)
def test_launcher_refuses_shared_or_production_resources(monkeypatch, tmp_path, old, new):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path)
    config.write_text(config.read_text().replace(old, new))
    assert launcher.main(["--config", str(config)]) == 1
    assert calls == []


def test_stop_uses_only_dev_app_and_needs_no_ai_credentials(monkeypatch, tmp_path):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path, credentials=False)
    assert launcher.main(["--config", str(config), "--stop"]) == 0
    assert calls[0][0][1:] == ["app", "stop", "ielts-practice-web-dev", "--yes", "--env", "main"]


def test_deployment_failure_is_returned_without_retry(monkeypatch, tmp_path):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path)
    monkeypatch.setattr(
        launcher.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=7)
    )
    assert launcher.main(["--config", str(config), "--deploy"]) == 7


def test_missing_config_never_deploys(monkeypatch, tmp_path):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path)
    config.unlink()
    assert launcher.main(["--config", str(config)]) == 1
    assert calls == []


def test_unassigned_config_value_fails_cleanly_without_cli(monkeypatch, tmp_path):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path)
    config.write_text(config.read_text().replace("MODAL_PROFILE=tungduong156glis", "MODAL_PROFILE"))
    assert launcher.main(["--config", str(config)]) == 1
    assert calls == []


@pytest.mark.parametrize("exit_code", [0, 7, 130])
def test_default_serve_inherits_ai_environment_and_preserves_exit_status(
    monkeypatch, tmp_path, exit_code
):
    launcher, config, calls = setup_launcher(monkeypatch, tmp_path)
    sessions = []

    class Process:
        def wait(self):
            return exit_code

    def popen(command, **kwargs):
        sessions.append((command, kwargs))
        return Process()

    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    assert launcher.main(["--config", str(config)]) == exit_code
    assert sessions, "Default startup still deploys instead of serving"
    command, options = sessions[0]
    assert command[1:] == ["serve", "deploy/modal/app.py"]
    assert options["env"]["IELTS_WEB_AI_ENABLED"] == "true"
    assert options["env"]["MODAL_PROFILE"] == "tungduong156glis"
    assert calls == []


def test_serve_allows_child_to_handle_ctrl_c_and_restores_parent_handler(monkeypatch, tmp_path):
    import signal

    launcher, config, _ = setup_launcher(monkeypatch, tmp_path)
    original = signal.getsignal(signal.SIGINT)
    received = []

    class Process:
        def wait(self):
            handler = signal.getsignal(signal.SIGINT)
            assert callable(handler) and handler is not original
            handler(signal.SIGINT, None)
            received.append(True)
            return 130

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: Process())
    assert launcher.main(["--config", str(config)]) == 130
    assert received == [True]
    assert signal.getsignal(signal.SIGINT) is original


def setup_openai_launcher(monkeypatch, tmp_path, **changes):
    from app.core.config import Settings

    launcher, config, calls = setup_launcher(monkeypatch, tmp_path, credentials=False)
    settings = Settings(
        _env_file=None,
        **{
            "ai_writing_openai_api_key": "fictional-local-openai-key",
            "ai_writing_modal_key": "",
            "ai_writing_modal_secret": "",
            "speaking_ai_model": None,
            **changes,
        },
    )
    monkeypatch.setattr(launcher, "Settings", lambda **kwargs: settings)

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(wait=lambda: 0)

    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    return launcher, config, calls


def test_openai_serve_forwards_private_local_settings_and_preserves_isolated_resources(
    monkeypatch, tmp_path, capsys
):
    from app.core.config import Settings
    from app.providers.writing_llm import is_configured

    launcher, config, calls = setup_openai_launcher(
        monkeypatch,
        tmp_path,
        ai_writing_openai_stage_overrides={"task1.scoring.ta": {"reasoning_effort": "high"}},
    )
    monkeypatch.setenv("AI_WRITING_OPENAI_API_KEY", "unrelated-inherited-key")
    assert launcher.main(["--config", str(config), "--provider", "openai", "--no-asr"]) == 0
    assert len(calls) == 1
    command, options = calls[0]
    assert command[1:] == ["serve", "deploy/modal/app.py"]
    environment = options["env"]
    assert environment["MODAL_PROFILE"] == "tungduong156glis"
    assert environment["IELTS_MODAL_CONFIG_SECRET"] == "fictional-staging-config"
    assert environment["IELTS_MODAL_DATABASE_VOLUME"] == "fictional-staging-database"
    assert environment["AI_WRITING_PROVIDER"] == "openai"
    assert environment["SPEAKING_AI_PROVIDER"] == "openai"
    assert environment["AI_WRITING_OPENAI_API_KEY"] == "fictional-local-openai-key"
    assert environment["AI_WRITING_OPENAI_MAX_OUTPUT_TOKENS"] == "32768"
    assert environment["IELTS_WEB_SPEAKING_ASR_ENABLED"] == "false"
    # Round-trip the real runtime settings without contacting Modal or OpenAI.
    for key, value in environment.items():
        if key.startswith(("AI_WRITING_", "SPEAKING_AI_")):
            monkeypatch.setenv(key, value)
    runtime = Settings(_env_file=None)
    assert is_configured(runtime)
    assert runtime.ai_writing_openai_stage_overrides["task1.scoring.ta"].reasoning_effort == "high"
    assert "fictional-local-openai-key" not in capsys.readouterr().out
    assert all("fictional-local-openai-key" not in item for item in command)


@pytest.mark.parametrize(
    "changes",
    [
        {"ai_writing_openai_api_key": ""},
        {"ai_writing_openai_max_output_tokens": 4096},
        {"ai_writing_openai_model": "unsupported-fictional-model"},
    ],
)
def test_invalid_openai_configuration_fails_offline_without_fallback(
    monkeypatch, tmp_path, capsys, changes
):
    launcher, config, calls = setup_openai_launcher(monkeypatch, tmp_path, **changes)
    assert launcher.main(["--config", str(config), "--provider", "openai", "--no-asr"]) == 1
    assert calls == []
    output = capsys.readouterr()
    assert "OpenAI" in output.err
    assert "fictional-local-openai-key" not in output.out + output.err


def test_openai_check_needs_no_proxy_credentials_and_starts_no_service(
    monkeypatch, tmp_path, capsys
):
    launcher, config, calls = setup_openai_launcher(monkeypatch, tmp_path)
    assert (
        launcher.main(["--config", str(config), "--provider", "openai", "--no-asr", "--check"]) == 0
    )
    assert calls == []
    output = capsys.readouterr().out
    assert "openai" in output.lower()
    assert "fictional-local-openai-key" not in output


def setup_hybrid_launcher(monkeypatch, tmp_path, **changes):
    import hashlib

    launcher, config, calls = setup_openai_launcher(
        monkeypatch,
        tmp_path,
        **{
            "speaking_azure_key": "fictional-azure-key",
            "speaking_azure_region": "southeastasia",
            **changes,
        },
    )
    model = tmp_path / "silero.onnx"
    model.write_bytes(b"fictional-pinned-model")
    monkeypatch.setattr(
        launcher, "VAD_SHA256", hashlib.sha256(model.read_bytes()).hexdigest(), raising=False
    )
    config.write_text(
        config.read_text()
        + "IELTS_WEB_SPEAKING_PROFILE=speaking_hybrid_v1\n"
        + f"IELTS_WEB_SPEAKING_VAD_MODEL_PATH={model.as_posix()}\n"
    )
    return launcher, config, calls, model


def test_hybrid_default_launch_shares_azure_and_uses_openai_without_gpu_proxy(
    monkeypatch, tmp_path, capsys
):
    launcher, config, calls, model = setup_hybrid_launcher(monkeypatch, tmp_path)
    monkeypatch.setenv("IELTS_WEB_SPEAKING_AI_PROVIDER", "vllm")
    assert launcher.main(["--config", str(config)]) == 0
    assert len(calls) == 1
    environment = calls[0][1]["env"]
    assert environment["IELTS_WEB_SPEAKING_PROFILE"] == "speaking_hybrid_v1"
    assert environment["IELTS_WEB_AI_PROVIDER"] == "openai"
    assert environment["IELTS_WEB_SPEAKING_AI_PROVIDER"] == "openai"
    assert environment["SPEAKING_AI_PROVIDER"] == "openai"
    assert environment["SPEAKING_AZURE_KEY"] == "fictional-azure-key"
    assert environment["SPEAKING_AZURE_REGION"] == "southeastasia"
    assert environment["SPEAKING_AZURE_PROSODY"] == "true"
    assert environment["IELTS_WEB_SPEAKING_VAD_MODEL_PATH"] == str(model.resolve())
    assert environment["IELTS_WEB_CHART_SPECIALIST_ENABLED"] == "false"
    assert not environment.get("AI_WRITING_MODAL_SECRET")
    output = capsys.readouterr()
    assert "fictional-azure-key" not in output.out + output.err


def test_hybrid_missing_azure_fails_offline_without_attempting_a_service(
    monkeypatch, tmp_path, capsys
):
    launcher, config, calls, _ = setup_hybrid_launcher(
        monkeypatch, tmp_path, speaking_azure_region=""
    )
    assert launcher.main(["--config", str(config), "--check"]) == 1
    assert calls == []
    assert "SPEAKING_AZURE_KEY and SPEAKING_AZURE_REGION" in capsys.readouterr().err


def test_hybrid_rejects_modified_vad_asset_before_launch(monkeypatch, tmp_path, capsys):
    launcher, config, calls, model = setup_hybrid_launcher(monkeypatch, tmp_path)
    model.write_bytes(b"modified-model")
    assert launcher.main(["--config", str(config)]) == 1
    assert calls == []
    assert "checksum" in capsys.readouterr().err.lower()


def test_hybrid_explicit_no_asr_does_not_require_azure_or_model(monkeypatch, tmp_path):
    launcher, config, calls, model = setup_hybrid_launcher(
        monkeypatch, tmp_path, speaking_azure_region=""
    )
    model.unlink()
    assert launcher.main(["--config", str(config), "--no-asr"]) == 0
    assert calls[0][1]["env"]["IELTS_WEB_SPEAKING_ASR_ENABLED"] == "false"


def test_explicit_legacy_profile_overrides_local_hybrid_selection(monkeypatch, tmp_path):
    launcher, config, calls, _ = setup_hybrid_launcher(monkeypatch, tmp_path)
    assert (
        launcher.main(
            [
                "--config",
                str(config),
                "--speaking-profile",
                "legacy",
                "--provider",
                "openai",
                "--no-asr",
            ]
        )
        == 0
    )
    assert calls[0][1]["env"]["IELTS_WEB_SPEAKING_PROFILE"] == "legacy"
