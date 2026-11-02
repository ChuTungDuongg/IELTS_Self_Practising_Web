"""Real process signals with injected offline worker/storage, no DB/provider calls."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("signal_name", ["SIGTERM", "SIGINT"])
def test_dedicated_worker_drains_on_service_stop_signal(signal_name):
    script = """
import asyncio
import signal
from types import SimpleNamespace
import app.workers.writing as worker
from app.core.config import Settings
events = []
class OfflineWorker:
    def __init__(self, *_args): pass
    def start(self):
        asyncio.get_running_loop().call_soon(signal.raise_signal, getattr(signal, SIGNAL_NAME))
async def stop(): events.append("stopped")
async def dispose(): events.append("disposed")
worker.get_settings = lambda: Settings(_env_file=None, ai_writing_enabled=True, ai_writing_vllm_base_url="https://fictional.invalid/v1")
worker.initialize_asset_storage = lambda _settings: None
worker.WritingAIWorker = OfflineWorker
worker.stop_writing_ai_workers = stop
worker.engine = SimpleNamespace(dispose=dispose)
asyncio.run(worker.main())
print(",".join(events))
""".replace("SIGNAL_NAME", repr(signal_name))
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "stopped,disposed"
