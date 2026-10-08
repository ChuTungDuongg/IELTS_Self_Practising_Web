import json

import httpx
import pytest

from app.core.config import Settings
from app.providers.writing_llm import create_provider, is_configured
from app.providers.writing_llm.base import ProviderFailure


@pytest.mark.parametrize("provider", ["vllm", "openai"])
async def test_transports_use_backend_headers_and_discard_reasoning(monkeypatch, provider):
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_provider=provider,
        ai_writing_vllm_base_url="https://private.modal.run/v1",
        ai_writing_modal_key="proxy-key",
        ai_writing_modal_secret="proxy-secret",
        ai_writing_vllm_api_key="vllm-key",
        ai_writing_openai_api_key="openai-key",
    )

    def handler(request):
        body = json.loads(request.content)
        assert str(request.url).endswith("/v1/chat/completions")
        assert body["stream"] is False
        if provider == "vllm":
            assert request.headers["Modal-Key"] == "proxy-key"
            assert request.headers["Modal-Secret"] == "proxy-secret"
            assert body["temperature"] == 0 and body["seed"] == 0
        else:
            assert request.headers["Authorization"] == "Bearer openai-key"
            assert "temperature" not in body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"evidence":[]}',
                            "reasoning_content": "private reasoning",
                        },
                    }
                ],
                "usage": {"total_tokens": 25, "secret": "secret"},
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = await create_provider(settings).complete(
        [{"role": "user", "content": "JSON evidence"}], {"type": "object"}
    )
    assert result.text == '{"evidence":[]}' and result.usage == {"total_tokens": 25}


@pytest.mark.parametrize(
    "failure,code",
    [
        ("timeout", "PROVIDER_TIMEOUT"),
        ("http", "PROVIDER_HTTP_ERROR"),
        ("json", "INVALID_PROVIDER_OUTPUT"),
        ("truncated", "INVALID_PROVIDER_OUTPUT"),
    ],
)
async def test_transport_safe_failures(monkeypatch, failure, code):
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://provider.example/v1",
    )

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("raw secret", request=request)
        if failure == "http":
            return httpx.Response(500, text="raw secret")
        if failure == "json":
            return httpx.Response(200, text="raw secret")
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "length", "message": {"content": "raw secret"}}]},
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(ProviderFailure) as error:
        await create_provider(settings).complete([], {})
    assert error.value.code == code and "raw secret" not in str(error.value)


def test_modal_proxy_pair_required_and_secrets_not_in_repr():
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://private.modal.run/v1",
        ai_writing_vllm_api_key="secret-bearer",
    )
    assert not is_configured(settings)
    settings.ai_writing_modal_key = "secret-key"
    settings.ai_writing_modal_secret = "secret-value"
    assert is_configured(settings) and "secret-value" not in repr(settings)
