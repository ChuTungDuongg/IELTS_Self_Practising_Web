# Admin Writing Benchmark Bank Design

## Status

Conversational design approved on 2026-10-13; written specification awaiting final user review before implementation planning.

This is an architectural extension that adds a single ADMIN-only Writing benchmark data bank to the existing application. The web application is responsible only for authoring, validating, storing and exporting labelled benchmark samples. Benchmark inference remains an offline/Colab CLI workflow and must reuse the repository's existing Writing evaluation metrics and Task 1 benchmark machinery rather than becoming a production background job.

## Goal

Provide one canonical Writing benchmark bank containing at most:

- 100 Academic Writing Task 1 samples;
- 100 Writing Task 2 samples.

Each sample is entered and labelled by one ADMIN. There is no dataset versioning, no v1/v2 bank concept, no multi-rater workflow and no adjudication subsystem.

The bank must support:

- fast ADMIN-only data entry outside Workspace/Builder;
- Task 1 prompt + image + essay + TA/CC/LR/GRA human labels;
- Task 2 prompt + essay + TR/CC/LR/GRA human labels;
- production-consistent derived overall bands;
- DEV/HOLDOUT split assignment;
- overall-band distribution guidance toward a balanced calibration set;
- draft autosave and explicit completeness validation;
- ZIP export for Google Colab containing canonical JSONL, Task 1 images and convenience CSV copies;
- reuse of the existing Task 1 benchmark CLI;
- a Task 2 benchmark CLI using the same agreement/error metric definitions where applicable.

## Non-goals

This feature does not:

- create multiple benchmark datasets or dataset versions;
- add rater accounts, inter-rater reliability or adjudication;
- run 200-sample benchmarking from the production web application;
- write benchmark predictions, reports, latency results or experiment histories back into the production database;
- expose benchmark samples to USER or TEACHER roles;
- reuse ordinary learner Attempt/WritingTask/AttemptWritingScore records as benchmark ground truth;
- use CSV as the canonical benchmark input format;
- commit private/licensed essays or images into the Git repository;
- automatically tune, offset, cap or deploy AI scores from benchmark results.

## Current architecture to reuse

The repository already contains a substantial Task 1 evaluation stack under `backend/app/evaluation/task1/` plus `scripts/benchmark_task1.py`. Its local manifest contract contains a sample ID, `dev | holdout` split, Task 1 type, prompt, local image path, essay and TA/CC/LR/GRA human scores. Reports already include criterion/overall agreement metrics such as exact agreement, within ±0.5, within ±1.0, signed bias, MAE, RMSE and QWK, together with operational latency/failure/usage data and Task 1 perception diagnostics.

The existing Task 1 `BenchmarkSample` also carries benchmark-only metadata such as `raters`, `provenance` and `redistributable`. This new web bank has exactly one human labeler per sample; export therefore writes `raters=1` deterministically and maps the bank's source/provenance metadata into the existing manifest contract. The production database does not need to model individual raters.

The repository already has `LocalAssetStorage` and authenticated asset handling for PNG/JPEG/WebP files. Task 1 benchmark images should reuse this storage abstraction instead of storing image bytes/base64 in PostgreSQL.

Task 2 currently has production scoring but no equivalent dedicated benchmark CLI. This design adds a Task 2 evaluation path without duplicating the entire Task 1 perception-specific stack.

## 1. Admin route and access boundary

Add a standalone ADMIN page:

```text
/admin/writing-benchmark
```

It is outside Workspace/Builder and outside Teacher pages.

Both layers enforce ADMIN-only access:

- frontend route/presentation uses the existing admin authentication/guard conventions;
- every CRUD, image and export backend route uses `AdminUser` or the project's equivalent ADMIN dependency;
- hiding a nav item is never treated as authorization;
- USER/TEACHER direct API calls receive the repository's normal safe unauthorized response.

The page may be linked from the Admin area, but should remain a distinct benchmark-data tool rather than being embedded into Test Builder.

## 2. Single canonical bank and capacity

There is one logical benchmark bank only.

Capacity is fixed at:

```text
Task 1: maximum 100 samples
Task 2: maximum 100 samples
```

The backend enforces the limits transactionally; frontend disabling is only convenience. It must not be possible to create sample 101 by racing API requests or bypassing UI controls.

There is no `BenchmarkDataset` table, bank version, release entity or bank selector.

## 3. Persistence model

Create a dedicated benchmark-ground-truth model instead of reusing learner attempts.

Conceptually:

```text
WritingBenchmarkSample
- id: UUID primary key
- task_number: 1 | 2
- sequence_number: 1..100
- status: DRAFT | COMPLETE
- split: DEV | HOLDOUT
- prompt: text
- essay: text
- task1_task_type: nullable, Task 1 only
- task1_image_key: nullable, Task 1 only
- human_ta_tr: nullable decimal half-band
- human_cc: nullable decimal half-band
- human_lr: nullable decimal half-band
- human_gra: nullable decimal half-band
- source_note/provenance: nullable bounded text
- redistributable: boolean, default false
- created_at
- updated_at
```

Constraints:

- unique `(task_number, sequence_number)`;
- `sequence_number` between 1 and 100;
- criterion labels must be production-valid Writing half bands from 0 to 9;
- Task 1 may carry `task1_task_type`/image; Task 2 must not require them;
- a COMPLETE Task 1 requires prompt, essay, task type, image, split and all four labels;
- a COMPLETE Task 2 requires prompt, essay, split and all four labels;
- DRAFT permits partially entered fields needed for autosave;
- changing/removing a required field from a COMPLETE record demotes it to DRAFT or rejects an explicit COMPLETE update; the service must never leave an invalid COMPLETE record.

`human_overall` is deliberately not stored. It is derived by the same production Writing four-criterion aggregation/rounding helper used by scoring so database values cannot drift from displayed/exported totals.

Do not add separate Task 1 and Task 2 sample tables unless implementation constraints make the single typed model substantially less safe. The preferred model is one table with task-aware validation because the UI, distribution logic and export workflow are shared.

## 4. Human labelling semantics

Exactly one ADMIN enters the canonical human labels for a sample.

Task 1 labels:

```text
TA
CC
LR
GRA
```

Task 2 labels:

```text
TR
CC
LR
GRA
```

No written feedback is stored or required.

The UI presents criterion labels as controlled half-band selects/comboboxes, not arbitrary numeric text fields.

The displayed overall is read-only and derived live for convenience, but the backend recomputes it independently when presenting, validating and exporting data.

No AI-generated score may silently populate the canonical human fields. Ground truth is human-entered data.

## 5. DEV and HOLDOUT

Every sample has:

```text
DEV | HOLDOUT
```

This is not dataset versioning; it is evaluation hygiene inside the single bank.

The recommended target is approximately:

```text
80 DEV
20 HOLDOUT
```

per task.

DEV is used for iterative prompt/calibration investigation. HOLDOUT is reserved for final evaluation and should not be repeatedly inspected/tuned against.

The application shows split counts and guidance but does not automatically move samples between splits.

New samples may default to DEV for faster authoring.

## 6. Sample identity

Database identity is UUID.

Human-facing stable codes use task + slot:

```text
T1-001 ... T1-100
T2-001 ... T2-100
```

`sequence_number` is a stable slot, not array position. Deleting T1-037 must not renumber T1-038..T1-100. A future new sample may reuse the now-free 037 slot while receiving a new UUID.

Exports use the stable human-facing code as the benchmark sample `id` so reports remain easy to cross-reference with the admin bank.

## 7. Authoring UX

The page uses a master/detail editor rather than rendering 200 full forms.

Desktop concept:

```text
Writing Benchmark Bank
Task 1 63/100 complete   Task 2 41/100 complete

[Task 1] [Task 2]

Samples                    Selected sample
T1-001 ✓ 7.0               Prompt
T1-002 Draft               [textarea]
T1-003 ✓ 6.5               Image / task type
...                         Essay
[+ New sample]              [textarea]
                            Human labels
                            Derived overall
```

The sample list shows at least:

- stable code;
- DRAFT/COMPLETE status;
- derived overall when labels are complete;
- DEV/HOLDOUT state where useful.

On narrow screens, list and detail may stack/navigate using existing responsive conventions; do not attempt to squeeze two unusably narrow panes beside each other.

## 8. Draft autosave and fast-entry workflow

The intended workload is manual entry of up to 200 samples, so losing a form is unacceptable.

Use debounced autosave for DRAFT/edited records, approximately 800–1200 ms after stable input, following existing project request/error conventions. Do not save on every keystroke without debounce.

Provide explicit immediate-save behavior, including:

```text
Ctrl/Cmd + S -> save immediately
Ctrl/Cmd + Enter -> validate/mark COMPLETE and move to next incomplete sample when successful
```

Exact shortcuts may be omitted on unsupported contexts, but desktop authoring should support them if they do not conflict with existing browser/editor behavior.

Autosave status should be subtle and clear, e.g. Saving / Saved / Retry required, without modal interruption.

A failed autosave must not clear local form content.

## 9. Task 1 image handling

Task 1 COMPLETE records require one task image.

Reuse `LocalAssetStorage` and existing image MIME/size validation conventions:

```text
PNG
JPEG
WebP
```

Store only a storage-relative key/path in the benchmark table.

Use a dedicated benchmark namespace, conceptually:

```text
benchmark/writing/task1/<sample-uuid>.<ext>
```

The admin editor provides preview, replace and remove actions.

Replacing/deleting images must use existing safe cleanup patterns so obsolete benchmark assets do not accumulate unnecessarily. If the image is removed from a COMPLETE Task 1 sample, the sample becomes DRAFT.

Benchmark images do not need an unauthenticated public URL. The admin preview/API remains authenticated, and ZIP export reads the asset server-side.

## 10. Completeness validation

Task 1 COMPLETE requires:

- nonblank prompt;
- nonblank essay;
- valid Task 1 task type from the production registry;
- valid stored image;
- DEV/HOLDOUT split;
- TA, CC, LR, GRA half-band labels.

Task 2 COMPLETE requires:

- nonblank prompt;
- nonblank essay;
- DEV/HOLDOUT split;
- TR, CC, LR, GRA half-band labels.

No feedback is required.

The API returns structured validation errors that the detail editor can associate with fields.

DRAFT records may remain incomplete indefinitely.

## 11. Distribution planner

The top of the page shows current count and progress for Task 1 and Task 2, plus a suggested overall-band distribution.

The suggested target for each 100-sample task bank is:

| Overall | Suggested |
| ---: | ---: |
| 4.0 | 8 |
| 4.5 | 8 |
| 5.0 | 9 |
| 5.5 | 10 |
| 6.0 | 11 |
| 6.5 | 12 |
| 7.0 | 12 |
| 7.5 | 10 |
| 8.0 | 8 |
| 8.5 | 6 |
| 9.0 | 6 |

Total: 100.

This is guidance only, not a save/export constraint. It intentionally gives more density to the common 6.0–7.5 calibration region while preserving meaningful coverage at the ends of the scale.

For each band, UI can show:

```text
8.0: 5 / suggested 8 -> ~3 more recommended
```

Distribution is computed from COMPLETE samples only.

The page may additionally expose a compact criterion-distribution view for TA/TR, CC, LR and GRA to reveal label concentration, but there are no hard criterion-specific target quotas.

Split guidance also shows approximate progress toward 80 DEV / 20 HOLDOUT per task.

## 12. Export behavior

Provide one action:

```text
Export benchmark bundle
```

Export includes COMPLETE samples only. DRAFT samples are never silently converted or partially exported.

The user may export before reaching 100/100 so the CLI/Colab pipeline can be smoke-tested on a small bank.

Before export, present a concise summary such as:

```text
Task 1: 93 complete, 7 draft
Task 2: 100 complete
DEV/HOLDOUT counts
```

The backend constructs the ZIP deterministically enough that its contents and manifest identities are reproducible from the same stored sample state. ZIP byte-for-byte timestamp identity is not required, but sample ordering, IDs and paths are stable.

## 13. Canonical ZIP contract

The bundle shape is:

```text
writing-benchmark.zip
├── task1.jsonl
├── task2.jsonl
├── task1.csv
├── task2.csv
├── manifest.schema.json
├── README.txt
└── images/
    ├── T1-001.png
    ├── T1-002.webp
    └── ...
```

JSONL is canonical benchmark input. CSV is an inspection convenience only.

Task 1 image filenames are stable sample codes plus the validated source extension. `task1.jsonl` references relative local paths such as:

```text
images/T1-001.png
```

No base64 images are placed in JSONL/CSV.

`manifest.schema.json` may contain separate Task 1/Task 2 definitions or a small wrapper documenting both contracts. It must reflect what the shipped CLIs actually accept.

`README.txt` provides short Colab/local invocation instructions and clearly states that the ZIP contains benchmark source material that may be private/licensed.

## 14. Task 1 JSONL compatibility

Prefer direct compatibility with the existing `backend/app/evaluation/task1/models.py::BenchmarkSample` contract so `scripts/benchmark_task1.py` can consume an exported Task 1 manifest without a conversion script.

Export each Task 1 sample conceptually as:

```json
{
  "schema_version": 1,
  "id": "T1-001",
  "split": "dev",
  "task_type": "pie_chart",
  "prompt": "...",
  "image_path": "images/T1-001.png",
  "essay": "...",
  "human_scores": {
    "ta": 7.5,
    "cc": 7.0,
    "lr": 8.0,
    "gra": 7.5
  },
  "raters": 1,
  "provenance": "admin-labelled benchmark sample...",
  "redistributable": false,
  "visual_truth": null
}
```

The web bank does not add a multi-rater model merely because the CLI contract contains `raters`; it always exports `raters=1`.

`visual_truth` is not required by this authoring page. It may remain `null`. Existing Task 1 score metrics still work; perception-truth metrics remain unavailable when no independent visual truth annotation exists.

For provenance, export a bounded nonblank string. If the admin did not provide a source note, use a deterministic neutral value such as `admin-labelled benchmark sample`; do not invent authorship/licence claims. `redistributable` defaults false unless ADMIN explicitly marks otherwise.

## 15. Task 2 JSONL contract

Add a dedicated strict Task 2 benchmark sample model, conceptually:

```json
{
  "schema_version": 1,
  "id": "T2-001",
  "split": "holdout",
  "prompt": "...",
  "essay": "...",
  "human_scores": {
    "tr": 7.0,
    "cc": 7.0,
    "lr": 7.5,
    "gra": 7.0
  },
  "raters": 1,
  "provenance": "admin-labelled benchmark sample...",
  "redistributable": false
}
```

Use `tr` in the Task 2 benchmark contract for human-facing Task Response semantics even if production internals use `ta` as a generic trait key. The evaluation adapter maps the Task 2 benchmark label safely to the production Task Response criterion without altering scoring semantics.

The schema validates the same 0–9 half-band range as production Writing criteria.

## 16. CSV convenience exports

`task1.csv` and `task2.csv` are provided for Excel/Google Sheets inspection only.

Use standard UTF-8 CSV quoting so multiline prompts/essays remain valid.

Flattened columns include at least:

```text
id
split
task_type (Task 1 only)
prompt
essay
image_path (Task 1 only)
human_ta_or_tr
human_cc
human_lr
human_gra
human_overall
provenance
redistributable
```

CSV must not become a second canonical parser path for the benchmark runner.

## 17. Shared score metrics

Task 1 already implements pure score agreement arithmetic including:

- exact agreement;
- within ±0.5;
- within ±1.0;
- signed prediction-minus-human bias;
- MAE;
- RMSE;
- Quadratic Weighted Kappa over the 19 half-band bins.

Task 2 must use the same definitions.

Refactor only as much as needed to share the score-only metric primitives, for example into a small `backend/app/evaluation/writing/metrics.py`, while keeping Task 1 perception metrics Task-1-specific. Preserve compatibility for existing Task 1 imports/tests through direct import updates or a deliberate re-export.

Do not fork a second subtly different QWK/MAE implementation.

Task 2 overall must use the same production Writing four-criterion aggregation/half-band rounding as ordinary scoring.

## 18. Task 2 benchmark CLI

Add a dedicated Task 2 CLI rather than overloading Task 1's image/perception runner.

Conceptually:

```text
scripts/benchmark_task2.py
```

It consumes `task2.jsonl`, invokes the production Task 2 score-first Writing scoring path with configured provider/model settings and records predictions without feeding human labels into the request.

Required CLI behavior should mirror the useful non-perception portions of Task 1:

- `--manifest`;
- `--split dev|holdout`;
- `--limit` for smoke runs;
- bounded concurrency;
- `--resume` with cache identity that includes sample contents/labels, provider/model, prompt/scoring contract and relevant implementation identity;
- output directory containing `report.json`, `report.md`, `disagreements.csv`, `cache/` and `attempts/` or equivalent existing conventions;
- failed samples remain visible in failure statistics rather than disappearing;
- labels are used only for post-inference metrics and never enter model prompts.

No Task 2 image/perception/DePlot fields are introduced.

Do not create an experiment-tracking service or DB table for benchmark runs.

## 19. Metrics and reports

For Task 1, preserve the existing report semantics.

For Task 2, report at minimum for TR, CC, LR, GRA and derived overall:

- comparable count;
- exact agreement;
- within ±0.5;
- within ±1.0;
- signed bias;
- MAE;
- RMSE;
- QWK when sample-count/variance requirements are satisfied;
- failure/nonscorable rate;
- wall-clock latency;
- provider request count/token usage when available.

If existing benchmark infrastructure already provides Pearson/Spearman in a reusable Writing/Speaking metrics module, Task 2 may include them consistently. Do not add a second formula merely to increase the report surface. The core acceptance requirement is the existing Writing Task 1 agreement/error metric set plus operational latency/failure information.

Reports should include band-bucket and split strata where inexpensive and consistent with Task 1 conventions so under/over-scoring at specific human bands is visible.

## 20. Google Colab workflow

The production application never needs direct database access from Colab.

Recommended workflow:

```text
ADMIN web page
-> export writing-benchmark.zip
-> upload ZIP to Colab
-> clone/current repository checkout
-> install backend dependencies
-> unzip dataset
-> configure model/provider secrets in Colab environment
-> run Task 1 or Task 2 benchmark CLI
-> inspect report.json/report.md/disagreements.csv
```

This intentionally avoids placing production PostgreSQL credentials or admin auth tokens in Colab.

The bundle README should show commands compatible with the repository's actual root/backend execution conventions.

## 21. Privacy and data handling

Benchmark source material may be private or licensed.

Requirements:

- ADMIN-only CRUD/export;
- benchmark images are not exposed as anonymous public assets merely for this feature;
- no essays/images are committed to Git by the application;
- no benchmark data is written to logs beyond safe IDs/statuses;
- export is an explicit ADMIN action;
- `redistributable` defaults false;
- CLI reports should continue defaulting to sample IDs/metrics rather than reproducing full essays or images;
- provider calls necessarily send the benchmark input required for scoring, so README/documentation must state that running a benchmark uploads sample content to the configured scoring provider according to that provider setup.

## 22. Delete/replace behavior

Deleting a benchmark sample deletes only benchmark-bank data and its dedicated image asset. It must not affect authored IELTS tests, learner attempts or AI run history.

Delete requires the existing destructive-action confirmation convention.

Replacement image cleanup is best-effort but must never delete the newly committed asset if a request races/fails. Follow existing storage-service patterns for write-then-update/cleanup ordering.

Stable sequence numbers of neighboring samples are never renumbered.

## 23. API shape

Exact paths follow current `/api/v1/admin/...` conventions. Conceptually provide:

```text
GET    /admin/writing-benchmark/summary
GET    /admin/writing-benchmark/samples?task=1|2
POST   /admin/writing-benchmark/samples
GET    /admin/writing-benchmark/samples/{id}
PATCH  /admin/writing-benchmark/samples/{id}
DELETE /admin/writing-benchmark/samples/{id}
POST   /admin/writing-benchmark/samples/{id}/image     # Task 1
DELETE /admin/writing-benchmark/samples/{id}/image
GET    /admin/writing-benchmark/export
```

The service layer owns capacity, completeness, overall calculation, storage and export rules. Routers remain thin.

Autosave PATCH must allow partial DRAFT payloads but validate any supplied criterion values and task-specific fields.

Do not implement public/teacher equivalents.

## 24. Summary endpoint

The page should not download every essay merely to build top-level distribution statistics.

Provide a bounded summary response containing at least:

- total/draft/complete count by task;
- DEV/HOLDOUT count by task;
- complete-sample overall-band histogram by task;
- optional criterion histograms;
- suggested target histogram constants.

The list endpoint returns lightweight rows. Full prompt/essay is loaded for the selected sample/detail rather than duplicating all 200 essays in every summary refresh.

## 25. Migration

Create one Alembic migration for the benchmark table and constraints after the current single head.

No existing production tables need destructive modification.

Expected database changes are benchmark-specific only.

Validate:

- fresh upgrade succeeds on PostgreSQL;
- one Alembic head remains;
- capacity/unique-slot constraints have service-level race protection where SQL CHECK alone cannot express per-task row count.

Do not reset or mutate production data during implementation.

## 26. Testing strategy

Use TDD and focused tests while developing.

Backend coverage should include at minimum:

- ADMIN access succeeds; USER/TEACHER denied;
- create/update DRAFT with partial fields;
- Task 1 COMPLETE requirements;
- Task 2 COMPLETE requirements;
- half-band validation;
- derived overall matches production aggregation;
- unique slot and 100-per-task capacity, including concurrent/race-safe service behavior where practical;
- Task 1 image MIME/size/storage path handling;
- image remove/replace demotes invalid COMPLETE records safely;
- delete cleans benchmark-owned image without touching unrelated assets;
- summary counts/distribution and DEV/HOLDOUT counts;
- export excludes DRAFT;
- export before 100 samples is allowed;
- Task 1 JSONL validates through the existing Task 1 `BenchmarkSample` model;
- export writes `raters=1` and safe provenance/redistributable values;
- ZIP paths cannot traverse outside bundle roots;
- CSV correctly quotes multiline prompt/essay;
- Task 2 benchmark model rejects invalid labels/extra fields;
- Task 2 metric definitions match shared Task 1 score metrics;
- Task 2 human labels never enter provider prompts;
- Task 2 resume/cache identity changes when sample/label/model/prompt contract changes;
- failed Task 2 inference remains represented in reports.

Frontend focused coverage should include:

- `/admin/writing-benchmark` access guard;
- Task 1/Task 2 tabs and progress counts;
- master/detail selection;
- DRAFT/COMPLETE status;
- debounce autosave and save-error preservation;
- Ctrl/Cmd+S immediate save where implemented;
- Complete-and-next workflow;
- Task 1 image preview/replace/remove;
- criterion selectors and derived overall;
- overall-band distribution planner;
- DEV/HOLDOUT counts;
- export summary/action;
- max-100 new-sample button behavior;
- responsive list/detail rendering without horizontal overflow.

No browser/Playwright/live AI is required for normal feature verification unless a focused test exposes a problem that cannot be diagnosed otherwise.

## 27. CI and implementation constraints

The implementation must inspect the current remote CI baseline before feature work and the final pushed SHA afterward.

Use focused local tests during iteration. Do not spend quota on live model calls, Modal, GPU inference or broad browser E2E for this data-management feature.

Task 2 CLI tests use fake providers/fixtures. A one-sample real Colab smoke is a manual post-implementation workflow, not a CI test.

The final change should preserve:

- one Alembic head;
- existing Task 1 benchmark compatibility;
- existing Writing score-first production behavior;
- Task 1/Task 2 AI prompt semantics except where a later independent calibration task changes them;
- normal learner/admin/test-builder data boundaries.

## 28. Operational workflow after implementation

Intended user flow:

```text
1. ADMIN opens /admin/writing-benchmark
2. enters/labels samples over time; autosave keeps DRAFT state
3. completes up to 100 Task 1 and 100 Task 2 samples
4. watches distribution planner while curating labels
5. marks ~80 DEV / ~20 HOLDOUT per task
6. exports ZIP at any point, including before bank completion
7. uploads ZIP to Google Colab
8. runs Task 1 and/or Task 2 CLI
9. compares MAE/QWK/bias/agreement/latency/failures
10. prompt/model changes are evaluated on DEV; HOLDOUT is reserved for final checks
```

The admin bank remains source ground truth only. Benchmark output stays outside the production database.

## 29. Acceptance criteria

The feature is acceptable when all of the following hold:

- only ADMIN can access CRUD/image/export behavior;
- there is one bank, no dataset-version UX or schema;
- Task 1 and Task 2 are independently capped at 100 samples;
- one ADMIN-entered four-criterion human label set is canonical per sample;
- overall is always derived with production scoring arithmetic;
- DRAFT autosave supports incomplete work safely;
- COMPLETE validation prevents incomplete samples entering export;
- Task 1 images are stored privately through existing asset storage;
- the page gives clear overall-band and split guidance without enforcing artificial quotas;
- Task 1 export can be consumed directly by the current Task 1 benchmark CLI;
- Task 2 has a dedicated CLI with the same score-agreement metric definitions;
- ZIP includes canonical JSONL, images and convenience CSV;
- Colab requires only the exported bundle, repository code and scoring-provider configuration, not production DB/admin credentials;
- no benchmark predictions/results are written back to the application database;
- existing CI and Task 1 benchmark behavior remain green.
