from typing import Any

from app.core.config import Settings
from app.providers.writing_llm.base import Completion, Message
from app.providers.writing_llm.http import ChatCompletionHTTP


class VLLMProvider:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.ai_writing_vllm_model
        self.startup_timeout = settings.ai_writing_startup_timeout_seconds
        headers = {}
        if settings.ai_writing_vllm_api_key:
            headers["Authorization"] = f"Bearer {settings.ai_writing_vllm_api_key}"
        if settings.ai_writing_modal_key and settings.ai_writing_modal_secret:
            headers["Modal-Key"] = settings.ai_writing_modal_key
            headers["Modal-Secret"] = settings.ai_writing_modal_secret
        self.transport = ChatCompletionHTTP(
            settings.ai_writing_vllm_base_url, headers, settings.ai_writing_request_timeout_seconds
        )

    async def ensure_ready(self) -> None:
        await self.transport.ensure_model(self.model, self.startup_timeout)

    async def complete(self, messages: list[Message], schema: dict[str, Any]) -> Completion:
        return await self.transport.send(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "temperature": 0.0,
                "seed": 0,
                "max_tokens": 1800,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "assessment", "schema": schema},
                },
            }
        )
