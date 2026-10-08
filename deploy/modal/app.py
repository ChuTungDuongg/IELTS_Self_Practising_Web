"""Single command: modal serve deploy/modal/app.py (persistent: modal deploy)."""

import os
import sys
import threading
from pathlib import Path
from uuid import uuid4

import modal
from deploy.modal.writing_llm import MODEL
from deploy.modal.writing_llm import app as llm_app
from deploy.modal.writing_llm import serve as llm_serve

ROOT = Path(__file__).resolve().parents[2] if modal.is_local() else Path("/workspace")
MODE = os.environ.get(
    "IELTS_MODAL_MODE", "dev" if modal.is_local() and "serve" in sys.argv else "production"
)
app = modal.App("ielts-practice-web-dev" if MODE == "dev" else "ielts-practice-web")
AI_ENABLED = os.environ.get(
    "IELTS_WEB_AI_ENABLED", os.environ.get("AI_WRITING_ENABLED", "true")
).lower() in {"true", "1", "yes"}
if AI_ENABLED:
    app.include(llm_app)
database = modal.Volume.from_name(
    "ielts-web-postgres-dev" if MODE == "dev" else "ielts-web-postgres",
    create_if_missing=True,
    version=2,
)
assets = modal.Volume.from_name("ielts-web-assets", create_if_missing=True)
snapshots = modal.Volume.from_name("ielts-postgres-backups")
owners = modal.Dict.from_name("ielts-web-database-owner", create_if_missing=True)
image = (
    modal.Image.from_registry("postgres:17-bookworm", add_python="3.12")
    .entrypoint([])
    .apt_install("nginx", "curl", "xz-utils")
    .run_commands(
        "curl -fsSL https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-x64.tar.xz -o /tmp/node.tar.xz",
        "tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1",
        "rm /tmp/node.tar.xz",
    )
    .add_local_dir(
        ROOT / "backend",
        "/workspace/backend",
        ignore=[".venv", ".env*", ".pytest_cache", ".ruff_cache", "__pycache__", "tests"],
        copy=True,
    )
    .run_commands(
        "python -m pip install --require-hashes -r /workspace/backend/requirements.txt",
        "python -m pip install --no-deps /workspace/backend",
    )
    .add_local_dir(
        ROOT / "frontend",
        "/workspace/frontend",
        ignore=["node_modules", ".next", ".env*", "tests", "*.tsbuildinfo"],
        copy=True,
    )
    .env(
        {
            "NEXT_PUBLIC_API_BASE_URL": "/api/v1",
            "API_INTERNAL_BASE_URL": "http://127.0.0.1:9001/api/v1",
            "NEXT_TELEMETRY_DISABLED": "1",
        }
    )
    .run_commands("cd /workspace/frontend && npm ci && npm run build")
    .env({"IELTS_MODAL_MODE": MODE, "IELTS_WEB_AI_ENABLED": str(AI_ENABLED).lower()})
    .add_local_file(
        ROOT / "deploy/modal/web_runtime.py", "/workspace/deploy/modal/web_runtime.py", copy=True
    )
    .add_local_file(
        ROOT / "deploy/modal/nginx.conf", "/workspace/deploy/modal/nginx.conf", copy=True
    )
    .add_local_python_source("deploy.modal")
)

# Explicit shell overrides travel as an ephemeral Secret, never image variables.
web_secrets = [
    modal.Secret.from_name("ielts-web-config"),
    # Keep the same dependency graph locally and remotely. Remote containers
    # already contain these variables; this API returns an empty Secret there.
    modal.Secret.from_local_environ([key for key in os.environ if key.startswith("AI_WRITING_")]),
]


@app.cls(
    image=image,
    cpu=2,
    memory=4096,
    volumes={"/database": database, "/storage": assets, "/snapshots": snapshots},
    secrets=web_secrets,
    min_containers=1,
    max_containers=1,
    timeout=900,
    scaledown_window=300,
)
class Web:
    @modal.enter()
    def start(self):
        import sys

        sys.path.insert(0, "/workspace/deploy/modal")
        from web_runtime import WebRuntime, configure_ai_environment

        configure_ai_environment(AI_ENABLED, MODEL, llm_serve.get_web_url() if AI_ENABLED else None)

        self.owner = uuid4().hex
        self.stop_heartbeat = threading.Event()
        if not owners.put(MODE, self.owner, skip_if_exists=True):
            raise RuntimeError(
                "Another container owns PostgreSQL. Stop it first. For a crashed deployment, use the documented stale-owner recovery."
            )
        self.runtime = WebRuntime()
        try:
            self.runtime.start()
            database.commit()
        except Exception:
            self.runtime.stop()
            owners.pop(MODE, None)
            raise

        def heartbeat():
            while not self.stop_heartbeat.wait(60):
                owners.get(MODE)  # Keep the guard from expiring during long runs.

        threading.Thread(target=heartbeat, daemon=True).start()

    @modal.web_server(8000, startup_timeout=240)
    def web(self):
        pass

    @modal.exit()
    def stop(self):
        if not hasattr(self, "runtime"):
            return
        self.stop_heartbeat.set()
        self.runtime.stop()
        database.commit()
        assets.commit()
        if owners.get(MODE) == self.owner:
            owners.pop(MODE, None)
