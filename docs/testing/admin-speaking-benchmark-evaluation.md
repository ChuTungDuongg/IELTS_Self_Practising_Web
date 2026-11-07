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
3. **Preflight & Informed Operator Consent:** Before any run is queued, the API executes offline static readiness checks (credential presence, model configuration, audio asset accessibility) and displays an exact request budget (typical 8 requests: 3 Azure PA, 1 Silero VAD, 4 OpenAI criterion scoring; maximum bound of 20 with retries and schema repairs). A grading run cannot be created without explicit user consent.
4. **Physical-Request Ledger & Billing Safety:** Every network request that can incur cost (including internal OpenAI schema repairs and transport length retries) commits an `ATTEMPTED` ledger row to PostgreSQL *before* transmission. If network drops or an unknown failure occurs, the call is marked `INTERRUPTED_BILLING_UNKNOWN`. The system **never** automatically retries calls with unknown billing status; explicit operator reconciliation and renewed consent are mandatory.
5. **Score-First Atomic Checkpoints:** Criterion scores are persisted to PostgreSQL checkpoints immediately upon receipt from OpenAI, before generating advisory feedback sentences.
6. **Immutable Prediction Records:** On completion, the grading run stores a finalized `SpeakingBenchmarkGradingRun.prediction` snapshot. The run is locked and immutable.

## Database Schema & Migration

Migration `20261108_0046_speaking_benchmark_grading.py` adds three tables:

- `speaking_benchmark_grading_runs`: Links to `sample_id`, `review_id`, `created_by`, `claimed_by`. Tracks lifecycle status (`QUEUED`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `CANCELLED`), configuration snapshot, provider identity, consent metadata, lease token, lease expiry, heartbeat timestamp, failure details, and frozen `prediction` JSONB.
- `speaking_benchmark_grading_checkpoints`: Append-only criterion checkpoints (`pronunciation`, `fluency`, `lexical`, `grammar`, `overall`) with score, band, raw provider output, and timestamps.
- `speaking_benchmark_physical_requests`: Physical network call ledger tracking provider (`azure_speech`, `openai`), endpoint, request digest, billable units (seconds or tokens), estimated cost, status (`ATTEMPTED`, `COMPLETED`, `FAILED_DETERMINISTIC`, `FAILED_TRANSIENT`, `INTERRUPTED_BILLING_UNKNOWN`), latency, and error codes.

## Owner-Scoped API Surface

All routes require `ADMIN` authentication and are owner-scoped (matching the authenticated admin's `user.id`). Other admins receive 404.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/admin/speaking-benchmark/samples/{id}/grading/preflight` | Static readiness check, model info, and request budget |
| GET | `/api/v1/admin/speaking-benchmark/samples/{id}/grading/runs` | List grading runs for sample |
| POST | `/api/v1/admin/speaking-benchmark/samples/{id}/grading/runs` | Enqueue a new grading run (requires preflight consent) |
| GET | `/api/v1/admin/speaking-benchmark/samples/{id}/grading/runs/{runId}` | Get run details, checkpoints, and status |
| POST | `/api/v1/admin/speaking-benchmark/samples/{id}/grading/runs/{runId}/cancel` | Safely cancel a queued or running job |
| GET | `/api/v1/admin/speaking-benchmark/samples/{id}/grading/runs/{runId}/requests` | Inspect physical network request ledger |
| GET | `/api/v1/admin/speaking-benchmark/reports/summary` | Aggregate benchmark metrics (MAE, RMSE, Pearson, Spearman, QWK) |
| GET | `/api/v1/admin/speaking-benchmark/reports/samples` | Paginated sample-level comparison and global outlier list |
| GET | `/api/v1/admin/speaking-benchmark/reports/export.csv` | Formula-safe RFC 4180 CSV export |
| GET | `/api/v1/admin/speaking-benchmark/reports/export.json` | Complete versioned benchmark dataset JSON export |

## Dedicated Grading Worker

The grading worker runs as an independent daemon or one-shot CLI command:

```powershell
# Run continuously with 2-second queue polling
uv run python scripts/speaking_benchmark_grading_worker.py --poll-interval 2.0

# Process at most one queued run and exit
uv run python scripts/speaking_benchmark_grading_worker.py --once

# Process up to N jobs and exit
uv run python scripts/speaking_benchmark_grading_worker.py --limit 5
```

Worker features:
- **Distributed Lease Heartbeats:** 60-second lease with 20-second background heartbeats.
- **Crash Recovery & Stolen Lease Protection:** Crashed or abandoned runs past their lease deadline are reclaimed or safely failed with informative diagnostics.
- **Graceful Termination:** Handles `SIGINT` / `SIGTERM` cleanly, transitioning active runs to `CANCELLED` or recording interrupted billing state without corrupting database transactions.

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
- **Native Next.js Dashboard:** Located at `/admin/speaking-benchmark/reports`, featuring metric cards, difference distribution charts, criteria radar comparisons, global outliers, and accessible table fallbacks.

## Local Testing Commands

All unit and integration tests run offline against synthetic audio fixtures and mock providers without requiring cloud credentials or incurring billing costs.

```powershell
# 1. Provision disposable test databases
# Ensure Docker container 'codex-speaking-lab-test' is running on port 5546

# 2. Run P2 Focused Grading Backend Tests (29 tests)
$env:TEST_DATABASE_URL="postgresql+asyncpg://benchmark_test:benchmark_test@127.0.0.1:5546/bandpilot_lab_p2_focus_test"
$env:P2_TEST_DATABASE_URL="postgresql+asyncpg://benchmark_test:benchmark_test@127.0.0.1:5546/bandpilot_lab_p2_focus_test"
uv run --project backend python -m pytest backend/tests/test_admin_speaking_benchmark_grading_api.py backend/tests/test_admin_speaking_benchmark_grading_input.py backend/tests/test_admin_speaking_benchmark_grading_migration.py backend/tests/test_admin_speaking_benchmark_grading_models.py backend/tests/test_admin_speaking_benchmark_grading_preflight.py backend/tests/test_admin_speaking_benchmark_grading_providers.py backend/tests/test_admin_speaking_benchmark_grading_reports.py backend/tests/test_admin_speaking_benchmark_grading_report_persistence.py backend/tests/test_admin_speaking_benchmark_grading_safety.py backend/tests/test_admin_speaking_benchmark_grading_vertical.py backend/tests/test_admin_speaking_benchmark_grading_worker.py -q --tb=short

# 3. Run P1 Regression Tests (15 tests)
$env:TEST_DATABASE_URL="postgresql+asyncpg://benchmark_test:benchmark_test@127.0.0.1:5546/bandpilot_lab_regression_test"
uv run --project backend python -m pytest backend/tests/test_admin_speaking_benchmark.py -q --tb=short

# 4. Backend Linting Check
uv run --project backend ruff check backend

# 5. Frontend Evaluation Tests
npm --prefix frontend test tests/speaking-benchmark-evaluation.test.tsx

# 6. Frontend Typecheck, Lint, and Build
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Safety Notice & Limitations

- **Benchmark Validation Only:** Synthetic and test fixtures prove functional mechanics, concurrency safety, crash recovery, and ledger integrity. They do not claim live calibration accuracy or psychometric validation.
- **Provider Billing Notice:** Live evaluation requires active Azure Speech and OpenAI API keys configured in the environment. Evaluation should only be initiated on approved datasets with full awareness of cloud provider token and audio duration charges.
