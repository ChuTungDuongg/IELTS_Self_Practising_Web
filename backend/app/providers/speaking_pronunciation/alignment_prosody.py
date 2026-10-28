"""Bounded CPU acoustic proxies, without phonetic models or score mappings."""

import asyncio
import math
import wave
from statistics import mean, pstdev

from app.core.exceptions import AppError
from app.schemas.speaking_ai import PronunciationEvidence
from app.services.speaking_audio import NormalizedAudio, await_audio_thread
from app.services.speaking_features import tokens, validate_alignment
from app.services.speaking_quality import classify_quality, measure_audio, read_pcm


def coefficient(values):
    average = mean(values) if values else 0
    return pstdev(values) / average if average and len(values) > 1 else None


def pitch(frame, minimum_correlation):
    # Downsample to 4kHz and centre a 40ms frame. Search 80..400Hz; these are
    # pitch proxies, not word stress, accent correctness or phoneme evidence.
    downsampled = list(frame[::4])
    centre = mean(downsampled)
    values = [value - centre for value in downsampled]
    if not any(values):
        return None
    correlations = []
    for offset in range(10, 51):
        a, b = values[:-offset], values[offset:]
        denominator = math.sqrt(sum(n * n for n in a) * sum(n * n for n in b))
        correlation = (
            sum(x * y for x, y in zip(a, b, strict=True)) / denominator if denominator else 0
        )
        correlations.append(correlation)
    # Choose the first credible local period peak. A global maximum can select
    # a multiple of the period and incorrectly report a subharmonic.
    for index, correlation in enumerate(correlations):
        if (
            correlation >= minimum_correlation
            and correlation >= correlations[max(0, index - 1)]
            and correlation >= correlations[min(len(correlations) - 1, index + 1)]
        ):
            return 4000 / (index + 10)
    return None


class AlignmentProsodyProvider:
    def __init__(self, config, quality_config):
        self.config, self.quality_config = config, quality_config

    async def analyse(self, audio, transcript, alignment):
        if not isinstance(audio, NormalizedAudio):
            raise ValueError("Normalized audio is required")
        return await await_audio_thread(
            asyncio.to_thread(self._analyse, audio, transcript, alignment)
        )

    def _analyse(self, audio, transcript, alignment):
        base = dict(
            version=self.config.version, source_audio_fingerprint=audio.source_audio_fingerprint
        )
        try:
            metrics = measure_audio(audio, self.quality_config)
            samples = read_pcm(audio)
        except (AppError, OSError, ValueError, wave.Error, EOFError):
            return PronunciationEvidence(
                **base,
                status="UNAVAILABLE",
                error_code="AUDIO_UNAVAILABLE",
                limitations=["AUDIO_UNAVAILABLE"],
            )
        if classify_quality(metrics, self.quality_config) != "AUDIO_OK":
            return PronunciationEvidence(
                **base,
                status="UNAVAILABLE",
                error_code="AUDIO_QUALITY_UNAVAILABLE",
                rms=metrics.rms,
                limitations=["AUDIO_QUALITY_UNAVAILABLE"],
            )
        words, text_words = validate_alignment(audio, alignment), tokens(transcript)
        coverage = (
            min(1, sum(len(tokens(w.word)) for w in words) / len(text_words)) if text_words else 0
        )
        low = [
            w
            for w in words
            if w.confidence is not None and w.confidence < self.config.low_confidence_threshold
        ]
        confidence = [w.confidence for w in words if w.confidence is not None]
        step = max(
            640,
            math.ceil(max(1, len(samples) - 639) / self.config.maximum_pitch_frames / 640) * 640,
        )
        pitches, energies = [], []
        for start in range(0, len(samples) - 639, step):
            frame = samples[start : start + 640]
            rms = math.sqrt(sum((n / 32768) ** 2 for n in frame) / len(frame))
            if rms >= self.quality_config.activity_rms:
                energies.append(rms)
                estimate = pitch(frame, self.config.minimum_pitch_correlation)
                if estimate is not None:
                    pitches.append(estimate)
        word_energy = []
        for word in words[:200]:
            frame = samples[int(word.start * 16000) : int(word.end * 16000)]
            if frame:
                word_energy.append(math.sqrt(sum((n / 32768) ** 2 for n in frame) / len(frame)))
        limitations = [
            "PHONEME_ALIGNMENT_UNAVAILABLE",
            "LINGUISTIC_STRESS_UNAVAILABLE",
            "LISTENER_EFFORT_UNAVAILABLE",
            "ASR_CONFIDENCE_PROXY_ONLY",
            "PITCH_ENERGY_PROXIES",
        ]
        if audio.segment_count > 1:
            limitations.append("RECOVERY_GAP_BOUNDARIES_UNAVAILABLE")
        aligned_tokens = [item for word in words for item in tokens(word.word)]
        complete = bool(text_words) and aligned_tokens == text_words and audio.segment_count == 1
        usable = (
            complete
            and len(words) >= self.config.minimum_aligned_words
            and len(confidence) == len(words)
            and not low
            and bool(pitches)
        )
        if not complete:
            limitations.append("ALIGNMENT_INCOMPLETE")
        return PronunciationEvidence(
            **base,
            status="AVAILABLE" if usable else "LOW_EVIDENCE",
            alignment_word_count=len(words),
            alignment_coverage=coverage,
            confidence_coverage=len(confidence) / len(words) if words else 0,
            low_confidence_count=len(low),
            mean_alignment_confidence=mean(confidence) if confidence else None,
            low_confidence_spans=low[:200],
            word_duration_cv=coefficient([w.end - w.start for w in words]) if complete else None,
            inter_word_gap_mean_seconds=mean(
                [b.start - a.end for a, b in zip(words, words[1:], strict=False)]
            )
            if complete and len(words) > 1
            else None,
            rms=metrics.rms,
            energy_cv=coefficient(energies),
            word_energy_cv=coefficient(word_energy) if complete else None,
            acoustic_frame_count=len(energies),
            voiced_pitch_frames=len(pitches),
            pitch_mean_hz=mean(pitches) if pitches else None,
            pitch_range_hz=max(pitches) - min(pitches) if pitches else None,
            intelligibility_proxy=mean(confidence)
            if complete and confidence and len(confidence) == len(words)
            else None,
            limitations=limitations,
        )
