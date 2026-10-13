"""Content-free provider accounting shared by offline Writing evaluators."""

from collections import Counter
from typing import Any

from app.providers.writing_llm.base import (
    Completion,
    CompletionOptions,
    Message,
    ProviderFailure,
    safe_completion_usage,
)


class CountedProvider:
    def __init__(self, provider):
        self.provider, self.calls, self.usage = provider, 0, Counter()
        self.failure_usage = Counter()

    async def ensure_ready(self):
        await self.provider.ensure_ready()

    async def complete(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        *,
        options: CompletionOptions | None = None,
    ) -> Completion:
        self.calls += 1
        try:
            completion = await self.provider.complete(messages, schema, options=options)
        except ProviderFailure as error:
            self.failure_usage.update(safe_completion_usage(error.usage))
            raise
        # Preserve existing Task 1 success-only counters without changing outputs.
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = completion.usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                self.usage[key] += value
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
