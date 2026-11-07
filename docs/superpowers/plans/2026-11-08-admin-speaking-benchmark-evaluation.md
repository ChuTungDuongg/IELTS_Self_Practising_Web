# Admin Speaking Benchmark Lab Phase 2 implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` for inline implementation and one fresh final code review. Checkboxes track independently testable deliverables. No commits, pushes, deployments or live paid requests are authorized for this phase.

**Goal:** Grade explicit P1 approved candidate windows with the production Speaking stack, durably preserve paid-call attempts/predictions, and compare/export owner-scoped human-vs-AI evidence.

**Architecture:** Extend P1 with grading runs and per-call checkpoints. A separate CPU worker reuses production normalization, Azure/lexical providers, VAD, evidence/scorer and metrics. Human labels enter only comparison/report queries.

**Tech stack:** Existing FastAPI/SQLAlchemy/PostgreSQL/Alembic, AssetStorage, Next.js/React/Zod/i18n; existing optional Azure/ONNX/OpenAI transports. Native SVG charts; no additional charting, queue or model framework.

**Spec:** `docs/superpowers/specs/2026-11-08-admin-speaking-benchmark-evaluation-design.md`; original user Phase 2 request.

## Global constraints

- Preserve P1, learner grades, production scoring prompts and existing interrupted-request protections.
- Only an explicitly selected frozen approved revision can authorize candidate audio.
- No provider request from imports, migrations, page load, preflight or unauthorised submission.
- Commit ATTEMPTED before each potentially billable physical request, including internal OpenAI repair POSTs.
- Unknown billing is never free and never automatically retried.
- Human scores/notes do not enter provider contexts, evidence, model selection or prediction identity.
- Missing criteria never produce band zero or an invented Overall.
- No actual deployment/paid inference/commit/push; preserve initial unrelated untracked files.

## Review focus

1. Crash between HTTP POST completion and DB result persistence must block automatic replay.
2. Internal OpenAI budget/schema repairs must each receive a durable attempt before POST.
3. Sample deletion between stages must fence new calls and later purge private derived artifacts safely.
4. Changes to human labels or Luna prompts must not resubmit completed acoustic analysis.
5. Multiple runs/configurations and unverified labels must not bias denominators or double-count candidates.

## Task 1 — constrained persistence, ownership and lifecycle

**Files:** create `backend/app/models/speaking_benchmark_grading.py`, `backend/app/schemas/speaking_benchmark_grading.py`, `backend/app/repositories/speaking_benchmark_grading.py`, additive migration after 0045; modify model exports, P1 owned/deletion/cleanup as narrowly required.

**Interfaces:** owner-scoped `owned_run(session, owner_id, sample_id, run_id, lock=False)`; typed run/checkpoint/status schemas; immutable finalized prediction and completed attempt contracts. Repository never constructs a provider.

- [ ] Write failing tests for owner/review/source FK binding, duplicate submission, status/band bounds, append-only attempts and finalized prediction mutation rejection.
- [ ] Implement two tables and deletion-pending support with constrained identities/revisions and indexes; keep samples private immediately during deferred deletion.
- [ ] Run new model/repository tests; run migration upgrade/downgrade in an isolated schema preserving legacy rows.
- [ ] Verify P1 upload/review/labels/delete regressions.

## Task 2 — source-bound production evidence adapter

**Files:** create `backend/app/services/speaking_benchmark_audio.py` and `speaking_benchmark_evidence.py`; extract a small pure projection helper from replay only where duplication would otherwise occur. Preserve replay CLI validation/receipts.

**Interfaces:** `load_approved_input(...)` returns an inference-safe manifest/source binding without human-label fields; `materialize_approved_audio(...)` privately normalizes exact candidate windows; response-evidence construction uses `build_feature_bundle` and `build_attempt_evidence`.

- [ ] Tests reject draft/unapproved/stale/hash-changed/wrong-source/overlapping/examiner windows and accept explicitly selected historical approved revisions with a warning.
- [ ] Assert normalized duration and source-relative timeline for multiple Parts, and that a spy analyzer receives only approved windows.
- [ ] Assert independent lexical GRA/LR/FC and PA PR provenance; preserve awkward grammar/fillers, missing PR and unavailable Overall through existing scorer rules.
- [ ] Run relevant replay/segment review/hybrid feature/scorer regression tests.

## Task 3 — static readiness, preflight and consent

**Files:** create `backend/app/services/speaking_benchmark_preflight.py`; extend safe config/env examples and typed DTOs. Add grading availability/preflight endpoints in a focused router.

**Interfaces:** safe `grading_availability(settings)`; source/config-bound `preflight(...)`; submission consent includes exact revision/config, disclosure booleans, all selected provider estimates, maximum estimate and idempotency key.

- [ ] Tests prove readiness/preflight make zero network/inference calls, reject unknown billing/configuration/topology and incomplete consent, and validate all-window/provider budgets.
- [ ] Derive typical/max OpenAI physical-request counts from production repair policy with fake HTTP responses; do not hard-code an undercount of nominal score/feedback calls.
- [ ] Support baseline PA, optional STT, and explicitly configured local/Modal Whisper without fallback or startup/provisioning.
- [ ] Submission validates preflight identity and enqueues only; changed source/configuration requires a new preflight.

## Task 4 — durable physical-request ledger and score checkpoints

**Files:** create `backend/app/services/speaking_benchmark_ledger.py`, `speaking_benchmark_providers.py`, `speaking_benchmark_scoring.py`; narrow optional provider factory/transport extension only if necessary.

**Interfaces:** `begin_attempt(...)`, `complete_attempt(...)`, `interrupt_attempt(...)` use short fenced transactions; ledger-backed Azure/lexical analyzer and OpenAI transport adapters reuse normalized completed results. Existing scorer score-first callback persists parsed scores before feedback.

- [ ] Tests cover real production OpenAI known-length repair and schema repair with a fake transport; every POST observes a previously committed ATTEMPTED row.
- [ ] Test timeout, cancellation, result-save failure and crash leave billing unknown and prevent another POST after restart.
- [ ] Test safe completed PA/lexical/score reuse, prompt-only invalidation, no duplicate requests, and feedback failure preserving a valid score.
- [ ] Test human label/notes changes do not change inference identity or appear in messages/evidence/provider context.
- [ ] Test immutable completed-attempt results and exact-stage renewed retry preserving old attempts.

## Task 5 — separate grading worker and recovery

**Files:** create `backend/app/services/speaking_benchmark_grading_worker.py`, `scripts/speaking_benchmark_grading_worker.py`, separate CPU Dockerfile; keep P1 worker intact.

**Interfaces:** `GradingJobRunner.claim/heartbeat/run_once`; token-checked stages; same-source/config checks; sample deletion/cancellation gate before each new attempt. SIGTERM awaits cleanup. No DB transaction remains open during provider awaits.

- [ ] Test independent PostgreSQL claim concurrency, expired lease before/after attempted calls, stale completion fencing, process cancellation, and one-run-per-worker execution.
- [ ] Test deleted/deletion-pending samples cannot start new calls; uncertain in-flight outcomes stay accounted and private artifacts eventually purge retryably.
- [ ] Test explicit interrupted-stage reconciliation/consent and no automatic uncertain retry.
- [ ] Test configured remote external-DB/shared-storage topology and explicit embedded-mode rejection; no Web Torch/GPU dependency.

## Task 6 — owner-scoped API and offline vertical slice

**Files:** focused grading router, typed schemas and API registration; new `backend/tests/test_admin_speaking_benchmark_grading*.py` fixtures.

**Endpoints:** grading availability; sample grading preflight; run create/list/detail/cancel/retry-interrupted/comparison, following the user's supplied route prefix.

- [ ] Test non-admin/cross-owner access for every endpoint, bounded pagination and no client-supplied prediction/evidence acceptance.
- [ ] Exercise approved synthetic audio → committed consent/run → separate fake-provider worker → persisted predictions/usage → reopening. Use production scorer/evidence with independent fixture human labels loaded only after inference.
- [ ] Confirm partial availability/feedback states and missing Overall are truthful; no raw payload/private keys in DTOs.

## Task 7 — comparison, metrics and exports

**Files:** create `backend/app/repositories/speaking_benchmark_reports.py`, `backend/app/services/speaking_benchmark_reports.py`, focused report schemas/routes and tests.

**Interfaces:** explicit label revision selection; default latest verified label; versioned latest-finalized-run-per-sample selection for one configuration; shared rows/metrics for summary, paginated samples, CSV and JSON.

- [ ] Tests for literal MAE/RMSE/bias/agreement values, missing predictions, insufficient/constant-vector correlations/QWK and zero-sample null statuses using existing `score_metrics`.
- [ ] Tests for DEV/HOLDOUT/config/version/date/status filters, all eligible labelled denominator rows, duplicate-run suppression and speaker-leakage warnings.
- [ ] Tests for post-label-edit recomputation without provider construction or request, explicit historical label selection and default exclusion of unverified labels.
- [ ] Tests for UTF-8/formula-safe CSV, schema-versioned JSON, owner isolation, all forbidden fields absent and no silent truncation when report limits are exceeded.

## Task 8 — sample AI Evaluation UI

**Files:** typed `frontend/src/lib/api/speaking-benchmark-grading.ts`, focused components under `features/speaking-benchmark/evaluation/`, sample-detail integration and EN/VI strings.

- [ ] Tests for explicit approved revision/provider selection, static readiness/budget blockers, disclosure consent and idempotent run submission.
- [ ] Tests for polling, cancellation/recovery, partial/failed/unknown billing states, historical run/label selection, comparison and preserving dirty P1 forms.
- [ ] Render score/feedback/evidence-reference DTOs only; route timestamps through the existing single source audio player.
- [ ] Use existing tokens/components with Taste and UI/UX Pro Max accessibility/responsive checks; no new chart dependency.

## Task 9 — report dashboard UI

**Files:** `/admin/speaking-benchmark/reports/page.tsx`, typed report client and focused report/filter/chart/table/export components plus translations/tests.

- [ ] Tests for admin route, filters/config selection, missing-data/null metric presentation, distinct human/AI legend, sample outliers and export links respecting active filters.
- [ ] Accessible compact SVG charts/table equivalents: criterion errors, band distribution, human-vs-AI scatter and signed errors; genuine summary counts and split coverage.
- [ ] Verify keyboard controls, bounded chart points, pagination, responsive widths and explicit insufficiency/leakage warnings.

## Task 10 — documentation, regression and delivery

**Files:** new `docs/testing/admin-speaking-benchmark-evaluation.md`; update P1/replay/AI Speaking/transcription/Modal/architecture/index docs and this ledger.

- [ ] Document exact local worker/web setup, optional dependencies/VAD setup, safe static readiness, identities, ledger/recovery/deletion, report selection/metric/export protocol and remote topology.
- [ ] Document a first real-evaluation procedure requiring separate explicit authorization; provide no invented live prices, sample counts or accuracy.
- [ ] Run focused tests as each unit lands, additive migrations on disposable PostgreSQL, full backend/frontend suites, lint/typecheck/build and available browser workflow with fake providers/synthetic audio.
- [ ] Fresh final code review; fix reproducible lifecycle/privacy/billing defects with regression tests. Report actual results and unverified live/cloud limits. Do not commit/push/deploy without new authorization for this phase.

## Execution status

- [x] Read user request and inspect current HEAD/working tree/P1, replay/scorer/metrics/provider boundaries.
- [x] Record a concrete design and implementation plan.
- [x] Fresh builder check of this design: no important unanswered implementation choice found.
- [x] Required skill design/plan approval before product-code implementation (explicit user approval, 2026-11-08).

Implementation approved; progress and verification are recorded in the plan-scoped execution ledger.
