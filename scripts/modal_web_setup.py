"""One-time backend secrets/assets setup; never prints secret values.

From backend/: uv run python ../scripts/modal_web_setup.py --snapshot <stamp>/database.dump
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot", required=True, help="Verified snapshot path inside ielts-postgres-backups"
    )
    args = parser.parse_args()
    settings = Settings(_env_file=ROOT / "backend/.env")
    if not settings.jwt_secret:
        raise SystemExit("Configure JWT_SECRET before Modal web setup.")
    values = {
        "JWT_SECRET": settings.jwt_secret,
        "JWT_ISSUER": settings.jwt_issuer,
        "JWT_AUDIENCE": settings.jwt_audience,
        "AUTH_COOKIE_SECURE": "true",
        "IELTS_SEED_SNAPSHOT": args.snapshot,
    }
    for name in type(settings).model_fields:
        if name.startswith("ai_writing_"):
            value = getattr(settings, name)
            values[name.upper()] = str(value).lower() if isinstance(value, bool) else str(value)
    with tempfile.TemporaryDirectory(prefix="ielts-modal-secret-") as temporary:
        file = Path(temporary) / "config.json"
        file.write_text(json.dumps(values), encoding="utf-8")
        result = subprocess.run(
            ["modal", "secret", "create", "ielts-web-config", "--from-json", str(file), "--force"],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise SystemExit("Modal secret setup failed. Check workspace access.")
    print("Backend configuration saved in Modal Secret ielts-web-config.")


if __name__ == "__main__":
    main()
