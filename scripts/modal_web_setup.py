"""One-time backend secrets/assets setup; never prints secret values.

From backend/: uv run python ../scripts/modal_web_setup.py --snapshot <stamp>/database.dump
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot", required=True, help="Verified snapshot path inside ielts-postgres-backups"
    )
    parser.add_argument("--config", type=Path, default=ROOT / ".env.modal")
    parser.add_argument(
        "--secret-name", help="Defaults to the staging Secret selected in .env.modal"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Explicitly replace an existing dedicated config Secret",
    )
    parser.add_argument(
        "--disable-ai",
        action="store_true",
        help="Isolated dev config with fresh JWT and no local AI credentials",
    )
    args = parser.parse_args(argv)
    configuration = dotenv_values(args.config, interpolate=False) if args.config.is_file() else {}
    secret_name = (
        args.secret_name or configuration.get("IELTS_MODAL_CONFIG_SECRET") or "ielts-web-config"
    )
    cli = configuration.get("MODAL_CLI_PATH") or shutil.which("modal") or "modal"
    environment = dict(os.environ)
    for name in ("MODAL_PROFILE", "MODAL_ENVIRONMENT"):
        if configuration.get(name):
            environment[name] = configuration[name]
    settings = Settings(_env_file=ROOT / "backend/.env")
    if not settings.jwt_secret:
        raise SystemExit("Configure JWT_SECRET before Modal web setup.")
    values = {
        "JWT_SECRET": secrets.token_urlsafe(48) if args.disable_ai else settings.jwt_secret,
        "JWT_ISSUER": settings.jwt_issuer,
        "JWT_AUDIENCE": settings.jwt_audience,
        "AUTH_COOKIE_SECURE": "true",
        "IELTS_SEED_SNAPSHOT": args.snapshot,
    }
    speech_fields = {
        "speaking_profile",
        "speaking_asr_enabled",
        "speaking_asr_provider",
        "speaking_asr_language",
        "speaking_processing_timeout_seconds",
        "speaking_azure_key",
        "speaking_azure_region",
        "speaking_azure_locale",
        "speaking_azure_allow_paid",
        "speaking_azure_billing_mode",
        "speaking_azure_prosody",
        "speaking_azure_timeout_seconds",
        "speaking_azure_max_concurrency",
        "speaking_azure_max_queue",
    }
    for name in () if args.disable_ai else type(settings).model_fields:
        if not name.startswith(("ai_writing_", "speaking_ai_")) and name not in speech_fields:
            continue
        value = getattr(settings, name)
        if hasattr(value, "get_secret_value"):
            value = value.get_secret_value()
        if value is not None and value != "":
            if isinstance(value, (dict, list)):
                value = json.dumps(settings.model_dump(mode="json")[name], separators=(",", ":"))
            values[name.upper()] = str(value).lower() if isinstance(value, bool) else str(value)
    if args.disable_ai:
        if secret_name == "ielts-web-config":
            raise SystemExit("Isolated dev setup requires a dedicated --secret-name")
        values.update(
            STORAGE_BACKEND="local",
            STORAGE_ROOT="/storage",
            IELTS_DEPLOYMENT_ENV="dev",
            IELTS_AUTO_MIGRATE="true",
            AI_WRITING_ENABLED="false",
            SPEAKING_AI_ENABLED="false",
            SPEAKING_ASR_ENABLED="false",
        )
    with tempfile.TemporaryDirectory(prefix="ielts-modal-secret-") as temporary:
        file = Path(temporary) / "config.json"
        file.write_text(json.dumps(values), encoding="utf-8")
        result = subprocess.run(
            [
                cli,
                "secret",
                "create",
                secret_name,
                "--from-json",
                str(file),
                *(["--force"] if args.force or secret_name == "ielts-web-config" else []),
            ],
            capture_output=True,
            text=True,
            env=environment,
        )
        if result.returncode:
            raise SystemExit("Modal secret setup failed. Check workspace access.")
    print(f"Backend configuration saved in Modal Secret {secret_name}.")


if __name__ == "__main__":
    main()
