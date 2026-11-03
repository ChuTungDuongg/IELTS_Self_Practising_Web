"""Request-facing configuration failures are safe before runs or paid calls."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.speaking_llm import config_identity as speaking_identity
from app.providers.speaking_llm import create_provider as speaking_provider
from app.providers.speaking_llm import is_configured as speaking_is_configured
from app.providers.writing_llm import create_provider, is_configured
from app.providers.writing_llm.openai import output_identity
from app.services.writing_ai import input_fingerprint


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


@pytest.mark.parametrize(
    "changes",
    [
        {"ai_writing_openai_max_output_tokens": 4096},
        {"ai_writing_openai_model": "private-unsupported-model"},
        {"ai_writing_openai_image_detail": "original"},
    ],
)
def test_invalid_active_configuration_is_not_advertised_ready(changes):
    config = settings(**changes)
    assert is_configured(config) is False
    assert speaking_is_configured(config) is False


@pytest.mark.parametrize("factory", [create_provider, speaking_provider])
@pytest.mark.parametrize(
    "changes",
    [
        {"ai_writing_openai_max_output_tokens": 4096},
        {"ai_writing_openai_model": "private-unsupported-model"},
    ],
)
def test_invalid_factory_configuration_returns_safe_503_before_network(
    monkeypatch, factory, changes
):
    def unexpected_network(*_args, **_kwargs):
        pytest.fail("Invalid configuration must not create an HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected_network)
    with pytest.raises(AppError) as failure:
        factory(settings(**changes))
    assert failure.value.code == "AI_PROVIDER_CONFIGURATION_ERROR"
    assert failure.value.status_code == 503
    assert "private" not in failure.value.message


@pytest.mark.parametrize(
    "changes",
    [
        {"ai_writing_openai_max_output_tokens": 4096},
        {"ai_writing_openai_model": "private-unsupported-model"},
    ],
)
def test_fingerprint_and_speaking_identity_fail_as_request_errors(changes):
    config = settings(**changes)
    request = WritingScoringRequest(
        attempt_id=uuid4(),
        writing_task_id=uuid4(),
        prompt="Fictional parks.",
        response="A fictional essay.",
        paragraph_mode="textarea",
    )
    with pytest.raises(AppError) as writing_failure:
        input_fingerprint(
            request, "fictional-v1", "openai", config.ai_writing_openai_model, settings=config
        )
    with pytest.raises(AppError) as speaking_failure:
        speaking_identity(config)
    for failure in (writing_failure, speaking_failure):
        assert failure.value.code == "AI_PROVIDER_CONFIGURATION_ERROR"
        assert failure.value.status_code == 503
        assert "private" not in failure.value.message


def test_speaking_model_override_is_checked_at_identity_and_factory_boundary():
    config = settings(speaking_ai_model="private-unsupported-speaking-model")
    assert is_configured(config) is True
    assert speaking_is_configured(config) is False
    for operation in (speaking_identity, speaking_provider):
        with pytest.raises(AppError) as failure:
            operation(config)
        assert failure.value.code == "AI_PROVIDER_CONFIGURATION_ERROR"
        assert failure.value.status_code == 503


@pytest.mark.parametrize(
    "factory,code",
    [
        (create_provider, "AI_NOT_CONFIGURED"),
        (speaking_provider, "SPEAKING_AI_NOT_CONFIGURED"),
    ],
)
def test_missing_credentials_keep_existing_error_contract(factory, code):
    with pytest.raises(AppError) as failure:
        factory(settings(ai_writing_openai_api_key=""))
    assert failure.value.code == code
    assert failure.value.status_code == 503


def test_dormant_openai_configuration_leaves_vllm_identity_and_factory_unchanged():
    before = settings(
        ai_writing_provider="vllm",
        speaking_ai_provider="vllm",
        ai_writing_vllm_base_url="https://fictional.invalid/v1",
    )
    changed = before.model_copy(
        update={
            "ai_writing_openai_max_output_tokens": 4096,
            "ai_writing_openai_model": "private-unsupported-model",
            "ai_writing_openai_image_detail": "original",
        }
    )
    assert is_configured(changed) is True
    assert speaking_is_configured(changed) is True
    assert create_provider(changed).model == before.ai_writing_vllm_model
    assert speaking_identity(changed) == speaking_identity(before)


def test_openai_identity_versions_the_source_image_assessment_prompt():
    assert output_identity(settings())["task1_assessment_contract"] == "source-image-envelope-v1"


async def test_invalid_writing_configuration_never_inserts_or_reuses_a_run(monkeypatch):
    from app.services.writing_ai import WritingAIService

    @asynccontextmanager
    async def transaction():
        yield

    def unexpected_work(*_args, **_kwargs):
        pytest.fail("Configuration failure must precede cache lookups, writes and network")

    session = SimpleNamespace(begin=transaction, add=unexpected_work)
    service = WritingAIService(session, uuid4(), settings(ai_writing_openai_max_output_tokens=4096))
    service.repository = SimpleNamespace(equivalent=unexpected_work, dispatch_lock=unexpected_work)
    request = WritingScoringRequest(
        attempt_id=uuid4(),
        writing_task_id=uuid4(),
        prompt="Fictional parks.",
        response="A fictional essay.",
        paragraph_mode="textarea",
    )

    async def authorized_input(*_args, **_kwargs):
        return request

    monkeypatch.setattr(service, "input", authorized_input)
    monkeypatch.setattr(httpx, "AsyncClient", unexpected_work)
    with pytest.raises(AppError) as failure:
        await service.create(request.attempt_id, request.writing_task_id, force=False)
    assert failure.value.code == "AI_PROVIDER_CONFIGURATION_ERROR"
    assert failure.value.status_code == 503
