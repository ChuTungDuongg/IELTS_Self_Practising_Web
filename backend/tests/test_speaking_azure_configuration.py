"""Azure selection composes CPU Web only; no live provider/Modal requests."""

import builtins
from unittest.mock import MagicMock

import pytest
from test_modal_app import load_app, stub_runtime

from app.core.config import Settings
from app.core.exceptions import AppError
from app.providers.speaking_asr import create_provider, provider_identity


def azure_settings(**overrides):
    return Settings(
        _env_file=None,
        **{
            "speaking_asr_enabled": True,
            "speaking_asr_provider": "azure",
            "speaking_azure_key": "fictional-azure-private-key",
            "speaking_azure_region": "japaneast",
            "speaking_azure_billing_mode": "free_only",
            **overrides,
        },
    )


@pytest.mark.parametrize("missing", ["speaking_azure_key", "speaking_azure_region"])
def test_azure_configuration_is_validated_only_when_asr_is_needed(missing):
    settings = azure_settings(**{missing: ""})
    with pytest.raises(AppError) as caught:
        create_provider(settings)
    assert caught.value.code == "SPEAKING_ASR_UNAVAILABLE"
    assert "fictional-azure-private-key" not in repr(settings)


def test_explicit_azure_selects_versioned_profile_and_a_safe_identity():
    settings = azure_settings()
    assert settings.speaking_profile == "speaking_hybrid_v1"
    provider = create_provider(settings)
    identity = provider_identity(settings)
    assert identity["provider"] == "azure"
    assert identity["region"] == "japaneast" and identity["locale"] == "en-US"
    assert provider.identity == identity
    assert "fictional-azure-private-key" not in str(identity)
    assert "fictional-azure-private-key" not in repr(settings)


@pytest.mark.parametrize("provider", ["local", "modal"])
def test_other_providers_never_require_an_azure_key(provider):
    settings = Settings(_env_file=None, speaking_asr_provider=provider, speaking_azure_key=None)
    assert settings.speaking_profile == "legacy"
    assert provider_identity(settings)["provider"] in {"faster-whisper", "modal"}


@pytest.mark.parametrize("enabled", [True, False])
def test_azure_composition_and_startup_never_imports_whisper_or_includes_any_gpu(
    monkeypatch, enabled
):
    import os
    import sys

    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    monkeypatch.setenv("SPEAKING_AI_PROVIDER", "openai")
    monkeypatch.setenv("SPEAKING_ASR_PROVIDER", "azure")
    monkeypatch.setenv("SPEAKING_ASR_ENABLED", str(enabled).lower())
    monkeypatch.setenv("SPEAKING_AZURE_KEY", "fictional-azure-private-key")
    monkeypatch.setenv("SPEAKING_PROFILE", "legacy")
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"deploy.modal.speaking_asr", "deploy.modal.writing_llm"}:
            pytest.fail("Azure/OpenAI must not import a GPU service")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr("deploy.modal.speaking_cpu.probe", lambda: {})
    module, modal, llm = load_app(monkeypatch, asr_enabled=enabled, asr_provider="azure")
    assert module.SPEECH_ENABLED is enabled
    assert module.ASR_PROVIDER == "azure"
    assert module.MODAL_ASR_SERVICE_ENABLED is False
    modal.App.return_value.include.assert_not_called()
    assert "gpu" not in modal.App.return_value.cls.call_args.kwargs
    assert not any("whisper" in str(call) for call in modal.Volume.from_name.call_args_list)
    images = str(modal.Image.from_registry.return_value.env.call_args_list)
    assert "fictional-azure-private-key" not in images
    stub_runtime(monkeypatch, external=True)
    from deploy.modal.web_runtime import configure_speaking_asr_environment

    sys.modules[
        "web_runtime"
    ].configure_speaking_asr_environment = configure_speaking_asr_environment
    module.Web().start()
    assert os.environ["SPEAKING_ASR_PROVIDER"] == "azure"
    assert os.environ["SPEAKING_ASR_ENABLED"] == str(enabled).lower()
    llm.serve.get_web_url.assert_not_called()


def test_explicit_modal_provider_preserves_legacy_gpu_composition(monkeypatch):
    monkeypatch.setenv("SPEAKING_ASR_PROVIDER", "modal")
    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    module, modal, _ = load_app(monkeypatch, asr_enabled=True, asr_provider="modal")
    assert module.MODAL_ASR_SERVICE_ENABLED is True
    assert modal.App.return_value.include.call_count == 1


def test_local_provider_fails_clearly_in_modal_without_gpu_fallback(monkeypatch):
    monkeypatch.setenv("SPEAKING_ASR_PROVIDER", "local")
    with pytest.raises(ValueError, match="local ASR"):
        load_app(monkeypatch, asr_enabled=True, asr_provider="local")


def test_disabled_azure_factory_never_constructs_a_client(monkeypatch):
    constructor = MagicMock(side_effect=AssertionError("Azure client must not be created"))
    monkeypatch.setattr(
        "app.services.speaking_hybrid.AzureSpeechAnalyzer", constructor, raising=False
    )
    with pytest.raises(AppError):
        create_provider(azure_settings(speaking_asr_enabled=False))
    constructor.assert_not_called()


def test_profile_readiness_uses_no_client_and_discloses_no_secret(monkeypatch):
    from app.services import speaking_profile

    monkeypatch.setattr(speaking_profile, "version", lambda _: "offline-sdk-version")
    status = speaking_profile.hybrid_profile_status(azure_settings())
    assert status["configured"] and status["provider"] == "azure"
    assert status["billing_authorized"]
    assert "fictional-azure-private-key" not in str(status)
    assert not {"key", "key_length", "key_prefix", "endpoint"} & status.keys()
    blocked = speaking_profile.hybrid_profile_status(
        azure_settings(speaking_azure_billing_mode="unknown")
    )
    assert blocked["configured"] is False
