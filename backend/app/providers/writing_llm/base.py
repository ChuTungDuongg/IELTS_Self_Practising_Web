from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict, get_args


class Message(TypedDict):
    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


SafeFinishReason = Literal[
    "stop",
    "length",
    "abort",
    "error",
    "content_filter",
    "tool_calls",
    "function_call",
    "missing",
    "other",
]


def safe_finish_reason(value: object) -> SafeFinishReason:
    if value is None:
        return "missing"
    return value if isinstance(value, str) and value in get_args(SafeFinishReason) else "other"


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
    "EVIDENCE_UNKNOWN_SOURCE_ID",
    "EVIDENCE_SCHEMA_INVALID",
    "SCORE_SCHEMA_INVALID",
    "SCORE_CALIBRATION_INVALID",  # Historical diagnostics only; not emitted by v4 validation.
    "PROVIDER_FINISH_LENGTH",
    "PROVIDER_FINISH_ABORT",
    "PROVIDER_FINISH_ERROR",
    "PROVIDER_FINISH_OTHER",
]

# Non-fatal explanation diagnostics are distinct from repair/failure reasons.
CalibrationDiagnosticReason = Literal[
    "CALIBRATION_DROPPED",
    "CALIBRATION_SOURCE_DROPPED",
    "CALIBRATION_METADATA_NORMALIZED",
]


class ProviderFailure(Exception):
    """Only allowlisted codes/messages cross this boundary; no raw exception bodies."""

    MESSAGES = {
        "AI_PROVIDER_UNREACHABLE": "Không thể kết nối dịch vụ AI. Bạn có thể thử chấm lại.",
        "AI_PROVIDER_AUTH_FAILED": "Dịch vụ AI chưa được xác thực. Vui lòng kiểm tra cấu hình backend.",
        "AI_PROVIDER_ENDPOINT_ERROR": "Địa chỉ dịch vụ AI chưa đúng. Vui lòng kiểm tra cấu hình backend.",
        "AI_PROVIDER_HTTP_ERROR": "Dịch vụ AI gặp lỗi. Bạn có thể thử chấm lại.",
        "AI_PROVIDER_RATE_LIMITED": "Dịch vụ AI đang bận. Bạn có thể thử chấm lại sau.",
        "AI_MODEL_UNAVAILABLE": "Mô hình AI chưa sẵn sàng. Vui lòng kiểm tra cấu hình backend.",
        "AI_PROVIDER_STARTUP_TIMEOUT": "Mô hình AI chưa khởi động kịp. Bạn có thể thử chấm lại.",
        "AI_PROVIDER_TIMEOUT": "Yêu cầu AI quá thời gian cho phép. Bạn có thể thử chấm lại.",
        "AI_PROVIDER_BAD_RESPONSE": "AI trả về dữ liệu chưa hợp lệ. Bạn có thể thử chấm lại.",
        # Retain compatibility with older stored failures and provider adapters.
        "PROVIDER_TIMEOUT": "Chấm AI quá thời gian cho phép. Bạn có thể thử chấm lại.",
        "PROVIDER_HTTP_ERROR": "Dịch vụ AI chưa sẵn sàng. Bạn có thể thử chấm lại.",
        "INVALID_PROVIDER_OUTPUT": "AI trả về dữ liệu chưa hợp lệ. Bạn có thể thử chấm lại.",
    }

    def __init__(
        self,
        code: str,
        *,
        reason: OutputFailureReason | None = None,
        finish_reason: str | None = None,
    ) -> None:
        self.code = code
        self.message = self.MESSAGES[code]
        self.reason = reason if reason in get_args(OutputFailureReason) else None
        self.finish_reason = (
            safe_finish_reason(finish_reason) if finish_reason is not None else None
        )
        super().__init__(self.message)


class LLMProvider(Protocol):
    async def ensure_ready(self) -> None: ...

    async def complete(self, messages: list[Message], schema: dict[str, Any]) -> Completion: ...


def validate_finish(value: object) -> None:
    """vLLM 0.13 emits stop/length/abort/error; abort/error are not success.

    Source: vllm/v1/engine/__init__.py at v0.13.0. Tool/filter/unknown/missing
    metadata is unsupported for this text-only JSON interaction, classified
    separately from truncation. Never log an arbitrary provider-supplied value.
    """
    finish = safe_finish_reason(value)
    if finish == "stop":
        return
    reason = {
        "length": "PROVIDER_FINISH_LENGTH",
        "abort": "PROVIDER_FINISH_ABORT",
        "error": "PROVIDER_FINISH_ERROR",
    }.get(finish, "PROVIDER_FINISH_OTHER")
    raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason=reason, finish_reason=finish)
