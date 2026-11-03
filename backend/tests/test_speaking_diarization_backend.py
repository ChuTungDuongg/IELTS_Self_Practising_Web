"""Offline subprocess/cache contracts; no model download or native inference."""

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_speaking_segment_review import draft  # noqa: F401

from app.core.config import Settings
from app.evaluation.speaking import diarization_backend as boundary
from app.evaluation.speaking import replay_diarization as coordinator
from app.evaluation.speaking.manifest import BenchmarkInputError


def test_child_environment_never_forwards_provider_credentials_or_implicit_hf_token(monkeypatch):
    for key in ("SPEAKING_AZURE_KEY", "AI_WRITING_OPENAI_API_KEY", "HF_TOKEN", "HF_ENDPOINT"):
        monkeypatch.setenv(key, "PRIVATE_MARKER")
    env = boundary.offline_environment()
    assert "PRIVATE_MARKER" not in json.dumps(env)
    assert env["PYANNOTE_METRICS_ENABLED"] == "false" and env["HF_HUB_OFFLINE"] == "1"
    assert env["CUDA_VISIBLE_DEVICES"] == ""
    assert env["OPENBLAS_NUM_THREADS"] == "2"


def test_setup_token_is_environment_only_and_analyze_namespaces_file_speakers(
    tmp_path, monkeypatch
):
    model = tmp_path / "model"
    model.mkdir()
    (model / "bandpilot-model.json").write_text("{}")
    engine = boundary.LocalDiarizer(python=sys.executable, model_dir=model)
    calls = []

    class Process:
        pid = os.getpid()
        returncode = 0

        def poll(self):
            return 0

    def start(command, **options):
        calls.append((command, options))
        path = Path(command[command.index("--output") + 1])
        raw = {
            "schema_version": 1,
            "identity": engine.identity,
            "runtime_versions": engine.identity["versions"],
            "duration_ms": 1000,
            "regular": [{"speaker": "SPEAKER_00", "start": 0, "end": 0.5}],
            "exclusive": [{"speaker": "SPEAKER_00", "start": 0, "end": 0.5}],
        }
        path.write_text(json.dumps(raw))
        return Process()

    monkeypatch.setattr(boundary.subprocess, "Popen", start)
    engine.setup("PRIVATE_HF_TOKEN_MARKER")
    assert calls[-1][1]["env"]["HF_TOKEN"] == "PRIVATE_HF_TOKEN_MARKER"
    assert "PRIVATE_HF_TOKEN_MARKER" not in json.dumps(calls[-1][0])
    first = engine.analyze(
        tmp_path / "audio.wav",
        source="part1.wav",
        metadata={"sha256": "a" * 64, "duration_ms": 1000},
        cache_key="b" * 64,
    )
    second = engine.analyze(
        tmp_path / "audio.wav",
        source="part2.wav",
        metadata={"sha256": "a" * 64, "duration_ms": 1000},
        cache_key="b" * 64,
    )
    assert first.regular[0].speaker_id != second.regular[0].speaker_id
    assert "HF_TOKEN" not in calls[-1][1]["env"]


def test_missing_environment_and_weights_fail_without_fallback(tmp_path):
    engine = boundary.LocalDiarizer(python=tmp_path / "missing-python")
    with pytest.raises(BenchmarkInputError, match="ENV_MISSING"):
        engine._run("analyze")
    engine = boundary.LocalDiarizer(python=sys.executable, model_dir=tmp_path / "missing-model")
    with pytest.raises(BenchmarkInputError, match="MODEL_MISSING"):
        engine._run("analyze")
    with pytest.raises(BenchmarkInputError, match="HF_TOKEN_REQUIRED"):
        engine.setup(None)


def test_subprocess_memory_limit_waits_for_native_process_exit(tmp_path, monkeypatch):
    import psutil

    model = tmp_path / "model"
    model.mkdir()
    (model / "bandpilot-model.json").write_text("{}")
    stopped = []

    class Process:
        pid = 99999
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            stopped.append("terminate")
            self.returncode = -15

        def wait(self, timeout):
            stopped.append("wait")

    monkeypatch.setattr(boundary.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(
        psutil,
        "Process",
        lambda _: SimpleNamespace(
            memory_info=lambda: SimpleNamespace(rss=10 * 1024**3), children=lambda **_: []
        ),
    )
    with pytest.raises(BenchmarkInputError, match="MEMORY_LIMIT"):
        boundary.LocalDiarizer(python=sys.executable, model_dir=model, memory_mb=512)._run(
            "analyze"
        )
    assert stopped == ["terminate", "wait"]


def test_cached_diarization_survives_prompt_label_and_pause_changes(draft, monkeypatch):  # noqa: F811
    root, item, metadata = draft

    def probe(path, _):
        return {**metadata, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    monkeypatch.setattr(coordinator, "probe_audio", probe)
    monkeypatch.setattr(
        coordinator,
        "normalize_recording",
        lambda _root, _name, _meta, destination, _settings: destination.write_bytes(
            b"normalized fixture"
        ),
    )

    class Engine:
        identity = {"model": "fixture", "revision": "v1"}
        config = {"threads": 2}
        calls = 0

        def analyze(self, _, *, source, metadata, cache_key):
            self.calls += 1
            return item.model_copy(
                update={
                    "source": source,
                    "source_sha256": metadata["sha256"],
                    "cache_key": cache_key,
                    "identity": self.identity.copy(),
                }
            )

    engine = Engine()
    configured = Settings(_env_file=None)
    _, reused = coordinator.auto_segment(root, configured, backend=engine)
    assert engine.calls == 1 and reused == 0
    (root / "human_labels.json").write_text('{"private_label":"not inference input"}')
    configured.speaking_ai_prompt_version = "another-prompt"
    _, reused = coordinator.auto_segment(root, configured, backend=engine, pause_tolerance_ms=1000)
    assert engine.calls == 1 and reused == 1
    engine.identity = {**engine.identity, "revision": "v2"}
    coordinator.auto_segment(root, configured, backend=engine)
    assert engine.calls == 2
    (root / item.source).write_bytes(b"different recording")
    coordinator.auto_segment(root, configured, backend=engine)
    assert engine.calls == 3


def test_no_heavy_dependency_in_production_images_or_backend():
    project = boundary.ROOT / "backend/pyproject.toml"
    assert "pyannote" not in project.read_text() and '"torch' not in project.read_text()
    image = (boundary.ROOT / "deploy/modal/app.py").read_text()
    assert "pyannote" not in image and "speaking_diarization" not in image
    lock = (boundary.TOOL / "uv.lock").read_text()
    assert 'registry = "https://download.pytorch.org/whl/cpu"' in lock
    assert 'name = "nvidia-' not in lock


def test_model_receipt_detects_changed_assets_and_path_escape(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "local_diarization_worker", boundary.TOOL / "worker.py"
    )
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.yaml").write_text("fixture config; no model inference")
    (model / "weights.bin").write_bytes(b"synthetic contract bytes")
    receipt = {
        "identity": worker.IDENTITY,
        "files": {name: worker.digest(model / name) for name in ("config.yaml", "weights.bin")},
    }
    (model / worker.RECEIPT).write_text(json.dumps(receipt))
    assert worker.verify_model(model)["identity"] == worker.IDENTITY
    (model / "weights.bin").write_bytes(b"changed bytes")
    with pytest.raises(ValueError, match="asset mismatch"):
        worker.verify_model(model)
    receipt["files"] = {"../outside.bin": "a" * 64}
    (tmp_path / "outside.bin").write_bytes(b"private outside fixture")
    (model / worker.RECEIPT).write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="asset mismatch"):
        worker.verify_model(model)


@pytest.mark.parametrize("download_fails", [False, True])
def test_explicit_setup_pins_snapshot_and_never_persists_or_echoes_token(
    tmp_path, monkeypatch, download_fails
):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "local_diarization_setup", boundary.TOOL / "worker.py"
    )
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    calls = []

    def download(name, **options):
        calls.append((name, options))
        if download_fails:
            raise OSError("PRIVATE_HF_TOKEN_AND_SENSITIVE_URL")
        snapshot = options["local_dir"]
        snapshot.mkdir()
        (snapshot / "config.yaml").write_text("synthetic setup fixture; never loaded by model")
        (snapshot / "weights.bin").write_bytes(b"synthetic bytes" * 100)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    monkeypatch.setenv("HF_TOKEN", "PRIVATE_HF_TOKEN_AND_SENSITIVE_URL")
    monkeypatch.setattr(worker, "versions", lambda: worker.IDENTITY["versions"])
    target = tmp_path / "model"
    output = worker.setup(target)
    assert calls[0][0] == worker.IDENTITY["model"]
    assert calls[0][1]["revision"] == worker.IDENTITY["revision"]
    assert "HF_TOKEN" not in os.environ
    assert "PRIVATE_HF_TOKEN" not in json.dumps(output)
    if download_fails:
        assert output["error_code"] == "REPLAY_DIARIZATION_MODEL_DOWNLOAD_FAILED_CHECK_HF_ACCESS"
        assert not target.exists()
    else:
        assert worker.verify_model(target)["identity"] == worker.IDENTITY
        assert "PRIVATE_HF_TOKEN" not in (target / worker.RECEIPT).read_text()
