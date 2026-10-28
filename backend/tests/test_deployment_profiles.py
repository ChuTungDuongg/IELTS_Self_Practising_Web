from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from deploy.runtime_config import validate_runtime
from sqlalchemy.exc import OperationalError

from app.api.v1.health import ready
from app.core.config import Settings
from app.core.exceptions import AppError

ROOT = Path(__file__).resolve().parents[2]


def cloud_environment(backend="s3"):
    return {
        "DATABASE_URL": "postgresql+asyncpg://fixture:fictional@database.example.invalid/bandpilot?ssl=verify-full",
        "STORAGE_BACKEND": backend,
        "S3_BUCKET": "private-fixture",
        "S3_REGION": "us-east-1" if backend == "s3" else "auto",
        "S3_ENDPOINT_URL": "" if backend == "s3" else "https://fixture.r2.cloudflarestorage.com",
        "AWS_ACCESS_KEY_ID": "fixture",
        "AWS_SECRET_ACCESS_KEY": "fictional-secret",
        "JWT_SECRET": "fictional-backend-secret-at-least-32-characters",
        "AUTH_COOKIE_SECURE": "true",
        "FRONTEND_ORIGIN": "https://bandpilot.example.com",
        "IELTS_DEPLOYMENT_ENV": "production",
        "IELTS_AUTO_MIGRATE": "false",
    }


def test_embedded_demo_defaults_remain_compatible():
    assert validate_runtime({}) == (False, True)


@pytest.mark.parametrize("backend", ["s3", "r2"])
def test_managed_profiles_require_operator_migrations_and_secure_runtime(backend):
    env = cloud_environment(backend)
    assert validate_runtime(env, mode="production", expected_backend=backend) == (True, False)
    assert validate_runtime(env, production=True) == (True, False)
    Settings(_env_file=None, **{key.lower(): value for key, value in env.items()})


@pytest.mark.parametrize(
    "override",
    [
        {"DATABASE_URL": ""},
        {"DATABASE_URL": "postgresql+asyncpg://fixture@database.example.invalid/bandpilot"},
        {
            "DATABASE_URL": "postgresql+asyncpg://fixture@database.example.invalid/bandpilot?ssl=disable"
        },
        {"DATABASE_URL": "sqlite:///test"},
        {"STORAGE_BACKEND": "unsupported"},
        {"AUTH_COOKIE_SECURE": "false"},
        {"JWT_SECRET": "short"},
        {"FRONTEND_ORIGIN": "http://bandpilot.example.com"},
        {"FRONTEND_ORIGIN": "https://user:password@bandpilot.example.com"},
        {"IELTS_AUTO_MIGRATE": "true"},
        {"IELTS_AUTO_MIGRATE": "maybe"},
        {"IELTS_DEPLOYMENT_ENV": "dev"},
    ],
)
def test_invalid_cloud_profile_fails_closed_without_echoing_credentials(override):
    with pytest.raises(RuntimeError) as error:
        validate_runtime(cloud_environment() | override, mode="production")
    assert "fictional-secret" not in str(error.value)


def test_missing_environment_label_prevents_dev_using_production_cloud_secret():
    env = cloud_environment()
    with pytest.raises(RuntimeError, match="IELTS_DEPLOYMENT_ENV"):
        validate_runtime(env, mode="dev")
    env.pop("IELTS_DEPLOYMENT_ENV")
    with pytest.raises(RuntimeError, match="IELTS_DEPLOYMENT_ENV"):
        validate_runtime(env, mode="dev")


async def test_readiness_checks_database_without_leaking_failures():
    session = SimpleNamespace(execute=AsyncMock())
    assert (await ready(session)).status == "ready"
    for failure in (OperationalError("PRIVATE", {}, Exception("PRIVATE_PASSWORD")), TimeoutError()):
        session.execute.side_effect = failure
        with pytest.raises(AppError) as error:
            await ready(session)
        assert error.value.status_code == 503 and "PRIVATE" not in str(error.value)


def test_aws_compose_exposes_only_proxy_and_keeps_migrations_explicit():
    compose = yaml.safe_load((ROOT / "deploy/aws/compose.yml").read_text())
    services = compose["services"]
    assert set(services) == {"backend", "frontend", "proxy", "migrate"}
    assert all("ports" not in services[name] for name in ("backend", "frontend", "migrate"))
    assert services["proxy"]["ports"] == ["80:8080", "443:8443"]
    assert services["migrate"]["profiles"] == ["tools"]
    assert services["migrate"]["restart"] == "no"
    assert "alembic" in services["migrate"]["command"]
    assert services["backend"]["environment"]["IELTS_AUTO_MIGRATE"] == "false"
    assert "env_file" not in services["frontend"]
    assert services["backend"]["environment"]["AUTH_COOKIE_SECURE"] == "true"
    assert all(
        mount["read_only"] and not mount["bind"]["create_host_path"]
        for mount in services["backend"]["volumes"]
    )
    assert services["backend"]["restart"] == "unless-stopped"
    assert services["backend"]["stop_grace_period"] == "60s"


def test_docker_build_inputs_exclude_secrets_and_keep_correct_api_routes():
    backend = (ROOT / "deploy/aws/backend.Dockerfile").read_text()
    frontend = (ROOT / "deploy/aws/frontend.Dockerfile").read_text()
    ignore = (ROOT / ".dockerignore").read_text()
    assert "--require-hashes" in backend and "/api/v1/ready" in backend
    assert "USER appuser" in backend and "USER node" in frontend
    assert "NEXT_PUBLIC_API_BASE_URL=/api/v1" in frontend
    assert "API_INTERNAL_BASE_URL=http://backend:8000/api/v1" in frontend
    assert "**/.env*" in ignore and "**/*.env" in ignore
    assert "storage" in ignore and "backups" in ignore
    assert all(
        secret not in frontend for secret in ("AWS_ACCESS_KEY", "DATABASE_URL", "JWT_SECRET")
    )
    assert "COPY . ." not in backend + frontend


@pytest.mark.parametrize("name", ["deploy/modal/nginx.conf", "deploy/aws/nginx.conf"])
def test_proxy_contract_preserves_authorization_streaming_and_uploads(name):
    config = (ROOT / name).read_text()
    assert config.count("{") == config.count("}")
    assert "location /api/" in config and "proxy_buffering off;" in config
    assert "proxy_set_header X-Forwarded-Proto https;" in config
    assert "proxy_read_timeout 900s;" in config
    assert "client_max_body_size 310m;" in config
    assert "proxy_cache off;" in config
    assert "proxy_hide_header Set-Cookie" not in config


def test_aws_iam_policy_is_scoped_to_one_bucket_and_object_prefix():
    import json

    policy = json.loads((ROOT / "deploy/aws/s3-iam-policy.example.json").read_text())
    statements = policy["Statement"]
    assert statements[0]["Action"] == ["s3:ListBucket"]
    assert statements[1]["Resource"].endswith("/production/media/*")
    assert set(statements[1]["Action"]) == {"s3:GetObject", "s3:PutObject", "s3:DeleteObject"}


def test_operator_migration_accepts_url_encoded_database_password_without_running_migrations(
    monkeypatch,
):
    import runpy
    from unittest.mock import MagicMock

    from alembic.config import Config

    from alembic import context

    url = "postgresql+asyncpg://fixture:p%40ss%25word@database.invalid/bandpilot?ssl=verify-full"
    config = Config()
    captured = {}
    monkeypatch.setattr(context, "config", config, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(context, "configure", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(context, "begin_transaction", MagicMock())
    # This exercises only Alembic configuration: no SQL, connection or real migration.
    monkeypatch.setattr(context, "run_migrations", MagicMock())
    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(database_url=url))
    runpy.run_path(str(ROOT / "backend/alembic/env.py"))
    assert captured["url"] == url


def test_production_entrypoint_validates_before_exec_and_uses_existing_settings(monkeypatch):
    import os

    from deploy import runtime_config

    with patch.dict(os.environ, cloud_environment(), clear=True):
        captured = []
        monkeypatch.setattr(
            "sys.argv", ["runtime_config.py", "python", "-m", "alembic", "upgrade", "head"]
        )
        monkeypatch.setattr(
            runtime_config.os, "execvp", lambda program, args: captured.append((program, args))
        )
        runtime_config.main()
        assert captured == [("python", ["python", "-m", "alembic", "upgrade", "head"])]
        os.environ.pop("JWT_SECRET")
        with pytest.raises(SystemExit):
            runtime_config.main()
        assert len(captured) == 1
