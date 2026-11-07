"""Human-reference lexical metrics; no provider output can supply the reference."""

import unicodedata
from math import ceil

from app.evaluation.speaking.hybrid import _edit_distance, _tokens
from app.evaluation.speaking.manifest import BenchmarkInputError


def alignment(reference, hypothesis):
    """Bounded Levenshtein alignment, retaining exact matched reference positions."""
    if len(reference) * len(hypothesis) > 4_000_000:
        raise BenchmarkInputError("REPLAY_ASR_METRICS_TOO_LARGE")
    width = len(hypothesis) + 1
    directions = bytearray((len(reference) + 1) * width)
    previous = list(range(width))
    for i, word in enumerate(reference, 1):
        current = [i]
        for j, token in enumerate(hypothesis, 1):
            candidates = (previous[j - 1] + (word != token), previous[j] + 1, current[-1] + 1)
            direction = min(range(3), key=candidates.__getitem__)
            current.append(candidates[direction])
            directions[i * width + j] = direction
        previous = current
    i, j = len(reference), len(hypothesis)
    substitutions = deletions = insertions = 0
    matched = {}
    while i or j:
        direction = directions[i * width + j] if i and j else (1 if i else 2)
        if direction == 0:
            if reference[i - 1] == hypothesis[j - 1]:
                matched[i - 1] = j - 1
            else:
                substitutions += 1
            i, j = i - 1, j - 1
        elif direction == 1:
            deletions += 1
            i -= 1
        else:
            insertions += 1
            j -= 1
    return substitutions, deletions, insertions, matched


def lexical_metrics(text, reference=None):
    if reference is None:
        return {"wer": None, "cer": None, "reference_words": 0, "truth": "UNAVAILABLE"}
    expected, observed = _tokens(reference.text), _tokens(text)
    substitutions, deletions, insertions, matched = alignment(expected, observed)
    errors = substitutions + deletions + insertions
    # Same lexical normalization as analysis_evaluation: case/punctuation only.
    assert errors == _edit_distance(expected, observed)
    original = unicodedata.normalize("NFC", reference.text)
    recognized = unicodedata.normalize("NFC", text)
    char_errors = (
        _edit_distance(original, recognized)
        if len(original) * len(recognized) <= 4_000_000
        else None
    )
    spans = {
        "filler": [
            (i, i + 1) for i, word in enumerate(expected) if word in {"um", "uh", "erm", "er"}
        ],
        "repetition": [
            (i - 1, i + 1) for i in range(1, len(expected)) if expected[i] == expected[i - 1]
        ],
        "self_correction": [],
        "incorrect_grammar": [],
    }
    annotated = {a.kind for a in reference.annotations}
    for annotation in reference.annotations:
        spans[annotation.kind].append((annotation.start_token, annotation.end_token))
    preservation = {}
    for kind, windows in spans.items():
        windows = sorted(set(windows))
        count = len(windows)
        retained = sum(
            all(i in matched for i in range(start, end))
            and all(matched[i] == matched[i - 1] + 1 for i in range(start + 1, end))
            for start, end in windows
        )
        preservation[kind] = {
            "reference_events": count,
            "preserved_events": retained,
            "recall": retained / count if count else None,
            "annotated": kind in annotated or kind in {"filler", "repetition"},
        }
    return {
        "truth": "HUMAN_VERIFIED",
        "reference_words": len(expected),
        "word_errors": errors,
        "wer": errors / len(expected) if expected else None,
        "cer": char_errors / len(original) if original and char_errors is not None else None,
        "character_errors": char_errors,
        "reference_characters": len(original),
        "cer_limited": char_errors is None,
        "substitutions": substitutions,
        "missing_words": deletions,
        "hallucinated_words": insertions,
        "preservation": preservation,
    }


def coverage_metrics(results, duration_ms):
    words = [w for result in results for w in result.words]
    timed = [w for w in words if w.start_ms is not None and w.end_ms is not None]
    previous = 0
    valid = True
    for word in timed:
        if not previous <= word.start_ms <= word.end_ms <= duration_ms:
            valid = False
        previous = word.end_ms
    spans = sorted(
        (u.start_ms, u.end_ms) for r in results for u in r.utterances if u.start_ms is not None
    )
    covered, end = 0, 0
    for start, stop in spans:
        covered += max(0, stop - max(start, end))
        end = max(end, stop)
    return {
        "stream_completed": bool(results) and all(r.coverage.stream_completed for r in results),
        "recognized_window_ms": covered,
        "recognized_window_ratio": covered / duration_ms if duration_ms else None,
        "word_timing_valid": valid if timed else None,
        "word_timing_coverage": len(timed) / len(words) if words else None,
        "word_count": len(words),
        "untimed_word_count": len(words) - len(timed),
        "uncertain_region_count": sum(len(r.uncertain_regions) for r in results),
        "uncertain_regions": [
            region.model_dump() for r in results for region in r.uncertain_regions
        ],
        "provider_error_codes": sorted({r.error_code for r in results if r.error_code}),
        "limitations": sorted({v for r in results for v in r.limitations}),
    }


def aggregate(rows):
    labelled = [r["metrics"] for r in rows if r["metrics"]["truth"] == "HUMAN_VERIFIED"]
    latencies = sorted(r["latency_ms"] for r in rows if r.get("latency_ms") is not None)
    reference_words = sum(m["reference_words"] for m in labelled)
    characters = sum(m["reference_characters"] for m in labelled if m["cer"] is not None)
    preservation = {}
    for kind in ("filler", "repetition", "self_correction", "incorrect_grammar"):
        values = [m["preservation"][kind] for m in labelled]
        count = sum(v["reference_events"] for v in values)
        retained = sum(v["preserved_events"] for v in values)
        preservation[kind] = {
            "reference_events": count,
            "preserved_events": retained,
            "recall": retained / count if count else None,
        }
    return {
        "samples": len(rows),
        "status_counts": {
            state: sum(r["status"] == state for r in rows)
            for state in ("COMPLETE", "PARTIAL", "FAILED", "UNKNOWN", "NOT_ATTEMPTED")
        },
        "human_labelled_samples": len(labelled),
        "wer": sum(m["word_errors"] for m in labelled) / reference_words
        if reference_words
        else None,
        "cer": sum(m["character_errors"] for m in labelled if m["cer"] is not None) / characters
        if characters
        else None,
        "latency_mean_ms": sum(latencies) / len(latencies) if latencies else None,
        "latency_p95_ms": latencies[ceil(len(latencies) * 0.95) - 1] if latencies else None,
        "new_requests": sum(r["new_requests"] for r in rows),
        "cache_hits": sum(r["cache_reused"] for r in rows),
        "missing_words": sum(m["missing_words"] for m in labelled) if labelled else None,
        "hallucinated_words": sum(m["hallucinated_words"] for m in labelled) if labelled else None,
        "preservation": preservation,
        "observed_usage": {
            field: sum(u[field] for r in rows for u in r.get("usage", []))
            for field in (
                "attempted_calls",
                "submitted_audio_ms",
                "successful_calls",
                "failed_calls",
            )
        },
        "usage_is_invoice": False,
    }
