"""Deterministic bootstrap/diagnostic contracts. No real credentials or downloads."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation.speaking import diarization_backend as boundary


def load_tool(name):
    spec = importlib.util.spec_from_file_location(
        "test_diarization_" + name, boundary.TOOL / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bootstrap():
    return load_tool("diarization_runtime")


def shared(directory, bootstrap, major=7):
    directory.mkdir(parents=True)
    for name, version in zip(
        ("avcodec", "avformat", "avutil", "swresample", "swscale"),
        bootstrap.FFMPEG_ABIS[major],
        strict=True,
    ):
        (directory / f"{name}-{version}.dll").write_bytes(b"synthetic DLL marker")
    return directory


def test_restricted_child_keeps_windows_bootstrap_and_explicit_dll_path(monkeypatch, tmp_path):
    monkeypatch.setenv("SYSTEMROOT", str(tmp_path / "Windows"))
    monkeypatch.setenv("BANDPILOT_FFMPEG_DLL_DIR", str(tmp_path))
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / "conda"))
    monkeypatch.setenv("AZURE_PRIVATE_SECRET", "NEVER_FORWARD")
    env = boundary.offline_environment()
    assert env["SYSTEMROOT"] == str(tmp_path / "Windows")
    assert env["BANDPILOT_FFMPEG_DLL_DIR"] == str(tmp_path)
    assert env["CONDA_PREFIX"] == str(tmp_path / "conda")
    assert "NEVER_FORWARD" not in json.dumps(env)


def test_conda_environment_is_discovered_without_activation(bootstrap, tmp_path):
    installed = shared(tmp_path / "anaconda3/envs/audio/Library/bin", bootstrap)
    result = bootstrap.resolve_ffmpeg(environ={}, home=tmp_path, windows=True)
    assert result == (installed.resolve(), 7)


def test_explicit_then_path_then_active_conda_precedence(bootstrap, tmp_path):
    explicit = shared(tmp_path / "explicit", bootstrap, 6)
    on_path = shared(tmp_path / "path", bootstrap, 7)
    active = shared(tmp_path / "active/Library/bin", bootstrap, 5)
    env = {
        "BANDPILOT_FFMPEG_DLL_DIR": str(explicit),
        "PATH": str(on_path),
        "CONDA_PREFIX": str(active.parent.parent),
    }
    assert bootstrap.resolve_ffmpeg(environ=env, home=tmp_path, windows=True)[1] == 6
    del env["BANDPILOT_FFMPEG_DLL_DIR"]
    assert bootstrap.resolve_ffmpeg(environ=env, home=tmp_path, windows=True)[1] == 7
    del env["PATH"]
    assert bootstrap.resolve_ffmpeg(environ=env, home=tmp_path, windows=True)[1] == 5


def test_static_ffmpeg_and_incomplete_shared_set_are_rejected(bootstrap, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "ffmpeg.exe").write_bytes(b"synthetic exe marker")
    (static / "avcodec-61.dll").write_bytes(b"incomplete shared set")
    with pytest.raises(bootstrap.StageError, match="SHARED_DLLS_MISSING"):
        bootstrap.resolve_ffmpeg(environ={"PATH": str(static)}, home=tmp_path, windows=True)
    with pytest.raises(bootstrap.StageError, match="OVERRIDE_INVALID"):
        bootstrap.resolve_ffmpeg(
            environ={"BANDPILOT_FFMPEG_DLL_DIR": str(static)}, home=tmp_path, windows=True
        )


def test_dll_handle_stays_alive_and_registration_precedes_native_imports(
    bootstrap, tmp_path, monkeypatch
):
    events, handle = [], object()
    monkeypatch.setattr(bootstrap, "resolve_ffmpeg", lambda **_: (tmp_path, 7))
    monkeypatch.setattr(
        bootstrap.os,
        "add_dll_directory",
        lambda path: events.append("register") or handle,
        raising=False,
    )
    monkeypatch.setattr(
        bootstrap.importlib, "import_module", lambda name: events.append(name) or SimpleNamespace()
    )
    _, result = bootstrap.native_imports(windows=True)
    assert events == ["register", "torch", "torchcodec", "pyannote.audio"]
    assert bootstrap.DLL_HANDLES == [handle]
    assert result["native_imports"] == "OK"


def test_linux_never_uses_windows_dll_registration(bootstrap, monkeypatch):
    monkeypatch.setattr(
        bootstrap.os,
        "add_dll_directory",
        lambda _: pytest.fail("Windows-only API on Linux"),
        raising=False,
    )
    monkeypatch.setattr(bootstrap.importlib, "import_module", lambda _: SimpleNamespace())
    assert bootstrap.native_imports(windows=False)[1]["ffmpeg_shared_major"] is None


@pytest.mark.parametrize(
    "exception,expected",
    [
        (ModuleNotFoundError("PRIVATE_MARKER"), "PACKAGE_MISSING"),
        (OSError("PRIVATE_MARKER"), "TORCHCODEC_NATIVE_LOAD_FAILED"),
    ],
)
def test_native_import_errors_preserve_their_stage(bootstrap, monkeypatch, exception, expected):
    monkeypatch.setattr(bootstrap, "resolve_ffmpeg", lambda **_: (None, None))

    def imports(name):
        if name == "torchcodec":
            raise exception
        return SimpleNamespace()

    monkeypatch.setattr(bootstrap.importlib, "import_module", imports)
    with pytest.raises(bootstrap.StageError) as caught:
        bootstrap.native_imports()
    assert caught.value.code.endswith(expected) and caught.value.stage == "torchcodec_import"
    assert "PRIVATE_MARKER" not in json.dumps(caught.value.payload())


@pytest.mark.parametrize(
    "name,status,code",
    [
        ("HTTPError", 401, "HF_AUTHENTICATION_FAILED"),
        ("GatedRepoError", 403, "HF_GATED_ACCESS_DENIED"),
        ("SSLError", None, "HF_SSL_FAILED"),
        ("ProxyError", None, "HF_PROXY_FAILED"),
        ("ConnectionError", None, "HF_NETWORK_FAILED"),
        ("ReadTimeout", None, "HF_NETWORK_FAILED"),
        ("RevisionNotFoundError", 404, "HF_REVISION_NOT_FOUND"),
        ("EntryNotFoundError", 404, "HF_FILE_NOT_FOUND"),
        ("HTTPError", 500, "HF_DOWNLOAD_FAILED"),
    ],
)
def test_hf_errors_are_structured_and_secret_free(bootstrap, name, status, code):
    error = type(name, (Exception,), {})("PRIVATE_TOKEN https://signed.invalid/?credential=PRIVATE")
    error.response = SimpleNamespace(status_code=status)
    result = bootstrap.download_error(error).payload()
    assert result["error_code"] == "REPLAY_DIARIZATION_" + code
    assert result["stage"] == "model_download" and "PRIVATE" not in json.dumps(result)


def test_model_mkdir_and_temporary_directory_errors_are_not_native_failures(tmp_path, monkeypatch):
    worker = load_tool("worker")
    monkeypatch.setattr(
        Path, "mkdir", lambda *a, **kw: (_ for _ in ()).throw(PermissionError("PRIVATE"))
    )
    with pytest.raises(worker.runtime.StageError, match="MODEL_STORAGE_UNWRITABLE"):
        worker.model_parent(tmp_path / "model")
    monkeypatch.setattr(
        worker.tempfile,
        "TemporaryDirectory",
        lambda **kw: (_ for _ in ()).throw(OSError("PRIVATE")),
    )
    with pytest.raises(worker.runtime.StageError, match="TEMP_DIRECTORY_FAILED"):
        worker.temporary_directory(tmp_path, "test-")


def test_existing_verified_setup_never_reads_token_or_imports_native_modules(tmp_path, monkeypatch):
    worker = load_tool("worker")
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.yaml").write_text("synthetic verified model fixture")
    (model / "weights.bin").write_bytes(b"synthetic contract weights")
    (model / worker.RECEIPT).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "identity": worker.IDENTITY,
                "files": {
                    name: worker.digest(model / name) for name in ("config.yaml", "weights.bin")
                },
            }
        )
    )
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(
        worker.runtime, "native_imports", lambda: pytest.fail("Download imports native modules")
    )
    assert worker.setup(model)["state"] == "ALREADY_INSTALLED"


def test_inference_network_fence_blocks_dns_and_connection(bootstrap, monkeypatch):
    import socket

    for owner, name in (
        (socket, "getaddrinfo"),
        (socket, "create_connection"),
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
    ):
        monkeypatch.setattr(owner, name, getattr(owner, name))
    bootstrap.forbid_network()
    with pytest.raises(OSError, match="forbids network"):
        socket.getaddrinfo("huggingface.co", 443)
    with pytest.raises(OSError, match="forbids network"):
        socket.create_connection(("huggingface.co", 443))


@pytest.mark.parametrize("missing", [True, False])
def test_missing_and_incompatible_packages_are_not_dll_errors(bootstrap, monkeypatch, missing):
    monkeypatch.setattr(bootstrap, "sys", SimpleNamespace(version_info=(3, 12)))

    def version(_):
        if missing:
            raise bootstrap.importlib.metadata.PackageNotFoundError("PRIVATE")
        return "0.0.0"

    monkeypatch.setattr(bootstrap.importlib.metadata, "version", version)
    with pytest.raises(bootstrap.StageError) as caught:
        bootstrap.package_versions({"versions": {"torch": "2.8.0"}})
    expected = "PACKAGE_MISSING" if missing else "PACKAGE_VERSION_INCOMPATIBLE"
    assert caught.value.code.endswith(expected) and caught.value.stage == "packages"


def test_wrapped_hf_ssl_failure_is_not_reported_as_missing_file(bootstrap):
    error = type("LocalEntryNotFoundError", (Exception,), {})("PRIVATE")
    error.__cause__ = type("SSLError", (Exception,), {})("PRIVATE")
    assert bootstrap.download_error(error).code.endswith("HF_SSL_FAILED")


def test_diagnose_checks_storage_without_token_or_download(tmp_path, monkeypatch):
    worker = load_tool("worker")
    monkeypatch.setattr(worker, "versions", lambda: worker.IDENTITY["versions"])
    checked = []
    monkeypatch.setattr(
        worker,
        "hf_downloader",
        lambda: checked.append("hf_sdk") or (lambda: pytest.fail("HF called")),
    )
    monkeypatch.setattr(worker.runtime, "forbid_network", lambda: None)
    monkeypatch.setattr(worker.runtime, "native_imports", lambda: ({}, {"native_imports": "OK"}))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    result = worker.diagnose(tmp_path / "models/community")
    assert checked == ["hf_sdk"]
    assert result["model_state"] == "NOT_INSTALLED"
    assert not (tmp_path / "models/community").exists()
    assert str(tmp_path) not in json.dumps(result)


def test_unexpected_implementation_error_keeps_safe_class_and_stage(tmp_path, monkeypatch):
    worker = load_tool("worker")
    output = tmp_path / "result.json"
    monkeypatch.setattr(worker, "versions", lambda: {})
    monkeypatch.setattr(
        worker, "setup", lambda _: (_ for _ in ()).throw(RuntimeError("PRIVATE_TOKEN"))
    )
    monkeypatch.setattr(
        worker.argparse.ArgumentParser,
        "parse_args",
        lambda _: SimpleNamespace(operation="setup", model_dir=tmp_path, output=output),
    )
    assert worker.main() == 2
    result = json.loads(output.read_text())
    assert result["error_code"] == "REPLAY_DIARIZATION_INTERNAL_ERROR"
    assert result["stage"] == "setup" and result["exception_class"] == "RuntimeError"
    assert "PRIVATE_TOKEN" not in output.read_text()


def test_audio_decoder_also_uses_discovered_ffmpeg_without_path_changes(tmp_path, monkeypatch):
    from app.core.config import Settings

    settings = Settings(_env_file=None)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        (tmp_path / name).write_bytes(b"synthetic executable marker")
    helper = SimpleNamespace(resolve_ffmpeg=lambda: (tmp_path, 7), StageError=RuntimeError)
    monkeypatch.setattr(boundary, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(boundary, "local_runtime", lambda: helper)
    monkeypatch.setattr(boundary.shutil, "which", lambda _: None)
    configured = boundary.LocalDiarizer(python=tmp_path).audio_settings(settings)
    assert configured.speaking_ffmpeg_path == str(tmp_path / "ffmpeg.exe")
    assert settings.speaking_ffmpeg_path == "ffmpeg"


def test_missing_systemroot_is_reported_before_importing_any_sdk(bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="nt", environ={}))
    with pytest.raises(bootstrap.StageError, match="WINDOWS_SYSTEMROOT_MISSING"):
        bootstrap.package_versions({"versions": {}})


def test_parent_retains_safe_stage_and_class_from_failed_worker(tmp_path, monkeypatch):
    import os
    import sys

    def start(command, **_):
        output = Path(command[command.index("--output") + 1])
        output.write_text(
            json.dumps(
                {
                    "error_code": "REPLAY_DIARIZATION_HF_AUTHENTICATION_FAILED",
                    "stage": "model_download",
                    "exception_class": "HTTPError",
                }
            )
        )
        return SimpleNamespace(pid=os.getpid(), returncode=2, poll=lambda: 2)

    monkeypatch.setattr(boundary.subprocess, "Popen", start)
    with pytest.raises(boundary.DiarizationProcessError) as caught:
        boundary.LocalDiarizer(python=sys.executable, model_dir=tmp_path).preflight()
    assert caught.value.stage == "model_download" and caught.value.exception_class == "HTTPError"
    assert str(caught.value) == "REPLAY_DIARIZATION_HF_AUTHENTICATION_FAILED"


def test_parent_ipc_temp_failure_has_a_precise_code(monkeypatch):
    monkeypatch.setattr(
        boundary.tempfile,
        "TemporaryDirectory",
        lambda **_: (_ for _ in ()).throw(PermissionError("PRIVATE_PATH")),
    )
    with pytest.raises(boundary.DiarizationProcessError, match="TEMP_DIRECTORY_FAILED") as caught:
        with boundary.temporary_workspace():
            pytest.fail("Invalid temporary storage was used")
    assert caught.value.stage == "parent_temporary_directory"
