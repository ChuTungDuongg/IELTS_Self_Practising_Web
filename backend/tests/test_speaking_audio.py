"""Tiny PCM fixtures and metadata boundaries; never execute FFmpeg/models."""

import math
import wave
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.schemas.speaking_ai import AudioMetrics, AudioQualityConfig
from app.services.speaking_audio import NormalizedAudio
from app.services.speaking_quality import assess_audio_quality, classify_quality


def pcm(tmp_path, samples, *, segment_count=1):
    path = tmp_path / "synthetic.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(
            b"".join(
                int(max(-32768, min(32767, n))).to_bytes(2, "little", signed=True) for n in samples
            )
        )
    return NormalizedAudio(
        path, "source", "pcm-v1", "cache", len(samples) * 1000 // 16000, segment_count=segment_count
    )


def healthy(**changes):
    return AudioMetrics(
        duration_seconds=3,
        speech_seconds=2,
        rms=0.1,
        clipping_ratio=0,
        background_proxy_ratio=0,
        **changes,
    )


@pytest.mark.parametrize(
    "field,threshold,failing,direction",
    [
        ("duration_seconds", "minimum_duration_seconds", "TOO_SHORT", "below"),
        ("speech_seconds", "minimum_speech_seconds", "TOO_SHORT", "below"),
        ("rms", "minimum_rms", "VERY_LOW_SIGNAL", "below"),
        ("clipping_ratio", "maximum_clipping_ratio", "SEVERE_CLIPPING", "at"),
        ("background_proxy_ratio", "maximum_background_ratio", "BACKGROUND_DOMINANT", "at"),
    ],
)
@pytest.mark.parametrize("offset", [-1e-6, 0, 1e-6])
def test_quality_threshold_boundaries(field, threshold, failing, direction, offset):
    config = AudioQualityConfig(minimum_duration_seconds=2)
    metrics = healthy().model_copy(update={field: getattr(config, threshold) + offset})
    if field == "duration_seconds":
        metrics.speech_seconds = 1
    result = classify_quality(metrics, config)
    fails = offset < 0 if direction == "below" else offset >= 0
    assert result == (failing if fails else "AUDIO_OK")


@pytest.mark.parametrize(
    "kind,state",
    [
        ("normal", "AUDIO_OK"),
        ("silence", "NO_SPEECH"),
        ("low", "VERY_LOW_SIGNAL"),
        ("clipped", "SEVERE_CLIPPING"),
        ("noise", "BACKGROUND_DOMINANT"),
        ("short", "TOO_SHORT"),
        ("corrupt", "AUDIO_CORRUPT"),
        ("asr", "ASR_UNUSABLE"),
    ],
)
def test_synthetic_quality_states_are_explicit_without_scores(tmp_path, kind, state):
    length = 3200 if kind == "short" else 32000
    amplitude = 0 if kind == "silence" else 30 if kind == "low" else 5000
    samples = (
        [32767 if n % 2 else -32768 for n in range(length)]
        if kind in {"clipped", "noise"}
        else [int(amplitude * math.sin(n / 10)) for n in range(length)]
    )
    if kind == "noise":
        samples = [n // 8 for n in samples]
    audio = pcm(tmp_path, samples)
    if kind == "corrupt":
        audio.path.write_bytes(b"invalid container")
    before = audio.path.read_bytes()
    result = assess_audio_quality(
        audio, AudioQualityConfig(), asr_usable=False if kind == "asr" else None
    )
    assert result.state == state and result.assessable == (state == "AUDIO_OK")
    assert audio.path.read_bytes() == before
    assert not {"score", "band", "ielts_band"} & result.model_dump().keys()
    assert str(tmp_path) not in result.model_dump_json()


def test_quality_identity_and_recovery_metadata(tmp_path):
    audio = pcm(tmp_path, [5000] * 32000, segment_count=2)
    config = AudioQualityConfig()
    first = assess_audio_quality(audio, config)
    assert first.metrics.duration_seconds == 2 and first.metrics.speech_seconds == 2
    assert first.metrics.segment_count == 2 and first.metrics.recovery_gaps_known is False
    assert assess_audio_quality(audio, config) == first
    assert (
        assess_audio_quality(replace(audio, source_audio_fingerprint="other"), config).cache_key
        != first.cache_key
    )
    assert (
        assess_audio_quality(audio, config.model_copy(update={"version": "quality-next"})).cache_key
        != first.cache_key
    )
    assert assess_audio_quality(audio, config, asr_usable=False).cache_key != first.cache_key


@pytest.mark.parametrize(
    "field,value",
    [
        ("minimum_rms", -1),
        ("maximum_clipping_ratio", 2),
        ("minimum_duration_seconds", float("nan")),
        ("activity_rms", float("inf")),
    ],
)
def test_quality_configuration_is_bounded(field, value):
    with pytest.raises(ValidationError):
        AudioQualityConfig(**{field: value})


@pytest.mark.parametrize("offset", [-1e-6, 0, 1e-6])
def test_silence_floor_boundary(offset):
    config = AudioQualityConfig()
    metrics = healthy().model_copy(update={"rms": config.silence_floor_rms + offset})
    assert classify_quality(metrics, config) == ("NO_SPEECH" if offset <= 0 else "VERY_LOW_SIGNAL")


@pytest.mark.parametrize(
    "threshold", ["activity_rms", "clipping_amplitude", "noise_zero_crossing_ratio"]
)
@pytest.mark.parametrize("offset", [-1e-6, 0, 1e-6])
def test_sample_level_thresholds(threshold, offset, tmp_path):
    if threshold == "noise_zero_crossing_ratio":
        samples = [5000 if n % 4 < 2 else -5000 for n in range(32000)]
        exact = (
            sum((a < 0) != (b < 0) for a, b in zip(samples[:320], samples[1:320], strict=False))
            / 319
        )
        expected = "BACKGROUND_DOMINANT" if offset <= 0 else "AUDIO_OK"
    else:
        samples = [32000 if threshold == "clipping_amplitude" else 1000] * 32000
        exact = samples[0] / 32768
        expected = (
            ("SEVERE_CLIPPING" if offset <= 0 else "AUDIO_OK")
            if threshold == "clipping_amplitude"
            else ("AUDIO_OK" if offset <= 0 else "NO_SPEECH")
        )
    config = AudioQualityConfig(**{threshold: exact + offset})
    assert assess_audio_quality(pcm(tmp_path, samples), config).state == expected


def test_impossible_quality_metadata_and_contradictory_thresholds_are_rejected():
    with pytest.raises(ValidationError):
        AudioMetrics(
            duration_seconds=1,
            speech_seconds=2,
            rms=0.1,
            clipping_ratio=0,
            background_proxy_ratio=0,
        )
    with pytest.raises(ValidationError):
        AudioQualityConfig(silence_floor_rms=0.01, minimum_rms=0.005)
