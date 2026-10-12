from typing import Protocol

from app.schemas.speaking_ai import PronunciationEvidence, WordTiming
from app.services.speaking_audio import NormalizedAudio


class PronunciationEvidenceProvider(Protocol):
    async def analyse(
        self, audio: NormalizedAudio, transcript: str, alignment: list[WordTiming]
    ) -> PronunciationEvidence: ...
