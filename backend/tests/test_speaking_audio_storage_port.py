import hashlib
import wave
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace

import pytest

from app.services.speaking_audio import (
    NormalizedAudioRef,
    _render,
    copy_verified_chunk,
    stage_normalized_audio,
)


def test_copy_verified_chunk_streams_from_storage_and_checks_digest(tmp_path):
    class Port:
        @contextmanager
        def open_reader(self, key):
            assert key == "speaking-private/example.webm"
            yield BytesIO(b"audio")

    path = tmp_path / "chunk"
    copy_verified_chunk(
        Port(), "speaking-private/example.webm", hashlib.sha256(b"audio").hexdigest(), 5, path
    )
    assert path.read_bytes() == b"audio"


def test_copy_verified_chunk_rejects_oversize_and_corruption(tmp_path):
    class Port:
        @contextmanager
        def open_reader(self, key):
            yield BytesIO(b"audio")

    with pytest.raises(ValueError):
        copy_verified_chunk(Port(), "speaking-private/example.webm", "0" * 64, 10, tmp_path / "bad")
    with pytest.raises(ValueError):
        copy_verified_chunk(
            Port(),
            "speaking-private/example.webm",
            hashlib.sha256(b"audio").hexdigest(),
            4,
            tmp_path / "large",
        )
    existing = tmp_path / "existing"
    existing.write_bytes(b"do not replace")
    with pytest.raises(FileExistsError):
        copy_verified_chunk(Port(), "speaking-private/example.webm", "0" * 64, 10, existing)
    assert existing.read_bytes() == b"do not replace"


def test_ffmpeg_input_staging_uses_storage_and_removes_temporary_files(tmp_path):
    class Port:
        @contextmanager
        def open_reader(self, key):
            yield BytesIO({"speaking-private/a": b"a", "speaking-private/b": b"b"}[key])

    def executor(args, _timeout):
        inputs = [args[i + 1] for i, value in enumerate(args) if value == "-i"]
        assert len(inputs) == 1
        from pathlib import Path

        assert Path(inputs[0]).read_bytes() == b"ab"
        with wave.open(args[-1], "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 160)

    settings = SimpleNamespace(
        speaking_max_chunk_bytes=20,
        speaking_ffmpeg_path="ffmpeg",
        speaking_max_decoded_seconds=2,
        speaking_processing_timeout_seconds=5,
    )
    chunks = [
        (key, hashlib.sha256(data).hexdigest(), len(data))
        for key, data in [("speaking-private/a", b"a"), ("speaking-private/b", b"b")]
    ]
    assert _render([("audio/webm", chunks)], tmp_path / "out.wav", settings, executor, Port()) == 10
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.wav"]


async def test_normalized_audio_staging_lasts_until_context_exits(tmp_path):
    from app.storage.local import LocalAssetStorage

    storage = LocalAssetStorage(tmp_path / "store")
    wav = tmp_path / "source.wav"
    with wave.open(str(wav), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 160)
    with wav.open("rb") as source:
        storage.put_stream(
            "speaking-derived/a.wav", source, content_type="audio/wav", max_bytes=1000
        )
    ref = NormalizedAudioRef("speaking-derived/a.wav", "source", "pcm-v1", "cache", 10)
    async with stage_normalized_audio(storage, ref, 2) as audio:
        assert audio.path.exists()
        assert audio.duration_ms == 10
        assert audio.path.read_bytes() == wav.read_bytes()


async def test_file_consuming_thread_is_joined_before_cancellation():
    import asyncio
    import threading

    from app.services.speaking_audio import await_audio_thread

    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def work():
        started.set()
        release.wait(5)
        finished.set()

    task = asyncio.create_task(await_audio_thread(asyncio.to_thread(work)))
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


async def test_asr_timeout_waits_for_file_consumer_to_stop():
    import asyncio
    import threading

    from app.services.speaking_audio import await_audio_thread

    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def work():
        started.set()
        release.wait(5)
        finished.set()

    async def timed_work():
        return await asyncio.wait_for(await_audio_thread(asyncio.to_thread(work)), timeout=0.02)

    task = asyncio.create_task(timed_work())
    assert await asyncio.to_thread(started.wait, 5)
    await asyncio.sleep(0.04)
    assert not task.done()
    release.set()
    with pytest.raises(TimeoutError):
        await task
    assert finished.is_set()
