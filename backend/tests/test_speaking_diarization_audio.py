"""Decoder integration is separate from any claim about speaker recognition quality."""

import hashlib
import wave

from test_speaking_replay_audio import settings, source  # noqa: F401

from app.evaluation.speaking.diarization_backend import normalize_recording
from app.evaluation.speaking.replay_audio import probe_audio


def test_whole_recording_normalization_preserves_source_and_grading_cap(source, settings, tmp_path):  # noqa: F811
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "diarization.wav"
    duration = normalize_recording(
        tmp_path, source.name, probe_audio(source, settings), destination, settings
    )
    assert duration == 3000 and settings.speaking_max_decoded_seconds == 600
    with wave.open(str(destination)) as normalized:
        assert (
            normalized.getnchannels(),
            normalized.getframerate(),
            normalized.getsampwidth(),
        ) == (1, 16000, 2)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_fourteen_minute_diarization_pcm_is_separate_from_response_cap(settings, tmp_path):  # noqa: F811
    path = tmp_path / "full_speaking.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
        for _ in range(840):
            output.writeframes(b"\x80" * 8000)
    duration = normalize_recording(
        tmp_path, path.name, probe_audio(path, settings), tmp_path / "whole.wav", settings
    )
    assert duration == 840000 and settings.speaking_max_decoded_seconds == 600
