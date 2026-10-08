# T1-C Hybrid TACS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a private versioned human Writing anchor bank, its admin workspace, grounded Direct TA plus bounded TACS language scoring, and the existing T1-C benchmark extension.

**Architecture:** PostgreSQL snapshots own administrator-validated labels. Task 1 always scores TA from its existing grounded visual analysis; only CC/LR/GRA traverse bidirectional language-anchor trees, with criterion-local Direct fallback. The existing worker, provider limiter, SSE, MTS rollback, and benchmark are extended rather than replaced.

**Tech Stack:** Existing Next.js 16/React 19/Zod 4, FastAPI/Pydantic 2, SQLAlchemy 2, PostgreSQL/Alembic, pytest/Vitest; no new product dependencies.

**Spec:** `docs/superpowers/specs/2026-10-08-t1c-human-anchor-tacs-design.md`, approved with the administrator's mandatory Hybrid TACS corrections on 2026-10-08.

## Global Constraints

- Production Task 1 TA never queries anchor ladders or invokes a comparator.
- Task 2 production remains existing local MTS (`mts-task2-v7`).
- Four human labels are stored, with no required feedback or independent overall.
- ACTIVE/RETIRED anchor content is immutable; production anchors are administrator-entered/validated only.
- Frozen Writing tasks are selected from authoritative relationships; no manually entered task UUID workflow.
- Production trees use CC/LR/GRA only, separated by task number, with contiguous whole-band ladders.
- Exactly two comparisons per node; strict agreement; one representative; no third vote or comparator repair.
- Default node budget 2; benchmark choices 1/2/3; no clamping or invented out-of-range score.
- Comparator messages receive no label, anchor designation, set metadata, provenance, or note.
- All completions share the existing configured bounded provider; preserve token safety and cancellation/checkpoints.
- AI remains advisory; no mutation of official scores, attempts, history, or analytics.
- No browser, Playwright, expensive full suite, repeated GPU inference, automatic human benchmark, deployment, or push.
- Preserve existing local changes and old useful documentation, including `docs/MTS.pdf`.

## Review Focus

- Activation while a run is queued must preserve that run's old or explicitly empty snapshot (Task 5 tests).
- Activation concurrent with draft editing must never publish partially written content (Task 1 tests).
- Provider failure in one ordering must not create a hidden third vote or cancel successful unrelated traits (Tasks 3/4 tests).
- Feedback failure or a feedback output containing a score must never overwrite/discard a deterministic tree score or invalidate its aggregate (Tasks 4/5/6 tests).
- A stale task-search or anchor-detail response must not change the form's selected task/response or enable active editing (Task 6 tests).

## Working method and file ownership

Implement in the authoritative local checkout on a `codex/` branch, after following the worktree skill's environment checks. Do not switch to remote main or lose the untracked approved design/plan. A separate managed worktree is only useful if additional unrelated local work appears; copy these approved artifacts before executing there.

Tasks 1–2 own the anchor persistence/API contract. Tasks 3–4 own the pure comparison and hybrid services. Task 5 integrates run persistence/worker/configuration and public progress. Task 6 owns the admin frontend and safe progress rendering. Tasks 7–8 extend the existing evaluation framework. Task 9 updates documentation and assembles verification. The frontend and benchmark must use the contracts below without inventing alternative field names.

Use an implementation ledger beside this plan to record red/green evidence, completed tasks, review findings, and any concrete deviations. Do not commit generated private data or temporary review output. Make focused commits after meaningful passing checks if using a commit-based workflow; do not push.

Run all `uv run` commands below from `backend/`, where the existing `.env` and
Alembic script location are resolved correctly. Run `npm --prefix frontend` and
Git commands from the repository root. The read-only `uv run alembic heads` check
from `backend/` confirmed `20261008_0020` as the sole starting head.

---

### Task 1: Anchor tables, immutable lifecycle, and snapshot queries

**Files:** Create `backend/app/models/writing_anchors.py`, `backend/app/schemas/writing_anchors.py`, `backend/app/repositories/writing_anchors.py`, `backend/app/services/writing_anchors.py`, `backend/alembic/versions/20261008_0021_writing_human_anchors.py`, `backend/tests/test_writing_anchors.py`, `backend/tests/test_writing_anchor_migration.py`; modify `backend/app/models/__init__.py`.

**Interfaces produced:**

- `HumanAnchorScores(ta: Decimal, cc: Decimal, lr: Decimal, gra: Decimal)` validates through the existing `validate_writing_criterion_score`.
- `HumanAnchorInput(writing_task_id: UUID, response_text: str, human_scores: HumanAnchorScores, admin_note: str | None, provenance: str | None)` preserves original paragraphs, rejects blank response and oversized input.
- Frozen `AnchorRecord(id: UUID, writing_task_id: UUID, test_version_id: UUID, task_number: Literal[1, 2], task_type: str | None, prompt: str, response_text: str, human_scores: HumanAnchorScores)` and `AnchorSnapshot(id: UUID | None, version: int | None, anchors: tuple[AnchorRecord, ...])` are internal DTOs, never learner output.
- `WritingAnchorService(session)` provides `active_snapshot() -> AnchorSnapshot`, `snapshot(set_id: UUID) -> AnchorSnapshot`, `create_draft(admin_id: UUID, name: str) -> AnchorSetResponse`, `activate(admin_id: UUID, set_id: UUID) -> AnchorSetResponse`, draft CRUD, frozen-task listing, and `coverage() -> AnchorCoverageResponse`.
- `AnchorSnapshot.language_anchors(task_number: Literal[1, 2], criterion: LanguageTrait) -> tuple[AnchorRecord, ...]` is the sole production bank accessor. Research exact-task filtering is separate and cannot be called by production TA.
- Admin DTOs share these names: `AnchorSetResponse {id,name,version,status,created_at,activated_at,retired_at}`, `FrozenWritingTask {id,test_version_id,test_title,version_number,task_number,task_type,prompt_preview}`, `AnchorSummary {id,anchor_set_id,task,word_count,human_scores,created_at}`, `AnchorDetail` adds `response_text,admin_note,provenance`; paginated lists use `{items,total,offset,limit}`.
- `AnchorCoverageResponse {active_set,production_task1,research_task1_ta,research_task2,recommendations,node_budget}`. Each criterion row uses `{criterion,counts,ladder,readiness,pilot_complete}`; `counts` includes all half-bands, while the matrix displays 5–9 and the ladder uses all eligible whole bands. TA research rows include frozen task identity. Empty data returns explicit empty arrays/counts, never an exception.

- [ ] Write tests proving four valid half-band labels persist without feedback/overall; 6.2, NaN, and infinity fail; paragraphs survive roundtrip; draft tasks fail; published and previously published archived tasks succeed; Task 1/2 language scopes remain separate.
- [ ] Write lifecycle tests: initial empty bank, clone preserves all four labels/text, monotonically increasing versions, one DRAFT/ACTIVE, atomic retirement/activation, sparse/empty activation allowed, draft CRUD, ACTIVE/RETIRED mutation rejection, and concurrent activation/edit serialization.
- [ ] Run `uv run pytest tests/test_writing_anchors.py tests/test_writing_anchor_migration.py -q --tb=short`; confirm missing implementations fail before writing product code.
- [ ] Implement `writing_anchor_sets`/`writing_human_anchors` using existing UUID/timestamp conventions, Decimal half-band checks, exact task FK with RESTRICT deletion, creator FK without data-erasing cascade, partial unique indexes for active/draft, and transactional global lifecycle locking. Verify the current Alembic head before choosing `down_revision` (observed `20261008_0020`).
- [ ] Implement PostgreSQL immutability guards for insert/update/delete in frozen sets and content updates to ACTIVE/RETIRED sets. Allow only controlled ACTIVE-to-RETIRED status/timestamp transition. Draft mutations lock their owning set; clone creates new rows, never edits prior data.
- [ ] Implement repository/service methods and coverage with authoritative task joins; use `(PUBLISHED) OR (ARCHIVED AND published_at IS NOT NULL)`. Only CC/LR/GRA determine production readiness; mature means three anchors at every whole band 5–9 and pilot means two at 6/7/8. Data entry has no readiness gate.
- [ ] Verify fresh upgrade, downgrade, and upgrade on an isolated disposable test database. Confirm existing data remains untouched and anchor tables begin empty. Re-run focused tests until green.

### Task 2: Admin-only anchor API

**Files:** Create `backend/app/api/v1/writing_anchors.py`, `backend/tests/test_writing_anchor_api.py`; modify `backend/app/api/v1/router.py`.

**Consumes:** Task 1 service/DTOs and existing `AdminUser`, `get_session`, `AppError`.

**Produces:** `/api/v1/admin/writing-anchors` endpoints:

| Method | Suffix | Contract |
| --- | --- | --- |
| GET | `/sets` | `{items: AnchorSetResponse[]}` |
| POST | `/sets` | `{name}` -> initial/next cloned draft, 201 |
| POST | `/sets/{set_id}/activate` | activated set |
| GET | `/tasks` | frozen task page; `search,task_number,offset,limit` |
| GET | `/coverage` | active `AnchorCoverageResponse` |
| GET | `/anchors` | summary page; `set_id,search,task_number,writing_task_id,task_type,status,offset,limit` |
| POST | `/sets/{set_id}/anchors` | `HumanAnchorInput` -> detail, 201 |
| GET | `/anchors/{anchor_id}` | `AnchorDetail` |
| PATCH | `/anchors/{anchor_id}` | complete validated replacement input -> detail |
| DELETE | `/anchors/{anchor_id}` | draft deletion, 204 |

- [ ] Write parameterized tests for every endpoint: unauthenticated 401, normal user 403, admin allowed. Assert frozen identity mismatch, invalid score, missing task, and frozen mutation return safe 4xx errors rather than leaking SQL/provider data.
- [ ] Run `uv run pytest tests/test_writing_anchor_api.py -q --tb=short`; confirm red.
- [ ] Implement thin routes with `AdminUser` on reads and writes; map service conflicts to existing structured `AppError` responses. Cap pagination/search and return compact summaries without response text.
- [ ] Verify Task 1 TA and Task 2 TR fields both persist through this API; activate/clone/version flow works; coverage does not require TA. Re-run Task 1/2 focused tests; confirm green.

### Task 3: Language-only tree and score-free comparator

**Files:** Create `backend/app/domains/scoring/tacs.py`, `backend/app/domains/scoring/tacs_prompts.py`, `backend/app/schemas/tacs.py`, `backend/app/services/writing_pairwise.py`, `backend/tests/test_tacs_tree.py`, `backend/tests/test_writing_pairwise.py`.

**Consumes:** Task 1 `AnchorSnapshot`, the existing `LLMProvider`/`CompletionOptions` and bounded provider wrapper.

**Produces:**

- `LanguageTrait = Literal['cc','lr','gra']` and strict `PairwisePreference {preference: RESPONSE_1_BETTER | RESPONSE_2_BETTER | COMPARABLE}`.
- `ComparisonResponse(task_prompt: str, response_text: str)` has no label/anchor metadata field.
- `pairwise_messages(criterion: LanguageTrait, response_1: ComparisonResponse, response_2: ComparisonResponse) -> list[Message]` only serializes criterion semantics, the required preference JSON schema, and these two texts/contexts. Version `task1-tacs-pairwise-v2` after independent review verified OpenAI JSON-mode needs the schema in messages.
- `contiguous_ladder(bands: Iterable[Decimal]) -> tuple[int, ...]`; widest adjacent run, ties by overlap with 6–8, proximity to 7, then ascending stable order; fewer than two adjacent bands -> empty.
- `representative(snapshot: AnchorSnapshot, anchors: Sequence[AnchorRecord], criterion: LanguageTrait, band: int, target_fingerprint: str) -> AnchorRecord` hashes sorted stable IDs and the supplied stable inputs.
- `PairwiseComparator(provider).compare(criterion, response_1, response_2) -> PairwisePreference` makes one short validated call without repair.
- `TACSTree(comparator, max_nodes: int = 2).score(snapshot, task_number, criterion, target: ComparisonResponse, target_fingerprint: str) -> TreeResult`, where `TreeResult` contains Decimal score or explicit fallback reason plus private visited-node/directional/selected-ID diagnostics. No TA trait is accepted.

- [ ] Write exact flow tests: `(COMPARABLE,COMPARABLE)` -> 7/two calls; consistent >7 then <8 -> 7.5/four; <7 then >6 -> 6.5/four. Assert response order, rubric equivalence, and swapped context with each pair.
- [ ] Write strict conflict, comparable-vs-better, sparse 6/8, edge out-of-range, two-node exhaustion on 5–9, provider failure, deterministic representative, half-band non-pivot, and invalid TA trait tests. Assert no third call, no fallback clamp, and no hidden node beyond budget.
- [ ] Test actual message-boundary types/serialization: metadata cannot be passed, scores/provenance/set identity never serialize, and legitimate essay numbers survive. Assert the schema forbids score/rationale/extras.
- [ ] Run `uv run pytest tests/test_tacs_tree.py tests/test_writing_pairwise.py -q --tb=short`; confirm red.
- [ ] Implement the pure helpers, score-free prompts, comparator with `CompletionOptions(max_tokens=128)` and existing finish validation, and tree. At each node attempt both forward and reverse once via the same bounded provider; normalize to target-relative results; propagate cancellation/trace persistence errors instead of converting them to provider fallback.
- [ ] Maintain sequential node traversal; lower-median pivots after initial 7. Use only actually established bounds and Decimal midpoint. Return NO_ANCHORS, INSUFFICIENT_CONTIGUOUS_COVERAGE, OUT_OF_RANGE, POSITION_CONFLICT, BUDGET_EXHAUSTED, or PAIRWISE_PROVIDER_FAILURE as appropriate.
- [ ] Re-run the focused tests; confirm green and exact provider counts for each case.

### Task 4: Grounded Direct and production Hybrid TACS services

**Files:** Create `backend/app/domains/scoring/direct_writing_prompts.py`, `backend/app/services/task1_direct.py`, `backend/app/services/task1_tacs.py`, `backend/tests/test_task1_direct.py`, `backend/tests/test_task1_tacs.py`; extend `backend/app/schemas/tacs.py`, `backend/app/services/writing_execution.py` only for new content-free latency stages.

**Consumes:** Existing `Task1WritingScoringService` perception helpers, `Task1ScoringRequest`, MTS `_validated` output-safety helpers, `CriterionResult`, Task 3 tree.

**Produces:**

- `direct_messages(request: Task1ScoringRequest, trait: Trait, analysis: Task1Analysis | None) -> list[Message]`, version `task1-direct-v1`; only TA gets grounded visual/claim context.
- `Task1DirectScoringService(provider, chart_derenderer=None, chart_timeout=90, *, max_concurrent_requests=2, latency=None).assess(request, trace) -> Task1WritingResult | None`, sharing the MTS-compatible `usage`, `diagnostics`, `failures`, `latency_summary` worker contract.
- `Task1TACSScoringService(..., *, anchor_snapshot: AnchorSnapshot, target_fingerprint: str, max_tree_nodes: int = 2, max_concurrent_requests=2, latency=None)` uses composite version `task1-hybrid-tacs-v2` and the same assess/worker contract, adding private `scoring_metadata()`.
- Strict feedback input/output for only selected CC/LR/GRA. Version `task1-tacs-feedback-v2`; messages include the full output JSON schema and exact selected keys for OpenAI JSON mode. Output per trait has feedback/strengths/improvements and no score. Use one request with bounded max_tokens 4096, no feedback repair/rescore path.

- [ ] Write Direct tests asserting one normal scoring call per criterion, grounded TA analysis is present, other criteria remain text-only, source evidence list is empty, scores validate/normalize through existing helpers, and length repair remains bounded with 3072/4096 caps.
- [ ] Write explicit TA boundary tests using spies that fail if a TA bank accessor/comparator is called. Assert GROUNDED_DIRECT mode with both empty and populated banks; human TA values do not enter TA prompts or affect its result. Preserve visual-confidence failure behavior.
- [ ] Write Hybrid tests for three language trees/fallbacks, one synthesis call only for pairwise successes, zero synthesis when all Direct, deterministic scores unchanged by feedback, extra score field rejected, synthesis failure preserving scores/modes/diagnostics and aggregate without rescore/Direct substitution/unrelated failure, existing DePlot/claims behavior, peak concurrency cap, and text branches beginning before perception completes.
- [ ] Run `uv run pytest tests/test_task1_direct.py tests/test_task1_tacs.py -q --tb=short`; confirm red.
- [ ] Reuse the existing perception and trace/failure orchestration rather than copying it. Add Direct criterion execution that skips evidence selection but preserves `_validated` token/finish/output safeguards. Override the hybrid language branch only; TA always calls Direct after grounded analysis.
- [ ] Reuse one provider limiter for every completion. At pairwise success the deterministic score is final. Attach validated synthesis normally; on synthesis failure populate `CriterionResult` with the unchanged score, `feedback=None`, empty strengths/improvements, `feedback_status='UNAVAILABLE'`, and safe `feedback_error_code='AI_FEEDBACK_UNAVAILABLE'`. Preserve private modes/tree diagnostics and aggregate established scores. Adapt only CriterionResult, leaving Direct/raw provider feedback mandatory. Legacy feedback defaults to AVAILABLE; validate status/text coherence.
- [ ] Re-run new tests plus `test_task1_writing_ai.py`, `test_task1_grounding_regression.py`, `test_writing_concurrency.py`, and `test_writing_completion_budgets.py`; confirm green without weakening existing tests or altering MTS prompts.

### Task 5: Pinned execution configuration, worker cutover, and safe SSE

**Files:** Modify `backend/app/core/config.py`, `backend/.env.example`, `backend/app/models/writing_ai.py`, `backend/app/services/writing_ai.py`, `backend/app/services/writing_ai_worker.py`, `backend/app/schemas/writing_ai.py`, `backend/app/services/writing_execution.py`; create `backend/alembic/versions/20261008_0022_writing_tacs_execution.py`, `backend/app/services/task1_scorer.py`, `backend/tests/test_task1_scorer_selection.py`, `backend/tests/test_tacs_run_pinning.py`; extend `backend/tests/test_writing_ai.py` as needed for architecture/SSE assertions.

**Consumes:** Tasks 1/4 snapshots and services; current persisted worker/checkpoint architecture.

**Produces:**

- Settings `ai_writing_task1_scorer: Literal['anchor_pairwise','direct','mts'] = 'anchor_pairwise'`, `ai_writing_pairwise_max_tree_nodes: int = 2` constrained 1–3.
- Immutable `Task1ExecutionConfig` with architecture, composite/direct/pairwise/feedback/visual versions, pinned set ID/version (including explicit none), and node budget. Provider/model remain existing run identity fields.
- Run fields `scoring_architecture`, nullable `anchor_set_id` FK with RESTRICT, nullable `execution_config_json` JSONB, and nullable `scoring_diagnostics_json` JSONB. Migration adds fields without rewriting old run content; null config means legacy MTS.
- `input_fingerprint(request,prompt_version,provider,model,*,execution: Task1ExecutionConfig | None=None)` extends Task 1 execution keys only; legacy/no-execution behavior and Task 2 contract stay compatible.
- `create_task1_scorer(execution, snapshot, provider, chart_derenderer, ..., target_fingerprint)` returns the pinned MTS/Direct/Hybrid service. Empty snapshot decision stays empty; never re-query active at worker execution.
- Events add safe `anchor.search.started`, `anchor.node.started`, `anchor.forward.completed`, `anchor.reverse.completed`, `anchor.node.completed`, `anchor.bracket.completed`; payloads contain criterion/stage only, not tree data. Public criterion mode/reason may be added explicitly; private diagnostics stay outside result JSON/public DTOs.

- [ ] Write selector validation/default/rollback tests, fingerprint invalidation for set version/node budget/prompt identity, unchanged Task 2 fingerprints, and correct Task 1 detection for all new/old version labels.
- [ ] Write enqueue/activate/execute tests: run pinned to old snapshot uses old anchors after retirement; no-bank run stays no-bank after activation; frozen empty active set behaves safely; old pending/completed runs remain readable.
- [ ] Write public snapshot/SSE tests proving no anchor ID/text/label/pivot/preference leaks, internal metadata persists modes and counts, replay/heartbeat/partial failure work, feedback failure persists a COMPLETED scored run with unavailable feedback, and official score records stay untouched.
- [ ] Run `uv run pytest tests/test_task1_scorer_selection.py tests/test_tacs_run_pinning.py tests/test_writing_ai.py -q --tb=short`; confirm red.
- [ ] Implement migration/settings and enqueue pinning before fingerprint/cache selection. Load only the pinned set at worker startup in a short database transaction; do not keep a DB session across provider calls. Use the recorded execution config, while retaining existing provider/model safety checks.
- [ ] Persist private modes/tree data with each criterion checkpoint, including partial successes/failures. Extend timing allowlists safely. Keep architecture metadata outside strict result models and apply public presentation allowlists. Preserve Task 2 MTS selection and prompt version.
- [ ] Re-run focused worker/SSE, new pinning/selector tests, Task 1 AI regressions, and Task 2 MTS v3/v4/v5/output-validation regressions plus completion/concurrency/provider tests. Verify the new migration on a disposable test database.

### Task 6: Admin anchor workspace and learner progress compatibility

**Files:** Create `frontend/src/app/admin/writing-anchors/page.tsx`, `frontend/src/lib/api/writing-anchors.ts`, `frontend/src/features/writing-anchors/anchor-workspace.tsx`, `anchor-form.tsx`, `anchor-coverage.tsx`, `anchor-workspace.module.css`, `frontend/tests/writing-anchors-api.test.ts`, `writing-anchors-admin.test.tsx`; modify `frontend/src/app/admin/page.tsx`, `frontend/src/components/ui/app-shell.tsx`, `frontend/src/lib/api/writing-ai.ts`, `frontend/src/features/writing/writing-ai-progress.tsx`, and targeted existing navigation/progress tests.

**Consumes:** Task 2 exact endpoint/DTO fields and Task 5 safe event/activity names. HTTP only; no browser-side domain persistence.

**Produces:** `/admin/writing-anchors`, protected by the existing admin layout, with visible admin navigation and typed Zod-validated API functions. No new auth logic.

- [ ] Read installed `frontend/node_modules/next/dist/docs/` guidance for app routing/server-client boundaries as required by `frontend/AGENTS.md`.
- [ ] Write API tests for DTO parsing, invalid half-band inputs, paragraph-preserving mutation body, and frozen detail/list separation.
- [ ] Write Vitest user-flow tests: empty/create-draft, searchable task selection with titles/version/preview, Task 1 TA versus Task 2 TR labels, four score fields/no feedback, create/view/edit/delete, read-only active/retired sets, clone/activate, stale request responses, HTTP validation/conflict/auth errors, and refresh after mutations.
- [ ] Write coverage tests asserting CC/LR/GRA production readiness and separate TA/Task 2 research wording, informational recommendations, empty state, contiguous ladder text, accessible state labels, responsive overflow/layout classes, and theme variables. Extend navigation/progress tests for safe new phases and Vietnamese copy without bank details.
- [ ] Run `npm --prefix frontend test -- tests/writing-anchors-api.test.ts tests/writing-anchors-admin.test.tsx tests/admin-dashboard.test.tsx tests/writing-ai-progress.test.tsx`; confirm red.
- [ ] Implement the typed client and focused workspace components, using existing form/card/button/theme conventions. Include set/status/task/type/search filters, pagination, full detail on demand, cancel/save states, and response-order-safe asynchronous task search. Only draft sets enable writes; backend errors remain visible.
- [ ] Extend safe Writing event/activity/result schemas and progress rendering with simple language. Show unavailable feedback without hiding its score or fabricating feedback, and preserve existing human feedback when copying score suggestions. Keep empty evidence supported. Add navigation only for administrators and the dashboard workspace link; add focused feedback-unavailable rendering/copy tests.
- [ ] Re-run targeted Vitest, `npm --prefix frontend run typecheck`, and targeted ESLint for changed files. Do not open a browser or use Playwright.

### Task 7: Benchmark anchor sources, architecture selector, and leakage guard

**Files:** Modify `backend/app/evaluation/task1/models.py`, `manifest.py`, `runner.py`, `scripts/benchmark_task1.py`, and `benchmarks/writing_task1/manifest.schema.json` only if the input schema changes; create `backend/app/evaluation/task1/anchor_sources.py`, `architectures.py`, `backend/tests/test_task1_tacs_benchmark.py`; extend `backend/tests/test_task1_benchmark.py`.

**Consumes:** Production services and immutable snapshot DTOs from Tasks 1/4/5, existing benchmark loaded samples/provider counters/checkpoints.

**Produces:** `--architecture direct|mts|direct-self-consistency|anchor-pairwise|all`; `--tree-node-budget 1|2|3`; mutually exclusive `--anchor-source postgres` versus `--anchor-manifest PATH` for A3; architecture-aware configs/record/cache identity. Existing `--scoring-version v3|v5|both` remains explicitly an MTS comparison, not a false Direct/TACS version selector. Default current architecture is Hybrid TACS, with no-anchor Direct fallback supported.

- [ ] Write tests for all four fake-provider architectures, explicit labels, correct production Hybrid service use, grounded Direct TA in A3, independent three-run A2 median/individual spread/variance, and existing MTS legacy compatibility.
- [ ] Write private-manifest and read-only PostgreSQL source tests, immutable snapshot identity/density, invalid human-score/provenance input rejection, Task 1/2 separation, and no database mutations.
- [ ] Write leakage tests rejecting same sample ID and normalized essay hash across the selected split before any provider call/cache reuse. Normalize with deterministic NFKC/casefold/whitespace collapse for leakage only, preserving stored essay text. Labels, visual truth, and private provenance never enter scorer requests.
- [ ] Run `uv run pytest tests/test_task1_tacs_benchmark.py tests/test_task1_benchmark.py -q --tb=short`; confirm red.
- [ ] Implement versioned private manifest loading into the production snapshot DTO, read-only active-PostgreSQL loading, preflight split-wide leakage checks, architecture configs/CLI validation, and production-service dispatch. Private manifest supports all four labels and task identity; it is never production ingestion.
- [ ] Implement A2 as three independent full A0 assessments. Store per-repeat scores/perception/cost summaries without essay/provider text; deterministic median by criterion. Classify aggregated perception as OK only if all repeats are certified OK; preserve their individual summaries.
- [ ] Bump benchmark contract version and extend implementation hash/fingerprint/cache keys with architecture, prompts, pinned snapshot/digest, tree budget, and self-consistency count. Old checkpoints must not masquerade as current records. Dry-run performs no provider call or production mutation.
- [ ] Re-run focused benchmark and leakage tests; confirm green. No real dataset or GPU benchmark run.

### Task 8: Comparable T1-C metrics and reports

**Files:** Modify `backend/app/evaluation/task1/report.py`, `models.py`, and `metrics.py` only where needed; extend `backend/tests/test_task1_benchmark_metrics.py`, `backend/tests/test_task1_tacs_benchmark.py`.

**Consumes:** Task 7 architecture-aware EvaluationRecords, production private tree metadata, existing score/perception metrics.

**Produces:** Architecture-identified JSON/Markdown/CSV reports and resume records with comparable A0/A1/A2/A3 metrics and safe cost diagnostics.

- [ ] Write tests asserting criterion/overall exact/±0.5/±1/MAE/RMSE/bias/QWK behavior is retained, missing QWK conditions remain explicit, and ALL/PERCEPTION_OK groups preserve existing meaning.
- [ ] Write A3 report tests for mean/p50/max language nodes, pairwise calls, visited bands, set ID/version/density, exact directional agreement rate, position conflict, every fallback reason, total Direct fallback, latency, and token/call totals. TA GROUNDED_DIRECT is excluded from pairwise/fallback denominators but its accuracy remains reported.
- [ ] Write privacy/roundtrip tests: no source essay, anchor text, private note/provenance, raw completion, or credentials appear in reports/checkpoints. Architecture/anchor-version/IDs and band/count diagnostics are benchmark metadata, not learner payloads.
- [ ] Run `uv run pytest tests/test_task1_benchmark_metrics.py tests/test_task1_tacs_benchmark.py -q --tb=short`; confirm red for new expectations.
- [ ] Extend existing aggregators/ablations/renderers; state denominators and failed/attempted run counts. Preserve perception/specialist metrics and true provider accounting, including failed comparisons, Direct repairs, and one synthesis request. Distinguish theoretical cost bounds from observations.
- [ ] Re-run report/benchmark tests and confirm schema-compatible serialization/resume behavior.

### Task 9: Current documentation, historical classification, and final review

**Files:** Create `docs/lces_adapt.md`; modify `README.md`, `docs/ai-writing.md`, `docs/modal-web.md`, `docs/enhance_latency.md`, `benchmarks/writing_task1/README.md`; mark `docs/task2-v3-verification.md` historical; retain old `docs/superpowers/plans/` as history, and retain `docs/MTS.pdf`. Record audit classification and verification results in the implementation ledger/report rather than changing past plans' technical claims.

- [ ] Audit the required documents and inbound links using `rg`; inspect `docs/MTS.pdf` as a retained MTS research reference. Classify CURRENT/HISTORICAL/SUPERSEDED. Delete nothing unless genuinely redundant with no remaining inbound links.
- [ ] Write `docs/lces_adapt.md` with all 27 approved sections, including the hybrid architecture diagram, why TA is visual-grounded Direct, three production language labels plus one TA evaluation label, true bidirectional tree behavior, actual feedback-failure/call policy, and interview/CV examples without fabricated gains.
- [ ] Update the current overview/config/API/CLI documents to describe Hybrid TACS default, empty-bank language fallback, grounded Direct TA, retained MTS selector/A1, unchanged Task 2, privacy/pinning, leakage, and A0/A1/A2/A3/A4 status. Preserve measured MTS latency findings; add only the theoretical 2 calls/node, 4/language criterion, 12/run before fallbacks cost model.
- [ ] Search again for unqualified contradictory current claims about TA pairwise, all-four TACS, MTS-only production, sequential criteria, old current versions, or TA readiness gates. Historical banners must make old statements unambiguous.
- [ ] Run the final focused backend set once: anchor/migration/API, tree/comparator/Direct/Hybrid/pinning/selector/benchmark/metrics, Task 1 visual/AI regressions, touched worker/SSE, and Task 2 MTS/output/completion/concurrency/provider regressions. Re-run only changed/failing areas after fixes.
- [ ] Run targeted frontend Vitest and `npm --prefix frontend run typecheck`; targeted ESLint for changed frontend files; `uv run ruff check` on all changed Python modules/tests/migrations; `git diff --check`. Record exact commands/counts and unavailable checks honestly.
- [ ] Request one independent whole-change review after implementation (or task reviews if the chosen execution method requires them). Give the reviewer the approved spec, this plan, diff, focused results, and special focus on TA exclusion, snapshot races, structured label secrecy, bounded call counts, SSE privacy, and Task 2 compatibility. Resolve material findings and re-run their covering checks.
- [ ] Produce the requested final implementation report covering starting/final Git state, migration/tables/lifecycle, admin form/task picker/readiness, hybrid criterion modes, tree/bias/budget, A0–A4/leakage, documentation changes/classification, exact checks, and unmeasured real-model limitations. Explicitly confirm no production TA anchors, numeric label prompt leakage, one-way production nodes, unbounded search, clamping, fake production anchors, official-score mutation, MTS removal, or push.

## Plan self-review

All approved subsystems have an owning task: persistence/lifecycle/coverage (1), authorization/API (2), score-free language comparison/tree (3), grounded Direct TA and Hybrid feedback (4), pinned run/cache/worker/SSE (5), admin/navigation/learner compatibility (6), A0–A3 sources/leakage/cache (7), metrics/reporting (8), current/historical documentation and final checks (9). A4 and Task 2 production cutover remain excluded.

The five Review Focus conditions each have explicit owning tests above. Cross-task DTO/API names match the interfaces; production TA receives neither a ladder nor a comparator. The administrator approved Native execution and the complete plan on 2026-10-08, with the score/feedback reliability correction incorporated above. Scoring succeeds independently of feedback synthesis; there is no remaining approval gate before implementation.
