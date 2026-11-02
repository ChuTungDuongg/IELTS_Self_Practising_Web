import asyncio
import hashlib
import random
from typing import Any

from app.core.config import Settings
from app.providers.writing_llm.admission import admission
from app.providers.writing_llm.base import Completion, CompletionOptions, Message, ProviderFailure
from app.providers.writing_llm.http import ChatCompletionHTTP
from app.providers.writing_llm.messages import serialize_messages


def output_identity(settings: Settings, *, model: str | None = None) -> dict:
    model = model or settings.ai_writing_openai_model
    return {
        "contract": "openai-chat-json-v2",
        "endpoint_hash": hashlib.sha256(settings.ai_writing_openai_base_url.encode()).hexdigest(),
        "reasoning_effort": "none" if model == "gpt-6-luna" else "provider_default",
        "max_output_tokens": settings.ai_writing_openai_max_output_tokens,
    }


class OpenAIProvider:
    """Dormant without a key. JSON mode plus local validation supports future models.

    Temperature/seed are omitted because support depends on the configured model.
    Luna uses reasoning_effort=none so small score caps cover visible JSON.
    No reasoning content is parsed, stored or streamed.
    """

    def __init__(self, settings: Settings) -> None:
        self.model = settings.ai_writing_openai_model
        self.max_output_tokens = settings.ai_writing_openai_max_output_tokens
        self.limit = settings.ai_writing_openai_max_concurrent_requests
        self.max_queued = settings.ai_writing_openai_max_queued_requests
        self.readiness_retries = settings.ai_writing_openai_readiness_retries
        self.startup_timeout = settings.ai_writing_startup_timeout_seconds
        self.transport = ChatCompletionHTTP(
            settings.ai_writing_openai_base_url,
            {"Authorization": f"Bearer {settings.ai_writing_openai_api_key}"},
            settings.ai_writing_request_timeout_seconds,
        )

    async def ensure_ready(self) -> None:
        try:
            async with asyncio.timeout(self.startup_timeout):
                async with admission(self.limit, self.max_queued).slot():
                    for attempt in range(self.readiness_retries + 1):
                        try:
                            await self.transport.ensure_model(self.model, self.transport.timeout)
                            return
                        except ProviderFailure as exc:
                            if exc.code not in {
                                "AI_PROVIDER_RATE_LIMITED",
                                "AI_PROVIDER_UNREACHABLE",
                                "AI_MODEL_UNAVAILABLE",
                                "AI_PROVIDER_HTTP_ERROR",
                            }:
                                raise
                            if attempt == self.readiness_retries:
                                raise
                            await asyncio.sleep(0.5 * 2**attempt + random.uniform(0, 0.25))
        except TimeoutError:
            raise ProviderFailure("AI_PROVIDER_STARTUP_TIMEOUT") from None

    async def complete(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        *,
        options: CompletionOptions | None = None,
    ) -> Completion:
        # Prompt construction already supplies the schema. The common MTS contract
        # validates JSON mode output identically to vLLM structured output.
        body = {
            "model": self.model,
            "messages": serialize_messages(messages),
            "stream": False,
            "max_completion_tokens": min(options.max_tokens, self.max_output_tokens)
            if options is not None and options.max_tokens is not None
            else self.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.model == "gpt-6-luna":
            body["reasoning_effort"] = "none"
        # POSTs are not replayed: timeout/5xx can follow billable inference. The
        # existing scorer may repair invalid successful JSON once, explicitly.
        try:
            async with asyncio.timeout(self.transport.timeout):
                async with admission(self.limit, self.max_queued).slot():
                    return await self.transport.send(body)
        except TimeoutError:
            raise ProviderFailure("AI_PROVIDER_TIMEOUT") from None
