# Writing task bands and TA diagnostics implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Complete the requested focused Writing band correction and prepare evidence-based TA diagnosis without changing unverified production scores.

**Architecture:** Derive an additive task_band in response DTOs with round_to_half; preserve raw means and weighted module scoring. Reuse the Task 1 benchmark runner for a DEV-only evidence-input comparison and safe resolved inference diagnostics.

**Tech Stack:** FastAPI/Pydantic/Decimal, Next.js/Zod/Vitest, pytest.

**Spec:** User request in this chat, 2026-11-03; AGENTS.md and docs/architecture.md.

## Global constraints

- Keep raw overall/task_score meanings; no database duplication or migration.
- Focused attempts keep band_score null and stay outside full-skill/Full Mock totals.
- Preserve AI advisory/human final distinction, streaming, cancellation, one-column feedback, reasoning policy and source-image reconciliation.
- No live inference, production changes, push or deployment; no expected bands in model requests.
- Existing untracked work in the original checkout stays untouched.

## Review focus

- Zero scores must survive nullable DTOs and UI.
- Old payloads need the same half-up presentation fallback.
- Missing criteria must never turn into a band of zero.
- Two-task Writing must aggregate raw means before rounding.
- DEV evidence arms must differ only in free-form evidence assessments; no labels leak into requests.

### Task 1: Add derived bands and verify persistence/DTO contracts

Files: backend/app/schemas/attempts.py, backend/app/services/attempts.py; backend/tests/test_writing_scoring.py, test_focused_attempts.py.

Interfaces: WritingTaskScore.task_band and HistoryItem.task_band are nullable additive fields; overall and task_score retain raw means.

- [x] Add failing half-up boundary, zero/missing and save/reload/history regression tests.
- [x] Run focused tests; confirm the new DTO regression fails before implementation.
- [x] Derive task_band using round_to_half at presentation only.
- [x] Verify no double rounding with raw 6.125 and 6.25 producing final 6.0.

### Task 2: Make focused review/history consistent and correct TA/TR labels

Files: frontend/src/lib/api/{exam,history}.ts, frontend/src/features/{writing/writing-review,history/attempt-history-list}.tsx, shared band helper and related tests; docs/focused-attempts.md.

Interfaces: nullable optional task_band accepted from backend; one shared half-up helper for legacy/raw values.

- [x] Add failing component/API/helper tests for 4.625 → 4.5 after save/reload/history and Task 2 TR accessibility.
- [x] Use derived band in focused score surfaces; preserve module raw summaries.
- [x] Verify 0, 9, all required ties and missing criteria.
- [x] Update the focused scoring contract documentation.

### Task 3: Investigate TA and add controlled DEV diagnostics

Files: existing Task 1 evaluation modules/CLI/tests; docs/ai-writing.md, docs/writing-benchmark-bank.md.

Interfaces: DEV-only baseline/source-ID-only evidence arms, distinct cache identities, safe per-call resolved metadata; production defaults unchanged.

- [x] Inventory accessible benchmark inputs and run artifacts without publishing private content.
- [x] Read current official descriptors; trace score, validation, persistence, SSE and UI.
- [x] Add failing isolation/privacy/runtime-metadata tests before diagnostic code.
- [x] Add the comparison through existing runner, keep live disabled without cost admission.
- [x] Document confirmed findings, untested hypotheses and required real-case evidence.

### Task 4: Verification and handoff

- [x] Run relevant backend/frontend suites, lint/typecheck and available desktop/mobile visual checks.
- [x] Review complete diff and preserve unrelated original work.
- [x] Record actual results, limitations and rollback instructions. Leave changes reviewable without pushing or deploying.


## Execution notes

- Implemented on a managed isolated worktree/branch from c1fc40f; original untracked work preserved.
- Task 1/2: DTO half-up cases and no-double-rounding verified; save/reload/history API against dedicated PostgreSQL and two browser E2Es passed. Zero/missing/9 covered.
- Task 3: user confirmed no actual TA8/AI7 case exists. Production prompts/policy unchanged; DEV experiment is plan-only and rejects all inference, even injected factories. Synthetic scorer contracts cover 4/7/8 without asserting IELTS accuracy.
- Review: independent reviewer found a factory/direct-evaluate gate bypass and malformed diagnostic status crash. Both received failing regression tests, were fixed and re-reviewed without additional P1/P2 findings.
- Ruling: no paid grading calls; no expected bands in requests; no default reasoning/prompt changes without labelled evidence.
- Ruling: generated Next dev typecheck finds the pre-existing themeInitializationScript export in unchanged frontend/src/app/layout.tsx. Preserve unrelated theme code and report the baseline limitation.

Verification: see [handoff report](../../writing-task-band-ta-verification.md); required checks ran, with the recorded baseline Next generated-type failure.

Follow-up authorization: user requested commit, push and wait for green CI. Fix Next route export and Ruff format blockers, then create a draft PR because CI only triggers on PR/main. No merge/deploy. Typecheck and 78 frontend/102 backend focused checks passed before commit.
