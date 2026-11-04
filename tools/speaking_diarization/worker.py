"""Isolated optional model process. No Azure, OpenAI, backend or database imports."""

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
import wave
from pathlib import Path

IDENTITY = json.loads(Path(__file__).with_name("model.json").read_text(encoding="utf-8"))
RECEIPT = "bandpilot-model.json"
_spec = importlib.util.spec_from_file_location(
    "isolated_diarization_runtime", Path(__file__).with_name("diarization_runtime.py")
)
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(65536):
            checksum.update(block)
    return checksum.hexdigest()


def versions():
    return runtime.package_versions(IDENTITY)


def verify_model(directory):
    receipt = json.loads((directory / RECEIPT).read_text(encoding="utf-8"))
    if receipt["identity"] != IDENTITY or not 1 <= len(receipt["files"]) <= 2048:
        raise ValueError("Model identity mismatch")
    for name, checksum in receipt["files"].items():
        path = (directory / name).resolve(strict=True)
        if (
            not path.is_relative_to(directory.resolve())
            or path.is_symlink()
            or digest(path) != checksum
        ):
            raise ValueError("Model asset mismatch")
    if not (directory / "config.yaml").is_file():
        raise ValueError("Model config missing")
    return receipt


def verified_model(directory):
    try:
        return verify_model(directory)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise runtime.StageError("MODEL_ASSET_MISSING_OR_CHANGED", "model_verify", error) from None


def model_parent(directory):
    try:
        if directory.exists() and not directory.is_dir():
            raise NotADirectoryError()
        directory.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise runtime.StageError("MODEL_STORAGE_UNWRITABLE", "model_storage", error) from None


def temporary_directory(parent, prefix):
    try:
        return tempfile.TemporaryDirectory(prefix=prefix, dir=parent)
    except OSError as error:
        raise runtime.StageError("TEMP_DIRECTORY_FAILED", "temporary_directory", error) from None


def hf_downloader():
    try:
        from huggingface_hub import snapshot_download

        return snapshot_download
    except ImportError as error:
        raise runtime.StageError("PACKAGE_MISSING", "hf_sdk_import", error) from None
    except Exception as error:
        raise runtime.StageError("HF_SDK_IMPORT_FAILED", "hf_sdk_import", error) from None


def diagnose(directory):
    runtime.forbid_network()
    actual = versions()
    hf_downloader()  # Import-only check: never invoke HF or prompt for a token here.
    model_parent(directory)
    with temporary_directory(directory.parent, "diarization-write-probe-") as temporary:
        try:
            (Path(temporary) / "probe").write_bytes(b"local storage preflight")
        except OSError as error:
            raise runtime.StageError("MODEL_STORAGE_UNWRITABLE", "model_storage", error) from None
    state = "VERIFIED" if directory.exists() and verified_model(directory) else "NOT_INSTALLED"
    _, native = runtime.native_imports()
    return {
        "schema_version": 1,
        "state": "PREFLIGHT_OK",
        "model_state": state,
        "python": "3.12",
        "runtime_versions": actual,
        **native,
    }


def setup(directory):
    # Download needs package metadata and HF SDK, never a TorchCodec/pyannote import.

    token = os.environ.pop("HF_TOKEN", "")
    if directory.exists():
        verified_model(directory)
        return {"schema_version": 1, "state": "ALREADY_INSTALLED", "identity": IDENTITY}
    if not token:
        raise runtime.StageError("HF_TOKEN_REQUIRED", "hf_authentication")
    model_parent(directory)
    snapshot_download = hf_downloader()
    with temporary_directory(directory.parent, "diarization-setup-") as temporary:
        snapshot = Path(temporary) / "snapshot"
        try:
            snapshot_download(
                IDENTITY["model"],
                revision=IDENTITY["revision"],
                token=token,
                local_dir=snapshot,
                max_workers=2,
            )
        except Exception as error:
            raise runtime.download_error(error) from None
        try:
            files = [
                p
                for p in snapshot.rglob("*")
                if p.is_file() and ".cache" not in p.relative_to(snapshot).parts
            ]
            if len(files) > 2048 or sum(p.stat().st_size for p in files) > 4 * 1024**3:
                raise runtime.StageError("MODEL_ASSET_INVALID", "model_verify")
            if not any(
                p.suffix in {".bin", ".safetensors"} and p.stat().st_size > 1024 for p in files
            ):
                raise runtime.StageError("MODEL_ASSET_INVALID", "model_verify")
            receipt = {
                "schema_version": 1,
                "identity": IDENTITY,
                "runtime_versions": versions(),
                "files": {p.relative_to(snapshot).as_posix(): digest(p) for p in files},
            }
            (snapshot / RECEIPT).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            verified_model(snapshot)
            # Both absolute paths stay inside the explicit model parent; never overwrite assets.
            if (
                not snapshot.resolve().is_relative_to(directory.parent.resolve())
                or directory.exists()
            ):
                raise runtime.StageError("MODEL_STORAGE_CONFLICT", "model_install")
            snapshot.replace(directory)
        except OSError as error:
            raise runtime.StageError("MODEL_STORAGE_UNWRITABLE", "model_install", error) from None
    return {"schema_version": 1, "state": "INSTALLED", "identity": IDENTITY}


def infer(args):
    # Fence before importing telemetry-enabled libraries. Cached assets only, even on malformed configs.
    runtime.forbid_network()
    verified_model(args.model_dir)
    actual = versions()
    modules, _ = runtime.native_imports()
    torch, Pipeline = modules["torch"], modules["pyannote.audio"].Pipeline

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    if args.device == "cuda" and not torch.cuda.is_available():
        return {"error_code": "REPLAY_DIARIZATION_REQUESTED_GPU_UNAVAILABLE"}
    try:
        pipeline = Pipeline.from_pretrained(args.model_dir, token=False)
        if pipeline is None:
            raise ValueError("Offline model unavailable")
        pipeline.to(torch.device(args.device))
    except Exception as error:
        raise runtime.StageError("MODEL_LOAD_FAILED", "model_load", error) from None
    # Predecoded PCM avoids a second decoder/resampler and keeps the original timeline intact.
    with wave.open(str(args.audio), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError("Invalid diarization PCM")
        frames = source.getnframes()
        if not 0 < frames <= 1800 * 16000:
            raise ValueError("Invalid diarization duration")
        pcm = bytearray(source.readframes(frames))
        if len(pcm) != frames * 2:
            raise ValueError("Incomplete diarization PCM")
    waveform = torch.frombuffer(pcm, dtype=torch.int16).float().div_(32768).unsqueeze(0)
    with torch.inference_mode():
        output = pipeline(
            {"waveform": waveform, "sample_rate": 16000}, max_speakers=args.max_speakers
        )

    def rows(annotation):
        return [
            {"speaker": str(label), "start": float(turn.start), "end": float(turn.end)}
            for turn, _, label in annotation.itertracks(yield_label=True)
        ]

    return {
        "schema_version": 1,
        "regular": rows(output.speaker_diarization),
        "exclusive": rows(output.exclusive_speaker_diarization),
        "runtime_versions": actual,
        "identity": IDENTITY,
        "duration_ms": frames * 1000 // 16000,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("setup", "analyze", "diagnose"))
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--threads", type=int, default=2, choices=range(1, 9))
    parser.add_argument("--max-speakers", type=int, default=8, choices=range(1, 21))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    try:
        versions()
        if args.operation == "setup":
            result = setup(args.model_dir.resolve())
        elif args.operation == "diagnose":
            result = diagnose(args.model_dir.resolve())
        else:
            result = infer(args)
    except runtime.StageError as error:
        result = error.payload()
    except Exception as error:
        result = runtime.StageError("INTERNAL_ERROR", args.operation, error).payload()
    args.output.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    return 2 if "error_code" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
