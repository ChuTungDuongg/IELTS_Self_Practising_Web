"""Load explicitly supplied local data without logging rejected content."""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.evaluation.task1.models import BenchmarkSample, Split
from app.providers.writing_llm.base import ImagePart


class BenchmarkInputError(ValueError):
    """Messages are fixed codes/line numbers, never Pydantic input dumps."""


@dataclass(frozen=True)
class LoadedSample:
    sample: BenchmarkSample
    image: ImagePart


def load_image(path: Path) -> ImagePart:
    try:
        with path.open("rb") as source:
            data = source.read(10 * 1024 * 1024 + 1)
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif data.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        else:
            mime = "image/webp"
        return ImagePart(mime, data)
    except (OSError, ValueError):
        raise BenchmarkInputError("BENCHMARK_IMAGE_INVALID") from None


def load_manifest(path: Path, split: Split, limit: int | None = None) -> list[LoadedSample]:
    if split not in {"dev", "holdout"} or (limit is not None and limit < 1):
        raise BenchmarkInputError("BENCHMARK_SELECTION_INVALID")
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            raise BenchmarkInputError("BENCHMARK_MANIFEST_TOO_LARGE")
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        raise BenchmarkInputError("BENCHMARK_MANIFEST_UNREADABLE") from None
    samples, identities = [], set()
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
        if sample.split != split or (limit is not None and len(samples) >= limit):
            continue
        image_path = Path(sample.image_path)
        if not image_path.is_absolute():
            image_path = path.parent / image_path
        samples.append(LoadedSample(sample, load_image(image_path)))
    if not samples:
        raise BenchmarkInputError("BENCHMARK_NO_SELECTED_SAMPLES")
    return samples
