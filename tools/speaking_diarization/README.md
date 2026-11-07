# Optional local diarization environment

This is a developer tool environment, not a backend/Modal dependency or service.
Its CPU lock targets Windows x86-64 and Linux x86-64 with Python 3.12. The backend
keeps its existing Python/runtime/package versions.

On the configured Windows machine, run this single setup command from the repository root:

```powershell
uv run --project backend python scripts/replay_speaking.py --setup-diarization-model
```

Setup is an explicit gated model download. First accept the
[Community-1 model conditions](https://huggingface.co/pyannote/speaker-diarization-community-1),
then enter a read token at the hidden terminal prompt when requested. Existing `HF_TOKEN`
in the process environment takes precedence over ignored `backend/.env`. Native imports,
package versions and writable storage are checked **before** reading/prompting for the token.
Already installed, verified assets return success without a token or another download.
Never put the token in arguments or chat. Setup binds
the model revision in `model.json` and writes a file-checksum receipt. Ordinary
inference uses only local receipt-verified assets and rejects network access. Model download
uses the HF SDK without importing TorchCodec; the separate offline preflight checks native readiness.

After setup, `--auto-segment` uses the same automatic DLL discovery. No Conda activation,
global PATH/registry change or GPU setup is required. Windows discovery tries the validated
`BANDPILOT_FFMPEG_DLL_DIR` override, PATH directories, active Conda `Library/bin`, then known
Conda installation/env directories and the user's bounded `.conda/environments.txt` registry.
It checks a coherent avcodec/avformat/avutil/swresample/swscale DLL set for FFmpeg 4–7;
finding a static `ffmpeg.exe` alone is insufficient. `os.add_dll_directory()` runs before
native imports and its handles live until worker exit. Missing ffmpeg/ffprobe on PATH can
also be resolved from that shared installation for audio probing/normalization.

The restricted child environment preserves Windows `SYSTEMROOT` case-insensitively. Dropping
it caused Winsock error 10106 during HF SDK/Torch import on the reported machine, even with
FFmpeg installed. Provider credentials and implicit HF tokens remain excluded from inference.
The bootstrap follows Python's documented [Windows environment requirements](https://docs.python.org/3.12/library/subprocess.html#subprocess.Popen)
and [DLL-directory lifetime](https://docs.python.org/3.12/library/os.html#os.add_dll_directory).

`--diagnose-diarization` runs package, storage and real native-import checks offline, without
a token, download or audio. Output contains safe status/stage/exception-class codes only.
The old generic dependency error is replaced by these stage-specific codes (prefix omitted):

| Code | Meaning |
| --- | --- |
| `ENV_MISSING_RUN_UV_SYNC`, `ENV_START_FAILED` | Isolated interpreter absent/cannot start |
| `WINDOWS_SYSTEMROOT_MISSING` | Required Windows bootstrap environment missing |
| `PYTHON_VERSION_UNSUPPORTED`, `PACKAGE_MISSING`, `PACKAGE_VERSION_INCOMPATIBLE` | Runtime/version issue |
| `FFMPEG_SHARED_DLLS_MISSING`, `FFMPEG_OVERRIDE_INVALID` | No compatible shared set / invalid explicit override |
| `TORCH_NATIVE_LOAD_FAILED`, `TORCHCODEC_NATIVE_LOAD_FAILED`, `PYANNOTE_NATIVE_LOAD_FAILED` | Import stage failed after discovery/registration |
| `MODEL_STORAGE_UNWRITABLE`, `TEMP_DIRECTORY_FAILED` | Filesystem/storage issue, not a decoder failure |
| `HF_AUTHENTICATION_FAILED`, `HF_GATED_ACCESS_DENIED` | HTTP 401 / 403 or gated access denied |
| `HF_SDK_IMPORT_FAILED` | SDK import/bootstrap failure, not a decoder error |
| `HF_SSL_FAILED`, `HF_PROXY_FAILED`, `HF_NETWORK_FAILED` | Structured transport failure |
| `HF_REVISION_NOT_FOUND`, `HF_FILE_NOT_FOUND`, `HF_DOWNLOAD_FAILED` | Pinned revision/file/download issue |
| `MODEL_ASSET_MISSING_OR_CHANGED`, `MODEL_ASSET_INVALID` | Receipt/checksum/asset issue |
| `INTERNAL_ERROR` | Unexpected implementation failure, with safe stage/class |

401/403 errors link to the model access page; credentials are not silently retried. Optional
advanced `BANDPILOT_FFMPEG_DLL_DIR` configuration is unnecessary for a discoverable existing
Conda installation. Tokens, headers, signed URLs and raw exception bodies are never printed.
HTTP/revision/file distinctions use the pinned [HF SDK error contracts](https://huggingface.co/docs/huggingface_hub/v0.36.0/package_reference/utilities#http-errors),
with transport causes checked before a wrapping local-cache-miss exception.

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
remain unverified until an operator runs the opt-in real-speech integration test. Provisioning
a new developer machine still uses the isolated project's locked Python 3.12 environment;
this repair changes no package pins, backend lockfile or production image dependencies.

Verified on the reported Windows machine: automatic discovery of its existing FFmpeg 7
installation and real Torch/TorchCodec/pyannote imports inside the isolated, network-fenced
worker, with no DLL override or Conda activation. **DOWNLOAD_UNVERIFIED**: no token/download
or real-recording inference was performed during this repair. HF access/local CPU setup is
independent of Azure/OpenAI billing; diagnostics and diarization make no paid provider calls.

Repair validation: 414 offline replay/diarization/scorer/provider/composition tests passed,
12 skipped (10 PATH-based decoder tests, one symlink-permission test, one opt-in model test).
The automatically discovered decoder was additionally exercised on a synthetic one-second WAV:
ffprobe/normalization succeeded, source SHA stayed unchanged, no provider was called.
Linux-specific DLL bypass is covered deterministically; Docker verification was unavailable
because Docker Desktop's daemon was stopped. Package pins/lockfiles were not changed.


## Persistent admin lab worker

The [Speaking Benchmark Lab](../../docs/testing/admin-speaking-benchmark.md) reuses this pinned CPU subprocess from a separate PostgreSQL worker: from `backend/`, run `uv run --locked python ../scripts/speaking_benchmark_worker.py`. It never installs this environment into FastAPI/Modal Web. The API packages a small identity-only JSON copy; a deterministic test checks it matches `model.json`. No weights or native libraries are included there. Remote workers require external PostgreSQL and shared private R2/S3 plus a persistent pre-provisioned model cache.
