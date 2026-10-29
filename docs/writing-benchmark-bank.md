# Admin Writing benchmark bank

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Admin Writing benchmark bank. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/services/writing_benchmark.py).
> Đọc cùng [current module/guide](modules/writing.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

`/admin/writing-benchmark` is ADMIN-only, outside Workspace/Builder. The existing
frontend guard and every backend action enforce that boundary. One bank stores
ground truth only: at most 100 Task 1 and 100 Task 2 samples, including drafts.
There are no dataset versions, rater accounts, adjudication, experiment runs,
prediction tables or report tables.

## Authoring

The master/detail page shows stable `T1-001` / `T2-001` slot codes, Draft/Complete,
DEV/HOLDOUT and derived overall. Deleting never renumbers neighbors. Reusing a
deleted slot gives the new sample a new UUID. Creation always starts Draft.

Autosave waits 1000 ms. Ctrl/Cmd+S saves immediately. Ctrl/Cmd+Enter saves the
latest edits, waits for PATCH ACK, completes, waits for Complete ACK, then selects
the next persisted incomplete sample. A technical row `revision` prevents stale
writes; it is not a dataset version. Save failures/conflicts preserve local text.
Conflict reload explicitly confirms discarding local edits. Selection, tabs,
images, deletion and export flush/serialize pending edits.

Task 1 Complete requires prompt, essay, a production task type, valid private
image and TA/CC/LR/GRA. Task 2 requires prompt, essay and TR/CC/LR/GRA. Both require
a split. Only 0–9 half bands are accepted, before database rounding. Overall uses
production four-criterion mean/half-up rounding and is never stored. Full Writing
module weighting does not apply to individual essays. No human feedback is stored.

Autosave never automatically completes. Invalidating a Complete record demotes it
to Draft; removing a Task 1 image does likewise. Explicit completion returns safe
field-path errors. Complete-only distribution and DEV 80 / HOLDOUT 20 targets are
guidance, never quotas. Lower valid bands remain legal. Criterion histograms are P1.

## API and persistence

Routes are relative to `/api/v1/admin/writing-benchmark`, all using `AdminUser`:

| Action | Method / path |
| --- | --- |
| Summary | `GET /summary` |
| Lightweight list | `GET /samples?task=1` or `task=2` |
| New draft | `POST /samples` with `task_number` |
| Detail | `GET /samples/{uuid}` |
| Autosave | `PATCH /samples/{uuid}` with `expected_revision` |
| Complete | `POST /samples/{uuid}/complete` with `expected_revision` |
| Delete | `DELETE /samples/{uuid}?expected_revision=...` |
| Upload image | `POST /samples/{uuid}/image`, multipart file/revision |
| Read private image | `GET /samples/{uuid}/image` |
| Remove image | `DELETE /samples/{uuid}/image?expected_revision=...` |
| ZIP | `GET /export` |

`writing_benchmark_samples` is the only new table. Migration `20261013_0035`
follows `20261013_0034`. Named constraints cover tasks, unique slots, exact half
bands, Complete requirements and revisions. Per-task PostgreSQL transaction-level
advisory locks allocate the lowest free slot safely when concurrent creates race.
List/summary queries do not load all essays. Identity, slot, image key and overall
are server managed. No learner Attempt, grade or AI-run persistence is used.

## Images and bundle

LocalAssetStorage holds images outside PostgreSQL in the dedicated namespace:
`benchmark/writing/task1/<sample-uuid>/<fresh-asset-uuid>.<ext>`.
PNG/JPEG/WebP reuse MIME, extension and signature validation. The limit is
`min(max_image_upload_mb, 10 MiB)`. Every replacement uses an immutable key:
write new file → commit row/revision → best-effort delete old file. An uncertain
commit ACK retains the possibly committed new image. Traversal, foreign keys
and symlinks are rejected. Private reads use authentication and `no-store`;
bounded bytes are copied under a row lock before delivery to prevent unlink races.
No generic Asset rows with fake TestVersion ownership are created.

Export flushes edits and reviews fresh Complete/Draft/DEV/HOLDOUT counts. Only
Complete rows are included. Empty, partial and full bundles are all allowed:

```text
writing-benchmark.zip
├── task1.jsonl
├── task2.jsonl
├── task1.csv
├── task2.csv
├── manifest.schema.json
├── README.txt
└── images/
    └── T1-XXX.png|jpg|webp
```

All six root files are present even when one task is empty. JSONL is canonical;
CSV preserves multiline quoting and has no input parser. Archive paths are
generated from safe codes/extensions, never uploaded filenames or raw keys.
Shared row locks protect the staged image/manifest snapshot, including during
cancellation. Temporary ZIPs are removed after delivery/failure.

Task 1 instantiates CURRENT `app.evaluation.task1.models.BenchmarkSample`, using
canonical task types such as `PIE_CHART`, so no conversion is needed. Export uses
`raters=1`, `visual_truth=null`, and neutral `admin-labelled benchmark sample`
when the source note is blank. No authorship/license claim is invented.
Redistribution defaults false. Task 2 is text-only with TR; its evaluation adapter
maps production `ta` to `tr`. `schema_version=1` means file-format compatibility.

## Google Colab / local workflow

Admin → Export ZIP → upload ZIP to Colab → clone repo → install backend dependencies
→ unzip → provider secrets → Task 1 or Task 2 CLI → local reports.
No production PostgreSQL credentials, admin JWT/session or production API access
are required. There is no direct Colab ingestion from the production API.

In a Colab cell/terminal, adjusting paths as needed:

```sh
git clone https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web.git
cd IELTS_Self_Practising_Web
pip install uv
uv sync --project backend --locked --group dev
unzip /content/writing-benchmark.zip -d /content/writing-benchmark
uv run --project backend python scripts/benchmark_task1.py --manifest /content/writing-benchmark/task1.jsonl --split dev --scoring-version v12 --chart-specialist off --dry-run --output benchmarks/writing_task1/reports/dev-plan
uv run --project backend python scripts/benchmark_task2.py --manifest /content/writing-benchmark/task2.jsonl --split dev --dry-run --max-concurrent-llm-requests 2 --output benchmarks/writing_task2/reports/dev-plan
```

Set Colab Secrets/environment variables for the current provider fields in
`backend/.env.example`: `AI_WRITING_ENABLED=true`, `AI_WRITING_PROVIDER`, provider
URL/model/API key, and existing proxy credentials when required. Production
configuration defaults and prompts are unchanged. The CLI reads environment
variables and optional `backend/.env`. Never commit secrets into notebooks.

Optional **manual** one-sample inference after provider setup (not a CI test):

```sh
uv run --project backend python scripts/benchmark_task1.py --manifest /content/writing-benchmark/task1.jsonl --split dev --limit 1 --scoring-version v12 --chart-specialist off --resume --output benchmarks/writing_task1/reports/dev-smoke
uv run --project backend python scripts/benchmark_task2.py --manifest /content/writing-benchmark/task2.jsonl --split dev --limit 1 --max-concurrent-llm-requests 2 --resume --output benchmarks/writing_task2/reports/dev-smoke
```

Inference sends prompts, essays and Task 1 images to the configured provider.
Keep private/licensed bundles private. Use DEV for iteration and separate HOLDOUT
output for final evaluation; repeated tuning on HOLDOUT undermines that boundary.

Task 2 samples execute sequentially. The 1–4 limit bounds production criterion
requests within each sample. MTSWritingScoringService runs directly, without
learner persistence, AI workers, image perception or DePlot. Human labels never
enter inference prompts. Shared metrics are exact/±0.5/±1 agreement, signed bias,
MAE, RMSE and QWK. QWK needs 10 comparable half-band pairs and nonzero expected variance.

Outputs: `report.json`, `report.md`, `disagreements.csv`, `cache/`, `attempts/`.
Failures remain visible; partial valid criteria contribute metrics but overall
needs four predictions. Reports show latency, calls and available usage without
source text/secret URLs/provider errors. Resume covers contents, labels, split,
provider/model/hashed endpoint, effective prompt, runtime settings, paragraph
provenance, contract and implementation. Paths/presentation captions do not
invalidate it. Failed/corrupt/inconsistent records are not success hits. Earlier
failed attempts/costs survive retry-to-success. Interrupted in-flight costs are
unknown, never fabricated. Predictions/reports stay in CLI/Colab output and never
automatically change production scoring. Accuracy must be established separately.

## Implementation validation — 2026-10-13

Implementation began on clean main `1ad0465a2b96d19fd41df3a117927f9d5cfa2989`.
Its exact-SHA CI run `38396464810` and Golden Path E2E run `38396464698` were green;
no baseline repair was needed. Fourteen sequential TDD tasks were committed.

The final focused backend set passed **224 tests**, with **one skip** because this
Windows host cannot create symlinks; Linux CI exercises that real-filesystem guard.
The focused frontend set passed **58 tests**, including affected Builder/Admin
regressions. Frontend typecheck, targeted Ruff lint/format, targeted ESLint and
`git diff --check` passed. Only `.gitkeep` is tracked in private input/storage and
generated-report directories; no private benchmark data was added.

A fresh isolated PostgreSQL database, `bandpilot_benchmark_20261013_2138`, upgraded
from empty through `alembic upgrade head`. The single head is `20261013_0035`.
Actual migration round trips and capacity races used independent PostgreSQL
connections and temporary schemas, not ORM-only schema construction.

The integrated API → ZIP → both current loaders → both fake-provider CLI test
completed without changing learner Attempt/final-grade/AI-run rows. It exposed
and covered repeated export cancellation: snapshot locks now remain held until
the staging thread finishes, and canceled ZIPs are removed afterward.

No browser, local E2E, live provider, GPU inference, deployment or full local suite
was used. Required remote workflows are checked on the final pushed SHA before
completion is reported. Criterion histograms remain intentionally deferred P1.
