"""Validate deployment wiring with a fake Modal SDK, without GPU allocation."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def config_type():
    sys.path.insert(0, str(ROOT))
    from deploy.modal.writing_llm_config import WritingServingConfig

    return WritingServingConfig


@pytest.mark.parametrize("sequences", [1, 2, 4])
@pytest.mark.parametrize("profile,scaledown", [("cost", 60), ("interactive", 300)])
def test_config_and_host_remote_environment_agree(sequences, profile, scaledown):
    config = config_type().from_env(
        {"IELTS_WRITING_LLM_MAX_NUM_SEQS": str(sequences), "IELTS_WRITING_LLM_PROFILE": profile}
    )
    assert config.max_num_seqs == sequences and config.scaledown_seconds == scaledown
    assert config_type().from_env(config.image_env()) == config
    command = config.command()
    assert command[command.index("--max-num-seqs") + 1] == str(sequences)
    assert command[command.index("--max-model-len") + 1] == "8192"
    assert command[command.index("--gpu-memory-utilization") + 1] == "0.90"
    assert "--enforce-eager" in command
    assert "--disable-log-requests" in command and "--disable-uvicorn-access-log" in command
    assert command[2] == "mistralai/Ministral-3-8B-Instruct-2512"


@pytest.mark.parametrize(
    "env",
    [
        {"IELTS_WRITING_LLM_MAX_NUM_SEQS": "3"},
        {"IELTS_WRITING_LLM_MAX_NUM_SEQS": "0"},
        {"IELTS_WRITING_LLM_PROFILE": "always-on"},
        {"IELTS_WRITING_LLM_SCALEDOWN_SECONDS": "1"},
        {"IELTS_WRITING_LLM_SCALEDOWN_SECONDS": "901"},
    ],
)
def test_invalid_settings_fail_before_deploy(env):
    with pytest.raises(ValueError):
        config_type().from_env(env)


def test_default_is_conservative_and_idle_window_can_be_overridden():
    assert config_type().from_env({}).max_num_seqs == 2
    assert (
        config_type().from_env({"IELTS_WRITING_LLM_SCALEDOWN_SECONDS": "180"}).scaledown_seconds
        == 180
    )


def test_modal_admission_matches_vllm_without_extra_gpu_replicas(monkeypatch):
    config_type()
    modal = MagicMock()
    image = MagicMock()
    modal.Image.from_registry.return_value = image
    for method in ("entrypoint", "env", "add_local_python_source"):
        getattr(image, method).return_value = image
    modal.App.return_value.function.return_value = lambda function: function
    for decorator in ("web_server", "concurrent"):
        getattr(modal, decorator).return_value = lambda function: function
    monkeypatch.setitem(sys.modules, "modal", modal)
    monkeypatch.setenv("IELTS_WRITING_LLM_MAX_NUM_SEQS", "4")
    monkeypatch.setenv("IELTS_WRITING_LLM_PROFILE", "interactive")
    monkeypatch.delenv("IELTS_WRITING_LLM_SCALEDOWN_SECONDS", raising=False)
    spec = importlib.util.spec_from_file_location(
        "latency_serving_test", ROOT / "deploy/modal/writing_llm.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kwargs = modal.App.return_value.function.call_args.kwargs
    assert kwargs["gpu"] == "L4" and kwargs["min_containers"] == 0 and kwargs["max_containers"] == 1
    assert kwargs["scaledown_window"] == 300 and kwargs["memory"] == 32768 and kwargs["cpu"] == 4
    modal.concurrent.assert_called_once_with(max_inputs=4)
    modal.web_server.assert_called_once_with(8000, startup_timeout=600, requires_proxy_auth=True)
    popen = MagicMock()
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    module.serve()
    popen.assert_called_once_with(module.config.command())
