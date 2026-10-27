# Teacher, classrooms and content governance

## Staff and Gradebook (P3)

Classrooms now resolve contextual owner, Co-teacher and TA capabilities separately from global roles. Staff invitations require acceptance; Gradebook uses canonical accepted results and human-final subjective grades, with classroom-only academic profiles and safe bounded CSV export. See [staff, Gradebook and Classroom UX/UI contracts](classroom-gradebook.md). P1/P2's owner-only descriptions below document those original phases; the capability matrix in the P3 guide governs current shared operations.

## Assignment scheduling and submission management (P2)

Assignments now support availability, inclusive due/cut-off boundaries, late acceptance, shared root-start limits, individual exceptions, private student progress, paginated teacher monitoring, a classroom agenda and in-app assignment notifications. The existing exam engines, grading and immutable-version provenance remain authoritative. See [the P2 policy, API, migration and reminder deployment guide](classroom-assignment-scheduling.md) for full semantics. Immediate policy enforcement and notifications work when the backend runs; periodic reminders require the documented host scheduler configuration.

## Classroom 2.0 workspace (P1)

The shared detail page for `/classrooms/{id}` and `/teacher/classrooms/{id}` now separates **Stream**, **Classwork**, **Assignments**, and **People**. Existing assignment creation, launch, provenance, results, and human/advisory AI grading remain in their existing components and services. The classroom header includes the teacher display name and authorized active membership count. Archived classrooms retain readable published content and are read-only.

### Content and authorization

- The teacher owner authors announcements/discussions, sections and TEXT/LINK/FILE resources. Content uses `DRAFT`, `PUBLISHED`, and `ARCHIVED`; staff can inspect drafts and archives. Student reads expose only published content. A published resource in an unpublished section remains hidden, including direct UUID and file access.
- ADMIN retains existing classroom archive/restore, management and read oversight, including drafts. P1 deliberately does **not** grant ADMIN authorship or moderation of another teacher's new learning content. Another teacher has no ownership rights. Existing historical memberships permit retained published reads; an active membership (or the teacher owner) is required for comments.
- Flat comment threads are cursor-paginated oldest-first. Authors can edit/retract their comments; the owner can moderate others. Retraction/moderation preserves the stored body and audit timestamps but returns an empty body to clients. Posts are archived rather than deleted. Locked discussions reject new comments.
- The Stream combines posts and canonical `ClassroomAssignment` rows with a bounded SQL UNION, so existing assignments need no backfill or independent lifecycle. Pinned entries precede the regular newest-first feed. Cursor keys include pin state, creation timestamp, content kind and UUID; timestamp ties are deterministic. Cursors are bound to the classroom/filter. As with normal keyset feeds, moving an entry across the cursor by pinning it during pagination can change its position; refreshing restarts the view.
- Markdown is stored as bounded text. The client renders a small subset (bold, italic, lists and HTTP/HTTPS links) as React nodes; raw HTML is never injected. Resource URLs require absolute HTTP/HTTPS addresses without embedded credentials.
- First publication of an announcement creates recipient-scoped notifications for active enrolled accounts, in the same transaction. Existing notification deduplication and a retained first-publication timestamp prevent repeat notifications after edits or republishing. Notifications grant no content access.

### Structured Classwork and ordering

Sections have stable UUIDs, explicit positions and independent publication states. Each item references exactly one resource or existing assignment. Composite foreign keys prevent cross-classroom section/resource/assignment placement. Resource and assignment placement is unique; assignment TestVersion references remain unchanged. Existing assignments without placement remain available in Assignments and the Uncategorized Classwork grouping.

Classroom row locks serialize every new write with archival and membership changes. Each classwork edit increments `classrooms.content_revision`. Reorder requests supply the revision and complete desired target order; stale revisions return `409 CLASSWORK_CHANGED`. The server validates every identifier, normalizes positions and moves references atomically. Keyboard move controls complement drag and drop. The client refreshes after successful writes and exposes failures without pretending they succeeded.

### Private files

Files use the existing local storage abstraction under `storage/classroom-resources/`, with generated UUID filenames. PostgreSQL stores metadata and a private storage key, never binary content. Storage keys and filesystem paths are omitted from public DTOs. The file endpoint rechecks classroom membership/history, publication and containing-section visibility on every request.

Uploads are bounded to **20 MiB** and allow PDF, PNG, JPEG, WebP, UTF-8 plain text and DOCX. Filename traversal/control characters, unsupported MIME/extension pairs and mismatched signatures are rejected. DOCX containers have entry/uncompressed-size limits and reject macro payloads and unsafe member paths. No new external storage service is used. Upload staging follows the existing shielded worker pattern; failed attachment transactions check durable references and remove unreferenced files. If a database outage makes the outcome unknowable, the file is retained and the compensation failure is logged, avoiding deletion of a possibly committed resource. Archived resource files are retained with their history.

Downloads send private/no-store and nosniff headers. PDF/images may be viewed inline through the authenticated endpoint; other supported documents download as attachments. External links open with safe external-link attributes.

The resource viewer fetches private files through the existing refresh-aware HTTP client before creating temporary browser Blob URLs. This keeps downloads working when the short-lived access cookie has expired but the login session is still valid. Pending requests are cancelled and Blob URLs are revoked when the viewer closes.

### Database and endpoints

Revision **`20261027_0036`**, following `20261013_0035`, adds `classroom_sections`, `classroom_resources`, `classroom_content_items`, `classroom_posts`, `classroom_post_resources`, and `classroom_comments`, plus `classrooms.content_revision`, notification enum values and supporting keys/indexes. The migration is additive and does not rewrite existing assignments, attempts or TestVersion data. Downgrade refuses retained workspace/notification history; additive PostgreSQL enum labels remain after an empty-domain downgrade.

New endpoint groups beneath `/api/v1/classrooms/{id}`:

| Paths | Operations |
| --- | --- |
| `/feed` | GET cursor page, bounded `limit`, staff-only optional status filter |
| `/posts`, `/posts/{postId}` | POST create; GET detail; PATCH edit/lifecycle/lock |
| `/posts/{postId}/{publish,archive,pin}` | POST publication, archival and pin changes |
| `/posts/{postId}/comments` | GET cursor page; POST comment |
| `/comments/{commentId}` | PATCH own comment; DELETE retract/moderate |
| `/classwork` | GET authorized sections/resources/items and revision |
| `/sections`, `/sections/{sectionId}`, `/sections/reorder` | GET/POST, PATCH, POST full section order |
| `/resources`, `/resources/{resourceId}` | GET/POST, GET/PATCH content metadata |
| `/resources/upload`, `/resources/{resourceId}/file` | POST multipart upload; GET authenticated file (`inline=true` for PDF/images) |
| `/items`, `/items/reorder` | POST canonical assignment placement; POST move/reorder target items |

P1 does not introduce deadlines, availability windows, cutoff policies, attempt limits, late submission rules, extensions, gradebook, attendance, analytics, recommendations, co-teachers, teaching assistants, email or realtime transport. The Markdown editor is intentionally lightweight and comments are flat. File replacement and permanent content deletion are not offered. Existing exam timers and grading policies remain authoritative.

### P1 focused verification

With `DATABASE_URL` and `TEST_DATABASE_URL` set to an isolated PostgreSQL test database migrated through head, run from `backend/`:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_classroom_resource_storage.py tests/test_classroom_classwork_unit.py tests/test_classroom_classwork.py tests/test_classroom_posts.py tests/test_classroom_assignments.py tests/test_classrooms_and_notifications.py -p no:cacheprovider -q
```

Verified **101 passing backend cases**, including permission failures, hidden-section/file UUID access, archived read-only mutations, revision conflicts, assignment identity preservation, announcement deduplication, equal-timestamp feed pagination, upload compensation and frozen migration contracts. The additive migration also upgraded a fresh isolated database through `20261027_0036` successfully.

From `frontend/`, the focused Vitest scope is `tests/classroom-content.test.tsx`, `tests/classroom-content-api.test.ts`, `tests/teacher-classroom-ui.test.tsx`, `tests/teacher-api-contract.test.ts`, `tests/teacher-pagination.test.tsx`, and `tests/notification-center.test.tsx`: **57 passing cases**. Scoped Ruff/ESLint, TypeScript and task-scoped `git diff --check` also passed. Independent source review findings were resolved with regression coverage.

No browser, screenshots, E2E, production build or full repository test suite was run under this task's execution limits. Visual layout is reviewed statically and remains unverified in a real browser.

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

## Assignments and results

An assignment references one immutable version. The owner can use their own actively CLASSROOM/PUBLIC-approved teacher content or published official ADMIN content. Another teacher's community content is not assignable to the owner's classroom. One approval can be used in multiple classrooms belonging to its author. Retries are allowed.

Assignment start supports available Reading/Listening/Writing/Speaking modules, focused units and Full Mock. Existing lifecycle services create the attempts. Inside that transaction, the backend locks and checks the active account, version eligibility, classroom, assignment and membership. Browser-supplied provenance is rejected by ordinary attempt/session DTOs.

- Standalone and focused attempts store `Attempt.classroom_assignment_id`.
- Full Mock stores `TestSession.classroom_assignment_id`; its child attempts derive provenance from their parent session and keep their own assignment field null. A database check disallows dual provenance.
- Personal practice leaves both fields null.

A teacher result query must match the actual assignment provenance and the classroom's current teacher owner. `student_id + test_version_id`, membership or knowledge of UUIDs is insufficient. Personal practice on the same version stays private. Assignment-originated history remains readable after membership ends, classroom archival or approval revocation.

Result views reuse the existing student-owned read services only after this authorization. They show saved/submitted answers, objective correctness/reviews when unlocked, Writing text and existing manual/advisory AI results. Result reads do not change timestamps, synchronize timers, edit answers or invoke assessment. Authorized teachers explicitly save Writing/Speaking human final criteria through separate assignment-scoped mutations; objective results remain read-only. Full Mock answer-key review remains locked until the session finishes. Result lists and the moderation queue provide Previous/Next pages, retaining filters and stable ordering.

## Surfaces and API groups

| UI | Purpose |
| --- | --- |
| `/teacher/tests`, `/teacher/tests/new`, `/teacher/tests/{testId}/versions/{versionId}/edit` | Owned Builder and moderation submission/cancellation. |
| `/teacher/classrooms` and classroom detail | Owner management, invitations, members, assignments and result navigation. |
| `/classrooms` and classroom detail | Invitation inbox, membership history and assignment starts for any signed-in role. |
| Classroom assignment result routes under `/teacher/classrooms/...` and `/classrooms/...` | Shared result UI with teacher subjective grading and read-only objective results; neutral routes also support authorized ADMIN inspection. |
| `/admin/moderation`, `/admin/moderation/{requestId}` | ADMIN queue, preview and decisions. |
| Existing header, Library and ADMIN users | Notification bell, official/community attribution, TEACHER role controls and localized conflict messages. |

API groups under `/api/v1`:

- `/classrooms` (role-scoped list), `/classrooms/{id}/members`, `/classrooms/{id}/invitations`, `/classroom-invitations/{id}/{accept|decline|cancel}` and `/me/classroom-invitations`.
- `/classrooms/{id}/assignments`, assignment detail/archive and `/classroom-assignments/{id}/start`.
- `/classrooms/{id}/assignments/{assignmentId}/results`, `/students/{studentId}/attempts` and `/attempts/{attemptId}`.
- `/test-versions/{id}/moderation-requests`, `/test-moderation-requests/{id}/cancel`, `/admin/test-moderation-requests` and its detail/decision routes.
- `/notifications`, `/notifications/unread-count`, `/notifications/{id}/read` and `/notifications/read-all`.

## Deliberate v1 limits

No email delivery, realtime notification transport, co-teachers, ownership transfer, deadlines, retry limits, organization tenancy or full classroom analytics was added. Writing/Speaking human final grading is supported as described below. Existing scoring, timer, autosave, renderer, audio-policy and personal-practice behavior remains in the existing engines.

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


## Human final subjective grading

Writing and Speaking AI assessments remain advisory. In personal practice, the attempt owner may enter criteria or copy a completed AI assessment into the form, edit it, and explicitly Save a final practice score. Copying never persists a score. Writing annotations remain pedagogical feedback and do not enter grading arithmetic.

For classroom attempts, students cannot enter, revise, or copy AI into final scores. They see “Waiting for teacher grading” (VI: “Đang chờ giáo viên chấm”) until a human final score exists. The owning classroom teacher grades through assignment-scoped routes; administrators retain final grading authority. A teacher cannot grade personal work even when the student and test version match an assignment. Historical assignment results remain gradeable after membership ends.

Classroom provenance means either the attempt has a classroom assignment ID or its parent Full Mock TestSession has one. Both skills use the same authorization policy. Active attempts and children of an IN_PROGRESS Full Mock remain locked. Objective classroom results remain read-only.

Speaking final FC/LR/GRA/PR criteria and optional feedback are stored independently in `attempt_speaking_scores` (Alembic `20261013_0033`). Explicit human Save uses the existing equal-weight Speaking overall calculation. AI workers never write human final scores. Focused Speaking keeps its final criterion assessment without creating a whole-module analytics band; focused Writing likewise preserves task-only grading.

The backend exposes `grading.context`, `can_edit_final`, `can_copy_ai_to_final`, and `waiting_for_teacher` in subjective reviews and classroom result detail. Clients render these capabilities; mutation routes recheck authorization. Generic owner/admin routes are `PUT /attempts/{id}/writing-scores/{task_id}` and `PUT /speaking-attempts/{id}/final-score`. Teacher routes are `PUT /classrooms/{classroom_id}/assignments/{assignment_id}/attempts/{id}/writing-scores/{task_id}` and the same assignment prefix ending in `/speaking-score`.
