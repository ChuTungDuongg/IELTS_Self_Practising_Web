from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict


class Message(TypedDict):
    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    usage: dict[str, int] = field(default_factory=dict)


class ProviderFailure(Exception):
    """Only allowlisted codes/messages cross this boundary; no raw exception bodies."""

    MESSAGES = {
        "PROVIDER_TIMEOUT": "AI grading timed out. Please regrade to try again.",
        "PROVIDER_HTTP_ERROR": "The AI provider is unavailable. Please regrade to try again.",
        "INVALID_PROVIDER_OUTPUT": "The AI provider returned an invalid assessment. Please regrade.",
    }

    def __init__(self, code: str) -> None:
        self.code = code
        self.message = self.MESSAGES[code]
        super().__init__(self.message)


class LLMProvider(Protocol):
    async def complete(self, messages: list[Message], schema: dict[str, Any]) -> Completion: ...
