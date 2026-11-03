"""Private offline speech evidence comparison. Never used by inference.

Truth is independently human annotated. Missing labels stay unknown, including
TTS whose source text does not establish what a recognizer should hear.
"""

import json
import re
from math import ceil
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.evaluation.speaking.manifest import BenchmarkInputError, _text, _unique
from app.evaluation.speaking.models import Identifier, Prediction
from app.schemas.speaking_grading import StrictDTO

Milliseconds = Annotated[float, Field(ge=0, le=3_600_000, allow_inf_nan=False, strict=True)]


class EvidenceLabels(StrictDTO):
    lexical_transcript: str | None = Field(default=None, max_length=100000)
    word_boundaries_ms: dict[Identifier, tuple[Milliseconds, Milliseconds]] | None = Field(
        default=None, max_length=10000
    )
    pauses_ms: list[tuple[Milliseconds, Milliseconds]] | None = Field(
        default=None, max_length=10000
    )
    feedback_labels: dict[Identifier, Annotated[bool, Field(strict=True)]] | None = Field(
        default=None, max_length=10000
    )

    @model_validator(mode="after")
    def valid_spans(self):
        spans = [*(self.word_boundaries_ms or {}).values(), *(self.pauses_ms or [])]
        if any(end <= start for start, end in spans):
            raise ValueError("Invalid temporal interval")
        return self


class ObservedEvidence(EvidenceLabels):
    feedback_flags: list[Identifier] = Field(default_factory=list, max_length=10000)
    latency_ms: Milliseconds | None = None
    provider_calls: int | None = Field(default=None, ge=0, le=100000, strict=True)
    usage: dict[
        Literal["prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"],
        Annotated[int, Field(ge=0, le=100000000, strict=True)],
    ] = Field(default_factory=dict)
    repeat_scores: list[dict[Literal["fc", "lr", "gra", "pr"], float | None]] = Field(
        default_factory=list, max_length=100
    )

    @field_validator("repeat_scores", mode="before")
    @classmethod
    def validate_scores(cls, values):
        return [Prediction(id="repeat", scores=row).scores for row in values]

    @model_validator(mode="after")
    def unique_flags(self):
        if len(set(self.feedback_flags)) != len(self.feedback_flags):
            raise ValueError("Duplicate feedback observation")
        if self.feedback_labels is not None:
            raise ValueError("Observed flags cannot supply truth labels")
        return self


class EvaluationRow(StrictDTO):
    id: Identifier
    truth_source: Literal["human", "unlabelled"]
    truth: EvidenceLabels = Field(default_factory=EvidenceLabels)
    observed: ObservedEvidence

    @model_validator(mode="after")
    def no_invented_truth(self):
        if self.truth_source != "human" and any(
            v is not None for v in self.truth.model_dump().values()
        ):
            raise ValueError("Independent human evidence labels required")
        return self


class AnalysisEvaluation(StrictDTO):
    schema_version: Literal[1]
    samples: list[EvaluationRow] = Field(max_length=10000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({row.id for row in self.samples}) != len(self.samples):
            raise ValueError("Duplicate evidence sample")
        return self


def load_analysis_evaluation(path: Path):
    try:
        return AnalysisEvaluation.model_validate(json.loads(_text(path), object_pairs_hook=_unique))
    except (ValueError, RecursionError):
        raise BenchmarkInputError("BENCHMARK_ANALYSIS_INVALID") from None


def _tokens(text):
    # Punctuation/case insensitive; lexical fillers, repetitions and errors remain.
    return re.findall(r"\w+(?:['’]\w+)*", text.casefold())


def _edit_distance(reference, observed):
    previous = list(range(len(observed) + 1))
    for i, word in enumerate(reference, 1):
        current = [i]
        for j, token in enumerate(observed, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (word != token)))
        previous = current
    return previous[-1]


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def analysis_report(evaluation: AnalysisEvaluation, sample_ids: set[str]):
    if {r.id for r in evaluation.samples} - sample_ids:
        raise BenchmarkInputError("BENCHMARK_ANALYSIS_ID_UNKNOWN")
    errors = words = lexical_count = boundary_count = boundary_missing = 0
    boundary_errors, latencies, calls, usages = [], [], [], {}
    pause_tp = pause_fp = pause_fn = pause_count = 0
    tp = fp = tn = fn = unjudged = labelled_feedback = 0
    repeats = {trait: [] for trait in ("fc", "lr", "gra", "pr")}
    for row in evaluation.samples:
        truth, observed = row.truth, row.observed
        if truth.lexical_transcript is not None and observed.lexical_transcript is not None:
            reference = _tokens(truth.lexical_transcript)
            # Quadratic matching is bounded independently of JSON read size.
            recognized = _tokens(observed.lexical_transcript)
            if len(reference) * len(recognized) > 4_000_000:
                raise BenchmarkInputError("BENCHMARK_ANALYSIS_TOO_LARGE")
            errors += _edit_distance(reference, recognized)
            words += len(reference)
            lexical_count += 1
        if truth.word_boundaries_ms is not None:
            for identifier, span in truth.word_boundaries_ms.items():
                predicted = (observed.word_boundaries_ms or {}).get(identifier)
                if predicted is None:
                    boundary_missing += 1
                else:
                    boundary_errors.extend(abs(a - b) for a, b in zip(span, predicted, strict=True))
                    boundary_count += 1
        if truth.pauses_ms is not None and observed.pauses_ms is not None:
            if len(truth.pauses_ms) * len(observed.pauses_ms) > 4_000_000:
                raise BenchmarkInputError("BENCHMARK_ANALYSIS_TOO_LARGE")
            pause_count += 1
            candidates = []
            for i, (start, end) in enumerate(truth.pauses_ms):
                for j, (left, right) in enumerate(observed.pauses_ms):
                    intersection = max(0, min(end, right) - max(start, left))
                    iou = intersection / (max(end, right) - min(start, left))
                    if iou >= 0.5:
                        candidates.append((iou, i, j))
            matched_truth, matched_observed = set(), set()
            for _, i, j in sorted(candidates, reverse=True):
                if i not in matched_truth and j not in matched_observed:
                    matched_truth.add(i)
                    matched_observed.add(j)
            pause_tp += len(matched_truth)
            pause_fn += len(truth.pauses_ms) - len(matched_truth)
            pause_fp += len(observed.pauses_ms) - len(matched_observed)
        labels = truth.feedback_labels or {}
        flags = set(observed.feedback_flags)
        labelled_feedback += len(labels)
        unjudged += len(flags - labels.keys())
        for identifier, positive in labels.items():
            emitted = identifier in flags
            tp += int(positive and emitted)
            fp += int(not positive and emitted)
            tn += int(not positive and not emitted)
            fn += int(positive and not emitted)
        if observed.latency_ms is not None:
            latencies.append(observed.latency_ms)
        if observed.provider_calls is not None:
            calls.append(observed.provider_calls)
        for key, value in observed.usage.items():
            usages[key] = usages.get(key, 0) + value
        for trait in repeats:
            values = [
                scores[trait] for scores in observed.repeat_scores if scores.get(trait) is not None
            ]
            if len(values) >= 2:
                repeats[trait].append(max(values) - min(values))
    latencies.sort()
    return {
        "schema_version": 1,
        "lexical_fidelity": {
            "wer": _ratio(errors, words),
            "edits": errors,
            "reference_words": words,
            "paired_samples": lexical_count,
            "normalization": "case-and-punctuation-only-v1",
        },
        "timing": {
            "boundary_mae_ms": _ratio(sum(boundary_errors), len(boundary_errors)),
            "matched_words": boundary_count,
            "missing_words": boundary_missing,
        },
        "pauses": {
            "precision": _ratio(pause_tp, pause_tp + pause_fp),
            "recall": _ratio(pause_tp, pause_tp + pause_fn),
            "true_positive": pause_tp,
            "false_positive": pause_fp,
            "false_negative": pause_fn,
            "labelled_samples": pause_count,
            "match_iou": 0.5,
        },
        "feedback": {
            "false_positive_rate": _ratio(fp, fp + tn),
            "false_discovery_rate": _ratio(fp, fp + tp),
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": fn,
            "labelled_units": labelled_feedback,
            "unjudged_flags": unjudged,
        },
        "telemetry": {
            "latency_p50_ms": latencies[ceil(len(latencies) * 0.5) - 1] if latencies else None,
            "latency_p95_ms": latencies[ceil(len(latencies) * 0.95) - 1] if latencies else None,
            "latency_samples": len(latencies),
            "provider_calls": sum(calls) if calls else None,
            "call_samples": len(calls),
            "usage": usages,
        },
        "repeat_stability": {
            trait: {
                "samples": len(ranges),
                "mean_range": _ratio(sum(ranges), len(ranges)),
                "maximum_range": max(ranges) if ranges else None,
            }
            for trait, ranges in repeats.items()
        },
        "limitations": [
            "Only independently human-labelled evidence enters fidelity and false-positive denominators.",
            "Missing truth is unknown; unjudged flags are not false positives or true negatives.",
            "TTS source text is not human transcript, pronunciation, or IELTS truth.",
            "WER is token fidelity, not proof of guaranteed verbatim recognition; boundary IDs must be manually aligned.",
            "Repeated scores must use fresh inference, not cache replay; reports do not establish production readiness.",
        ],
    }
