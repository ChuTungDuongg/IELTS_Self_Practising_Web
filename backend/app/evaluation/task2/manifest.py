"""Explicit local JSONL only; never connect to the production API/database."""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.evaluation.task2.models import BenchmarkSample, Split


class BenchmarkInputError(ValueError):
    """Only fixed codes and line numbers are exposed, never rejected contents."""


@dataclass(frozen=True)
class LoadedSample:
    sample: BenchmarkSample


def load_manifest(path: Path, split: Split, limit: int | None = None):
    if split not in {"dev", "holdout"} or (limit is not None and limit < 1):
        raise BenchmarkInputError("BENCHMARK_SELECTION_INVALID")
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            raise BenchmarkInputError("BENCHMARK_MANIFEST_TOO_LARGE")
        with path.open("rb") as source:
            data = source.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024:
            raise BenchmarkInputError("BENCHMARK_MANIFEST_TOO_LARGE")
        lines = data.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        raise BenchmarkInputError("BENCHMARK_MANIFEST_UNREADABLE") from None
    result, identities = [], set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            sample = BenchmarkSample.model_validate(json.loads(line))
        except (ValueError, ValidationError):
            raise BenchmarkInputError(f"BENCHMARK_SAMPLE_INVALID:line={line_number}") from None
        if sample.id in identities:
            raise BenchmarkInputError(f"BENCHMARK_DUPLICATE_ID:line={line_number}")
        identities.add(sample.id)
        if sample.split == split and (limit is None or len(result) < limit):
            result.append(LoadedSample(sample))
    if not result:
        raise BenchmarkInputError("BENCHMARK_NO_SELECTED_SAMPLES")
    return result
