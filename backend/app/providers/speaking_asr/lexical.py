"""Opt-in lexical recognizers. Construction never submits audio or starts a GPU."""

import asyncio
import hashlib
import time
import wave

from app.core.exceptions import AppError
from app.schemas.speech_analysis import (
    SpeechAnalysisIdentity,
    SpeechAnalysisResult,
    SpeechAnalysisSource,
    SpeechCapabilities,
    SpeechCoverage,
    SpeechUsage,
    SpeechUtterance,
    SpeechWord,
)
from app.services.speaking_audio import await_audio_thread, fingerprint

PROVIDERS = ("azure_pa", "azure_stt", "faster_whisper_local", "faster_whisper_modal")


def selection(settings):
    return getattr(settings, "speaking_lexical_asr_provider", "azure_pa")


def whisper_settings(settings, provider):
    return settings.model_copy(update={"speaking_asr_provider": provider})


def lexical_identity(settings, strategy=None):
    from app.providers.speaking_asr import provider_identity
    from app.providers.speech_analysis.azure import azure_analysis_identity, azure_stt_identity

    strategy = strategy or selection(settings)
    if strategy == "azure_pa":
        return azure_analysis_identity(settings)
    if strategy == "azure_stt":
        return azure_stt_identity(settings)
    if strategy not in PROVIDERS:
        raise AppError("SPEAKING_LEXICAL_ASR_UNAVAILABLE", "Unknown lexical provider.", 503)
    native = provider_identity(
        whisper_settings(settings, "modal" if strategy.endswith("modal") else "local")
    )
    config = {
        "strategy": strategy,
        "model_identity": fingerprint(native),
        "decode_policy": "existing-faster-whisper-v1",
        "remote": strategy.endswith("modal"),
        "model": native["model"],
        "model_revision": settings.speaking_asr_model_revision,
        "model_version": native["version"],
    }
    return SpeechAnalysisIdentity(
        provider=strategy,
        adapter_version="independent-lexical-v1",
        model_version=native["version"],
        locale=settings.speaking_asr_language,
        configuration=config,
        configuration_fingerprint=fingerprint([native, config]),
    )


def require_lexical_permission(settings, strategy=None, *, duration_ms=None):
    """Operator estimates admit a request; they are neither prices nor invoice caps."""
    strategy = strategy or selection(settings)
    if strategy == "azure_pa":
        return
    if strategy not in PROVIDERS:
        raise AppError("SPEAKING_LEXICAL_ASR_UNAVAILABLE", "Unknown lexical provider.", 503)
    if strategy == "faster_whisper_local":
        return
    estimate = settings.speaking_lexical_asr_estimated_cost_usd_per_minute
    budget = settings.speaking_lexical_asr_max_estimated_cost_usd_per_response
    if (
        not settings.speaking_lexical_asr_allow_additional_requests
        or estimate is None
        or budget is None
        or strategy == "faster_whisper_modal"
        and (not settings.speaking_lexical_asr_allow_gpu or estimate <= 0)
    ):
        raise AppError(
            "SPEAKING_LEXICAL_ASR_NOT_AUTHORIZED",
            "Independent speech requests require explicit permission and a budget.",
            409,
        )
    if duration_ms is not None and estimate * duration_ms / 60000 > budget:
        raise AppError(
            "SPEAKING_LEXICAL_ASR_BUDGET_EXCEEDED",
            "The lexical speech estimate exceeds the response budget.",
            409,
        )


class WhisperLexicalAnalyzer:
    def __init__(self, settings, strategy):
        from app.providers.speaking_asr import create_provider

        self.identity = lexical_identity(settings, strategy)
        self.strategy = strategy
        configured = whisper_settings(settings, "modal" if strategy.endswith("modal") else "local")
        self.provider = create_provider(configured)

    async def analyze(self, audio, *, response_id=None, take_number=None, segment_id=None):
        from app.schemas.speaking_ai import ASRResult

        start = time.monotonic()

        def pcm_hash():
            with wave.open(str(audio.path), "rb") as source:
                return hashlib.sha256(source.readframes(source.getnframes())).hexdigest()

        digest = await await_audio_thread(asyncio.to_thread(pcm_hash))
        result = ASRResult.model_validate(await self.provider.transcribe(audio))
        if any(w.end * 1000 > audio.duration_ms for w in result.words):
            raise AppError(
                "SPEAKING_LEXICAL_ASR_UNAVAILABLE", "Lexical word timing exceeds audio.", 503
            )
        uid = "lex_" + fingerprint([audio.cache_key, self.identity.model_dump(), segment_id])[:24]
        words = [
            SpeechWord(
                evidence_id=f"{uid}_w{i}",
                utterance_id=uid,
                text=w.word,
                start_ms=round(w.start * 1000),
                end_ms=round(w.end * 1000),
                recognition_confidence=w.confidence,
            )
            for i, w in enumerate(result.words)
        ]
        first = words[0].start_ms if words else None
        last = words[-1].end_ms if words else None
        return SpeechAnalysisResult(
            provider=self.identity,
            source=SpeechAnalysisSource(
                audio_fingerprint=audio.source_audio_fingerprint,
                normalized_audio_fingerprint=digest,
                duration_ms=audio.duration_ms,
                response_id=str(response_id) if response_id is not None else None,
                take_number=take_number,
                segment_id=str(segment_id) if segment_id is not None else None,
            ),
            status="COMPLETE",
            lexical_transcript=result.text,
            utterances=[
                SpeechUtterance(
                    evidence_id=uid, lexical_text=result.text, start_ms=first, end_ms=last
                )
            ],
            words=words,
            coverage=SpeechCoverage(
                audio_duration_ms=audio.duration_ms,
                stream_completed=True,
                final_utterance_count=1,
                word_count=len(words),
                timed_word_count=len(words),
                recognized_span_ms=(last - first) if words else 0,
                confidence_word_count=sum(w.recognition_confidence is not None for w in words),
            ),
            capabilities=SpeechCapabilities(
                continuous_recognition=False,
                unscripted=False,
                word_timing_observed=True if words else None,
                recognition_confidence_observed=True
                if any(w.recognition_confidence is not None for w in words)
                else None,
            ),
            usage=SpeechUsage(
                attempted_calls=1,
                submitted_audio_ms=audio.duration_ms,
                successful_calls=1,
                outcome="COMPLETED",
                billing_uncertain=self.strategy.endswith("modal"),
            ),
            latency_ms=int((time.monotonic() - start) * 1000),
            limitations=[
                "ASR_IS_NOT_GROUND_TRUTH",
                "ASR_DISFLUENCIES_NOT_GUARANTEED",
                "NO_CROSS_PROVIDER_ALIGNMENT",
            ]
            + (["WORD_TIMING_UNAVAILABLE"] if not words else []),
        )


def create_lexical_analyzer(settings, strategy=None):
    strategy = strategy or selection(settings)
    if strategy == "azure_pa":
        raise ValueError("Azure PA must reuse its existing analysis, not make another request")
    require_lexical_permission(settings, strategy)
    if strategy == "azure_stt":
        from app.providers.speech_analysis.azure import AzureSpeechAnalyzer

        return AzureSpeechAnalyzer(settings, pronunciation=False)
    return WhisperLexicalAnalyzer(settings, strategy)
