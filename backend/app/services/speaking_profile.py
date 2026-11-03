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
    return {
        "profile": settings.speaking_profile,
        "provider": settings.speaking_asr_provider,
        "configured": bool(
            settings.speaking_asr_enabled
            and settings.speaking_asr_provider == "azure"
            and authorized
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
    }
