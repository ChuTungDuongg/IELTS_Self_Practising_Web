"""Pure adapters around existing ASR/P2 metrics. No inference or database access."""

import random
from collections import defaultdict
from statistics import mean

from pydantic import ValidationError

from app.evaluation.speaking.asr_comparison import HumanReference
from app.evaluation.speaking.asr_metrics import (
    aggregate,
    alignment,
    coverage_metrics,
    lexical_metrics,
)
from app.evaluation.speaking.asr_normalization import normalized_text
from app.evaluation.speaking.hybrid import _tokens
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.schemas.speaking_benchmark_research import METRIC_PROTOCOL, NORMALIZATION
from app.schemas.speech_analysis import SpeechAnalysisResult


def reference_metrics(text, reference):
    if reference is None or reference.status != "VERIFIED" or reference.uncertainty:
        return lexical_metrics(text) | {
            "unavailable_reason": "REFERENCE_HAS_UNCERTAIN_SPEECH"
            if reference and reference.uncertainty
            else "VERIFIED_HUMAN_REFERENCE_MISSING"
        }
    try:
        ref = HumanReference(
            segment_id=reference.segment_id,
            source_sha256=reference.source_sha256,
            start_ms=reference.start_ms,
            end_ms=reference.end_ms,
            human_verified=True,
            provenance="independent_human_transcriber",
            text=normalized_text(reference.text),
            annotations=reference.annotations,
        )
        result = lexical_metrics(normalized_text(text), ref)
    except ValidationError:
        return lexical_metrics(text) | {"unavailable_reason": "REFERENCE_ANNOTATION_BOUNDS_INVALID"}
    except BenchmarkInputError:
        return lexical_metrics(text) | {"unavailable_reason": "BOUNDED_ALIGNMENT_LIMIT_EXCEEDED"}
    return result | {
        "deletions": result["missing_words"],
        "insertions": result["hallucinated_words"],
        "normalization": NORMALIZATION,
    }


def transcript_diff(reference, hypothesis):
    """Bounded edit script, sharing the existing deterministic alignment tie policy."""
    a, b = _tokens(normalized_text(reference)), _tokens(normalized_text(hypothesis))
    try:
        return alignment(a, b, with_operations=True)[4]
    except BenchmarkInputError:
        return []


def observation_metrics(result, reference, duration_ms):
    parsed = SpeechAnalysisResult.model_validate(result) if result else None
    return {
        "metrics": reference_metrics(parsed.lexical_transcript, reference)
        if parsed and parsed.coverage.stream_completed
        else lexical_metrics(""),
        "coverage": coverage_metrics([parsed], duration_ms) if parsed else None,
        "real_time_factor": parsed.latency_ms / duration_ms
        if parsed and parsed.latency_ms is not None and duration_ms
        else None,
    }


def summarize_asr(rows):
    result = aggregate(rows)
    comparable = [r for r in rows if r["metrics"].get("wer") is not None]
    by_sample, by_speaker = defaultdict(list), defaultdict(list)
    for r in comparable:
        by_sample[r["sample_id"]].append(r["metrics"]["wer"])
        if r.get("candidate_id"):
            by_speaker[r["candidate_id"]].append(r["metrics"]["wer"])
    return result | {
        "protocol": METRIC_PROTOCOL,
        "micro_wer": result["wer"],
        "macro_sample_wer": mean(mean(v) for v in by_sample.values()) if by_sample else None,
        "macro_speaker_wer": mean(mean(v) for v in by_speaker.values()) if by_speaker else None,
        "comparable_responses": len(comparable),
        "eligible_reference_responses": sum(
            r.get("reference_status") == "VERIFIED" and not r.get("reference_uncertainty")
            for r in rows
        ),
        "reference_words": sum(r["metrics"].get("reference_words", 0) for r in comparable),
        "missing_or_failed_results": sum(r["status"] not in {"COMPLETE", "PARTIAL"} for r in rows),
        "unavailable_accuracy_responses": len(rows) - len(comparable),
        "known_speakers": len(by_speaker),
    }


def paired_difference(values):
    """Values are (candidate pseudonym or None, left-minus-right error).

    Equal candidate weighting; repeated recordings cannot manufacture independence.
    Percentile interval is descriptive, seeded, and requires ten known clusters.
    """
    groups = defaultdict(list)
    for speaker, delta in values:
        if speaker:
            groups[speaker].append(delta)
    # A fixed seed is reproducible only when candidate order is stable across
    # query plans/process hash seeds. Responses within a candidate remain clustered.
    means = [mean(groups[speaker]) for speaker in sorted(groups)]
    result = {
        "matched_samples": len(values),
        "known_independent_speakers": len(groups),
        "sample_mean_difference": mean(v for _, v in values) if values else None,
        "speaker_mean_difference": mean(means) if means else None,
        "ci95": None,
        "ci_status": "INSUFFICIENT_INDEPENDENT_SPEAKERS",
        "positive_means": "LOWER_ERROR_FOR_RIGHT",
        "resampling_unit": "candidate",
        "bootstrap_seed": 1701,
    }
    if len(means) >= 10 and all(s for s, _ in values):
        rng = random.Random(1701)
        draws = sorted(mean(rng.choices(means, k=len(means))) for _ in range(2000))
        result.update(ci95=[draws[49], draws[1949]], ci_status="DESCRIPTIVE_CLUSTER_BOOTSTRAP")
    return result
