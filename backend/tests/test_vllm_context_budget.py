"""A larger output cap must preserve long inputs that fit the existing context."""

import json

import httpx
import pytest
from test_writing_completion_budgets import CORE, EVIDENCE, assess

from app.core.config import Settings
from app.providers.writing_llm import create_provider
from app.providers.writing_llm.base import CompletionOptions, ProviderFailure


def rejection(requested=3072, context=8192, input_tokens=6000):
    # Exact vLLM 0.13 pre-inference validation error, not a token estimate.
    return {
        "error": {
            "message": (
                "'max_tokens' or 'max_completion_tokens' is too large: "
                f"{requested}. This model's maximum context length is {context} tokens "
                f"and your request has {input_tokens} input tokens "
                f"({requested} > {context} - {input_tokens})."
            ),
            "type": "BadRequestError",
            "param": None,
            "code": 400,
        }
    }


def success(output=CORE, finish="stop"):
    return httpx.Response(
        200,
        json={"choices": [{"finish_reason": finish, "message": {"content": json.dumps(output)}}]},
    )


def install(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    return create_provider(
        Settings(
            _env_file=None,
            ai_writing_enabled=True,
            ai_writing_vllm_base_url="https://provider.example/v1",
        )
    )


async def test_long_input_accepted_after_one_pre_inference_context_resubmit(monkeypatch, caplog):
    bodies, inferences = [], []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(400, json=rejection())
        inferences.append(body)
        return success()

    provider = install(monkeypatch, handler)
    completion = await provider.complete(
        [{"role": "user", "content": "PRIVATE long Task 1 input"}],
        {"type": "object"},
        options=CompletionOptions(max_tokens=3072),
    )
    assert json.loads(completion.text) == CORE
    assert len(bodies) == 2 and len(inferences) == 1
    assert [body["max_tokens"] for body in bodies] == [3072, 2192]
    assert bodies[1] == {**bodies[0], "max_tokens": 2192}
    assert "PRIVATE" not in caplog.text and "6000" not in caplog.text


async def test_context_resubmit_never_retries_length_or_accepts_its_json(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return (
            httpx.Response(400, json=rejection()) if len(bodies) == 1 else success(finish="length")
        )

    provider = install(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as failed:
        await provider.complete([], {}, options=CompletionOptions(max_tokens=3072))
    assert failed.value.reason == "PROVIDER_FINISH_LENGTH" and len(bodies) == 2


async def test_repeated_context_rejection_fails_after_one_resubmit(monkeypatch, caplog):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(
            400, json=rejection(body["max_tokens"], input_tokens=6000 + 100 * (len(bodies) - 1))
        )

    provider = install(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as failed:
        await provider.complete([], {}, options=CompletionOptions(max_tokens=3072))
    assert failed.value.code == "AI_PROVIDER_ENDPOINT_ERROR"
    assert [body["max_tokens"] for body in bodies] == [3072, 2192]
    assert "input tokens" not in caplog.text + str(vars(failed.value))


@pytest.mark.parametrize(
    "change",
    [
        {"message": "PRIVATE unrelated bad request"},
        {"message": rejection()["error"]["message"] + " PRIVATE suffix"},
        {"message": rejection(4096)["error"]["message"]},
        {"message": rejection(input_tokens=8192)["error"]["message"]},
        {"message": rejection(context=10_000_001)["error"]["message"]},
        {"message": rejection()["error"]["message"].replace("(3072 >", "(4096 >")},
        {"type": "UnexpectedError"},
        {"code": 404},
        {"param": "unrelated"},
    ],
)
async def test_unverified_context_errors_are_not_resubmitted_or_exposed(
    monkeypatch, caplog, change
):
    bodies = []
    error = rejection()
    error["error"].update(change)

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(400, json=error)

    provider = install(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as failed:
        await provider.complete([], {}, options=CompletionOptions(max_tokens=3072))
    assert failed.value.code == "AI_PROVIDER_ENDPOINT_ERROR" and len(bodies) == 1
    assert "PRIVATE" not in caplog.text + str(vars(failed.value))


async def test_default_visual_budget_retains_existing_behavior(monkeypatch):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(400, json=rejection(1800, input_tokens=6500))

    provider = install(monkeypatch, handler)
    with pytest.raises(ProviderFailure):
        await provider.complete([], {})
    assert len(bodies) == 1 and bodies[0]["max_tokens"] == 1800


async def test_mts_length_repair_still_has_only_two_inferences_when_context_is_tight(monkeypatch):
    scoring_requests, scoring_inferences, bodies = 0, 0, []

    def handler(request):
        nonlocal scoring_requests, scoring_inferences
        body = json.loads(request.content)
        bodies.append(body)
        schema = body["response_format"]["json_schema"]["schema"]
        if "evidence" in schema["properties"]:
            return success(EVIDENCE)
        scoring_requests += 1
        if scoring_requests <= 4:
            input_tokens = 6000 if scoring_requests <= 2 else 6050
            if body["max_tokens"] + input_tokens > 8192:
                return httpx.Response(
                    400, json=rejection(body["max_tokens"], input_tokens=input_tokens)
                )
        scoring_inferences += 1
        return success(finish="length" if scoring_inferences == 1 else "stop")

    result, service, events = await assess(install(monkeypatch, handler))
    assert result is not None
    assert result.criteria.ta.score == 6.5
    assert scoring_inferences == 5  # Two TA inferences, one for each remaining trait.
    assert len(bodies) == 11  # Nine logical completions plus two validation-only 400s.
    assert [body["max_tokens"] for body in bodies[:5]] == [1800, 3072, 2192, 4096, 2142]
    assert (
        len(service.diagnostics) == 1 and service.diagnostics[0].reason == "PROVIDER_FINISH_LENGTH"
    )
    assert sum(event == "criterion.retrying" for event, _ in events) == 1
