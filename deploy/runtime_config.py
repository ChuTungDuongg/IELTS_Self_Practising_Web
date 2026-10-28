"""Offline deployment validation shared by Modal and the production entrypoint."""

import os
import sys
from urllib.parse import parse_qs, urlsplit


def boolean(env, name, default):
    value = env.get(name, default).strip().lower()
    if value not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return value == "true"


def validate_runtime(env, *, expected_backend=None, mode=None, production=False):
    backend = env.get("STORAGE_BACKEND", "local").strip()
    if backend not in {"local", "s3", "r2"}:
        raise RuntimeError("STORAGE_BACKEND must be local, s3 or r2")
    if expected_backend and backend != expected_backend:
        raise RuntimeError("STORAGE_BACKEND does not match the Modal deployment topology")
    label = env.get("IELTS_DEPLOYMENT_ENV", "")
    if production and label != "production":
        raise RuntimeError("AWS production requires IELTS_DEPLOYMENT_ENV=production")
    if mode and label and label != mode:
        raise RuntimeError("IELTS_DEPLOYMENT_ENV does not match this Modal environment")
    external = bool(env.get("DATABASE_URL", "").strip())
    cloud = backend in {"s3", "r2"}
    if cloud and mode and label != mode:
        raise RuntimeError(
            "Cloud Modal mode requires a matching IELTS_DEPLOYMENT_ENV in its Secret"
        )
    if (cloud or production) and not external:
        raise RuntimeError("Cloud deployment requires an external DATABASE_URL")
    if production and not cloud:
        raise RuntimeError("AWS production requires STORAGE_BACKEND=s3 or r2")
    if external:
        try:
            database = urlsplit(env["DATABASE_URL"])
            valid = database.scheme == "postgresql+asyncpg" and bool(
                database.hostname and database.path.strip("/")
            )
            tls = parse_qs(database.query).get("ssl", [""])
        except ValueError:
            valid, tls = False, []
        if not valid:
            raise RuntimeError("DATABASE_URL must be a PostgreSQL asyncpg connection URL")
        if (cloud or production) and (
            len(tls) != 1 or tls[0] not in {"require", "verify-ca", "verify-full"}
        ):
            raise RuntimeError(
                "Managed DATABASE_URL must require TLS with ?ssl=require or verify-full"
            )
    migrate = boolean(env, "IELTS_AUTO_MIGRATE", "false" if external else "true")
    if external and migrate:
        raise RuntimeError(
            "External PostgreSQL requires IELTS_AUTO_MIGRATE=false; run migrations separately"
        )
    if cloud or production:
        origin = urlsplit(env.get("FRONTEND_ORIGIN", ""))
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
            or origin.username is not None
            or origin.password is not None
        ):
            raise RuntimeError("Cloud deployment requires an HTTPS FRONTEND_ORIGIN")
        if not boolean(env, "AUTH_COOKIE_SECURE", "false"):
            raise RuntimeError("Cloud deployment requires AUTH_COOKIE_SECURE=true")
        if len(env.get("JWT_SECRET", "")) < 32:
            raise RuntimeError("Cloud deployment requires JWT_SECRET with at least 32 characters")
    return external, migrate


def main():
    try:
        validate_runtime(os.environ, production=True)
        # P3 Settings remains authoritative for all storage/credential validation.
        from app.core.config import Settings

        Settings()
    except (ValueError, RuntimeError):
        raise SystemExit(
            "Deployment configuration is invalid; verify database TLS, storage, origin and backend secrets"
        ) from None
    if len(sys.argv) < 2:
        raise SystemExit("Provide the application or explicit migration command")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
