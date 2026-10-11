# Teacher, classrooms and content governance

This v1 implementation follows the approved [design](superpowers/specs/2026-10-11-teacher-classroom-content-governance-design.md) and [implementation plan](superpowers/plans/2026-10-11-teacher-classroom-content-governance.md). PostgreSQL remains authoritative; every domain mutation goes through FastAPI.

## Setup and roles

Apply the normal backend migration command, `uv run alembic upgrade head`. Revision `20261011_0024` follows `20261011_0023`; it adds `TEACHER`, content ownership, moderation, classroom resources, notifications and assignment provenance. Legacy tests retain `origin=ADMIN` and may have no owner. Newly created tests must have an authenticated owner.

| Role | Capabilities |
| --- | --- |
| USER | Existing personal practice/history, classroom invitations, membership and assigned practice. Cannot author tests or self-select a privileged role at registration. |
| TEACHER | All normal USER capabilities, plus owned Builder content and owned classrooms. Cannot enter the general ADMIN workspace or mutate another teacher's content. |
| ADMIN | Existing administrative and official/manual Writing grading powers, role changes, global Builder administration, moderation and classroom archive/restore. |

Promote an existing account to TEACHER through the ADMIN account controls. Demotion, promotion away from TEACHER, or deactivation conflicts while the account has active classrooms, pending moderation, or drafts in unarchived teacher tests. Archive the classrooms, resolve requests and archive/delete drafts or their tests first. Role changes retain academic history and teacher attribution. ADMIN-only permanent deletion also refuses accounts referenced by the governance domain, including notifications, instead of deleting those records.

The OCR draft CLI now requires an active ADMIN owner explicitly:

```powershell
uv run python -m app.import_draft path/to/manifest.json --owner-user-id ADMIN_UUID
```

Transfer imports likewise stamp the authenticated author's ownership/origin. Neither import can invent an administrative actor.

Downgrade is intended for an empty feature domain: it refuses classroom/notification/moderation history, TEACHER accounts or teacher-origin content. PostgreSQL's additive `TEACHER` enum label remains after a safe downgrade; it is not removed by rewriting the existing user enum.

## Owned content and moderation

Teacher-created content always stays `origin=TEACHER` and retains its owner. ADMIN approval does not turn it into official content. Official content is ADMIN-origin content; PUBLIC-approved teacher content appears as community content with the contributor's display name.

`TestVersion.status` remains `DRAFT`, `PUBLISHED` or `ARCHIVED`. Independent moderation records have scope `CLASSROOM` or `PUBLIC` and retain submitter, reviewer, notes and transition timestamps. Owner cancellation has a separate `CANCELLED` audit state, rather than being recorded as an ADMIN rejection. A version can have at most one pending request per scope.

- A pending request locks that version's authored content, assets and shared test metadata. Cancelling or rejecting the final pending request unlocks a draft.
- A teacher can submit directly for PUBLIC, or request PUBLIC approval later for the same CLASSROOM-approved immutable version.
- CLASSROOM approval permits assignment use in the owner's classrooms; it does not expose the test globally. PUBLIC approval permits global personal practice and also implies classroom eligibility.
- Approval runs the existing complete-content validator. Approving a new draft publishes it and archives any preceding active published version in one transaction. Attempts still reference their original frozen version.
- Published content needs a new draft and fresh moderation to change. Cloning a published version into a new draft remains possible while its PUBLIC request is pending.
- Bare publish cannot bypass moderation for teacher-origin content, even when called by ADMIN. Official ADMIN content keeps its existing publish flow.
- Revocation changes future visibility and starts. If CLASSROOM approval remains after PUBLIC revocation, classroom starts still work. Revoking the final approval blocks new starts without deleting existing attempts, assignments or results.

Library and personal Skill Practice request `public_only=true` on test/version reads, including direct Library links. This uses the same backend eligibility policy for every role, so a teacher's CLASSROOM-only content stays in their Builder and classroom workflow. The ADMIN overview retains its separate count of all Builder tests.

The ADMIN queue and detail page provide a read-only preview plus approve/reject/revoke actions. Owner requests and cancellation are in the teacher Builder toolbar. Backend policy enforcement also covers lower-level Reading, Listening, Writing, module, asset and transfer endpoints.

## Classrooms, invitations and notifications

A classroom has exactly one active TEACHER owner. The owner creates/updates/archives it; ADMIN can archive and restore it. Restore requires its owner to still be an active TEACHER. Archived classroom content and results remain readable, while new invitations, membership changes and assignment starts are blocked.

Invitations use normalized email addresses. An existing account receives an in-app invitation. An unknown email remains pending without an email delivery or automatic membership. Registration, password login and Google login bind matching pending invitations and create an idempotent notification. The invited account must explicitly accept or decline. Only that account may respond; concurrent acceptance creates one membership and one accepted transition.

Students may leave and owners may remove them. Membership periods retain `joined_at`/`left_at`; rejoining creates a new period. Invitation cancellation and classroom archival do not erase academic records.

Notifications are recipient-scoped events with a type, structured payload, entity reference and read timestamp. The header bell fetches an unread count and list, with Load more for older entries. Opening it does not mark notifications read; mark-one and mark-all are explicit actions. EN/VI text is rendered from payloads. Event creation is in the domain transaction and deduplicated; notifications grant no authority. The UI resets notification state when the signed-in recipient changes.

## Assignments and read-only results

An assignment references one immutable version. The owner can use their own actively CLASSROOM/PUBLIC-approved teacher content or published official ADMIN content. Another teacher's community content is not assignable to the owner's classroom. One approval can be used in multiple classrooms belonging to its author. Retries are allowed.

Assignment start supports available Reading/Listening/Writing modules, focused units and Full Mock. Existing lifecycle services create the attempts. Inside that transaction, the backend locks and checks the active account, version eligibility, classroom, assignment and membership. Browser-supplied provenance is rejected by ordinary attempt/session DTOs.

- Standalone and focused attempts store `Attempt.classroom_assignment_id`.
- Full Mock stores `TestSession.classroom_assignment_id`; its child attempts derive provenance from their parent session and keep their own assignment field null. A database check disallows dual provenance.
- Personal practice leaves both fields null.

A teacher result query must match the actual assignment provenance and the classroom's current teacher owner. `student_id + test_version_id`, membership or knowledge of UUIDs is insufficient. Personal practice on the same version stays private. Assignment-originated history remains readable after membership ends, classroom archival or approval revocation.

Result views reuse the existing student-owned read services only after this authorization. They show saved/submitted answers, objective correctness/reviews when unlocked, Writing text and existing manual/advisory AI results. They do not change timestamps, synchronize timers, edit answers, invoke assessment, mutate scores or allow teacher grading. Full Mock answer-key review remains locked until the session finishes. Result lists and the moderation queue provide Previous/Next pages, retaining filters and stable ordering.

## Surfaces and API groups

| UI | Purpose |
| --- | --- |
| `/teacher/tests`, `/teacher/tests/new`, `/teacher/tests/{testId}/versions/{versionId}/edit` | Owned Builder and moderation submission/cancellation. |
| `/teacher/classrooms` and classroom detail | Owner management, invitations, members, assignments and result navigation. |
| `/classrooms` and classroom detail | Invitation inbox, membership history and assignment starts for any signed-in role. |
| Classroom assignment result routes under `/teacher/classrooms/...` and `/classrooms/...` | Shared read-only result UI; neutral routes also support authorized ADMIN inspection. |
| `/admin/moderation`, `/admin/moderation/{requestId}` | ADMIN queue, preview and decisions. |
| Existing header, Library and ADMIN users | Notification bell, official/community attribution, TEACHER role controls and localized conflict messages. |

API groups under `/api/v1`:

- `/classrooms` (role-scoped list), `/classrooms/{id}/members`, `/classrooms/{id}/invitations`, `/classroom-invitations/{id}/{accept|decline|cancel}` and `/me/classroom-invitations`.
- `/classrooms/{id}/assignments`, assignment detail/archive and `/classroom-assignments/{id}/start`.
- `/classrooms/{id}/assignments/{assignmentId}/results`, `/students/{studentId}/attempts` and `/attempts/{attemptId}`.
- `/test-versions/{id}/moderation-requests`, `/test-moderation-requests/{id}/cancel`, `/admin/test-moderation-requests` and its detail/decision routes.
- `/notifications`, `/notifications/unread-count`, `/notifications/{id}/read` and `/notifications/read-all`.

## Deliberate v1 limits

No email delivery, realtime notification transport, co-teachers, ownership transfer, deadlines, retry limits, teacher grading, organization tenancy, full classroom analytics or Speaking was added. Existing scoring, timer, autosave, renderer, audio-policy and personal-practice behavior remains in the existing engines.

## Focused verification

Verification uses fictional fixtures and a new local PostgreSQL database. No browser, Playwright/E2E, dev server, build, live model/GPU, Modal or deployment is used. A fresh upgrade through `20261011_0024`, empty-domain downgrade to `20261011_0023`, and re-upgrade succeed. The migration history has one head.

From `backend/`, with `DATABASE_URL` and `TEST_DATABASE_URL` pointing to the isolated test database:

```powershell
uv run pytest tests/test_teacher_domain_models.py tests/test_teacher_roles_and_test_ownership.py tests/test_test_version_moderation.py tests/test_moderation_concurrency.py tests/test_classrooms_and_notifications.py tests/test_classroom_assignments.py tests/test_teacher_assignment_results.py tests/test_admin.py tests/test_auth.py tests/test_api_contract.py tests/test_asset_access.py tests/test_writing_builder.py tests/test_focused_attempts.py tests/test_full_mock_sessions.py tests/test_writing_attempts.py tests/test_attempt_scoring_history.py tests/test_test_version_concurrency.py tests/test_listening.py tests/test_asset_cloning.py tests/test_transfer.py tests/test_draft_import.py tests/test_writing_relevance.py tests/test_writing_ai_practice_feedback.py tests/test_writing_ai_observer_lifecycle.py tests/test_reading_publish_regression.py tests/test_test_lifecycle.py tests/test_lifecycle_refactor.py -q --tb=short
```

From `frontend/`:

```powershell
npx vitest run tests/teacher-classroom-ui.test.tsx tests/notification-center.test.tsx tests/teacher-api-contract.test.ts tests/teacher-builder-governance.test.tsx tests/teacher-pagination.test.tsx tests/auth.test.tsx tests/admin-api.test.ts tests/admin-user-detail.test.tsx tests/admin-user-list.test.tsx tests/app-shell.test.tsx tests/builder-workspace-page.test.tsx tests/builder-workspace-navigation.test.tsx tests/builder-route.test.tsx tests/writing-review.test.tsx tests/writing-ai-practice-feedback.test.tsx tests/practice-library.test.tsx tests/runner-localization.test.tsx tests/skill-practice.test.tsx tests/home-user-metric.test.tsx tests/interactive-planet.test.tsx
npm run typecheck
```

Results: **355 backend tests** and **269 frontend tests** passed. Typecheck passed. Ruff and ESLint are limited to changed/new source files using these PowerShell commands (from their respective backend/frontend directories):

```powershell
$repoRoot = git rev-parse --show-toplevel
$changedPython = @(git -C $repoRoot diff --name-only ad220178 -- '*.py'; git -C $repoRoot ls-files --others --exclude-standard -- '*.py') | Sort-Object -Unique | Where-Object { $_ -like 'backend/*' } | ForEach-Object { $_.Substring(8) }
uv run ruff check @changedPython
uv run ruff format --check @changedPython
```

```powershell
$repoRoot = git rev-parse --show-toplevel
$changedTs = @(git -C $repoRoot diff --name-only ad220178 -- '*.ts' '*.tsx'; git -C $repoRoot ls-files --others --exclude-standard -- '*.ts' '*.tsx') | Sort-Object -Unique | Where-Object { $_ -like 'frontend/*' } | ForEach-Object { $_.Substring(9) }
npx eslint @changedTs
```

Ruff check/format passed for 57 Python files; ESLint passed for 75 TS/TSX files. `git diff --check` is run before committing. The implementation plan records the regression coverage and review outcomes.
