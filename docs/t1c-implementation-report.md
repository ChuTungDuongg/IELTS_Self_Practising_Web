# T1-C implementation and verification record

Implemented natively in the authoritative Windows checkout, on local branch `codex/t1c-hybrid-tacs`. Starting local HEAD and read-only remote-main reference matched `a4c3f3c245495d33d79f6bf6c25e0b0778492874`. Existing Writing changes were retained. No push, deployment or main-branch merge was performed.

## Delivered behavior

- Alembic 0021: versioned human anchor sets and four-label anchors, initially empty. PostgreSQL frozen-content triggers, transactional activation/retirement, clone-to-draft and serialized concurrent editing are covered by actual database tests. Frozen published/previously-published archived task identity remains authoritative.
- Admin-only API and `/admin/writing-anchors`: searchable frozen task picker, original paragraphs, TA/TR/CC/LR/GRA labels, private note/provenance, draft CRUD, read-only frozen detail, clone/activation, filters/pagination and coverage. Production Task 1 CC/LR/GRA readiness is separate from exact-task TA and Task 2 research labels. Sparse recommendations are informational.
- Grounded Direct TA retains primary vision, optional fail-open DePlot, reconciliation, facts and claims. CC/LR/GRA use independent trees or Direct fallback. Each visited node selects one stable representative and makes exactly two swapped comparisons; consensus is exact, comparisons have no repair, and default search stops at two nodes. Adjacent supported bounds reconstruct Decimal half-bands; unsupported outer ranges do not clamp.
- Successful deterministic scores survive the separate single feedback synthesis boundary. Failed/invalid synthesis leaves score, mode and tree diagnostics intact, with null/omitted feedback, empty lists and explicit UNAVAILABLE status. No fabricated feedback, rescore or Direct replacement occurs. Four valid scores can still produce a COMPLETED aggregate. Frontend copy preserves existing human comments for unavailable AI feedback.
- Alembic 0022: pinned execution/anchor FK and private diagnostic JSONB. Queued runs retain the old frozen version or explicit no-bank decision after activation. Public DTOs/SSE expose safe stages and results, without bank content, labels, IDs, pivots or preferences. Legacy runs remain readable; Task 2 stays MTS v7.
- Existing T1-C benchmark extended to A0 Direct, A1 MTS, A2 independent full Direct N=3 median, and A3 exact Hybrid; A4 remains future work. Private manifest/read-only ACTIVE PostgreSQL sources, source digest/cache versioning, split-wide ID/normalized-essay leakage rejection and architecture costs are implemented. Target labels/truth/provenance never enter model inputs. TA accuracy is retained and excluded from language-tree/fallback denominators.

## Documentation audit

| Artifact | Classification | Action |
| --- | --- | --- |
| README, `docs/ai-writing.md`, `docs/modal-web.md` | CURRENT | Updated Hybrid default/config/admin/run contract; Task 2 remains MTS |
| `docs/lces_adapt.md` | CURRENT | Added all 27 approved sections, architecture, reliability, budget and conservative interview/CV language |
| `benchmarks/writing_task1/README.md` | CURRENT | Added A0–A3 CLI/sources/leakage/cache/report contracts; preserved explicit historical MTS comparison commands |
| `docs/enhance_latency.md` | HISTORICAL MTS measurement case study | Added scope banner; original measured values preserved |
| `docs/task2-v3-verification.md` | HISTORICAL | Added version/scope banner; original evidence retained |
| Prior implementation plans | HISTORICAL | Retained without rewriting their earlier technical claims |
| `docs/MTS.pdf` | HISTORICAL research reference | Inspected title/abstract of the 18-page reference; retained unchanged |

Inbound-link and contradictory-current-claim searches were performed. No document was deleted or designated SUPERSEDED merely because a newer design exists.

## Focused verification commands

All backend tests ran from `backend/`, using an owned disposable PostgreSQL 17 container on `127.0.0.1:55433`. The administrator's configured database was not migrated or seeded. Actual migration upgrade/downgrade/upgrade and concurrent edit/activation used additional uniquely named disposable databases. Test inputs are fictional; no production human bank was fabricated.

```powershell
uv run pytest tests/test_writing_anchors.py tests/test_writing_anchor_migration.py tests/test_writing_anchor_api.py tests/test_tacs_tree.py tests/test_writing_pairwise.py tests/test_task1_direct.py tests/test_task1_tacs.py tests/test_task1_scorer_selection.py tests/test_tacs_run_pinning.py tests/test_task1_tacs_benchmark.py tests/test_task1_benchmark.py tests/test_task1_benchmark_metrics.py tests/test_task1_visual.py tests/test_task1_writing_ai.py tests/test_task1_grounding_regression.py tests/test_writing_ai.py tests/test_mts_writing_v3.py tests/test_mts_writing_v4.py tests/test_mts_writing_v5.py tests/test_mts_writing_validation.py tests/test_mts_descriptor_fit.py tests/test_writing_ai_output_normalization.py tests/test_writing_completion_budgets.py tests/test_writing_concurrency.py tests/test_writing_llm_providers.py tests/test_chart_cross_check.py -q --tb=line
uv run python ../scripts/benchmark_task1.py --help
```

Ruff checked every changed backend Python module/test/migration and the CLI, from `backend/` so repository settings apply. `git diff --check` checked whitespace. The first combined focused run exposed a missing legacy-test fixture import after Ruff cleanup; the fixture is now self-contained, and the affected 37 tests passed before the combined rerun.

Frontend focused commands ran from `frontend/`:

```powershell
npm test -- tests/writing-anchors-api.test.ts tests/writing-anchors-admin.test.tsx tests/admin-dashboard.test.tsx tests/writing-ai-progress.test.tsx tests/writing-ai-feedback-availability.test.tsx tests/writing-ai-assessment.test.tsx tests/writing-review.test.tsx
npm test -- tests/root-layout.test.tsx tests/auth.test.tsx tests/admin-dashboard.test.tsx
npm run typecheck
npx eslint src/app/admin/writing-anchors/page.tsx src/features/writing-anchors src/lib/api/writing-anchors.ts src/lib/api/writing-ai.ts src/features/writing/writing-ai-progress.tsx src/features/writing/writing-ai-criterion-card.tsx src/features/writing/writing-review.tsx src/app/admin/page.tsx src/components/ui/app-shell.tsx tests/writing-anchors-api.test.ts tests/writing-anchors-admin.test.tsx tests/writing-ai-feedback-availability.test.tsx tests/writing-ai-progress.test.tsx tests/writing-ai-assessment.test.tsx
```

The primary seven frontend files passed 72 tests; root/auth/dashboard passed 41 tests (dashboard overlaps). Typecheck and targeted ESLint passed. The installed Next.js routing/server-client guidance was read before implementation. Browser/Playwright/build/deployment and expensive unrelated suites were intentionally excluded by the approved scope.

Final combined backend outcome and independent review disposition are recorded below after completion.

## Practical limits

No live GPU or human-labelled benchmark was run. Real-model agreement, position-conflict/fallback rates and latency/cost remain unmeasured. Default theoretical search bound is twelve language comparisons before Direct fallbacks, feedback synthesis and perception calls; it is not a latency gain claim. Production anchor tables start empty and require administrator-validated entries for pairwise use.

No production TA anchor query, numeric anchor-label prompt leakage, one-way node, unbounded search, out-of-range clamp, synthetic production anchor, official-score mutation, MTS removal or push is introduced.

Combined focused backend command: **641 passed in 84.59s**. Every changed Python file and CLI passed Ruff under backend configuration; whitespace checks passed. Independent whole-change review follows this verified implementation.
