# Phase 3 implementation plan

1. Inspect P1/P2 approval, ledger, worker, providers, metrics, storage and UI.
2. Add append-only reference and frozen experiment/variant/observation tables in
   additive migration 0047. Test only on disposable PostgreSQL.
3. Implement reference validation/history/verification APIs; never inference input.
4. Implement frozen cohort/provider identities, static preflight, consent and APIs.
5. Share ASR metric/alignment logic; add explicit v2 normalization, denominators,
   paired cluster statistics, band comparisons and safe CSV/JSON exports.
6. Implement independently leased ASR research worker, durable physical attempts,
   exact cache reuse, interruption/reconciliation, cancellation and deletion fencing.
7. Schedule P2 paired variants sequentially without changing scorer contracts.
8. Build typed Zod clients, reference editor, research list/setup/results/comparison
   UI using existing tokens and bilingual messages. Preserve P1/P2 controls.
9. Add synthetic/fake-provider regression tests: ownership, immutability, billing,
   restart, concurrency, source binding, metrics and end-to-end persistence.
10. Run migrations on disposable DBs, focused/regression tests, lint/type/build;
    inspect UI at desktop/mobile, review defects, record actual results and limits.

Steps 1–10 are implemented. Verification results and remaining live limitations are
recorded in [the testing guide](../../testing/admin-speaking-benchmark-research.md).
The shared production scorer, existing ASR adapters, replay metrics and P1 approval
remain authoritative; no new scoring engine or production GPU dependency was added.

No production migrations, model downloads, paid calls or deployment were performed.
The user subsequently authorized committing/pushing main and fixing CI failures;
that authorization does not authorize paid inference or production migration/deployment.

## Follow-up verification plan (current request, no commit/push authorization)

Baseline: `00e295f`. Existing implementation is preserved. Execute inline with
systematic debugging, failing regression tests, and verification before completion.

- [x] Fetch main, inspect P1/P2/P3 and run baseline metrics/frontend/P3 database tests.
- [x] Add regression tests for unlinked paired evidence, nonbillable reuse receipts,
  uncertain P2 accounting and atomic cancellation. Test on separate disposable PG.
- [x] Persist P2 cache receipts in `RequestLedger.cached`; scope report checkpoints
  to linked runs; retain missing evidence and count physical requests separately.
- [x] Fence linked P2 cancellation inside the research cancellation transaction.
- [x] Validate annotations against the same NFC token stream used for metrics.
- [x] Review reference editor uncertainty preservation and loading transitions.
- [x] Run focused P1/P2/P3 and replay regressions, frontend checks and Alembic round
  trip; independent code review; record actual counts and live limitations.

Review findings resolved: cache receipts cannot reconcile physical unknowns;
P2 recovery preserves research attribution; bootstrap candidate order is stable;
provider disagreement uses declared NFC normalization. Editor corrections retain
uncertainty spans/types, guard history loading/response switching and preserve
unsaved text during locale changes. No migration was added: existing `reused_from`
checkpoint support is sufficient. No historical prediction/reference is rewritten.

Verification exposed an existing Windows decoder issue when the installed FFmpeg
directory was added to PATH: `shutil.which` returns an uppercase `.EXE` suffix.
The replay probe now casefolds that suffix before locating `ffprobe.exe`, backed by
a deterministic failure/recovery test and real synthetic decode tests. No decoder
download or production provider behavior changed.

Final verification: 280 backend tests passed, 1 Windows symlink-permission skip
(142.17 s); 2,009 frontend tests passed across 170 files (161.11 s); focused frontend
38 passed; actual WAV/MP3 and executable-discovery tests 11 passed. TypeScript,
ESLint, Ruff lint/format, production build and disposable 0047→0046→0047 migration
round trip passed. Independent review found no unresolved issue in the fixes.
Full backend and browser visual QA were not rerun. Live accuracy remains unverified.
The task's disposable PostgreSQL container is removed after verification.

Subsequent operator instruction: commit, push main and fix CI. This authorizes
integrating these audited changes and CI repairs; paid inference, deployment and
production migrations remain unauthorized. CI results are reported for the exact
pushed commit, separately from the offline audit above.
