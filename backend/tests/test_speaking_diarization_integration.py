"""Operator opt-in only: requires private legally usable, human-verified two-speaker speech."""

import json
import os
import tempfile
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("SPEAKING_DIARIZATION_INTEGRATION") != "1",
    reason="Opt-in real-speech model test; no automatic weights/download/API calls",
)
def test_pinned_local_model_on_private_two_speaker_fixture():
    from app.core.config import Settings
    from app.evaluation.speaking.diarization_backend import ROOT, LocalDiarizer, normalize_recording
    from app.evaluation.speaking.replay_audio import probe_audio, resolve_source
    from app.evaluation.speaking.replay_manifest import discover, private_root
    from app.services.speaking_audio import fingerprint

    root = private_root(
        Path(os.environ["SPEAKING_DIARIZATION_INTEGRATION_INPUT"]),
        ROOT / "benchmarks/speaking/private",
    )
    declaration = json.loads((root / "integration-permission.json").read_text(encoding="utf-8"))
    assert declaration["legally_usable"] is True and declaration["human_verified_speakers"] >= 2
    before = (root / "segments.json").read_bytes() if (root / "segments.json").exists() else None
    sources = discover(root)
    assert len(sources) == 1, "Use one small legally usable two-speaker recording"
    name = sources[0]
    settings = Settings(_env_file=None)
    metadata = probe_audio(resolve_source(root, name), settings)
    assert metadata["duration_ms"] <= 120000, "Integration fixture must be at most two minutes"
    # Bypass only the local diarization cache: this opt-in test must actually execute the model.
    with tempfile.TemporaryDirectory(prefix="diarization-integration-") as directory:
        audio = Path(directory) / "recording.wav"
        normalize_recording(root, name, metadata, audio, settings)
        result = LocalDiarizer().analyze(
            audio, source=name, metadata=metadata, cache_key=fingerprint(metadata)
        )
    assert len({turn.speaker_id for turn in result.regular}) >= 2
    if before is not None:
        assert (root / "segments.json").read_bytes() == before
    # This verifies model execution, not DER, accent fairness or grading accuracy.
