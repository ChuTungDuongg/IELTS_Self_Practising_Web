# Independent final review — 2026-10-27

## Scope

Reviewed the task-specific working-tree changes against base `54ff874b41f36bb8409509d77fd17adf411e50d8`, repository AGENTS instructions, `docs/architecture.md`, the supplied task specification, implementation plan and worker reports. Inspected the approved reference image directly. Excluded unrelated untracked skill/configuration/design-reference files.

Review covered classroom capability resolution; direct API mutation paths; legacy memberships and classroom attempts; personal/scoped Writing and Speaking final grading; AI creation/cancellation/read side effects; teacher/co-teacher/TA preservation; bounded directory queries and response privacy; shared observer controls; Classwork search, archive safety and responsive CSS.

Also reviewed the subsequent authorized homepage locale-anchor fix: both auth translations reserve intrinsic width in one CSS grid cell, sizing text is hidden from accessibility APIs and pointer interaction, and visible link labels still track the selected locale. No additional finding identified.

## Outstanding findings

None after the review corrections below were inspected in source.

## Corrections verified during review

1. **P1 — Writing AI cancellation trusted historical ownership.** `backend/app/services/writing_ai.py:385`. An administrator who owned a legacy classroom attempt/run could cancel the run without passing the new classroom mutation boundary. Cancellation now resolves the attempt and checks classroom provenance before `fail_run`.
2. **P2 — Writing AI reads could persist stale-run state.** `backend/app/services/writing_ai.py:306`. List/get/event snapshot paths invoked `recover_stale`, which could write failure state and append events for a legacy Admin classroom run. The recovery boundary now checks provenance and preserves read-only observation without writing that run. Speaking AI snapshots were also inspected; they present stale state without this persistence path.
3. **P2 — Archived resource controls overlapped at 481–640 px.** `frontend/src/features/classrooms/content/classroom-workspace.css:199`. The compact resource View button and archive overflow originally occupied grid column 2, row 1. View now occupies row 2 throughout the compact breakpoint; the management overflow remains in row 1.

These are closed findings against the reviewed final source, not unresolved release blockers.

## Specification compliance verdict

**Pass by source inspection, subject to the verification limits below.** Admin capabilities use an explicit read-only allowlist and take precedence over legacy owner/staff rows. Shared service boundaries reject classroom writes, and final-grade policy covers both classroom and personal endpoints with direct/Full Mock provenance. Owner restoration remains available; co-teacher and TA scopes remain distinct. Separate global account management and test moderation retain their existing policies.

The Admin directory uses server-side filters, deterministic paginated queries, bounded page sizes and minimal people/classroom fields. Its observer and roster links open the existing shared classroom workspace. Admin presentation omits management, authoring, participation, final-grade and personal-progress controls while preserving browsing, search, disclosure and permitted academic views.

Classwork source follows the approved book/search heading, folder topic, neutral observer empty state and distinct compact archive composition. Vietnamese search normalizes case/accents including đ, retains parent/child context, and archive actions reuse protected deletion/removal and deadline-preserving restoration. Restored resources remain drafts.

## Code quality verdict

**Acceptable for integration.** Authorization remains in FastAPI services, query logic stays in repositories, and frontend controls derive from explicit read/write capability props. The shared presentation avoids a separate Admin screen implementation. No change to published version content, attempt/score history, schema, or protected-history deletion rules was identified.

## Verification evidence and limits

- Existing implementer/root evidence supplied for this review: 222 task-focused frontend tests plus 62 disjoint homepage/Gravity/Classwork CSS checks passed; TypeScript typecheck and scoped lint passed. Backend report records 167 focused authorization/archive/AI read/worker/SSE/cancellation tests and scoped Ruff passed. Directory worker separately records seven focused backend contract tests. The root worker will perform its final combined focused validation after source freeze.
- The independent reviewer did not rerun test suites or invoke database fixtures. A focused `git diff --check` on the final Writing AI and mobile CSS corrections passed with only Git line-ending notices.
- Backend authorization REST tests use real routers/services with controlled database doubles. Actual isolated PostgreSQL behavior, row-count/concurrency/query-plan checks and the modified PostgreSQL integration tests remain unverified because an explicitly isolated test database was unavailable.
- No server, browser, Playwright/Cypress, production build, persistent process, database reset, commit or push was performed during this review. Approved-image/source comparison is not rendered-UI screenshot verification; actual desktop/mobile geometry and theme contrast remain unverified.

Final integration validation by the primary agent: 176 focused backend tests and 284 focused frontend tests passed; changed-file Ruff/ESLint, TypeScript and diff whitespace checks passed. No rendered UI or PostgreSQL integration claim is made.
