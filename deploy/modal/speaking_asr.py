"""Proxy-protected, scale-to-zero Speaking transcription on a separate GPU."""

import io
import logging
import math
import tempfile
import wave
from pathlib import Path

import modal

MODEL = "Systran/faster-whisper-large-v3"
REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"
FASTER_WHISPER_VERSION = "1.2.1"
CTRANSLATE2_VERSION = "4.8.2"
COMPUTE_TYPE = "int8_float16"
SERVICE_VERSION = "fw1.2.1-ct2-4.8.2-int8fp16-beam5-v1-edaa852"
MAX_WAV_BYTES = 20 * 1024 * 1024
MAX_SECONDS = 600

app = modal.App("ielts-speaking-asr")
cache = modal.Volume.from_name("ielts-speaking-asr-model-cache", create_if_missing=True)
image = (
    modal.Image.from_registry("nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install(
        f"faster-whisper=={FASTER_WHISPER_VERSION}",
        f"ctranslate2=={CTRANSLATE2_VERSION}",
        "fastapi==0.135.1",
    )
    .env({"HF_HOME": "/cache/huggingface", "HF_HUB_DISABLE_TELEMETRY": "1"})
)


class NoSpeechError(ValueError):
    pass


def validate_wav(content: bytes) -> float:
    if not 0 < len(content) <= MAX_WAV_BYTES:
        raise ValueError("Invalid audio size")
    try:
        with wave.open(io.BytesIO(content), "rb") as source:
            frames = source.getnframes()
            if (
                source.getnchannels() != 1
                or source.getframerate() != 16000
                or source.getsampwidth() != 2
                or source.getcomptype() != "NONE"
                or not 0 < frames <= MAX_SECONDS * 16000
                or len(source.readframes(frames)) != frames * 2
            ):
                raise ValueError("Invalid normalized WAV")
        return frames / 16000
    except (EOFError, wave.Error):
        raise ValueError("Invalid normalized WAV") from None


def load_model():
    logging.getLogger("faster_whisper").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    from faster_whisper import WhisperModel

    model = WhisperModel(
        MODEL,
        revision=REVISION,
        device="cuda",
        compute_type=COMPUTE_TYPE,
        download_root="/cache/huggingface",
    )
    cache.commit()  # The ASGI container is long-lived; persist the pinned model immediately.
    return model


def transcribe_wav(content: bytes, model) -> dict:
    duration = validate_wav(content)
    stage = "model_call"
    # Temporary candidate bytes stay outside the mounted model-cache Volume.
    try:
        with tempfile.TemporaryDirectory(prefix="speaking-asr-") as directory:
            path = Path(directory) / "normalized.wav"
            path.write_bytes(content)
            segments, _ = model.transcribe(
                str(path),
                language="en",
                word_timestamps=True,
                vad_filter=True,
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text_parts, words, text_length = [], [], 0
            stage = "segment_iteration"
            for segment in segments:
                stage = "segment_validation"
                text_parts.append(segment.text)
                text_length += len(segment.text)
                if text_length > 60000:
                    raise ValueError("Transcript too long")
                for word in segment.words or []:
                    start, end = float(word.start), float(word.end)
                    confidence = None if word.probability is None else float(word.probability)
                    if (
                        not math.isfinite(start)
                        or not math.isfinite(end)
                        or start < 0
                        or end < start
                        or end > duration
                        or (words and start < words[-1]["end"])
                        or not word.word
                        or len(word.word) > 200
                        or (
                            confidence is not None
                            and (not math.isfinite(confidence) or not 0 <= confidence <= 1)
                        )
                    ):
                        raise ValueError("Invalid word timing")
                    words.append(
                        {"word": word.word, "start": start, "end": end, "confidence": confidence}
                    )
                    if len(words) > 10000:
                        raise ValueError("Too many words")
                stage = "segment_iteration"
    except Exception as error:
        # Only a fixed stage and class; upstream errors may contain private paths.
        logging.getLogger(__name__).warning("ASR %s failed (%s)", stage, type(error).__name__)
        raise
    text = "".join(text_parts).strip()
    if not text:
        raise NoSpeechError("No speech")
    return {
        "text": text,
        "words": words,
        "provider": "modal",
        "model": MODEL,
        "version": SERVICE_VERSION,
        "language": "en",
    }


@app.function(
    image=image,
    gpu="T4",
    cpu=4,
    memory=16384,
    volumes={"/cache": cache},
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
    timeout=600,
)
@modal.asgi_app(requires_proxy_auth=True)
def serve_asr():
    import asyncio

    from fastapi import FastAPI, HTTPException, Request

    model = load_model()  # Once on container startup, reused by warm requests.
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    lock = asyncio.Lock()

    @api.get("/health")
    async def health():
        return {"provider": "modal", "model": MODEL, "version": SERVICE_VERSION}

    @api.post("/transcribe")
    async def transcribe(request: Request):
        if request.headers.get("content-type") != "audio/wav":
            raise HTTPException(415, "Normalized WAV is required.")
        length = request.headers.get("content-length")
        if length and (not length.isdecimal() or int(length) > MAX_WAV_BYTES):
            raise HTTPException(413, "Audio is too large.")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_WAV_BYTES:
                raise HTTPException(413, "Audio is too large.")
        try:
            validate_wav(content)
        except ValueError:
            raise HTTPException(422, "Invalid normalized audio.") from None
        async with lock:
            try:
                return await asyncio.to_thread(transcribe_wav, bytes(content), model)
            except NoSpeechError:
                raise HTTPException(422, "No usable speech was detected.") from None
            except Exception as error:
                # Class only: provider exceptions may contain private paths or audio context.
                logging.getLogger(__name__).warning(
                    "ASR inference failed (%s)", type(error).__name__
                )
                raise HTTPException(503, "Transcription is unavailable.") from None

    return api
