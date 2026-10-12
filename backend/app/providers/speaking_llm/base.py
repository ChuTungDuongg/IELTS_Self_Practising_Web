"""Reuse the structured transport contract, with a separate Speaking namespace."""

from typing import Protocol

from app.providers.writing_llm.base import Completion, CompletionOptions, Message

__all__ = ["Completion", "CompletionOptions", "Message", "SpeakingLLMProvider"]


class SpeakingLLMProvider(Protocol):
    async def ensure_ready(self) -> None: ...

    async def complete(
        self, messages: list[Message], schema: dict, *, options: CompletionOptions | None = None,
    ) -> Completion: ...
