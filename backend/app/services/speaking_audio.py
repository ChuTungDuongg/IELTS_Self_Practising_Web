"""Immutable raw containers -> bounded private mono PCM artifact. No ASR here."""

import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.exceptions import AppError
from app.models.speaking import SpeakingMediaCleanup, SpeakingResponse, SpeakingResponseTake
from app.models.speaking_transcript import SpeakingNormalizedAudio
from app.schemas.speaking_timeline import AudioSegmentMapping, validate_timeline
from app.services.asset_cleanup import compensate_files
from app.services.speaking_media import committed_fingerprint, ordered_chunks, ordered_segments
from app.storage.factory import get_asset_storage


async def await_audio_thread(awaitable):
    """Wait for a file-consuming thread to finish before propagating cancellation."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


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
        "segment_metadata_version": 2 if settings.speaking_profile == "speaking_hybrid_v1" else 1,
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
    timeline: tuple[AudioSegmentMapping, ...] = ()
    response_start_ms: int = 0


@dataclass(frozen=True)
class NormalizedAudioRef:
    storage_key: str = field(repr=False)
    source_audio_fingerprint: str
    normalizer_version: str
    cache_key: str
    duration_ms: int
    segment_count: int = 1
    timeline: tuple[AudioSegmentMapping, ...] = ()


@asynccontextmanager
async def stage_normalized_audio(storage, ref: NormalizedAudioRef, maximum_seconds: int):
    if not ref.storage_key.startswith("speaking-derived/"):
        raise ValueError("Invalid normalized audio namespace")
    with tempfile.TemporaryDirectory(prefix="speaking-read-") as directory:
        path = Path(directory) / "normalized.wav"

        def download_and_validate():
            maximum = maximum_seconds * 32000 + 4096
            size = 0
            with storage.open_reader(ref.storage_key) as source, path.open("xb") as output:
                while block := source.read(min(64 * 1024, maximum - size + 1)):
                    size += len(block)
                    if size > maximum:
                        raise AppError(
                            "ASSET_SIZE_INVALID", "The asset exceeds the allowed size.", 422
                        )
                    output.write(block)
            return wav_duration(path, maximum_seconds)

        validation = asyncio.create_task(asyncio.to_thread(download_and_validate))
        try:
            duration = await asyncio.shield(validation)
        except asyncio.CancelledError:
            await asyncio.gather(validation, return_exceptions=True)
            raise
        if duration != ref.duration_ms:
            raise ValueError("Invalid normalized duration")
        yield NormalizedAudio(
            path,
            ref.source_audio_fingerprint,
            ref.normalizer_version,
            ref.cache_key,
            ref.duration_ms,
            segment_count=ref.segment_count,
            timeline=validate_timeline(ref.timeline, ref.duration_ms),
        )


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


def copy_verified_chunk(storage, key, expected_sha256, max_bytes, destination):
    digest = hashlib.sha256()
    size = 0
    output = destination.open("xb")
    try:
        with output, storage.open_reader(key) as source:
            while block := source.read(min(64 * 1024, max_bytes - size + 1)):
                size += len(block)
                if size > max_bytes:
                    raise ValueError("Recording chunk exceeds its limit")
                digest.update(block)
                output.write(block)
        if size != max_bytes or digest.hexdigest() != expected_sha256:
            raise ValueError("Recording integrity check failed")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _render(groups, destination, settings, executor, storage, *, window_ms=None):
    # Chunk concatenation is allowed inside one recorder container only. FFmpeg
    # independently decodes every recovered container before concatenating PCM.
    with tempfile.TemporaryDirectory(prefix="decode-", dir=destination.parent) as directory:
        inputs = []
        formats = {
            "audio/webm": "matroska",
            "audio/webm;codecs=opus": "matroska",
            "audio/mp4": "mov",
            "audio/ogg;codecs=opus": "ogg",
            "audio/mpeg": "mp3",
            "audio/wav": "wav",
        }
        args = [
            settings.speaking_ffmpeg_path,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]
        if window_ms is not None:
            args.extend(["-xerror", "-err_detect", "explode"])
        for index, (mime, chunks) in enumerate(groups):
            container = Path(directory) / f"segment-{index}"
            with container.open("xb") as output:
                for chunk_index, (key, checksum, byte_size) in enumerate(chunks):
                    path = Path(directory) / f"chunk-{index}-{chunk_index}"
                    copy_verified_chunk(storage, key, checksum, byte_size, path)
                    with path.open("rb") as chunk:
                        shutil.copyfileobj(chunk, output, 64 * 1024)
                    path.unlink()
            inputs.append(container)
            args.extend(
                ["-protocol_whitelist", "file,pipe", "-f", formats[mime], "-i", str(container)]
            )
        window_filter = ""
        if window_ms is not None:
            start, end = window_ms
            if (
                len(groups) != 1
                or not 0 <= start < end
                or end - start > settings.speaking_max_decoded_seconds * 1000
            ):
                raise ValueError("Invalid normalized source window")
            window_filter = (
                f"atrim=start={start / 1000:.3f}:end={end / 1000:.3f},asetpts=PTS-STARTPTS,"
            )
        filters = [
            f"[{n}:a]{window_filter}aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a{n}]"
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


def _render_mapped(groups, destination, settings, executor, storage):
    """Decode containers independently and concatenate PCM without adding recovery silence."""
    lengths, total_frames = [], 0
    with tempfile.TemporaryDirectory(prefix="mapped-", dir=destination.parent) as directory:
        with wave.open(str(destination), "wb") as output:
            output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            for index, group in enumerate(groups):
                path = Path(directory) / f"{index}.wav"
                _render([group], path, settings, executor, storage)
                with wave.open(str(path), "rb") as source:
                    frames = source.getnframes()
                    if total_frames + frames > settings.speaking_max_decoded_seconds * 16000:
                        raise ValueError("Recording exceeds decoded limit")
                    # Preserve exact sample bounds internally; integer milliseconds are presentation.
                    output.writeframes(source.readframes(frames))
                    total_frames += frames
                    lengths.append(frames)
    return wav_duration(destination, settings.speaking_max_decoded_seconds), lengths


async def normalize_committed_take(
    session, response_id: UUID, settings, *, storage=None, executor=execute_ffmpeg
):
    storage = storage or get_asset_storage(settings)
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
        repair_key = None
        key = fingerprint([source, normalization_identity(settings)])
        cached = await session.scalar(
            select(SpeakingNormalizedAudio).where(
                SpeakingNormalizedAudio.response_id == response_id,
                SpeakingNormalizedAudio.cache_key == key,
            )
        )
        if cached:
            try:
                result = NormalizedAudioRef(
                    cached.storage_key,
                    source,
                    cached.normalizer_version,
                    key,
                    cached.duration_ms,
                    segment_count=cached.metadata_json.get("segment_count", 1),
                    timeline=validate_timeline(
                        cached.metadata_json.get("timeline", []), cached.duration_ms
                    ),
                )
                async with stage_normalized_audio(
                    storage, result, settings.speaking_max_decoded_seconds
                ):
                    pass
                return result
            except AppError as error:
                if error.code not in {"ASSET_NOT_FOUND", "ASSET_SIZE_INVALID"}:
                    raise
            except (ValueError, wave.Error, EOFError):
                pass
            await session.execute(
                insert(SpeakingMediaCleanup)
                .values(storage_key=cached.storage_key)
                .on_conflict_do_nothing(index_elements=["storage_key"])
            )
            if settings.speaking_profile == "speaking_hybrid_v1":
                # The row also owns billable speech checkpoints. Keep them durable even
                # if rendering fails or the process dies while repairing derivative bytes.
                repair_key = cached.storage_key
            else:
                await session.delete(cached)
        groups, segment_ids = [], []
        try:
            for segment in await ordered_segments(session, take.id):
                chunks = await ordered_chunks(session, segment.id)
                if chunks:
                    paths = []
                    for chunk in chunks:
                        if not chunk.storage_key.startswith("speaking-private/"):
                            raise ValueError("Invalid raw namespace")
                        if not 0 < chunk.byte_size <= 10 * 1024 * 1024:
                            raise ValueError("Invalid recorded chunk size")
                        paths.append((chunk.storage_key, chunk.sha256, chunk.byte_size))
                    groups.append((segment.mime_type, paths))
                    segment_ids.append(segment.id)
        except (AppError, OSError, ValueError):
            raise AppError(
                "SPEAKING_AUDIO_UNASSESSABLE", "Recording data is unavailable.", 409
            ) from None
    if not groups:
        raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "No accepted recording is available.", 409)
    with tempfile.TemporaryDirectory(prefix="speaking-normalize-") as directory:
        candidate = Path(directory) / "normalized.wav"
        object_key = f"speaking-derived/{uuid4().hex}.wav"
        uploaded = False
        try:
            hybrid = settings.speaking_profile == "speaking_hybrid_v1"
            renderer = _render_mapped if hybrid else _render
            rendering = asyncio.create_task(
                asyncio.to_thread(renderer, groups, candidate, settings, executor, storage)
            )
            try:
                rendered = await asyncio.shield(rendering)
                duration, lengths = rendered if hybrid else (rendered, [])
            except asyncio.CancelledError:
                # A subprocess/thread cannot be cancelled by dropping its awaiter.
                # Wait for the bounded decode before cleaning its private output.
                try:
                    await rendering
                except Exception:
                    pass
                raise
        except (AppError, OSError, ValueError, wave.Error, subprocess.SubprocessError, KeyError):
            raise AppError(
                "SPEAKING_AUDIO_UNASSESSABLE", "Recording could not be decoded.", 409
            ) from None

        offset, timeline = 0, []
        for sid, frames in zip(segment_ids, lengths, strict=hybrid):
            timeline.append(
                AudioSegmentMapping(
                    response_id=response_id,
                    take_number=take.take_number,
                    segment_id=sid,
                    normalized_start_ms=offset // 16,
                    normalized_end_ms=(offset + frames) // 16,
                    normalized_start_frame=offset,
                    normalized_end_frame=offset + frames,
                    gap_before_unknown=bool(timeline),
                )
            )
            offset += frames
        timeline = validate_timeline(timeline, duration)

        def upload():
            with candidate.open("rb") as file:
                return storage.put_stream(
                    object_key,
                    file,
                    content_type="audio/wav",
                    max_bytes=settings.speaking_max_decoded_seconds * 32000 + 4096,
                )

        task = asyncio.create_task(asyncio.to_thread(upload))
        try:
            try:
                await asyncio.shield(task)
                uploaded = True
            except asyncio.CancelledError:
                result = (await asyncio.gather(task, return_exceptions=True))[0]
                if not isinstance(result, FileExistsError):
                    await compensate_files(session, storage, [object_key])
                raise
            except FileExistsError:
                raise
            except Exception:
                await compensate_files(session, storage, [object_key])
                raise
            async with session.begin():
                statement = insert(SpeakingNormalizedAudio).values(
                    response_id=response_id,
                    cache_key=key,
                    source_audio_fingerprint=source,
                    normalizer_version=settings.speaking_normalizer_version,
                    storage_key=object_key,
                    duration_ms=duration,
                    metadata_json={
                        "sample_rate": 16000,
                        "channels": 1,
                        "segment_count": len(groups),
                        "timeline_version": "segment-ms-v1" if hybrid else None,
                        "timeline": [row.model_dump(mode="json") for row in timeline],
                    },
                )
                if repair_key:
                    statement = statement.on_conflict_do_update(
                        index_elements=["response_id", "cache_key"],
                        set_={
                            "storage_key": object_key,
                            "duration_ms": duration,
                            "metadata_json": SpeakingNormalizedAudio.metadata_json.op("||")(
                                statement.excluded.metadata_json
                            ),
                        },
                        where=SpeakingNormalizedAudio.storage_key == repair_key,
                    )
                else:
                    statement = statement.on_conflict_do_nothing(
                        index_elements=["response_id", "cache_key"]
                    )
                row_id = await session.scalar(statement.returning(SpeakingNormalizedAudio.id))
                if row_id:
                    result = NormalizedAudioRef(
                        object_key,
                        source,
                        settings.speaking_normalizer_version,
                        key,
                        duration,
                        segment_count=len(groups),
                        timeline=timeline,
                    )
                else:
                    row = await session.scalar(
                        select(SpeakingNormalizedAudio).where(
                            SpeakingNormalizedAudio.response_id == response_id,
                            SpeakingNormalizedAudio.cache_key == key,
                        )
                    )
                    result = NormalizedAudioRef(
                        row.storage_key,
                        source,
                        row.normalizer_version,
                        key,
                        row.duration_ms,
                        segment_count=row.metadata_json.get("segment_count", 1),
                        timeline=validate_timeline(
                            row.metadata_json.get("timeline", []), row.duration_ms
                        ),
                    )
            if not row_id:
                await compensate_files(session, storage, [object_key])
                uploaded = False
                async with stage_normalized_audio(
                    storage, result, settings.speaking_max_decoded_seconds
                ):
                    pass
            return result
        except BaseException:
            if uploaded:
                await compensate_files(session, storage, [object_key])
            raise
