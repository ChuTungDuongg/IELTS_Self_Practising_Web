# Admin Observer and Approved Classwork Implementation Plan

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Admin Observer and Approved Classwork Implementation Plan. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [current module/guide](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **For agentic workers:** Use focused independent implementation work with task review and integration verification. The user explicitly requests implementation, commit and safe push to origin/main.

**Goal:** Enforce read-only classroom oversight for platform administrators and share the approved Classwork presentation across roles.

**Architecture:** FastAPI resolves explicit classroom capabilities and rejects writes at service boundaries. Next.js renders the existing workspace using separate read/write capability props. The admin directory uses bounded server queries, and archive operations retain existing history protection and refresh semantics.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Next.js, React, Zod, pytest, Vitest.

**Spec:** User-provided attachment `Pasted text.txt` (CODEX TASK — Match Approved Classwork Design + Enforce Strict Admin Observer Mode).

## Global Constraints

- Preserve PostgreSQL authority, immutable TestVersions, attempts, scope, schedules and grading provenance.
- Admin is an observer in classrooms, including when legacy membership/staff records exist.
- Preserve separately authorized platform account administration and global test moderation.
- Use existing APIs and shared workspace components; localize Vietnamese/English and preserve both themes.
- Do not start servers, browsers, browser tests, production builds, persistent processes, database resets or the whole test suite.
- Preserve existing untracked skills/design files. Commit only task files; push origin/main without force.

## Review Focus

- Personal Writing/Speaking routes must also reject Admin final grading of classroom attempts.
- Read-only roster access must never imply member-management access.
- Restoring an archived classroom must remain available to its owner, without Admin authority.
- Search preserves matching topic children and finds Vietnamese content regardless of case/diacritics.
- Archived assignment details remain accessible without mounting mutation controls; mobile actions are not duplicated.

### Task 1: Backend authorization

**Files:** `backend/app/services/classroom_capabilities.py`, classroom services, `grading_policy.py`, focused backend tests.

- [x] Add failing focused capability/service/REST tests for Admin denials and teacher/co-teacher/student isolation.
- [x] Explicitly allow roster/grade/analytics read capabilities; separate roster view from member mutation.
- [x] Remove assignment and grading bypasses; audit all classroom mutations and owner restoration.
- [x] Run focused tests and Ruff; record any database prerequisites without touching real data.

### Task 2: Shared Classwork visual presentation

**Files:** `frontend/src/features/classrooms/content/` Classwork components and CSS, focused component tests.

- [x] Add tests for topic/resource/assignment search and teacher versus observer archived actions.
- [x] Add book/search header, folder topics, neutral empty states and distinct compact archives using existing tokens.
- [x] Surface direct teacher Restore/Delete/Details and mobile contextual actions; preserve confirmations/history-safe removal.
- [x] Run focused Vitest and scoped ESLint. Browser/screenshot verification is explicitly excluded by the user.

### Task 3: Admin directory and observer wiring

**Files:** admin directory route/service/schema, typed frontend clients, admin directory UI, classroom detail/workspace/header/membership components, tests.

- [x] Implement bounded Admin teacher/student/classroom discovery with ownership and enrolled counts.
- [x] Separate roster/classroom/member/content/assignment/grade/analytics permissions throughout shared workspace.
- [x] Display observer indicator and read-only roster; omit authoring, personal progress and grade controls for Admin.
- [x] Run focused frontend/API tests, typecheck and scoped lint.

### Task 4: Integration and delivery

- [x] Review all changed paths against the supplied access matrix and design composition.
- [x] Run allowed focused checks and `git diff --check`, inspect task diffs and commit logical units.
- [x] Prepare scoped logical commits and a safe push to origin/main; record actual commit/push evidence in the final response.

## Final verification evidence

- 176 focused backend tests passed, including 51 direct REST denials; no database fixtures executed.
- 284 focused frontend tests passed across 16 files.
- Changed-file Ruff/ESLint, TypeScript and whitespace checks passed.
- Independent review found no outstanding issues after fixes to AI cancellation/read recovery and compact resource rows.
- Additional user request: homepage VI/EN controls retain their position using intrinsic sizing for both translated authentication labels; accessible labels and navigation remain unchanged.
- Browser rendering, production build and real PostgreSQL integration were intentionally not run under the user restrictions.
