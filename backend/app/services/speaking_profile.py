"""Local readiness facts only: credentials never imply a verified live capability."""

import hashlib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.providers.speech_analysis.azure_policy import BILLING_BLOCKED, billing_authorized
from app.services.speaking_vad import VAD_SHA256


def hybrid_profile_status(settings):
    limitations = []
    key = settings.speaking_azure_key
    if not key or not key.get_secret_value().strip() or not settings.speaking_azure_region:
        limitations.append("AZURE_CONFIGURATION_MISSING")
    authorized = billing_authorized(settings)
    if not authorized:
        limitations.append(BILLING_BLOCKED)
    try:
        sdk = version("azure-cognitiveservices-speech")
    except PackageNotFoundError:
        sdk = None
        limitations.append("AZURE_SDK_MISSING")
    try:
        vad = (
            settings.speaking_vad_model_sha256 == VAD_SHA256
            and hashlib.sha256(Path(settings.speaking_vad_model_path).read_bytes()).hexdigest()
            == VAD_SHA256
        )
        version("onnxruntime")
    except (OSError, PackageNotFoundError):
        vad = False
    if not vad:
        limitations.append("VAD_UNAVAILABLE")
    lexical = lexical_profile_status(settings)
    if lexical["provider"] in {"azure_pa", "azure_stt"}:
        lexical["limitations"] += [
            x
            for x in limitations
            if x in {"AZURE_CONFIGURATION_MISSING", "AZURE_SDK_MISSING", BILLING_BLOCKED}
        ]
        lexical["configured"] = not lexical["limitations"]
    pronunciation_configured = bool(
        settings.speaking_asr_enabled
        and authorized
        and not any(x in limitations for x in ("AZURE_CONFIGURATION_MISSING", "AZURE_SDK_MISSING"))
    )
    return {
        "profile": settings.speaking_profile,
        "provider": settings.speaking_asr_provider,
        "configured": bool(
            settings.speaking_asr_enabled
            and settings.speaking_asr_provider == "azure"
            and authorized
            and lexical["configured"]
            and not any(
                x in limitations for x in ("AZURE_CONFIGURATION_MISSING", "AZURE_SDK_MISSING")
            )
        ),
        "vad_available": vad,
        "billing_authorized": authorized,
        "sdk_version": sdk,
        "locale": settings.speaking_azure_locale,
        "prosody_requested": settings.speaking_azure_prosody,
        "live_status": "LIVE_UNVERIFIED",
        "limitations": limitations,
        "lexical_asr": lexical,
        "pronunciation_configured": pronunciation_configured,
    }


def lexical_profile_status(settings):
    from app.core.exceptions import AppError
    from app.providers.speaking_asr.lexical import create_lexical_analyzer, selection

    strategy = selection(settings)
    limitations = []
    if strategy != "azure_pa":
        try:
            create_lexical_analyzer(settings)
            if strategy == "faster_whisper_local":
                version("faster-whisper")
                directory = Path(settings.speaking_asr_model_directory)
                if not all(
                    (directory / name).is_file()
                    for name in (
                        "model.bin",
                        "config.json",
                        "tokenizer.json",
                        "preprocessor_config.json",
                    )
                ):
                    limitations.append("LEXICAL_LOCAL_MODEL_UNAVAILABLE")
        except PackageNotFoundError:
            limitations.append("LEXICAL_LOCAL_DEPENDENCY_UNAVAILABLE")
        except AppError as error:
            limitations.append(error.code)
    return {
        "provider": strategy,
        "configured": not limitations,
        "additional_provider_request": strategy != "azure_pa",
        "gpu_endpoint_required": strategy == "faster_whisper_modal",
        "limitations": limitations,
    }
