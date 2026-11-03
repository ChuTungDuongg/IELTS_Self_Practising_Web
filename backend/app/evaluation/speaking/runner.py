"""Private, sequential benchmark adapter to the production P4/P5/P6 pipeline."""

import asyncio
import hashlib
import json
import tempfile
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.core.exceptions import AppError
from app.evaluation.speaking.manifest import BenchmarkInputError, load_predictions
from app.evaluation.speaking.models import (
    EvaluationTelemetry,
    InferenceSample,
    Prediction,
    PredictionSet,
    Reason,
    SpeechEvaluationTelemetry,
    provenance,
)
from app.evaluation.speaking.report import atomic_write
from app.schemas.speaking_ai import ASRResult
from app.services.speaking_audio import (
    NormalizedAudio,
    _render,
    await_audio_thread,
    execute_ffmpeg,
    fingerprint,
    wav_duration,
)
from app.services.speaking_features import build_feature_bundle
from app.services.speaking_quality import assess_audio_quality
from app.services.speaking_scorer import SpeakingScorer, build_attempt_evidence
from app.storage.local import LocalAssetStorage


def audio_digest(path):
    # No path or body is persisted. Bound raw input independently of decoded limits.
    if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise BenchmarkInputError("BENCHMARK_AUDIO_UNAVAILABLE")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def input_key(sample, root, identity):
    sources = [
        audio_digest((root / r.audio_path).resolve()) if r.audio_path else r.fixture_id
        for r in sample.responses
    ]
    return fingerprint([sample.model_dump(mode="json"), sources, identity.model_dump()])


async def load_evidence(sample, root, settings, *, on_speech_usage=None):
    from app.providers.speaking_asr import create_provider, provider_identity

    rows = []
    asr = None
    expected_asr = provider_identity(settings)
    with tempfile.TemporaryDirectory(prefix="speaking-benchmark-") as directory:
        for index, response in enumerate(sample.responses):
            if response.fixture_id:
                raise BenchmarkInputError("BENCHMARK_AUDIO_UNAVAILABLE")
            source = (root / response.audio_path).resolve()
            digest = await asyncio.to_thread(audio_digest, source)
            if source.suffix.lower() == ".wav":
                # Already-normalized PCM fixtures use the same production validator.
                path = source
                duration = await asyncio.to_thread(
                    wav_duration, source, settings.speaking_max_decoded_seconds
                )
            else:
                mime = {
                    ".webm": "audio/webm",
                    ".ogg": "audio/ogg;codecs=opus",
                    ".mp4": "audio/mp4",
                    ".m4a": "audio/mp4",
                }.get(source.suffix.lower())
                if mime is None:
                    raise BenchmarkInputError("BENCHMARK_AUDIO_UNAVAILABLE")
                path = Path(directory) / f"response-{index}.wav"
                key = source.relative_to(root.resolve()).as_posix()
                size = source.stat().st_size
                duration = await await_audio_thread(
                    asyncio.to_thread(
                        _render,
                        [(mime, [(key, digest, size)])],
                        path,
                        settings,
                        execute_ffmpeg,
                        LocalAssetStorage(root.resolve()),
                    )
                )
            audio = NormalizedAudio(
                path,
                digest,
                settings.speaking_normalizer_version,
                fingerprint([digest, settings.speaking_normalizer_version]),
                duration,
            )
            quality = await await_audio_thread(
                asyncio.to_thread(assess_audio_quality, audio, settings.speaking_quality)
            )
            if not quality.assessable or quality.state != "AUDIO_OK":
                raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "Audio unavailable for assessment.")
            speech_analysis = None
            if settings.speaking_profile == "speaking_hybrid_v1":
                from app.services.speaking_hybrid import analysis_to_asr, analyze_response

                if not settings.speaking_asr_enabled:
                    raise AppError(
                        "SPEAKING_ASR_UNAVAILABLE", "Transcription is not configured.", 503
                    )
                speech_analysis = await analyze_response(audio, settings)
                if on_speech_usage:
                    await on_speech_usage(
                        {
                            "attempted_calls": sum(
                                r.usage.attempted_calls for r in speech_analysis
                            ),
                            "failed_calls": sum(r.usage.failed_calls for r in speech_analysis),
                            "submitted_audio_ms": sum(
                                r.usage.submitted_audio_ms for r in speech_analysis
                            ),
                            "latency_ms": sum(r.latency_ms for r in speech_analysis)
                            if all(r.latency_ms is not None for r in speech_analysis)
                            else None,
                        }
                    )
                transcript = analysis_to_asr(speech_analysis, audio)
            else:
                asr = asr or create_provider(settings)
                transcript = ASRResult.model_validate(await asr.transcribe(audio))
            if any(
                getattr(transcript, key) != expected_asr[key]
                for key in ("provider", "model", "version")
            ):
                raise BenchmarkInputError("BENCHMARK_EVIDENCE_INVALID")
            if not transcript.text.strip():
                raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "Audio unavailable for assessment.")
            features = await build_feature_bundle(
                audio,
                transcript,
                settings,
                part_number=response.part_number,
                **({"speech_analysis": speech_analysis} if speech_analysis is not None else {}),
            )
            rows.append(
                {
                    "response_id": uuid5(NAMESPACE_URL, f"benchmark:{sample.id}:{index}"),
                    "prompt_id": uuid5(NAMESPACE_URL, f"benchmark-prompt:{sample.id}:{index}"),
                    "part_number": response.part_number,
                    "prompt_type": response.prompt_type,
                    "prompt_text": response.prompt_text,
                    "cue_points": response.cue_points,
                    "verbatim": transcript.text,
                    "clean": " ".join(transcript.text.split()),
                    "words": transcript.words,
                    "features": features,
                }
            )
    if (
        sum(len(r["verbatim"]) + len(r["clean"]) + len(r["prompt_text"]) for r in rows)
        > settings.speaking_ai_max_input_characters
    ):
        raise BenchmarkInputError("BENCHMARK_EVIDENCE_INVALID")
    return build_attempt_evidence(rows)


def safe_reason(error):
    code = (
        error.code
        if isinstance(error, AppError)
        else str(error)
        if isinstance(error, BenchmarkInputError)
        else "BENCHMARK_PROCESSING_FAILED"
    )
    from typing import get_args

    return code if code in get_args(Reason) else "BENCHMARK_PROCESSING_FAILED"


async def evaluate_samples(
    samples,
    root,
    output,
    settings,
    *,
    scorer=None,
    evidence_loader=None,
    resume=False,
    run_provenance=None,
):
    """Only fully scored matching checkpoints are reused; partial failures are retried."""
    identity = run_provenance or provenance(settings)
    loader = evidence_loader or load_evidence
    saved = {}
    checkpoint_path = output / "predictions.json"
    if resume and checkpoint_path.exists():
        cached = load_predictions(checkpoint_path)
        if cached.provenance == identity:
            saved = {p.id: p for p in cached.predictions}
    results = []

    def persist():
        bundle = PredictionSet(
            schema_version=1, provenance=identity, predictions=sorted(results, key=lambda p: p.id)
        )
        atomic_write(
            checkpoint_path,
            json.dumps(bundle.model_dump(mode="json"), sort_keys=True, indent=2, allow_nan=False)
            + "\n",
        )
        return bundle

    for sample in sorted(samples, key=lambda s: s.id):
        row = Prediction(id=sample.id)
        results.append(row)
        started = perf_counter()
        try:
            row.cache_key = await asyncio.to_thread(input_key, sample, root, identity)
            existing = saved.get(sample.id)
            if existing and existing.cache_key == row.cache_key and existing.overall is not None:
                results[-1] = existing
                persist()
                continue
            if (
                existing
                and existing.cache_key == row.cache_key
                and settings.speaking_profile == "speaking_hybrid_v1"
                and existing.telemetry
                and (
                    existing.telemetry.speech_analysis_started
                    or existing.telemetry.speech
                    and existing.telemetry.speech.attempted_calls
                )
            ):
                # CLI checkpoints must not rebill audio just because a later rubric call failed.
                # An operator may reconcile and explicitly choose a new output/run if needed.
                results[-1] = existing
                persist()
                continue
            inference_input = InferenceSample(id=sample.id, responses=sample.responses)
            row.telemetry = EvaluationTelemetry()
            if settings.speaking_profile == "speaking_hybrid_v1":
                row.telemetry.speech_analysis_started = True
                persist()  # Durable before any potentially billable audio leaves this process.

            async def observe_speech(usage, current=row):
                incoming = SpeechEvaluationTelemetry.model_validate(usage)
                existing = current.telemetry.speech
                current.telemetry.speech = (
                    incoming
                    if existing is None
                    else SpeechEvaluationTelemetry(
                        attempted_calls=existing.attempted_calls + incoming.attempted_calls,
                        failed_calls=existing.failed_calls + incoming.failed_calls,
                        submitted_audio_ms=existing.submitted_audio_ms
                        + incoming.submitted_audio_ms,
                        latency_ms=existing.latency_ms + incoming.latency_ms
                        if existing.latency_ms is not None and incoming.latency_ms is not None
                        else None,
                    )
                )

            evidence = await loader(
                inference_input,
                root,
                settings,
                **({"on_speech_usage": observe_speech} if loader is load_evidence else {}),
            )
            if scorer is None:
                from app.providers.speaking_llm import create_provider

                scorer = SpeakingScorer(
                    create_provider(settings),
                    score_max_tokens=settings.speaking_ai_score_max_tokens,
                    feedback_max_tokens=settings.speaking_ai_feedback_max_tokens,
                )
            await scorer.provider.ensure_ready()

            async def checkpoint(result, current=row):
                current.scores[result.criterion] = result.score
                persist()  # Production score-first callback: feedback cannot precede this ACK.

            async def observe(record, current=row):
                telemetry = current.telemetry
                telemetry.provider_calls += 1
                attempts = record.get("provider_attempts", ())
                telemetry.provider_attempts += max(1, len(attempts))
                telemetry.provider_errors += int(record.get("provider_error_code") is not None)
                from app.providers.writing_llm.base import safe_completion_usage

                for key, value in safe_completion_usage(record.get("usage")).items():
                    telemetry.usage[key] = telemetry.usage.get(key, 0) + value

            for trait in ("fc", "lr", "gra", "pr"):
                result = await scorer.score_criterion(
                    trait, evidence, checkpoint, on_provider_call=observe
                )
                row.scores[trait] = result.score
                if result.score is None:
                    row.reasons[trait] = result.error_code or "BENCHMARK_PROCESSING_FAILED"
                persist()
        except Exception as error:
            code = safe_reason(error)
            for trait in ("fc", "lr", "gra", "pr"):
                if row.scores.get(trait) is None:
                    row.scores[trait], row.reasons[trait] = None, code
            persist()
        finally:
            if row.telemetry is not None:
                row.telemetry.latency_ms = (perf_counter() - started) * 1000
    return persist()
