"""One container runs the existing Next.js/FastAPI stack and private PostgreSQL."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from deploy.runtime_config import validate_runtime


def nginx_config_with_timings(config: str) -> str:
    """Enable opt-in timings without logging URLs, headers, client addresses or request data."""
    marker = "    access_log off;"
    if config.count(marker) != 1:
        raise RuntimeError("Unexpected nginx configuration; cannot enable timing logs")
    timing = (
        "    log_format timing 'id=$request_id status=$status "
        "request_s=$request_time upstream=$upstream_addr "
        "upstream_s=$upstream_response_time connect_s=$upstream_connect_time';\n"
        "    access_log /dev/stdout timing;"
    )
    config = config.replace(marker, timing, 1)
    host_header = "            proxy_set_header Host $host;"
    if config.count(host_header) != 2:
        raise RuntimeError("Unexpected nginx proxy configuration; cannot enable timing logs")
    return config.replace(host_header, host_header + "\n            proxy_set_header X-Request-ID $request_id;")


def configure_ai_environment(enabled: bool, model: str, endpoint: str | None) -> None:
    os.environ["AI_WRITING_ENABLED"] = str(enabled).lower()
    # Both graders share the Writing transport. The explicit Speaking provider/model
    # overrides remain optional; the adapter inherits the hydrated Writing defaults.
    os.environ["SPEAKING_AI_ENABLED"] = str(enabled).lower()
    if enabled and os.environ.get("AI_WRITING_PROVIDER", "vllm") == "vllm":
        # Resolve this App's hydrated function URL: no temporary URL in .env.
        os.environ["AI_WRITING_VLLM_BASE_URL"] = endpoint.rstrip("/") + "/v1" if endpoint else ""
        os.environ["AI_WRITING_VLLM_MODEL"] = model


def safe_ai_configuration() -> dict[str, bool | str]:
    """Log effective AI wiring without URLs, credentials, or candidate content."""
    # Modal imports its entry point as `app`, which shadows the backend's `app`
    # package in this process. Resolve effective Settings in the same cwd as uvicorn.
    probe = """import json
from app.core.config import Settings
from app.providers.speaking_llm import is_configured, provider_identity
settings = Settings()
provider, model = provider_identity(settings)
print(json.dumps({
    'speaking_ai_enabled': settings.speaking_ai_enabled,
    'speaking_ai_configured': is_configured(settings),
    'speaking_provider': provider,
    'speaking_model': model,
    'writing_vllm_transport_url_configured': bool(settings.ai_writing_vllm_base_url),
    'speaking_asr_enabled': settings.speaking_asr_enabled,
}))"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=Path(__file__).resolve().parents[2] / "backend",
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    # Diagnostics must never prevent the existing application from starting.
    return {"inspection": "unavailable"}


def configure_chart_environment(
    enabled: bool, model: str, revision: str, endpoint: str | None
) -> None:
    os.environ["AI_WRITING_CHART_SPECIALIST_ENABLED"] = str(enabled).lower()
    if enabled:
        os.environ["AI_WRITING_CHART_SPECIALIST_PROVIDER"] = "deplot"
        os.environ["AI_WRITING_DEPLOT_MODEL"] = model
        os.environ["AI_WRITING_DEPLOT_REVISION"] = revision
        os.environ["AI_WRITING_DEPLOT_BASE_URL"] = endpoint.rstrip("/") if endpoint else ""


def configure_speaking_asr_environment(
    enabled: bool, model: str, revision: str, version: str, endpoint: str | None
) -> None:
    os.environ["SPEAKING_ASR_ENABLED"] = str(enabled).lower()
    if enabled:
        os.environ["SPEAKING_ASR_PROVIDER"] = "modal"
        os.environ["SPEAKING_ASR_BASE_URL"] = endpoint.rstrip("/") if endpoint else ""
        os.environ["SPEAKING_ASR_MODEL"] = model
        os.environ["SPEAKING_ASR_MODEL_REVISION"] = revision
        os.environ["SPEAKING_ASR_VERSION"] = version
        os.environ["SPEAKING_ASR_LANGUAGE"] = "en"
        # Includes the first pinned-model download; transcript jobs still heartbeat.
        os.environ["SPEAKING_PROCESSING_TIMEOUT_SECONDS"] = "600"


class WebRuntime:
    def __init__(self) -> None:
        self.processes: list[subprocess.Popen] = []
        self.database_root = Path("/database")
        self.snapshot_root = Path("/snapshots")
        self.pgdata = self.database_root / "pgdata"
        self.local_postgres = not bool(os.environ.get("DATABASE_URL"))
        self.database_ca_path: Path | None = None
        self.nginx_timing_config: Path | None = None

    def command(self, args: list[str], *, cwd: str | None = None, postgres: bool = False) -> str:
        operation = args[0]
        if postgres:
            args = ["runuser", "-u", "postgres", "--", *args]
        # Tool diagnostics can echo connection information. Keep failures generic.
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        if result.returncode:
            if operation == "initdb":
                # initdb runs before any user data or credentials are loaded.
                raise RuntimeError(f"PostgreSQL initialization failed: {result.stderr[:800]}")
            raise RuntimeError(f"Startup command failed: {operation}. Inspect configuration.")
        return result.stdout

    def start(self) -> None:
        external, auto_migrate = validate_runtime(
            os.environ,
            expected_backend=os.environ.get("IELTS_MODAL_STORAGE_BACKEND"),
            mode=os.environ.get("IELTS_MODAL_MODE"),
        )
        if external == self.local_postgres:
            raise RuntimeError("Database selection changed after runtime initialization")
        if os.environ.get("IELTS_MODAL_DATABASE_MODE") == "external" and not external:
            raise RuntimeError(
                "External database topology requires DATABASE_URL in the backend Secret"
            )
        if external:
            self.prepare_database_ca()
        self.command(
            ["python", "-c", "from app.core.config import Settings; Settings()"],
            cwd="/workspace/backend",
        )
        if self.local_postgres:
            self.start_postgres()
        if os.environ.get("STORAGE_BACKEND", "local").lower() == "local":
            os.environ.setdefault("STORAGE_ROOT", "/storage")
        os.environ["AUTH_COOKIE_SECURE"] = "true"
        os.environ["API_INTERNAL_BASE_URL"] = "http://127.0.0.1:9001/api/v1"
        if auto_migrate:
            self.command(["python", "-m", "alembic", "upgrade", "head"], cwd="/workspace/backend")
        self.processes.append(
            subprocess.Popen(
                [
                    "python",
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "9001",
                    "--proxy-headers",
                    "--forwarded-allow-ips",
                    "127.0.0.1",
                    "--no-access-log",
                ],
                cwd="/workspace/backend",
            )
        )
        self.processes.append(
            subprocess.Popen(
                [
                    "node",
                    "node_modules/next/dist/bin/next",
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "3000",
                ],
                cwd="/workspace/frontend",
                env={
                    **{
                        key: os.environ[key]
                        for key in ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "TMP", "TEMP")
                        if key in os.environ
                    },
                    "NODE_ENV": "production",
                    "NEXT_PUBLIC_API_BASE_URL": "/api/v1",
                    "API_INTERNAL_BASE_URL": "http://127.0.0.1:9001/api/v1",
                    "NEXT_TELEMETRY_DISABLED": "1",
                },
            )
        )
        self.wait_http("http://127.0.0.1:9001/api/v1/ready")
        self.wait_http("http://127.0.0.1:3000/")
        nginx_config = Path("/workspace/deploy/modal/nginx.conf")
        if os.environ.get("IELTS_MODAL_WEB_TIMINGS", "").lower() in {"1", "true", "yes"}:
            # The generated file changes access logging only; proxy behavior remains intact.
            with tempfile.NamedTemporaryFile(mode="w", prefix="ielts-nginx-", suffix=".conf", delete=False) as file:
                self.nginx_timing_config = Path(file.name)
                file.write(nginx_config_with_timings(nginx_config.read_text(encoding="utf-8")))
            nginx_config = self.nginx_timing_config
        self.processes.append(
            subprocess.Popen(
                ["nginx", "-c", str(nginx_config), "-g", "daemon off;"],
                env={key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ},
            )
        )

    def prepare_database_ca(self) -> None:
        certificate = os.environ.get("IELTS_DATABASE_CA_PEM", "")
        if not certificate:
            return
        if (
            len(certificate.encode()) > 32 * 1024
            or "-----BEGIN CERTIFICATE-----" not in certificate
            or "PRIVATE KEY" in certificate
            or os.environ.get("PGSSLROOTCERT")
        ):
            raise RuntimeError(
                "Provide a public database CA PEM or PGSSLROOTCERT, without private keys"
            )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", prefix="ielts-db-ca-", delete=False
        ) as file:
            file.write(certificate)
            self.database_ca_path = Path(file.name)
        os.environ["PGSSLROOTCERT"] = str(self.database_ca_path)

    def start_postgres(self) -> None:
        self.pgdata.mkdir(parents=True, exist_ok=True)
        # Modal exposes the mount through a symlink; chown its actual child.
        self.command(["chown", "-R", "postgres:postgres", str(self.pgdata)])
        initialized = self.pgdata.joinpath("PG_VERSION").exists()
        if not initialized:
            self.command(
                ["initdb", "-D", str(self.pgdata), "--auth-local=trust", "--auth-host=trust"],
                postgres=True,
            )
        # The Modal single-writer guard is acquired before this runtime starts.
        # Leftover PID files from a terminated container are not valid here.
        self.pgdata.joinpath("postmaster.pid").unlink(missing_ok=True)
        self.command(
            [
                "pg_ctl",
                "-D",
                str(self.pgdata),
                "-l",
                str(self.pgdata / "postgres.log"),
                "-o",
                "-h 127.0.0.1 -p 5432",
                "-w",
                "start",
            ],
            postgres=True,
        )
        if not self.command(
            ["psql", "-tAc", "SELECT 1 FROM pg_database WHERE datname='ielts'"], postgres=True
        ).strip():
            self.command(["createdb", "ielts"], postgres=True)
        restored = self.database_root / "snapshot-restored"
        if not restored.exists():
            snapshot = os.environ.get("IELTS_SEED_SNAPSHOT", "")
            if snapshot:
                if initialized:
                    raise RuntimeError(
                        "Refusing to seed an existing PostgreSQL directory; use an explicit reviewed restore"
                    )
                snapshot_root = self.snapshot_root.resolve()
                source = (snapshot_root / snapshot.lstrip("/")).resolve()
                if not source.is_relative_to(snapshot_root) or source.name != "database.dump":
                    raise RuntimeError("Invalid snapshot path")
                manifest = json.loads(source.with_name("manifest.json").read_text())
                if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["database_sha256"]:
                    raise RuntimeError("Snapshot checksum mismatch")
                self.command(
                    [
                        "pg_restore",
                        "--dbname=ielts",
                        "--clean",
                        "--if-exists",
                        "--single-transaction",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                        str(source),
                    ],
                    postgres=True,
                )
            restored.write_text(snapshot or "empty database")
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres@127.0.0.1:5432/ielts"

    def wait_http(self, url: str) -> None:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in self.processes):
                raise RuntimeError("An application process exited during startup")
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(1)
        raise RuntimeError("Application startup timed out")

    def stop(self) -> None:
        for process in reversed(self.processes):
            process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if self.local_postgres and self.pgdata.joinpath("postmaster.pid").exists():
            self.command(
                ["pg_ctl", "-D", str(self.pgdata), "-m", "fast", "-w", "stop"], postgres=True
            )
        if self.database_ca_path is not None:
            self.database_ca_path.unlink(missing_ok=True)
            if os.environ.get("PGSSLROOTCERT") == str(self.database_ca_path):
                os.environ.pop("PGSSLROOTCERT", None)
            self.database_ca_path = None
        if self.nginx_timing_config is not None:
            self.nginx_timing_config.unlink(missing_ok=True)
            self.nginx_timing_config = None
