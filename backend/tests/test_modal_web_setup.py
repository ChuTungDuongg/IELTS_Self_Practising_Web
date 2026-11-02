import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def synthetic_settings(monkeypatch):
    import app.core.config as config

    settings = config.Settings.model_construct(
        jwt_secret="fictional-jwt-secret-at-least-32-characters",
        ai_writing_provider="openai",
        ai_writing_openai_api_key="fictional-openai-key",
        ai_writing_openai_model="fixture-model",
        speaking_ai_request_timeout_seconds=45.0,
        speaking_ai_score_max_tokens=200,
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


def test_custom_config_updates_require_explicit_force_and_copy_speaking_controls(monkeypatch):
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
    assert values["SPEAKING_AI_REQUEST_TIMEOUT_SECONDS"] == "45.0"
    assert values["SPEAKING_AI_SCORE_MAX_TOKENS"] == "200"
    assert "SPEAKING_AI_PROVIDER" not in values
    module.main([*arguments, "--force"])
    assert "--force" in captured[1][0]
