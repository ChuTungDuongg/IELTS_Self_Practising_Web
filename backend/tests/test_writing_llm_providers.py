import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.providers.writing_llm import create_provider, is_configured
from app.providers.writing_llm.base import ProviderFailure


async def test_explicit_provider_task_cancellation_closes_inflight_response_and_propagates(
    monkeypatch, caplog
):
    caplog.set_level("INFO", logger="app.providers.writing_llm.http")
    waiting, release, interrupted, closed = (asyncio.Event() for _ in range(4))

    class WaitingBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"choices":['
            waiting.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                interrupted.set()
                raise

        async def aclose(self):
            closed.set()

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, stream=WaitingBody())
            ),
            **kwargs,
        ),
    )
    provider = create_provider(
        Settings(
            _env_file=None,
            ai_writing_enabled=True,
            ai_writing_vllm_base_url="https://provider.example/v1",
        )
    )
    job = asyncio.create_task(provider.complete([], {}))
    try:
        await asyncio.wait_for(waiting.wait(), 2)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert interrupted.is_set() and closed.is_set()
        assert "AI provider request cancelled: operation=/chat/completions" in caplog.text
        assert "provider.example" not in caplog.text
    finally:
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


async def test_incomplete_http_transfer_is_not_success_even_if_received_json_is_valid(
    monkeypatch, caplog
):
    class IncompleteBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(
                {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
            ).encode()
            raise httpx.RemoteProtocolError("PRIVATE truncated transfer body")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, stream=IncompleteBody())
            ),
            **kwargs,
        ),
    )
    provider = create_provider(
        Settings(
            _env_file=None,
            ai_writing_enabled=True,
            ai_writing_vllm_base_url="https://provider.example/v1",
        )
    )
    with pytest.raises(ProviderFailure) as failure:
        await provider.complete([], {})
    assert failure.value.code == "AI_PROVIDER_UNREACHABLE"
    assert "PRIVATE" not in str(failure.value) + caplog.text


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
    assert result.finish_reason == "stop"


@pytest.mark.parametrize(
    "failure,code",
    [
        ("timeout", "AI_PROVIDER_TIMEOUT"),
        ("http", "AI_PROVIDER_HTTP_ERROR"),
        ("json", "AI_PROVIDER_BAD_RESPONSE"),
        ("truncated", "AI_PROVIDER_BAD_RESPONSE"),
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
    if failure == "json":
        assert error.value.reason == "INVALID_JSON"
    elif failure == "truncated":
        assert error.value.reason == "PROVIDER_FINISH_LENGTH"
        assert error.value.finish_reason == "length"


@pytest.mark.parametrize(
    "data,reason",
    [
        (
            {"choices": [{"finish_reason": "stop", "message": {"content": "  "}}]},
            "EMPTY_MODEL_CONTENT",
        ),
        (
            {
                "choices": [
                    {"finish_reason": "length", "message": {"content": "private incomplete JSON"}}
                ]
            },
            "PROVIDER_FINISH_LENGTH",
        ),
        (
            {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
            "MALFORMED_COMPLETION_ENVELOPE",
        ),
        ({"choices": []}, "MALFORMED_COMPLETION_ENVELOPE"),
        ({"private": "unexpected envelope"}, "MALFORMED_COMPLETION_ENVELOPE"),
        (
            {
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                "usage": ["private"],
            },
            "MALFORMED_COMPLETION_ENVELOPE",
        ),
    ],
)
async def test_transport_classifies_output_without_retaining_raw_text(monkeypatch, data, reason):
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://provider.example/v1",
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)), **kwargs
        ),
    )
    with pytest.raises(ProviderFailure) as failed:
        await create_provider(settings).complete([], {})
    assert failed.value.reason == reason
    assert "private" not in str(failed.value) + str(vars(failed.value))


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


@pytest.mark.parametrize(
    "finish,reason,safe",
    [
        ("length", "PROVIDER_FINISH_LENGTH", "length"),
        ("abort", "PROVIDER_FINISH_ABORT", "abort"),
        ("error", "PROVIDER_FINISH_ERROR", "error"),
        ("content_filter", "PROVIDER_FINISH_OTHER", "content_filter"),
        ("private provider metadata", "PROVIDER_FINISH_OTHER", "other"),
        (None, "PROVIDER_FINISH_OTHER", "missing"),
    ],
)
async def test_finish_semantics_not_interchangeable_even_with_complete_json(
    monkeypatch, finish, reason, safe, caplog
):
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://provider.example/v1",
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"finish_reason": finish, "message": {"content": '{"evidence":[]}'}}
                        ]
                    },
                )
            ),
            **kwargs,
        ),
    )
    with pytest.raises(ProviderFailure) as failed:
        await create_provider(settings).complete([], {})
    assert failed.value.reason == reason and failed.value.finish_reason == safe
    assert "private provider" not in str(vars(failed.value)) + caplog.text


async def test_vllm_evidence_contract_is_guided_and_budget_is_not_globally_increased(monkeypatch):
    from app.schemas.writing_ai import EvidenceSelection

    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://provider.example/v1",
    )

    def handler(request):
        body = json.loads(request.content)
        assert body["temperature"] == 0.0 and body["seed"] == 0
        assert body["max_tokens"] == 1800
        schema = body["response_format"]["json_schema"]["schema"]
        assert body["response_format"]["type"] == "json_schema"
        assert schema["properties"]["evidence"]["maxItems"] == 4
        assert "source_id" in schema["$defs"]["EvidenceChoice"]["required"]
        assert "quote" not in schema["$defs"]["EvidenceChoice"]["properties"]
        source_id = schema["$defs"]["EvidenceChoice"]["properties"]["source_id"]
        assert not {"pattern", "minLength", "maxLength", "format"} & source_id.keys()
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"evidence":[]}'}}]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    backend_schema = EvidenceSelection.model_json_schema(mode="serialization")
    await create_provider(settings).complete([], backend_schema)
    # Provider compatibility never mutates the authoritative backend schema.
    assert "pattern" in backend_schema["$defs"]["EvidenceChoice"]["properties"]["source_id"]


def test_guided_schema_strips_nested_constraints_preserving_properties_and_numeric_bounds():
    from app.providers.writing_llm.vllm import guided_json_schema
    from app.schemas.writing_ai import ScoringOutput

    backend = ScoringOutput.model_json_schema(mode="serialization")
    guided = guided_json_schema(backend)
    assert guided["properties"]["score"] == backend["properties"]["score"]
    assert guided["properties"]["strengths"]["maxItems"] == 3
    assert "maxLength" not in guided["properties"]["strengths"]["items"]
    assert backend["properties"]["strengths"]["items"]["maxLength"] == 240
    # Keyword removal applies to schema nodes, never to names in property maps.
    named = {
        "type": "object",
        "properties": {
            "format": {"anyOf": [{"type": "string", "format": "date-time"}]},
            "pattern": {"type": "array", "items": {"type": "string", "pattern": "x"}},
        },
    }
    simplified = guided_json_schema(named)
    assert set(simplified["properties"]) == {"format", "pattern"}
    assert simplified["properties"]["format"]["anyOf"] == [{"type": "string"}]
    assert simplified["properties"]["pattern"]["items"] == {"type": "string"}


async def test_vllm_request_keeps_max_items_while_verbose_output_is_normalized_locally(monkeypatch):
    from app.domains.scoring.ai_writing_normalization import normalize_scoring_output
    from app.schemas.writing_ai import RawScoringOutput, ScoringOutput

    calls = []
    output = {
        "score": 6.5,
        "feedback": "Từ vựng nhìn chung phù hợp nhưng cần chính xác hơn. " * 25,
        "strengths": ["Diễn đạt rõ ý."] * 4,
        "improvements": ["Rà soát dạng từ."],
    }

    def handler(request):
        calls.append(request)
        schema = json.loads(request.content)["response_format"]["json_schema"]["schema"]
        assert set(schema["required"]) == {"score", "feedback", "strengths", "improvements"}
        assert schema["properties"]["strengths"]["maxItems"] == 3
        assert schema["properties"]["improvements"]["maxItems"] == 3
        assert "maxLength" not in schema["properties"]["feedback"]
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://provider.example/v1",
    )
    completion = await create_provider(settings).complete(
        [], ScoringOutput.model_json_schema(mode="serialization")
    )
    normalized, issues = normalize_scoring_output(
        RawScoringOutput.model_validate_json(completion.text)
    )
    assert normalized.score == 6.5 and len(normalized.feedback) <= 800
    assert len(normalized.strengths) == 3 and issues and len(calls) == 1
