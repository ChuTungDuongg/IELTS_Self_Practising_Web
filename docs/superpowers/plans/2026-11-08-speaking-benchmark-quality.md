# Speaking Benchmark P4 implementation plan

> Execute the supplied design in this session. Use focused parallel domain workers,
> TDD, systematic debugging and verification before completion. No P4 commit/push,
> live inference or deployment without separate authorization.

**Goal:** Human-reviewed questions, independent ratings/adjudication, reproducible QA
and frozen regression gates over persisted P1-P3 evidence.

**Architecture:** Existing modular monolith, additive PostgreSQL 0048, private AssetStorage,
question CPU consumer and read-only statistical projections. Default P2/P3 labels unchanged.

**Spec:** `docs/superpowers/specs/2026-11-08-speaking-benchmark-quality-design.md`.

## Global constraints

- Use `b62bbee` baseline; stop CI monitoring per latest operator instruction.
- Raw audio stays private in AssetStorage. Human/reference data is evaluation-only.
- Examiner regular-turn overlaps are rejected; no acoustic separation claims.
- Freeze all source/review/provider/label/reference/metric identities.
- Blind assignments do not relax owner-only dataset APIs.
- No automatic inference, scoring changes, averaging-as-consensus or promotion.
- Every paid request persists ATTEMPTED before submission; unknowns need reconciliation.
- Do not stage unrelated user files. Keep P4 uncommitted.

## Review focus

- Overlap hidden by exclusive diarization: extraction must inspect regular turns.
- Rater user impersonation/revocation: scoped audio/DTO queries must enforce grants.
- Legacy labels lack source identity: strict gate cannot pretend otherwise.
- Missing/unpaired evidence: quality failures and coverage prevent false PASS.
- Historical selection changes: only a new immutable report may use new annotations.

## Ownership and interfaces

Questions domain owns `models/speaking_benchmark_questions.py`,
`schemas/speaking_benchmark_questions.py`, `services/speaking_benchmark_questions*.py`,
`api/v1/speaking_benchmark_questions.py`, question CLI worker and question tests.
Exports `router`; model classes `SpeakingBenchmarkQuestionJob/Request`;
`cancel_question_jobs(session,sample_id)`; no P1/P2/P3 file edits without coordination.

Human domain owns `models/speaking_benchmark_human.py`, `schemas/speaking_benchmark_human.py`,
`services/speaking_benchmark_human*.py`, `api/v1/speaking_benchmark_human.py`, human tests.
Exports `router`; `SpeakingBenchmarkRater/RaterAssignment/HumanAssessment/Adjudication`;
`resolve_human_label(session,owner_id,sample_id,review_revision,selection)` (caller transaction),
returning JSON `{kind,id,revision,bands,eligible,provenance,binding_status}`;
`resolve_label_id` must enforce owner and approved source binding. No default report edits.

Quality/gates domain (root) owns `models/speaking_benchmark_quality.py`, corresponding
schemas/API, `services/speaking_benchmark_quality*.py`, suite/gate services/tests and CLI.
Root integrates model/router/config/0048 migration, P1 deletion and P2/P3 explicit
label-policy overrides. Frontend worker owns new typed quality client, focused UI,
route pages/translations/tests; sample/research integration is coordinated with root.

### Task 1 — design and baseline

- [x] Read P4 and current P1-P3/auth/storage/provider contracts; record baseline.
- [x] Write design and plan; obtain independent builder recon, settle minor decisions.

### Task 2 — Question Assistant

- [ ] Failing tests: examiner confirmation/regular overlap/source/Part bindings and chronology.
- [ ] Implement typed job/request models, deterministic proposals and static preflight.
- [ ] Implement durable fenced ASR worker/cache/reconciliation/cancellation/deletion guards.
- [ ] Implement owner routes and append-only accepted/rejected decisions creating P1 drafts.
- [ ] Fake ASR integration proves no auto approval/inference on page/preflight and unknown recovery.

### Task 3 — Human raters and adjudication

- [ ] Failing tests: scoped blind DTO/audio, identity impersonation, revision conflicts, invalid bands.
- [ ] Implement immutable source-bound assessments, assignments/revocation and external provenance.
- [ ] Implement explicit adjudication and independent pairwise agreement using existing metrics.
- [ ] Implement label resolver and verify legacy labels/default selection remain untouched.

### Task 4 — Persistence integration

- [ ] Register models/routers/settings and freeze additive 0048 DDL/guards after actual head.
- [ ] Migration roundtrip on throwaway PostgreSQL; FK/immutability/source/owner tests.
- [ ] Fence question jobs and revoke assignment access on deletion without breaking media cleanup.
- [ ] Add opt-in P2/P3 label projection policies with no inference/fingerprint mutation.

### Task 5 — QA and frozen suites

- [ ] Failing tests: missing vs corrupted source, uncertain labels/refs, leakage, incomplete evidence.
- [ ] Implement read-only typed QA issues/protocol/eligibility and immutable snapshots.
- [ ] Freeze suite revisions/cohorts/exact label/reference selections and holdout audit/consent.
- [ ] Verify historical snapshots reproduce after later human edits or deleted source.

### Task 6 — Regression gates and reports

- [ ] Failing tests: invalid identities, missing evidence, duplicate candidate clusters and QA precedence.
- [ ] Resolve persisted P2/P3 artifacts against frozen suite selections only.
- [ ] Calculate paired metrics/bootstrap via existing functions and versioned thresholds.
- [ ] Persist immutable PASS/FAIL/INCONCLUSIVE/INVALID reports; exports and saved-JSON offline CLI.
- [ ] Prove recomputation cannot construct a paid provider or deploy/change prompts.

### Task 7 — Native UI

- [ ] Typed Zod client for questions, human ratings, QA/suites/gates/reports and scoped reviewer APIs.
- [ ] Focused Question Assistant, blind form, rater assignment and adjudication components.
- [ ] QA/suite/gate pages, baseline/candidate selection, report history and filtered exports.
- [ ] Sample/research links, shared playback, dirty protection, i18n/accessibility/mobile behavior.
- [ ] Deterministic frontend workflow/error/revision-conflict tests.

### Task 8 — Verification and delivery

- [ ] Focused P4 and P1-P3 regressions, full backend on separate disposable databases.
- [ ] Full frontend, TypeScript, ESLint, Ruff lint/format, build and Alembic roundtrip.
- [ ] Available offline browser flow; final independent review and fixes.
- [ ] Canonical P4 operations guide and required documentation/index updates.
- [ ] Record first full-suite result separately from reruns, exact counts and remaining live limits.


## Review and integration checkpoint — 2026-11-08

The user has now authorized review, fixes, commit/push to main and CI repair.
The earlier no-push instruction above describes the initial development phase.
Implementation is present for Tasks 2–7; checkboxes are retained as the original
acceptance checklist, not a blanket completion claim. Review corrections and
verification limits are recorded in the P4 operations guide. Local focused
P4 began with 51 passes; additional evidence/paired-cohort/real UI contract tests
were added during review. Full-suite results and CI must be checked for the exact
integrated commit before claiming delivery complete. No live inference or
production deployment is authorized by this checkpoint.
