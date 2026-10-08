"""One container runs the existing Next.js/FastAPI stack and private PostgreSQL."""

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def configure_ai_environment(enabled: bool, model: str, endpoint: str | None) -> None:
    os.environ["AI_WRITING_ENABLED"] = str(enabled).lower()
    if enabled and os.environ.get("AI_WRITING_PROVIDER", "vllm") == "vllm":
        # Resolve this App's hydrated function URL: no temporary URL in .env.
        os.environ["AI_WRITING_VLLM_BASE_URL"] = endpoint.rstrip("/") + "/v1" if endpoint else ""
        os.environ["AI_WRITING_VLLM_MODEL"] = model


class WebRuntime:
    def __init__(self) -> None:
        self.processes: list[subprocess.Popen] = []
        self.database_root = Path("/database")
        self.snapshot_root = Path("/snapshots")
        self.pgdata = self.database_root / "pgdata"
        self.local_postgres = not bool(os.environ.get("DATABASE_URL"))

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
        if self.local_postgres:
            self.start_postgres()
        os.environ["STORAGE_ROOT"] = "/storage"
        os.environ["AUTH_COOKIE_SECURE"] = "true"
        os.environ["API_INTERNAL_BASE_URL"] = "http://127.0.0.1:9001/api/v1"
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
            )
        )
        self.wait_http("http://127.0.0.1:9001/api/v1/health")
        self.wait_http("http://127.0.0.1:3000/")
        self.processes.append(
            subprocess.Popen(
                ["nginx", "-c", "/workspace/deploy/modal/nginx.conf", "-g", "daemon off;"]
            )
        )

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
        if self.local_postgres and self.pgdata.joinpath("postmaster.pid").exists():
            self.command(
                ["pg_ctl", "-D", str(self.pgdata), "-m", "fast", "-w", "stop"], postgres=True
            )
