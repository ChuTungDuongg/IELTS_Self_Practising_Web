# BandPilot performance investigation — 27 October 2026

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: BandPilot performance investigation — 27 October 2026. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/repositories/tests.py).
> Đọc cùng [current module/guide](handbook/testing-and-delivery.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Baseline: `origin/main` at `4b24dbbbf999fb5f8482036ce64cfe1aff55cf71`.
The current remote logs were downloaded through the GitHub Actions API before
editing. [CI 40507333869](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions/runs/40507333869)
failed only in the Listening continuity test (1,620/1,621 tests passed).
[Golden Path 40507334185](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions/runs/40507334185)
passed. The workflows and their quality gates are unchanged.

## Measurement boundaries

No development server, browser, local production build, local E2E runner, full
local test suite, database reset, or live AI request was launched. Evidence comes
from focused component tests, request/render counts, PostgreSQL SQL compilation,
runtime import graph checks and inspection of existing `.next` artifacts. The
existing build predates these edits; it is not an after-build measurement.
All numbers below describe deterministic test scenarios, not browser latency.

## Confirmed issues and implemented changes

| Area | Observed problem and root cause | Before | After | Protection / tradeoff |
| --- | --- | --- | --- | --- |
| Listening CI | `renderWithLocale` already supplies a persistent wrapper. The test's `rerender` inserted a second provider, replacing the player subtree. | Focused player file: 24 pass, 1 fail. | Same `audio` and player nodes, current time, rate, volume, mute and playing UI survive locale/layout/appearance changes. | Keep `toBe`, playback state and media-call assertions. Source changes and independent exam restrictions remain covered. No player lifecycle change was needed. |
| Global header | `HeaderBar key={pathname}` remounted notifications on navigation. | One route change: 2 list calls and 2 unread-count calls including initial mount. | 1 list call and 1 count call; the header node survives. | Account ID still resets notifications. Opening the panel still refreshes it; no shared notification cache. Menu closes on navigation and stays closed when returning. |
| Locale subscriptions | Every translated component subscribed to the full preference context. | Appearance-only change caused 1 extra translated probe render. | 0 extra probe renders. | A separate memoized locale subscription shares the same authoritative preferences state. Preference write queuing, failures and account changes retain their tests. |
| Homepage | Independent profile/admin loaders waited for catalog/history to finish. | With catalog unresolved, neither later loader started. | Both start before catalog resolves, after user authentication. | Same API requests and error handling; concurrent independent reads. No time-based benchmark claim. |
| Catalog / Skill Practice | List loaders issued a separate detail request for each selected published version. Each request repeated ORM graph loading. | Six fictional Library tests: 1 list + 6 details = 7 loader calls. | 1 list, no detail calls, same 6 cards. Skill Practice likewise avoids its extra detail request. | Opt-in `public_only=true&include_details=true`; reuse the existing key-free `VersionDetail` DTO and public policy. Non-catalog callers stay lightweight. Missing embedded summaries retain the existing per-version fallback. |
| Reading | Passage blocks rerendered with the runner's display clock and answer-save state. | A batched 3-second timer advance produced an extra passage-text render. | 0 extra passage-text renders during that advance or an unrelated answer/save. | Stable highlight callbacks/controller plus a memoized passage boundary. Highlights and locale still invalidate it. DOM remains mounted. |
| Classroom locale | Localized error callbacks were fetch dependencies. | EN→VI caused Classwork and Stream to each issue a second request. | Each remains at 1 request. | Store the caught error and translate during rendering. Explicit refresh, filters, mutations, aborts and request sequencing remain. |
| Assignment progress | Order-sensitive ID signatures and an inline context value repeated work for equivalent inputs. | Reorder/deduplicate the same IDs: 2 progress calls. | 1 call and no extra context-consumer render. | Canonical ID set, memoized context. Required progress reads, 100-ID batches and explicit refresh remain. No private-data cache. |
| Classroom module loading | Gradebook, analytics, plans and profiles were static dependencies of the default Stream workspace. | All four reachable through static runtime imports. | None reachable through the initial static import graph. | Load the existing panels with `next/dynamic` only when selected; localized loading status. No changed permissions, data APIs, or exam controls. First use fetches the panel chunk. Bundle bytes and browser timing remain unmeasured. |
| Analytics comparison | Selecting two attempts loaded the user's entire full-module history and navigation events. | SQL had user/scope filters but no selected-ID/final-status predicate. | SQL restricts to the two IDs, same owner/scope, finalized status; skips unused navigation-event loading. | Compiled SQL/loader regression test. Dashboard still loads events for timing. Existing primary keys suffice; no migration or cache. |

Catalog SQL loading uses batches of at most 100 selected version IDs. A
database-free diagnostic checks 250 IDs produce batches of 100/100/50. The
PostgreSQL regression compares the old list-plus-details path with the new
catalog path, verifies identical DTOs, and requires fewer SELECTs (at most 20 for
the six-test fixture). It also checks learner, owner and administrator visibility:
classroom-only approvals, drafts, archived tests and unauthorized records stay
excluded. These database-backed checks are delegated to the unchanged remote CI,
not run against the user's development database.

## Other audit findings and limits

- `AuthProvider` is mounted in the root layout; its initial session check does not
  depend on pathname. Its context already uses memoization, and the HTTP client
  already coalesces refresh requests. Authentication/logout refreshes serve
  freshness requirements and were retained.
- The existing Three.js entry uses `import("./scene")` after browser preference
  checks. The existing loadable manifest confirms a separate scene chunk. An
  import-graph test now keeps it outside the global shell. No invented bundle
  reduction percentage is reported.
- Classroom already renders only the active tab and retains the progress
  provider outside tab content. Gradebook bounds student/assignment pages, and
  LMS loaders abort obsolete responses. No broad keep-mounted tab cache or
  heavyweight virtualization package was introduced.
- Writing retains its 750 ms revision-aware autosave, explicit flush before
  submission, and telemetry completion boundary. Speaking recording/chunk
  transport and AI workflows were inspected but not changed. No demonstrated
  recording or AI bottleneck justified changing their lifecycle.
- Question registries still bring Builder editors into some exam import paths;
  separating that contract needs a dedicated editor/rendering follow-up. Large
  production catalogs and full analytics dashboards also need representative
  runtime measurements before pagination or aggregate redesign.
- Development compilation latency cannot be inferred from these tests. Measure
  production navigation, API latency/SQL plans, long tasks, layout work, memory,
  and compressed route chunks separately before choosing further changes.

## Regression checks and compatibility

Focused frontend coverage includes navigation, shell, personalization,
notifications, homepage loaders, catalog and Skill Practice, Reading/Listening
navigation, player continuity, Writing runner, Classroom content/LMS/analytics,
assignment progress and import boundaries. The Listening test was run repeatedly.
The personalization harness now waits for enabled account controls before
interacting, instead of racing its async preferences load.

Local backend checks use only mocked sessions and compiled SQL/schema contracts.
TypeScript typecheck, ESLint on changed files, scoped Ruff lint/format and
`git diff --check` accompany the tests. Remote CI supplies the full suites,
migrations, production build and Golden Path browser tests.

No changes to scoring, TestVersion mutation rules, historical attempt references,
deadline enforcement, autosave queues, Full Mock progression, Classroom
permissions, human-final grading, AI providers or notification routes. Public
catalog enrichment uses current-request authorization and the existing public
summary DTO; no answer keys or cross-user shared cache are introduced.
