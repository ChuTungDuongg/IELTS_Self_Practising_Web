"""Bounded local file probing and production normalization of explicit source windows."""

import hashlib
import json
import math
import shutil
import subprocess
import wave
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_models import local_name
from app.evaluation.speaking.runner import audio_digest
from app.schemas.speaking_timeline import AudioSegmentMapping
from app.services.speaking_audio import NormalizedAudio, _render, execute_ffmpeg, fingerprint
from app.storage.local import LocalAssetStorage

MAX_SOURCE_SECONDS = 1800


def pcm_digest(audio):
    digest = hashlib.sha256()
    with wave.open(str(audio.path), "rb") as source:
        while frames := source.readframes(32768):
            digest.update(frames)
    return digest.hexdigest()


def resolve_source(root, name):
    try:
        local_name(name)
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Outside source root")
        if path.suffix.lower() not in {".mp3", ".wav"}:
            raise ValueError("Unsupported source")
        return path
    except (OSError, ValueError, TypeError):
        raise BenchmarkInputError("REPLAY_SOURCE_INVALID") from None


def probe_audio(path, settings):
    if not path.is_file() or not 0 < path.stat().st_size <= 128 * 1024 * 1024:
        raise BenchmarkInputError("REPLAY_SOURCE_SIZE_INVALID")
    with path.open("rb") as source:
        header = source.read(16)
    if header[:4] in {b"RIFF", b"RF64"} and header[8:12] == b"WAVE":
        container = "wav"
    elif header[:3] == b"ID3" or len(header) >= 2 and header[0] == 255 and header[1] & 224 == 224:
        container = "mp3"
    else:
        raise BenchmarkInputError("REPLAY_AUDIO_FORMAT_INVALID")
    ffmpeg = shutil.which(settings.speaking_ffmpeg_path)
    if not ffmpeg:
        raise BenchmarkInputError("REPLAY_FFMPEG_UNAVAILABLE")
    executable = Path(ffmpeg).with_name(
        "ffprobe.exe" if Path(ffmpeg).suffix.casefold() == ".exe" else "ffprobe"
    )
    if not executable.is_file():
        raise BenchmarkInputError("REPLAY_FFPROBE_UNAVAILABLE")
    try:
        process = subprocess.run(
            [
                str(executable),
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-f",
                container,
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels:format=format_name,duration,size",
                "-of",
                "json",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=True,
        )
        if len(process.stdout) > 65536:
            raise ValueError("Probe too large")
        data = json.loads(process.stdout)
        (stream,) = data["streams"]
        seconds = float(data["format"]["duration"])
        rate, channels = int(stream["sample_rate"]), int(stream["channels"])
        if not math.isfinite(seconds) or not 0 < seconds <= MAX_SOURCE_SECONDS:
            raise ValueError("Source duration invalid")
        if not 8000 <= rate <= 192000 or not 1 <= channels <= 8:
            raise ValueError("Source parameters invalid")
        if data["format"]["format_name"] != container:
            raise ValueError("Source format mismatch")
        # Probe metadata alone does not establish that compressed frames can be decoded.
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-err_detect",
                "explode",
                "-protocol_whitelist",
                "file,pipe",
                "-f",
                container,
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-vn",
                "-t",
                str(MAX_SOURCE_SECONDS + 0.1),
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=True,
        )
        return {
            "duration_ms": math.floor(seconds * 1000),
            "sample_rate": rate,
            "channels": channels,
            "format": container,
            "size_bytes": path.stat().st_size,
            "sha256": audio_digest(path),
        }
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise BenchmarkInputError("REPLAY_AUDIO_UNREADABLE") from None


def normalize_window(root, source_name, metadata, segment, destination, settings):
    start, end = segment.start_ms, segment.end_ms
    if start is None or end is None or not 0 <= start < end <= metadata["duration_ms"]:
        raise BenchmarkInputError("REPLAY_SEGMENT_RANGE_INVALID")
    if end - start > settings.speaking_max_decoded_seconds * 1000:
        raise BenchmarkInputError("REPLAY_RESPONSE_DURATION_EXCEEDED")
    path = resolve_source(root, source_name)
    if audio_digest(path) != metadata["sha256"]:
        raise BenchmarkInputError("REPLAY_SOURCE_CHANGED")
    mime = "audio/wav" if metadata["format"] == "wav" else "audio/mpeg"
    duration = _render(
        [
            (
                mime,
                [
                    (
                        path.relative_to(root.resolve()).as_posix(),
                        metadata["sha256"],
                        metadata["size_bytes"],
                    )
                ],
            )
        ],
        destination,
        settings,
        execute_ffmpeg,
        LocalAssetStorage(root.resolve()),
        window_ms=(start, end),
    )
    if abs(duration - (end - start)) > 100:
        raise BenchmarkInputError("REPLAY_SEGMENT_DECODE_LENGTH_MISMATCH")
    key = fingerprint([metadata["sha256"], start, end, settings.speaking_normalizer_version])
    rid = uuid5(NAMESPACE_URL, key)
    mapping = AudioSegmentMapping(
        response_id=rid,
        take_number=1,
        segment_id=uuid5(rid, "source-window"),
        normalized_start_ms=0,
        normalized_end_ms=duration,
        source_start_ms=start,
    )
    return NormalizedAudio(
        destination,
        metadata["sha256"],
        settings.speaking_normalizer_version,
        key,
        duration,
        timeline=(mapping,),
    )
