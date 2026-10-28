import importlib.util
from pathlib import Path
from types import SimpleNamespace


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
