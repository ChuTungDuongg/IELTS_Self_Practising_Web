"""Isolated optional model process. No Azure, OpenAI, backend or database imports."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import socket
import tempfile
import wave
from pathlib import Path

IDENTITY = json.loads(Path(__file__).with_name("model.json").read_text(encoding="utf-8"))
RECEIPT = "bandpilot-model.json"


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(65536):
            checksum.update(block)
    return checksum.hexdigest()


def versions():
    actual = {name: importlib.metadata.version(name) for name in IDENTITY["versions"]}
    if any(actual[name].split("+")[0] != wanted for name, wanted in IDENTITY["versions"].items()):
        raise ValueError("Unsupported isolated environment")
    return actual


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


def setup(directory):
    # Explicit setup only. HF agreement must already have been accepted by the operator.
    from huggingface_hub import snapshot_download

    token = os.environ.pop("HF_TOKEN", "")
    if not token:
        return {"error_code": "REPLAY_DIARIZATION_HF_TOKEN_REQUIRED"}
    if directory.exists():
        try:
            verify_model(directory)
        except (OSError, ValueError, KeyError):
            return {"error_code": "REPLAY_DIARIZATION_MODEL_ASSET_MISSING_OR_CHANGED"}
        return {"schema_version": 1, "state": "ALREADY_INSTALLED", "identity": IDENTITY}
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="diarization-setup-", dir=directory.parent
    ) as temporary:
        snapshot = Path(temporary) / "snapshot"
        try:
            snapshot_download(
                IDENTITY["model"],
                revision=IDENTITY["revision"],
                token=token,
                local_dir=snapshot,
                max_workers=2,
            )
        except Exception:
            # Hub errors can contain credentials, URLs and headers, and some inherit OSError.
            return {"error_code": "REPLAY_DIARIZATION_MODEL_DOWNLOAD_FAILED_CHECK_HF_ACCESS"}
        files = [
            p
            for p in snapshot.rglob("*")
            if p.is_file() and ".cache" not in p.relative_to(snapshot).parts
        ]
        if len(files) > 2048 or sum(p.stat().st_size for p in files) > 4 * 1024**3:
            raise ValueError("Model setup size exceeded")
        if not any(p.suffix in {".bin", ".safetensors"} and p.stat().st_size > 1024 for p in files):
            raise ValueError("No model weights")
        receipt = {
            "schema_version": 1,
            "identity": IDENTITY,
            "runtime_versions": versions(),
            "files": {p.relative_to(snapshot).as_posix(): digest(p) for p in files},
        }
        (snapshot / RECEIPT).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        verify_model(snapshot)
        # Both absolute paths are within the explicit model parent, and destination is absent.
        if not snapshot.resolve().is_relative_to(directory.parent.resolve()) or directory.exists():
            raise ValueError("Unsafe setup destination")
        snapshot.replace(directory)
    return {"schema_version": 1, "state": "INSTALLED", "identity": IDENTITY}


def no_network(*_args, **_kwargs):
    raise OSError("Offline diarization forbids network access")


def infer(args):
    # Fence before importing telemetry-enabled libraries. Cached assets only, even on malformed configs.
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    socket.getaddrinfo = no_network
    try:
        verify_model(args.model_dir)
    except (OSError, ValueError, KeyError):
        return {"error_code": "REPLAY_DIARIZATION_MODEL_ASSET_MISSING_OR_CHANGED"}
    runtime = versions()
    import torch
    from pyannote.audio import Pipeline

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    if args.device == "cuda" and not torch.cuda.is_available():
        return {"error_code": "REPLAY_DIARIZATION_REQUESTED_GPU_UNAVAILABLE"}
    pipeline = Pipeline.from_pretrained(args.model_dir, token=False)
    if pipeline is None:
        raise ValueError("Offline model unavailable")
    pipeline.to(torch.device(args.device))
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
        "runtime_versions": runtime,
        "identity": IDENTITY,
        "duration_ms": frames * 1000 // 16000,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("setup", "analyze"))
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--threads", type=int, default=2, choices=range(1, 9))
    parser.add_argument("--max-speakers", type=int, default=8, choices=range(1, 21))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    try:
        versions()
        result = setup(args.model_dir.resolve()) if args.operation == "setup" else infer(args)
    except (ImportError, importlib.metadata.PackageNotFoundError, OSError):
        result = {"error_code": "REPLAY_DIARIZATION_DEPENDENCIES_OR_NATIVE_RUNTIME_UNAVAILABLE"}
    except Exception:
        result = {
            "error_code": "REPLAY_DIARIZATION_MODEL_DOWNLOAD_FAILED_ACCEPT_HF_TERMS"
            if args.operation == "setup"
            else "REPLAY_DIARIZATION_MODEL_OR_INFERENCE_FAILED"
        }
    args.output.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    return 2 if "error_code" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
