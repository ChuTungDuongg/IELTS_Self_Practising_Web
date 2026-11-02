"""Official OpenAI transport contracts, entirely in-process and fictional."""

import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.providers.speaking_llm import create_provider as speaking_provider
from app.providers.writing_llm import create_provider
from app.providers.writing_llm.base import CompletionOptions, ProviderFailure


def settings(**changes):
    return Settings(
        _env_file=None,
        **{
            "ai_writing_enabled": True,
            "ai_writing_provider": "openai",
            "ai_writing_openai_api_key": "fictional-private-key",
            "speaking_ai_enabled": True,
            "speaking_ai_provider": "openai",
            **changes,
        },
    )


def intercept(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )


def completed():
    return httpx.Response(
        200,
        json={
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ready":true}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        },
    )


@pytest.mark.parametrize("factory", [create_provider, speaking_provider])
async def test_luna_default_model_budget_and_backend_only_auth(monkeypatch, factory):
    def handler(request):
        body = json.loads(request.content)
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fictional-private-key"
        assert body["model"] == "gpt-6-luna"
        assert body["reasoning_effort"] == "none"
        assert body["max_completion_tokens"] == 128
        assert body["response_format"] == {"type": "json_object"}
        assert not {"temperature", "seed", "max_tokens", "extra_body", "tools"} & body.keys()
        return completed()

    intercept(monkeypatch, handler)
    result = await factory(settings(ai_writing_openai_max_output_tokens=128)).complete(
        [{"role": "user", "content": "Return JSON."}], {}, options=CompletionOptions(max_tokens=256)
    )
    assert json.loads(result.text) == {"ready": True}
    assert result.usage["total_tokens"] == 14


def test_missing_credentials_fail_before_any_request():
    with pytest.raises(AppError, match="Chấm AI"):
        create_provider(settings(ai_writing_openai_api_key=""))
    with pytest.raises(AppError) as error:
        speaking_provider(settings(ai_writing_openai_api_key=""))
    assert error.value.code == "SPEAKING_AI_NOT_CONFIGURED"


@pytest.mark.parametrize(
    "failure,code",
    [
        (401, "AI_PROVIDER_AUTH_FAILED"),
        (429, "AI_PROVIDER_RATE_LIMITED"),
        ("quota", "AI_PROVIDER_QUOTA_EXHAUSTED"),
        (503, "AI_MODEL_UNAVAILABLE"),
        (500, "AI_PROVIDER_HTTP_ERROR"),
        ("timeout", "AI_PROVIDER_TIMEOUT"),
    ],
)
async def test_paid_posts_are_never_replayed_and_errors_are_redacted(
    monkeypatch, caplog, failure, code
):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("fictional-private-key private body", request=request)
        return httpx.Response(
            429 if failure == "quota" else failure,
            json={
                "error": {
                    "code": "insufficient_quota" if failure == "quota" else "private-code",
                    "message": "fictional-private-key private body",
                }
            },
        )

    intercept(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as error:
        await create_provider(settings()).complete([], {})
    assert error.value.code == code
    assert len(calls) == 1 and calls[0].method == "POST"
    assert "fictional-private-key" not in str(error.value) + caplog.text
    assert "private body" not in str(error.value) + caplog.text


async def test_writing_and_speaking_share_bounded_admission_and_cancel_releases_slot(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    active = peak = calls = 0

    async def handler(_request):
        nonlocal active, peak, calls
        calls += 1
        active += 1
        peak = max(peak, active)
        started.set()
        try:
            await release.wait()
            return completed()
        finally:
            active -= 1

    intercept(monkeypatch, handler)
    config = settings(
        ai_writing_openai_max_concurrent_requests=1, ai_writing_openai_max_queued_requests=1
    )
    writing, speaking = create_provider(config), speaking_provider(config)
    first = asyncio.create_task(writing.complete([], {}))
    second = None
    try:
        await asyncio.wait_for(started.wait(), 1)
        second = asyncio.create_task(speaking.complete([], {}))
        await asyncio.sleep(0)
        with pytest.raises(ProviderFailure) as error:
            await asyncio.wait_for(writing.complete([], {}), 0.2)
        assert error.value.code == "AI_PROVIDER_BUSY"
        assert calls == peak == 1
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert (await asyncio.wait_for(second, 1)).usage["total_tokens"] == 14
        assert peak == 1
    finally:
        release.set()
        for task in (first, second):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (first, second) if t), return_exceptions=True)


async def test_only_readiness_gets_retry_with_jitter(monkeypatch):
    calls, delays = [], []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
        return httpx.Response(200, json={"data": [{"id": "gpt-6-luna"}]})

    async def sleep(delay):
        delays.append(delay)

    intercept(monkeypatch, handler)
    from app.providers.writing_llm import openai

    monkeypatch.setattr(openai.asyncio, "sleep", sleep)
    await create_provider(settings()).ensure_ready()
    assert len(calls) == 3 and all(r.method == "GET" for r in calls)
    assert len(delays) == 2 and 0 < delays[0] <= delays[1] <= 3


def test_cache_identity_tracks_output_policy_without_secrets():
    from app.providers.speaking_llm import config_identity
    from app.providers.writing_llm.openai import output_identity

    original = settings()
    changed = settings(ai_writing_openai_max_output_tokens=1024)
    assert output_identity(original) != output_identity(changed)
    assert config_identity(original) != config_identity(changed)
    assert output_identity(original) == output_identity(
        settings(ai_writing_openai_api_key="rotated")
    )
    assert "fictional-private-key" not in json.dumps(config_identity(original))

    from uuid import uuid4

    from app.domains.scoring.writing import WritingScoringRequest
    from app.services.writing_ai import input_fingerprint

    request = WritingScoringRequest(
        attempt_id=uuid4(),
        writing_task_id=uuid4(),
        prompt="Fictional parks",
        response="A fictional argument.",
        paragraph_mode="textarea",
    )
    before = input_fingerprint(request, "fictional-v1", "openai", "gpt-6-luna", settings=original)
    assert before != input_fingerprint(
        request, "fictional-v1", "openai", "gpt-6-luna", settings=changed
    )
    assert before == input_fingerprint(
        request,
        "fictional-v1",
        "openai",
        "gpt-6-luna",
        settings=settings(ai_writing_openai_api_key="rotated"),
    )


@pytest.mark.parametrize(
    "message", [{"content": None, "refusal": "private refusal"}, {"content": ""}, {}]
)
async def test_invalid_paid_content_keeps_safe_usage_for_accounting(monkeypatch, message):
    intercept(
        monkeypatch,
        lambda _request: httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": message}],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 7,
                    "total_tokens": 12,
                    "private": "fictional-private-key",
                },
            },
        ),
    )
    with pytest.raises(ProviderFailure) as error:
        await create_provider(settings()).complete([], {})
    assert error.value.usage == {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
    assert error.value.finish_reason == "stop"
    assert "private" not in str(error.value)
