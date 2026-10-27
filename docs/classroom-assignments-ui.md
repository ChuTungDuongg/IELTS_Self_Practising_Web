# Classroom Assignments management

The approved Assignments mockup is implemented inside the existing Classroom workspace. At desktop widths from 1100px, a fluid 29% creation panel sits beside the 71% management column, separated by an 18px gap. Active rows use compact skill identities, target labels, status badges, populated schedule dates and result/context actions. Archived rows have a restrained burgundy surface with restore, permanent-delete and details controls. Shared semantic tokens support both themes; the stylesheet is scoped to this tab.

The existing assignment engine remains authoritative. Test selection resolves the eligible published revision without exposing technical revision numbers. The teacher must select an actual skill or eligible Full Mock; focused units come from authorized VersionDetail metadata. Scheduling retains available time, due time, hard cut-off, attempt limits and late-submission policy in a disclosure. Writes have duplicate-submit guards, pending/error/success feedback and canonical Classwork/Assignments/progress refresh. A failed refresh after a successful creation retries loading without repeating creation.

The header's IELTS assignment action reveals and focuses the same creation form. At mobile widths it opens the initially collapsed form. Once visited, the Assignments tab stays mounted while hidden so search, filter and unsaved form state survive tab navigation. Monitoring and schedule editors mount only when requested. Staff do not fetch student progress for every row; the opening-status badge schedules only its next timestamp boundary.

Title/notes/test/target search is local, case-insensitive and Vietnamese accent-insensitive. It searches the complete assignment list returned by the current non-paginated endpoint. All/Active/Archived filtering hides irrelevant empty groups. API-provided student progress continues to control starts, resumes and result links. Teachers and co-teachers receive management controls only through `assignments.manage`; Admin Observer mounts no creation form and exposes no mutation controls. Backend capabilities remain authoritative.

## Explicit deletion policy

The user twice confirmed that permanent deletion must erase all student work, scores and related data even for completed assignments. This overrides the protected-history wording in the supplied visual specification. The UI confirmation and archive notice state the irreversible consequences in VI/EN. Removing a Classwork placement remains a separate operation that preserves the assignment and its work; restore preserves the frozen version, target, attempts and schedule without extending dates.

Authorized hard deletion removes the assignment's direct and Full Mock attempts, sessions, dependent evaluation/AI records, extensions, policy history, assignment notifications and content/plan references in one transaction. Plans retain their identity and receive a revision bump when an affected activity is removed. Private Speaking media keys enter the existing durable cleanup outbox before their rows disappear; local workers are cancelled only after commit. Shared published exam versions and assets are retained. Resource deletion removes its links from posts/plans without deleting those posts/plans.

Migration `20261028_0042` changes the policy-history trigger to reject UPDATE while allowing DELETE. It performs no data deletion. Deploy it before using the new deletion endpoint; without it PostgreSQL still rejects deleting policy events. The downgrade reinstates the former DELETE restriction. After the user explicitly approved applying this migration, the current local database was upgraded from `0041` to `0042`; a read-only inspection confirmed the live trigger is now `BEFORE UPDATE` only. No assignment was deleted for verification. The user's supplied traceback confirmed that the previous trigger caused the DELETE 500 error shown as a browser network error.

## Verification limits

Focused Vitest coverage includes layout composition, archive/active counts, Vietnamese search, status filtering, empty states, creation permissions, desktop/mobile form behavior, exact targets for all four skills, Full Mock eligibility, scheduling, duplicate submission, success/error/reload retry, result routes, schedule disclosure, lazy monitoring, localization and CSS contracts at 375/768/1024/1100/1440px. Existing observer, student progress, archive/restore and classroom lifecycle tests remain in the selection.

Backend DB-free tests inspect scoped PostgreSQL statements, cascade metadata, private-media outbox ordering, permission denial, post-commit cancellation and migration upgrade/downgrade SQL. These checks do not replace PostgreSQL integration tests. Updated database integration cases are retained but were not run against the development database. No browser, screenshots of the implementation, dev server, production build, E2E, full suite or live AI calls were launched. Pixel spacing, rendered contrast and viewport behavior still require manual visual review.

Final verification passed 156 focused frontend tests, 87 database-free backend tests, TypeScript, scoped ESLint, scoped Ruff lint/format and `git diff --check`.

The companion homepage change handles a network outage with a localized retry notice and public landing content, without rendering fabricated account metrics or swallowing unrelated API errors. The existing homepage language/login sizing fix remains intact.

## File groups

- Assignment composition: `frontend/src/features/classrooms/assignment-list.tsx`, `assignment-form.tsx`, `assignments/assignment-row.tsx`, `assignments/assignment-status.tsx`, `assignments/assignment-sync.tsx`, `assignments/creation-panel.tsx`, `assignments/start-assignment.tsx`, `assignments/messages.ts`, `assignments/assignments.css`, `content/classroom-workspace.tsx`, `scheduling/assignment-management.tsx`.
- Destructive-action UI: `frontend/src/features/classrooms/content/archived-assignment-actions.tsx`, `content-action.tsx`, `content-messages.ts`.
- Homepage recovery: `frontend/src/app/page.tsx`, `frontend/src/components/home/overview-content.tsx`, `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Backend lifecycle: `backend/app/api/v1/classroom_assignments.py`, `backend/app/services/classroom_assignments.py`, `classroom_classwork.py`, `classroom_deletion.py`, `writing_ai_worker.py`, `speaking_transcript_worker.py`, `backend/alembic/versions/20261028_0042_classroom_hard_delete.py`.
- Frontend tests: `assignments-tab.test.tsx`, `assignments-css.test.ts`, `assignment-target-ui.test.tsx`, `classroom-content.test.tsx`, `classwork-compact.test.tsx`, `home-user-metric.test.tsx` under `frontend/tests/`.
- Backend tests: `test_classroom_hard_delete_unit.py`, `test_classroom_archive_unit.py`, `test_classroom_removal_activities.py` under `backend/tests/`.
- Documentation: this document and `docs/classroom-archive-calendar.md`.
