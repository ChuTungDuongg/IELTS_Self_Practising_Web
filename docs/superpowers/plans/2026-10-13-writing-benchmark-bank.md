# Admin Writing Benchmark Bank Implementation Plan

**Status:** Plan only, prepared for user review. The design is approved; do not reopen its product or architecture decisions. Do not execute this plan until the user authorizes implementation.

**Goal:** Add one private ADMIN-authored Writing ground-truth bank, capped at 100 samples per task, with safe draft editing, production-derived overall bands, distribution guidance, compatible ZIP export and an offline Task 2 benchmark CLI.

**Spec:** [Approved Writing benchmark bank design](../specs/2026-10-13-writing-benchmark-bank-design.md). The user's approval supersedes the spec's older “awaiting final user review” status sentence.

**Architecture:** One benchmark sample table, thin ADMIN-only FastAPI routes, a benchmark repository/service, existing `LocalAssetStorage`, a separate admin master/detail page, shared score-only evaluation metrics and a dedicated Task 2 offline evaluator. Production scoring remains unchanged.

**Tech stack:** FastAPI, SQLAlchemy async/PostgreSQL, Alembic, Pydantic, stdlib ZIP/CSV/tempfiles, Next.js/React, existing Zod clients, EN/VI dictionaries, pytest and Vitest/Testing Library. No new dependency is expected.

**Execution:** Fourteen sequential, independently verifiable tasks. Each task follows RED → minimal implementation → GREEN → scoped commit. Checkbox steps track future implementation; none was executed during this planning run. Do not delegate or invoke live providers as part of normal validation.

## Inspected baseline and evidence

- Synced clean `main` with `git fetch origin`, `git pull --ff-only origin main`, `git status --short`, and `git log --oneline -12`.
- Inspected SHA: `7a39025ad201b672c81986721eac671c24da7d67` (`Document admin Writing benchmark bank design`). Read the entire 747-line spec.
- Remote [CI run 38392866057](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions/runs/38392866057): **completed / success** for that exact SHA. Remote [Golden path E2E run 38392866113](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions/runs/38392866113): **completed / success**. No existing CI failure was found; no baseline code repair belongs to this run.
- Read-only `uv run alembic heads` from `backend/`: exactly `20261013_0034 (head)`. Its parent is `20261013_0033`. Reserve `20261013_0035_writing_benchmark_bank.py` / revision `20261013_0035` only if this remains the head when implementation begins; otherwise use one new revision after the newly inspected head.
- No production, test, schema or migration file was changed while planning. No local test suite, browser, Playwright, live inference or deployment was run.

### Actual reuse points

| Area | Inspected implementation | Consequence for this plan |
| --- | --- | --- |
| Admin access | `frontend/src/app/admin/layout.tsx`, `features/auth/admin-guard.tsx`, `admin-only.tsx`, `auth-provider.tsx`; `backend/app/api/dependencies.py::AdminUser`, `require_admin` | Reuse both existing server/client guards and backend ADMIN dependency; no new authentication or teacher variant. |
| Admin APIs | `backend/app/api/v1/admin.py`, `api/v1/router.py`; `schemas/admin.py`, `services/admin.py` | Add a separate router under `/admin/writing-benchmark`; retain thin routers and service-owned transactions. |
| ORM/repositories | `models/base.py`, `models/__init__.py`, `models/enums.py`, `models/entities.py`, `models/writing_ai.py`, `repositories/tests.py`, `repositories/writing_ai.py` | Reuse UUID/timestamp mixins, named constraints, Decimal columns, explicit transactions and locked reads. Do not attach samples to learner attempts or frozen test versions. |
| Test schema | `backend/tests/conftest.py`, `test_focused_scope_migration.py`, `test_teacher_domain_models.py`, `test_subjective_grading.py` | Main fixture uses PostgreSQL and a rollback transaction, with savepoints and conditional recent migration application. Search found metadata/constraint inspection but no current `Base.metadata.create_all` fixture or SQLite ORM schema builder. Add explicit model registration/schema coverage; do not invent or rewrite a nonexistent SQLite fixture. |
| Storage | `storage/local.py`, `storage/__init__.py`, `api/v1/assets.py`, `services/tests.py::resolve_owned_or_inherited_asset`, `_delete_files` | `store`/`store_file` choose image MIME rules only for `category="images"`; arbitrary nested categories currently use audio rules. Extend the same storage class deliberately. Generic assets require `test_version_id`; benchmark images must not become generic `Asset` rows or inherit test access. |
| ZIP delivery | `api/v1/transfer.py`, `frontend/src/lib/api/transfer.ts` | Reuse temporary ZIP + authenticated `FileResponse` + cleanup and existing `apiResponse` binary-download conventions. Build on disk, not a potentially gigabyte-sized backend `BytesIO`. |
| Writing arithmetic | `domains/scoring/writing.py::validate_writing_criterion_score`, `calculate_task_overall`; `ai_writing.py::aggregate_ai_task_two`; `ielts_band.py::round_to_half` | Derive the individual essay's four-criterion mean and rounded half band using production helpers. Do not apply Task 1/Task 2 weighted full-module arithmetic to an individual benchmark sample. |
| Task 1 evaluation | `evaluation/task1/models.py`, `manifest.py`, `metrics.py`, `runner.py`, `report.py`, `scripts/benchmark_task1.py`, `test_task1_benchmark_metrics.py`, `test_task1_benchmark.py` | Directly validate exported Task 1 JSONL with current `BenchmarkSample`; extract score metrics without moving perception logic. Preserve typed resume/attempt/failure semantics. |
| Current scorer identities | Task 1 composite/scoring v12, visual v3; `mts_prompts.py::AI_WRITING_PROMPT_VERSION` / `effective_prompt_version` gives Task 2 v12; `services/mts_writing.py::MTSWritingScoringService.assess`, `_assess_task2_criterion` | Task 2 benchmark calls the current production service: score-only → evidence → feedback, with relevance and bounded provider concurrency. Human targets never enter `WritingScoringRequest`. Do not change prompt versions/calibration for this feature. |
| Task 2 benchmark absence | Searched `backend/app/evaluation/`, `scripts/`, `benchmarks/` | No dedicated Task 2 benchmark CLI/package exists. `evaluation/task1/legacy_task2_v6.py` is a frozen Task 1 evaluation dependency, not a current Task 2 runner. |
| Frontend contracts | `lib/api/client.ts::{apiRequest,apiResponse,ApiError}`, `admin.ts`, `assets.ts`, `server-client.ts` | Use Zod-validated DTOs, cookie/session-aware requests, `ApiError.details`, multipart uploads and binary export. No frontend PostgreSQL access. |
| Autosave/dialogs | `features/test-builder/builder-lifecycle.tsx::{BuilderLifecycleProvider,useBuilderAutosave}`, `writing-builder.tsx`, `autosave-link.tsx`, `components/ui/confirm-dialog.tsx` | Reuse the existing 1000-ms configurable autosave/drain mechanism and dialogs. The hook supports optional lifecycle context; the provider can supply status/flush barriers outside Builder. Do not use its permanent whole-draft `beginDelete` state for deleting one bank row. |
| UI/i18n | `features/auth/admin-content.tsx`, `components/ui/page-heading.tsx`, `app/globals.css`, `lib/i18n/{en,vi,types}.ts`, `features/writing/task-types.ts` | Retain BandPilot admin surfaces and Writing semantics. Add scoped page CSS and EN/VI labels; reuse Task 1 type IDs, not their currently English-only display labels. |
| CI | `.github/workflows/ci.yml` | CI runs lint/format from `backend/`, including `../scripts`, then fresh PostgreSQL migration, one head and full backend tests; frontend runs typecheck/lint/unit tests. Targeted local checks must use the same backend working directory/configuration. |

`benchmarks/writing_task1/README.md` still describes v11 despite the current v12 CLI. Correct those documentation references in Task 13; this is documentation drift, not a discovered CI failure. The spec's illustrative lowercase `pie_chart` is not the current enum value: export canonical `PIE_CHART`/other registry values and validate against the model instead of copying the example literally.

## Implementation decisions within the approved design

1. **Single table and stable slots.** `WritingBenchmarkSample` uses UUID identity and a unique `(task_number, sequence_number)` with task `1|2` and slot `1..100`. These constraints alone make more than 100 rows per task impossible. Transactional task-scoped PostgreSQL advisory locking additionally makes lowest-free-slot allocation and capacity errors deterministic under races, including empty-bank races. Deletion may free a slot; neighboring codes never change. Both drafts and completed rows consume capacity.
2. **Technical edit revision only.** Add an internal integer `revision` for optimistic autosave safety, following existing Builder `expected_revision`/`advance_revision` behavior. This is a row concurrency token, not a bank/dataset version, history table or visible version selector. Task number, slot, UUID and image key are server-managed and immutable through PATCH. A row lock plus revision check protects PATCH, Complete, image mutations and Delete.
3. **Draft/completion lifecycle.** Creation always creates DRAFT, with DEV default, empty prompt/essay and null labels. PATCH preserves exact entered strings and permits partial content; supplied scores/types are always validated. PATCH retains COMPLETE only while all completeness conditions remain valid; invalidating edits demote it to DRAFT. Explicit Complete validates the latest persisted revision and rejects missing fields with safe field-path errors. Image removal demotes Task 1 to DRAFT atomically. No automatic completion from autosave.
4. **Labels/overall.** Store nullable `human_ta_tr`, `human_cc`, `human_lr`, `human_gra` as production-valid half bands; task-aware UI labels the first TA or TR. Use unscaled PostgreSQL Numeric plus range/mod checks, so database coercion cannot round an invalid value such as 6.49 into an apparently valid 6.5 before validation. Derive nullable `human_overall` in DTOs/summary/CSV using `aggregate_ai_task_two`, never store it. Export Task 1 `ta` and Task 2 `tr`. All 0–9 values are valid even though suggested distribution begins at 4.0.
5. **Field bounds.** Match the existing canonical Task 1 manifest bounds: prompt 20,000 characters, essay 100,000, source note 2,000. Nonblank checks inspect `.strip()` without rewriting saved prompt/essay. Provider context limits still apply offline; oversized inference inputs yield visible failures, never silent truncation or a production input-policy change.
6. **Private immutable image keys.** Reuse `LocalAssetStorage` with a narrowly scoped `store_benchmark_writing_image(sample_id, ...)` helper. Use `benchmark/writing/task1/<sample-uuid>/<fresh-asset-uuid>.<ext>` so concurrent replacements never overwrite the same file. Reuse image MIME/extension/size guards and existing trusted-image signature validation; cap at `min(max_image_upload_mb, 10)` MiB to match Task 1 CLI `ImagePart`. No API accepts an image key/path. Validate namespace/sample ownership before resolve/delete/export.
7. **Cleanup order.** Write a new unique file, commit the locked row update, then best-effort remove the obsolete owned file. A transaction failure cleans only a proven-uncommitted new file. Cancellation/lost commit acknowledgement must not delete a possibly committed asset; use existing durable mutation/checkpoint patterns and prefer a safely retained orphan to destroying committed data. Deletion/removal commits DB changes before obsolete-file cleanup. No new cleanup subsystem or background benchmark job.
8. **API boundary.** New `api/v1/writing_benchmark.py` router has prefix `/admin/writing-benchmark` and ADMIN dependency on every route: summary, list/create, detail/PATCH/delete, explicit `POST /samples/{id}/complete`, and image POST/GET/DELETE, plus GET export. List/summary omit essays, prompts and raw storage keys. Complete errors use a benchmark-owned structured response `{code,message,errors:[{path,message}]}` compatible with `ApiError.details`, without changing global error behavior.
9. **Summary guidance.** Return per-task total/draft/complete counts, complete split counts, and all 19 overall half-band bins. Suggested targets are exactly 4.0→8, 4.5→8, 5.0→9, 5.5→10, 6.0→11, 6.5→12, 7.0→12, 7.5→10, 8.0→8, 8.5→6, 9.0→6 (sum 100), and DEV 80/HOLDOUT 20. These are advice only. Expose lower-band actual counts without inventing quotas; compute distribution from COMPLETE rows only. Criterion histograms are deferred P1.
10. **Snapshot export.** Read COMPLETE rows in stable task/slot order under shared row locks while staging their immutable images and archive, so image replace/delete cannot remove a file being copied. Do blocking ZIP/file work outside the event loop, with no SQLAlchemy session use in the worker thread. Release locks once the temporary ZIP is complete. Missing/invalid COMPLETE assets fail export safely; never manufacture image bytes or silently omit an invalid completed row. Empty/partial banks may export.
11. **Bundle contract.** Always produce the six specified root files plus `images/`; stable image names are generated codes and validated extensions. JSONL is canonical, emits numeric human labels, `raters=1`, safe nonblank provenance fallback `admin-labelled benchmark sample`, false redistributable unless explicitly set, and null visual truth. Use stdlib `csv` quoting for exact multiline content. Generate the combined schema from the two actual Pydantic models (e.g. `TypeAdapter` union) so `$defs` references remain valid. No CSV parser or bank-version field.
12. **Task 2 evaluator.** Separate contracts/manifest/runner/report/CLI; use production `MTSWritingScoringService`, current effective prompt identity and `paragraph_mode="textarea"`. Translate emitted production `ta` to report `tr` at the evaluation adapter only. Samples run sequentially; within each sample the existing production provider limiter bounds criterion requests. CLI exposes `--max-concurrent-llm-requests 1..4`; do not multiply concurrency through parallel sample workers.
13. **Offline resume and failures.** Extract only the small content-free checkpoint/provider-count primitives needed by both evaluators, preserving Task 1 imports/behavior. Identity includes sample contents/labels/split, provider/model, hashed endpoint, effective prompt, relevant runtime settings, paragraph provenance, evaluation contract and implementation hash. Validated successful attempts can resume; failures/corruption/inconsistent scores retry only on a subsequent requested run. Preserve attempts and cumulative costs. Reports contain IDs/scores/statuses, not essays, paths, secrets or raw errors.
14. **Frontend workflow.** Keep the bank outside Workspace/Builder, while reusing autosave primitives. Use `delay=1000`, a selected-sample editor keyed by UUID, durable ACK before selection/tab/Complete-and-next/image/export transitions, and local drafts retained after failure/conflict. Disable edits during explicit transitions; a delayed response must not overwrite newer local typing or another sample. Ctrl/Cmd+S flushes; Ctrl/Cmd+Enter flushes, completes, then selects the next persisted incomplete row only after success. No 200-form rendering.

## Validation conventions for the tasks below

- Commands are **future implementation commands**, not claims that tests already ran. Backend commands run from `backend/`; frontend commands from `frontend/`; Git commands from repository root.
- For integration/migration/race coverage, configure both `DATABASE_URL` and `TEST_DATABASE_URL` to an explicitly isolated PostgreSQL test target. Never reset or migrate production. The normal rollback fixture is unsuitable for a genuine multi-connection race because its outer transaction can retain advisory locks; Task 2 supplies a separate temporary PostgreSQL schema/independent-session fixture with cleanup.
- Write the listed regression assertions first. RED must demonstrate the missing behavior, not an unrelated test setup error; use API 404s, missing model/table assertions or imports inside individual tests for initially absent modules.
- No full local suites during normal iteration, browser/Playwright/E2E, dev server, production build, live LLM/ASR/GPU, Modal or new service. Focused fake-provider tests establish contracts/plumbing, not measured model accuracy.
- Recheck main/head before implementation and record any new remote baseline failure. Do not start feature work on an unexplained baseline regression. This planning run does not repair production code.

---

### Task 1: Extract shared Writing score metrics without changing Task 1

**Files:**

- Create `backend/app/evaluation/writing/__init__.py` and `metrics.py`.
- Create `backend/tests/test_writing_benchmark_metrics.py`.
- Modify `backend/app/evaluation/task1/metrics.py` and `backend/tests/test_task1_benchmark_metrics.py`.
- Modify `backend/app/evaluation/task1/runner.py` and `backend/tests/test_task1_benchmark.py` to cover the newly shared dependency in cache identity.

**Interfaces:** Move `score_metrics(pairs, *, minimum_qwk_samples=10)` unchanged into the shared module. Expose `overall_score(scores, *, traits=("ta","cc","lr","gra"))` using production aggregation; Task 2 can supply `("tr","cc","lr","gra")`. Deliberately re-export both from Task 1 for import compatibility. Keep perception helpers and `perception_metrics` in Task 1. Do not change Speaking metrics or add correlations.

- [ ] **RED tests:** Shared import/Task 1 alias parity; hand-calculated exact/±0.5/±1/bias/MAE/RMSE/QWK; all 19 bins; empty, too-small and zero-variance populations; preserve non-half-band arithmetic without quantizing QWK labels; Task 1/Task 2 overall mappings and production tie rounding. The existing dependency-hash test must also detect edits to the extracted shared metric file.
- [ ] **RED command:** `uv run pytest tests/test_writing_benchmark_metrics.py tests/test_task1_benchmark_metrics.py -q`.
- [ ] **Minimal implementation:** Move only score arithmetic, parameterize trait selection for overall, retain the existing metric keys/QWK statuses/minimum count. Extend Task 1 `implementation_hash()` patterns with `evaluation/writing/*.py`; it currently only includes `evaluation/task1/*.py` for evaluation code. No second QWK implementation.
- [ ] **GREEN command:** `uv run pytest tests/test_writing_benchmark_metrics.py tests/test_task1_benchmark_metrics.py tests/test_task1_benchmark.py -q`.
- [ ] **Commit:** `Share Writing benchmark score metrics`.

### Task 2: Add the single sample model, migration and race-safe repository

**Files:**

- Create `backend/app/models/writing_benchmark.py`.
- Modify `backend/app/models/enums.py` and `backend/app/models/__init__.py`.
- Create `backend/alembic/versions/20261013_0035_writing_benchmark_bank.py` (reconfirm parent first).
- Create `backend/app/repositories/writing_benchmark.py`.
- Create `backend/tests/benchmark_helpers.py`, `test_writing_benchmark_models.py`, and `test_writing_benchmark_migration.py`.
- Modify `backend/tests/conftest.py` only for the new conditional rollback schema path; do not replace its transaction/auth fixtures.

**Interfaces:** `WritingBenchmarkSample`, `WritingBenchmarkStatus`, `WritingBenchmarkSplit`; repository `lock_task_capacity(task_number)`, `allocate_slot(task_number)`, `get(sample_id, lock=False)`, `list_rows(task_number)`, `complete_rows(lock_shared=False)`, and `summary_labels()`. Use a fixed namespaced `pg_advisory_xact_lock(namespace, task_number)` in the create/delete transaction; always acquire capacity lock before the sample row lock when both are needed.

- [ ] **RED tests:** Model registration in `Base.metadata`; named unique/task/slot/type/half-band/COMPLETE/revision constraints; nullable DRAFT labels; no human-overall column; Task 2 rejects Task 1 fields; direct SQL cannot allocate slot 101/duplicate slot/6.3 or 6.49 label/invalid COMPLETE; stable codes and gap reuse with new UUID. Real migration upgrade/downgrade/re-upgrade touches only the new table/types.
- [ ] **RED command:** `uv run pytest tests/test_writing_benchmark_models.py tests/test_writing_benchmark_migration.py -q`.
- [ ] **Minimal implementation:** One table with UUID/timestamps, slot, task, status/split, exact prompt/essay, nullable Task 1 type/key, four nullable Numeric labels, bounded source note, false-default redistribution flag and nonnegative technical revision. Mirror schema/service rules in named SQL constraints where possible. Freeze allowed Task 1 type values in the new migration; do not import changing runtime registries into historical migrations.
- [ ] **Race fixture:** Add a helper creating a unique temporary PostgreSQL schema on the explicit test database and independently committed connections; apply the actual new migration there. Do not use the shared rollback connection for contention tests or `Base.metadata.create_all` over all application tables. Clean the temporary schema in `finally`; report skipped race coverage as a limitation, never a pass.
- [ ] **GREEN command:** `uv run pytest tests/test_writing_benchmark_models.py tests/test_writing_benchmark_migration.py -q`; inspect one head with `uv run alembic heads`. Fresh full upgrade on a separate empty PostgreSQL test target is required again in Task 14.
- [ ] **Commit:** `Add Writing benchmark sample persistence`.

### Task 3: ADMIN-only CRUD, capacity and explicit completeness

**Files:**

- Create `backend/app/schemas/writing_benchmark.py`.
- Create `backend/app/services/writing_benchmark.py`.
- Create `backend/app/api/v1/writing_benchmark.py` and modify `backend/app/api/v1/router.py`.
- Create `backend/tests/test_writing_benchmark_api.py` and `test_writing_benchmark_capacity.py`.
- Extend `backend/tests/benchmark_helpers.py` for fictional bank fixtures and role clients.

**Interfaces:** `BenchmarkSampleCreate`, `BenchmarkSamplePatch`, `BenchmarkSampleDetail`, `BenchmarkSampleListItem`, `BenchmarkMutation(expected_revision)`, `BenchmarkCompletionFailure`; `WritingBenchmarkService.create/patch/complete/delete/detail/list`. `completion_issues(sample)` returns safe field-path issues. Reuse production score/type validators and revision behavior; publish numeric nullable score/overall DTO fields, not Decimal strings. Add router paths listed above; image/export/summary routes follow in later tasks.

- [ ] **RED tests:** ADMIN success; anonymous 401 and USER/TEACHER 403 for direct APIs; empty/partial DRAFT saves; exact CRLF/emoji/whitespace preservation; invalid/out-of-range/non-finite/6.3 labels rejected; unknown/forged server fields rejected; immutable task/slot; Task 1 Complete without image rejected; Task 2 all labels required; derived overall matches production at ties; invalidating a COMPLETE row demotes it; stale revision rejected without overwrite.
- [ ] **Capacity RED:** Fill 100 slots including DRAFTs; 101st returns a safe 409. Race two creates at 99 using independent transactions: one succeeds, one gets capacity error, exactly 100 rows remain. Also race initial creation: distinct slots/UUIDs. Deleting slot 37 never renumbers 38; a new record can reuse 37 with new UUID. Task 2 capacity remains independent.
- [ ] **RED command:** `uv run pytest tests/test_writing_benchmark_api.py tests/test_writing_benchmark_capacity.py -q`.
- [ ] **Minimal implementation:** Routers use `AdminUser`; services own begin/lock/validate/flush/commit. Explicit Complete is separate from partial PATCH. For Task 1 success fixtures, seed a backend-owned valid private image; do not make the public PATCH accept paths. Completion errors carry only fixed messages/field paths, not submitted content or SQL/provider internals. Default source note remains nullable; no author/rater account schema.
- [ ] **GREEN command:** `uv run pytest tests/test_writing_benchmark_api.py tests/test_writing_benchmark_capacity.py -q`.
- [ ] **Commit:** `Add admin Writing benchmark authoring API`.

### Task 4: Private Task 1 image lifecycle through existing storage

**Files:**

- Modify `backend/app/storage/local.py` (and `storage/__init__.py` only if an export is needed).
- Extend `backend/app/services/writing_benchmark.py` and `api/v1/writing_benchmark.py`.
- Create `backend/tests/test_writing_benchmark_images.py` and extend `benchmark_helpers.py`.
- Modify `backend/tests/test_storage.py` for unchanged generic image/audio behavior; existing cloning regressions are in `backend/tests/test_asset_cloning.py`.

**Interfaces:** `LocalAssetStorage.store_benchmark_writing_image(sample_id, mime_type, original_name, content, max_bytes)`, narrowly reused destination/image-validation internals, and service `replace_image/remove_image/image_content`. Private `owns_image_key(sample_id,key)` guards every resolve/cleanup/export. Image mutations require `expected_revision`; upload uses multipart `file` and revision. GET image returns an authenticated `FileResponse`, safe code-derived filename and `Cache-Control: no-store`.

- [ ] **RED tests:** Valid PNG/JPEG/WebP including JPEG extension compatibility; spoofed/unsupported MIME/extension/signature, empty/oversized upload and Task 2 image rejected; server-generated immutable namespace; no raw key DTO and no anonymous/generic Asset access; role denial on GET/POST/DELETE image. Missing file blocks Complete. Removing image atomically demotes COMPLETE. Replace preserves previous valid image if DB update fails, deletes only the new uncommitted file, and obsolete cleanup after commit cannot delete the current image. Race replace/remove/delete and stale revision/lost ACK cases. Malicious traversal/symlink/unrelated-asset keys cannot be served or deleted.
- [ ] **RED command:** `uv run pytest tests/test_writing_benchmark_images.py -q`.
- [ ] **Minimal implementation:** Keep existing images/audio behavior; do not pass a benchmark directory as generic `category`. Add one server-controlled namespace path inside `LocalAssetStorage`, reuse current guards and trusted-image signature validation. Limit upload reads to maximum+1 bytes. Lock/revision-check mutations and follow the approved cleanup ordering. File I/O goes through the existing storage abstraction, with bounded safe diagnostics for best-effort cleanup failure.
- [ ] **GREEN command:** `uv run pytest tests/test_writing_benchmark_images.py tests/test_storage.py tests/test_asset_cloning.py -q`.
- [ ] **Commit:** `Add private Writing benchmark image lifecycle`.

### Task 5: Lightweight summary and distribution guidance

**Files:**

- Extend `backend/app/schemas/writing_benchmark.py`, `repositories/writing_benchmark.py`, `services/writing_benchmark.py`, and `api/v1/writing_benchmark.py`.
- Create `backend/tests/test_writing_benchmark_summary.py`.

**Interfaces:** `BenchmarkBankSummary`, `BenchmarkTaskSummary`; repository `summary_labels()` selects task/status/split/four scores only; service `summary()` computes counts and production-rounded histograms. `GET /summary` is ADMIN-only. Guidance constants live with benchmark domain/service logic, not a new scoring rule.

- [ ] **RED tests:** Drafts consume total capacity but never count toward complete histogram/split targets; zero-data summary; per-task isolation; all lower/upper valid bands and production rounding; exact target counts sum 100; split targets 80/20; no quota affects save/Complete; summary/list contain no prompt/essay/image key; role denial.
- [ ] **RED command:** `uv run pytest tests/test_writing_benchmark_summary.py -q`.
- [ ] **Minimal implementation:** Return bounded 19-bin actual counts plus nullable suggested target by band; total/draft/complete and complete DEV/HOLDOUT counts. Do not load all essay bodies, cache duplicate overall or add mandatory criterion histograms.
- [ ] **GREEN command:** `uv run pytest tests/test_writing_benchmark_summary.py tests/test_writing_benchmark_api.py -q`.
- [ ] **Commit:** `Add Writing benchmark distribution summary`.

### Task 6: Define strict Task 2 JSONL contracts before export

**Files:**

- Create `backend/app/evaluation/task2/__init__.py`, `models.py`, and `manifest.py`.
- Create `backend/tests/test_task2_benchmark_contracts.py`.

**Interfaces:** Task 2 `HumanScores(tr,cc,lr,gra)`, `BenchmarkSample`, `BenchmarkConfig`, `EvaluationRecord`, `LoadedSample`, `load_manifest(path,split,limit)`, and safe fixed-code `BenchmarkInputError`. Use `schema_version: 1` as file format only, safe ASCII IDs, exact bounded prompt/essay, half bands, one-rater metadata, nonblank provenance and strict bool redistribution. Task 2 records contain no visual/image/specialist fields. Completed records require all four valid predictions; failed records may preserve completed criteria and must retain failures; derive both overalls via shared production arithmetic.

- [ ] **RED tests:** Extra/visual/score-inconsistent fields, invalid half bands and missing labels rejected; Task 2 uses `tr`, not manifest `ta`; exact strings, split/limit/duplicate IDs, manifest size limits and safe invalid-file diagnostics; blank content rejected; no CSV reader. Numeric human labels and schema defaults round-trip. Configuration identity contains effective Task 2 prompt/model/runtime identity without endpoint secrets; file-format version does not become bank metadata.
- [ ] **RED command:** `uv run pytest tests/test_task2_benchmark_contracts.py -q`.
- [ ] **Minimal implementation:** Separate text-only contracts and local JSONL loader, bounded like Task 1. Preserve Task 1 `BenchmarkSample` and historical configs. Do not import app API/DB workers just to construct a sample or compute an identity.
- [ ] **GREEN command:** `uv run pytest tests/test_task2_benchmark_contracts.py tests/test_task1_benchmark.py -q`.
- [ ] **Commit:** `Define Task 2 Writing benchmark manifests`.

### Task 7: Deterministic compatible ZIP, JSONL and convenience CSV export

**Files:**

- Create `backend/app/services/writing_benchmark_export.py`.
- Extend `backend/app/api/v1/writing_benchmark.py` and repository export snapshot query.
- Create `backend/tests/test_writing_benchmark_export.py`.

**Interfaces:** `WritingBenchmarkExportService.export(path)`; pure `task1_manifest_sample(row,image_path)`, `task2_manifest_sample(row)`, `write_csv(rows,task_number)`, and `manifest_schema()`. GET `/export` returns `writing-benchmark.zip`, using the existing temporary-file/background-cleanup delivery pattern. Task 1 mapper instantiates CURRENT `evaluation.task1.models.BenchmarkSample`, not a parallel export schema. Task 2 mapper uses Task 6 model.

- [ ] **RED tests:** Export at 0/1/<100 samples; drafts excluded; exact six root files and `images/`; stable task/slot ordering/code/image names; Task 1 exported lines validate directly through current model and `load_manifest` using generated images; Task 2 lines validate through its loader. Always raters=1, false default redistribution, null visual truth and neutral nonblank source fallback with no invented license claim. Decimal half-band labels serialize as numeric JSON. CSV quoted commas/quotes/multiline CRLF/Unicode preserve exact content and derived overall.
- [ ] **Safety RED:** Traversal/absolute/foreign-storage keys and hostile filenames cannot become ZIP entry names or leak unrelated files; missing invalid completed images fail safely; replace/delete during export cannot mix row/image states; temporary ZIP is removed after delivery/failure; identical snapshots yield identical ordered contents (byte-for-byte ZIP timestamp equality unnecessary). USER/TEACHER/anonymous export denied. No predictions/report files inside bank export.
- [ ] **RED command:** `uv run pytest tests/test_writing_benchmark_export.py -q`.
- [ ] **Minimal implementation:** Generate names from validated task/slot/MIME extension only, never archive user paths. Shared-lock the selected rows while staging ZIP contents in a tempfile; copy validated owned images before releasing locks. Use stdlib JSON/CSV/ZIP and Pydantic-generated combined schema with valid references. Include both manifests/CSVs even when one task is empty. Reuse the authenticated file-response cleanup pattern; handle cancellation without deleting live assets.
- [ ] **GREEN command:** `uv run pytest tests/test_writing_benchmark_export.py tests/test_task2_benchmark_contracts.py tests/test_task1_benchmark.py -q`.
- [ ] **Commit:** `Export the admin Writing benchmark bundle`.

### Task 8: Task 2 production-backed runner and score-only reports

**Files:**

- Create `backend/app/evaluation/writing/runtime.py` and `checkpoints.py`.
- Create `backend/app/evaluation/task2/runner.py` and `report.py`.
- Modify `backend/app/evaluation/task1/runner.py` only to reuse/re-export extracted content-free provider-count/checkpoint helpers.
- Create `backend/tests/test_task2_benchmark.py` and `test_task2_benchmark_reports.py`; extend `test_task1_benchmark.py` only for extraction compatibility assertions.

**Interfaces:** Shared `CountedProvider`, `atomic_write`, `save_attempt`, `cached_record(...,record_type=...)`, `attempt_history(...,record_type=...)`; Task 2 `configuration(settings,max_concurrent_llm_requests)`, `implementation_hash()`, `fingerprint(item,config)`, `evaluate(...)`, `run_benchmark(...)`; report `aggregate/build_report/markdown_report/write_report`. Keep specialist/perception/Task 1 ablation logic in Task 1.

- [ ] **RED tests:** Fake production Task 2 assessment maps `ta` events/results to `tr`; target/source-note/redistribution fields never enter provider payloads. Changing human labels alone produces identical provider requests while invalidating the evaluation cache; do not use coincidental numeric substring matching as a leakage test. Scoring input contains only prompt/exact essay and deterministic internal IDs with textarea provenance. No DB engine/auth/API worker or chart provider needed. Bounded peak requests reflect config 1..4; samples do not multiply that limit. All valid predictions remain unadjusted.
- [ ] **Report RED:** TR/CC/LR/GRA/overall metric values equal the shared implementation exactly; partial completed criteria contribute comparable pairs, missing predictions do not fabricate scores/overall; failed samples remain in denominator and safe record/failure list. Split/target-band strata, QWK unavailable reasons, signed bias, latency, request counts and available token usage; report/CSV never reproduce source text or raw provider errors. First-attempt/all-attempt failures and cumulative cost remain after retry-to-success; cache hits are excluded from new-call counts.
- [ ] **RED command:** `uv run pytest tests/test_task2_benchmark.py tests/test_task2_benchmark_reports.py -q`.
- [ ] **Minimal implementation:** Invoke `MTSWritingScoringService.assess` with current effective prompt identity and its existing concurrency/relevance behavior, not `WritingAIWorker`/Attempt persistence. Build target data only after inference for metrics. Reuse shared score arithmetic and the minimal typed checkpoint/provider-count primitives; never call Task 1 visual runner for Task 2. Include shared runtime/checkpoint files in both evaluators' implementation hashes. For Task 2, reconcile token totals from the service's safe usage records when provider failures supply usage; never double-count the same completion or invent unavailable usage. Preserve Task 1 outputs/old helpers and do not add an experiment tracker or benchmark DB result table.
- [ ] **GREEN command:** `uv run pytest tests/test_task2_benchmark.py tests/test_task2_benchmark_reports.py tests/test_task1_benchmark.py tests/test_writing_score_first.py tests/test_writing_concurrency.py -q`.
- [ ] **Commit:** `Add production-backed Task 2 benchmark evaluation`.

### Task 9: Task 2 CLI, resumability and safe offline execution

**Files:**

- Create `scripts/benchmark_task2.py`.
- Create `backend/tests/test_task2_benchmark_cli.py` and `test_task2_benchmark_resume.py`.
- Extend `backend/app/evaluation/task2/runner.py` only for CLI/cache cases exposed by these tests.

**Interfaces:** `main(argv=None)` flags `--manifest`, required `--split dev|holdout`, `--limit`, `--dry-run`, `--resume`, `--output`, `--max-concurrent-llm-requests 1..4`. Default output under ignored `benchmarks/writing_task2/reports/`. Exit codes follow Task 1: 0 successful/dry-run, 1 evaluated failures, 2 input/config failure, 130 explicit interruption. No automatic whole-sample retries or live calls in tests.

- [ ] **RED tests:** CLI argument bounds, invalid/CSV/empty selection, safe stdout/stderr, dry-run creates no provider, root and backend invocation compatibility, no production DB/auth configuration required. Fake-provider runner tests prove changed essay/prompt/labels/split/model/provider/effective prompt/paragraph provenance/implementation/timeouts invalidate cache. Path/presentation-label changes alone need not invalidate semantic identity. Corrupt/inconsistent checkpoints and failed attempts never count as successful resume hits.
- [ ] **Resume RED:** Interrupt after one success; previous success resumes, failure retries on a later invocation, all attempts remain; recovery from validated completed attempt after torn checkpoint; incomplete records/incorrect derived overalls are rejected; reports stay available with INTERRUPTED/failure status. No secret endpoint/API key in cache keys/records/logs and no human labels in inference requests after resume miss.
- [ ] **RED command:** `uv run pytest tests/test_task2_benchmark_cli.py tests/test_task2_benchmark_resume.py -q`.
- [ ] **Minimal implementation:** Adapt Task 1's safe CLI entry conventions, current provider configuration and typed atomic checkpoints, while keeping Task 2 independent of perception. `schema_version: 1` is a format field, not an exposed bank version. Preserve script `noqa: E402` exceptions after adding backend to `sys.path`.
- [ ] **GREEN command:** `uv run pytest tests/test_task2_benchmark_cli.py tests/test_task2_benchmark_resume.py tests/test_task1_benchmark.py -q`.
- [ ] **Commit:** `Add resumable Task 2 benchmark CLI`.

### Task 10: Frontend API/Zod contracts and binary/image clients

**Files:**

- Create `frontend/src/lib/api/writing-benchmark.ts`.
- Create `frontend/tests/writing-benchmark-api.test.ts`.

**Interfaces:** `benchmarkSampleSchema`, lightweight list/summary schemas, partial PATCH and structured completion issue schemas; `getWritingBenchmarkSummary/listWritingBenchmarkSamples/getWritingBenchmarkSample/createWritingBenchmarkSample/updateWritingBenchmarkSample/completeWritingBenchmarkSample/deleteWritingBenchmarkSample/uploadWritingBenchmarkImage/removeWritingBenchmarkImage/exportWritingBenchmarkBundle`. Use injectable `ApiRequester` for JSON calls; use existing `apiResponse` for authenticated ZIP and appropriate image request/URL conventions. Retain numeric nullable labels and backend-derived overall.

- [ ] **RED tests:** Correct exact paths/methods/query/body/revision, numeric half bands and null DRAFT fields, Task 1-only image/type handling, list lacks full content, completion errors retain field paths via `ApiError.details`, multipart file/revision without manual multipart Content-Type, private preview URL has no raw key, ZIP response/filename and failure behavior. Reject forged overall/task/slot/key writes. No `/assets/images` upload with fabricated TestVersion.
- [ ] **RED command:** `npx vitest run tests/writing-benchmark-api.test.ts`.
- [ ] **Minimal implementation:** One typed HTTP module aligned with backend DTOs, reuse shared session-aware client and existing binary download behavior. Do not add a CSV parser, data version selector or frontend database access.
- [ ] **GREEN command:** `npx vitest run tests/writing-benchmark-api.test.ts tests/admin-api.test.ts`; then `npm run typecheck`.
- [ ] **Commit:** `Add typed admin Writing benchmark clients`.

### Task 11: Admin master/detail editor, autosave and private image controls

**Files:**

- Create `frontend/src/app/admin/writing-benchmark/page.tsx`.
- Create `frontend/src/features/writing-benchmark/bank-page.tsx`, `sample-list.tsx`, `sample-editor.tsx`, `image-field.tsx`, and `bank.module.css`.
- Modify `frontend/src/features/auth/admin-content.tsx` for the admin entry link.
- Modify `frontend/src/lib/i18n/en.ts` and `vi.ts`.
- Create `frontend/tests/writing-benchmark-page.test.tsx` and `writing-benchmark-autosave.test.tsx`; extend `admin-dashboard.test.tsx` for link visibility.

**Interfaces:** `WritingBenchmarkBankPage`, `BenchmarkSampleList`, `BenchmarkSampleEditor`, `BenchmarkImageField`, a small page-specific draft→PATCH helper and numeric presentation-only overall helper. Reuse `AdminLayout`, `AdminGuard`, `PageHeading`, `BuilderLifecycleProvider/useBuilderAutosave` with resource key `writing-benchmark:<uuid>` and 1000-ms delay, and `ConfirmDialog`. Reuse the provider's `runTransition/flushAutosaves` barriers; do not use `beginDelete` to permanently disable the entire bank. No shared Builder hook refactor is required unless a focused regression demonstrates it is necessary.

- [ ] **RED tests:** ADMIN page/link; USER/TEACHER blocked including direct route; Task tabs, lightweight list and selected detail only; stable code/split/state/overall; creation disabled at total 100 even with many drafts; backend capacity race error recovers list state. Fake timers show one save after stable 1000-ms input; edits during an in-flight save remain; rejected autosave/conflict preserves local form; Retry/Save now; exact newline/Unicode input; stale response cannot replace another selected UUID.
- [ ] **Transition RED:** Ctrl/Cmd+S immediate flush and prevent default; Ctrl/Cmd+Enter does not select next incomplete until latest PATCH ACK and Complete ACK; validation/save failures remain on current editor with field errors/local content. Tab/selection changes flush safely before unmount; no accidental auto-Complete. Confirmed Delete/image removal wait for durable mutation success, retain errors when rejected, and never leave an image-less COMPLETE UI row. Preview/replace/remove target current UUID/revision only.
- [ ] **Presentation RED:** EN/VI labels including task types, first criterion TA/TR, status and actions; semantic labels/buttons/tabs, current row/state visible beyond color, focus restoration and dialog keyboard behavior. Narrow-screen layout stacks list/detail using `min-width:0`, wrapping and bounded grid columns; no hard fixed-width page overflow. Respect existing reduced-motion/theme tokens. Structural/unit tests plus CSS review; no local browser claim.
- [ ] **RED command:** `npx vitest run tests/writing-benchmark-page.test.tsx tests/writing-benchmark-autosave.test.tsx`.
- [ ] **Minimal implementation:** One selected editor, local drafts keyed by UUID, revision refs updated only from matching successful responses, reuse autosave drain and dialog infrastructure. Draft validity permits missing required content; Complete enforces backend issues. Show subtle localized save state. Present client overall only as provisional convenience and replace it with server-derived value after ACK; numeric half-band arithmetic must match production tie fixtures. Use unoptimized authenticated image delivery, as in the current Writing Builder, rather than a public Next image-optimizer proxy. Render safe image upload/preview controls and no bank/dataset/rater UI.
- [ ] **GREEN command:** `npx vitest run tests/writing-benchmark-page.test.tsx tests/writing-benchmark-autosave.test.tsx tests/builder-autosave.test.tsx tests/writing-builder.test.tsx tests/admin-dashboard.test.tsx`; `npm run typecheck`.
- [ ] **Commit:** `Add admin Writing benchmark master-detail editor`.

### Task 12: Distribution and export UI integration

**Files:**

- Create `frontend/src/features/writing-benchmark/distribution.tsx` and `export-button.tsx`.
- Modify `bank-page.tsx`, `bank.module.css`, `frontend/src/lib/i18n/en.ts`, and `vi.ts`.
- Create `frontend/tests/writing-benchmark-distribution.test.tsx` and `writing-benchmark-export.test.tsx`.

**Interfaces:** `BenchmarkDistribution(summary)` renders actual/suggested overall counts and complete split guidance; `BenchmarkExportButton` flushes current edits, refreshes summary, presents complete/draft/split counts and invokes the single ZIP action. Use existing dialog semantics when presenting the export summary and existing download/object-URL cleanup pattern.

- [ ] **RED tests:** Exact 11 suggested targets/100 total; COMPLETE-only histogram and split counts; lower bands/above-target counts remain legitimate; no distribution blocking Complete/export; Task 1/Task 2 progress independent. Export available before full capacity, drafts explicitly excluded, empty/partial bank summary, dirty form flushes before export; failed save/export preserves form and permits retry; one authenticated bundle download and object URL released. EN/VI copy and keyboard focus/reduced-motion/narrow layout semantics.
- [ ] **RED command:** `npx vitest run tests/writing-benchmark-distribution.test.tsx tests/writing-benchmark-export.test.tsx`.
- [ ] **Minimal implementation:** Use server summary, not a download of 200 essays or a separately stored overall. Show guidance as advice; no color-only status, dataset versions or prediction metrics in app. Keep criterion histograms out of the P0 implementation.
- [ ] **GREEN command:** `npx vitest run tests/writing-benchmark-distribution.test.tsx tests/writing-benchmark-export.test.tsx tests/writing-benchmark-page.test.tsx`; `npm run typecheck`.
- [ ] **Commit:** `Add benchmark distribution and bundle export controls`.

### Task 13: Documentation, schema publishing and Colab instructions

**Files:**

- Create `docs/writing-benchmark-bank.md`.
- Modify `docs/ai-writing.md` and `benchmarks/writing_task1/README.md`.
- Create `benchmarks/writing_task2/README.md`, `manifest.schema.json`, `private/.gitkeep`, and `reports/.gitkeep`.
- Modify `.gitignore` with Task 2 private data/reports/cache/attempt rules following Task 1; explicitly allow the two `.gitkeep` files through directory ignore rules.
- Extend `backend/tests/test_writing_benchmark_export.py` and `test_task2_benchmark_cli.py` for README/schema/offline-smoke contracts.

**Interfaces:** Generated Task 2 schema equals its model's JSON schema; exported README uses actual CLI flags, backend/root execution conventions and current Task 1 v12/Task 2 effective prompt labels. Keep `schema_version:1` explicitly a file-format compatibility field.

- [ ] **RED tests:** Exported root files/schema references match shipped models; README commands contain actual supported flags and safe relative manifest/image paths; fake/dry-run one-sample workflow executes with no production DB/JWT/session and no live provider. Private fixture/report paths remain ignored; no essay/image/real labels become tracked data. Preserve Task 1 manifest/test imports and historical version accessibility.
- [ ] **RED command:** `uv run pytest tests/test_writing_benchmark_export.py tests/test_task2_benchmark_cli.py -q`.
- [ ] **Minimal documentation:** Explain ADMIN → ZIP → Colab upload → clone/install backend deps → unzip → provider secrets → separate Task 1/Task 2 CLI → reports. Include dry-run and manual one-sample inference commands but do not execute live inference. Show Task 1 v12 and Task 2 current prompt config, DEV/HOLDOUT hygiene, one-rater metadata, neutral source note, false-default redistribution, and provider content disclosure. No production PostgreSQL credentials, admin JWT, direct API ingestion, prediction DB, automatic calibration, new GPU deployment or required notebook app integration.
- [ ] **GREEN command:** `uv run pytest tests/test_writing_benchmark_export.py tests/test_task2_benchmark_cli.py tests/test_task1_benchmark.py -q`; inspect tracked/ignored paths with `git status --short` and `git check-ignore` for fictional temporary paths only.
- [ ] **Commit:** `Document Writing benchmark export and Colab evaluation`.

### Task 14: Focused integrated regression, fresh migration and remote CI gate

**Files:**

- Modify `backend/tests/test_writing_benchmark_export.py` for `test_bank_bundle_fake_cli_pipeline` and production-record isolation assertions.
- Modify `frontend/tests/writing-benchmark-page.test.tsx` for any missing integrated authoring/ACK assertions.
- Modify `docs/writing-benchmark-bank.md` with actual validation results when implementation finishes.
- A reproduced introduced failure may require its exact owning implementation/test file from Tasks 1–13; record that file and focused reproducer before repair. Do not change unrelated Speaking/Writing scoring.

**Interfaces:** Full data-bank → canonical bundle → fake Task 1/Task 2 CLI path; no learner Attempt/grade/AI-run writes; no bank prediction persistence. CI workflow remains unchanged unless a demonstrated feature-specific test-discovery requirement demands a minimal edit.

- [ ] **RED integrated test:** Add an ADMIN-owned fictional Task 1 and Task 2, autosave incomplete content, demonstrate rejected completion without image/labels, upload/label/Complete, export, consume both current loaders, fake-score and verify report outputs. Assert forbidden roles, 101st-race protection, independent stable slots, removal demotion, production overall parity, draft exclusion, no path escape, label leakage, shared metrics, invalidated resume and visible failures. Prove learner/history/final-grade rows are untouched and no prediction table/model exists. Add missing assertions before implementation/fix.
- [ ] **RED command:** `uv run pytest tests/test_writing_benchmark_export.py::test_bank_bundle_fake_cli_pipeline -q`; use `npx vitest run tests/writing-benchmark-page.test.tsx` for missing authoring assertions.
- [ ] **Minimal repair:** Fix the deterministic cause in its owning layer. Retain the approved bank boundaries, current Task 1/2 scoring contracts, existing Task 1 historical compatibility and all migration history.
- [ ] **Backend GREEN (focused feature files):**

  ```powershell
  uv run pytest tests/test_writing_benchmark_metrics.py tests/test_writing_benchmark_models.py tests/test_writing_benchmark_migration.py tests/test_writing_benchmark_api.py tests/test_writing_benchmark_capacity.py tests/test_writing_benchmark_images.py tests/test_writing_benchmark_summary.py tests/test_writing_benchmark_export.py tests/test_task2_benchmark_contracts.py tests/test_task2_benchmark.py tests/test_task2_benchmark_reports.py tests/test_task2_benchmark_cli.py tests/test_task2_benchmark_resume.py tests/test_task1_benchmark_metrics.py tests/test_task1_benchmark.py -q
  ```

- [ ] **Frontend GREEN (focused feature files):**

  ```powershell
  npx vitest run tests/writing-benchmark-api.test.ts tests/writing-benchmark-page.test.tsx tests/writing-benchmark-autosave.test.tsx tests/writing-benchmark-distribution.test.tsx tests/writing-benchmark-export.test.tsx tests/builder-autosave.test.tsx tests/writing-builder.test.tsx tests/admin-dashboard.test.tsx
  npm run typecheck
  ```

- [ ] **Targeted lint/format:** From `backend/`, run `uv run ruff check` and `uv run ruff format --check` on changed/new backend paths and touched `../scripts/...` paths. Do not run script autofixes from a different root/config and remove the required E402 exceptions. From `frontend/`, run `npx eslint` on the touched frontend files only.
- [ ] **Fresh PostgreSQL GREEN:** On an explicitly isolated empty test database, run `uv run alembic upgrade head`; verify exactly one head with `uv run alembic heads` and `ScriptDirectory.get_heads()`. Run the actual new revision's migration/race tests on real PostgreSQL; compare model constraints/defaults with the migration. No production database reset.
- [ ] **Git/CI gate:** Run `git diff --check`; inspect intended file scope and no source-data tracking. Commit the completed integration or any small regression repair (`Verify Writing benchmark bank integration` when a final commit is needed), push without force, and inspect CI plus Golden path E2E if triggered for the exact final SHA. Read failing job logs, run only the relevant focused local reproducer, fix, commit and push again until required CI is green. Record actual pass counts, migration head, SHA, workflow links/status and clean worktree; no unrun/live-model accuracy claim.
- [ ] **Commit boundary:** Finish the feature only after focused checks and the exact pushed SHA's required CI are green. Earlier task commits remain independently reviewable.

## Acceptance review checklist

- [ ] One bank, one table, no datasets/versions/raters/adjudication/experiment or prediction storage.
- [ ] ADMIN-only frontend and every backend CRUD/summary/image/export action; direct USER/TEACHER access denied.
- [ ] DRAFT permits partial content; supplied half bands always valid; Complete/image removal cannot leave an invalid completed record.
- [ ] Capacity includes drafts; database constraints and real 101st-create race test enforce 100 per task.
- [ ] UUID/slot identities stable; delete never renumbers neighbors; reuse gets new UUID.
- [ ] Overall matches production four-criterion mean/rounding, not weighted full Writing, and is never stored twice.
- [ ] Images use existing storage with private owned immutable keys, safe MIME/size/signature/path handling and commit-safe cleanup.
- [ ] Lightweight summary/list, complete-only distribution, exact guidance totals and 80/20 advisory split; lower valid bands remain accepted.
- [ ] Export works before 100/100, excludes drafts, has deterministic IDs/order/paths, direct CURRENT Task 1 model compatibility, Task 2 strict contract, raters=1, safe provenance and multiline CSV.
- [ ] Task 2 CLI is production-backed, database/auth independent, text-only, bounded and label-free at inference; same shared metrics with visible failures and robust identity/resume/attempt history.
- [ ] Autosave/shortcuts/transitions retain local content and wait for durable ACK; shared Builder, auth and annotation/paragraph behavior remain intact.
- [ ] EN/VI, semantic controls/focus/dialogs, responsive bounded layout and existing visual system.
- [ ] Fresh PostgreSQL migration, one Alembic head, focused validation and final exact-SHA remote CI green.

## Review decisions still required

None discovered. The approved choices determine product scope. The storage namespace, technical row revision, explicit Complete operation, metric extraction and Task 2 trait adapter are implementation details resolved above from current code. The only approval still needed is the user's review of this plan before any implementation begins.
