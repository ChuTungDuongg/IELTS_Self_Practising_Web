"""Bounded backend-only transport to the proxy-protected Modal ASR endpoint."""

import asyncio
import io
import json
import wave
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.providers.speaking_asr import provider_identity
from app.schemas.speaking_ai import ASRResult
from app.services.speaking_audio import NormalizedAudio, await_audio_thread

MAX_WAV_BYTES = 20 * 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024


def _normalized_bytes(audio: NormalizedAudio, maximum_seconds: int) -> bytes:
    if not isinstance(audio, NormalizedAudio) or audio.channels != 1 or audio.sample_rate != 16000:
        raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "Normalized audio is required.", 409)
    try:
        with audio.path.open("rb") as source:
            content = source.read(MAX_WAV_BYTES + 1)
        if not 0 < len(content) <= MAX_WAV_BYTES:
            raise ValueError("Invalid size")
        with wave.open(io.BytesIO(content), "rb") as source:
            frames = source.getnframes()
            if (
                source.getnchannels() != 1
                or source.getframerate() != 16000
                or source.getsampwidth() != 2
                or source.getcomptype() != "NONE"
                or not 0 < frames <= maximum_seconds * 16000
                or len(source.readframes(frames)) != frames * 2
                or frames * 1000 // 16000 != audio.duration_ms
            ):
                raise ValueError("Invalid normalized WAV")
        return content
    except (OSError, ValueError, EOFError, wave.Error):
        raise AppError(
            "SPEAKING_AUDIO_UNASSESSABLE", "Normalized audio is unavailable.", 409
        ) from None


class ModalASRProvider:
    def __init__(self, settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.identity = provider_identity(settings)
        self.transport = transport
        try:
            url = urlsplit(settings.speaking_asr_base_url)
            valid = (
                url.scheme == "https"
                and bool(url.hostname)
                and url.hostname.endswith(".modal.run")
                and not url.username
                and not url.password
                and not url.port
                and url.path in {"", "/"}
                and not url.query
                and not url.fragment
                and bool(settings.ai_writing_modal_key)
                and bool(settings.ai_writing_modal_secret)
            )
        except ValueError:
            valid = False
        if not valid:
            raise AppError(
                "SPEAKING_ASR_UNAVAILABLE", "Remote transcription is not configured.", 503
            )
        self.endpoint = settings.speaking_asr_base_url.rstrip("/") + "/transcribe"
        self.timeout = max(5.0, float(settings.speaking_processing_timeout_seconds) - 5.0)

    async def transcribe(self, audio: NormalizedAudio) -> ASRResult:
        content = await await_audio_thread(
            asyncio.to_thread(_normalized_bytes, audio, self.settings.speaking_max_decoded_seconds)
        )
        try:
            payload = await asyncio.wait_for(self._request(content), timeout=self.timeout)
            result = ASRResult.model_validate(json.loads(payload))
            if (
                result.provider != self.identity["provider"]
                or result.model != self.identity["model"]
                or result.version != self.identity["version"]
                or result.language != self.identity["language"]
                or any(word.end > audio.duration_ms / 1000 for word in result.words)
            ):
                raise ValueError("Unexpected ASR identity or timing")
            return result
        except AppError:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, ValidationError, json.JSONDecodeError):
            raise AppError(
                "SPEAKING_ASR_UNAVAILABLE", "Remote transcription is unavailable.", 503
            ) from None

    async def _request(self, content: bytes) -> bytes:
        headers = {
            "Content-Type": "audio/wav",
            "Modal-Key": self.settings.ai_writing_modal_key,
            "Modal-Secret": self.settings.ai_writing_modal_secret,
        }
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, follow_redirects=False, trust_env=False
        ) as client:
            async with client.stream(
                "POST", self.endpoint, content=content, headers=headers
            ) as response:
                if response.status_code == 422:
                    raise AppError("ASR_UNUSABLE", "Transcription found no usable speech.", 409)
                if response.status_code != 200:
                    raise AppError(
                        "SPEAKING_ASR_UNAVAILABLE", "Remote transcription is unavailable.", 503
                    )
                payload = bytearray()
                async for chunk in response.aiter_bytes():
                    payload.extend(chunk)
                    if len(payload) > MAX_RESULT_BYTES:
                        raise AppError(
                            "SPEAKING_ASR_UNAVAILABLE", "Remote transcription is unavailable.", 503
                        )
                return bytes(payload)
