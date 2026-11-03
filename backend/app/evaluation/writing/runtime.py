"""Content-free provider accounting shared by offline Writing evaluators."""

import asyncio
from collections import Counter
from typing import Any

from app.providers.writing_llm.base import (
    Completion,
    CompletionOptions,
    Message,
    ProviderFailure,
    safe_completion_usage,
    safe_finish_reason,
)


class CountedProvider:
    def __init__(self, provider):
        self.provider, self._calls, self.usage = provider, 0, Counter()
        initial_attempts = getattr(provider, "request_attempts", None)
        self._authoritative_attempts = type(initial_attempts) is int and initial_attempts >= 0
        self._initial_request_attempts = initial_attempts if self._authoritative_attempts else 0
        self.failure_usage = Counter()
        self.truncated_call_count = 0
        self.finish_reasons = Counter()

    @property
    def calls(self):
        # A provider can repair one truncated response inside complete(). Count
        # both POSTs, including requests interrupted before metadata is returned.
        if self._authoritative_attempts:
            return max(0, self.provider.request_attempts - self._initial_request_attempts)
        return self._calls

    def _record_attempts(self, result):
        attempts = getattr(result, "attempts", ())
        if self._authoritative_attempts and not attempts:
            # Admission rejection, queued timeout and queued cancellation have
            # no POST or finish metadata. The provider counter is authoritative.
            return
        self._calls += max(1, len(attempts))
        finishes = (
            [item.get("finish_reason") for item in attempts]
            if attempts
            else [getattr(result, "finish_reason", None)]
        )
        for value in finishes:
            finish = safe_finish_reason(value)
            self.finish_reasons[finish] += 1
            self.truncated_call_count += finish == "length"

    @property
    def task1_image_assessment(self):
        return getattr(self.provider, "task1_image_assessment", False)

    @property
    def run_timeout_seconds(self):
        return getattr(self.provider, "run_timeout_seconds", None)

    @property
    def policy(self):
        return getattr(self.provider, "policy", None)

    @property
    def reasoned_inference(self):
        return getattr(self.provider, "reasoned_inference", False)

    async def ensure_ready(self):
        await self.provider.ensure_ready()

    async def complete(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        *,
        options: CompletionOptions | None = None,
    ) -> Completion:
        try:
            completion = await self.provider.complete(messages, schema, options=options)
        except ProviderFailure as error:
            self._record_attempts(error)
            self.failure_usage.update(safe_completion_usage(error.usage))
            raise
        except asyncio.CancelledError as error:
            # A completed first attempt can be known even while its budget repair
            # is cancelled. Preserve known usage; the in-flight POST is unknown.
            self._record_attempts(error)
            self.failure_usage.update(safe_completion_usage(getattr(error, "usage", {})))
            raise
        except BaseException:
            # The request may have been billed; usage and finish are unknown.
            if not self._authoritative_attempts:
                self._calls += 1
            raise
        self.usage.update(safe_completion_usage(completion.usage))
        self._record_attempts(completion)
        return completion


def reconciled_usage(provider, scorer):
    observed = Counter(provider.usage) + provider.failure_usage
    recorded = Counter()
    if scorer is not None:
        for usage in scorer.usage:
            recorded.update(safe_completion_usage(usage))
    # Both sources describe the same calls. Never add their duplicate totals.
    return {
        key: max(observed.get(key, 0), recorded.get(key, 0))
        for key in observed.keys() | recorded.keys()
    }
