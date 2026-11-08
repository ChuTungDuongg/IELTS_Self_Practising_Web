"""Deterministic response evidence from VERBATIM and accepted audio only."""

import asyncio
import re
from statistics import mean, median

from app.schemas.speaking_ai import ASRResult, FluencyEvidence, SpeakingFeatureBundle, WordTiming
from app.services.speaking_audio import NormalizedAudio, await_audio_thread, fingerprint
from app.services.speaking_hybrid_features import extract_hybrid_fluency
from app.services.speaking_quality import assess_audio_quality

FEATURE_VERSION = "fluency-v1"
PAUSE_SECONDS = 0.25
LONG_PAUSE_SECONDS = 2


def tokens(text):
    if not isinstance(text, str) or len(text) > 60000:
        raise ValueError("Invalid transcript evidence")
    return re.findall(r"\b\w+(?:['’]\w+)*\b", text.casefold())


def validate_alignment(audio, words):
    if len(words) > 10000:
        raise ValueError("Invalid alignment length")
    validated = [WordTiming.model_validate(w) for w in words]
    if any(w.end > audio.duration_ms / 1000 for w in validated) or any(
        b.start < a.end for a, b in zip(validated, validated[1:], strict=False)
    ):
        raise ValueError("Invalid alignment timing")
    return validated


def feature_identity(settings):
    if settings.speaking_profile == "speaking_hybrid_v1":
        from app.services.speaking_vad import VAD_VERSION

        return {
            "profile": "speaking_hybrid_v1",
            "fluency": "fluency-v2",
            "evidence": "evidence-v3"
            if getattr(settings, "speaking_lexical_asr_provider", "azure_pa") != "azure_pa"
            else "evidence-v2",
            "vad": VAD_VERSION,
            "vad_checksum": settings.speaking_vad_model_sha256,
            "pause_ms": 250,
            "long_pause_ms": 2000,
            "eligibility": "coverage-v1",
            "projection": "stratified-pr-300-v1",
            "feedback": "validated-audio-ids-v1",
            **(
                {"lexical_projection": "independent-lexical-v1"}
                if getattr(settings, "speaking_lexical_asr_provider", "azure_pa") != "azure_pa"
                else {}
            ),
        }
    return {
        "fluency": FEATURE_VERSION,
        "pause_seconds": PAUSE_SECONDS,
        "long_pause_seconds": LONG_PAUSE_SECONDS,
        "pronunciation_enabled": settings.speaking_pronunciation_enabled,
        "pronunciation": settings.speaking_pronunciation.model_dump(),
    }


def phrase_repetitions(items):
    count, position = 0, 0
    while position < len(items):
        repeated = next(
            (
                size
                for size in range(4, 1, -1)
                if position + size * 2 <= len(items)
                and items[position : position + size]
                == items[position + size : position + 2 * size]
            ),
            None,
        )
        if repeated:
            count += 1
            position += repeated * 2
        else:
            position += 1
    return count


def extract_fluency_features(audio, verbatim_transcript, words, *, part_number=None):
    if not isinstance(audio, NormalizedAudio) or not 0 <= audio.duration_ms <= 1800000:
        raise ValueError("Normalized audio metadata is required")
    items, alignment = tokens(verbatim_transcript), validate_alignment(audio, words)
    aligned = [item for word in alignment for item in tokens(word.word)]
    # Exact token agreement prevents a partial/mismatched alignment from turning
    # unaligned words into apparent silence. Whitespace/punctuation may differ.
    complete = bool(items) and aligned == items
    status = "COMPLETE" if complete else "PARTIAL" if aligned else "UNAVAILABLE"
    duration = audio.duration_ms / 1000
    limitations = ["LEXICAL_DISFLUENCY_PROXIES"]
    data = dict(
        timing_status=status,
        total_duration_seconds=duration,
        word_count=len(items),
        aligned_word_count=len(aligned),
        timing_coverage=min(1, len(aligned) / len(items)) if items else 0,
        words_per_minute=len(items) * 60 / duration if duration else None,
        filled_pause_count=sum(w in {"um", "uh"} for w in items),
        token_repetition_count=sum(a == b for a, b in zip(items, items[1:], strict=False)),
        phrase_repetition_count=phrase_repetitions(items),
        false_start_count=len(re.findall(r"\b\w+[-—–]\s+\w", verbatim_transcript)),
        self_correction_count=len(re.findall(r"\bi\s+mean\b", verbatim_transcript, re.IGNORECASE)),
        limitations=limitations,
    )
    if complete:
        speech = min(duration, sum(w.end - w.start for w in alignment))
        data.update(
            speech_duration_seconds=speech,
            silence_duration_seconds=duration - speech,
            speech_ratio=speech / duration if duration else 0,
            silence_ratio=(duration - speech) / duration if duration else 0,
            articulation_rate=len(items) * 60 / speech if speech else None,
        )
    else:
        limitations.append("WORD_TIMING_INCOMPLETE")
    if audio.segment_count > 1:
        limitations.append("RECOVERY_GAP_BOUNDARIES_UNAVAILABLE")
    elif complete:
        gaps = [b.start - a.end for a, b in zip(alignment, alignment[1:], strict=False)]
        pauses = [gap for gap in gaps if gap >= PAUSE_SECONDS]
        long_count = sum(gap >= LONG_PAUSE_SECONDS for gap in pauses)
        turns, start = [], alignment[0].start
        for a, b in zip(alignment, alignment[1:], strict=False):
            if b.start - a.end >= LONG_PAUSE_SECONDS:
                turns.append(a.end - start)
                start = b.start
        turns.append(alignment[-1].end - start)
        data.update(
            pause_count=len(pauses),
            mean_pause_seconds=mean(pauses) if pauses else 0,
            median_pause_seconds=median(pauses) if pauses else 0,
            max_pause_seconds=max(pauses, default=0),
            long_pause_count=long_count,
            long_pause_ratio=long_count / len(pauses) if pauses else 0,
            average_turn_seconds=mean(turns),
            part2_sustained_seconds=max(turns) if part_number == 2 else None,
        )
    return FluencyEvidence(**data)


async def build_feature_bundle(
    audio,
    transcript: ASRResult,
    settings,
    *,
    part_number=None,
    speech_analysis=None,
    lexical_analysis=None,
    vad_result=None,
):
    from app.providers.speaking_pronunciation import create_provider

    transcript = ASRResult.model_validate(transcript)
    quality = await await_audio_thread(
        asyncio.to_thread(assess_audio_quality, audio, settings.speaking_quality, asr_usable=True)
    )
    if settings.speaking_profile == "speaking_hybrid_v1":
        from app.services.speaking_hybrid_features import pronunciation_from_analysis
        from app.services.speaking_vad import measure_vad_async

        if speech_analysis is None:
            raise ValueError("Hybrid features require the shared speech analysis result")
        vad = vad_result if vad_result is not None else await measure_vad_async(audio, settings)
        fluency = extract_hybrid_fluency(
            audio, transcript.text, transcript.words, vad, part_number=part_number
        )
        return SpeakingFeatureBundle(
            version="evidence-v3" if lexical_analysis is not None else "evidence-v2",
            profile="speaking_hybrid_v1",
            timeline=list(audio.timeline),
            speech_analysis=speech_analysis,
            lexical_analysis=lexical_analysis,
            source_audio_fingerprint=audio.source_audio_fingerprint,
            quality=quality,
            fluency=fluency,
            pronunciation=pronunciation_from_analysis(audio, speech_analysis),
            cache_key=fingerprint(
                [
                    audio.cache_key,
                    feature_identity(settings),
                    transcript.model_dump(),
                    [r.model_dump(mode="json") for r in speech_analysis],
                    *(
                        [[r.model_dump(mode="json") for r in lexical_analysis]]
                        if lexical_analysis is not None
                        else []
                    ),
                    part_number,
                ]
            ),
        )
    fluency = extract_fluency_features(
        audio, transcript.text, transcript.words, part_number=part_number
    )
    pronunciation = await create_provider(settings).analyse(
        audio, transcript.text, transcript.words
    )
    return SpeakingFeatureBundle(
        cache_key=fingerprint(
            [
                audio.cache_key,
                transcript.model_dump(),
                quality.cache_key,
                feature_identity(settings),
                part_number,
            ]
        ),
        source_audio_fingerprint=audio.source_audio_fingerprint,
        quality=quality,
        fluency=fluency,
        pronunciation=pronunciation,
    )
