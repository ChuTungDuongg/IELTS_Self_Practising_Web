import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr


@pytest.fixture(autouse=True)
def synthetic_settings(monkeypatch):
    import app.core.config as config

    settings = config.Settings.model_construct(
        jwt_secret="fictional-jwt-secret-at-least-32-characters",
        ai_writing_provider="openai",
        ai_writing_openai_api_key="fictional-openai-key",
        ai_writing_openai_model="fixture-model",
        ai_writing_openai_stage_overrides={
            "task1.scoring.ta": config.OpenAIStageOverride(reasoning_effort="high"),
        },
        speaking_ai_request_timeout_seconds=45.0,
        speaking_ai_score_max_tokens=200,
        speaking_asr_enabled=True,
        speaking_asr_provider="azure",
        speaking_azure_key=SecretStr("fictional-private-azure-key"),
        speaking_azure_region="japaneast",
        speaking_azure_billing_mode="free_only",
    )
    monkeypatch.setattr(config, "Settings", lambda **kwargs: settings)


def test_custom_staging_secret_never_overwrites_or_copies_ai_secrets(monkeypatch, capsys):
    path = Path(__file__).resolve().parents[2] / "scripts/modal_web_setup.py"
    spec = importlib.util.spec_from_file_location("modal_setup_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import json

    captured = []

    def run(args, **kwargs):
        captured.append((args, json.loads(Path(args[args.index("--from-json") + 1]).read_text())))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    module.main(
        [
            "--snapshot",
            "synthetic/database.dump",
            "--secret-name",
            "staging-fixture-config",
            "--disable-ai",
        ]
    )
    args, values = captured[0]
    assert args[3] == "staging-fixture-config" and "--force" not in args
    assert values["STORAGE_BACKEND"] == "local" and values["IELTS_DEPLOYMENT_ENV"] == "dev"
    assert not any("KEY" in key or "TOKEN" in key or "PASSWORD" in key for key in values)
    assert values["JWT_SECRET"] not in capsys.readouterr().out
    assert values["SPEAKING_ASR_ENABLED"] == "false"
    assert "SPEAKING_AZURE_KEY" not in values


def test_custom_config_updates_require_explicit_force_and_copy_speaking_controls(
    monkeypatch, capsys
):
    import json

    path = Path(__file__).resolve().parents[2] / "scripts/modal_web_setup.py"
    spec = importlib.util.spec_from_file_location("modal_setup_update_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = []

    def run(args, **kwargs):
        captured.append((args, json.loads(Path(args[args.index("--from-json") + 1]).read_text())))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    arguments = ["--snapshot", "synthetic/database.dump", "--secret-name", "custom-config"]
    module.main(arguments)
    assert "--force" not in captured[0][0]
    values = captured[0][1]
    assert values["AI_WRITING_OPENAI_API_KEY"] == "fictional-openai-key"
    assert values["AI_WRITING_OPENAI_MODEL"] == "fixture-model"
    assert (
        json.loads(values["AI_WRITING_OPENAI_STAGE_OVERRIDES"])["task1.scoring.ta"][
            "reasoning_effort"
        ]
        == "high"
    )
    assert values["SPEAKING_AI_REQUEST_TIMEOUT_SECONDS"] == "45.0"
    assert values["SPEAKING_AI_SCORE_MAX_TOKENS"] == "200"
    assert values["SPEAKING_ASR_ENABLED"] == "true"
    assert values["SPEAKING_ASR_PROVIDER"] == "azure"
    assert values["SPEAKING_AZURE_KEY"] == "fictional-private-azure-key"
    assert values["SPEAKING_AZURE_REGION"] == "japaneast"
    assert values["SPEAKING_AZURE_ALLOW_PAID"] == "false"
    assert values["SPEAKING_AZURE_BILLING_MODE"] == "free_only"
    assert "fictional-private-azure-key" not in capsys.readouterr().out
    assert all("fictional-private-azure-key" not in item for item in captured[0][0])
    assert "SPEAKING_AI_PROVIDER" not in values
    module.main([*arguments, "--force"])
    assert "--force" in captured[1][0]


def test_setup_uses_the_same_modal_profile_secret_and_cli_as_launcher(monkeypatch, tmp_path):
    import json

    path = Path(__file__).resolve().parents[2] / "scripts/modal_web_setup.py"
    spec = importlib.util.spec_from_file_location("modal_setup_profile_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = tmp_path / ".env.modal"
    config.write_text(
        "MODAL_PROFILE=fictional-profile\nMODAL_ENVIRONMENT=fictional-environment\n"
        "MODAL_CLI_PATH=fictional-modal-cli\nIELTS_MODAL_CONFIG_SECRET=fictional-config\n"
    )
    calls = []

    def run(args, **options):
        values = json.loads(Path(args[args.index("--from-json") + 1]).read_text())
        calls.append((args, options, values))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    module.main(["--config", str(config), "--snapshot", "existing/database.dump", "--force"])
    command, options, values = calls[0]
    assert command[0] == "fictional-modal-cli" and command[3] == "fictional-config"
    assert options["env"]["MODAL_PROFILE"] == "fictional-profile"
    assert options["env"]["MODAL_ENVIRONMENT"] == "fictional-environment"
    assert values["IELTS_SEED_SNAPSHOT"] == "existing/database.dump"
