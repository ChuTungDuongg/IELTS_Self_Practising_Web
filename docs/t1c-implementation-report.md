# T1-C implementation and verification record

Implemented natively in the authoritative Windows checkout `C:/Users/Admin/IELTS_Self_Practising_Web`, on local branch `codex/t1c-hybrid-tacs`. Starting local HEAD and read-only remote-main reference matched `a4c3f3c245495d33d79f6bf6c25e0b0778492874`. The tracked checkout was clean; existing Writing work and the approved design/plan were retained. No push, deployment or main-branch merge was performed.

## Delivered behavior

- Alembic 0021: initially empty `writing_anchor_sets` and `writing_human_anchors`, with all four labels. PostgreSQL frozen-content triggers, transactional DRAFT→ACTIVE→RETIRED activation/retirement, clone-to-draft and serialized concurrent editing are covered by actual database tests. Frozen published/previously-published archived task identity remains authoritative.
- Admin-only API and `/admin/writing-anchors`: searchable frozen task picker, original paragraphs, TA/TR/CC/LR/GRA labels, private note/provenance, draft CRUD, read-only frozen detail, clone/activation, filters/pagination and coverage. Production Task 1 CC/LR/GRA readiness is separate from exact-task TA and Task 2 research labels. Sparse recommendations are informational.
- Grounded Direct TA retains primary vision, optional fail-open DePlot, reconciliation, facts and claims. CC/LR/GRA use independent trees or Direct fallback. Each visited node selects one stable representative and makes exactly two swapped comparisons; consensus is exact, comparisons have no repair, and default search stops at two nodes. Adjacent supported bounds reconstruct Decimal half-bands; unsupported outer ranges do not clamp.
- Successful deterministic scores survive the separate single feedback synthesis boundary. Failed/invalid synthesis leaves score, mode and tree diagnostics intact, with null/omitted feedback, empty lists and explicit UNAVAILABLE status. No fabricated feedback, rescore or Direct replacement occurs. Four valid scores can still produce a COMPLETED aggregate. Frontend copy preserves existing human comments for unavailable AI feedback.
- Alembic 0022: pinned execution/anchor FK and private diagnostic JSONB. Queued runs retain the old frozen version or explicit no-bank decision after activation. Public DTOs/SSE expose safe stages and results, without bank content, labels, IDs, pivots or preferences. Legacy runs remain readable; Task 2 stays MTS v7.
- Existing T1-C benchmark extended to A0 Direct, A1 MTS, A2 independent full Direct N=3 median, and A3 exact Hybrid; A4 remains future work. Private manifest/read-only ACTIVE PostgreSQL sources, source digest/cache versioning, split-wide ID/normalized-essay leakage rejection and architecture costs are implemented. Target labels/truth/provenance never enter model inputs. TA accuracy is retained and excluded from language-tree/fallback denominators.

Trees use the widest contiguous whole-band run of at least two bands, with ties resolved by overlap with 6–8, proximity to 7 and stable ascending order. The first pivot is 7 when supported; otherwise and thereafter it is the lower median of remaining bands. A SHA-256 hash of target fingerprint, criterion, band and frozen set identity/version indexes UUID-sorted representatives. Forward/reverse preferences are normalized to TARGET_BETTER/ANCHOR_BETTER/COMPARABLE and must agree exactly; conflict causes criterion-local Direct fallback. There is no comparator retry or third vote. Default budget two means two calls/node, four/language criterion and twelve/run before fallback/perception/synthesis.

Technical minimum is one anchor at each of two adjacent whole bands. Pilot advice is two per band 6/7/8; mature advice is three per band 5–9. Half-band labels are stored and shown in coverage details but do not form pivots. Empty/sparse banks remain activatable; unusable coverage takes Direct fallback, and TA remains grounded Direct. Production tables are not seeded with generated anchors.

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
$env:DATABASE_URL='postgresql+asyncpg://tacs_test:tacs_test@127.0.0.1:55433/tacs_test'
uv run pytest tests/test_writing_anchors.py tests/test_writing_anchor_migration.py tests/test_writing_anchor_api.py tests/test_tacs_tree.py tests/test_writing_pairwise.py tests/test_task1_direct.py tests/test_task1_tacs.py tests/test_task1_scorer_selection.py tests/test_tacs_run_pinning.py tests/test_task1_tacs_benchmark.py tests/test_task1_benchmark.py tests/test_task1_benchmark_metrics.py tests/test_task1_visual.py tests/test_task1_writing_ai.py tests/test_task1_grounding_regression.py tests/test_writing_ai.py tests/test_mts_writing_v3.py tests/test_mts_writing_v4.py tests/test_mts_writing_v5.py tests/test_mts_writing_validation.py tests/test_mts_descriptor_fit.py tests/test_writing_ai_output_normalization.py tests/test_writing_completion_budgets.py tests/test_writing_concurrency.py tests/test_writing_llm_providers.py tests/test_chart_cross_check.py -q --tb=line
uv run python ../scripts/benchmark_task1.py --help
$taskPythonFiles = @(git diff --name-only a4c3f3c HEAD -- 'backend/*.py' 'backend/**/*.py' | ForEach-Object { $_.Substring(8) })
$taskPythonFiles += @(git diff --name-only -- 'backend/*.py' 'backend/**/*.py' | ForEach-Object { $_.Substring(8) })
uv run ruff check @taskPythonFiles ../scripts/benchmark_task1.py
```

Ruff checked every changed backend Python module/test/migration and the CLI, from `backend/` so repository settings apply. `git diff --check` checked whitespace. The first combined focused run exposed a missing legacy-test fixture import after Ruff cleanup; the fixture is now self-contained, and the affected 37 tests passed before the combined rerun.

Frontend focused commands ran from `frontend/`:

```powershell
npm test -- tests/writing-anchors-api.test.ts tests/writing-anchors-admin.test.tsx tests/admin-dashboard.test.tsx tests/writing-ai-progress.test.tsx tests/writing-ai-feedback-availability.test.tsx tests/writing-ai-assessment.test.tsx tests/writing-review.test.tsx tests/root-layout.test.tsx tests/auth.test.tsx
npm run typecheck
npx eslint src/app/admin/writing-anchors/page.tsx src/features/writing-anchors src/lib/api/writing-anchors.ts src/lib/api/writing-ai.ts src/features/writing/writing-ai-progress.tsx src/features/writing/writing-ai-criterion-card.tsx src/features/writing/writing-review.tsx src/app/admin/page.tsx src/components/ui/app-shell.tsx tests/writing-anchors-api.test.ts tests/writing-anchors-admin.test.tsx tests/writing-ai-feedback-availability.test.tsx tests/writing-ai-progress.test.tsx tests/writing-ai-assessment.test.tsx
```

Final combined frontend result: **112 passed in nine files**, including root layout, authorization, admin navigation, anchor workspace, feedback availability, assessment and Writing review. Typecheck and targeted ESLint passed. The installed Next.js routing/server-client guidance was read before implementation. Browser/Playwright/build/deployment and expensive unrelated suites were intentionally excluded by the approved scope.

Final combined backend result: **662 passed in 104.63s**, including the existing Task 2 MTS, output validation, completion budgets, concurrency and provider regressions. Every changed Python file and CLI passed Ruff under backend configuration. `git diff --check` passed.

## Independent review and single Native fix pass

One fresh whole-change reviewer inspected `a4c3f3c..46367a1`, read-only, without real inference or browser tools. It found four Important issues and no Critical issue. The author confirmed each, wrote covering tests, observed failure and fixed them in one Native pass; no second reviewer was dispatched.

| Finding | Result and evidence |
| --- | --- |
| Unsupported saved prompt/visual versions executed current code | Factory now rejects the full unsupported execution contract with safe `AI_CONFIGURATION_CHANGED`, before provider readiness/inference. Fifteen selector cases and a queued-version-change integration test went RED→GREEN; legacy null execution still selects MTS. |
| OpenAI JSON-mode messages omitted feedback output structure | Pairwise and feedback prompts now embed full strict JSON schemas; feedback also names exact selected criterion keys and limits. Actual OpenAI HTTP payload tests for both boundaries went RED→GREEN. Pairwise/feedback/composite versions bumped to v2. |
| A2 numeric perception metrics copied first repeat | All repeat counts are pooled and rates recomputed; independent observation denominators are explicit, sample certification remains conservative and confidence uses the weakest repeat. Correct+missing and correct+wrong+missing cases went RED→GREEN; individual repeats remain retained. |
| Successful activation retained stale DRAFT controls/coverage on refresh error | Authoritative activation status applies immediately; set and coverage reads succeed/fail independently and coverage is invalidated during refresh. Two refresh-failure cases went RED→GREEN. |

The review also noted omitted half-band details/call-bound guidance, creation dates and deterministic A2 interpretation. Required admin omissions were regraded as Important completion gaps against the approved specification and covered by a RED→GREEN UI test. A2 interpretation was included in the Important benchmark correction: separate invocations at vLLM temperature/seed zero can yield identical results; fake-provider tests prove invocation independence, not decoding diversity. No deferred minors remain.

The new backend regression run changed from 20 failed/17 passed to 37/37 passed. Admin checks changed from 3 failed/4 passed to 7/7 passed. One combined UI run exposed a date assertion preceding its separate list response; the test now waits for that row, and the final combined nine-file run passed 112/112. The final focused backend suite passed 662/662.

### Rulings made for behaviors the reviewer declined to judge

- Live-model accuracy, positional bias and measured latency/cost: mechanism tests suffice for this authorized implementation, with no real inference or measured quality/performance claim. Cost if wrong: model accuracy/bias/spend still requires an authorized human-labelled benchmark.
- Actual narrow-width/dark-mode browser rendering: component tests and responsive/theme CSS inspection stand under the user's browser/Playwright prohibition. Cost if wrong: visual layout defects can remain until browser QA is authorized.
- Task 2 production TACS, A4 and exact LCES reproduction: explicitly outside scope; existing Task 2 MTS remains. Cost if wrong: extending these behaviors requires separately scoped implementation and validation.

## Practical limits

No live GPU or human-labelled benchmark was run. Real-model agreement, position-conflict/fallback rates and latency/cost remain unmeasured. Default theoretical search bound is twelve language comparisons before Direct fallbacks, feedback synthesis and perception calls; it is not a latency gain claim. Production anchor tables start empty and require administrator-validated entries for pairwise use.

No production TA anchor query, numeric anchor-label prompt leakage, one-way node, unbounded search, out-of-range clamp, synthetic production anchor, official-score mutation, MTS removal or push is introduced.

The owned disposable database container is removed after verification. No deployment, configured-database migration, production bank seeding, remote push or main-branch merge is part of this delivery.
