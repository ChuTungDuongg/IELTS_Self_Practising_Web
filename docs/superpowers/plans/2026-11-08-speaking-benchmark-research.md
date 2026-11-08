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
