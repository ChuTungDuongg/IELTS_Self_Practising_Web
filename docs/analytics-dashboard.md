# Personal practice analytics

The `/analytics` workspace uses the existing Raleway/Segoe UI typography, theme
tokens, application shell and user-scoped FastAPI Analytics service. Its scoped
stylesheet lives in `frontend/src/features/analytics/analytics.css`.

## Date and skill scope

- The initial server fetch and client controls both use **all history**. There is
  no client refetch or reinterpretation of lifetime totals during hydration.
- The 7, 30 and 90 day presets include today in BandPilot's calendar,
  `Asia/Ho_Chi_Minh` (UTC+7), anchored at page load. The date caption shows the
  exact inclusive calendar dates. The API receives explicit UTC timestamps and
  applies a half-open interval `[start, end)`.
- `GET /api/v1/analytics` accepts optional timezone-aware `start` and `end`.
  Naive, reversed, equal, and two-sided ranges longer than 3660 days return 422.
  Omitting the bounds retains the existing all-history behavior.
- Finalized attempts belong to their `finished_at`, falling back to `started_at`
  for historical records without a finish timestamp. Active/paused attempts
  belong to their start date. These are **attempt cohorts**, not a measurement
  of seconds falling inside the calendar window: each selected attempt's full
  recorded active duration is included.
- The skill filter applies to finalized counts, practice duration, trends,
  accuracy, attention areas, recent activity, timing segments and comparison
  options. As in the existing API, the four skill averages, completed mock
  count, mock result and practice-derived overall cover all skills within the
  selected date scope. Their captions explicitly say so.
- Completed Full Mocks are counted once per completed session by its finish
  date (historical fallback: start). Their result may include component attempts
  completed earlier than that session's completion date.

## Metric semantics

- The four headline cards show finalized full-module attempts, recorded active
  time, completed Full Mock sessions, and a labelled overall score source.
  Existing finalized statuses and full-module scope are unchanged; an interrupted
  or abandoned finalized attempt is still included, just as before.
- Total and average recorded time retain the existing active/paused population.
  Paused wall-clock time is excluded by the timer engine. The timing card does
  not claim that its average is limited to completed attempts.
- The overall card prefers the latest completed Full Mock overall when one is
  available, otherwise the API's practice-derived overall. The source is named
  next to the value; neither is represented as an official IELTS exam result.
- Recorded navigation segments remain segment counts. They are not described
  as time per question, a Writing task average, or a complete timing breakdown.
- Accuracy uses only graded Reading/Listening answers (`is_correct` is not null).
  Attention areas require at least five graded answers per actual registered
  question type. Comparison accuracy preserves the existing endpoint behavior.
- Recent activity shows the five newest finalized attempts, linking to the
  existing `/review/{attempt_id}` route. The full list links to `/history`.

## Chart and interactions

Each observed skill has its own straight SVG polyline, color and point shape.
Chronological x positions use timestamps; equal timestamps remain equal.
Null, non-finite, out-of-band and invalid-date observations are not plotted as
zero. No overall series, interpolation, fictional growth or radar polygon is
introduced. Every point has a native keyboard control, timestamped tooltip and
corresponding row in the accessible score table. A single retained Tab stop and
Left/Right/Home/End navigation avoid hundreds of Tab stops on long histories.

Filters commit their values together with successful data responses. Failed
requests preserve the previous selection and results, and can retry the failed
scope. Successful scope changes remount the comparison panel so a previous
request cannot publish results into the new scope. Authored titles remain text;
new comparison options include their actual finish date so repeated attempts
on the same test can be distinguished. Legacy API labels remain supported.

The supporting cards retain all existing comparison fields, including Writing
criteria, raw score, accuracy, elapsed duration and band. Custom ranges, prior
period growth, a radar chart and per-question timing are deliberately omitted.

## Focused verification

Frontend:

```powershell
cd frontend
npm exec -- vitest run tests/analytics-page.test.tsx tests/analytics-dashboard.test.tsx tests/analytics-scope.test.ts tests/band-trend.test.tsx tests/speaking-api.test.ts --maxWorkers=2
npm run typecheck
npm exec -- eslint src/app/analytics/page.tsx src/features/analytics src/lib/api/analytics.ts src/lib/i18n/en.ts src/lib/i18n/vi.ts tests/analytics-page.test.tsx tests/analytics-dashboard.test.tsx tests/analytics-scope.test.ts tests/band-trend.test.tsx
```

Backend database tests exclusively use `isolated_db_session`. Provision a fresh
test PostgreSQL database and supply `P2_TEST_DATABASE_URL` or `TEST_DATABASE_URL`
distinct from the ordinary `DATABASE_URL`, following
`backend/testsupport/test_database.py`. Existing CI already provisions that
separate service. Do not point these commands at an application database.

```powershell
cd backend
uv run --offline pytest tests/test_analytics.py tests/test_analytics_date_scope.py tests/test_analytics_date_validation.py tests/test_analytics_query_scope.py tests/test_test_database_safety.py -q
uv run --offline ruff check app/api/v1/analytics.py app/services/analytics.py app/schemas/analytics.py tests/test_analytics.py tests/test_analytics_date_scope.py tests/test_analytics_date_validation.py
```

The focused integration run uses synthetic fixtures and rollback-only sessions.
No schema migration or production data change is required. Browser/screenshot
verification, development servers, builds and deployment are excluded from this
task; responsive/theme behavior is reviewed statically and tested as DOM/CSS
contracts rather than claimed as visually verified.
