"""Explicit private, candidate-only ASR comparison. Importing this module makes no requests."""

import asyncio
import math
import tempfile
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.evaluation.speaking.asr_metrics import aggregate, coverage_metrics, lexical_metrics
from app.evaluation.speaking.hybrid import _edit_distance, _tokens
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_audio import normalize_window, pcm_digest
from app.evaluation.speaking.replay_cache import (
    live_lock,
    private_write,
    read_checkpoint,
    save_checkpoint,
)
from app.evaluation.speaking.replay_manifest import validate
from app.evaluation.speaking.replay_models import read_json
from app.evaluation.speaking.replay_runner import check_live_limits, safe_error, speech_evidence
from app.providers.speaking_asr.lexical import PROVIDERS, create_lexical_analyzer, lexical_identity
from app.providers.speech_analysis.azure import AzureSpeechAnalyzer
from app.providers.speech_analysis.azure_policy import (
    TERMINAL_AZURE_ERRORS,
    require_billing_authorization,
)
from app.schemas.speaking_grading import StrictDTO
from app.schemas.speech_analysis import SpeechAnalysisResult
from app.services.speaking_audio import await_audio_thread, fingerprint, normalization_identity


class Annotation(StrictDTO):
    kind: Literal["filler", "repetition", "self_correction", "incorrect_grammar"]
    start_token: int = Field(ge=0, strict=True)
    end_token: int = Field(gt=0, strict=True)


class WindowBinding(StrictDTO):
    segment_id: str = Field(min_length=1, max_length=100)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    start_ms: int = Field(ge=0, strict=True)
    end_ms: int = Field(gt=0, strict=True)


class HumanReference(WindowBinding):
    human_verified: Literal[True]
    provenance: Literal["independent_human_transcriber"]
    text: str = Field(max_length=30000)
    accent: str | None = Field(default=None, max_length=100)
    speaking_speed: Literal["slow", "typical", "fast"] | None = None
    response_length: Literal["short", "long"] | None = None
    annotations: list[Annotation] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def spans(self):
        count = len(_tokens(self.text))
        if self.end_ms <= self.start_ms or any(
            not a.start_token < a.end_token <= count for a in self.annotations
        ):
            raise ValueError("Invalid human annotation bounds")
        return self


class HumanReferences(StrictDTO):
    schema_version: Literal[1]
    references: list[HumanReference] = Field(max_length=100)


class FixtureObservation(WindowBinding):
    provider: Literal["azure_pa", "azure_stt", "faster_whisper_local", "faster_whisper_modal"]
    silence_ms: int | None = Field(default=None, ge=100, le=5000)
    result: SpeechAnalysisResult

    @model_validator(mode="after")
    def provenance(self):
        expected = {"azure_pa": "azure-speech", "azure_stt": "azure-stt"}.get(
            self.provider, self.provider
        )
        if (
            self.result.provider.provider != expected
            or self.result.source.audio_fingerprint != self.source_sha256
        ):
            raise ValueError("Fixture provider/source provenance mismatch")
        return self


class OfflineFixtures(StrictDTO):
    schema_version: Literal[1]
    observations: list[FixtureObservation] = Field(max_length=1000)


def _bound(row, segment, source):
    if (row.segment_id, row.source_sha256, row.start_ms, row.end_ms) != (
        segment.id,
        source["sha256"],
        segment.start_ms,
        segment.end_ms,
    ):
        raise BenchmarkInputError("REPLAY_ASR_REFERENCE_OR_FIXTURE_WINDOW_MISMATCH")


def _private_model(root, path, model):
    if path is None:
        return None
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()) or path.is_symlink():
        raise BenchmarkInputError("REPLAY_PRIVATE_ROOT_REQUIRED")
    return read_json(resolved, model)


def plan_comparison(manifest, metadata, settings, providers, segment_ids, silence_values):
    if (
        not providers
        or len(set(providers)) != len(providers)
        or any(p not in PROVIDERS for p in providers)
    ):
        raise BenchmarkInputError("REPLAY_ASR_EXPLICIT_PROVIDERS_REQUIRED")
    if not manifest.candidate_only_verified:
        raise BenchmarkInputError("REPLAY_SPEAKER_NOT_VERIFIED")
    candidates = [
        s for s in manifest.segments if s.speaker_role == "candidate" and s.start_ms is not None
    ]
    if segment_ids:
        if set(segment_ids) - {s.id for s in candidates}:
            raise BenchmarkInputError("REPLAY_ASR_CANDIDATE_SEGMENT_REQUIRED")
        candidates = [s for s in candidates if s.id in segment_ids]
    if not candidates:
        raise BenchmarkInputError("REPLAY_ASR_CANDIDATE_SEGMENT_REQUIRED")
    variants = []
    for provider in providers:
        for silence in (
            (silence_values or [settings.speaking_azure_segmentation_silence_timeout_ms])
            if provider.startswith("azure_")
            else [None]
        ):
            if silence is not None and (type(silence) is not int or not 100 <= silence <= 5000):
                raise BenchmarkInputError("REPLAY_ASR_SEGMENTATION_INVALID")
            variant = (provider, silence)
            if variant in variants:
                raise BenchmarkInputError("REPLAY_ASR_SEGMENTATION_INVALID")
            variants.append(variant)
    return candidates, variants


def authorize_comparison(
    settings,
    variants,
    *,
    allow_live,
    allow_gpu,
    max_audio_seconds,
    seconds,
    estimate,
    budget,
    provider_estimates,
):
    check_live_limits(allow_live, max_audio_seconds, budget, estimate, "compare-asr")
    if seconds > max_audio_seconds:
        raise BenchmarkInputError("REPLAY_AUDIO_BUDGET_EXCEEDED")
    selected = {p for p, _ in variants}
    if set(provider_estimates) != selected or any(
        type(x) not in (int, float) or not math.isfinite(x) or x < 0
        for x in provider_estimates.values()
    ):
        raise BenchmarkInputError("REPLAY_ASR_EVERY_PROVIDER_ESTIMATE_REQUIRED")
    if sum(provider_estimates.values()) > estimate:
        raise BenchmarkInputError("REPLAY_ESTIMATED_BUDGET_EXCEEDED")
    if "faster_whisper_modal" in selected and (
        not allow_gpu or provider_estimates["faster_whisper_modal"] <= 0
    ):
        raise BenchmarkInputError("REPLAY_ASR_MODAL_GPU_NOT_AUTHORIZED")
    if selected & {"azure_pa", "azure_stt"}:
        require_billing_authorization(settings)
        if not settings.speaking_azure_key or not settings.speaking_azure_region:
            raise BenchmarkInputError("REPLAY_AZURE_CONFIGURATION_MISSING")
    # Validate ALL selected configurations before submitting the first paid request.
    for provider, silence in variants:
        configured = _settings(
            settings,
            provider,
            silence,
            allow_gpu,
            budget,
            provider_estimates[provider],
            seconds * sum(p == provider for p, _ in variants) / len(variants),
        )
        if provider != "azure_pa":
            create_lexical_analyzer(configured, provider)


def _settings(settings, provider, silence, allow_gpu, budget, estimate, provider_seconds):
    return settings.model_copy(
        update={
            "speaking_lexical_asr_provider": provider,
            "speaking_azure_segmentation_silence_timeout_ms": silence,
            "speaking_lexical_asr_allow_additional_requests": True,
            "speaking_lexical_asr_allow_gpu": allow_gpu,
            # Convert the accepted total over ALL this provider's windows/variants to a rate.
            # This process-scoped admission estimate is never saved to dotenv.
            "speaking_lexical_asr_estimated_cost_usd_per_minute": estimate / provider_seconds * 60,
            "speaking_lexical_asr_max_estimated_cost_usd_per_response": budget,
        }
    )


def _rss():
    try:
        import psutil

        return psutil.Process().memory_info().rss
    except (ImportError, OSError):
        return None


def _checkpoint_results(checkpoint, audio, identity, digest, part, settings):
    """Terminal evidence is reportable only after the same provenance checks as a cache hit."""
    expected = fingerprint(
        [
            audio.cache_key,
            digest,
            part,
            normalization_identity(settings),
            identity.model_dump(mode="json"),
        ]
    )
    if checkpoint.get("identity") != expected or checkpoint.get("execution") != "LIVE":
        return []
    results = [
        SpeechAnalysisResult.model_validate(value) for value in checkpoint.get("results", [])
    ]
    if len(results) > 1 or any(
        r.provider != identity
        or r.source.audio_fingerprint != audio.source_audio_fingerprint
        or r.source.normalized_audio_fingerprint != digest
        or r.source.duration_ms != audio.duration_ms
        or r.source.segment_id != str(audio.timeline[0].segment_id)
        for r in results
    ):
        return []
    return results


async def compare_asr(
    root,
    output_root,
    settings,
    *,
    providers,
    segment_ids=None,
    silence_values=None,
    fixtures_path=None,
    references_path=None,
    allow_live=False,
    allow_gpu=False,
    max_audio_seconds=120,
    estimated_cost_usd=None,
    max_estimated_cost_usd=None,
    provider_estimates=None,
):
    manifest, metadata, _ = validate(root, settings)
    selected, variants = plan_comparison(
        manifest, metadata, settings, providers, segment_ids, silence_values
    )
    fixtures = _private_model(root, fixtures_path, OfflineFixtures)
    references = _private_model(root, references_path, HumanReferences)
    refs = {}
    for reference in references.references if references else []:
        if reference.segment_id in refs or reference.segment_id not in {
            s.id for s in manifest.segments
        }:
            raise BenchmarkInputError("REPLAY_ASR_HUMAN_REFERENCES_INVALID")
        segment = next(s for s in manifest.segments if s.id == reference.segment_id)
        _bound(reference, segment, metadata[segment.source or manifest.source])
        refs[reference.segment_id] = reference
    fixture_map = {}
    for fixture in fixtures.observations if fixtures else []:
        key = (fixture.segment_id, fixture.provider, fixture.silence_ms)
        if key in fixture_map:
            raise BenchmarkInputError("REPLAY_ASR_FIXTURE_DUPLICATE")
        fixture_map[key] = fixture
    seconds = sum(s.end_ms - s.start_ms for s in selected) / 1000 * len(variants)
    if fixtures:
        if allow_live or allow_gpu:
            raise BenchmarkInputError("REPLAY_MODE_CONFLICT")
        if not math.isfinite(max_audio_seconds) or seconds > max_audio_seconds:
            raise BenchmarkInputError("REPLAY_AUDIO_BUDGET_EXCEEDED")
        # Preflight every fixture before processing any sample.
        for segment in selected:
            for provider, silence in variants:
                row = fixture_map.get((segment.id, provider, silence))
                if row is None:
                    raise BenchmarkInputError("REPLAY_ASR_FIXTURE_MISSING")
                _bound(row, segment, metadata[segment.source or manifest.source])
    else:
        authorize_comparison(
            settings,
            variants,
            allow_live=allow_live,
            allow_gpu=allow_gpu,
            max_audio_seconds=max_audio_seconds,
            seconds=seconds,
            estimate=estimated_cost_usd,
            budget=max_estimated_cost_usd,
            provider_estimates=provider_estimates or {},
        )
    namespace = fingerprint(str(root.resolve()))
    execution = "OFFLINE_FIXTURES" if fixtures else "LIVE"
    output = output_root / (
        "asr-"
        + fingerprint(
            [namespace, metadata, [s.model_dump() for s in selected], variants, execution]
        )[:20]
    )
    report = {
        "schema_version": 1,
        "status": "COMPARED",
        "execution": execution,
        "candidate_audio_seconds": seconds / len(variants),
        "provider_audio_seconds": seconds,
        "limits": {
            "total_estimate_usd": estimated_cost_usd,
            "budget_usd": max_estimated_cost_usd,
            "provider_estimates_usd": provider_estimates or {},
        },
        "samples": [],
        "providers": {},
        "strata": {},
        "disagreement": [],
        "limitations": [
            "ASR_IS_NOT_GROUND_TRUTH",
            "EDIT_INSERTIONS_ARE_HALLUCINATION_PROXIES",
            "RECOGNIZED_WINDOWS_ARE_NOT_VERIFIED_SPEECH_COVERAGE",
            "REMOTE_CPU_MEMORY_GPU_USAGE_UNAVAILABLE",
            "NO_ENGINE_RANKING_WITHOUT_HUMAN_REFERENCES",
        ],
    }
    if fixtures:
        report["limitations"].append("OFFLINE_FIXTURES_NOT_LIVE_PROVIDER_EXECUTION")
    blocked_azure = False
    with live_lock(output_root), tempfile.TemporaryDirectory(prefix="asr-comparison-") as directory:
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
                        Path(directory) / f"{index}.wav",
                        settings,
                    )
                )
                digest = await await_audio_thread(asyncio.to_thread(pcm_digest, audio))
                for provider, silence in variants:
                    variant = provider + (
                        f":silence={silence}" if silence is not None else ":default"
                    )
                    row = {
                        "segment_id": segment.id,
                        "provider": variant,
                        "pcm_sha256": digest,
                        "new_requests": 0,
                        "cache_reused": False,
                        "latency_ms": None,
                        "metrics": lexical_metrics(""),
                        "status": "NOT_ATTEMPTED",
                        "host_process_cpu_seconds": None,
                        "host_rss_before_bytes": None,
                        "host_rss_after_bytes": None,
                        "remote_gpu_seconds": None,
                    }
                    report["samples"].append(row)
                    results = []
                    checkpoint = None
                    path = None
                    identity = None
                    try:
                        if fixtures:
                            result = fixture_map[(segment.id, provider, silence)].result
                            if (
                                result.source.normalized_audio_fingerprint != digest
                                or result.source.duration_ms != audio.duration_ms
                            ):
                                raise BenchmarkInputError("REPLAY_ASR_FIXTURE_PCM_MISMATCH")
                            results = [result]
                        else:
                            if blocked_azure and provider.startswith("azure_"):
                                raise BenchmarkInputError("REPLAY_AZURE_RESOURCE_BLOCKED")
                            configured = _settings(
                                settings,
                                provider,
                                silence,
                                allow_gpu,
                                max_estimated_cost_usd,
                                (provider_estimates or {})[provider],
                                seconds * sum(p == provider for p, _ in variants) / len(variants),
                            )
                            identity = lexical_identity(configured, provider)
                            key = fingerprint(
                                [
                                    namespace,
                                    audio.cache_key,
                                    digest,
                                    segment.part_number,
                                    normalization_identity(configured),
                                    identity.model_dump(mode="json"),
                                ]
                            )
                            path = output_root / ".speech-cache" / f"SENSITIVE-{key}.json"
                            existed = path.exists()
                            row["checkpoint_found"] = existed
                            row["host_rss_before_bytes"] = _rss()
                            cpu = time.process_time()
                            analyzer = (
                                AzureSpeechAnalyzer(configured)
                                if provider == "azure_pa"
                                else create_lexical_analyzer(configured, provider)
                            )
                            try:
                                results, checkpoint, row["cache_reused"] = await speech_evidence(
                                    audio,
                                    segment,
                                    path,
                                    configured,
                                    analyzer=analyzer,
                                    offline_test=False,
                                    identity=identity,
                                )
                            finally:
                                row["host_process_cpu_seconds"] = time.process_time() - cpu
                                row["host_rss_after_bytes"] = _rss()
                                checkpoint = read_checkpoint(path)
                                row["new_requests"] = (
                                    checkpoint["attempts"] if checkpoint and not existed else 0
                                )
                    except (Exception, asyncio.CancelledError) as error:
                        row["error_code"] = safe_error(error)
                        row["status"] = (
                            "UNKNOWN"
                            if checkpoint and checkpoint["state"] == "ATTEMPTED"
                            else "FAILED"
                        )
                        if checkpoint:
                            results = (
                                _checkpoint_results(
                                    checkpoint,
                                    audio,
                                    identity,
                                    digest,
                                    segment.part_number,
                                    configured,
                                )
                                if identity
                                else []
                            )
                            row["billing_uncertain"] = checkpoint["billing_uncertain"]
                        if isinstance(error, asyncio.CancelledError):
                            report["status"] = "CANCELLED"
                            raise
                    if results:
                        row.update(
                            status=results[0].status,
                            text=" ".join(r.lexical_transcript for r in results),
                            identity=results[0].provider.model_dump(mode="json"),
                            latency_ms=sum(r.latency_ms for r in results)
                            if all(r.latency_ms is not None for r in results)
                            else None,
                            usage=[r.usage.model_dump() for r in results],
                            coverage=coverage_metrics(results, audio.duration_ms),
                            billing_uncertain=any(r.usage.billing_uncertain for r in results),
                        )
                        row["metrics"] = lexical_metrics(row["text"], refs.get(segment.id))
                        blocked_azure |= any(r.error_code in TERMINAL_AZURE_ERRORS for r in results)
                observations = [
                    r for r in report["samples"] if r["segment_id"] == segment.id and "text" in r
                ]
                for left, right in combinations(observations, 2):
                    a, b = _tokens(left["text"]), _tokens(right["text"])
                    if len(a) * len(b) <= 4_000_000:
                        report["disagreement"].append(
                            {
                                "segment_id": segment.id,
                                "left": left["provider"],
                                "right": right["provider"],
                                "word_edit_distance": _edit_distance(a, b),
                                "is_accuracy": False,
                            }
                        )
        except (Exception, asyncio.CancelledError):
            # Decoder/metric failures must never leave a report claiming completion.
            report["status"] = "FAILED" if report["status"] != "CANCELLED" else "CANCELLED"
            raise
        finally:
            grouped = defaultdict(list)
            strata = defaultdict(list)
            for row in report["samples"]:
                grouped[row["provider"]].append(row)
                reference = refs.get(row["segment_id"])
                for field in ("accent", "speaking_speed", "response_length"):
                    if reference and getattr(reference, field):
                        strata[(row["provider"], field, getattr(reference, field))].append(row)
            report["providers"] = {key: aggregate(rows) for key, rows in grouped.items()}
            report["strata"] = [
                {"provider": p, "dimension": d, "value": v, **aggregate(rows)}
                for (p, d, v), rows in strata.items()
            ]
            if (
                any(r["status"] != "COMPLETE" for r in report["samples"])
                and report["status"] == "COMPARED"
            ):
                report["status"] = "PARTIAL_COMPARISON"
            save_checkpoint(output / "SENSITIVE-results.json", report)
            lines = [
                f"# ASR comparison: {execution}",
                "",
                f"Status: {report['status']}. Candidate seconds: {report['candidate_audio_seconds']}; summed provider seconds: {seconds}.",
                "",
                "| Provider | Samples | Human references | WER | CER | Mean ms | p95 ms | New requests |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for provider, values in report["providers"].items():
                lines.append(
                    "| "
                    + " | ".join(
                        str(x) if x is not None else "unavailable"
                        for x in (
                            provider,
                            values["samples"],
                            values["human_labelled_samples"],
                            values["wer"],
                            values["cer"],
                            values["latency_mean_ms"],
                            values["latency_p95_ms"],
                            values["new_requests"],
                        )
                    )
                    + " |"
                )
            lines += [
                "",
                "Estimates admit requests; they are not prices or hard invoice caps. No accuracy ranking is inferred.",
                "",
                "Private transcripts, per-window diagnostics, preservation metrics, strata and usage: SENSITIVE-results.json.",
            ]
            private_write(output / "summary.md", "\n".join(lines) + "\n")
    return output, report
