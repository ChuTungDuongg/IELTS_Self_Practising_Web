# Windows diarization setup repair

Base bfc89ef; preserve unrelated untracked assets. Initial repair excluded commit/push/deploy;
the subsequent user request authorizes commit, push to main and CI repair. No deployment.

- [x] Reproduce restricted-child errors without credentials or model downloads.
- [x] Add safe stage/domain diagnostics, then Windows shared-FFmpeg discovery and DLL lifetime tests.
- [x] Preserve Windows SYSTEMROOT and a narrow path-only discovery allowlist.
- [x] Separate token-free native/storage preflight from pinned HF setup and offline inference.
- [x] Make verified setup idempotent, add CLI diagnose, update one-command instructions.
- [x] Run real isolated native preflight and offline replay/regression tests; report download/inference limits.

Observed before changes: restricted child imports huggingface_hub successfully but Torch raises
OSError winerror 10106. SYSTEMROOT and the explicit FFmpeg override are absent from the child.
The existing worker collapses import, filesystem and other OSError failures into one dependency
code; setup prompts for a token before checking deterministic local failures.

Confirmed exact setup root cause: importing `snapshot_download` from the lazy HF SDK raises
OSError 10106 with the old environment; restoring SYSTEMROOT makes it succeed. A local socket
probe independently reproduces the same difference without connecting to any server.

Actual isolated worker preflight: Python 3.12/pinned packages, Torch/TorchCodec/pyannote imports
and FFmpeg shared major 7 pass with network blocked, no explicit DLL override or activated
Conda prefix. Automatic discovery matches the existing installation. Discovered ffmpeg/ffprobe
also normalize a synthetic one-second WAV correctly and preserve its SHA.

Final regression: 414 passed / 12 environment/opt-in skips. Ruff/format and uv lock check pass.
Docker Desktop daemon was off, so Linux is covered by deterministic Windows-API bypass tests,
not a new native Linux claim. DOWNLOAD_UNVERIFIED / MODEL_UNVERIFIED: no weights downloaded,
private recording processed, paid provider call, commit, push or deployment in this repair.
After the final HF-SDK import preflight change, 47 focused bootstrap/backend/CLI tests pass;
the normal --diagnose-diarization CLI again passes real isolated imports and reports
NOT_INSTALLED without requesting a token. Ruff checks 564 Python files and uv resolves the
unchanged 90-package tool lock. A separate real decoder probe confirms automatic ffprobe/WAV
normalization; no global PATH, registry or Conda environment was modified.
