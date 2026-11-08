# Admin Speaking Benchmark Lab — Phase 2: Evaluation, Grading Worker, and Metrics Dashboard

Implementation baseline: `5fb734e27b2c782dbaaaaca4eb3168c6150bf8d6`. This feature evaluates approved Phase 1 Speaking candidate audio against production Azure Speech and OpenAI scoring pipelines, persisting durable physical request ledgers, immutable predictions, and Human vs AI comparative metrics. See the [design](../superpowers/specs/2026-11-08-admin-speaking-benchmark-evaluation-design.md) and [implementation plan](../superpowers/plans/2026-11-08-admin-speaking-benchmark-evaluation.md).

```mermaid
flowchart TD
    UI[Next.js Admin Lab & Reports Dashboard] --> API[FastAPI: AdminUser + owner scope]
    API --> DB[(PostgreSQL samples / reviews / grading runs / ledger)]
    API --> AS[Private AssetStorage: source audio]
    W[Separate CPU Grading Worker] -->|claim + heartbeat + lease fence| DB
    W --> AS
    W --> N[Verified candidate windows / FFmpeg normalization]
    N --> PA[Azure Pronunciation Assessment]
    N --> LX[Optional configured lexical ASR]
    N --> V[CPU Silero VAD]
    PA --> E[Production evidence bundle]
    LX --> E
    V --> E
    E --> S[Production SpeakingScorer / OpenAI]
    S -->|score-first checkpoints| DB
    S --> P[Immutable grading prediction]
    P --> R[Post-inference comparison / metrics / CSV & JSON export]
    H[Independent human-label revision] --> R
```

## Architecture & Data Flow

1. **Source of Truth & Approval Invariant:** Only frozen approved reviews (`SpeakingBenchmarkReview.manifest`) with verified candidate-only windows (`candidate_only_verified == true`) are eligible for AI evaluation. Unapproved draft reviews, examiner turns, and unverified candidate windows are strictly barred from inference.
2. **Strict No-Label-Leakage Policy:** Ground Truth human labels and examiner notes never enter provider requests, evidence bundles, prompt templates, or model selection. Changes to human scores recompute comparison metrics immediately without triggering AI re-evaluation.
3. **Preflight & Informed Operator Consent:** Before any run is queued, the API checks configuration, local VAD availability, and the source-bound audio without contacting inference providers. For `N` candidate windows, the request budget is `N` Azure PA calls plus up to 8 typical OpenAI calls (4 criterion scores and 4 feedback calls). The OpenAI maximum is calculated from the configured output/repair policy; the default is 20. Independent lexical ASR adds another `N` requests. For 3 windows with `azure_pa`, this means 11 typical and 23 maximum physical requests under the default policy. Silero VAD runs locally and adds no cloud request. Cached results or unavailable criteria can reduce submissions. Operator USD estimates are admission estimates, not prices or hard billing caps. Queueing requires explicit consent for all selected providers.
4. **Physical-Request Ledger & Billing Safety:** Every network request that can incur cost (including internal OpenAI schema repairs and transport length retries) commits an `ATTEMPTED` ledger row to PostgreSQL *before* transmission. If network drops or an unknown failure occurs, the call is marked `INTERRUPTED_BILLING_UNKNOWN`. The system **never** automatically retries calls with unknown billing status; explicit operator reconciliation and renewed consent are mandatory.
5. **Score-First Atomic Checkpoints:** Criterion scores are persisted to PostgreSQL checkpoints immediately upon receipt from OpenAI, before generating advisory feedback sentences.
6. **Immutable Prediction Records:** On completion, the grading run stores a finalized `SpeakingBenchmarkGradingRun.prediction` snapshot. The run is locked and immutable.

## Database Schema & Migration

Migration `20261108_0046_speaking_benchmark_grading.py` adds two tables and a nullable deletion tombstone to Phase 1 samples:

- `speaking_benchmark_grading_runs`: Owner/sample and approved `review_revision` foreign keys; source/manifest/configuration fingerprints; submission idempotency key; consent; candidate duration/window count; lease/heartbeat; errors; immutable finalized `prediction` JSONB. States are `PENDING`, `RUNNING`, `INTERRUPTED`, `COMPLETED`, `PARTIAL`, `FAILED`, and `CANCELLED`.
- `speaking_benchmark_grading_checkpoints`: Both physical-request accounting and local score checkpoints live here. Each row binds `run_id`, stage, provider, identity, and attempt number to a normalized result, bounded usage and timestamps. States are `ATTEMPTED`, `COMPLETED`, `FAILED`, and `INTERRUPTED_BILLING_UNKNOWN`; billing states are `UNKNOWN`, `OBSERVED`, and `NOT_BILLABLE`. CPU score snapshots are not billable requests. Completed results are protected by database triggers. There is no separate `speaking_benchmark_physical_requests` table and no redundant raw-provider-payload archive.

## Owner-Scoped API Surface

All routes require `ADMIN` authentication and are owner-scoped (matching the authenticated admin's `user.id`). Other admins receive 404.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/admin/speaking-benchmark/grading-availability` | Static provider/configuration readiness; no network inference |
| GET | `/api/v1/admin/speaking-benchmark/samples/{id}/grading-reviews` | List approved revisions for explicit selection |
| POST | `/api/v1/admin/speaking-benchmark/samples/{id}/grading/preflight` | Validate selected `review_revision` and `lexical_provider`; return fingerprint and request budget |
| GET | `/api/v1/admin/speaking-benchmark/samples/{id}/grading-runs` | List grading runs; bounded `offset`/`limit` pagination |
| POST | `/api/v1/admin/speaking-benchmark/samples/{id}/grading-runs` | Enqueue with preflight fingerprint, submission UUID and consent |
| GET | `/api/v1/admin/speaking-benchmark/samples/{id}/grading-runs/{runId}` | Run details; request ledger is included in `requests` |
| POST | `/api/v1/admin/speaking-benchmark/samples/{id}/grading-runs/{runId}/cancel` | Cancel a run; already submitted requests remain potentially billable |
| POST | `/api/v1/admin/speaking-benchmark/samples/{id}/grading-runs/{runId}/retry-interrupted` | Exact checkpoint reconciliation and renewed consent |
| GET | `/api/v1/admin/speaking-benchmark/samples/{id}/grading-runs/{runId}/comparison` | Compare against latest verified or explicit `label_revision` |
| GET | `/api/v1/admin/speaking-benchmark/reports/summary` | Aggregate benchmark metrics (MAE, RMSE, Pearson, Spearman, QWK) |
| GET | `/api/v1/admin/speaking-benchmark/reports/samples` | Paginated sample-level comparison and global outlier list |
| GET | `/api/v1/admin/speaking-benchmark/reports/export.csv` | Formula-safe RFC 4180 CSV export |
| GET | `/api/v1/admin/speaking-benchmark/reports/export.json` | Complete versioned benchmark dataset JSON export |

## Dedicated Grading Worker

The grading worker runs as an independent daemon or one-shot CLI command:

```powershell
# Run continuously with 2-second queue polling
uv run --env-file backend/.env --project backend python scripts/speaking_benchmark_grading_worker.py --poll-interval 2.0

# Process at most one queued run and exit
uv run --env-file backend/.env --project backend python scripts/speaking_benchmark_grading_worker.py --once

# Process up to N jobs and exit
uv run --env-file backend/.env --project backend python scripts/speaking_benchmark_grading_worker.py --limit 5
```

Worker features:

Commands above run from the repository root and explicitly load `backend/.env`; `--project backend` selects dependencies but does not change the working directory. Omit `--env-file` when all settings are exported in the shell. Keep API and worker configuration identical, especially database/storage, enablement flags and provider identities.
- **CLI bounds:** Default idle polling is 5 seconds. `--poll-interval` must be positive and finite. `--limit` counts claimed runs, including failed/cancelled runs, and waits if the queue is empty; it is not an idle-poll limit. `--once` exits even if no run is queued and is mutually exclusive with `--limit`.
- **Distributed Lease Heartbeats:** 90-second lease with 20-second background heartbeats.
- **Crash Recovery & Stolen Lease Protection:** Crashed or abandoned runs past their lease deadline are reclaimed or safely failed with informative diagnostics.
- **Cancellation versus shutdown:** Admin cancellation or lease loss stops only that execution; the daemon continues polling. `SIGINT` / `SIGTERM` cancels the daemon and awaits cleanup. In-flight unresolved requests become `INTERRUPTED_BILLING_UNKNOWN`; shutdown does not declare them free or automatically retry them. A run stopped without unresolved requests is finalized as failed; the API's explicit cancel action retains `CANCELLED`.

## Configuration and operator workflow

Start the Phase 1 web/API and storage as described in [the Phase 1 guide](admin-speaking-benchmark.md). Keep these Phase 2 defaults in `backend/.env` until live processing is explicitly authorized:

```dotenv
SPEAKING_BENCHMARK_GRADING_ENABLED=false
SPEAKING_BENCHMARK_GRADING_ALLOW_LIVE=false
```

For an authorized live test only, enable both flags in the API and worker environments. Configure `SPEAKING_ASR_ENABLED=true`, Azure credentials/billing declarations, `SPEAKING_AI_ENABLED=true`, `SPEAKING_AI_PROVIDER=openai`, the intended `SPEAKING_AI_MODEL`, and backend-only `AI_WRITING_OPENAI_API_KEY`. Keep `SPEAKING_LEXICAL_ASR_PROVIDER=azure_pa` for the one-pass default. The benchmark explicitly selects its lexical provider per run. Independent providers also require their existing permission/budget settings; see [transcription configuration](../speaking-transcription.md).

Install the worker's existing CPU extras with `uv sync --project backend --frozen --extra azure-speech --extra speech-vad`. Place the pinned Silero ONNX model in a persistent private location, set `SPEAKING_VAD_MODEL_PATH` to that file and `SPEAKING_VAD_MODEL_SHA256` to its verified digest. Use the pinned model/setup in [the hybrid guide](../ai-speaking.md); an arbitrary file/digest is not a validated replacement. FFmpeg/ffprobe must be resolvable. Neither the worker nor preflight downloads model weights per job. No Pyannote/Torch or GPU dependency is added to this grading worker.

The API and worker must see the same PostgreSQL database and private assets. A local worker may use local storage on the same host. The separate CPU container in `deploy/speaking-benchmark-grading.Dockerfile` uses remote mode, which requires externally reachable PostgreSQL plus shared R2/S3 and a mounted persistent VAD model. Modal embedded PostgreSQL/local storage is incompatible and fails readiness; do not assume container files or loopback databases are shared. No migration or deployment is performed by the worker.

1. Open `/admin/speaking-benchmark/{sampleId}` and explicitly approve verified candidate segmentation in Phase 1. AI Evaluation refreshes its approved revision choices after approval, without starting inference or automatically selecting the new revision.
2. Select the exact approved revision and lexical provider. Run preflight, listen to its candidate windows, inspect blockers and request counts, and provide per-provider estimates and consent. No inference is submitted by viewing the page or preflight.
3. Confirm queueing, then start the separate worker with one of the commands above. This step can incur charges when live processing is enabled; CLI flags are not a substitute for per-run consent.
4. Inspect progress, physical-request ledger and criterion checkpoints. Cancelling stops further authorized work but cannot undo submitted requests. After a timeout/unknown outcome, reconcile the exact checkpoint and renew authorization before retrying; preserve the old attempt.
5. Review Human vs AI and `/admin/speaking-benchmark/reports`. Human-label edits refresh comparisons only. They do not enqueue grading or alter stored predictions.

Rollback: disable both Phase 2 flags in API and worker environments and stop the worker gracefully. Keep the additive schema/history; no downgrade or learner-record rewrite is needed. Requests already submitted may still be billed.

## Human vs AI Metrics & Reporting

- **Criteria:** Evaluates `overall`, `pronunciation`, `fluency`, `lexical`, and `grammar`.
- **Statistical Metrics:**
  - Mean Absolute Error (MAE) and Root Mean Squared Error (RMSE)
  - Mean Bias Error (MBE)
  - Exact Agreement percentage and Within-0.5 Band Agreement percentage
  - Pearson correlation $r$ (requires $\ge 3$ pairs)
  - Spearman rank correlation $\rho$ (requires $\ge 3$ pairs)
  - Quadratic Weighted Kappa (QWK) with $N=19$ discrete IELTS half-band levels (requires $\ge 5$ pairs)
- **Global Outliers:** Top 10 absolute overall discrepancies ($|\text{Human} - \text{AI}|$) computed across all eligible samples.
- **Formula-Safe CSV Export:** Cells beginning with `=`, `+`, `-`, `@`, `\t`, or `\r` are prepended with `'` to prevent formula execution in Microsoft Excel and Google Sheets.
- **Native Next.js Dashboard:** Located at `/admin/speaking-benchmark/reports`, featuring metric cards, Human-vs-AI scatter, error distribution and signed criterion-error charts, global outliers, and accessible table fallbacks. Missing metrics remain unavailable rather than zero.

## Local Testing Commands

All unit and integration tests run offline against synthetic audio fixtures and mock providers without requiring cloud credentials or incurring billing costs.

```powershell
# 1. Provision disposable test databases
# Ensure Docker container 'codex-speaking-lab-test' is running on port 5546

# 2. Run P2 focused tests. DATABASE_URL must name a DIFFERENT disposable
# baseline database; the isolated fixture rejects the application database.
$env:DATABASE_URL="postgresql+asyncpg://benchmark_test:benchmark_test@127.0.0.1:5546/bandpilot_lab_regression_test"
$env:TEST_DATABASE_URL=$env:DATABASE_URL
$env:P2_TEST_DATABASE_URL="postgresql+asyncpg://benchmark_test:benchmark_test@127.0.0.1:5546/bandpilot_lab_p2_focus_test"
$focusedTests = @(Get-ChildItem backend/tests/test_admin_speaking_benchmark_grading*.py | ForEach-Object FullName)
uv run --project backend python -m pytest @focusedTests backend/tests/test_admin_speaking_benchmark_shutdown.py -q --tb=short

# 3. Run P1 Regression Tests (15 tests)
uv run --project backend python -m pytest backend/tests/test_admin_speaking_benchmark.py -q --tb=short

# 4. Backend Linting Check
Push-Location backend
uv run ruff check --config pyproject.toml . ../scripts
uv run ruff format --config pyproject.toml --check app tests ../scripts
Pop-Location

# 5. Frontend Evaluation Tests
npm --prefix frontend test -- tests/speaking-benchmark-evaluation.test.tsx tests/speaking-benchmark.test.tsx

# 6. Frontend Typecheck, Lint, and Build
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Offline verification — 2026-11-08 maintenance

- Fresh disposable PostgreSQL migration to `20261108_0046`: passed; no schema change was needed for these fixes.
- All admin Speaking Lab backend regressions (Phase 1 + Phase 2, CLI and shutdown): **71 passed**. Added tests cover API cancellation followed by a second claimed run, process cancellation preserving billing uncertainty, CLI argument bounds, idle polling/job limits, and SIGTERM cleanup for both workers.
- Full backend run: **3907 passed, 3 failed, 16 skipped**. Two classroom tests failed because this local run incorrectly set `TEST_DATABASE_URL` differently from primary `DATABASE_URL`; the Phase 1 cleanup test selected a stale outbox row left by earlier fixtures. After correcting the environment and isolating/cleaning fixture-owned outbox rows, `pytest --lf` reran those **3 tests successfully**. This is not presented as an entirely green single full-suite run.
- Full frontend suite: **1999 passed / 169 files**. The focused Speaking Lab/Evaluation suite has **28 passed**, including revision refresh, history paging, unsaved tab state/keyboard navigation, and expected playback interruption versus genuine failure.
- Typecheck, ESLint, production build, backend Ruff lint and format checks: passed. Backend checks use the same working directory/configuration as CI.
- Real Chromium with a loopback-only fake API and a generated 60-second silent WAV: review/label tab switching, single-player speaker playback/stop, approval refresh and run paging passed. Desktop control-bottom/approval-width differences were checked within 1 CSS pixel; 390px layouts had no page overflow. These fixtures do not establish diarization accuracy, live provider behavior or production deployment readiness.
- No Azure/OpenAI/GPU inference or deployment was executed. Private audio, browser captures and local verification scripts remain outside tracked source.

## Safety Notice & Limitations

- **Benchmark Validation Only:** Synthetic and test fixtures prove functional mechanics, concurrency safety, crash recovery, and ledger integrity. They do not claim live calibration accuracy or psychometric validation.
- **Provider Billing Notice:** Live evaluation requires active Azure Speech and OpenAI API keys configured in the environment. Evaluation should only be initiated on approved datasets with full awareness of cloud provider token and audio duration charges.


## Phase 3 paired research

[Research experiments](admin-speaking-benchmark-research.md) schedule compatible P2 runs sequentially per sample; the active-run constraint and physical OpenAI repair ledger remain intact. PA and CPU VAD evidence are cached independently of lexical/scorer choices. Human transcript references and band labels are joined only after inference. Unknown research requests also block new P2 provider submissions on that sample.

Consumed cross-run cache artifacts now create nonbillable `reused_from` checkpoint
receipts in the consuming run. Receipts do not increment physical provider-request
totals or copy usage, and cannot settle an unknown physical request. Research
cancellation fences its linked P2 run atomically; interrupted-run reconciliation
preserves the experiment attribution. Frozen historical predictions stay unchanged.
