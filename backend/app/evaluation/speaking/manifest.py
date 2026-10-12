"""Bounded local reads; rejected private content is never included in errors."""

import json
from pathlib import Path

from app.evaluation.speaking.models import BenchmarkSample, PredictionSet


class BenchmarkInputError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def _text(path):
    try:
        with path.open("rb") as source:
            value = source.read(16 * 1024 * 1024 + 1)
        if len(value) > 16 * 1024 * 1024:
            raise ValueError("Too large")
        return value.decode("utf-8")
    except (OSError, UnicodeError, ValueError):
        raise BenchmarkInputError("BENCHMARK_INPUT_UNREADABLE") from None


def load_manifest(path: Path, max_samples=None):
    if max_samples is not None and (type(max_samples) is not int or not 1 <= max_samples <= 10000):
        raise BenchmarkInputError("BENCHMARK_SELECTION_INVALID")
    items, ids = [], set()
    for number, line in enumerate(_text(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            sample = BenchmarkSample.model_validate(json.loads(line, object_pairs_hook=_unique))
        except (ValueError, RecursionError):
            raise BenchmarkInputError(f"BENCHMARK_SAMPLE_INVALID:line={number}") from None
        if sample.id in ids:
            raise BenchmarkInputError(f"BENCHMARK_DUPLICATE_ID:line={number}")
        ids.add(sample.id)
        items.append(sample)
        if len(items) > 10000:
            raise BenchmarkInputError("BENCHMARK_TOO_MANY_SAMPLES")
    if not items:
        raise BenchmarkInputError("BENCHMARK_NO_SAMPLES")
    return items[:max_samples] if max_samples else items


def load_predictions(path: Path):
    try:
        return PredictionSet.model_validate(json.loads(_text(path), object_pairs_hook=_unique))
    except (ValueError, RecursionError):
        raise BenchmarkInputError("BENCHMARK_PREDICTIONS_INVALID") from None
