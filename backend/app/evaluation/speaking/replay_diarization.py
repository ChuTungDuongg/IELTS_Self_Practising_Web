"""Private developer diarization cache, independent of prompts, labels and Azure checkpoints."""

import tempfile
from pathlib import Path

from app.evaluation.speaking.diarization_backend import LocalDiarizer, normalize_recording
from app.evaluation.speaking.diarization_models import DiarizationResult
from app.evaluation.speaking.replay_audio import probe_audio, resolve_source
from app.evaluation.speaking.replay_cache import live_lock, read_checkpoint, save_checkpoint
from app.evaluation.speaking.replay_manifest import discover
from app.services.speaking_audio import fingerprint


def auto_segment(root, settings, *, backend=None, pause_tolerance_ms=3000):
    backend = backend or LocalDiarizer()
    if hasattr(backend, "audio_settings"):
        settings = backend.audio_settings(settings)
    sources = {name: probe_audio(resolve_source(root, name), settings) for name in discover(root)}
    results, reused = [], 0
    with live_lock(root / ".diarization-cache"):
        for name, metadata in sources.items():
            key = fingerprint(
                [name, metadata["sha256"], backend.identity, backend.config, "original-time-pcm-v1"]
            )
            path = root / ".diarization-cache" / f"SENSITIVE-{key}.json"
            existing = read_checkpoint(path)
            if existing:
                result = DiarizationResult.model_validate(existing)
                if (
                    result.cache_key != key
                    or result.source != name
                    or result.source_sha256 != metadata["sha256"]
                ):
                    raise ValueError("Invalid diarization cache")
                reused += 1
            else:
                with tempfile.TemporaryDirectory(prefix="replay-diarization-") as directory:
                    audio = Path(directory) / "recording.wav"
                    normalize_recording(root, name, metadata, audio, settings)
                    result = backend.analyze(audio, source=name, metadata=metadata, cache_key=key)
                save_checkpoint(path, result.model_dump(mode="json"))
            results.append(result)
        identity = fingerprint([r.cache_key for r in results])
        save_checkpoint(
            root / "diarization.json",
            {
                "schema_version": 1,
                "identity": identity,
                "pause_tolerance_ms": pause_tolerance_ms,
                "sources": [r.model_dump(mode="json") for r in results],
            },
        )
    from app.evaluation.speaking.replay_segment_review import generate_proposals

    proposal = generate_proposals(root)
    return proposal, reused
