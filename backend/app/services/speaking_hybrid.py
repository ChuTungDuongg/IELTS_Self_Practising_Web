"""Explicit coordinator: one Azure session per continuous recorder segment, shared by ASR/PR."""

import tempfile
import wave
from dataclasses import replace
from pathlib import Path

from app.core.exceptions import AppError
from app.providers.speech_analysis.azure_policy import (
    TERMINAL_AZURE_ERRORS,
    require_billing_authorization,
)
from app.schemas.speaking_ai import ASRResult, WordTiming
from app.services.speaking_audio import await_audio_thread, fingerprint


async def analyze_response(audio, settings, *, analyzer=None, on_result=None):
    import asyncio

    from app.providers.speech_analysis.azure import AzureSpeechAnalyzer

    analyzer = analyzer or AzureSpeechAnalyzer(settings)
    if not audio.timeline and audio.segment_count > 1:
        raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "Recovery timeline is unavailable.", 409)
    if not audio.timeline:
        result = await analyzer.analyze(audio)
        if on_result:
            await on_result(result)
        return [result]
    results = []
    with tempfile.TemporaryDirectory(prefix="speech-segments-") as directory:
        for mapping in audio.timeline:
            path = Path(directory) / "segment.wav"

            def extract(mapping=mapping, path=path):
                with (
                    wave.open(str(audio.path), "rb") as source,
                    wave.open(str(path), "wb") as output,
                ):
                    output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                    first = (
                        mapping.normalized_start_frame
                        if mapping.normalized_start_frame is not None
                        else mapping.normalized_start_ms * 16
                    )
                    last = (
                        mapping.normalized_end_frame
                        if mapping.normalized_end_frame is not None
                        else mapping.normalized_end_ms * 16
                    )
                    source.setpos(first)
                    output.writeframes(source.readframes(last - first))

            await await_audio_thread(asyncio.to_thread(extract))
            segment = replace(
                audio,
                path=path,
                duration_ms=(
                    (mapping.normalized_end_frame - mapping.normalized_start_frame) // 16
                    if mapping.normalized_start_frame is not None
                    else mapping.normalized_end_ms - mapping.normalized_start_ms
                ),
                segment_count=1,
                timeline=(),
                response_start_ms=0,
                cache_key=fingerprint([audio.cache_key, mapping.model_dump(mode="json")]),
            )
            result = await analyzer.analyze(
                segment,
                response_id=str(mapping.response_id),
                take_number=mapping.take_number,
                segment_id=str(mapping.segment_id),
            )
            results.append(result)
            if on_result:
                await on_result(result)
            # Each failed/partial stream is terminal here. Never blind retry a billable call.
            if result.status != "COMPLETE":
                break
    return results


def analysis_to_asr(results, audio):
    from app.providers.speech_analysis.azure import ADAPTER_VERSION

    text, words = [], []
    by_segment = {str(m.segment_id): m for m in audio.timeline}
    for result in results:
        if result.source.audio_fingerprint != audio.source_audio_fingerprint:
            raise ValueError("Speech source mismatch")
        if not result.lexical_transcript.strip():
            continue
        text.append(result.lexical_transcript)
        mapping = by_segment.get(result.source.segment_id)
        offset = mapping.normalized_start_ms if mapping else 0
        words.extend(
            WordTiming(
                word=w.text,
                start=(w.start_ms + offset) / 1000,
                end=(w.end_ms + offset) / 1000,
                confidence=w.recognition_confidence,
            )
            for w in result.words
            if w.start_ms is not None and w.end_ms is not None
        )
    if not text:
        terminal = next(
            (r.error_code for r in results if r.error_code in TERMINAL_AZURE_ERRORS), None
        )
        if terminal:
            raise AppError(
                terminal,
                "Speech resource is unavailable under the current policy.",
                429 if terminal.endswith("QUOTA_EXCEEDED") else 409,
            )
        raise AppError("ASR_UNUSABLE", "No usable lexical speech was recognized.", 409)
    return ASRResult(
        text=" ".join(text),
        words=words,
        provider="azure",
        model="service-managed-unknown",
        version=ADAPTER_VERSION,
        language=results[0].provider.locale,
        # Per-word or utterance recognition confidence is optional, never pronunciation accuracy.
        mean_confidence=None,
    )


class HybridASRProvider:
    """Compatibility facade for configuration; worker calls coordinator explicitly to share result."""

    def __init__(self, settings):
        from app.providers.speech_analysis.azure import AzureSpeechAnalyzer

        key = settings.speaking_azure_key
        if not key or not key.get_secret_value().strip() or not settings.speaking_azure_region:
            raise AppError("SPEAKING_ASR_UNAVAILABLE", "Azure Speech is not configured.", 503)
        require_billing_authorization(settings)
        self.analyzer = AzureSpeechAnalyzer(settings)
        self.settings = self.analyzer.settings
        from app.providers.speaking_asr import provider_identity

        self.identity = provider_identity(settings)

    async def transcribe(self, audio):
        return analysis_to_asr(
            await analyze_response(audio, self.settings, analyzer=self.analyzer), audio
        )
