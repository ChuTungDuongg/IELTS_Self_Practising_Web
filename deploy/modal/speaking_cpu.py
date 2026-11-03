"""Pinned CPU speech runtime. Importing this module never imports a speech SDK."""

import json
from pathlib import Path

PACKAGES = (
    "azure-cognitiveservices-speech==1.53.0",
    "onnxruntime==1.23.2",
    "numpy==2.2.6",
)
SYSTEM_PACKAGES = ("libasound2", "libssl3", "ca-certificates", "ffmpeg")
VAD_CONTAINER_PATH = "/opt/speaking/silero-v6.0.onnx"
VAD_SHA256 = "597d30b3ec076608d059477bb14cfeffdf951bf5cae370d38f65d33bbfe82004"


def install_cpu_speech(image):
    return image.apt_install(*SYSTEM_PACKAGES).run_commands(
        "python -m pip install " + " ".join(PACKAGES)
    )


def include_vad_model(image, path: Path, expected_sha256: str):
    """Explicit operator-supplied model, never a request/startup download."""
    import hashlib

    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("SPEAKING_VAD_ASSET_UNAVAILABLE")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("SPEAKING_VAD_CHECKSUM_MISMATCH")
    return image.add_local_file(path, VAD_CONTAINER_PATH, copy=True)


def probe():
    """Validate native loading and CPU runtime only: no key, model or network."""
    import ctypes
    from importlib.metadata import version

    import azure.cognitiveservices.speech as speech
    import numpy
    import onnxruntime

    ctypes.CDLL("libasound.so.2")
    ctypes.CDLL("libssl.so.3")
    for package in PACKAGES:
        name, expected = package.split("==")
        if version(name) != expected:
            raise RuntimeError("SPEAKING_CPU_DEPENDENCY_MISMATCH")
    if "CPUExecutionProvider" not in onnxruntime.get_available_providers():
        raise RuntimeError("SPEAKING_CPU_RUNTIME_UNAVAILABLE")
    # Constructs native SDK format/options without creating a recognizer/session.
    speech.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
    onnxruntime.SessionOptions()
    numpy.zeros(1, dtype=numpy.float32)
    return {"status": "CPU_NATIVE_PROBE_OK", "provider_calls": 0, "gpu_required": False}


if __name__ == "__main__":
    print(json.dumps(probe(), sort_keys=True))
