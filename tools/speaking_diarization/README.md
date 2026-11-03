# Optional local diarization environment

This is a developer tool environment, not a backend/Modal dependency or service.
Its CPU lock targets Windows x86-64 and Linux x86-64 with Python 3.12. The backend
keeps its existing Python/runtime/package versions.

From the repository root:

```powershell
uv sync --project tools/speaking_diarization --python 3.12 --locked
uv run --project backend python scripts/replay_speaking.py --setup-diarization-model
uv run --project backend python scripts/replay_speaking.py --auto-segment
```

Setup is an explicit gated model download. First accept the
[Community-1 model conditions](https://huggingface.co/pyannote/speaker-diarization-community-1),
then put a read token in ignored `backend/.env` as `HF_TOKEN=...`, or enter it in
the hidden terminal prompt. Never put the token in arguments or chat. Setup binds
the model revision in `model.json` and writes a file-checksum receipt. Ordinary
inference uses only local receipt-verified assets and rejects network access.

Pinned combination: pyannote.audio 4.0.7, Torch/torchaudio 2.8.0 CPU, TorchCodec
0.7.0, huggingface-hub 0.36.0, NumPy 2.2.6. TorchCodec's official
[compatibility matrix](https://github.com/meta-pytorch/torchcodec/tree/v0.8.0#installing-torchcodec)
lists 0.7 with Torch 2.8. Windows support is experimental and native FFmpeg shared
libraries may be necessary even though the worker preloads mono PCM into memory.
See [complete workflow and troubleshooting](../../docs/testing/speaking-audio-replay.md#9-local-speaker-diarization-và-review).

The default interpreter is this project's `.venv`; no package install or model
download occurs during replay. `--diarization-python` can select an already
prepared compatible interpreter. CPU is default; `--diarization-device cuda`
is explicit opt-in with an existing CUDA-capable environment. The shipped lock
has no NVIDIA packages and never provisions a GPU. Model execution and accuracy
remain unverified until an operator runs the opt-in real-speech integration test.
