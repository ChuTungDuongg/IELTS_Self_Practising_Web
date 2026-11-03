"""Offline preparation/validation, with no provider construction or database access."""

import json
from pathlib import Path

from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_audio import probe_audio, resolve_source
from app.evaluation.speaking.replay_models import (
    ReplayHumanLabels,
    ReplayManifest,
    ReplaySegment,
    read_json,
)


def private_root(path, allowed):
    root, allowed = path.resolve(), allowed.resolve()
    if not root.is_relative_to(allowed) or path.is_symlink() and root != path.absolute():
        raise BenchmarkInputError("REPLAY_PRIVATE_ROOT_REQUIRED")
    return root


def discover(root):
    if not root.is_dir():
        raise BenchmarkInputError("REPLAY_NO_AUDIO")
    files = sorted(p.name for p in root.iterdir() if p.suffix.lower() in {".wav", ".mp3"})
    if not files:
        raise BenchmarkInputError("REPLAY_NO_AUDIO")
    stems = [Path(name).stem.lower() for name in files]
    if len(stems) != len(set(stems)) or len(files) > 4:
        raise BenchmarkInputError("REPLAY_SOURCE_AMBIGUOUS")
    if len(files) > 1 and not set(stems) <= {"part1", "part2", "part3"}:
        raise BenchmarkInputError("REPLAY_SOURCE_AMBIGUOUS")
    return files


def read_private_json(root, name, model):
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise BenchmarkInputError("REPLAY_CONFIGURATION_INVALID")
    return read_json(path, model)


def prepare(root, settings):
    root.mkdir(parents=True, exist_ok=True)
    if (root / "segments.json").exists():
        return read_private_json(root, "segments.json", ReplayManifest), False
    files = discover(root)
    for name in files:
        probe_audio(resolve_source(root, name), settings)
    segments = []
    for name in files:
        stem = Path(name).stem.lower()
        parts = [int(stem[-1])] if stem in {"part1", "part2", "part3"} else [1, 2, 3]
        segments.extend(
            ReplaySegment(
                id=f"p{part}-answer-1",
                source=name if len(files) > 1 else None,
                part_number=part,
                prompt_type={1: "SHORT_ANSWER", 2: "LONG_TURN", 3: "FOLLOW_UP"}[part],
            )
            for part in parts
        )
    manifest = ReplayManifest(source=files[0] if len(files) == 1 else None, segments=segments)
    # Never overwrite operator timestamps/questions, even on a repeated --prepare.
    with (root / "segments.json").open("x", encoding="utf-8") as output:
        json.dump(manifest.model_dump(mode="json"), output, indent=2, ensure_ascii=False)
        output.write("\n")
    return manifest, True


def validate(root, settings):
    files = discover(root)
    metadata = {name: probe_audio(resolve_source(root, name), settings) for name in files}
    manifest = (
        read_private_json(root, "segments.json", ReplayManifest)
        if (root / "segments.json").exists()
        else ReplayManifest(source=files[0])
    )
    physical_windows = {}
    for segment in manifest.segments:
        name = segment.source or manifest.source
        path = resolve_source(root, name)
        if name not in metadata:
            metadata[name] = probe_audio(path, settings)
        if segment.start_ms is None:
            continue
        if segment.end_ms > metadata[name]["duration_ms"]:
            raise BenchmarkInputError("REPLAY_SEGMENT_RANGE_INVALID")
        if (
            segment.speaker_role == "candidate"
            and segment.end_ms - segment.start_ms > settings.speaking_max_decoded_seconds * 1000
        ):
            raise BenchmarkInputError("REPLAY_RESPONSE_DURATION_EXCEEDED")
        physical_windows.setdefault(path, []).append((segment.start_ms, segment.end_ms))
    for windows in physical_windows.values():
        spans = sorted(windows)
        if any(end > start for (_, end), (start, _) in zip(spans, spans[1:], strict=False)):
            raise BenchmarkInputError("REPLAY_SEGMENT_OVERLAP")
    labels = (
        read_private_json(root, "human_labels.json", ReplayHumanLabels)
        if (root / "human_labels.json").exists()
        else None
    )
    return manifest, metadata, labels
