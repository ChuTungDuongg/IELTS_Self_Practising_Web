"""Sequential private replay through production Azure, CPU evidence and SpeakingScorer."""

import asyncio
import math
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.core.exceptions import AppError
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.models import provenance
from app.evaluation.speaking.replay_audio import normalize_window, pcm_digest
from app.evaluation.speaking.replay_cache import live_lock, read_checkpoint, save_checkpoint
from app.evaluation.speaking.replay_manifest import validate
from app.evaluation.speaking.replay_models import ReplaySegment
from app.evaluation.speaking.replay_report import CRITERIA, compare_labels, write_replay_reports
from app.providers.speech_analysis.azure import azure_analysis_identity
from app.providers.speech_analysis.azure_policy import require_billing_authorization
from app.schemas.speaking_grading import CriterionResult
from app.schemas.speech_analysis import SpeechAnalysisResult
from app.services.speaking_audio import await_audio_thread, fingerprint, normalization_identity
from app.services.speaking_features import build_feature_bundle, feature_identity
from app.services.speaking_hybrid import analysis_to_asr, analyze_response
from app.services.speaking_profile import hybrid_profile_status
from app.services.speaking_quality import assess_audio_quality
from app.services.speaking_scorer import SpeakingScorer, build_attempt_evidence, speaking_overall


def check_live_limits(allow_live, audio_seconds, budget, estimate, mode):
    if not allow_live:
        raise BenchmarkInputError("REPLAY_LIVE_REQUIRES_EXPLICIT_FLAG")
    if any(
        type(v) not in (int, float) or not math.isfinite(v)
        for v in (audio_seconds, budget, estimate)
    ):
        raise BenchmarkInputError("REPLAY_LIVE_LIMITS_REQUIRED")
    if (
        not 0 < audio_seconds <= 1800
        or budget <= 0
        or estimate < 0
        or mode == "full"
        and estimate == 0
    ):
        raise BenchmarkInputError("REPLAY_LIVE_LIMITS_REQUIRED")
    if estimate > budget:
        raise BenchmarkInputError("REPLAY_ESTIMATED_BUDGET_EXCEEDED")


def check_live_configuration(settings, mode):
    key = settings.speaking_azure_key
    if (
        settings.speaking_profile != "speaking_hybrid_v1"
        or not settings.speaking_asr_enabled
        or not key
        or not key.get_secret_value().strip()
        or not settings.speaking_azure_region
    ):
        raise BenchmarkInputError("REPLAY_AZURE_CONFIGURATION_MISSING")
    require_billing_authorization(settings)
    status = hybrid_profile_status(settings)
    if not status["configured"]:
        raise BenchmarkInputError("REPLAY_AZURE_SDK_OR_CONFIGURATION_UNAVAILABLE")
    if mode == "full":
        from app.providers.speaking_llm import is_configured

        if (
            not settings.speaking_ai_enabled
            or settings.speaking_ai_provider != "openai"
            or not is_configured(settings)
        ):
            raise BenchmarkInputError("REPLAY_OPENAI_CONFIGURATION_MISSING")
        if not status["vad_available"]:
            raise BenchmarkInputError("REPLAY_VAD_UNAVAILABLE_RUN_SETUP_SPEAKING_VAD")


def select_segments(manifest, metadata, mode, max_seconds, settings):
    candidates = [
        s for s in manifest.segments if s.speaker_role == "candidate" and s.start_ms is not None
    ]
    if mode == "full":
        reasons = manifest.grading_limitations()
        if reasons:
            raise BenchmarkInputError("REPLAY_" + reasons[0])
        selected = candidates
        if sum(s.end_ms - s.start_ms for s in selected) > max_seconds * 1000:
            raise BenchmarkInputError("REPLAY_AUDIO_BUDGET_EXCEEDED")
    else:
        # One bounded preview, even when an operator supplies an unsegmented 14-minute source.
        source = candidates[0] if candidates else None
        name = (source.source or manifest.source) if source else next(iter(metadata))
        start = source.start_ms if source else 0
        end = min(
            source.end_ms if source else metadata[name]["duration_ms"],
            start + int(min(max_seconds, 60, settings.speaking_max_decoded_seconds) * 1000),
        )
        selected = [
            source.model_copy(update={"source": name, "end_ms": end})
            if source
            else ReplaySegment(
                id="technical-preview",
                source=name,
                start_ms=start,
                end_ms=end,
                part_number=1,
                prompt_type="SHORT_ANSWER",
                speaker_role="unknown",
            )
        ]
    if any(s.end_ms - s.start_ms > settings.speaking_max_decoded_seconds * 1000 for s in selected):
        raise BenchmarkInputError("REPLAY_RESPONSE_DURATION_EXCEEDED")
    return selected


def safe_error(error):
    code = (
        error.code
        if isinstance(error, AppError)
        else str(error)
        if isinstance(error, BenchmarkInputError)
        else "REPLAY_PROCESSING_FAILED"
    )
    # Only internal domain tokens, never arbitrary exception text/provider bodies.
    return (
        code
        if code.startswith(("REPLAY_", "SPEAKING_", "ASR_"))
        and code.replace("_", "").isalnum()
        and code.isupper()
        and len(code) <= 100
        else "REPLAY_PROCESSING_FAILED"
    )


def base_report(mode, manifest, metadata, limits):
    candidates = [
        s for s in manifest.segments if s.speaker_role == "candidate" and s.start_ms is not None
    ]
    return {
        "schema_version": 1,
        "mode": mode,
        "status": "VALIDATED" if mode == "validate" else "PENDING",
        "input": {
            "file_count": len(metadata),
            "source_duration_ms": sum(m["duration_ms"] for m in metadata.values()),
            "candidate_duration_ms": sum(s.end_ms - s.start_ms for s in candidates),
            "part_counts": dict(Counter(str(s.part_number) for s in candidates)),
            "candidate_only_verified": manifest.candidate_only_verified,
            "full_grading_eligible": not manifest.grading_limitations(),
        },
        "azure": {
            "samples": [],
            "complete": 0,
            "partial": 0,
            "failed": 0,
            "unknown": 0,
            "recorded_attempts": 0,
            "new_attempts": 0,
            "submitted_audio_ms": 0,
            "latency_ms": None,
            "billing_uncertain": False,
            "word_timing_coverage": None,
            "pronunciation_word_coverage": None,
            "prosody_observed": None,
            "vad_available": None,
        },
        "luna": {
            "scores": {},
            "overall": None,
            "reasons": {},
            "provenance": None,
            "provider_calls": 0,
            "provider_attempts": 0,
            "usage": {},
            "latency_ms": None,
        },
        "evaluation": {"status": "UNLABELLED", "metrics": {}},
        "limits": limits,
        "limitations": [
            "LIVE_UNVERIFIED",
            "GRADING_ACCURACY_UNVERIFIED",
            *manifest.grading_limitations(),
        ],
    }


async def speech_evidence(audio, segment, path, settings, *, analyzer, offline_test):
    identity = azure_analysis_identity(settings)
    pcm_hash = await await_audio_thread(asyncio.to_thread(pcm_digest, audio))
    expected = fingerprint(
        [
            audio.cache_key,
            pcm_hash,
            segment.part_number,
            normalization_identity(settings),
            identity.model_dump(mode="json"),
        ]
    )
    cached = read_checkpoint(path)
    if cached:
        if cached.get("identity") != expected:
            raise BenchmarkInputError("REPLAY_CHECKPOINT_IDENTITY_MISMATCH")
        if cached.get("execution") != ("OFFLINE_TEST" if offline_test else "LIVE"):
            raise BenchmarkInputError("REPLAY_CHECKPOINT_EXECUTION_MISMATCH")
        results = [SpeechAnalysisResult.model_validate(r) for r in cached.get("results", [])]
        if (
            cached.get("state") != "COMPLETE"
            or len(results) != 1
            or any(r.status != "COMPLETE" for r in results)
        ):
            raise BenchmarkInputError(
                cached.get("error_code") or "REPLAY_AZURE_BILLING_UNKNOWN_INSPECT_CHECKPOINT"
            )
        if any(
            r.provider != identity
            or r.source.audio_fingerprint != audio.source_audio_fingerprint
            or r.source.duration_ms != audio.duration_ms
            or r.source.normalized_audio_fingerprint != pcm_hash
            or r.source.segment_id != str(audio.timeline[0].segment_id)
            or not r.coverage.stream_completed
            for r in results
        ):
            raise BenchmarkInputError("REPLAY_CHECKPOINT_EVIDENCE_INVALID")
        return results, cached, True
    saved = {
        "schema_version": 1,
        "identity": expected,
        "state": "ATTEMPTED",
        "results": [],
        "attempts": 1,
        "submitted_audio_ms": audio.duration_ms,
        "billing_uncertain": True,
        "execution": "OFFLINE_TEST" if offline_test else "LIVE",
        "error_code": None,
    }
    save_checkpoint(path, saved)  # ACK before any native/provider call can submit audio.

    async def persist(result):
        if (
            result.provider != identity
            or result.source.audio_fingerprint != audio.source_audio_fingerprint
            or result.source.normalized_audio_fingerprint != pcm_hash
            or result.source.duration_ms != audio.duration_ms
        ):
            raise BenchmarkInputError("REPLAY_CHECKPOINT_EVIDENCE_INVALID")
        saved["results"].append(result.model_dump(mode="json"))
        saved["error_code"] = result.error_code
        saved["state"] = (
            "COMPLETE"
            if result.status == "COMPLETE" and result.coverage.stream_completed
            else "TERMINAL"
        )
        save_checkpoint(path, saved)

    try:
        results = await analyze_response(audio, settings, analyzer=analyzer, on_result=persist)
    except (Exception, asyncio.CancelledError) as error:
        if saved["state"] == "ATTEMPTED":
            saved["error_code"] = "REPLAY_AZURE_BILLING_UNKNOWN_INSPECT_CHECKPOINT"
            save_checkpoint(path, saved)
        if isinstance(error, asyncio.CancelledError):
            raise
        raise BenchmarkInputError(saved["error_code"] or safe_error(error)) from None
    if saved["state"] != "COMPLETE":
        raise BenchmarkInputError(
            saved["error_code"] or "REPLAY_AZURE_INCOMPLETE_INSPECT_CHECKPOINT"
        )
    return results, saved, False


def coverage_row(key, results, checkpoint, reused, features=None):
    words = [w for r in results for w in r.words]
    timed = sum(w.start_ms is not None for w in words)
    targets = {
        o.target_id
        for r in results
        for o in r.observations
        if o.kind in {"pronunciation", "phoneme"}
        and o.score is not None
        and o.target_id in {w.evidence_id for w in words}
    }
    count = len(words)
    fluency = features.fluency if features else None
    return {
        "segment": key[:16],
        "status": results[0].status,
        "cache_reused": reused,
        "attempts": checkpoint["attempts"],
        "new_attempts": 0 if reused else checkpoint["attempts"],
        "submitted_audio_ms": checkpoint["submitted_audio_ms"],
        "billing_uncertain": True,
        "observed_usage": [r.usage.model_dump() for r in results],
        "word_count": count,
        "timed_word_count": timed,
        "pronunciation_word_count": min(count, len(targets)),
        "word_timing_coverage": timed / count if count else None,
        "pronunciation_word_coverage": min(count, len(targets)) / count if count else None,
        "capabilities": [r.capabilities.model_dump() for r in results],
        "provider": results[0].provider.model_dump(),
        "provider_reason_codes": sorted(
            {r.provider_reason_code for r in results if r.provider_reason_code}
        ),
        "error_codes": sorted({r.error_code for r in results if r.error_code}),
        "processed_duration_ms": sum(r.coverage.recognized_span_ms for r in results),
        "latency_ms": sum(r.latency_ms for r in results)
        if all(r.latency_ms is not None for r in results)
        else None,
        "vad_available": fluency.detected_speech_ms is not None if fluency else None,
        "detected_speech_ms": getattr(fluency, "detected_speech_ms", None),
        "limitations": sorted({v for r in results for v in r.limitations}),
    }


def aggregate_coverage(report):
    azure = report["azure"]
    rows = azure["samples"]
    for status, field in (("COMPLETE", "complete"), ("PARTIAL", "partial"), ("FAILED", "failed")):
        azure[field] = sum(
            r["status"] == status or status == "FAILED" and r["status"] == "CANCELLED" for r in rows
        )
    for field in ("submitted_audio_ms",):
        azure[field] = sum(r[field] for r in rows)
    azure["recorded_attempts"] = sum(r["attempts"] for r in rows)
    azure["unknown"] = sum(r["status"] == "UNKNOWN" for r in rows)
    azure["new_attempts"] = sum(r["new_attempts"] for r in rows)
    azure["billing_uncertain"] = any(r["billing_uncertain"] for r in rows)
    azure["latency_ms"] = (
        sum(r["latency_ms"] for r in rows)
        if rows and all(r["latency_ms"] is not None for r in rows)
        else None
    )
    words = sum(r["word_count"] for r in rows)
    for field, numerator in (
        ("word_timing_coverage", "timed_word_count"),
        ("pronunciation_word_coverage", "pronunciation_word_count"),
    ):
        azure[field] = sum(r[numerator] for r in rows) / words if words else None
    caps = [c for r in rows for c in r["capabilities"]]
    observed = [c["prosody_observed"] for c in caps if c["prosody_observed"] is not None]
    azure["prosody_observed"] = any(observed) if observed else None
    available = [r["vad_available"] for r in rows]
    azure["vad_available"] = (
        all(available) if available and all(x is not None for x in available) else None
    )


async def score_evidence(evidence, output, settings, report, *, scorer, resume):
    identity = provenance(settings)
    key = fingerprint(
        [evidence.model_dump(mode="json"), identity.model_dump(), feature_identity(settings)]
    )
    path = output / f"SENSITIVE-luna-{key}.json"
    saved = read_checkpoint(path) or {
        "schema_version": 1,
        "identity": key,
        "results": {},
        "telemetry": report["luna"],
        "pending": None,
    }
    if saved["identity"] != key:
        raise BenchmarkInputError("REPLAY_CHECKPOINT_IDENTITY_MISMATCH")
    report["luna"] = saved["telemetry"]
    luna = report["luna"]
    luna["provenance"] = identity.model_dump()
    if saved.get("pending"):
        raise BenchmarkInputError("REPLAY_LUNA_BILLING_UNKNOWN_INSPECT_CHECKPOINT")
    if saved["results"] and not resume and any(c not in saved["results"] for c in CRITERIA):
        raise BenchmarkInputError("REPLAY_LUNA_PARTIAL_USE_RESUME")
    if scorer is None:
        from app.providers.speaking_llm import create_provider

        scorer = SpeakingScorer(
            create_provider(settings),
            score_max_tokens=settings.speaking_ai_score_max_tokens,
            feedback_max_tokens=settings.speaking_ai_feedback_max_tokens,
        )
    ready = False

    async def checkpoint(result):
        saved["results"][result.criterion] = result.model_dump(mode="json")
        luna["scores"][result.criterion] = result.score
        saved["pending"] = (
            None  # A score-first checkpoint is safe to reuse even if feedback is interrupted.
        )
        save_checkpoint(path, saved)

    async def observe(record):
        from app.providers.writing_llm.base import safe_completion_usage

        luna["provider_calls"] += 1
        luna["provider_attempts"] += max(1, len(record.get("provider_attempts", ())))
        for name, count in safe_completion_usage(record.get("usage")).items():
            luna["usage"][name] = luna["usage"].get(name, 0) + count
        save_checkpoint(path, saved)

    started = perf_counter()
    for criterion in CRITERIA:
        stored = saved["results"].get(criterion)
        if stored:
            result = CriterionResult.model_validate(stored)
            if result.criterion != criterion:
                raise BenchmarkInputError("REPLAY_CHECKPOINT_EVIDENCE_INVALID")
            # Preserve score-first success. A known failed criterion can be explicitly resumed.
            if result.score is not None or result.status == "UNAVAILABLE" or not resume:
                luna["scores"][criterion] = result.score
                if result.error_code:
                    luna["reasons"][criterion] = result.error_code
                continue
        if not ready:
            await scorer.provider.ensure_ready()
            ready = True
        saved["pending"] = criterion
        save_checkpoint(path, saved)
        try:
            result = await scorer.score_criterion(
                criterion, evidence, checkpoint, on_provider_call=observe
            )
        except asyncio.CancelledError:
            luna["interrupted_calls_billing_unknown"] = (
                luna.get("interrupted_calls_billing_unknown", 0) + 1
            )
            save_checkpoint(path, saved)
            raise
        saved["pending"] = None
        saved["results"][criterion] = result.model_dump(mode="json")
        luna["scores"][criterion] = result.score
        luna["reasons"].pop(criterion, None)
        if result.error_code:
            luna["reasons"][criterion] = result.error_code
        luna["latency_ms"] = (luna["latency_ms"] or 0) + (perf_counter() - started) * 1000
        started = perf_counter()
        luna["overall"] = speaking_overall(luna["scores"])[1]
        save_checkpoint(path, saved)
    luna["overall"] = speaking_overall(luna["scores"])[1]
    save_checkpoint(path, saved)


async def run_replay(
    root,
    output_root,
    settings,
    *,
    mode="validate",
    allow_live=False,
    max_audio_seconds=60,
    max_estimated_cost_usd=None,
    estimated_cost_usd=None,
    resume=False,
    analyzer=None,
    scorer=None,
    offline_test=False,
):
    """No database/session dependencies. Injected test providers still require explicit live guards."""
    manifest, metadata, labels = await await_audio_thread(
        asyncio.to_thread(validate, root, settings)
    )
    if mode not in {"validate", "azure", "full"}:
        raise BenchmarkInputError("REPLAY_MODE_INVALID")
    limits = {
        "max_audio_seconds": max_audio_seconds,
        "max_concurrency": 1,
        "operator_estimated_cost_usd": estimated_cost_usd,
        "max_estimated_cost_usd": max_estimated_cost_usd,
        "estimate_accepted": allow_live,
        "provider_invoice_cap": False,
    }
    namespace = fingerprint(str(root.resolve()))
    run_key = fingerprint(
        [
            namespace,
            mode,
            manifest.model_dump(mode="json"),
            metadata,
            azure_analysis_identity(settings).model_dump(mode="json"),
            max_audio_seconds,
            "replay-v1",
        ]
    )
    output = output_root / f"replay-{run_key[:20]}"
    report = base_report(mode, manifest, metadata, limits)
    report["evaluation"] = {
        "status": "NOT_RUN_VALIDATE_ONLY" if mode == "validate" else "NOT_RUN_TECHNICAL_ONLY",
        "human_labels_present": labels is not None,
        "metrics": {},
    }
    if mode == "validate":
        write_replay_reports(output, report)
        return output, report
    check_live_limits(
        allow_live, max_audio_seconds, max_estimated_cost_usd, estimated_cost_usd, mode
    )
    check_live_configuration(settings, mode)
    selected = select_segments(manifest, metadata, mode, max_audio_seconds, settings)
    report["input"]["selected_audio_ms"] = sum(s.end_ms - s.start_ms for s in selected)
    report["input"]["candidate_duration_ms"] = sum(
        s.end_ms - s.start_ms for s in selected if s.speaker_role == "candidate"
    )
    report["input"]["part_counts"] = dict(
        Counter(str(s.part_number) for s in selected if s.speaker_role == "candidate")
    )
    if mode == "azure":
        report["limitations"].append("TECHNICAL_SMOKE_NO_IELTS_BANDS")
    with (
        live_lock(output_root),
        tempfile.TemporaryDirectory(prefix="speaking-replay-") as directory,
    ):
        rows = []
        save_checkpoint(
            output / "SENSITIVE-source-mapping.json",
            {
                "schema_version": 1,
                "manifest": manifest.model_dump(mode="json"),
                "selected": [s.model_dump(mode="json") for s in selected],
            },
        )
        try:
            for index, segment in enumerate(selected):
                name = segment.source or manifest.source
                audio = await await_audio_thread(
                    asyncio.to_thread(
                        normalize_window,
                        root,
                        name,
                        metadata[name],
                        segment,
                        Path(directory) / f"response-{index}.wav",
                        settings,
                    )
                )
                quality = await await_audio_thread(
                    asyncio.to_thread(assess_audio_quality, audio, settings.speaking_quality)
                )
                if not quality.assessable or quality.state != "AUDIO_OK":
                    raise BenchmarkInputError("SPEAKING_AUDIO_UNASSESSABLE")
                speech_key = fingerprint(
                    [
                        namespace,
                        audio.cache_key,
                        await await_audio_thread(asyncio.to_thread(pcm_digest, audio)),
                        segment.part_number,
                        normalization_identity(settings),
                        azure_analysis_identity(settings).model_dump(mode="json"),
                    ]
                )
                path = output_root / ".speech-cache" / f"SENSITIVE-{speech_key}.json"
                previously_submitted = path.exists()
                try:
                    results, checkpoint, reused = await speech_evidence(
                        audio, segment, path, settings, analyzer=analyzer, offline_test=offline_test
                    )
                except BaseException:
                    checkpoint = read_checkpoint(path)
                    if checkpoint:
                        results = [
                            SpeechAnalysisResult.model_validate(r) for r in checkpoint["results"]
                        ]
                        if results:
                            report["azure"]["samples"].append(
                                coverage_row(speech_key, results, checkpoint, previously_submitted)
                            )
                        else:
                            report["azure"]["samples"].append(
                                {
                                    "segment": speech_key[:16],
                                    "status": "UNKNOWN",
                                    "cache_reused": previously_submitted,
                                    "attempts": checkpoint["attempts"],
                                    "new_attempts": 0
                                    if previously_submitted
                                    else checkpoint["attempts"],
                                    "submitted_audio_ms": checkpoint["submitted_audio_ms"],
                                    "billing_uncertain": True,
                                    "word_count": 0,
                                    "timed_word_count": 0,
                                    "pronunciation_word_count": 0,
                                    "latency_ms": None,
                                    "capabilities": [],
                                    "vad_available": None,
                                }
                            )
                    raise
                features = None
                if not results[0].lexical_transcript.strip():
                    raise BenchmarkInputError("ASR_UNUSABLE")
                if mode == "full":
                    transcript = analysis_to_asr(results, audio)
                    features = await build_feature_bundle(
                        audio,
                        transcript,
                        settings,
                        part_number=segment.part_number,
                        speech_analysis=results,
                    )
                    rows.append(
                        {
                            "response_id": audio.timeline[0].response_id,
                            "prompt_id": uuid5(
                                NAMESPACE_URL,
                                fingerprint([segment.prompt_text, segment.cue_points]),
                            ),
                            "part_number": segment.part_number,
                            "prompt_type": segment.prompt_type,
                            "prompt_text": segment.prompt_text,
                            "cue_points": segment.cue_points,
                            "verbatim": transcript.text,
                            "clean": " ".join(transcript.text.split()),
                            "words": transcript.words,
                            "features": features,
                        }
                    )
                report["azure"]["samples"].append(
                    coverage_row(speech_key, results, checkpoint, reused, features)
                )
            if not offline_test:
                report["limitations"].remove("LIVE_UNVERIFIED")
            if mode == "full":
                if (
                    sum(len(r["verbatim"]) + len(r["clean"]) + len(r["prompt_text"]) for r in rows)
                    > settings.speaking_ai_max_input_characters
                ):
                    raise BenchmarkInputError("REPLAY_EVIDENCE_TOO_LARGE")
                await score_evidence(
                    build_attempt_evidence(rows),
                    output,
                    settings,
                    report,
                    scorer=scorer,
                    resume=resume,
                )
            report["status"] = (
                "TECHNICAL_SUCCESS"
                if mode == "azure"
                else "GRADED"
                if report["luna"]["overall"] is not None
                else "PARTIAL_GRADING"
            )
        except (Exception, asyncio.CancelledError) as error:
            report["status"] = (
                "CANCELLED" if isinstance(error, asyncio.CancelledError) else "FAILED"
            )
            code = safe_error(error)
            report["limitations"].append(code)
            if mode == "full":
                for criterion in CRITERIA:
                    if report["luna"]["scores"].get(criterion) is None:
                        report["luna"]["scores"][criterion] = None
                        report["luna"]["reasons"].setdefault(criterion, code)
        finally:
            aggregate_coverage(report)
            if mode == "full":
                report["evaluation"] = compare_labels(
                    labels, report["luna"]["scores"], report["luna"]["overall"]
                )
            write_replay_reports(output, report)
    return output, report
