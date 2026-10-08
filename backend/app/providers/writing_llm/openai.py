from typing import Any

from app.core.config import Settings
from app.providers.writing_llm.base import Completion, Message
from app.providers.writing_llm.http import ChatCompletionHTTP
from app.providers.writing_llm.messages import serialize_messages


class OpenAIProvider:
    """Dormant without a key. JSON mode plus local validation supports future models.

    Temperature/seed are omitted because support depends on the configured model.
    No reasoning fields are requested, parsed, stored or streamed.
    """

    def __init__(self, settings: Settings) -> None:
        self.model = settings.ai_writing_openai_model
        self.transport = ChatCompletionHTTP(
            settings.ai_writing_openai_base_url,
            {"Authorization": f"Bearer {settings.ai_writing_openai_api_key}"},
            settings.ai_writing_request_timeout_seconds,
        )

    async def ensure_ready(self) -> None:
        await self.transport.ensure_model(self.model, self.transport.timeout)

    async def complete(self, messages: list[Message], schema: dict[str, Any]) -> Completion:
        # Prompt construction already supplies the schema. The common MTS contract
        # validates JSON mode output identically to vLLM structured output.
        return await self.transport.send(
            {
                "model": self.model,
                "messages": serialize_messages(messages),
                "stream": False,
                "max_completion_tokens": 4096,
                "response_format": {"type": "json_object"},
            }
        )
