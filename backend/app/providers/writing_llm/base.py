from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict, get_args


class Message(TypedDict):
    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    usage: dict[str, int] = field(default_factory=dict)


OutputFailureReason = Literal[
    "INVALID_JSON",
    "SCHEMA_VALIDATION",
    "INVALID_HALF_BAND",
    "QUOTE_NOT_EXACT",
    "EVIDENCE_ITEM_TOO_LONG",
    "TOO_MANY_EVIDENCE_ITEMS",
    "FINISH_REASON_NOT_STOP",
    "EMPTY_MODEL_CONTENT",
    "MALFORMED_COMPLETION_ENVELOPE",
    "OUTPUT_TOO_LARGE",
]


class ProviderFailure(Exception):
    """Only allowlisted codes/messages cross this boundary; no raw exception bodies."""

    MESSAGES = {
        "AI_PROVIDER_UNREACHABLE": "The AI provider could not be reached. Please regrade.",
        "AI_PROVIDER_AUTH_FAILED": "AI provider authentication failed. Check the backend configuration.",
        "AI_PROVIDER_ENDPOINT_ERROR": "The AI provider endpoint is incorrect. Check the backend configuration.",
        "AI_PROVIDER_HTTP_ERROR": "The AI provider returned a server error. Please regrade.",
        "AI_PROVIDER_RATE_LIMITED": "The AI provider is busy. Please regrade later.",
        "AI_MODEL_UNAVAILABLE": "The configured AI model is unavailable. Check the backend configuration.",
        "AI_PROVIDER_STARTUP_TIMEOUT": "The AI model did not become ready in time. Please regrade.",
        "AI_PROVIDER_TIMEOUT": "The AI request timed out. Please regrade.",
        "AI_PROVIDER_BAD_RESPONSE": "The AI provider returned an invalid assessment. Please regrade.",
        # Retain compatibility with older stored failures and provider adapters.
        "PROVIDER_TIMEOUT": "AI grading timed out. Please regrade to try again.",
        "PROVIDER_HTTP_ERROR": "The AI provider is unavailable. Please regrade to try again.",
        "INVALID_PROVIDER_OUTPUT": "The AI provider returned an invalid assessment. Please regrade.",
    }

    def __init__(self, code: str, *, reason: OutputFailureReason | None = None) -> None:
        self.code = code
        self.message = self.MESSAGES[code]
        self.reason = reason if reason in get_args(OutputFailureReason) else None
        super().__init__(self.message)


class LLMProvider(Protocol):
    async def ensure_ready(self) -> None: ...

    async def complete(self, messages: list[Message], schema: dict[str, Any]) -> Completion: ...
