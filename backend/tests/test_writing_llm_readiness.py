import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.providers.writing_llm import create_provider, is_configured
from app.providers.writing_llm.base import ProviderFailure
from app.providers.writing_llm.http import api_base_url
from app.providers.writing_llm.vllm import VLLMProvider

MODEL = "mistralai/Ministral-3-8B-Instruct-2512"


def config(**overrides):
    return Settings(
        _env_file=None,
        **{
            "ai_writing_enabled": True,
            "ai_writing_vllm_base_url": "https://private.modal.run/v1",
            "ai_writing_modal_key": "proxy-key",
            "ai_writing_modal_secret": "proxy-secret",
            **overrides,
        },
    )


def mock_http(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def completion():
    return httpx.Response(
        200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"ready":true}'}}]}
    )


@pytest.mark.parametrize(
    "base",
    [
        "https://provider.example",
        "https://provider.example/",
        "https://provider.example/v1",
        "https://provider.example/v1/",
    ],
)
def test_api_url_accepts_origin_or_v1(base):
    assert api_base_url(base) == "https://provider.example/v1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"ai_writing_enabled": False},
        {"ai_writing_provider": "incorrect"},
        {"ai_writing_vllm_base_url": ""},
        {"ai_writing_vllm_base_url": "https://private.modal.run/v1/v1"},
        {"ai_writing_vllm_base_url": "https://key:secret@private.modal.run/v1"},
        {"ai_writing_vllm_base_url": "ftp://private.modal.run"},
        {"ai_writing_vllm_base_url": "http://private.modal.run/v1"},
        {"ai_writing_modal_key": ""},
        {"ai_writing_modal_secret": ""},
        {"ai_writing_vllm_model": ""},
    ],
)
def test_factory_rejects_unserviceable_config(overrides):
    settings = config(**overrides)
    assert not is_configured(settings)
    with pytest.raises(AppError, match="AI_NOT_CONFIGURED"):
        create_provider(settings)


def test_unified_model_and_separate_timeout_defaults():
    provider = create_provider(config())
    assert isinstance(provider, VLLMProvider)
    assert provider.model == MODEL
    assert provider.startup_timeout == 600
    assert provider.transport.timeout == 300


async def test_readiness_checks_exact_served_model_then_text_only_completion(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Modal-Key"] == "proxy-key"
        if request.method == "GET":
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json={"data": [{"id": MODEL}]})
        body = json.loads(request.content)
        assert body["model"] == MODEL
        assert body["messages"] == [{"role": "user", "content": "Return JSON"}]
        return completion()

    mock_http(monkeypatch, handler)
    provider = create_provider(config())
    await provider.ensure_ready()
    await provider.complete([{"role": "user", "content": "Return JSON"}], {})
    assert [request.method for request in requests] == ["GET", "POST"]


async def test_modal_303_polls_original_completion_once_without_resubmitting(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                303, headers={"Location": "/v1/chat/completions?__modal_request_id=opaque"}
            )
        assert request.method == "GET" and request.content == b""
        assert request.headers["Modal-Secret"] == "proxy-secret"
        return completion()

    mock_http(monkeypatch, handler)
    result = await create_provider(config()).complete([], {})
    assert result.text == '{"ready":true}'
    assert [request.method for request in requests] == ["POST", "GET"]


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/v1/chat/completions?poll=1",
        "http://private.modal.run/v1/chat/completions?poll=1",
        "/other-path?poll=1",
        "/v1/chat/completions",
        "https://user:secret@private.modal.run/v1/chat/completions?poll=1",
    ],
)
async def test_poll_redirect_never_leaks_headers_or_changes_path(monkeypatch, location):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(303, headers={"Location": location})

    mock_http(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as failed:
        await create_provider(config()).complete([], {})
    assert failed.value.code == "AI_PROVIDER_ENDPOINT_ERROR"
    assert len(requests) == 1


async def test_modal_redirects_are_bounded(monkeypatch):
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(303, headers={"Location": "/v1/chat/completions?poll=1"})

    mock_http(monkeypatch, handler)
    with pytest.raises(ProviderFailure):
        await create_provider(config()).complete([], {})
    assert methods == ["POST", "GET", "GET", "GET", "GET"]


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "AI_PROVIDER_AUTH_FAILED"),
        (403, "AI_PROVIDER_AUTH_FAILED"),
        (404, "AI_PROVIDER_ENDPOINT_ERROR"),
        (429, "AI_PROVIDER_RATE_LIMITED"),
        (500, "AI_PROVIDER_HTTP_ERROR"),
        (503, "AI_MODEL_UNAVAILABLE"),
        (504, "AI_PROVIDER_TIMEOUT"),
    ],
)
async def test_safe_http_classification(monkeypatch, caplog, status, code):
    mock_http(monkeypatch, lambda request: httpx.Response(status, text="raw secret response"))
    with pytest.raises(ProviderFailure) as error:
        await create_provider(config()).complete([], {})
    assert error.value.code == code
    assert "raw secret" not in str(error.value) + caplog.text
    assert "proxy-secret" not in caplog.text


@pytest.mark.parametrize("message", ["connection refused: raw secret", "DNS failure: raw secret"])
async def test_connection_failure_is_not_timeout_or_auth(monkeypatch, message):
    def handler(request):
        raise httpx.ConnectError(message, request=request)

    mock_http(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as error:
        await create_provider(config()).ensure_ready()
    assert error.value.code == "AI_PROVIDER_UNREACHABLE"
    assert "raw secret" not in str(error.value)


@pytest.mark.parametrize("health", [False, True])
async def test_timeout_distinguishes_startup_from_inference(monkeypatch, health):
    async def handler(request):
        await asyncio.sleep(1)
        return completion()

    mock_http(monkeypatch, handler)
    provider = create_provider(
        config(ai_writing_request_timeout_seconds=0.01, ai_writing_startup_timeout_seconds=0.01)
    )
    with pytest.raises(ProviderFailure) as error:
        if health:
            await provider.ensure_ready()
        else:
            await provider.complete([], {})
    assert error.value.code == ("AI_PROVIDER_STARTUP_TIMEOUT" if health else "AI_PROVIDER_TIMEOUT")


@pytest.mark.parametrize(
    "data,code",
    [
        ({"data": [{"id": "old-model"}]}, "AI_MODEL_UNAVAILABLE"),
        ({"data": None}, "AI_PROVIDER_BAD_RESPONSE"),
        ({}, "AI_PROVIDER_BAD_RESPONSE"),
    ],
)
async def test_readiness_rejects_wrong_model_and_bad_models_response(monkeypatch, data, code):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=data))
    with pytest.raises(ProviderFailure) as error:
        await create_provider(config()).ensure_ready()
    assert error.value.code == code


async def test_model_not_found_response_is_classified_without_exposing_message(monkeypatch):
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            404,
            json={
                "error": {"type": "NotFoundError", "message": "The model raw-secret does not exist"}
            },
        ),
    )
    with pytest.raises(ProviderFailure) as error:
        await create_provider(config()).complete([], {})
    assert error.value.code == "AI_MODEL_UNAVAILABLE"
    assert "raw-secret" not in str(error.value)
