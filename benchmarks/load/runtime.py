"""Private files and PostgreSQL ownership proof for a single isolated run."""

import hashlib
import json
import os
from pathlib import Path

from benchmarks.load.safety import (
    SafetyError,
    validate_manifest,
    validate_runtime_values,
)
from sqlalchemy import text


def read_run(directory: str | Path):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.local.json").read_text(encoding="utf-8"))
    private = json.loads((directory / "credentials.local.json").read_text(encoding="utf-8"))
    validate_manifest(manifest, requested_users=1)
    validate_runtime_values(manifest, private["environment"])
    if (
        directory.name != manifest["run_id"]
        or Path(manifest["storage_root"]).resolve() != directory / "storage"
    ):
        raise SafetyError("RUN_DIRECTORY_MISMATCH")
    return manifest, private


def write_private(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    path.chmod(0o600)


def proof(private: dict) -> str:
    return "ielts-load:" + hashlib.sha256(private["token"].encode()).hexdigest()


async def verify_database(connection, manifest, private, *, require_proof=True):
    row = (
        await connection.execute(
            text(
                "SELECT current_database(), current_user, r.rolsuper, "
                "shobj_description(d.oid, 'pg_database') FROM pg_database d "
                "JOIN pg_roles r ON r.rolname = current_user WHERE d.datname = current_database()"
            )
        )
    ).one()
    if row[0] != manifest["database_name"] or row[1] != manifest["database_user"] or row[2]:
        raise SafetyError("DATABASE_IDENTITY_OR_ROLE_MISMATCH")
    if require_proof and row[3] != proof(private):
        raise SafetyError("DATABASE_OWNERSHIP_PROOF_MISMATCH")


async def verify_fresh_probe_database(connection, manifest, private):
    """Global fake consumers may run only in a newly initialized, idle fixture DB."""
    await verify_database(connection, manifest, private)
    others = await connection.scalar(
        text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid <> pg_backend_pid()"
        )
    )
    if others:
        raise SafetyError("FRESH_PROBE_DATABASE_REQUIRED")
    tables = await connection.scalars(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name <> 'alembic_version'"
        )
    )
    for table_name in tables:
        quoted = connection.dialect.identifier_preparer.quote(table_name)
        predicate = (
            " WHERE NOT ((email='legacy-admin@local.invalid' AND role='USER' "
            "AND is_active=false AND password_hash IS NULL) "
            "OR (email=:admin_email AND role='ADMIN' AND is_active=true))"
            if table_name == "users"
            else ""
        )
        if await connection.scalar(
            text(f"SELECT count(*) FROM {quoted}{predicate}"),
            {"admin_email": private["admin"]["email"]} if predicate else {},
        ):
            raise SafetyError("FRESH_PROBE_DATABASE_REQUIRED")


def child_environment(directory: Path, private: dict) -> dict:
    essentials = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PATHEXT",
        "SYSTEMDRIVE",
        "NUMBER_OF_PROCESSORS",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in essentials}
    env.update(private["environment"])
    root = Path(__file__).resolve().parents[2]
    backend = private["environment"].get("LOAD_APPLICATION_SOURCE_ROOT", str(root / "backend"))
    env["PYTHONPATH"] = os.pathsep.join((str(root), backend))
    env["LOAD_RUN_DIRECTORY"] = str(directory.resolve())
    return env
