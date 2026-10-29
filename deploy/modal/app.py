"""Single command: modal serve deploy/modal/app.py (persistent: modal deploy)."""

import json
import os
import sys
import threading
from pathlib import Path
from uuid import uuid4

import modal
from deploy.modal.chart_derenderer import MODEL as DEPLOT_MODEL
from deploy.modal.chart_derenderer import REVISION as DEPLOT_REVISION
from deploy.modal.chart_derenderer import app as chart_app
from deploy.modal.chart_derenderer import serve as chart_serve
from deploy.modal.speaking_asr import MODEL as ASR_MODEL
from deploy.modal.speaking_asr import REVISION as ASR_REVISION
from deploy.modal.speaking_asr import SERVICE_VERSION as ASR_VERSION
from deploy.modal.speaking_asr import app as asr_app
from deploy.modal.speaking_asr import serve_asr as asr_serve
from deploy.modal.writing_llm import MODEL
from deploy.modal.writing_llm import app as llm_app
from deploy.modal.writing_llm import serve as llm_serve
from deploy.runtime_config import boolean

ROOT = Path(__file__).resolve().parents[2] if modal.is_local() else Path("/workspace")
MODE = os.environ.get(
    "IELTS_MODAL_MODE", "dev" if modal.is_local() and "serve" in sys.argv else "production"
)
if MODE not in {"dev", "production"}:
    raise ValueError("IELTS_MODAL_MODE must be dev or production")
ASSET_BACKEND = os.environ.get(
    "IELTS_MODAL_STORAGE_BACKEND", os.environ.get("STORAGE_BACKEND", "local")
).strip()
if ASSET_BACKEND not in {"local", "s3", "r2"}:
    raise ValueError("IELTS_MODAL_STORAGE_BACKEND must be local, s3 or r2")
DATABASE_MODE = os.environ.get(
    "IELTS_MODAL_DATABASE_MODE", "embedded" if ASSET_BACKEND == "local" else "external"
)
if DATABASE_MODE not in {"embedded", "external"}:
    raise ValueError("IELTS_MODAL_DATABASE_MODE must be embedded or external")
if ASSET_BACKEND != "local" and DATABASE_MODE != "external":
    raise ValueError("Cloud assets require the external database topology")
CONFIG_SECRET_NAME = os.environ.get("IELTS_MODAL_CONFIG_SECRET", "ielts-web-config").strip()
if not CONFIG_SECRET_NAME:
    raise ValueError("IELTS_MODAL_CONFIG_SECRET must not be empty")
REQUIRE_ISOLATION = boolean(os.environ, "IELTS_MODAL_REQUIRE_ASSET_ISOLATION", "false")
app = modal.App("ielts-practice-web-dev" if MODE == "dev" else "ielts-practice-web")
AI_ENABLED = os.environ.get(
    "IELTS_WEB_AI_ENABLED", os.environ.get("AI_WRITING_ENABLED", "true")
).lower() in {"true", "1", "yes"}
if AI_ENABLED:
    app.include(llm_app)
ASR_ENABLED = os.environ.get("IELTS_WEB_SPEAKING_ASR_ENABLED", str(AI_ENABLED)).lower() in {
    "true",
    "1",
    "yes",
}
if ASR_ENABLED:
    app.include(asr_app)
CHART_SPECIALIST_ENABLED = AI_ENABLED and os.environ.get(
    "IELTS_WEB_CHART_SPECIALIST_ENABLED",
    os.environ.get("AI_WRITING_CHART_SPECIALIST_ENABLED", "false"),
).lower() in {"true", "1", "yes"}
if CHART_SPECIALIST_ENABLED:
    app.include(chart_app)
DEFAULT_DATABASE_VOLUME = "ielts-web-postgres-dev" if MODE == "dev" else "ielts-web-postgres"
DATABASE_VOLUME_NAME = os.environ.get(
    "IELTS_MODAL_DATABASE_VOLUME",
    os.environ.get(f"IELTS_MODAL_{MODE.upper()}_DATABASE_VOLUME", DEFAULT_DATABASE_VOLUME),
).strip()
SNAPSHOTS_VOLUME_NAME = os.environ.get(
    "IELTS_MODAL_SNAPSHOTS_VOLUME", "ielts-postgres-backups"
).strip()
if DATABASE_MODE == "embedded" and (not DATABASE_VOLUME_NAME or not SNAPSHOTS_VOLUME_NAME):
    raise ValueError("Embedded database and snapshots Volume names must not be empty")
# Legacy guards remain compatible. Fresh staging databases get a distinct key,
# without clearing or taking over an existing dev/production owner.
OWNER_KEY = {
    "ielts-web-postgres": "production",
    "ielts-web-postgres-dev": "dev",
}.get(DATABASE_VOLUME_NAME, DATABASE_VOLUME_NAME)
database = (
    modal.Volume.from_name(
        DATABASE_VOLUME_NAME,
        create_if_missing=DATABASE_VOLUME_NAME == DEFAULT_DATABASE_VOLUME,
        version=2,
    )
    if DATABASE_MODE == "embedded"
    else None
)
ASSETS_VOLUME_NAME = os.environ.get(
    "IELTS_MODAL_ASSETS_VOLUME",
    os.environ.get(f"IELTS_MODAL_{MODE.upper()}_ASSETS_VOLUME", "ielts-web-assets"),
).strip()
if ASSET_BACKEND == "local" and not ASSETS_VOLUME_NAME:
    raise ValueError("IELTS_MODAL_ASSETS_VOLUME must not be empty")
if (
    ASSET_BACKEND == "local"
    and MODE == "dev"
    and REQUIRE_ISOLATION
    and ASSETS_VOLUME_NAME == "ielts-web-assets"
):
    raise ValueError("Dev isolation requires a pre-created separate asset Volume")
assets = (
    modal.Volume.from_name(
        ASSETS_VOLUME_NAME, create_if_missing=ASSETS_VOLUME_NAME == "ielts-web-assets"
    )
    if ASSET_BACKEND == "local"
    else None
)
snapshots = (
    modal.Volume.from_name(SNAPSHOTS_VOLUME_NAME, create_if_missing=False)
    if DATABASE_MODE == "embedded"
    else None
)
owners = (
    modal.Dict.from_name("ielts-web-database-owner", create_if_missing=True)
    if DATABASE_MODE == "embedded"
    else None
)
image = (
    modal.Image.from_registry("postgres:17-bookworm", add_python="3.12")
    .entrypoint([])
    .apt_install("nginx", "curl", "xz-utils", "ffmpeg")
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
    .env(
        {
            "IELTS_MODAL_MODE": MODE,
            "IELTS_MODAL_STORAGE_BACKEND": ASSET_BACKEND,
            "IELTS_MODAL_DATABASE_MODE": DATABASE_MODE,
            "IELTS_MODAL_CONFIG_SECRET": CONFIG_SECRET_NAME,
            "IELTS_MODAL_REQUIRE_ASSET_ISOLATION": str(REQUIRE_ISOLATION).lower(),
            "IELTS_MODAL_ASSETS_VOLUME": ASSETS_VOLUME_NAME,
            "IELTS_MODAL_DATABASE_VOLUME": DATABASE_VOLUME_NAME,
            "IELTS_MODAL_SNAPSHOTS_VOLUME": SNAPSHOTS_VOLUME_NAME,
            "IELTS_WEB_AI_ENABLED": str(AI_ENABLED).lower(),
            "IELTS_WEB_CHART_SPECIALIST_ENABLED": str(CHART_SPECIALIST_ENABLED).lower(),
        }
    )
    .add_local_file(
        ROOT / "deploy/modal/web_runtime.py", "/workspace/deploy/modal/web_runtime.py", copy=True
    )
    .add_local_file(
        ROOT / "deploy/modal/nginx.conf", "/workspace/deploy/modal/nginx.conf", copy=True
    )
    .add_local_python_source("deploy.modal", "deploy.runtime_config")
)

# Explicit shell overrides travel as an ephemeral Secret, never image variables.
web_secrets = [
    modal.Secret.from_name(CONFIG_SECRET_NAME),
    # Keep the same dependency graph locally and remotely. Remote containers
    # already contain these variables; this API returns an empty Secret there.
    modal.Secret.from_local_environ(
        [
            key
            for key in os.environ
            if key.startswith("AI_WRITING_") or key in {"SPEAKING_AI_PROVIDER", "SPEAKING_AI_MODEL"}
        ]
    ),
]


web_volumes = {}
if snapshots is not None:
    web_volumes["/snapshots"] = snapshots
if database is not None:
    web_volumes["/database"] = database
if assets is not None:
    web_volumes["/storage"] = assets


@app.function(image=image, secrets=web_secrets, max_containers=1, timeout=300)
def migrate_database():
    """Explicit operator action; never called by an external-database Web startup."""
    import subprocess

    from deploy.runtime_config import validate_runtime

    external, _ = validate_runtime(os.environ, expected_backend=ASSET_BACKEND, mode=MODE)
    if not external:
        raise RuntimeError("The operator migration function requires an external DATABASE_URL")
    from deploy.modal.web_runtime import WebRuntime

    runtime = WebRuntime()
    try:
        runtime.prepare_database_ca()
        result = subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd="/workspace/backend",
            capture_output=True,
            text=True,
        )
    finally:
        runtime.stop()
    if result.returncode:
        raise RuntimeError(
            "External database migration failed; inspect configuration and revision compatibility"
        )


@app.cls(
    image=image,
    cpu=2,
    memory=4096,
    volumes=web_volumes,
    secrets=web_secrets,
    min_containers=1,
    max_containers=1,
    timeout=900,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=8)
class Web:
    @modal.enter()
    def start(self):
        import sys

        sys.path.insert(0, "/workspace/deploy/modal")
        from web_runtime import (
            WebRuntime,
            configure_ai_environment,
            configure_speaking_asr_environment,
            safe_ai_configuration,
        )

        configure_ai_environment(AI_ENABLED, MODEL, llm_serve.get_web_url() if AI_ENABLED else None)
        configure_speaking_asr_environment(
            ASR_ENABLED,
            ASR_MODEL,
            ASR_REVISION,
            ASR_VERSION,
            asr_serve.get_web_url() if ASR_ENABLED else None,
        )
        from web_runtime import configure_chart_environment

        configure_chart_environment(
            CHART_SPECIALIST_ENABLED,
            DEPLOT_MODEL,
            DEPLOT_REVISION,
            chart_serve.get_web_url() if CHART_SPECIALIST_ENABLED else None,
        )
        print("Modal AI configuration: " + json.dumps(safe_ai_configuration()), flush=True)

        self.runtime = WebRuntime()
        self.owner = None
        self.stop_heartbeat = threading.Event()
        if self.runtime.local_postgres:
            if database is None:
                raise RuntimeError(
                    "External database topology requires DATABASE_URL in the backend Secret"
                )
            self.owner = uuid4().hex
            if not owners.put(OWNER_KEY, self.owner, skip_if_exists=True):
                raise RuntimeError(
                    "Another container owns PostgreSQL. Stop it first. For a crashed deployment, use the documented stale-owner recovery."
                )
        try:
            if assets is not None:
                # Before any application file handles are opened; never reload live media.
                assets.reload()
                print(
                    "Modal local assets use asynchronous Volume durability; HTTP success does not confirm a committed snapshot.",
                    flush=True,
                )
                if MODE == "dev" and ASSETS_VOLUME_NAME == "ielts-web-assets":
                    print(
                        "Modal dev is using the legacy shared assets Volume; opt into isolated Volumes before editing production media.",
                        flush=True,
                    )
            self.runtime.start()
            if self.runtime.local_postgres:
                database.commit()
        except Exception:
            self.runtime.stop()
            if self.owner and owners.get(OWNER_KEY) == self.owner:
                owners.pop(OWNER_KEY, None)
            raise

        if self.owner:

            def heartbeat():
                while not self.stop_heartbeat.wait(60):
                    owners.get(OWNER_KEY)

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
        try:
            failures = []
            for name, volume in (
                ("database", database if self.runtime.local_postgres else None),
                ("assets", assets),
            ):
                if volume is not None:
                    try:
                        # Processes stopped above; there are no live application file handles.
                        volume.commit()
                    except Exception:
                        failures.append(name)
            if failures:
                raise RuntimeError("Modal Volume commit failed: " + ", ".join(failures))
        finally:
            if self.owner and owners.get(OWNER_KEY) == self.owner:
                owners.pop(OWNER_KEY, None)
