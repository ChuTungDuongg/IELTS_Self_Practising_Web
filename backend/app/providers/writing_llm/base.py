import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict, get_args


class Message(TypedDict):
    role: Literal["system", "user"]
    content: str | list["TextPart | ImagePart"]


class TextPart(TypedDict):
    type: Literal["text"]
    text: str


@dataclass(frozen=True, slots=True)
class ImagePart:
    """Backend-loaded bytes only; no URL input and no accidental bytes in repr."""

    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        signatures = {
            "image/png": self.data.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": self.data.startswith(b"\xff\xd8\xff"),
            "image/webp": self.data.startswith(b"RIFF") and self.data[8:12] == b"WEBP",
        }
        if not signatures.get(self.mime_type) or not 0 < len(self.data) <= 10 * 1024 * 1024:
            raise ValueError("Invalid trusted image type or size")


@dataclass(frozen=True)
class Completion:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    attempts: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CompletionOptions:
    """Explicit inference purpose, independent from the contents of a prompt.

    ``max_tokens`` remains the legacy visible/business output target for vLLM.
    OpenAI's policy supplies a separate total reasoning + visible token budget.
    ``attempt`` is the caller's bounded schema-repair attempt (1 or 2).
    """

    max_tokens: int | None = None
    task: Literal["task1", "task2", "speaking"] | None = None
    stage: str = "default"
    criterion: str | None = None
    attempt: int = 1
    # Business-output deltas only. None resets a provisional preview per attempt.
    on_content: Callable[[str | None], Awaitable[None]] | None = field(default=None, repr=False)


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


def safe_completion_usage(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts = {
        key: count
        for key, count in value.items()
        if key in {"prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"}
        and type(count) is int
        and 0 <= count <= 10_000_000
    }
    details = value.get("completion_tokens_details")
    if isinstance(details, dict):
        reasoning = details.get("reasoning_tokens")
        if type(reasoning) is int and 0 <= reasoning <= 10_000_000:
            counts["reasoning_tokens"] = reasoning
    # Reasoning is a subset of completion_tokens, never an additional billable
    # quantity. Missing counters stay missing; do not estimate provider usage.
    return counts


OutputFailureReason = Literal[
    "RELEVANCE_AUXILIARY_FAILED",
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
    "FEEDBACK_SCHEMA_INVALID",
    "FEEDBACK_SCORE_MISMATCH",
    "SCORE_CALIBRATION_INVALID",  # Historical diagnostics only; not emitted by v4 validation.
    "PROVIDER_FINISH_LENGTH",
    "PROVIDER_FINISH_ABORT",
    "PROVIDER_FINISH_ERROR",
    "PROVIDER_FINISH_OTHER",
    "PROVIDER_CONTENT_FILTER",
    "PROVIDER_REFUSAL",
    "COMPLETION_BUDGET_EXHAUSTED",
]

# Non-fatal explanation diagnostics are distinct from repair/failure reasons.
CalibrationDiagnosticReason = Literal[
    "CALIBRATION_DROPPED",
    "CALIBRATION_SOURCE_DROPPED",
    "CALIBRATION_METADATA_NORMALIZED",
]

PresentationDiagnosticReason = Literal[
    "SCORE_PRESENTATION_NORMALIZED",
    "FEEDBACK_PRESENTATION_NORMALIZED",
    "FEEDBACK_FALLBACK_USED",
    "EVIDENCE_PRESENTATION_NORMALIZED",
    "EVIDENCE_ITEM_DROPPED",
    "EVIDENCE_FALLBACK_USED",
    "FEEDBACK_OBSERVATION_DROPPED",
    "LANGUAGE_FEEDBACK_VERIFICATION_UNAVAILABLE",
]


class ProviderFailure(Exception):
    """Only allowlisted codes/messages cross this boundary; no raw exception bodies."""

    MESSAGES = {
        "AI_PROVIDER_UNREACHABLE": "Không thể kết nối dịch vụ AI. Bạn có thể thử chấm lại.",
        "AI_PROVIDER_AUTH_FAILED": "Dịch vụ AI chưa được xác thực. Vui lòng kiểm tra cấu hình backend.",
        "AI_PROVIDER_ENDPOINT_ERROR": "Địa chỉ dịch vụ AI chưa đúng. Vui lòng kiểm tra cấu hình backend.",
        "AI_PROVIDER_HTTP_ERROR": "Dịch vụ AI gặp lỗi. Bạn có thể thử chấm lại.",
        "AI_PROVIDER_RATE_LIMITED": "Dịch vụ AI đang bận. Bạn có thể thử chấm lại sau.",
        "AI_PROVIDER_QUOTA_EXHAUSTED": "Hạn mức thanh toán AI đã hết. Vui lòng kiểm tra tài khoản nhà cung cấp.",
        "AI_PROVIDER_BUSY": "Dịch vụ chấm AI đang đầy. Vui lòng thử lại sau.",
        "AI_PROVIDER_CONFIGURATION_ERROR": "Cấu hình giới hạn AI chưa thống nhất. Vui lòng kiểm tra backend.",
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
        usage: dict | None = None,
        attempts: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.code = code
        self.message = self.MESSAGES[code]
        self.reason = reason if reason in get_args(OutputFailureReason) else None
        self.finish_reason = (
            safe_finish_reason(finish_reason) if finish_reason is not None else None
        )
        self.usage = safe_completion_usage(usage)
        self.attempts = attempts
        super().__init__(self.message)


def safe_inference_attempts(value: object) -> list[dict[str, Any]]:
    """Revalidate optional provider audit metadata at persistence boundaries.

    There are at most two HTTP attempts per logical OpenAI completion. Allowlist
    policy identifiers and counters; arbitrary bodies, prompts and reasoning
    fields are never retained even from a mutated/mock Completion object.
    """
    if not isinstance(value, (list, tuple)):
        return []
    enums = {
        "profile": {"openai_task1_reasoned_v1"},
        "model": {"gpt-6-luna"},
        "task": {"default", "task1", "task2", "speaking"},
        "stage": {
            "default",
            "visual_grounding",
            "visual_reconciliation",
            "claim_extraction",
            "claim_verification",
            "evidence",
            "evidence_selection",
            "relevance",
            "relevance_classification",
            "scoring",
            "feedback",
            "language_feedback",
        },
        "criterion": {"ta", "tr", "cc", "lr", "gra", "fc", "pr"},
        "reasoning_effort": {"none", "low", "medium", "high", "xhigh", "max"},
        "image_detail": {"auto", "low", "high", "original"},
    }
    numeric_ranges = {
        "schema_attempt": (1, 2),
        "attempt": (1, 2),
        "completion_budget": (128, 32768),
        "latency_ms": (0, 900_000),
    }
    safe = []
    for item in value[:2]:
        if not isinstance(item, dict):
            continue
        if any(
            not isinstance(item.get(key), str) or item[key] not in enums[key]
            for key in ("profile", "model", "task", "stage")
        ):
            continue
        record = {}
        for key, allowed in enums.items():
            field_value = item.get(key)
            if isinstance(field_value, str) and field_value in allowed:
                record[key] = field_value
            elif key in {"criterion", "image_detail"} and field_value is None:
                record[key] = None
        for key, (minimum, maximum) in numeric_ranges.items():
            field_value = item.get(key)
            if type(field_value) is int and minimum <= field_value <= maximum:
                record[key] = field_value
        timeout = item.get("timeout_seconds")
        if type(timeout) in {int, float} and 0 < timeout <= 900 and math.isfinite(timeout):
            record["timeout_seconds"] = timeout
        finish = item.get("finish_reason")
        record["finish_reason"] = safe_finish_reason(finish) if finish is not None else None
        record["usage"] = safe_completion_usage(item.get("usage"))
        code = item.get("failure_code")
        if isinstance(code, str) and code in ProviderFailure.MESSAGES:
            record["failure_code"] = code
        reason = item.get("failure_reason")
        if isinstance(reason, str) and reason in get_args(OutputFailureReason):
            record["failure_reason"] = reason
        safe.append(record)
    return safe


class LLMProvider(Protocol):
    async def ensure_ready(self) -> None: ...

    async def complete(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        *,
        options: CompletionOptions | None = None,
    ) -> Completion: ...


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
