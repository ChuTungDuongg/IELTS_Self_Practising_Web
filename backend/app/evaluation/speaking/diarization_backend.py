"""Bounded optional subprocess boundary; production Web never imports Torch or pyannote."""

import importlib.util
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from app.evaluation.speaking.diarization_models import DiarizationResult, SpeakerTurn
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_audio import MAX_SOURCE_SECONDS, resolve_source
from app.services.speaking_audio import _render, execute_ffmpeg, fingerprint
from app.storage.local import LocalAssetStorage

ROOT = Path(__file__).resolve().parents[4]
TOOL = ROOT / "tools/speaking_diarization"


class DiarizationProcessError(BenchmarkInputError):
    def __init__(self, code, stage, exception_class="RuntimeError"):
        super().__init__(code)
        self.stage = stage if isinstance(stage, str) and stage.isidentifier() else "worker"
        self.exception_class = (
            exception_class
            if isinstance(exception_class, str)
            and exception_class.isidentifier()
            and len(exception_class) <= 64
            else "Exception"
        )


@lru_cache(maxsize=1)
def local_runtime():
    spec = importlib.util.spec_from_file_location(
        "diarization_bootstrap", TOOL / "diarization_runtime.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def temporary_workspace():
    try:
        directory = tempfile.TemporaryDirectory(prefix="diarization-native-")
    except OSError as error:
        raise DiarizationProcessError(
            "REPLAY_DIARIZATION_TEMP_DIRECTORY_FAILED",
            "parent_temporary_directory",
            type(error).__name__,
        ) from None
    with directory as path:
        yield path


def model_identity():
    return json.loads((TOOL / "model.json").read_text(encoding="utf-8"))


def offline_environment(*, setup_token=None, threads=2, device="cpu"):
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "CONDA_PREFIX",
        "CONDA_EXE",
        "BANDPILOT_FFMPEG_DLL_DIR",
    }
    # Windows normalizes environment names to uppercase; dropping SYSTEMROOT breaks Winsock.
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(
        PYANNOTE_METRICS_ENABLED="false",
        OTEL_SDK_DISABLED="true",
        HF_HUB_DISABLE_TELEMETRY="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        DO_NOT_TRACK="1",
        HF_HUB_OFFLINE="0" if setup_token else "1",
        TRANSFORMERS_OFFLINE="0" if setup_token else "1",
        OMP_NUM_THREADS=str(threads),
        MKL_NUM_THREADS=str(threads),
        OPENBLAS_NUM_THREADS=str(threads),
        NUMEXPR_NUM_THREADS=str(threads),
        VECLIB_MAXIMUM_THREADS=str(threads),
        TOKENIZERS_PARALLELISM="false",
    )
    if device == "cpu":
        env["CUDA_VISIBLE_DEVICES"] = ""
    if setup_token:
        env["HF_TOKEN"] = setup_token
    return env


def normalize_recording(root, name, metadata, destination, settings):
    """Whole-recording analysis has its own 30-minute bound; never a grading NormalizedAudio."""
    path = resolve_source(root, name)
    decoder = SimpleNamespace(
        speaking_ffmpeg_path=settings.speaking_ffmpeg_path,
        speaking_max_decoded_seconds=MAX_SOURCE_SECONDS,
        speaking_processing_timeout_seconds=settings.speaking_processing_timeout_seconds,
    )
    mime = "audio/wav" if metadata["format"] == "wav" else "audio/mpeg"
    duration = _render(
        [
            (
                mime,
                [
                    (
                        path.relative_to(root.resolve()).as_posix(),
                        metadata["sha256"],
                        metadata["size_bytes"],
                    )
                ],
            )
        ],
        destination,
        decoder,
        execute_ffmpeg,
        LocalAssetStorage(root.resolve()),
        window_ms=(0, metadata["duration_ms"]),
    )
    if abs(duration - metadata["duration_ms"]) > 100:
        raise BenchmarkInputError("REPLAY_DIARIZATION_DECODE_LENGTH_MISMATCH")
    return duration


class LocalDiarizer:
    def __init__(
        self,
        *,
        python=None,
        model_dir=None,
        threads=2,
        max_speakers=8,
        device="cpu",
        timeout=1800,
        memory_mb=4096,
    ):
        self.python = (
            Path(python)
            if python
            else TOOL / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
        )
        try:
            self.model_dir = (
                Path(model_dir) if model_dir else ROOT / "storage/models/pyannote-community-1"
            ).resolve()
        except (OSError, ValueError) as error:
            raise DiarizationProcessError(
                "REPLAY_DIARIZATION_MODEL_STORAGE_INVALID", "model_storage", type(error).__name__
            ) from None
        if any(type(value) is not int for value in (threads, max_speakers, timeout, memory_mb)):
            raise BenchmarkInputError("REPLAY_DIARIZATION_OPTIONS_INVALID")
        if not 1 <= threads <= 8 or not 1 <= max_speakers <= 20 or device not in {"cpu", "cuda"}:
            raise BenchmarkInputError("REPLAY_DIARIZATION_OPTIONS_INVALID")
        if not 5 <= timeout <= 7200 or not 512 <= memory_mb <= 32768:
            raise BenchmarkInputError("REPLAY_DIARIZATION_RESOURCE_LIMIT_INVALID")
        self.config = {
            "threads": threads,
            "max_speakers": max_speakers,
            "device": device,
            "timeout": timeout,
            "memory_mb": memory_mb,
        }
        self.identity = model_identity()

    def _run(self, operation, *, audio=None, token=None):
        if not self.python.is_file():
            raise BenchmarkInputError("REPLAY_DIARIZATION_ENV_MISSING_RUN_UV_SYNC")
        if operation == "analyze" and not (self.model_dir / "bandpilot-model.json").is_file():
            raise BenchmarkInputError("REPLAY_DIARIZATION_MODEL_MISSING_USE_SETUP")
        import psutil

        with temporary_workspace() as directory:
            output = Path(directory) / "result.json"
            command = [
                str(self.python),
                str(TOOL / "worker.py"),
                operation,
                "--model-dir",
                str(self.model_dir),
                "--output",
                str(output),
            ]
            if audio:
                command.extend(
                    [
                        "--audio",
                        str(audio),
                        "--threads",
                        str(self.config["threads"]),
                        "--max-speakers",
                        str(self.config["max_speakers"]),
                        "--device",
                        self.config["device"],
                    ]
                )
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=offline_environment(
                        setup_token=token,
                        threads=self.config["threads"],
                        device=self.config["device"],
                    ),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except OSError as error:
                raise DiarizationProcessError(
                    "REPLAY_DIARIZATION_ENV_START_FAILED", "worker_start", type(error).__name__
                ) from None
            started = time.monotonic()
            descendants = {}
            try:
                try:
                    monitor = psutil.Process(process.pid)
                except psutil.NoSuchProcess:
                    monitor = None
                while process.poll() is None:
                    if time.monotonic() - started > self.config["timeout"]:
                        raise BenchmarkInputError(
                            "REPLAY_DIARIZATION_TIMEOUT_MANUAL_WORKFLOW_AVAILABLE"
                        )
                    try:
                        children = monitor.children(recursive=True) if monitor else []
                        descendants.update({p.pid: p for p in children})
                        memory = (monitor.memory_info().rss if monitor else 0) + sum(
                            p.memory_info().rss for p in children
                        )
                        if memory > self.config["memory_mb"] * 1024**2:
                            raise BenchmarkInputError("REPLAY_DIARIZATION_MEMORY_LIMIT")
                    except psutil.NoSuchProcess:
                        pass
                    time.sleep(0.1)
            finally:
                for child in descendants.values():
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                if descendants:
                    _, alive = psutil.wait_procs(list(descendants.values()), timeout=5)
                    for child in alive:
                        child.kill()
                    psutil.wait_procs(alive, timeout=5)
            if not output.is_file() or output.stat().st_size > 8 * 1024**2:
                raise BenchmarkInputError("REPLAY_DIARIZATION_PROCESS_FAILED")
            result = json.loads(output.read_text(encoding="utf-8"))
            if process.returncode or result.get("error_code"):
                code = result.get("error_code", "REPLAY_DIARIZATION_PROCESS_FAILED")
                if (
                    not isinstance(code, str)
                    or not code.startswith("REPLAY_DIARIZATION_")
                    or not code.replace("_", "").isalnum()
                ):
                    code = "REPLAY_DIARIZATION_PROCESS_FAILED"
                raise DiarizationProcessError(
                    code, result.get("stage", "worker"), result.get("exception_class", "Exception")
                )
            return result

    def preflight(self):
        return self._run("diagnose")

    def audio_settings(self, settings):
        if os.name != "nt" or shutil.which(settings.speaking_ffmpeg_path):
            return settings
        helper = local_runtime()
        try:
            directory, _ = helper.resolve_ffmpeg()
        except helper.StageError as error:
            raise DiarizationProcessError(error.code, error.stage, error.exception_class) from None
        if not all((directory / name).is_file() for name in ("ffmpeg.exe", "ffprobe.exe")):
            raise DiarizationProcessError(
                "REPLAY_DIARIZATION_FFMPEG_EXECUTABLES_MISSING", "audio_decoder"
            )
        return settings.model_copy(update={"speaking_ffmpeg_path": str(directory / "ffmpeg.exe")})

    def setup(self, token=None):
        if not token and not self.model_dir.exists():
            raise BenchmarkInputError("REPLAY_DIARIZATION_HF_TOKEN_REQUIRED")
        return self._run("setup", token=token)

    def analyze(self, path, *, source, metadata, cache_key):
        started = time.perf_counter()
        raw = self._run("analyze", audio=path)
        if (
            raw.get("identity") != self.identity
            or abs(raw["duration_ms"] - metadata["duration_ms"]) > 100
        ):
            raise BenchmarkInputError("REPLAY_DIARIZATION_RESULT_IDENTITY_INVALID")
        labels = sorted(
            {
                turn["speaker"]
                for timeline in (raw["regular"], raw["exclusive"])
                for turn in timeline
            }
        )
        if len(labels) > self.config["max_speakers"]:
            raise BenchmarkInputError("REPLAY_DIARIZATION_SPEAKER_LIMIT")
        namespace = fingerprint([source, metadata["sha256"]])[:8]
        speakers = {label: f"f{namespace}-speaker_{i:02}" for i, label in enumerate(labels)}

        def turns(timeline, prefix):
            results = []
            for index, turn in enumerate(timeline):
                if any(
                    type(turn[k]) not in (int, float) or not math.isfinite(turn[k])
                    for k in ("start", "end")
                ):
                    raise BenchmarkInputError("REPLAY_DIARIZATION_TIMING_INVALID")
                start, end = round(turn["start"] * 1000), round(turn["end"] * 1000)
                if not 0 <= start < end <= metadata["duration_ms"] + 2:
                    raise BenchmarkInputError("REPLAY_DIARIZATION_TIMING_INVALID")
                results.append(
                    SpeakerTurn(
                        id=f"{namespace}-{prefix}{index}",
                        speaker_id=speakers[turn["speaker"]],
                        start_ms=start,
                        end_ms=min(end, metadata["duration_ms"]),
                    )
                )
            return results

        return DiarizationResult(
            source=source,
            source_sha256=metadata["sha256"],
            duration_ms=metadata["duration_ms"],
            cache_key=cache_key,
            identity={
                **self.identity,
                "runtime_versions": raw["runtime_versions"],
                "configuration": self.config,
            },
            regular=turns(raw["regular"], "r"),
            exclusive=turns(raw["exclusive"], "x"),
            latency_ms=(time.perf_counter() - started) * 1000,
        )
