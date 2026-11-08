"""Private original-source materialization before P1 approval; no fabricated manifest."""

import asyncio
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from app.evaluation.speaking.replay_audio import probe_audio
from app.evaluation.speaking.replay_models import local_name
from app.services.speaking_audio import await_audio_thread
from app.services.speaking_benchmark import failure


@asynccontextmanager
async def materialize_source(storage, key, source_name, sha, duration_ms, settings):
    from app.evaluation.speaking.diarization_backend import LocalDiarizer

    local_name(source_name)
    resolved = await await_audio_thread(asyncio.to_thread(LocalDiarizer().audio_settings, settings))
    context = storage.materialize(
        key, max_bytes=settings.speaking_benchmark_max_upload_mb * 1024**2
    )
    source = await await_audio_thread(asyncio.to_thread(context.__enter__))
    try:
        with tempfile.TemporaryDirectory(prefix="benchmark-questions-") as directory:
            root = Path(directory)
            destination = root / source_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            await await_audio_thread(asyncio.to_thread(shutil.copyfile, source, destination))
            metadata = await await_audio_thread(
                asyncio.to_thread(probe_audio, destination, resolved)
            )
            if metadata["sha256"] != sha or abs(metadata["duration_ms"] - duration_ms) > 100:
                raise failure("SPEAKING_QUESTIONS_SOURCE_CHANGED", 409)
            yield root, metadata, resolved
    finally:
        await await_audio_thread(asyncio.to_thread(context.__exit__, None, None, None))
