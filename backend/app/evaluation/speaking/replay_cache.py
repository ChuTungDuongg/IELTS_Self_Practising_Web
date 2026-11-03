"""Private local checkpoints. An interrupted speech submission is never an automatic retry."""

import json
from contextlib import contextmanager

from app.evaluation.speaking.manifest import BenchmarkInputError, _unique
from app.evaluation.speaking.report import atomic_write


def private_write(path, content):
    if (
        path.parent.resolve() != path.parent.absolute()
        or path.is_symlink()
        or path.with_suffix(path.suffix + ".tmp").is_symlink()
    ):
        raise BenchmarkInputError("REPLAY_CHECKPOINT_INVALID")
    atomic_write(path, content)


def read_checkpoint(path):
    if not path.exists():
        return None
    try:
        if (
            path.parent.resolve() != path.parent.absolute()
            or path.is_symlink()
            or path.stat().st_size > 64 * 1024 * 1024
        ):
            raise ValueError("Invalid checkpoint")
        with path.open(encoding="utf-8") as source:
            result = json.load(source, object_pairs_hook=_unique)
        if not isinstance(result, dict) or result.get("schema_version") != 1:
            raise ValueError("Invalid checkpoint contract")
        return result
    except (OSError, ValueError, RecursionError):
        raise BenchmarkInputError("REPLAY_CHECKPOINT_INVALID") from None


def save_checkpoint(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise BenchmarkInputError("REPLAY_CHECKPOINT_INVALID")
    private_write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


@contextmanager
def live_lock(directory):
    """One live replay per private report namespace, including across processes."""
    directory.mkdir(parents=True, exist_ok=True)
    if directory.resolve() != directory.absolute():
        raise BenchmarkInputError("REPLAY_CHECKPOINT_INVALID")
    path = directory / "SENSITIVE-live.lock"
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError:
        raise BenchmarkInputError("REPLAY_LIVE_LOCKED_INSPECT_CHECKPOINTS") from None
    try:
        with stream:
            stream.write("Inspect interrupted billing checkpoints before removing a stale lock.\n")
        yield
    finally:
        path.unlink(missing_ok=True)
