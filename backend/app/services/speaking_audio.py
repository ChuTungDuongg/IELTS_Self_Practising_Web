"""Immutable raw containers -> bounded private mono PCM artifact. No ASR here."""

import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.exceptions import AppError
from app.models.speaking import SpeakingMediaCleanup, SpeakingResponse, SpeakingResponseTake
from app.models.speaking_transcript import SpeakingNormalizedAudio
from app.services.speaking_media import committed_fingerprint, ordered_chunks, ordered_segments
from app.storage.local import LocalAssetStorage


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def normalization_identity(settings):
    return {
        "version": settings.speaking_normalizer_version,
        "rate": 16000,
        "channels": 1,
        "codec": "pcm_s16le",
        "segment_metadata_version": 1,
        "maximum_seconds": settings.speaking_max_decoded_seconds,
    }


@dataclass(frozen=True)
class NormalizedAudio:
    path: Path = field(repr=False)
    source_audio_fingerprint: str
    normalizer_version: str
    cache_key: str
    duration_ms: int
    sample_rate: int = 16000
    channels: int = 1
    segment_count: int = 1


def execute_ffmpeg(args, timeout):
    subprocess.run(
        args, check=True, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def wav_duration(path, maximum):
    with wave.open(str(path), "rb") as audio:
        if (
            audio.getnchannels() != 1
            or audio.getframerate() != 16000
            or audio.getsampwidth() != 2
            or audio.getcomptype() != "NONE"
        ):
            raise ValueError("Unsupported normalized artifact")
        count = audio.getnframes()
        if not 0 < count <= maximum * 16000 or len(audio.readframes(count)) != count * 2:
            raise ValueError("Invalid normalized length")
        return count * 1000 // 16000


def _render(groups, destination, settings, executor):
    # Chunk concatenation is allowed inside one recorder container only. FFmpeg
    # independently decodes every recovered container before concatenating PCM.
    with tempfile.TemporaryDirectory(prefix="decode-", dir=destination.parent) as directory:
        inputs = []
        formats = {
            "audio/webm": "matroska",
            "audio/webm;codecs=opus": "matroska",
            "audio/mp4": "mov",
            "audio/ogg;codecs=opus": "ogg",
        }
        args = [
            settings.speaking_ffmpeg_path,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]
        for index, (mime, paths) in enumerate(groups):
            container = Path(directory) / f"segment-{index}"
            with container.open("xb") as output:
                for path in paths:
                    with path.open("rb") as chunk:
                        shutil.copyfileobj(chunk, output, 64 * 1024)
            inputs.append(container)
            args.extend(
                ["-protocol_whitelist", "file,pipe", "-f", formats[mime], "-i", str(container)]
            )
        filters = [
            f"[{n}:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a{n}]"
            for n in range(len(inputs))
        ]
        filters.append(
            "".join(f"[a{n}]" for n in range(len(inputs))) + f"concat=n={len(inputs)}:v=0:a=1[out]"
        )
        args.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[out]",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                "-t",
                str(settings.speaking_max_decoded_seconds + 0.1),
                "-fs",
                str(settings.speaking_max_decoded_seconds * 32000 + 4096),
                "-f",
                "wav",
                str(destination),
            ]
        )
        executor(args, settings.speaking_processing_timeout_seconds)
        return wav_duration(destination, settings.speaking_max_decoded_seconds)


async def normalize_committed_take(
    session, response_id: UUID, settings, *, storage=None, executor=execute_ffmpeg
):
    storage = storage or LocalAssetStorage(settings.resolved_storage_root)
    async with session.begin():
        response = await session.get(SpeakingResponse, response_id)
        if not response or not response.locked:
            raise AppError(
                "SPEAKING_AUDIO_UNASSESSABLE", "Committed recording is unavailable.", 409
            )
        take = await session.scalar(
            select(SpeakingResponseTake).where(
                SpeakingResponseTake.response_id == response_id,
                SpeakingResponseTake.take_number == response.active_take_number,
            )
        )
        if (
            not take
            or take.status != "COMMITTED"
            or await committed_fingerprint(session, take) != response.committed_audio_fingerprint
        ):
            raise AppError(
                "SPEAKING_AUDIO_UNASSESSABLE", "Recording provenance is unavailable.", 409
            )
        source = response.committed_audio_fingerprint
        key = fingerprint([source, normalization_identity(settings)])
        cached = await session.scalar(
            select(SpeakingNormalizedAudio).where(
                SpeakingNormalizedAudio.response_id == response_id,
                SpeakingNormalizedAudio.cache_key == key,
            )
        )
        if cached:
            try:
                if not cached.storage_key.startswith("speaking-derived/"):
                    raise ValueError("Invalid derived namespace")
                path = storage.resolve(cached.storage_key)
                if wav_duration(path, settings.speaking_max_decoded_seconds) != cached.duration_ms:
                    raise ValueError("Invalid cached duration")
                return NormalizedAudio(
                    path,
                    source,
                    cached.normalizer_version,
                    key,
                    cached.duration_ms,
                    segment_count=cached.metadata_json.get("segment_count", 1),
                )
            except (AppError, OSError, ValueError, wave.Error, EOFError):
                await session.execute(
                    insert(SpeakingMediaCleanup)
                    .values(storage_key=cached.storage_key)
                    .on_conflict_do_nothing(index_elements=["storage_key"])
                )
                await session.delete(cached)
        groups = []
        try:
            for segment in await ordered_segments(session, take.id):
                chunks = await ordered_chunks(session, segment.id)
                if chunks:
                    paths = []
                    for chunk in chunks:
                        if not chunk.storage_key.startswith("speaking-private/"):
                            raise ValueError("Invalid raw namespace")
                        path = storage.resolve(chunk.storage_key)
                        if hashlib.sha256(path.read_bytes()).hexdigest() != chunk.sha256:
                            raise ValueError("Invalid raw integrity")
                        paths.append(path)
                    groups.append((segment.mime_type, paths))
        except (AppError, OSError, ValueError):
            raise AppError(
                "SPEAKING_AUDIO_UNASSESSABLE", "Recording data is unavailable.", 409
            ) from None
    if not groups:
        raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "No accepted recording is available.", 409)
    directory = (storage.root / "speaking-derived").resolve()
    if storage.root not in directory.parents:
        raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "Recording storage is unavailable.", 503)
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{uuid4().hex}.wav"
    saved = False
    try:
        try:
            rendering = asyncio.create_task(
                asyncio.to_thread(_render, groups, candidate, settings, executor)
            )
            try:
                duration = await asyncio.shield(rendering)
            except asyncio.CancelledError:
                # A subprocess/thread cannot be cancelled by dropping its awaiter.
                # Wait for the bounded decode before cleaning its private output.
                try:
                    await rendering
                except Exception:
                    pass
                raise
        except (OSError, ValueError, wave.Error, subprocess.SubprocessError, KeyError):
            raise AppError(
                "SPEAKING_AUDIO_UNASSESSABLE", "Recording could not be decoded.", 409
            ) from None
        async with session.begin():
            row_id = await session.scalar(
                insert(SpeakingNormalizedAudio)
                .values(
                    response_id=response_id,
                    cache_key=key,
                    source_audio_fingerprint=source,
                    normalizer_version=settings.speaking_normalizer_version,
                    storage_key=f"speaking-derived/{candidate.name}",
                    duration_ms=duration,
                    metadata_json={
                        "sample_rate": 16000,
                        "channels": 1,
                        "segment_count": len(groups),
                    },
                )
                .on_conflict_do_nothing(index_elements=["response_id", "cache_key"])
                .returning(SpeakingNormalizedAudio.id)
            )
            if row_id:
                result = NormalizedAudio(
                    candidate,
                    source,
                    settings.speaking_normalizer_version,
                    key,
                    duration,
                    segment_count=len(groups),
                )
            else:
                row = await session.scalar(
                    select(SpeakingNormalizedAudio).where(
                        SpeakingNormalizedAudio.response_id == response_id,
                        SpeakingNormalizedAudio.cache_key == key,
                    )
                )
                result = NormalizedAudio(
                    storage.resolve(row.storage_key),
                    source,
                    row.normalizer_version,
                    key,
                    row.duration_ms,
                    segment_count=row.metadata_json.get("segment_count", 1),
                )
        saved = row_id is not None
        return result
    finally:
        if not saved:
            candidate.unlink(missing_ok=True)
