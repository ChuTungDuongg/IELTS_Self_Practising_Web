"""Pinned Silero ONNX measurement on CPU. No downloads, trimming, CUDA or band rules."""

import asyncio
import hashlib
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.services.speaking_quality import read_pcm

VAD_VERSION = "silero-v6.0-onnx-cpu-v1"
VAD_COMMIT = "fba061dc5559f696e62171e9a0741782b0fdc23c"
VAD_SHA256 = "597d30b3ec076608d059477bb14cfeffdf951bf5cae370d38f65d33bbfe82004"
VAD_URL = f"https://raw.githubusercontent.com/snakers4/silero-vad/{VAD_COMMIT}/src/silero_vad/data/silero_vad.onnx"
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="speaking-vad")
_admission = threading.BoundedSemaphore(10)


class VadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = VAD_VERSION
    available: bool
    spans: list[tuple[int, int]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def intervals_from_probabilities(
    values, duration_ms, *, threshold=0.5, min_speech_ms=250, min_silence_ms=250
):
    if not 0 < threshold < 1 or any(not math.isfinite(p) or not 0 <= p <= 1 for p in values):
        raise ValueError("Invalid VAD measurement")
    spans, start, silence = [], None, None
    for i, probability in enumerate(values):
        time = min(duration_ms, i * 32)
        if probability >= threshold:
            start = time if start is None else start
            silence = None
        elif start is not None:
            silence = time if silence is None else silence
            if time + 32 - silence >= min_silence_ms:
                if silence - start >= min_speech_ms:
                    spans.append((start, silence))
                start = silence = None
    if start is not None:
        end = silence if silence is not None else duration_ms
        if end - start >= min_speech_ms:
            spans.append((start, end))
    return spans


@lru_cache(maxsize=2)
def _session(path, checksum):
    if checksum != VAD_SHA256 or hashlib.sha256(Path(path).read_bytes()).hexdigest() != checksum:
        raise ValueError("VAD asset identity mismatch")
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    return ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])


def measure_vad(audio, settings):
    """State/context belong to this recording, never shared between candidate requests."""
    try:
        import numpy as np

        session = _session(settings.speaking_vad_model_path, settings.speaking_vad_model_sha256)
        samples = np.asarray(read_pcm(audio), dtype=np.float32) / 32768
        state, context = (
            np.zeros((2, 1, 128), dtype=np.float32),
            np.zeros((1, 64), dtype=np.float32),
        )
        probabilities = []
        # Reset recurrent state at recovered container boundaries, whose gaps are unknown.
        windows = [
            (
                m.normalized_start_frame
                if m.normalized_start_frame is not None
                else m.normalized_start_ms * 16,
                m.normalized_end_frame
                if m.normalized_end_frame is not None
                else m.normalized_end_ms * 16,
            )
            for m in audio.timeline
        ] or [(0, len(samples))]
        spans = []
        for first, last in windows:
            state.fill(0)
            context.fill(0)
            probabilities.clear()
            start = first // 16
            window = samples[first:last]
            for offset in range(0, len(window), 512):
                frame = np.zeros((1, 512), dtype=np.float32)
                current = window[offset : offset + 512]
                frame[0, : len(current)] = current
                output, state = session.run(
                    None,
                    {
                        "input": np.concatenate((context, frame), axis=1),
                        "state": state,
                        "sr": np.array(16000, dtype=np.int64),
                    },
                )
                context = frame[:, -64:]
                probabilities.append(float(output[0][0]))
            spans.extend(
                (a + start, b + start)
                for a, b in intervals_from_probabilities(probabilities, (last - first) // 16)
            )
        return VadResult(available=True, spans=spans, limitations=["VAD_SPEECH_ESTIMATE"])
    except Exception:
        return VadResult(available=False, limitations=["VAD_UNAVAILABLE"])


async def measure_vad_async(audio, settings):
    from app.services.speaking_audio import await_audio_thread

    if not _admission.acquire(blocking=False):
        return VadResult(available=False, limitations=["VAD_CAPACITY_EXCEEDED"])

    def run():
        try:
            return measure_vad(audio, settings)
        finally:
            _admission.release()

    return await await_audio_thread(asyncio.get_running_loop().run_in_executor(_executor, run))
