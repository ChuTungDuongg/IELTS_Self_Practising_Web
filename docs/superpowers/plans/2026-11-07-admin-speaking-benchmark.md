# Phase 1 implementation plan

1. Add constrained models, additive migration and strict DTOs. Verify migration upgrade/downgrade on disposable PostgreSQL.
2. Extract shared pure replay approval validator; add owner-scoped upload/storage, review/label revisions, authenticated streaming, deletion cleanup and API tests.
3. Add fenced PostgreSQL dispatcher/runner, CPU subprocess cancellation, separate local/container entrypoint and explicit remote topology guard. Test atomic claims, crash recovery and no paid/native imports.
4. Implement typed Zod client and native admin list/detail components, translations and navigation. Test upload, polling, playback, editing, revision conflict and labels.
5. Run backend/frontend regression checks, local browser workflow and available CPU smoke. Document startup, privacy, deployment limitations and Phase 2 consumption. Record actual results; do not turn unavailable live evidence into a completion claim.

No new diarization algorithm or production PyTorch dependency is planned. Existing `LocalDiarizer`, regular/exclusive timelines, role suggestions, proposal grouping, `ReplayManifest`, storage delivery and cleanup outbox are reused.

## Execution ledger — 2026-11-08

Tasks 1–5 implemented and verified within the local/offline boundaries below. These results are not a live production deployment or an accuracy benchmark on real interviews.

- Disposable PostgreSQL migration upgrade/downgrade preserved a sentinel legacy table and exercised half-band constraints. Both isolated regression databases were upgraded to the final additive schema.
- Relevant 39-file backend regression: **432 passed, 13 skipped**, 183.97 seconds. Existing Speaking replay, transcript/hybrid and Writing Benchmark suites were included. Local `.env` Azure defaults were overridden with the legacy/offline test configuration; no recognition provider was called.
- Final frontend full suite: **168 files, 1,988 passed**, 169.00 seconds. Focused Speaking/Writing page regression: **25 passed**. Tests reproduced and verified the metadata/review deadlock, delayed label-save snapshot (both pristine and edited forms), first-poll job completion and language-switch draft preservation.
- Ruff lint and format passed. `npm run build` completed successfully again after the final UI fixes with both new admin routes; TypeScript compilation and ESLint passed. The single Alembic head is `20261107_0045`.
- Browser workflow accepted a generated **840-second WAV, 26.88 MB**, retained original bytes and source duration, and reopened the persisted sample. A separate generated 60-second silence fixture with explicitly fictional timeline/question/label data exercised role assignment, candidate/Part/question confirmation, revision save, explicit approval and Overall-only unverified label persistence. It is not evidence of model accuracy or human ground truth.
- Actual pinned Community-1 CPU inference on **8 seconds of generated silence** completed in **49.893 seconds** with zero turns, revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`. A second web-queued smoke completed through the separately launched worker and durable job (one attempt). No real eligible interview was available in the private replay directory, so real speaker accuracy and 12–14-minute inference throughput remain unverified.
- Browser layouts checked at 1440, 768 and 390 pixels: one source audio element, no horizontal overflow and no displayed errors. Production-server startup was rejected by automatic command review without a detailed reason; production build succeeded, while browser evidence uses the development server. No retry of the rejected startup command was made.
- Separate CPU image/entrypoint and remote topology guard are implemented; the container image has not been built and no Modal/cloud deployment was attempted. Embedded Modal database/local assets remain explicitly incompatible with a separate remote worker.
- A fresh reviewer found three lifecycle/state issues: delayed label snapshot could remount dirty metadata, first-poll terminal jobs did not refresh review, and SIGTERM skipped native cleanup. Each was reproduced with deterministic tests and fixed. Worker shutdown and final migration checks: **3 passed**. SIGTERM now cancels once, waits for cleanup and restores the previous signal handler; worker failures still propagate.

The first whole-backend attempt used a separate `TEST_DATABASE_URL`, which conflicts with legacy classroom concurrency helpers requiring it to equal the disposable primary `DATABASE_URL`. That attempt was stopped after reproducing the helper assertion; no domain fix was made. The corrected whole-suite run uses CI's equal primary URLs plus a separate `P2_TEST_DATABASE_URL`.

The corrected full backend suite completed with **3,866 passed, 16 skipped**, 1063.98 seconds, plus two existing Starlette deprecation warnings. The separately added shutdown tests also passed (the final shutdown/migration command reported **3 passed**). Skipped cases remain outside the verified evidence; no real interview, paid recognition request or cloud deployment was substituted for them. Final full frontend suite: **1,988 passed**. The existing replay CLI `--help` still executes, and the Web image's CPU/no-native-runtime regression checks passed.

Ruling: continue in the existing shared checkout and preserve unrelated initial untracked design/agent files — the user explicitly requested inspecting and retaining current work; moving the late-stage implementation would add avoidable migration risk. A later explicit user instruction authorizes committing/pushing `main` after completion and fixing CI. Paid inference and manual deployment remain outside scope.
