from app.schemas.speaking_ai import PronunciationEvidence
from app.services.speaking_audio import NormalizedAudio


class UnavailablePronunciationProvider:
    def __init__(self, version):
        self.version = version

    async def analyse(self, audio, transcript, alignment):
        if not isinstance(audio, NormalizedAudio):
            raise ValueError("Normalized audio is required")
        return PronunciationEvidence(
            status="UNAVAILABLE",
            version=self.version,
            source_audio_fingerprint=audio.source_audio_fingerprint,
            error_code="PROVIDER_UNAVAILABLE",
            limitations=["PROVIDER_UNAVAILABLE"],
        )


def create_provider(settings):
    if not settings.speaking_pronunciation_enabled:
        return UnavailablePronunciationProvider(settings.speaking_pronunciation.version)
    from .alignment_prosody import AlignmentProsodyProvider

    return AlignmentProsodyProvider(settings.speaking_pronunciation, settings.speaking_quality)
