"""Provider graph regressions without importing real Modal resource definitions."""

import builtins

import pytest
from test_modal_app import load_app, stub_runtime


@pytest.fixture(autouse=True)
def clean_provider_selection(monkeypatch):
    for name in (
        "IELTS_WEB_AI_PROVIDER",
        "IELTS_WEB_SPEAKING_AI_PROVIDER",
        "AI_WRITING_PROVIDER",
        "SPEAKING_AI_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)


def test_openai_only_graph_never_imports_llm_or_other_disabled_gpu_services(monkeypatch):
    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {
            "deploy.modal.writing_llm",
            "deploy.modal.speaking_asr",
            "deploy.modal.chart_derenderer",
        }:
            pytest.fail(f"Unexpected GPU service import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    module, modal, llm = load_app(monkeypatch, asr_enabled=False)
    stub_runtime(monkeypatch, external=True)
    module.Web().start()
    modal.App.return_value.include.assert_not_called()
    llm.serve.get_web_url.assert_not_called()
    assert "gpu" not in modal.App.return_value.cls.call_args.kwargs


@pytest.mark.parametrize("writing,speaking", [("openai", "vllm"), ("vllm", "openai")])
def test_mixed_provider_graph_keeps_the_selected_vllm_transport(monkeypatch, writing, speaking):
    monkeypatch.setenv("AI_WRITING_PROVIDER", writing)
    monkeypatch.setenv("SPEAKING_AI_PROVIDER", speaking)
    module, modal, llm = load_app(monkeypatch, asr_enabled=False)
    stub_runtime(monkeypatch, external=True)
    module.Web().start()
    modal.App.return_value.include.assert_called_once_with(llm.app)
    llm.serve.get_web_url.assert_called_once()


def test_remote_graph_uses_frozen_providers_and_asr_selection(monkeypatch):
    monkeypatch.setenv("IELTS_WEB_AI_PROVIDER", "openai")
    monkeypatch.setenv("IELTS_WEB_SPEAKING_AI_PROVIDER", "")
    monkeypatch.setenv("AI_WRITING_PROVIDER", "vllm")
    monkeypatch.setenv("SPEAKING_AI_PROVIDER", "vllm")
    module, modal, llm = load_app(monkeypatch, local=False, asr_enabled=False)
    modal.App.return_value.include.assert_not_called()
    image_env = modal.Image.from_registry.return_value.env.call_args_list[-1].args[0]
    assert image_env["IELTS_WEB_AI_PROVIDER"] == "openai"
    assert image_env["IELTS_WEB_SPEAKING_AI_PROVIDER"] == ""
    assert image_env["IELTS_WEB_SPEAKING_ASR_ENABLED"] == "false"
    stub_runtime(monkeypatch, external=True)
    module.Web().start()
    llm.serve.get_web_url.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False])
def test_openai_and_disabled_ai_can_keep_asr_without_llm(monkeypatch, enabled):
    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    module, modal, llm = load_app(monkeypatch, enabled=enabled, asr_enabled=True)
    modal.App.return_value.include.assert_called_once_with(module.asr_app)
    assert module.ASR_ENABLED
    stub_runtime(monkeypatch, external=True)
    module.Web().start()
    module.asr_serve.get_web_url.assert_called_once()
    llm.serve.get_web_url.assert_not_called()


@pytest.mark.parametrize("provider", ["", "unknown", "https://private.invalid"])
def test_invalid_deployment_provider_is_rejected(monkeypatch, provider):
    monkeypatch.setenv("AI_WRITING_PROVIDER", provider)
    with pytest.raises(ValueError, match="AI.*PROVIDER"):
        load_app(monkeypatch, asr_enabled=False)
