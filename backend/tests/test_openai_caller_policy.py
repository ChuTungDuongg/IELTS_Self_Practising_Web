"""Caller metadata/accounting contracts using fictional inputs and fake inference."""

import asyncio
import json

import pytest
from test_speaking_ai import FEEDBACK, FakeProvider, checkpoint, evidence
from test_speaking_usage import memory_worker
from test_task1_visual import request
from test_writing_completion_budgets import BudgetProvider, assess

from app.providers.writing_llm.base import Completion, ProviderFailure
from app.services.speaking_scorer import SpeakingScorer
from app.services.task1_grounding import Task1VisualGroundingService
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_execution import WritingLatencyMetrics
from app.services.writing_relevance import classify_relevance


async def test_speaking_historical_get_does_not_require_current_inference_config(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.core.config import Settings
    from app.core.exceptions import AppError
    from app.services.speaking_ai import SpeakingAIService

    settings = Settings(
        _env_file=None,
        ai_writing_provider="openai",
        speaking_ai_provider="openai",
        ai_writing_openai_max_output_tokens=4096,
    )
    service = SpeakingAIService(None, SimpleNamespace(id=uuid4()), settings)
    old_result = SimpleNamespace(status="COMPLETED")

    async def snapshot(*_args):
        return old_result, []

    monkeypatch.setattr(service, "snapshot", snapshot)
    assert await service.get(uuid4(), uuid4()) is old_result
    # Only new inference/cache identity resolution needs the active valid policy.
    with pytest.raises(AppError) as failure:
        _ = service.identity
    assert failure.value.code == "AI_PROVIDER_CONFIGURATION_ERROR"


async def test_speaking_score_repair_feedback_have_explicit_metadata():
    provider = FakeProvider({"score": 6.3}, {"score": 6.5}, FEEDBACK)
    result = await SpeakingScorer(provider).score_criterion("fc", evidence(), checkpoint)
    assert result.status == "COMPLETED"
    options = [call[2] for call in provider.calls]
    assert [(o.task, o.stage, o.criterion, o.attempt) for o in options] == [
        ("speaking", "score", "fc", 1),
        ("speaking", "score", "fc", 2),
        ("speaking", "feedback", "fc", 1),
    ]
    assert [o.max_tokens for o in options] == [192, 192, 1024]


async def test_task2_passes_task_stage_and_criterion_without_changing_visible_targets():
    provider = BudgetProvider()
    result, _, _ = await assess(provider)
    assert result is not None
    assert {o.criterion for _, _, o in provider.calls} == {"ta", "cc", "lr", "gra"}
    assert all(o.task == "task2" and o.attempt == 1 for _, _, o in provider.calls)
    assert {o.stage: o.max_tokens for _, _, o in provider.calls} == {
        "score": 128,
        "evidence": 1800,
        "feedback": 1200,
    }


async def test_grounding_keeps_failed_usage_and_does_not_retry_budget_exhaustion():
    class Provider:
        reasoned_inference = True
        calls = 0

        async def complete(self, *_args, **_kwargs):
            self.calls += 1
            raise ProviderFailure(
                "AI_PROVIDER_BAD_RESPONSE",
                reason="COMPLETION_BUDGET_EXHAUSTED",
                finish_reason="length",
                usage={"completion_tokens": 100, "reasoning_tokens": 90},
            )

    provider = Provider()
    usage = []
    with pytest.raises(ProviderFailure):
        await Task1VisualGroundingService(provider, usage).ground(request())
    assert provider.calls == 1 and usage == [{"completion_tokens": 100, "reasoning_tokens": 90}]


@pytest.mark.parametrize(
    "reason",
    [
        "COMPLETION_BUDGET_EXHAUSTED",
        "PROVIDER_FINISH_ABORT",
        "PROVIDER_FINISH_ERROR",
        "PROVIDER_FINISH_OTHER",
    ],
)
async def test_relevance_failed_attempt_usage_is_retained_once(reason):
    class Provider:
        reasoned_inference = True
        calls = 0

        async def complete(self, *_args, **_kwargs):
            self.calls += 1
            raise ProviderFailure(
                "AI_PROVIDER_BAD_RESPONSE",
                reason=reason,
                finish_reason="length",
                usage={"completion_tokens": 100, "reasoning_tokens": 90},
            )

    async def trace(*_args):
        pass

    provider, usage = Provider(), []
    result = await classify_relevance(
        provider, request(), None, trace, usage, [], WritingLatencyMetrics()
    )
    assert result is None and provider.calls == 1
    assert usage == [{"completion_tokens": 100, "reasoning_tokens": 90}]


async def test_total_assessment_timeout_drains_children_and_keeps_completed_traits():
    from test_task1_visual import Task1FakeProvider

    class Provider(Task1FakeProvider):
        run_timeout_seconds = 0.2
        active = 0

        async def complete(self, messages, schema, *, options=None):
            if options and options.stage == "visual_grounding":
                self.active += 1
                try:
                    await asyncio.Event().wait()
                finally:
                    self.active -= 1
            return await super().complete(messages, schema, options=options)

    async def trace(*_args):
        pass

    provider = Provider()
    service = Task1WritingScoringService(provider, max_concurrent_requests=4)
    with pytest.raises(ProviderFailure) as failure:
        await service.assess(request(), trace)
    assert failure.value.code == "AI_PROVIDER_TIMEOUT"
    assert provider.active == service.provider.active == 0
    assert all(service.states[t].result for t in ("cc", "lr", "gra"))


async def test_speaking_worker_preserves_reasoning_subset_without_double_count(monkeypatch):
    usage = {
        "prompt_tokens": 20,
        "completion_tokens": 100,
        "total_tokens": 120,
        "reasoning_tokens": 90,
    }
    provider = FakeProvider(
        Completion('{"score":6.5}', usage), Completion(json.dumps(FEEDBACK), usage)
    )
    worker, run = memory_worker(monkeypatch, provider)
    run.status = "RUNNING"
    await worker._record_provider_call(
        run.id,
        run.lease_token,
        {
            "criterion": "fc",
            "stage": "score",
            "finish_reason": "stop",
            "usage": usage,
        },
    )
    assert run.usage_json["totals"] == usage
