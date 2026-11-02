"""Fail-closed target and resource identity checks shared by server and runner."""

import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


class SafetyError(ValueError):
    pass


IDENTITY_FIELDS = (
    "run_id",
    "environment",
    "database_name",
    "database_user",
    "storage_root",
    "credential_id",
    "deployment_id",
    "source_identity",
)


def validate_manifest(data: dict, *, requested_users: int) -> None:
    run_id = data.get("run_id", "")
    if not re.fullmatch(r"[a-f0-9]{12}", run_id):
        raise SafetyError("RUN_ID_INVALID")
    expected = {
        "environment": "isolated-load",
        "database_name": f"ielts_load_{run_id}",
        "database_user": f"load_{run_id}",
        "credential_id": f"load-{run_id}",
        "deployment_id": f"load-{run_id}",
    }
    if any(data.get(key) != value for key, value in expected.items()):
        raise SafetyError("INDEPENDENT_IDENTITY_REQUIRED")
    storage = Path(data.get("storage_root", ""))
    if not storage.is_absolute() or storage.name != "storage" or storage.parent.name != run_id:
        raise SafetyError("ISOLATED_STORAGE_REQUIRED")
    try:
        expires = datetime.fromisoformat(data["expires_at"])
        if expires.tzinfo is None or expires <= datetime.now(UTC):
            raise ValueError
        url = urlsplit(data["base_url"])
        port = url.port
    except (ValueError, KeyError, TypeError):
        raise SafetyError("MANIFEST_INVALID_OR_EXPIRED") from None
    if url.username or url.password or url.path or url.query or url.fragment or not port:
        raise SafetyError("TARGET_ORIGIN_REQUIRED")
    # Literal loopback only: no DNS rebinding, proxy, production URL or host override.
    if url.scheme != "http" or url.hostname != "127.0.0.1":
        raise SafetyError("LOCAL_OWNED_RUNNER_REQUIRED")
    max_users = data.get("max_users", 0)
    if not isinstance(max_users, int) or not 1 <= max_users <= 10:
        raise SafetyError("LOCAL_CAP_EXCEEDED")
    if not 1 <= requested_users <= max_users:
        raise SafetyError("USER_CAP_EXCEEDED")


def validate_attestation(manifest: dict, observed: dict) -> None:
    if observed.get("runner_owned") is not True:
        raise SafetyError("RUNNER_OWNERSHIP_REQUIRED")
    if any(observed.get(key) != manifest.get(key) for key in IDENTITY_FIELDS):
        raise SafetyError("ATTESTATION_MISMATCH")


def validate_path(path: str) -> None:
    if not path.startswith("/api/v1/") and path not in {
        "/__load__/identity",
        "/__load__/metrics",
    }:
        raise SafetyError("TARGET_PATH_INVALID")
    if any(value in path for value in ("\\", "\r", "\n", "://", "..", "//")):
        raise SafetyError("TARGET_PATH_INVALID")


def validate_runtime_values(manifest: dict, env: dict) -> None:
    validate_manifest(manifest, requested_users=1)
    url = urlsplit(env.get("DATABASE_URL", ""))
    if (
        url.scheme != "postgresql+asyncpg"
        or url.hostname != "127.0.0.1"
        or url.username != manifest["database_user"]
        or not url.password
        or url.path != "/" + manifest["database_name"]
        or url.query
        or url.fragment
    ):
        raise SafetyError("INDEPENDENT_DATABASE_REQUIRED")
    if (
        env.get("STORAGE_BACKEND") != "local"
        or Path(env.get("STORAGE_ROOT", "")).resolve() != Path(manifest["storage_root"]).resolve()
    ):
        raise SafetyError("ISOLATED_STORAGE_REQUIRED")
    if env.get("JWT_ISSUER") != manifest["credential_id"] or len(env.get("JWT_SECRET", "")) < 48:
        raise SafetyError("INDEPENDENT_CREDENTIALS_REQUIRED")
    if any(
        env.get(key, "false").lower() not in {"false", "0"}
        for key in ("AI_WRITING_ENABLED", "SPEAKING_AI_ENABLED", "SPEAKING_ASR_ENABLED")
    ):
        raise SafetyError("EXTERNAL_AI_FORBIDDEN")


def validate_runner_options(manifest: dict, options, *, requested_users: int) -> None:
    validate_manifest(manifest, requested_users=requested_users)
    if getattr(options, "host", None) not in (None, manifest["base_url"]):
        raise SafetyError("HOST_OVERRIDE_FORBIDDEN")
    if any(getattr(options, name, None) for name in ("master", "worker", "processes")):
        raise SafetyError("DISTRIBUTED_MODE_FORBIDDEN")
    if getattr(options, "num_users", None) not in (None, 1, requested_users):
        raise SafetyError("USER_OVERRIDE_FORBIDDEN")
