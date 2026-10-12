from app.core.exceptions import AppError
from app.services.speaking_audio import fingerprint


def provider_identity(settings):
    return {
        "provider": "faster-whisper",
        "model": settings.speaking_asr_model,
        "version": settings.speaking_asr_version,
        "language": settings.speaking_asr_language,
        "config_hash": fingerprint(
            [settings.speaking_asr_model_directory, "cpu", "int8", "word-timestamps", "vad"]
        ),
    }


def create_provider(settings):
    if not settings.speaking_asr_enabled or not settings.speaking_asr_model_directory:
        raise AppError("SPEAKING_ASR_UNAVAILABLE", "Local transcription is not configured.", 503)
    from .faster_whisper import FasterWhisperProvider

    return FasterWhisperProvider(settings)
