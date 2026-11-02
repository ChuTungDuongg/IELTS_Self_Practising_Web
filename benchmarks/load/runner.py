"""python -m benchmarks.load.runner: only explicitly isolated loopback resources."""

import argparse
import asyncio
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from benchmarks.load.client import RequestFailure
from benchmarks.load.runtime import (
    child_environment,
    proof,
    read_run,
    verify_database,
    write_private,
)
from benchmarks.load.safety import (
    SafetyError,
    validate_manifest,
    validate_runtime_values,
)
from benchmarks.load.source_identity import source_identity

ROOT = Path(__file__).resolve().parents[2]


async def initialize(directory, port, users, application_source=None):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ.get("LOAD_DATABASE_URL", "")
    match = re.fullmatch(r"ielts_load_([a-f0-9]{12})", urlsplit(url).path.removeprefix("/"))
    if not match:
        raise SafetyError("SET_LOAD_DATABASE_URL_TO_DEDICATED_DATABASE")
    run_id = match[1]
    directory = (directory or ROOT / "benchmarks" / "load" / ".runs" / run_id).resolve()
    if directory.name != run_id or directory.exists():
        raise SafetyError("FRESH_RUN_DIRECTORY_REQUIRED")
    manifest = {
        "run_id": run_id,
        "base_url": f"http://127.0.0.1:{port}",
        "environment": "isolated-load",
        "database_name": f"ielts_load_{run_id}",
        "database_user": f"load_{run_id}",
        "storage_root": str(directory / "storage"),
        "credential_id": f"load-{run_id}",
        "deployment_id": f"load-{run_id}",
        "max_users": users,
        "expires_at": (datetime.now(UTC) + timedelta(hours=8)).isoformat(),
    }
    validate_manifest(manifest, requested_users=users)
    application_source = (application_source or ROOT / "backend").resolve()
    if not (application_source / "app/main.py").is_file():
        raise SafetyError("APPLICATION_SOURCE_INVALID")
    manifest["source_identity"] = source_identity(application_source)
    private = {
        "token": secrets.token_urlsafe(48),
        "admin": {
            "email": f"load-{run_id}-admin@example.com",
            "password": secrets.token_urlsafe(32),
        },
        "environment": {
            "DATABASE_URL": url,
            "STORAGE_ROOT": manifest["storage_root"],
            "STORAGE_BACKEND": "local",
            "JWT_SECRET": secrets.token_urlsafe(48),
            "JWT_ISSUER": manifest["credential_id"],
            "JWT_AUDIENCE": manifest["credential_id"],
            "AUTH_COOKIE_SECURE": "false",
            "AI_WRITING_ENABLED": "false",
            "SPEAKING_AI_ENABLED": "false",
            "SPEAKING_ASR_ENABLED": "false",
            "FRONTEND_ORIGIN": manifest["base_url"],
            "IELTS_MODAL_WEB_TIMINGS": "1",
            "LOAD_APPLICATION_SOURCE_ROOT": str(application_source),
        },
    }
    validate_runtime_values(manifest, private["environment"])
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await verify_database(connection, manifest, private, require_proof=False)
            tables = await connection.scalars(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name <> 'alembic_version'"
                )
            )
            for table_name in tables:
                quoted = connection.dialect.identifier_preparer.quote(table_name)
                # Migration 0012 creates one disabled, credentialless historical owner.
                predicate = (
                    " WHERE NOT (email='legacy-admin@local.invalid' AND role='USER' AND is_active=false AND password_hash IS NULL)"
                    if table_name == "users"
                    else ""
                )
                if await connection.scalar(text(f"SELECT count(*) FROM {quoted}{predicate}")):
                    raise SafetyError("EMPTY_MIGRATED_DATABASE_REQUIRED")
            # The database comment binds this role/database to the generated private proof.
            await connection.execute(
                text(f"COMMENT ON DATABASE {manifest['database_name']} IS '{proof(private)}'")
            )
        directory.mkdir(parents=True)
        (directory / "storage").mkdir()
        write_private(directory / "manifest.local.json", manifest)
        write_private(directory / "credentials.local.json", private)
        for name, value in private["environment"].items():
            os.environ[name] = value
        sys.path.insert(0, str(application_source))
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.bootstrap_admin import bootstrap_admin
        from app.core.config import Settings

        settings = Settings(
            **{
                key.lower(): value
                for key, value in private["environment"].items()
                if key not in {"IELTS_MODAL_WEB_TIMINGS", "LOAD_APPLICATION_SOURCE_ROOT"}
            },
            initial_admin_email=private["admin"]["email"],
            initial_admin_password=private["admin"]["password"],
            initial_admin_name="Fictional load administrator",
        )
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await bootstrap_admin(session, settings)
    finally:
        await engine.dispose()
    print(f"Initialized isolated run: {directory}")


async def teardown(directory):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    manifest, private = read_run(directory)
    engine = create_async_engine(private["environment"]["DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            await verify_database(connection, manifest, private)
            # Only the attested, role-owned, uniquely named fixture DB may be cleared.
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
            await connection.execute(
                text(f"COMMENT ON DATABASE {manifest['database_name']} IS NULL")
            )
    finally:
        await engine.dispose()
    storage = await asyncio.to_thread(Path(manifest["storage_root"]).resolve)
    if storage.parent != directory.resolve() or storage.name != "storage":
        raise SafetyError("STORAGE_CLEANUP_SCOPE_INVALID")
    shutil.rmtree(storage)
    (directory / "credentials.local.json").unlink()
    (directory / "fixtures.local.json").unlink(missing_ok=True)
    print(
        "Isolated fixture schema/storage/credentials cleared; reports retained. Stop server before teardown."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "serve", "seed", "run", "teardown"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--port", type=int, default=18991)
    parser.add_argument(
        "--application-source",
        type=Path,
        help="Explicit backend source directory for a baseline comparison",
    )
    parser.add_argument("--users", type=int, default=5)
    parser.add_argument(
        "--profile", choices=("smoke", "ramp", "burst", "soak", "high"), default="smoke"
    )
    parser.add_argument("--scenario", choices=("A", "B", "C", "mixed"), default="mixed")
    args = parser.parse_args()
    if args.action == "init":
        asyncio.run(initialize(args.directory, args.port, args.users, args.application_source))
        return
    if not args.directory:
        raise SafetyError("RUN_DIRECTORY_REQUIRED")
    directory = args.directory.resolve()
    manifest, private = read_run(directory)
    validate_manifest(manifest, requested_users=args.users)
    env = child_environment(directory, private)
    if args.action == "serve":
        subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "benchmarks.load.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(urlsplit(manifest["base_url"]).port),
                "--no-access-log",
                "--workers",
                "1",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
    elif args.action == "seed":
        from benchmarks.load.fixtures import seed

        if (directory / "fixtures.local.json").exists():
            raise SafetyError("FIXTURES_ALREADY_EXIST")
        result = asyncio.run(seed(manifest, private, students=args.users))
        write_private(directory / "fixtures.local.json", result)
        print(f"Created {args.users} independent teacher/student cohorts using authenticated APIs.")
    elif args.action == "run":
        if args.profile == "high":
            raise SafetyError("HIGH_5000_IS_DESIGN_ONLY_REQUIRES_SEPARATE_CLOUD_AUTHORIZATION")
        env.update(
            LOAD_PROFILE=args.profile,
            LOAD_SCENARIO=args.scenario,
            LOAD_USERS=str(args.users),
        )
        from benchmarks.load.profiles import configured_profile

        for key in (
            "LOAD_RAMP_SECONDS",
            "LOAD_STEADY_SECONDS",
            "LOAD_DRAIN_SECONDS",
            "LOAD_THINK_SCALE",
            "LOAD_MAX_RPS_PER_USER",
        ):
            if key in os.environ:
                env[key] = os.environ[key]
        effective = configured_profile(args.profile, env)

        subprocess.run(
            [
                sys.executable,
                "-m",
                "locust",
                "-f",
                str(ROOT / "benchmarks/load/locustfile.py"),
                "--headless",
                "--only-summary",
                "--stop-timeout",
                str(math.ceil(effective["drain"])),
                "--exit-code-on-error",
                "1",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
    else:
        asyncio.run(teardown(directory))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 -- boundary must redact SQL/HTTP exceptions
        # Do not echo exceptions from SQL/HTTP libraries: they can contain credentials.
        code = (
            str(error) if isinstance(error, (SafetyError, RequestFailure)) else type(error).__name__
        )
        print(f"Load runner stopped: {code}", file=sys.stderr)
        raise SystemExit(1) from None
