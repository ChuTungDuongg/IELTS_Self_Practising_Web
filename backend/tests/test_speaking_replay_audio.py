"""Synthetic FFmpeg integration; no copyrighted recording or live provider."""

import hashlib
import json
import math
import shutil
import subprocess
import wave

import pytest

from app.core.config import Settings
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_audio import normalize_window, probe_audio, resolve_source
from app.evaluation.speaking.replay_manifest import prepare, validate
from app.evaluation.speaking.replay_models import ReplaySegment


@pytest.fixture
def settings():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip(
            "FFmpeg integration requires ffmpeg and ffprobe; exercised in Linux CPU container"
        )
    return Settings(_env_file=None)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "full_speaking.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
        data = b"".join(
            int(8000 * math.sin(i / 23)).to_bytes(2, "little", signed=True) * 2
            for i in range(44100 * 3)
        )
        output.writeframes(data)
    return path


@pytest.mark.parametrize("kind", ["wav", "mp3"])
def test_real_decode_probe_and_window_preserves_original(source, settings, tmp_path, kind):
    path = source
    if kind == "mp3":
        path = source.with_suffix(".mp3")
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), str(path)], check=True)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = probe_audio(path, settings)
    assert metadata["format"] == kind and metadata["sample_rate"] == 44100
    segment = ReplaySegment(
        id="part2", part_number=2, start_ms=500, end_ms=2500, prompt_type="LONG_TURN"
    )
    audio = normalize_window(
        tmp_path, path.name, metadata, segment, tmp_path / "normalized.wav", settings
    )
    assert 1999 <= audio.duration_ms <= 2001
    with wave.open(str(audio.path)) as actual:
        assert (actual.getnchannels(), actual.getframerate(), actual.getsampwidth()) == (
            1,
            16000,
            2,
        )
    assert audio.timeline[0].source_start_ms == 500
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_empty_corrupt_and_oversized_are_rejected_before_provider(tmp_path, settings):
    for data in (b"", b"not-audio", b"ID3invalid"):
        path = tmp_path / "corrupt.mp3"
        path.write_bytes(data)
        with pytest.raises(BenchmarkInputError):
            probe_audio(path, settings)
    with path.open("wb") as output:
        output.truncate(128 * 1024 * 1024 + 1)
    with pytest.raises(BenchmarkInputError, match="SIZE_INVALID"):
        probe_audio(path, settings)


def test_prepare_is_unverified_and_does_not_overwrite_operator_data(source, settings, tmp_path):
    prepared, created = prepare(tmp_path, settings)
    assert created and not prepared.candidate_only_verified
    assert all(row.start_ms is None and not row.prompt_text for row in prepared.segments)
    text = (tmp_path / "segments.json").read_text()
    assert prepare(tmp_path, settings)[1] is False
    assert (tmp_path / "segments.json").read_text() == text
    assert "SPEAKER_NOT_VERIFIED" in validate(tmp_path, settings)[0].grading_limitations()


def test_part_files_prepare_each_part_without_assuming_speaker(source, settings, tmp_path):
    for part in (1, 2, 3):
        shutil.copyfile(source, tmp_path / f"part{part}.wav")
    source.unlink()
    prepared, _ = prepare(tmp_path, settings)
    assert [s.part_number for s in prepared.segments] == [1, 2, 3]
    assert all(s.speaker_role == "unknown" for s in prepared.segments)


def test_bounds_and_production_cap_cannot_be_bypassed(source, settings, tmp_path):
    prepare(tmp_path, settings)
    value = json.loads((tmp_path / "segments.json").read_text())
    value["segments"][0].update(start_ms=0, end_ms=4000, speaker_role="candidate")
    (tmp_path / "segments.json").write_text(json.dumps(value))
    with pytest.raises(BenchmarkInputError, match="RANGE_INVALID"):
        validate(tmp_path, settings)
    metadata = probe_audio(source, settings)
    metadata["duration_ms"] = 840000
    segment = ReplaySegment(
        id="full", part_number=2, start_ms=0, end_ms=840000, prompt_type="LONG_TURN"
    )
    with pytest.raises(BenchmarkInputError, match="DURATION_EXCEEDED"):
        normalize_window(
            tmp_path, source.name, metadata, segment, tmp_path / "normalized.wav", settings
        )
    assert not (tmp_path / "normalized.wav").exists()


def test_real_header_is_checked_not_extension(source, settings, tmp_path):
    renamed = tmp_path / "renamed.mp3"
    source.rename(renamed)
    assert probe_audio(resolve_source(tmp_path, renamed.name), settings)["format"] == "wav"


def test_fourteen_minute_source_is_extracted_as_windows_not_one_response(settings, tmp_path):
    path = tmp_path / "full_speaking.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
        for _ in range(840):
            output.writeframes(b"\x80" * 8000)
    metadata = probe_audio(path, settings)
    assert metadata["duration_ms"] == 840000
    for part, start in ((1, 10000), (2, 300000), (3, 700000)):
        segment = ReplaySegment(
            id=f"p{part}",
            part_number=part,
            start_ms=start,
            end_ms=start + 2000,
            prompt_type="LONG_TURN" if part == 2 else "SHORT_ANSWER",
        )
        audio = normalize_window(
            tmp_path, path.name, metadata, segment, tmp_path / f"p{part}.wav", settings
        )
        assert audio.duration_ms == 2000 and audio.timeline[0].source_start_ms == start
    assert settings.speaking_max_decoded_seconds == 600
