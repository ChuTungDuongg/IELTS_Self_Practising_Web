"""Offline inference contracts; these tests do not establish IELTS band accuracy."""

import asyncio
import base64
import json

import httpx
import pytest

from app.core.config import Settings
from app.providers.writing_llm.base import CompletionOptions, ImagePart, ProviderFailure
from app.providers.writing_llm.openai import OpenAIProvider, output_identity
from app.providers.writing_llm.vllm import VLLMProvider


def settings(**changes):
    return Settings(_env_file=None, **changes)


def intercept(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )


def response(*, finish="stop", content='{"ok":true}', usage=None, refusal=None):
    return httpx.Response(
        200,
        json={
            "choices": [
                {"finish_reason": finish, "message": {"content": content, "refusal": refusal}}
            ],
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        },
    )


@pytest.mark.parametrize(
    "task,stage,criterion,effort,budget",
    [
        (None, "default", None, "low", 8192),
        ("task1", "visual_grounding", None, "medium", 16384),
        ("task1", "claim_extraction", None, "low", 8192),
        ("task1", "claim_verification", None, "medium", 16384),
        ("task1", "score", "TA", "medium", 16384),
        ("task1", "scoring", "TA", "medium", 16384),
        ("task1", "scoring", "LR", "low", 8192),
        ("task1", "feedback", "TA", "low", 8192),
        ("task2", "scoring", "TR", "low", 8192),
        ("speaking", "scoring", "FC", "low", 8192),
        ("speaking", "scoring", "LR", "low", 8192),
        ("speaking", "scoring", "GRA", "low", 8192),
        ("speaking", "scoring", "PR", "low", 8192),
    ],
)
async def test_stage_policy_sets_real_payload_without_legacy_clamp(
    monkeypatch, task, stage, criterion, effort, budget
):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return response()

    intercept(monkeypatch, handler)
    result = await OpenAIProvider(settings()).complete(
        [{"role": "user", "content": "JSON for a fictional task."}],
        {},
        options=CompletionOptions(max_tokens=128, task=task, stage=stage, criterion=criterion),
    )
    assert bodies[0]["reasoning_effort"] == effort
    assert bodies[0]["max_completion_tokens"] == budget
    assert not {"max_tokens", "reasoning", "temperature", "seed"} & bodies[0].keys()
    assert result.usage["total_tokens"] == 30
    assert result.attempts[0]["reasoning_effort"] == effort
    assert result.attempts[0]["completion_budget"] == budget


@pytest.mark.parametrize("detail", ["high", "auto", "low"])
async def test_openai_image_detail_is_inside_image_url_without_reencoding(monkeypatch, detail):
    data = b"\x89PNG\r\n\x1a\nfictional-image"
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return response()

    intercept(monkeypatch, handler)
    provider = OpenAIProvider(settings(ai_writing_openai_image_detail=detail))
    await provider.complete(
        [{"role": "user", "content": [ImagePart("image/png", data)]}],
        {},
        options=CompletionOptions(task="task1", stage="scoring", criterion="TA"),
    )
    part = bodies[0]["messages"][0]["content"][0]
    assert part == {
        "type": "image_url",
        "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(data).decode(),
            "detail": detail,
        },
    }
    assert provider.task1_image_assessment is True


async def test_vllm_keeps_existing_payload_and_small_business_cap(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return response()

    intercept(monkeypatch, handler)
    await VLLMProvider(settings(ai_writing_vllm_base_url="https://fictional.invalid/v1")).complete(
        [{"role": "user", "content": [ImagePart("image/png", b"\x89PNG\r\n\x1a\nfixture")]}],
        {},
        options=CompletionOptions(max_tokens=192, task="task1", stage="scoring", criterion="TA"),
    )
    assert bodies[0]["max_tokens"] == 192
    assert "reasoning_effort" not in bodies[0]
    assert "detail" not in bodies[0]["messages"][0]["content"][0]["image_url"]


@pytest.mark.parametrize(
    "changes",
    [
        {"ai_writing_openai_max_output_tokens": 4096},
        {"ai_writing_openai_model": "unverified-model"},
        {"ai_writing_openai_stage_overrides": {"task1.unknown": {"reasoning_effort": "high"}}},
        {
            "ai_writing_openai_max_output_tokens": 20000,
            "ai_writing_openai_stage_overrides": {
                "task1.scoring.TA": {"total_completion_tokens": 32768}
            },
        },
    ],
)
def test_unsafe_configuration_fails_before_inference(changes):
    with pytest.raises(ProviderFailure) as failure:
        OpenAIProvider(settings(**changes))
    assert failure.value.code == "AI_PROVIDER_CONFIGURATION_ERROR"


async def test_explicit_stage_override_and_global_cap_are_respected(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return response()

    intercept(monkeypatch, handler)
    provider = OpenAIProvider(
        settings(
            ai_writing_openai_max_output_tokens=20000,
            ai_writing_openai_repair_completion_tokens=20000,
            ai_writing_openai_stage_overrides={
                "task1.scoring.TA": {
                    "reasoning_effort": "high",
                    "total_completion_tokens": 18000,
                    "timeout_seconds": 120,
                }
            },
        )
    )
    result = await provider.complete(
        [], {}, options=CompletionOptions(task="task1", stage="score", criterion="TA")
    )
    assert bodies[0]["reasoning_effort"] == "high"
    assert bodies[0]["max_completion_tokens"] == 18000
    assert result.attempts[0]["timeout_seconds"] == 120


async def test_length_repairs_once_with_larger_budget_and_combines_usage_once(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return response(
            finish="length" if len(bodies) == 1 else "stop",
            content='{"partial":' if len(bodies) == 1 else '{"ok":true}',
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 100,
                "total_tokens": 110,
                "completion_tokens_details": {"reasoning_tokens": 90},
                "secret": "private",
            },
        )

    intercept(monkeypatch, handler)
    result = await OpenAIProvider(settings()).complete(
        [], {}, options=CompletionOptions(task="task1", stage="scoring", criterion="TA")
    )
    assert [body["max_completion_tokens"] for body in bodies] == [16384, 32768]
    assert bodies[0]["messages"] == bodies[1]["messages"]
    assert result.text == '{"ok":true}'
    assert result.usage == {
        "prompt_tokens": 20,
        "completion_tokens": 200,
        "total_tokens": 220,
        "reasoning_tokens": 180,
    }
    assert [attempt["finish_reason"] for attempt in result.attempts] == ["length", "stop"]


@pytest.mark.parametrize("schema_attempt,expected_calls", [(1, 2), (2, 1)])
async def test_budget_exhaustion_is_terminal_and_keeps_failed_attempt_usage(
    monkeypatch, schema_attempt, expected_calls
):
    calls = []

    def handler(request):
        calls.append(request)
        return response(finish="length", content="")

    intercept(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as failure:
        await OpenAIProvider(settings()).complete(
            [],
            {},
            options=CompletionOptions(
                task="task1", stage="scoring", criterion="TA", attempt=schema_attempt
            ),
        )
    assert failure.value.reason == "COMPLETION_BUDGET_EXHAUSTED"
    assert len(calls) == expected_calls
    assert failure.value.usage["total_tokens"] == 30 * expected_calls
    assert len(failure.value.attempts) == expected_calls


@pytest.mark.parametrize(
    "failure_kind,expected_reason",
    [
        ("empty", "EMPTY_MODEL_CONTENT"),
        ("refusal", "PROVIDER_REFUSAL"),
        ("filter", "PROVIDER_CONTENT_FILTER"),
        ("malformed", "MALFORMED_COMPLETION_ENVELOPE"),
    ],
)
async def test_non_budget_failures_are_never_budget_repaired(
    monkeypatch, failure_kind, expected_reason
):
    calls = []

    def handler(request):
        calls.append(request)
        return response(
            finish="content_filter" if failure_kind == "filter" else "stop",
            content=None if failure_kind in {"refusal", "malformed"} else "",
            refusal="private refusal" if failure_kind == "refusal" else None,
        )

    intercept(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as failure:
        await OpenAIProvider(settings()).complete([], {})
    assert failure.value.reason == expected_reason
    assert failure.value.usage["total_tokens"] == 30
    assert len(calls) == 1
    assert "private refusal" not in str(failure.value)


async def test_failed_budget_repair_timeout_keeps_known_usage_without_replaying(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return response(finish="length", content="")
        raise httpx.ReadTimeout("private", request=request)

    intercept(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as failure:
        await OpenAIProvider(settings()).complete([], {})
    assert failure.value.code == "AI_PROVIDER_TIMEOUT"
    assert failure.value.usage["total_tokens"] == 30
    assert len(calls) == len(failure.value.attempts) == 2
    assert failure.value.attempts[-1]["usage"] == {}


async def test_cancellation_during_budget_repair_propagates(monkeypatch):
    started = asyncio.Event()
    calls = []

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return response(finish="length", content="")
        started.set()
        await asyncio.Event().wait()

    intercept(monkeypatch, handler)
    job = asyncio.create_task(OpenAIProvider(settings()).complete([], {}))
    try:
        await asyncio.wait_for(started.wait(), 2)
        job.cancel()
        with pytest.raises(asyncio.CancelledError) as failure:
            await job
        assert len(calls) == 2
        assert failure.value.usage["total_tokens"] == 30
        assert len(failure.value.attempts) == 2
        assert failure.value.attempts[-1]["usage"] == {}
    finally:
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.parametrize(
    "changes",
    [
        {"ai_writing_openai_reasoning_effort": "medium"},
        {"ai_writing_openai_image_detail": "low"},
        {"ai_writing_openai_task1_image_assessment": False},
        {"ai_writing_openai_low_completion_tokens": 9000},
        {"ai_writing_openai_stage_overrides": {"task1.scoring.TA": {"reasoning_effort": "high"}}},
    ],
)
def test_identity_changes_for_every_output_affecting_policy_dimension(changes):
    assert output_identity(settings()) != output_identity(settings(**changes))
    assert "gpt-6-luna" in json.dumps(output_identity(settings()))
    assert "chat/completions" in json.dumps(output_identity(settings()))


def test_usage_filter_retains_reasoning_subset_without_inventing_other_usage():
    from app.providers.writing_llm.base import safe_completion_usage

    assert safe_completion_usage(
        {
            "completion_tokens": 50,
            "completion_tokens_details": {
                "reasoning_tokens": 40,
                "private": "do not retain",
            },
        }
    ) == {"completion_tokens": 50, "reasoning_tokens": 40}
    assert safe_completion_usage({"completion_tokens": 50, "reasoning_tokens": 40}) == {
        "completion_tokens": 50,
        "reasoning_tokens": 40,
    }
    assert safe_completion_usage({"completion_tokens_details": {"reasoning_tokens": -1}}) == {}


def test_criterion_override_inherits_unset_task_stage_fields():
    from app.providers.writing_llm.policy import OpenAIInferencePolicy

    policy = OpenAIInferencePolicy(
        settings(
            ai_writing_openai_image_detail="low",
            ai_writing_openai_stage_overrides={
                "task1.scoring": {
                    "timeout_seconds": 111,
                    "image_detail": "high",
                    "total_completion_tokens": 20000,
                },
                "task1.score.TA": {"reasoning_effort": "high"},
            },
        )
    )
    resolved = policy.resolve(
        CompletionOptions(task="task1", stage="score", criterion="TA"), has_image=True
    )
    assert resolved.timeout_seconds == 111
    assert resolved.image_detail == "high"
    assert resolved.total_completion_tokens == 20000
    assert resolved.reasoning_effort == "high"


def test_unused_openai_budget_does_not_block_vllm_configuration():
    provider = VLLMProvider(
        settings(
            ai_writing_openai_max_output_tokens=4096,
            ai_writing_vllm_base_url="https://fictional.invalid/v1",
        )
    )
    assert provider.model.startswith("mistralai/")


async def test_outer_schema_repair_uses_repair_budget_without_another_length_retry(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return response(finish="length", content="")

    intercept(monkeypatch, handler)
    provider = OpenAIProvider(settings())
    with pytest.raises(ProviderFailure) as failure:
        await provider.complete([], {}, options=CompletionOptions(stage="score", attempt=2))
    assert [body["max_completion_tokens"] for body in bodies] == [32768]
    assert provider.request_attempts == 1
    assert failure.value.reason == "COMPLETION_BUDGET_EXHAUSTED"


async def test_stage_timeout_is_one_budget_across_both_attempts(monkeypatch):
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.04)
        return response(finish="length" if len(calls) == 1 else "stop", content="{}")

    intercept(monkeypatch, handler)
    provider = OpenAIProvider(settings(ai_writing_openai_stage_timeout_seconds=0.06))
    with pytest.raises(ProviderFailure) as failure:
        await provider.complete([], {})
    assert failure.value.code == "AI_PROVIDER_TIMEOUT"
    assert len(calls) == 2
    assert failure.value.usage["total_tokens"] == 30
    assert len(failure.value.attempts) == 2


def test_total_run_timeout_is_explicit_and_in_identity():
    provider = OpenAIProvider(settings(ai_writing_openai_run_timeout_seconds=600))
    assert provider.run_timeout_seconds == 600
    assert provider.reasoned_inference is True
    assert output_identity(settings()) != output_identity(
        settings(ai_writing_openai_run_timeout_seconds=600)
    )


def test_safe_attempt_metadata_revalidates_fields_and_never_keeps_content():
    from app.providers.writing_llm.base import safe_inference_attempts

    raw = {
        "profile": "openai_task1_reasoned_v1",
        "model": "gpt-6-luna",
        "task": "task1",
        "stage": "scoring",
        "criterion": "ta",
        "schema_attempt": 1,
        "attempt": 2,
        "reasoning_effort": "medium",
        "image_detail": "high",
        "completion_budget": 32768,
        "timeout_seconds": 300,
        "finish_reason": "stop",
        "latency_ms": 100,
        "usage": {"completion_tokens": 50, "reasoning_tokens": 30, "secret": "private"},
        "raw_body": "private",
        "reasoning_content": "private",
        "image": "private",
        "failure_code": "AI_PROVIDER_BAD_RESPONSE",
        "failure_reason": "INVALID_JSON",
    }
    safe = safe_inference_attempts((raw, raw, raw))
    assert len(safe) == 2
    assert safe[0]["usage"] == {"completion_tokens": 50, "reasoning_tokens": 30}
    assert "private" not in json.dumps(safe)
    assert safe_inference_attempts([{**raw, "model": "private"}]) == []
    assert safe_inference_attempts([{**raw, "stage": "private"}]) == []
    assert safe_inference_attempts("private") == []
    dirty = safe_inference_attempts(
        [
            {
                **raw,
                "completion_budget": True,
                "latency_ms": -1,
                "failure_reason": "private",
                "failure_code": "private",
            }
        ]
    )[0]
    assert not {"completion_budget", "latency_ms", "failure_reason", "failure_code"} & dirty.keys()


async def test_admission_timeout_before_post_has_no_invented_attempt_or_usage(monkeypatch):
    from app.providers.writing_llm.admission import admission

    provider = OpenAIProvider(
        settings(
            ai_writing_openai_stage_timeout_seconds=0.01,
            ai_writing_openai_max_concurrent_requests=1,
        )
    )
    async with admission(provider.limit, provider.max_queued).slot():
        with pytest.raises(ProviderFailure) as failure:
            await provider.complete([], {})
    assert failure.value.code == "AI_PROVIDER_TIMEOUT"
    assert provider.request_attempts == 0
    assert failure.value.attempts == ()
    assert failure.value.usage == {}


@pytest.mark.parametrize(
    "changes",
    [
        {"ai_writing_openai_image_detail": "original"},
        {"ai_writing_openai_stage_overrides": {"task1.scoring.ta": {"image_detail": "original"}}},
    ],
)
def test_original_detail_fails_safe_until_model_and_chat_support_is_confirmed(changes):
    # Current model-specific vision sizing table omits gpt-6-luna. A generic
    # endpoint enum and another API's Luna support do not prove this pairing.
    with pytest.raises(ProviderFailure) as failure:
        OpenAIProvider(settings(**changes))
    assert failure.value.code == "AI_PROVIDER_CONFIGURATION_ERROR"
