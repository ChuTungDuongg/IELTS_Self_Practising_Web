"""Operator-only configuration and read-only database coordination.

No implicit application .env, no credential-bearing reports, no automatic cutover.
"""

import hashlib
import json
import os
import re
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.storage.factory import get_asset_storage
from app.storage.local import LocalAssetStorage
from app.storage.migration import inventory_cleanup, inventory_references
from app.storage.s3 import S3CompatibleStorage

ENVIRONMENTS = {"development", "staging", "production", "recovery"}


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:24]


def object_endpoint(endpoint, region=""):
    parsed = urlsplit(endpoint) if endpoint else None
    host = parsed.hostname if parsed else ""
    if not host or host.endswith(".amazonaws.com"):
        return "aws-cn" if region.startswith("cn-") else "aws"
    if host.endswith(".amazonaws.com.cn"):
        return "aws-cn"
    return f"{host}:{parsed.port or 443}"


@dataclass(frozen=True)
class StorageTarget:
    storage: object
    backend: str
    environment: str
    target_id: str

    def description(self):
        return {
            "backend": self.backend,
            "environment": self.environment,
            "target_id": self.target_id,
        }


def storage_target(prefix, backend):
    environment = os.environ.get(f"{prefix}_ENVIRONMENT", "")
    if environment not in ENVIRONMENTS:
        raise ValueError(f"{prefix}_ENVIRONMENT must explicitly identify the intended environment")
    values = {
        "storage_backend": backend,
        "s3_bucket": "",
        "s3_region": "",
        "s3_endpoint_url": "",
        "s3_key_prefix": "",
        "aws_access_key_id": None,
        "aws_secret_access_key": None,
        "aws_session_token": None,
    }
    if backend == "local":
        root = Path(os.environ.get(f"{prefix}_STORAGE_ROOT", ""))
        if not root.is_absolute():
            raise ValueError(f"{prefix}_STORAGE_ROOT must be an absolute directory")
        values["storage_root"] = root
        namespace = [
            "local",
            str(root.resolve()).casefold() if os.name == "nt" else str(root.resolve()),
        ]
    else:
        for field in (
            "s3_bucket",
            "s3_region",
            "s3_endpoint_url",
            "s3_key_prefix",
            "aws_access_key_id",
            "aws_secret_access_key",
            "aws_session_token",
        ):
            value = os.environ.get(f"{prefix}_{field.upper()}")
            # Retain compatibility with the prototype's explicit credential names.
            legacy = {
                "aws_access_key_id": "S3_ACCESS_KEY_ID",
                "aws_secret_access_key": "S3_SECRET_ACCESS_KEY",
                "aws_session_token": "S3_SESSION_TOKEN",
            }.get(field)
            if value is None and legacy:
                value = os.environ.get(f"{prefix}_{legacy}")
            if value:
                values[field] = value
        namespace = [
            "object",
            object_endpoint(values.get("s3_endpoint_url", ""), values.get("s3_region", "")),
            values.get("s3_bucket", ""),
            values.get("s3_key_prefix", ""),
        ]
    # Explicit None prevents the unprefixed credential environment from leaking
    # into independent source/destination configs. S3 may still use an IAM role.
    if (
        backend == "s3"
        and not values["aws_access_key_id"]
        and os.environ.get(f"{prefix}_USE_AWS_CHAIN") != "true"
    ):
        raise ValueError(
            f"{prefix}_USE_AWS_CHAIN=true explicitly opts into IAM/SDK credential discovery"
        )
    settings = Settings(_env_file=None, **values)
    storage = get_asset_storage(settings)
    return StorageTarget(storage, backend, environment, identity(namespace))


def validate_report_path(path, *, backup_dir=None):
    path = Path(path)
    if path.suffix != ".json" or path.is_symlink():
        raise ValueError("Report must be a private JSON file, not a symlink")
    resolved = path.resolve()
    roots = [os.environ.get(f"{prefix}_STORAGE_ROOT", "") for prefix in ("SOURCE", "DESTINATION")]
    if backup_dir:
        roots.append(str(backup_dir))
    if any(
        root and Path(root).is_absolute() and resolved.is_relative_to(Path(root).resolve())
        for root in roots
    ):
        raise ValueError("Report must be outside source/destination assets and backup bundle")


def probe_target(target, *, source=False):
    if isinstance(target.storage, LocalAssetStorage):
        if source and not target.storage.root.is_dir():
            raise ValueError("Source storage directory does not exist")
    elif isinstance(target.storage, S3CompatibleStorage):
        # Operator command only. Never creates a bucket or falls back to local.
        target.storage.client.head_bucket(Bucket=target.storage.bucket)


def validate_distinct(source, destination):
    if isinstance(source, LocalAssetStorage) and isinstance(destination, LocalAssetStorage):
        if (
            source.root == destination.root
            or source.root in destination.root.parents
            or destination.root in source.root.parents
        ):
            raise ValueError("Local source and destination roots overlap")
    if isinstance(source, S3CompatibleStorage) and isinstance(destination, S3CompatibleStorage):
        if (
            source.bucket == destination.bucket
            and object_endpoint(source.client.meta.endpoint_url)
            == object_endpoint(destination.client.meta.endpoint_url)
            and (
                source.prefix.startswith(destination.prefix)
                or destination.prefix.startswith(source.prefix)
            )
        ):
            raise ValueError("S3 source and destination prefixes overlap")


def require_write_confirmation(
    destination,
    confirmation,
    maintenance,
    *,
    source_environment=None,
    allow_cross_environment=False,
):
    if confirmation != destination.target_id:
        raise ValueError(
            "Pass --confirm-target with the destination target_id from a reviewed dry-run"
        )
    if not maintenance:
        raise ValueError(
            "Writes require --maintenance-window after all application/background writers stop"
        )
    if (
        source_environment
        and source_environment != destination.environment
        and not allow_cross_environment
    ):
        raise ValueError("Cross-environment writes require --allow-cross-environment")


def validate_database_url(url):
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    parsed = urlsplit(url)
    if parsed.scheme != "postgresql+asyncpg" or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("Explicit PostgreSQL database URL is required")
    if parsed.fragment or set(parse_qs(parsed.query, keep_blank_values=True)) - {"ssl"}:
        raise ValueError(
            "Use only ssl in the database URL query; supply CA/client certificates through PGSSL environment variables"
        )
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} and parse_qs(parsed.query).get(
        "ssl", [""]
    )[0] not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("Remote database requires TLS in its URL")
    return url


def database_id(url):
    parsed = urlsplit(validate_database_url(url))
    host = "loopback" if parsed.hostname in {"localhost", "127.0.0.1", "::1"} else parsed.hostname
    return identity([host, parsed.port or 5432, unquote(parsed.path)])


@asynccontextmanager
async def database_inventory(url, *, snapshot=False):
    engine = create_async_engine(
        validate_database_url(url), connect_args={"timeout": 10, "command_timeout": 60}
    )
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            async with AsyncSession(bind=connection) as session:
                references = await inventory_references(session)
                cleanup = await inventory_cleanup(session)
                token = (
                    await connection.scalar(text("SELECT pg_export_snapshot()"))
                    if snapshot
                    else None
                )
                yield references, cleanup, token
    finally:
        await engine.dispose()


def postgres_tool(tool, url, path, *, snapshot=None):
    """Host client tools; credentials are env-only, never command line or diagnostics."""
    parsed = urlsplit(validate_database_url(url))
    env = os.environ.copy()
    env.update(
        PGHOST=parsed.hostname,
        PGPORT=str(parsed.port or 5432),
        PGDATABASE=unquote(parsed.path.lstrip("/")),
        PGUSER=unquote(parsed.username or ""),
    )
    # Override ambient PG options, including an inherited password or service.
    for name in ("PGPASSWORD", "PGSERVICE", "PGOPTIONS", "PGHOSTADDR"):
        env.pop(name, None)
    env["PGCONNECT_TIMEOUT"] = "10"
    if parsed.password is not None:
        env["PGPASSWORD"] = unquote(parsed.password)
    ssl = parse_qs(parsed.query).get("ssl", [""])[0]
    if ssl:
        env["PGSSLMODE"] = ssl
    args = [tool, "--no-password"]
    if tool == "pg_dump":
        args += ["--format=custom", f"--file={path}"]
        if snapshot:
            args += [f"--snapshot={snapshot}"]
    elif tool == "pg_restore":
        # Empty isolated database only; deliberately no --clean or --create.
        args += [
            "--no-owner",
            "--no-acl",
            "--single-transaction",
            "--exit-on-error",
            f"--dbname={env['PGDATABASE']}",
            str(path),
        ]
    else:
        raise ValueError("Unsupported PostgreSQL operation")
    result = subprocess.run(
        args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False
    )
    if result.returncode:
        raise RuntimeError(
            f"{tool} failed; verify client/server compatibility and secure connectivity"
        )


async def check_restore_database(url, *, source_id, confirmation=None):
    url = validate_database_url(url)
    target_id = database_id(url)
    parsed = urlsplit(url)
    if os.environ.get("RESTORE_ENVIRONMENT") != "recovery" or not re.search(
        r"(?:^|_)(?:recovery|restore|test)(?:_|$)", unquote(parsed.path.lstrip("/")), re.I
    ):
        raise ValueError(
            "Restore requires RESTORE_ENVIRONMENT=recovery and a dedicated recovery/restore/test database name"
        )
    active = os.environ.get("DATABASE_URL")
    if target_id == source_id or (active and target_id == database_id(active)):
        raise ValueError("Restore target must differ from source and application database")
    if confirmation is not None and confirmation != target_id:
        raise ValueError("Pass --confirm-database with the reviewed recovery database_id")
    engine = create_async_engine(url, connect_args={"timeout": 10, "command_timeout": 60})
    try:
        async with engine.connect() as connection:
            objects = await connection.scalar(
                text("""SELECT count(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT IN ('pg_catalog','information_schema')
                AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')""")
            )
            sessions = await connection.scalar(
                text("""SELECT count(*) FROM pg_stat_activity
                WHERE datname=current_database() AND pid<>pg_backend_pid()""")
            )
            routines = await connection.scalar(
                text("""SELECT count(*) FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname NOT IN ('pg_catalog','information_schema')""")
            )
            schemas = await connection.scalar(
                text("""SELECT count(*) FROM pg_namespace
                WHERE nspname NOT IN ('public','pg_catalog','information_schema')
                AND nspname NOT LIKE 'pg_toast%' AND nspname NOT LIKE 'pg_temp_%'""")
            )
            if objects or routines or schemas or sessions:
                raise ValueError("Restore database must be empty with no other active sessions")
    finally:
        await engine.dispose()
    return target_id
