"""Modal composition/config tests without contacting Modal or starting a GPU."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODEL = "mistralai/Ministral-3-8B-Instruct-2512"


@pytest.fixture(autouse=True)
def clean_topology_environment(monkeypatch):
    for key in (
        "IELTS_MODAL_STORAGE_BACKEND",
        "STORAGE_BACKEND",
        "IELTS_MODAL_DATABASE_MODE",
        "IELTS_MODAL_CONFIG_SECRET",
        "IELTS_MODAL_REQUIRE_ASSET_ISOLATION",
        "IELTS_MODAL_DEV_ASSETS_VOLUME",
        "IELTS_MODAL_PRODUCTION_ASSETS_VOLUME",
        "IELTS_MODAL_DATABASE_VOLUME",
        "IELTS_MODAL_DEV_DATABASE_VOLUME",
        "IELTS_MODAL_SNAPSHOTS_VOLUME",
    ):
        monkeypatch.delenv(key, raising=False)


def load_app(
    monkeypatch,
    *,
    local=True,
    enabled=True,
    injected_keys=False,
    chart_enabled=False,
    frozen_chart_flag=None,
    asr_enabled=None,
):
    modal = MagicMock()
    modal.Volume.from_name.side_effect = lambda *args, **kwargs: MagicMock()
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
    app.function.return_value = lambda function: function
    modal.concurrent.return_value = lambda cls: cls
    for decorator in ("enter", "exit", "web_server"):
        getattr(modal, decorator).return_value = lambda function: function
    llm = ModuleType("deploy.modal.writing_llm")
    llm.MODEL = MODEL
    llm.app = object()
    llm.serve = MagicMock()
    monkeypatch.setitem(sys.modules, "modal", modal)
    monkeypatch.setitem(sys.modules, "deploy.modal.writing_llm", llm)
    asr = ModuleType("deploy.modal.speaking_asr")
    asr.MODEL = "Systran/faster-whisper-large-v3"
    asr.REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"
    asr.SERVICE_VERSION = "pinned-asr"
    asr.app = object()
    asr.serve_asr = MagicMock()
    monkeypatch.setitem(sys.modules, "deploy.modal.speaking_asr", asr)
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
    if asr_enabled is None:
        monkeypatch.delenv("IELTS_WEB_SPEAKING_ASR_ENABLED", raising=False)
    else:
        monkeypatch.setenv("IELTS_WEB_SPEAKING_ASR_ENABLED", str(asr_enabled).lower())
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


def test_speaking_overrides_are_ephemeral_backend_only(monkeypatch):
    monkeypatch.setenv("SPEAKING_AI_PROVIDER", "openai")
    monkeypatch.setenv("SPEAKING_AI_MODEL", "independent-model")
    monkeypatch.setenv("SPEAKING_AI_ENABLED", "false")
    _, modal, _ = load_app(monkeypatch)
    passed = modal.Secret.from_local_environ.call_args.args[0]
    assert "SPEAKING_AI_PROVIDER" in passed and "SPEAKING_AI_MODEL" in passed
    assert "SPEAKING_AI_ENABLED" not in passed
    image_env = [call.args[0] for call in modal.Image.from_registry.return_value.env.call_args_list]
    assert all(not any(key.startswith("SPEAKING_AI_") for key in values) for values in image_env)


def test_full_entry_point_includes_the_shared_gpu_function(monkeypatch):
    module, modal, llm = load_app(monkeypatch)
    assert [call.args[0] for call in modal.App.return_value.include.call_args_list] == [
        llm.app,
        module.asr_app,
    ]
    image = modal.Image.from_registry.return_value
    image.apt_install.assert_called_once_with("nginx", "curl", "xz-utils", "ffmpeg")
    assert "gpu" not in modal.App.return_value.cls.call_args.kwargs


def test_explicit_web_only_does_not_include_gpu(monkeypatch):
    module, modal, _ = load_app(monkeypatch, enabled=False)
    assert not module.AI_ENABLED
    modal.App.return_value.include.assert_not_called()


def test_web_uses_bounded_concurrency_with_one_cpu_container(monkeypatch):
    _, modal, _ = load_app(monkeypatch, enabled=False)
    modal.concurrent.assert_called_once_with(max_inputs=8)
    options = modal.App.return_value.cls.call_args.kwargs
    assert options["min_containers"] == 1
    assert options["max_containers"] == 1
    assert options["cpu"] == 2
    assert options["memory"] == 4096
    assert "gpu" not in options


def test_asset_volume_default_and_explicit_isolation(monkeypatch):
    monkeypatch.delenv("IELTS_MODAL_ASSETS_VOLUME", raising=False)
    _, modal, _ = load_app(monkeypatch)
    assert any(call.args[0] == "ielts-web-assets" for call in modal.Volume.from_name.call_args_list)
    monkeypatch.setenv("IELTS_MODAL_ASSETS_VOLUME", "ielts-assets-isolated-dev")
    _, modal, _ = load_app(monkeypatch)
    assert any(
        call.args[0] == "ielts-assets-isolated-dev"
        for call in modal.Volume.from_name.call_args_list
    )


def test_asset_volume_rejects_empty_explicit_name(monkeypatch):
    monkeypatch.setenv("IELTS_MODAL_ASSETS_VOLUME", " ")
    with pytest.raises(ValueError, match="IELTS_MODAL_ASSETS_VOLUME"):
        load_app(monkeypatch)


def test_explicit_asset_volume_does_not_create_empty_replacement(monkeypatch):
    monkeypatch.setenv("IELTS_MODAL_ASSETS_VOLUME", "precreated-assets")
    _, modal, _ = load_app(monkeypatch)
    call = next(
        call
        for call in modal.Volume.from_name.call_args_list
        if call.args[0] == "precreated-assets"
    )
    assert call.kwargs["create_if_missing"] is False


def test_explicit_asr_disable_keeps_llm_without_asr_gpu(monkeypatch):
    module, modal, llm = load_app(monkeypatch, asr_enabled=False)
    assert not module.ASR_ENABLED
    modal.App.return_value.include.assert_called_once_with(llm.app)


def test_chart_service_is_explicitly_optional_and_separate(monkeypatch):
    module, modal, llm = load_app(monkeypatch, chart_enabled=True)
    assert module.CHART_SPECIALIST_ENABLED
    assert [call.args[0] for call in modal.App.return_value.include.call_args_list] == [
        llm.app,
        module.asr_app,
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
    assert modal.App.return_value.include.call_count == (3 if frozen else 2)


@pytest.mark.parametrize("backend", ["s3", "r2"])
def test_cloud_topology_has_no_persistent_local_volumes_or_database_guard(backend, monkeypatch):
    monkeypatch.setenv("IELTS_MODAL_STORAGE_BACKEND", backend)
    monkeypatch.setenv("IELTS_MODAL_ASSETS_VOLUME", "")
    monkeypatch.setenv("IELTS_MODAL_CONFIG_SECRET", "isolated-cloud-config")
    module, modal, _ = load_app(monkeypatch)
    assert module.assets is None and module.database is None and module.owners is None
    assert modal.App.return_value.cls.call_args.kwargs["volumes"] == {}
    assert modal.App.return_value.cls.call_args.kwargs["max_containers"] == 1
    modal.Secret.from_name.assert_called_once_with("isolated-cloud-config")
    modal.Volume.from_name.assert_not_called()
    for call in modal.Image.from_registry.return_value.env.call_args_list:
        assert "AWS_SECRET_ACCESS_KEY" not in call.args[0]
        assert "DATABASE_URL" not in call.args[0]
        assert "STORAGE_BACKEND" not in call.args[0]


def test_mode_specific_volume_and_strict_dev_isolation(monkeypatch):
    monkeypatch.delenv("IELTS_MODAL_ASSETS_VOLUME", raising=False)
    monkeypatch.setenv("IELTS_MODAL_DEV_ASSETS_VOLUME", "precreated-dev-assets")
    monkeypatch.setenv("IELTS_MODAL_REQUIRE_ASSET_ISOLATION", "true")
    module, modal, _ = load_app(monkeypatch)
    assert module.ASSETS_VOLUME_NAME == "precreated-dev-assets"
    asset_call = next(
        call
        for call in modal.Volume.from_name.call_args_list
        if call.args[0] == "precreated-dev-assets"
    )
    assert asset_call.kwargs["create_if_missing"] is False
    monkeypatch.delenv("IELTS_MODAL_DEV_ASSETS_VOLUME")
    with pytest.raises(ValueError, match="Dev isolation"):
        load_app(monkeypatch)


def test_isolated_database_and_snapshot_volumes_require_explicit_creation(monkeypatch):
    monkeypatch.setenv("IELTS_MODAL_DATABASE_VOLUME", "precreated-staging-postgres")
    monkeypatch.setenv("IELTS_MODAL_SNAPSHOTS_VOLUME", "precreated-staging-snapshots")
    module, modal, _ = load_app(monkeypatch)
    assert module.DATABASE_VOLUME_NAME == "precreated-staging-postgres"
    assert module.OWNER_KEY == "precreated-staging-postgres"
    for name in ("precreated-staging-postgres", "precreated-staging-snapshots"):
        call = next(call for call in modal.Volume.from_name.call_args_list if call.args[0] == name)
        assert call.kwargs["create_if_missing"] is False
    runtime = stub_runtime(monkeypatch, external=False)
    monkeypatch.setattr(module.threading, "Thread", MagicMock())
    web = module.Web()
    web.start()
    module.owners.put.assert_called_once_with(
        "precreated-staging-postgres", web.owner, skip_if_exists=True
    )
    module.owners.get.return_value = web.owner
    web.stop()
    module.owners.pop.assert_called_with("precreated-staging-postgres", None)
    assert runtime.stop.call_count == 1


def test_legacy_database_guard_follows_volume_even_with_cross_mode_override(monkeypatch):
    monkeypatch.setenv("IELTS_MODAL_DATABASE_VOLUME", "ielts-web-postgres")
    module, _, _ = load_app(monkeypatch)
    assert module.MODE == "dev"
    assert module.OWNER_KEY == "production"


def stub_runtime(monkeypatch, *, external):
    runtime = ModuleType("web_runtime")
    instance = MagicMock()
    instance.local_postgres = not external
    runtime.WebRuntime = MagicMock(return_value=instance)
    for name in (
        "configure_ai_environment",
        "configure_speaking_asr_environment",
        "configure_chart_environment",
    ):
        setattr(runtime, name, MagicMock())
    runtime.safe_ai_configuration = lambda: {}
    monkeypatch.setitem(sys.modules, "web_runtime", runtime)
    return instance


def test_external_database_never_acquires_demo_guard_or_commits_database_volume(monkeypatch):
    monkeypatch.setenv("IELTS_MODAL_STORAGE_BACKEND", "r2")
    module, _, _ = load_app(monkeypatch)
    runtime = stub_runtime(monkeypatch, external=True)
    web = module.Web()
    web.start()
    assert web.owner is None
    web.stop()
    runtime.start.assert_called_once()
    runtime.stop.assert_called_once()


def test_demo_reload_precedes_processes_and_commit_occurs_after_stop(monkeypatch):
    module, _, _ = load_app(monkeypatch)
    runtime = stub_runtime(monkeypatch, external=False)
    monkeypatch.setattr(module.threading, "Thread", MagicMock())
    events = []
    module.assets.reload.side_effect = lambda: events.append("reload")
    module.assets.commit.side_effect = lambda: events.append("assets-committed")
    runtime.start.side_effect = lambda: events.append("start")
    runtime.stop.side_effect = lambda: events.append("stop")
    web = module.Web()
    web.start()
    module.owners.get.return_value = web.owner
    web.stop()
    assert events == ["reload", "start", "stop", "assets-committed"]
    module.owners.pop.assert_called_with("dev", None)


def test_shutdown_commit_failure_is_explicit_and_guard_is_released_after_database_stop(monkeypatch):
    module, _, _ = load_app(monkeypatch)
    runtime = stub_runtime(monkeypatch, external=False)
    monkeypatch.setattr(module.threading, "Thread", MagicMock())
    web = module.Web()
    web.start()
    module.owners.get.return_value = web.owner
    module.assets.commit.side_effect = RuntimeError("private provider diagnostic")
    with pytest.raises(RuntimeError, match="Volume commit") as error:
        web.stop()
    runtime.stop.assert_called_once()
    module.owners.pop.assert_called_with("dev", None)
    assert "private provider diagnostic" not in str(error.value)


def test_operator_migration_function_has_secrets_and_no_volume_or_automatic_invocation(monkeypatch):
    monkeypatch.setenv("IELTS_MODAL_STORAGE_BACKEND", "r2")
    module, modal, _ = load_app(monkeypatch)
    options = modal.App.return_value.function.call_args.kwargs
    assert options["secrets"] == module.web_secrets and options["max_containers"] == 1
    assert "volumes" not in options
    assert "migrate_database" not in module.Web.start.__code__.co_names
