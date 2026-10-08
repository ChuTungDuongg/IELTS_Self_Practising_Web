"""Modal composition/config tests without contacting Modal or starting a GPU."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODEL = "mistralai/Ministral-3-8B-Instruct-2512"


def load_app(
    monkeypatch,
    *,
    local=True,
    enabled=True,
    injected_keys=False,
    chart_enabled=False,
    frozen_chart_flag=None,
):
    modal = MagicMock()
    modal.is_local.return_value = local
    image = MagicMock()
    modal.Image.from_registry.return_value = image
    for method in (
        "entrypoint",
        "env",
        "apt_install",
        "run_commands",
        "add_local_dir",
        "add_local_file",
        "add_local_python_source",
    ):
        getattr(image, method).return_value = image
    app = modal.App.return_value
    app.cls.return_value = lambda cls: cls
    for decorator in ("enter", "exit", "web_server"):
        getattr(modal, decorator).return_value = lambda function: function
    llm = ModuleType("deploy.modal.writing_llm")
    llm.MODEL = MODEL
    llm.app = object()
    llm.serve = MagicMock()
    monkeypatch.setitem(sys.modules, "modal", modal)
    monkeypatch.setitem(sys.modules, "deploy.modal.writing_llm", llm)
    chart = ModuleType("deploy.modal.chart_derenderer")
    chart.MODEL, chart.REVISION, chart.app, chart.serve = (
        "google/deplot",
        "pinned",
        object(),
        MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "deploy.modal.chart_derenderer", chart)
    monkeypatch.setenv("AI_WRITING_CHART_SPECIALIST_ENABLED", str(chart_enabled).lower())
    if frozen_chart_flag is None:
        monkeypatch.delenv("IELTS_WEB_CHART_SPECIALIST_ENABLED", raising=False)
    else:
        monkeypatch.setenv("IELTS_WEB_CHART_SPECIALIST_ENABLED", str(frozen_chart_flag).lower())
    monkeypatch.setenv("IELTS_MODAL_MODE", "dev")
    monkeypatch.setenv("IELTS_WEB_AI_ENABLED", str(enabled).lower())
    if injected_keys:
        monkeypatch.setenv("AI_WRITING_MODAL_KEY", "fictional-key")
        monkeypatch.setenv("AI_WRITING_MODAL_SECRET", "fictional-secret")
    else:
        monkeypatch.delenv("AI_WRITING_MODAL_KEY", raising=False)
        monkeypatch.delenv("AI_WRITING_MODAL_SECRET", raising=False)
    spec = importlib.util.spec_from_file_location(
        "modal_composition_test", ROOT / "deploy/modal/app.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, modal, llm


@pytest.mark.parametrize("local,injected", [(True, False), (True, True), (False, True)])
def test_secret_dependency_count_is_stable_after_remote_injection(monkeypatch, local, injected):
    module, modal, _ = load_app(monkeypatch, local=local, injected_keys=injected)
    # Local and remote imports must agree even when only the container has AI keys.
    assert len(module.web_secrets) == 2
    modal.Secret.from_local_environ.assert_called_once()
    modal.Secret.from_dict.assert_not_called()
    assert modal.App.return_value.cls.call_args.kwargs["secrets"] == module.web_secrets


def test_full_entry_point_includes_the_shared_gpu_function(monkeypatch):
    _, modal, llm = load_app(monkeypatch)
    modal.App.return_value.include.assert_called_once_with(llm.app)
    assert "gpu" not in modal.App.return_value.cls.call_args.kwargs


def test_explicit_web_only_does_not_include_gpu(monkeypatch):
    module, modal, _ = load_app(monkeypatch, enabled=False)
    assert not module.AI_ENABLED
    modal.App.return_value.include.assert_not_called()


def test_chart_service_is_explicitly_optional_and_separate(monkeypatch):
    module, modal, llm = load_app(monkeypatch, chart_enabled=True)
    assert module.CHART_SPECIALIST_ENABLED
    assert [call.args[0] for call in modal.App.return_value.include.call_args_list] == [
        llm.app,
        module.chart_app,
    ]
    module, modal, _ = load_app(monkeypatch, enabled=False, chart_enabled=True)
    assert not module.CHART_SPECIALIST_ENABLED
    modal.App.return_value.include.assert_not_called()


@pytest.mark.parametrize("frozen,secret", [(True, False), (False, True)])
def test_chart_dependency_graph_uses_frozen_flag_over_remote_secret(monkeypatch, frozen, secret):
    module, modal, _ = load_app(
        monkeypatch, local=False, chart_enabled=secret, frozen_chart_flag=frozen
    )
    assert module.CHART_SPECIALIST_ENABLED is frozen
    assert modal.App.return_value.include.call_count == (2 if frozen else 1)
