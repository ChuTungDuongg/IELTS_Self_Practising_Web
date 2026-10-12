"""Read-only adapter over configured JSON transports; Writing settings stay intact."""

import hashlib

from app.core.config import Settings
from app.core.exceptions import AppError
from app.providers.writing_llm import create_provider as create_writing_provider
from app.providers.writing_llm import is_configured as writing_is_configured


def transport_settings(settings):
    source = settings.model_dump() if hasattr(settings, "model_dump") else vars(settings)
    copied = Settings.model_validate({k: v for k, v in source.items() if k in Settings.model_fields})
    update = {"ai_writing_enabled": bool(getattr(settings, "speaking_ai_enabled", False))}
    provider = getattr(settings, "speaking_ai_provider", None) or copied.ai_writing_provider
    update["ai_writing_provider"] = provider
    model = getattr(settings, "speaking_ai_model", None)
    if model and provider in {"openai", "vllm"}:
        update[f"ai_writing_{provider}_model"] = model
    for field in ("request_timeout_seconds", "startup_timeout_seconds"):
        value = getattr(settings, f"speaking_ai_{field}", None)
        if value is not None:
            update[f"ai_writing_{field}"] = value
    return copied.model_copy(update=update)


def provider_identity(settings) -> tuple[str, str]:
    delegated = transport_settings(settings)
    provider = delegated.ai_writing_provider
    model = getattr(delegated, f"ai_writing_{provider}_model", "")
    return provider, model


def config_identity(settings) -> dict:
    delegated = transport_settings(settings)
    provider, model = provider_identity(settings)
    base = getattr(delegated, f"ai_writing_{provider}_base_url", "")
    return {
        "provider": provider, "model": model,
        "transport_fingerprint": hashlib.sha256(base.encode()).hexdigest(),
        "prompt_version": getattr(settings, "speaking_ai_prompt_version", "speaking-score-v1"),
        "rubric_version": getattr(settings, "speaking_ai_rubric_version", "speaking-rubric-v1"),
        "score_max_tokens": getattr(settings, "speaking_ai_score_max_tokens", 192),
        "feedback_max_tokens": getattr(settings, "speaking_ai_feedback_max_tokens", 1024),
        "request_timeout_seconds": delegated.ai_writing_request_timeout_seconds,
        "startup_timeout_seconds": delegated.ai_writing_startup_timeout_seconds,
    }


def is_configured(settings) -> bool:
    return writing_is_configured(transport_settings(settings))


class ConfiguredSpeakingProvider:
    def __init__(self, delegate):
        self.delegate = delegate

    async def ensure_ready(self):
        await self.delegate.ensure_ready()

    async def complete(self, messages, schema, *, options=None):
        return await self.delegate.complete(messages, schema, options=options)


def create_provider(settings):
    if not getattr(settings, "speaking_ai_enabled", False):
        raise AppError("SPEAKING_AI_NOT_CONFIGURED", "Speaking AI is not configured.", 503)
    try:
        delegate = create_writing_provider(transport_settings(settings))
    except AppError:
        raise AppError(
            "SPEAKING_AI_NOT_CONFIGURED", "Speaking AI is not configured.", 503
        ) from None
    return ConfiguredSpeakingProvider(delegate)
