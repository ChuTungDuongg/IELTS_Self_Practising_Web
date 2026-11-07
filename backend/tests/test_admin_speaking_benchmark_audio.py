"""Actual bounded FFmpeg validation on generated audio; no speech or providers."""

import math
import struct
import wave
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.evaluation.speaking.diarization_backend import LocalDiarizer
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_audio import probe_audio
from app.schemas.speaking_benchmark import SampleMetadata
from app.services.speaking_benchmark import SpeakingBenchmarkService


def synthetic_wav(path, seconds=1):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(
            b"".join(
                struct.pack("<h", round(500 * math.sin(i * 2 * math.pi * 220 / 16000)))
                for i in range(16000 * seconds)
            )
        )


def audio_settings():
    try:
        settings = LocalDiarizer().audio_settings(Settings(_env_file=None))
        import shutil

        if not shutil.which(settings.speaking_ffmpeg_path):
            pytest.skip("FFmpeg unavailable")
        return settings
    except BenchmarkInputError:
        pytest.skip("FFmpeg unavailable")


def test_actual_media_probe_ignores_extension_and_rejects_corruption(tmp_path):
    settings = audio_settings()
    source = tmp_path / "no-extension"
    synthetic_wav(source)
    info = probe_audio(source, settings)
    assert info["duration_ms"] == 1000 and info["format"] == "wav"
    source.write_bytes(b"RIFF\x00\x00\x00\x00WAVEcorrupted")
    with pytest.raises(BenchmarkInputError, match="UNREADABLE"):
        probe_audio(source, settings)
    source.write_bytes(b"not audio")
    with pytest.raises(BenchmarkInputError, match="FORMAT_INVALID"):
        probe_audio(source, settings)


async def test_maximum_duration_rejected_before_private_storage(tmp_path):
    settings = audio_settings().model_copy(
        update={"storage_root": tmp_path, "speaking_benchmark_max_duration_seconds": 1}
    )
    source = tmp_path / "source"
    synthetic_wav(source, 2)
    service = SpeakingBenchmarkService(None, uuid4(), settings=settings)
    with pytest.raises(AppError) as error:
        await service.upload(
            source,
            SampleMetadata(code="DURATION", source_note="Synthetic test", rights_confirmed=True),
        )
    assert error.value.code == "SPEAKING_BENCHMARK_DURATION_EXCEEDED"
    assert not (tmp_path / "benchmark").exists()
