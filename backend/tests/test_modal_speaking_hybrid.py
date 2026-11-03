"""Modal graph selection is offline; CPU native probe is exercised in Docker."""

import builtins
import os

import pytest
from test_modal_app import load_app, stub_runtime


def test_hybrid_image_never_imports_whisper_and_does_not_change_writing_selection(monkeypatch):
    monkeypatch.setenv("IELTS_WEB_SPEAKING_PROFILE", "speaking_hybrid_v1")
    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "deploy.modal.speaking_asr":
            pytest.fail("hybrid speech must not import the legacy GPU ASR")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    module, modal, llm = load_app(monkeypatch, asr_enabled=True)
    assert module.SPEAKING_PROFILE == "speaking_hybrid_v1"
    assert not module.MODAL_ASR_SERVICE_ENABLED
    modal.App.return_value.include.assert_not_called()
    calls = str(modal.Image.from_registry.return_value.run_commands.call_args_list)
    assert "azure-cognitiveservices-speech==1.53.0" in calls
    assert "onnxruntime==1.23.2" in calls
    assert "torch" not in calls and "faster-whisper" not in calls
    assert "gpu" not in modal.App.return_value.cls.call_args.kwargs


def test_unknown_speech_profile_fails_before_remote_resources(monkeypatch):
    monkeypatch.setenv("IELTS_WEB_SPEAKING_PROFILE", "unknown")
    with pytest.raises(ValueError, match="SPEAKING_PROFILE"):
        load_app(monkeypatch)


def test_speaking_policy_is_forwarded_privately_without_changing_frozen_enablement(monkeypatch):
    monkeypatch.setenv("SPEAKING_AI_SCORER_VERSION", "fictional-policy-v2")
    monkeypatch.setenv("SPEAKING_AI_ENABLED", "false")
    monkeypatch.setenv("SPEAKING_AZURE_KEY", "fictional-private-key")
    _, modal, _ = load_app(monkeypatch)
    passed = modal.Secret.from_local_environ.call_args.args[0]
    assert "SPEAKING_AI_SCORER_VERSION" in passed
    assert "SPEAKING_AZURE_KEY" in passed
    assert "SPEAKING_AI_ENABLED" not in passed


@pytest.mark.parametrize("enabled", [True, False])
def test_hybrid_startup_preserves_explicit_speech_enablement_without_provider_calls(
    monkeypatch, enabled
):
    monkeypatch.setenv("IELTS_WEB_SPEAKING_PROFILE", "speaking_hybrid_v1")
    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    monkeypatch.setenv("SPEAKING_PROFILE", "legacy")
    monkeypatch.setenv("SPEAKING_ASR_ENABLED", "false")
    monkeypatch.setenv("SPEAKING_VAD_MODEL_PATH", "")
    monkeypatch.setenv("SPEAKING_VAD_MODEL_SHA256", "")
    monkeypatch.setattr(
        "deploy.modal.speaking_cpu.probe",
        lambda: {"status": "CPU_NATIVE_PROBE_OK", "provider_calls": 0},
    )
    module, modal, llm = load_app(monkeypatch, asr_enabled=enabled)
    stub_runtime(monkeypatch, external=True)
    import sys

    from deploy.modal.web_runtime import configure_speaking_asr_environment

    sys.modules[
        "web_runtime"
    ].configure_speaking_asr_environment = configure_speaking_asr_environment
    module.Web().start()
    assert os.environ["SPEAKING_PROFILE"] == "speaking_hybrid_v1"
    assert os.environ["SPEAKING_ASR_ENABLED"] == str(enabled).lower()
    llm.serve.get_web_url.assert_not_called()


def test_cpu_asset_copy_verifies_checksum_before_adding_model(tmp_path):
    import hashlib
    from unittest.mock import MagicMock

    from deploy.modal.speaking_cpu import include_vad_model

    model = tmp_path / "fictional.onnx"
    model.write_bytes(b"fictional-model")
    image = MagicMock()
    with pytest.raises(ValueError, match="VAD_CHECKSUM_MISMATCH"):
        include_vad_model(image, model, "0" * 64)
    image.add_local_file.assert_not_called()
    expected = hashlib.sha256(b"fictional-model").hexdigest()
    include_vad_model(image, model, expected)
    image.add_local_file.assert_called_once_with(model, "/opt/speaking/silero-v6.0.onnx", copy=True)
