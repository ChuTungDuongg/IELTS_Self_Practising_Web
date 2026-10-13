"""Typed atomic local checkpoints; no input text or credentials are persisted."""

from pathlib import Path

from pydantic import ValidationError


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def cached_record(path: Path, cache_key: str, config_key: str, sample_id: str, *, record_type):
    attempts = sorted((path.parent.parent / "attempts" / cache_key).glob("*.json"))
    if attempts:
        path = attempts[-1]
    try:
        record = record_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError):
        return None
    if (record.cache_key, record.config_key, record.sample_id, record.status) != (
        cache_key,
        config_key,
        sample_id,
        "COMPLETED",
    ):
        return None
    return record.model_copy(update={"cache_hit": True})


def save_attempt(output: Path, record) -> None:
    directory = output / "attempts" / record.cache_key
    numbers = [
        int(path.stem)
        for path in directory.glob("*.json")
        if path.stem.isdecimal() and len(path.stem) <= 9
    ]
    atomic_write(
        directory / f"{max(numbers, default=0) + 1:06d}.json", record.model_dump_json(indent=2)
    )


def attempt_history(output: Path, records, *, record_type):
    result = []
    for record in records:
        for path in sorted((output / "attempts" / record.cache_key).glob("*.json")):
            try:
                attempt = record_type.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, ValidationError):
                continue
            if (attempt.cache_key, attempt.config_key, attempt.sample_id) == (
                record.cache_key,
                record.config_key,
                record.sample_id,
            ):
                result.append(attempt)
    return result
