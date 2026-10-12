from typing import Protocol

from app.schemas.speaking_ai import ASRResult, WordTiming
from app.services.speaking_audio import NormalizedAudio

__all__ = ["ASRResult", "WordTiming", "SpeechASRProvider"]


class SpeechASRProvider(Protocol):
    identity: dict[str, str]

    async def transcribe(self, audio: NormalizedAudio) -> ASRResult: ...
