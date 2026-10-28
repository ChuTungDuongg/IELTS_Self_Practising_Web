"""One-time backend secrets/assets setup; never prints secret values.

From backend/: uv run python ../scripts/modal_web_setup.py --snapshot <stamp>/database.dump
"""

import argparse
import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot", required=True, help="Verified snapshot path inside ielts-postgres-backups"
    )
    parser.add_argument("--secret-name", default="ielts-web-config")
    parser.add_argument(
        "--disable-ai",
        action="store_true",
        help="Isolated dev config with fresh JWT and no local AI credentials",
    )
    args = parser.parse_args(argv)
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
    for name in () if args.disable_ai else type(settings).model_fields:
        if name.startswith("ai_writing_"):
            value = getattr(settings, name)
            values[name.upper()] = str(value).lower() if isinstance(value, bool) else str(value)
    # Speaking inherits the Writing transport and credentials. Only intentional
    # provider/model overrides belong in the persistent Secret; runtime owns enablement.
    for name in () if args.disable_ai else ("speaking_ai_provider", "speaking_ai_model"):
        value = getattr(settings, name)
        if value:
            values[name.upper()] = value
    if args.disable_ai:
        if args.secret_name == "ielts-web-config":
            raise SystemExit("Isolated dev setup requires a dedicated --secret-name")
        values.update(
            STORAGE_BACKEND="local",
            STORAGE_ROOT="/storage",
            IELTS_DEPLOYMENT_ENV="dev",
            IELTS_AUTO_MIGRATE="true",
            AI_WRITING_ENABLED="false",
            SPEAKING_ASR_ENABLED="false",
        )
    with tempfile.TemporaryDirectory(prefix="ielts-modal-secret-") as temporary:
        file = Path(temporary) / "config.json"
        file.write_text(json.dumps(values), encoding="utf-8")
        result = subprocess.run(
            [
                "modal",
                "secret",
                "create",
                args.secret_name,
                "--from-json",
                str(file),
                *(["--force"] if args.secret_name == "ielts-web-config" else []),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise SystemExit("Modal secret setup failed. Check workspace access.")
    print(f"Backend configuration saved in Modal Secret {args.secret_name}.")


if __name__ == "__main__":
    main()
