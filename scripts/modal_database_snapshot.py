"""Upload a verified PostgreSQL snapshot, not a live database, to a Modal Volume.

From backend/: uv run python ../scripts/modal_database_snapshot.py
Requires the authenticated Modal CLI and existing PostgreSQL backup prerequisites.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.backup_restore import (  # noqa: E402
    REPO_ROOT,
    BackupError,
    load_configuration,
    run_pg_dump,
    sha256_file,
)


async def schema_version(database_url: str) -> str:
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://", 1))
    try:
        async with engine.connect() as connection:
            return str(await connection.scalar(text("SELECT version_num FROM alembic_version")))
    finally:
        await engine.dispose()


def modal_command(*args: str) -> str:
    result = subprocess.run(["modal", *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise BackupError("Modal command failed. Check CLI authentication and Volume access.")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--volume", default="ielts-postgres-backups")
    args = parser.parse_args()
    try:
        database_url, _ = load_configuration()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        directory = REPO_ROOT / "backups" / "modal" / stamp
        directory.mkdir(parents=True)
        dump = directory / "database.dump"
        run_pg_dump(database_url, dump)
        manifest = {
            "format": "PostgreSQL custom dump",
            "created_at": datetime.now(UTC).isoformat(),
            "alembic_revision": asyncio.run(schema_version(database_url)),
            "database_sha256": sha256_file(dump),
            "database_bytes": dump.stat().st_size,
            "includes_assets": False,
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        existing = json.loads(modal_command("volume", "list", "--json"))
        if not any(
            item.get("name") == args.volume or item.get("Name") == args.volume for item in existing
        ):
            modal_command("volume", "create", args.volume)
        remote = f"/{stamp}/"
        for file in directory.iterdir():
            modal_command("volume", "put", args.volume, str(file), remote + file.name)
        with tempfile.TemporaryDirectory(prefix="ielts-volume-verify-") as temporary:
            downloaded = Path(temporary) / "database.dump"
            modal_command("volume", "get", args.volume, remote + "database.dump", str(downloaded))
            if sha256_file(downloaded) != manifest["database_sha256"]:
                raise BackupError("Uploaded database checksum did not match.")
        print(f"Verified database snapshot: Volume {args.volume}, path {remote}database.dump")
        print(f"Local copy: {directory}")
        print(f"SHA-256: {manifest['database_sha256']}")
        return 0
    except (BackupError, OSError, ValueError):
        print(
            "Database snapshot failed. Check PostgreSQL, Modal credentials and Volume access.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
