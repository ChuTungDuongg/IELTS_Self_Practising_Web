import asyncio
import hashlib
import logging
import random
import time
from typing import Any

from app.core.config import Settings
from app.core.exceptions import AppError
from app.providers.writing_llm.admission import admission
from app.providers.writing_llm.base import (
    Completion,
    CompletionOptions,
    ImagePart,
    Message,
    ProviderFailure,
    safe_completion_usage,
)
from app.providers.writing_llm.http import ChatCompletionHTTP
from app.providers.writing_llm.messages import serialize_messages
from app.providers.writing_llm.policy import OpenAIInferencePolicy

logger = logging.getLogger(__name__)


def output_identity(settings: Settings, *, model: str | None = None) -> dict:
    try:
        policy = OpenAIInferencePolicy(settings, model=model)
    except ProviderFailure as exc:
        # Identities are computed by request services before provider creation.
        # Keep configuration failures inside the application's structured error
        # boundary instead of leaking an unhandled provider exception as HTTP 500.
        raise AppError(exc.code, exc.message, 503) from None
    return {
        "contract": "openai-chat-json-v3",
        "task1_assessment_contract": "source-image-envelope-v1",
        "endpoint_hash": hashlib.sha256(settings.ai_writing_openai_base_url.encode()).hexdigest(),
        **policy.identity(),
    }


class OpenAIProvider:
    """Dormant without a key. JSON mode plus local validation supports future models.

    Temperature/seed are omitted because support depends on the configured model.
    Luna receives stage-specific reasoning + total completion budgets. No
    reasoning content is requested, parsed, stored or streamed. Only a definite
    length finish can trigger one explicitly bounded budget repair.
    """

    def __init__(self, settings: Settings) -> None:
        self.model = settings.ai_writing_openai_model
        self.policy = OpenAIInferencePolicy(settings)
        self.reasoned_inference = True
        self.task1_image_assessment = settings.ai_writing_openai_task1_image_assessment
        self.run_timeout_seconds = settings.ai_writing_openai_run_timeout_seconds
        self.request_attempts = 0
        self.max_output_tokens = settings.ai_writing_openai_max_output_tokens
        self.limit = settings.ai_writing_openai_max_concurrent_requests
        self.max_queued = settings.ai_writing_openai_max_queued_requests
        self.readiness_retries = settings.ai_writing_openai_readiness_retries
        self.startup_timeout = settings.ai_writing_startup_timeout_seconds
        self.transport = ChatCompletionHTTP(
            settings.ai_writing_openai_base_url,
            {"Authorization": f"Bearer {settings.ai_writing_openai_api_key}"},
            settings.ai_writing_request_timeout_seconds,
            openai_semantics=True,
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
        options = options or CompletionOptions()
        has_image = any(
            isinstance(part, ImagePart)
            for message in messages
            if isinstance(message["content"], list)
            for part in message["content"]
        )
        policy = self.policy.resolve(options, has_image=has_image)
        budget = policy.total_completion_tokens
        if options.attempt == 2:
            # An explicit outer schema repair has no additional budget retry.
            budget = max(budget, policy.repair_completion_tokens)
        # Prompt construction supplies the schema. Domain validation remains
        # authoritative; this endpoint has one cap for reasoning + visible JSON.
        body = {
            "model": self.model,
            "messages": serialize_messages(messages, image_detail=policy.image_detail),
            "stream": False,
            "max_completion_tokens": budget,
            "response_format": {"type": "json_object"},
            "reasoning_effort": policy.reasoning_effort,
        }
        usages: dict[str, int] = {}
        attempts: list[dict[str, Any]] = []
        started = time.monotonic()
        attempt_started = started
        request_in_flight = False

        def record(
            *, usage: dict, finish: str | None, code: str | None = None, reason: str | None = None
        ) -> None:
            nonlocal attempt_started
            safe_usage = safe_completion_usage(usage)
            for key, count in safe_usage.items():
                usages[key] = usages.get(key, 0) + count
            elapsed_ms = max(0, round((time.monotonic() - attempt_started) * 1000))
            metadata = {
                "profile": policy.profile,
                "model": self.model,
                "task": policy.task,
                "stage": policy.stage,
                "criterion": policy.criterion,
                "schema_attempt": options.attempt,
                "attempt": len(attempts) + 1,
                "reasoning_effort": policy.reasoning_effort,
                "image_detail": policy.image_detail,
                "completion_budget": body["max_completion_tokens"],
                "timeout_seconds": policy.timeout_seconds,
                "finish_reason": finish,
                "latency_ms": elapsed_ms,
                "usage": safe_usage,
            }
            if code is not None:
                metadata["failure_code"] = code
            if reason is not None:
                metadata["failure_reason"] = reason
            attempts.append(metadata)
            # Only resolved policy + allowlisted counters; no provider body,
            # prompt, secret, image or internal reasoning can reach this log.
            logger.info("OpenAI inference attempt: %s", metadata)
            attempt_started = time.monotonic()

        # The timeout covers admission + both possible requests together. Timeout,
        # 5xx and cancellation never replay a possibly billable inference POST.
        try:
            async with asyncio.timeout(policy.timeout_seconds):
                async with admission(self.limit, self.max_queued).slot():
                    for budget_attempt in range(2):
                        attempt_started = time.monotonic()
                        try:
                            self.request_attempts += 1
                            request_in_flight = True
                            completion = await self.transport.send(body)
                        except ProviderFailure as exc:
                            request_in_flight = False
                            record(
                                usage=exc.usage,
                                finish=exc.finish_reason,
                                code=exc.code,
                                reason=exc.reason,
                            )
                            is_length = exc.reason == "PROVIDER_FINISH_LENGTH"
                            can_repair = (
                                is_length
                                and budget_attempt == 0
                                and options.attempt == 1
                                and policy.repair_completion_tokens > body["max_completion_tokens"]
                            )
                            if can_repair:
                                body["max_completion_tokens"] = policy.repair_completion_tokens
                                continue
                            if is_length:
                                exc = ProviderFailure(
                                    exc.code,
                                    reason="COMPLETION_BUDGET_EXHAUSTED",
                                    finish_reason=exc.finish_reason,
                                )
                            exc.usage = usages.copy()
                            exc.attempts = tuple(attempts)
                            raise exc
                        request_in_flight = False
                        record(usage=completion.usage, finish=completion.finish_reason)
                        return Completion(
                            completion.text,
                            usages.copy(),
                            completion.finish_reason,
                            tuple(attempts),
                        )
        except TimeoutError:
            if request_in_flight:
                record(usage={}, finish=None, code="AI_PROVIDER_TIMEOUT")
            raise ProviderFailure(
                "AI_PROVIDER_TIMEOUT", usage=usages, attempts=tuple(attempts)
            ) from None
        except asyncio.CancelledError as exc:
            if request_in_flight:
                record(usage={}, finish=None)
            # Keep known billed usage from a completed length attempt available
            # to accounting consumers, while cancellation still propagates.
            # The interrupted request's unknown usage remains absent.
            exc.usage = usages.copy()
            exc.attempts = tuple(attempts)
            raise
