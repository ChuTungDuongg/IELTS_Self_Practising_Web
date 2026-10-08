"""Transport boundary used by MTS, independent of a hosting vendor."""

import httpx

from app.core.config import Settings
from app.core.exceptions import AppError
from app.providers.writing_llm.base import LLMProvider
from app.providers.writing_llm.http import api_base_url
from app.providers.writing_llm.openai import OpenAIProvider
from app.providers.writing_llm.vllm import VLLMProvider


def provider_identity(settings: Settings) -> tuple[str, str]:
    provider = settings.ai_writing_provider
    model = (
        settings.ai_writing_openai_model if provider == "openai" else settings.ai_writing_vllm_model
    )
    return provider, model


def is_configured(settings: Settings) -> bool:
    if not settings.ai_writing_enabled:
        return False
    base = (
        settings.ai_writing_openai_base_url
        if settings.ai_writing_provider == "openai"
        else settings.ai_writing_vllm_base_url
    )
    try:
        api_base_url(base)
    except (ValueError, TypeError, httpx.InvalidURL):
        return False
    if settings.ai_writing_provider == "openai":
        return bool(
            settings.ai_writing_openai_api_key
            and settings.ai_writing_openai_base_url
            and settings.ai_writing_openai_model
        )
    if settings.ai_writing_provider == "vllm":
        base = settings.ai_writing_vllm_base_url
        url = httpx.URL(base)
        if url.host.endswith((".modal.run", ".modal.direct")):
            if url.scheme != "https":
                return False
            if not (settings.ai_writing_modal_key and settings.ai_writing_modal_secret):
                return False
        return bool(base and settings.ai_writing_vllm_model)
    return False


def create_provider(settings: Settings) -> LLMProvider:
    if not is_configured(settings):
        raise AppError("AI_NOT_CONFIGURED", "AI grading is not configured.", 503)
    if settings.ai_writing_provider == "openai":
        return OpenAIProvider(settings)
    return VLLMProvider(settings)
