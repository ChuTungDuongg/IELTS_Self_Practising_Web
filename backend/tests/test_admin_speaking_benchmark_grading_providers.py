"""Real production OpenAI repair loop, with no HTTP or paid inference."""

import pytest

from app.core.config import Settings
from app.providers.writing_llm.base import Completion, CompletionOptions, ProviderFailure
from app.providers.writing_llm.openai import OpenAIProvider


class MemoryLedger:
    def __init__(self):
        self.rows = []

    async def cached(self, *args):
        return None

    async def begin(self, stage, provider, identity):
        self.rows.append({"status": "ATTEMPTED", "stage": stage})
        return len(self.rows) - 1

    async def finish(self, identifier, result, **kwargs):
        self.rows[identifier].update(status="COMPLETED", result=result)

    async def interrupt(self, identifier, code):
        self.rows[identifier]["status"] = "INTERRUPTED_BILLING_UNKNOWN"


async def test_internal_length_repair_has_a_committed_attempt_before_each_send():
    from app.services.speaking_benchmark_providers import LedgerSpeakingProvider

    ledger = MemoryLedger()
    provider = OpenAIProvider(
        Settings(
            _env_file=None,
            ai_writing_openai_api_key="fictional-offline-key",
            ai_writing_openai_model="gpt-6-luna",
        )
    )

    class FakeHTTP:
        calls = 0

        async def send(self, body):
            assert ledger.rows[-1]["status"] == "ATTEMPTED"
            self.calls += 1
            if self.calls == 1:
                raise ProviderFailure(
                    "AI_PROVIDER_BAD_RESPONSE",
                    reason="PROVIDER_FINISH_LENGTH",
                    finish_reason="length",
                    usage={"total_tokens": 20},
                )
            return Completion('{"score": 6}', {"total_tokens": 30}, "stop")

    transport = FakeHTTP()
    provider.transport = transport
    wrapper = LedgerSpeakingProvider(provider, ledger, "config")
    result = await wrapper.complete(
        [{"role": "user", "content": "fictional"}],
        {},
        options=CompletionOptions(task="speaking", stage="score", criterion="gra"),
    )
    assert result.text == '{"score": 6}'
    assert transport.calls == 2
    assert len(ledger.rows) == 2
    assert all(row["status"] == "COMPLETED" for row in ledger.rows)


async def test_timeout_is_unknown_and_not_automatically_replayed():
    from app.services.speaking_benchmark_providers import LedgerTransport

    ledger = MemoryLedger()

    class TimeoutHTTP:
        async def send(self, body):
            raise TimeoutError()

    wrapped = LedgerTransport(TimeoutHTTP(), ledger, "config")
    with pytest.raises(TimeoutError):
        await wrapped.send({"messages": []})
    assert len(ledger.rows) == 1
    assert ledger.rows[0]["status"] == "INTERRUPTED_BILLING_UNKNOWN"
