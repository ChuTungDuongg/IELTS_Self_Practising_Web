# Speaking audio replay implementation

Audit: remote main `6631ea4` is a merge of local `de3271b`; their committed trees
are identical. Work on current branch `codex/speaking-hybrid-v1`, preserving the
existing uncommitted configuration/billing follow-up. No database, push or deployment.

- [x] Add failing contracts for optional truth, source boundaries, segmentation and live guards.
- [x] Reuse bounded FFmpeg normalization for MP3/WAV windows and immutable source mapping.
- [x] Add separate speech/score checkpoints, including durable unknown-billing fences.
- [x] Wire Azure-only smoke and full production features/scorer, never synthetic human labels.
- [x] Generate privacy-safe reports and operator prepare/validate/live/resume documentation.
- [x] Run synthetic audio integration and offline regression; record LIVE_UNVERIFIED.

Full grading requires verified candidate-only answer windows, one candidate, Parts
1/2/3 and real question context. Unsegmented short smoke never produces IELTS bands.
Labels remain outside inference. Estimated budget acceptance is explicit, not an invoice cap.

Verification on this working tree:
- Targeted replay/benchmark/production evidence/scorer/Azure contracts: 328 passed, 9 skipped
  on Windows (8 FFmpeg integrations and one symlink-permission test).
- Local/Modal ASR, provider-aware composition/launcher and Writing regressions: 209 passed.
- Debian CPU container with FFmpeg, `--network none`, no mounted credentials: 42 replay
  tests passed; the Git executable check was deselected and passed separately on the host.
- Actual CLI prepare -> validate on a synthetic three-second WAV generated all five public
  reports with zero provider calls and no bands; source stayed outside tracked fixtures.
- Ruff lint and format passed for all backend app/tests and scripts (547 formatted files);
  `git diff --check` passed. No live provider call, database mutation, push or deployment.

Review: complete speech survives Luna failure/prompt changes; partial/timeout/cancelled/quota
requests cannot be automatically resubmitted. Scores checkpoint before feedback, and missing
temporal FC or PR prevents overall. Unknown confidence/prosody remains unknown. Summary files
exclude transcript/question/source paths/credentials; private checkpoints are clearly named.
No benchmark labels are relaxed or passed to inference. LIVE_UNVERIFIED remains in fake runs.
