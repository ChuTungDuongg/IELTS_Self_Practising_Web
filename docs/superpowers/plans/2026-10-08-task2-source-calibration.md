# Task 2 source grounding and calibration implementation plan

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Task 2 source grounding and calibration implementation plan. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/mts_writing.py).
> Đọc cùng [current module/guide](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> Execute inline using superpowers:executing-plans; preserve the current local checkout.

**Goal:** Reliable advisory Task 2 assessment with source-grounded Vietnamese feedback, calibrated bands, isolated failures, and live SSE cards.

**Architecture:** A pure splitter maps PnSm IDs to original Python character spans. The evidence interaction selects IDs; backend lookup supplies quotes. Each criterion retains its independent evidence/scoring interactions and one repair per invalid interaction. Scoring adds bounded comparative justification in the same interaction. PostgreSQL checkpoints expose completed results and failed criteria through snapshots and replayable events.

**Constraints:** User's Task 2 specification and subsequent calibration steering are authoritative. No Task 1, official score mutations, provider deployment changes, push, browser, Playwright, real inference, or unrelated suites. Keep historical DTO compatibility. v3 must invalidate v1/v2 cache fingerprints.

## Tasks

- [x] Add `essay_sources.segment_essay(essay)` and invariant tests for IDs, paragraphs, CRLF/LF, abbreviations, repeated sentences, and Unicode punctuation.
- [x] Add bounded evidence selection schemas and `resolve_evidence(selection, sources)`; replace quote matching with ID validation and exact lookup. Add resolution/repair tests.
- [x] Upgrade prompts and configured version to `mts-task2-v3`. Use current official IELTS Task 2 descriptors, holistic adjacent-band comparison and half-band interpolation. Add bounded source-backed justification summaries and structural consistency tests, with no deterministic severity gates, deductions or caps. Keep low-temperature vLLM and its 1800-token budget.
- [x] Classify safe provider finish metadata as stop/length/known terminal/other, reject length and unsupported terminals with one repair. Add mocked transport tests.
- [x] Isolate criterion provider failures, checkpoint `criterion.failed`, attempt remaining traits, and fail the run without aggregate if any trait failed. Persist failures in JSONB and expose snapshots; test with fake providers and targeted PostgreSQL integration tests.
- [x] Preserve the four-step UI; add persisted local failure states and live counts, retain immediate cards, replay, and heartbeat behavior. Test SSE continuation, reload/reconnect, terminal partial results and Vietnamese errors.
- [x] Update AI documentation; run targeted pytest/Vitest, typecheck, touched Ruff/ESLint, and diff check; review the diff and report files/status and calibration verification limits.

**Review focus:** Long unpunctuated sentences must not hit legacy quote limits; repeated text has distinct identity; old payloads remain readable; unknown finish values cannot leak text into logs; a failed trait cannot mark the run terminal while later traits are active.

**Execution notes:** User explicitly requires this current checkout; no worktree, commit or push. Follow-up correction supersedes proposed high-band heuristics: the only scoring dimensions are the four official criteria. Automated tests validate prompt and schema contracts with fake providers; they cannot establish empirical real-model calibration. PostgreSQL verification uses a temporary isolated local container rather than the unavailable configured development database.

**Final verification:** 170 focused pytest tests and 24 focused Vitest tests passed. TypeScript typecheck, touched Ruff/ESLint and `git diff --check` passed. Review found overly compressed descriptor distinctions, a mixed LR-failure/GRA-interruption timeline bug and a Band 9 comparison contradiction; each has a regression that failed before the fix and passed afterward. All review findings were addressed. The temporary PostgreSQL container was stopped. No browser, Playwright, GPU inference, Task 1 work, official score mutation, staging, commit or push.
