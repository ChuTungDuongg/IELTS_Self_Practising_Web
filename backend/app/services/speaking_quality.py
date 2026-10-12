"""Explainable technical quality proxies. No linguistic/IELTS scoring rules."""

import math
import sys
import wave
from array import array

from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.speaking_transcript import SpeakingNormalizedAudio
from app.schemas.speaking_ai import AudioMetrics, AudioQualityConfig, AudioQualityResult
from app.services.speaking_audio import NormalizedAudio, fingerprint, wav_duration


def quality_identity(settings):
    return settings.speaking_quality.model_dump()


def read_pcm(audio: NormalizedAudio):
    if not isinstance(audio, NormalizedAudio) or audio.channels != 1 or audio.sample_rate != 16000:
        raise ValueError("Normalized audio is required")
    if wav_duration(audio.path, 1800) != audio.duration_ms:
        raise ValueError("Normalized duration mismatch")
    with wave.open(str(audio.path), "rb") as source:
        samples = array("h", source.readframes(source.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def measure_audio(audio: NormalizedAudio, config: AudioQualityConfig):
    samples = read_pcm(audio)
    activity = noisy = clipping = 0
    squared = 0
    # Twenty-millisecond energy frames are an activity proxy, not a learned VAD
    # or proof of linguistic speech. Sustained high ZCR is a noise proxy only.
    for start in range(0, len(samples), 320):
        frame = samples[start : start + 320]
        power = sum((n / 32768) ** 2 for n in frame)
        squared += power
        clipping += sum(abs(n / 32768) >= config.clipping_amplitude for n in frame)
        if math.sqrt(power / len(frame)) >= config.activity_rms:
            activity += len(frame)
            crossings = sum((a < 0) != (b < 0) for a, b in zip(frame, frame[1:], strict=False))
            if crossings / max(1, len(frame) - 1) >= config.noise_zero_crossing_ratio:
                noisy += len(frame)
    return AudioMetrics(
        duration_seconds=len(samples) / 16000,
        speech_seconds=activity / 16000,
        rms=math.sqrt(squared / len(samples)),
        clipping_ratio=clipping / len(samples),
        background_proxy_ratio=noisy / activity if activity else 0,
        segment_count=audio.segment_count,
        recovery_gaps_known=audio.segment_count == 1,
    )


def classify_quality(metrics, config, *, asr_usable=None):
    if metrics is None:
        return "AUDIO_CORRUPT"
    if metrics.rms <= config.silence_floor_rms:
        return "NO_SPEECH"
    if metrics.rms < config.minimum_rms:
        return "VERY_LOW_SIGNAL"
    if metrics.clipping_ratio >= config.maximum_clipping_ratio:
        return "SEVERE_CLIPPING"
    if metrics.background_proxy_ratio >= config.maximum_background_ratio:
        return "BACKGROUND_DOMINANT"
    if not metrics.speech_seconds:
        return "NO_SPEECH"
    if (
        metrics.duration_seconds < config.minimum_duration_seconds
        or metrics.speech_seconds < config.minimum_speech_seconds
    ):
        return "TOO_SHORT"
    if asr_usable is False:
        return "ASR_UNUSABLE"
    return "AUDIO_OK"


def assess_audio_quality(audio, config=None, *, asr_usable=None):
    config = config or AudioQualityConfig()
    try:
        metrics = measure_audio(audio, config)
    except (AppError, ValueError, OSError, EOFError, wave.Error):
        metrics = None
    state = classify_quality(metrics, config, asr_usable=asr_usable)
    return AudioQualityResult(
        state=state,
        assessable=state == "AUDIO_OK",
        metrics=metrics,
        config=config,
        source_audio_fingerprint=audio.source_audio_fingerprint,
        cache_key=fingerprint(
            [audio.source_audio_fingerprint, audio.cache_key, config.model_dump(), asr_usable]
        ),
        asr_usable=asr_usable,
    )


async def persist_quality_result(session, audio, result):
    async with session.begin():
        row = await session.scalar(
            select(SpeakingNormalizedAudio)
            .where(
                SpeakingNormalizedAudio.cache_key == audio.cache_key,
                SpeakingNormalizedAudio.source_audio_fingerprint == audio.source_audio_fingerprint,
            )
            .with_for_update()
        )
        if row:
            row.metadata_json = {**row.metadata_json, "quality": result.model_dump(mode="json")}
