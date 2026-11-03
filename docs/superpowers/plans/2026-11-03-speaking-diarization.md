# Developer replay diarization

Base: `7a3fe4a` on `codex/speaking-hybrid-v1`; preserve unrelated untracked files.
The implementation initially excluded push/deploy, model download and paid provider calls.
A later user request explicitly authorized fixing the previous CI and pushing to main;
deployment, model downloads and paid provider calls remain outside the task.

- [x] Verify official Community-1 APIs, revision and compatible isolated CPU dependencies.
- [x] Add failing contracts/tests for diarization, role ambiguity, grouping and confirmation.
- [x] Implement a bounded offline subprocess adapter and explicit private model setup.
- [x] Propose source-relative responses without fabricating Parts, prompts or confidence.
- [x] Add CLI review, per-source identity/Part confirmation, small edits and final approval.
- [x] Preserve manual manifests and existing Azure cache/scorer/production flows.
- [x] Run deterministic regression, add opt-in real-speech integration contract and document limits.

Design: Community-1 regular AND exclusive timelines; per-file speaker identities; heuristic
role suggestions remain pending. A separate private proposal/review sidecar carries unknown
Parts/prompts and boundary/overlap flags. Only an explicit final approval can emit a strict
ReplayManifest. Known other-speaker overlap blocks grading selection. Human confirmation
of identity does not approve individual intervals. No diarization inference claims from tones.

Keep Torch/pyannote and its lockfile in `tools/speaking_diarization`, never backend/Modal
dependencies. Parent verifies private paths and immutable source hashes; a child runs with
offline/telemetry disabled/network blocked, bounded threads/RSS/time, and cleans up before
temporary files disappear. Setup alone can download the pinned gated model using private HF
credentials. Cache excludes prompts/labels. Existing grading and cost guards remain binding.

Self-review: exclusive timelines do not erase regular overlaps; known other-speaker overlap
cannot be acknowledged away. Unknown roles/Parts/questions never become verified automatically.
Confirmation is per file; final approval explicitly confirms the same candidate across files.
Audio/model changes invalidate operator state with an archive. Final manifests bind source SHA;
manual manifests without receipts remain supported. All model/package setup is opt-in.

Real model inference/accuracy, CPU latency/RSS on speech and paid provider behavior are
MODEL_UNVERIFIED / LIVE_UNVERIFIED: no weights or legally usable two-speaker speech were
available for authorized execution. Synthetic fixtures test plumbing only.

Validation: 358 passed / 12 skipped in isolated Windows offline regression; Docker CPU with
network disabled 81 passed / 1 real-model skip / 1 Git-dependent deselection. Ruff check and
format (562 files), optional uv lock check (90 packages) and git diff whitespace check passed.
Local Chromium playback seek/end-stop/no-autoplay/zero-network/mobile layout passed with a
clearly synthetic demo. No paid calls, database writes, model weights, push or deployment.
Broader DB-worker fixtures could not connect to a test PostgreSQL; no DB integration claim.
The documented root PowerShell contracts/replay command also passed (71 passed, 12 skipped)
with personal dotenv untouched. Configured-secret scan of all task files passed without
printing values. The backend dotenv/private fixtures/model weights remain gitignored.

Subsequent CI follow-up: the previous main run had 31 backend failures after Modal startup
tests leaked their hybrid profile/provider through `os.environ`. The Modal test harness now
isolates the environment and `sys.path`, with a regression test for restoring both.
The relevant Modal and Speaking regression groups were then rerun against two separately
migrated disposable PostgreSQL databases: 248 passed, including the previously failing paths.
