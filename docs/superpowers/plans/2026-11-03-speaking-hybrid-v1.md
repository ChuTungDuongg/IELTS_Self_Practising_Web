# Speaking hybrid v1 — design and implementation checklist

**Goal:** opt-in Azure unscripted speech evidence + CPU timeline/VAD + existing holistic,
score-first Luna rubric scoring and private, replayable feedback.

**Authority:** user implementation specification, AGENTS.md, architecture.md, and the binding
2026-10-11 Speaking design, plan and self-review amendments. Baseline/HEAD: 3cf5c9a.

**Architecture:** one explicit speech-analysis result per continuous segment; reuse its lexical
transcript, absolute millisecond timings and pronunciation observations. Persist the result in
existing private transcript JSONB checkpoints (no new storage service). Normalize without trimming;
retain segment mappings and unknown recovery gaps. Speech cache identity is independent of scorer
prompt identity. Legacy local/Modal providers and historical rows remain readable.

**Decisions:** en-US technical default, optional prosody; unknown capabilities remain unknown.
No reference text; no completeness/read-aloud penalties. Missing VAD/assets/evidence reduces
eligibility, never fabricates a score. Raw provider scores never map numerically to IELTS.
No live requests/benchmarks, deployment, provider switch or push as part of implementation.
Work in the existing checkout on codex/speaking-hybrid-v1; preserve unrelated untracked files.

## P1 — contract, Azure, timeline

- [x] Failing offline tests: final-only continuous events, offsets, missing fields, errors,
  partial streams, cancellation, sharing, and configuration with no reference.
- [x] Versioned neutral analysis schema, optional pinned SDK, bounded native execution.
- [x] Segment/take mapping persisted through normalization; no recovery-gap silence inference.
- [x] Shared coordinator wired into durable transcript checkpoints; cache/provider identity.

## P2 — fluency, eligibility, scorer

- [x] Failing tests: VAD windows, leading/preparation silence, gap boundaries, unknown fillers,
  lexical preservation, eligibility, criterion isolation and version projection.
- [x] Pinned CPU ONNX VAD with controlled setup and checksum, no request-time downloads.
- [x] VAD-based fluency spans/runs, heuristic lexical events, explicit coverage/limitations.
- [x] Attempt-level PR/FC eligibility, score-first behavior, four-criterion overall unchanged.
- [x] Validate feedback IDs and resolve private playback spans server-side.

## P3 — UI, evaluation, deployment, documentation

- [x] Extend existing review with accessible localized replay controls and bounded playback.
- [x] Evaluation: speaker-disjoint splits, fidelity/timing/false positives, band metrics,
  latency/calls/usage/repeat stability; live opt-in with limits only.
- [x] CPU Modal preset and config/readiness; legacy GPU deploy remains selectable.
- [x] Update current docs/config examples, privacy, cost assumptions, rollback and test evidence.
- [x] Run relevant offline/regression tests, typecheck/lint and browser visual verification.
- [x] Review integrated diff; document LIVE_UNVERIFIED and any environment limitations.

## Execution ledger

- Repository inspected: HEAD equals supplied baseline; only unrelated untracked files initially.
- User supplied the architecture and explicitly waived architecture clarification; proceed with it.
- Parallel work uses non-overlapping ownership for Azure adapter, review UI and evaluation/deploy;
  orchestration, normalization, fluency and scorer integration remain with the primary implementer.
- Review fixes: use exact frames at recovery joins; preserve billing ledger on derivative repair;
  stratify/bound PR payload while retaining full private evidence and coverage; no-match regions
  remain partial; CLI resume never blindly resends potentially billed audio.
- Final regression selection: 742 backend tests passed in 426.50s on dedicated PostgreSQL;
  150 frontend Speaking tests passed. Focused tests passed again for final projection/feedback changes.
- Actual CPU native + FastAPI lifecycle Docker probes and pinned ONNX runtime passed with zero
  provider calls; browser keyboard replay/mobile EN/VI light/dark QA performed.
- Source TypeScript/lint/lock/diff checks passed. Full generated Next typecheck retains the existing
  classroom `teacher` prop TS2344 error; no unrelated classroom fix attempted.
- Live Azure/Luna accuracy/cost benchmark and cloud Modal runtime remain unverified, as documented
  in [handoff](../2026-11-03-speaking-hybrid-handoff.md). No commit, push or deployment.

## Authorized delivery follow-up

- User subsequently authorized commit/push and CI fixes, with Azure credentials supplied later.
- [x] Add failing launcher tests, then forward hybrid Azure config/pinned VAD and full Luna policy.
- [x] Preserve legacy defaults; configure only the ignored local staging file for CPU hybrid.
- [x] Fix the classroom page's Next.js prop contract and use the repository's Ruff format policy.
- [ ] Commit/push the scoped implementation and verify GitHub CI; fix any failures.
- Azure/Luna live assessment and Modal cloud deployment remain unverified; no cloud deployment requested.
