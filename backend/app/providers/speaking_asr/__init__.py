from app.core.exceptions import AppError
from app.services.speaking_audio import fingerprint


def provider_identity(settings):
    if settings.speaking_asr_provider == "modal":
        return {
            "provider": "modal",
            "model": settings.speaking_asr_model,
            "revision": settings.speaking_asr_model_revision,
            "version": settings.speaking_asr_version,
            "language": settings.speaking_asr_language,
            # Endpoint rotation and proxy secrets are transport details, not model identity.
            "config_hash": fingerprint(
                [settings.speaking_asr_model_revision, settings.speaking_asr_version, "wav16k-s16le"]
            ),
        }
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
    if not settings.speaking_asr_enabled:
        raise AppError("SPEAKING_ASR_UNAVAILABLE", "Transcription is not configured.", 503)
    if settings.speaking_asr_provider == "modal":
        from .modal import ModalASRProvider

        return ModalASRProvider(settings)
    if not settings.speaking_asr_model_directory:
        raise AppError("SPEAKING_ASR_UNAVAILABLE", "Local transcription is not configured.", 503)
    from .faster_whisper import FasterWhisperProvider

    return FasterWhisperProvider(settings)
