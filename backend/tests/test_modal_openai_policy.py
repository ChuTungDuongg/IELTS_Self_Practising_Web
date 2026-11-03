"""OpenAI policy reaches the CPU backend without becoming image/frontend state."""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from deploy.modal import web_runtime
from test_modal_app import load_app

from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment():
    # Runtime hydration writes os.environ directly, outside monkeypatch bookkeeping.
    with patch.dict(os.environ):
        yield


def test_safe_configuration_preserves_policy_counters_and_rejects_private_fields(monkeypatch):
    summary = {
        "writing_provider": "openai",
        "writing_openai_profile": "openai_task1_reasoned_v1",
        "writing_openai_reasoning_effort": "low",
        "writing_openai_image_detail": "high",
        "writing_openai_low_completion_tokens": 8192,
        "writing_openai_medium_completion_tokens": 16384,
        "writing_openai_repair_completion_tokens": 32768,
        "writing_openai_max_output_tokens": 32768,
        "writing_openai_task1_image_assessment": True,
        "writing_openai_stage_timeout_seconds": 233.0,
        "writing_openai_run_timeout_seconds": 1440.0,
    }
    monkeypatch.setattr(
        web_runtime.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    **summary,
                    "writing_openai_api_key": "private-key",
                    "writing_openai_base_url": "https://private-gateway.invalid",
                    "reasoning": "private-internal-content",
                }
            ),
        ),
    )
    assert web_runtime.safe_ai_configuration() == summary


@pytest.mark.parametrize("local", [True, False])
def test_policy_shell_overrides_survive_modal_secret_transfer_and_cpu_hydration(monkeypatch, local):
    policy_environment = {
        "AI_WRITING_PROVIDER": "openai",
        "AI_WRITING_OPENAI_API_KEY": "private-test-key",
        "AI_WRITING_OPENAI_MODEL": "gpt-6-luna",
        "AI_WRITING_OPENAI_PROFILE": "openai_task1_reasoned_v1",
        "AI_WRITING_OPENAI_REASONING_EFFORT": "low",
        "AI_WRITING_OPENAI_IMAGE_DETAIL": "high",
        "AI_WRITING_OPENAI_LOW_COMPLETION_TOKENS": "8192",
        "AI_WRITING_OPENAI_MEDIUM_COMPLETION_TOKENS": "16384",
        "AI_WRITING_OPENAI_REPAIR_COMPLETION_TOKENS": "32768",
        "AI_WRITING_OPENAI_MAX_OUTPUT_TOKENS": "32768",
        "AI_WRITING_OPENAI_TASK1_IMAGE_ASSESSMENT": "true",
        "AI_WRITING_OPENAI_STAGE_TIMEOUT_SECONDS": "233",
        "AI_WRITING_OPENAI_RUN_TIMEOUT_SECONDS": "1440",
        "AI_WRITING_OPENAI_STAGE_OVERRIDES": json.dumps(
            {"task1.visual_grounding": {"reasoning_effort": "high"}}
        ),
        "SPEAKING_AI_PROVIDER": "",
    }
    for key, value in policy_environment.items():
        monkeypatch.setenv(key, value)
    for key in ("IELTS_WEB_AI_PROVIDER", "IELTS_WEB_SPEAKING_AI_PROVIDER"):
        monkeypatch.delenv(key, raising=False)

    _, modal, _ = load_app(monkeypatch, local=local, asr_enabled=False)
    secret_keys = modal.Secret.from_local_environ.call_args.args[0]
    # Exercise the actual allowlist selection as a backend-only transfer boundary.
    transferred = {key: os.environ[key] for key in secret_keys}
    with patch.dict(os.environ, transferred, clear=True):
        web_runtime.configure_ai_environment(
            True, "", None, provider="openai", speaking_provider=""
        )
        settings = Settings(_env_file=None)
        actual = settings.model_dump(mode="json")
        assert settings.ai_writing_enabled and settings.speaking_ai_enabled
        assert actual["ai_writing_provider"] == "openai"
        assert actual["ai_writing_openai_profile"] == "openai_task1_reasoned_v1"
        assert actual["ai_writing_openai_reasoning_effort"] == "low"
        assert actual["ai_writing_openai_image_detail"] == "high"
        assert actual["ai_writing_openai_low_completion_tokens"] == 8192
        assert actual["ai_writing_openai_medium_completion_tokens"] == 16384
        assert actual["ai_writing_openai_repair_completion_tokens"] == 32768
        assert actual["ai_writing_openai_max_output_tokens"] == 32768
        assert actual["ai_writing_openai_task1_image_assessment"] is True
        assert actual["ai_writing_openai_stage_timeout_seconds"] == 233
        assert actual["ai_writing_openai_run_timeout_seconds"] == 1440
        assert (
            actual["ai_writing_openai_stage_overrides"]["task1.visual_grounding"][
                "reasoning_effort"
            ]
            == "high"
        )
        assert not settings.ai_writing_vllm_base_url
        assert not settings.ai_writing_chart_specialist_enabled
    image_env = [call.args[0] for call in modal.Image.from_registry.return_value.env.call_args_list]
    assert all(
        not any(key.startswith("AI_WRITING_OPENAI_") for key in values) for values in image_env
    )
    assert "gpu" not in modal.App.return_value.cls.call_args.kwargs


def test_runtime_policy_probe_uses_effective_backend_settings_without_secrets(monkeypatch):
    monkeypatch.setenv("AI_WRITING_PROVIDER", "openai")
    monkeypatch.setenv("AI_WRITING_OPENAI_API_KEY", "private-test-key")
    monkeypatch.setenv("AI_WRITING_OPENAI_STAGE_TIMEOUT_SECONDS", "233")
    monkeypatch.setenv("AI_WRITING_OPENAI_RUN_TIMEOUT_SECONDS", "1440")
    monkeypatch.delenv("SPEAKING_AI_MODEL", raising=False)
    monkeypatch.delenv("SPEAKING_AI_PROVIDER", raising=False)
    web_runtime.configure_ai_environment(True, "", None, provider="openai", speaking_provider="")
    summary = web_runtime.safe_ai_configuration()
    assert summary["writing_provider"] == summary["speaking_provider"] == "openai"
    assert summary["writing_openai_profile"] == "openai_task1_reasoned_v1"
    assert summary["writing_openai_reasoning_effort"] == "low"
    assert summary["writing_openai_image_detail"] == "high"
    assert summary["writing_openai_max_output_tokens"] == 32768
    assert summary["writing_openai_task1_image_assessment"] is True
    assert summary["writing_openai_stage_timeout_seconds"] == 233
    assert summary["writing_openai_run_timeout_seconds"] == 1440
    assert "private-test-key" not in json.dumps(summary)
