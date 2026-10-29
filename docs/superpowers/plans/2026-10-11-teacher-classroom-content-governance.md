# Teacher, Classroom, Content Governance & Notification Implementation Plan

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Teacher, Classroom, Content Governance & Notification Implementation Plan. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [current module/guide](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TEACHER accounts, teacher-owned tests with ADMIN moderation, classrooms/invitations/assignments, generic in-app notifications, and read-only teacher access to assignment-originated student work without weakening existing USER/ADMIN security or history semantics.

**Architecture:** Keep the existing `Test`/`TestVersion` content lifecycle (`DRAFT`, `PUBLISHED`, `ARCHIVED`) and layer ownership, moderation, classroom access and notification resources around it. Authorization is server-side and resource-scoped; assignment provenance, not student membership plus test identity, is the boundary that lets a teacher inspect student work. Frontend work is intentionally minimal: expose the approved flows, reuse existing Builder/review components where possible, and do not introduce a separate visual-design project.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL/Alembic, Pydantic, Next.js 16, React 19, TypeScript, Zod, Vitest/RTL.

**Spec:** `docs/superpowers/specs/2026-10-11-teacher-classroom-content-governance-design.md`

## Global Constraints

- Public registration always creates `USER`; only ADMIN may promote `USER -> TEACHER`.
- `TEACHER` keeps normal USER capabilities; it is not a separate account table.
- Teacher-created content remains teacher-owned after approval; ADMIN moderation must never silently transfer ownership.
- Every teacher-created version must be ADMIN-approved before another user can use it, including classroom-only use.
- `CLASSROOM` and `PUBLIC` moderation are separate scopes; PUBLIC approval implies classroom eligibility, not vice versa.
- Keep `VersionStatus = DRAFT | PUBLISHED | ARCHIVED`; moderation state belongs in a separate table.
- Approved/published teacher versions are immutable; editing requires a new draft/version and fresh moderation.
- Each classroom has exactly one teacher owner in v1; no co-teacher or ownership-transfer workflow.
- Invitations are in-app only in v1; unknown emails remain pending until a matching account authenticates, and students must Accept/Decline explicitly.
- Assignment provenance is authoritative for teacher result access. Personal practice on the same test remains private.
- Teacher result access is read-only; existing ADMIN-only Writing grading mutations remain ADMIN-only.
- Archive/revocation changes future activity/visibility but never deletes academic history.
- Notifications are generic UX/event projections and never authorization tokens.
- Assignment retries are allowed; do not add a one-attempt-per-student unique constraint.
- Preserve current official/admin test visibility and existing attempt/history behavior outside classrooms.
- Current migration head at plan creation is `20261011_0023`; create the next migration from the actual head after pulling main and do not fork Alembic history if upstream moved.
- Keep validation focused and cheap: unit/integration tests only; no browser, Playwright, E2E, dev server, live model/GPU, Modal or deployment.

## Review Focus

1. Two concurrent Accept requests for the same invitation must create one active membership and one accepted transition, not duplicate rows.
2. A teacher who knows another teacher's test/version/classroom/assignment IDs must still receive 403/404 according to project conventions; IDs never bypass ownership checks.
3. Revoking PUBLIC approval while CLASSROOM approval remains must remove global visibility but preserve classroom eligibility; revoking the final active approval must block new assignment starts without deleting history.
4. Approving v2 of a test must never mutate attempts bound to v1; previous published content/history remains referentially valid even if v1 becomes archived for future starts.
5. Pending invitation binding on repeated login/registration must be idempotent: no duplicate invitation binding, membership, or notification.

---

### Task 1: Domain enums, persistence model, and Alembic migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/entities.py`
- Create: `backend/app/models/content_governance.py`
- Create: `backend/app/models/classroom.py`
- Create: `backend/app/models/notifications.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20261011_0024_teacher_classroom_governance.py` (or the next revision from the actual pulled head)
- Test: `backend/tests/test_teacher_domain_models.py`

**Interfaces:**
- Produces `UserRole.TEACHER` plus `TestOrigin`, `ModerationScope`, `ModerationStatus`, `ClassroomStatus`, `InvitationStatus`, `AssignmentStatus`, and the notification type/entity enums used by later tasks.
- Produces `Test.owner_user_id`, `Test.origin`, `TestVersionModeration`, `Classroom`, `ClassroomInvitation`, `ClassroomMembership`, `ClassroomAssignment`, `Notification`, and nullable assignment provenance FKs on `Attempt`/`TestSession` as selected below.
- Full-mock provenance lives on `TestSession.classroom_assignment_id`; standalone/focused module provenance lives on `Attempt.classroom_assignment_id`. Do not duplicate the full-mock assignment FK onto child attempts unless an existing query requires it and tests justify the duplication.

- [x] **Step 1: Write failing model/migration contract tests**

Add focused tests asserting the new enum values, teacher/test ownership columns, one-active-membership uniqueness, one-pending-invite uniqueness, one-pending-moderation-per-scope uniqueness, notification recipient/index fields, and nullable assignment provenance columns. Include a legacy test proving `origin=ADMIN, owner_user_id=NULL` is representable for pre-migration official tests.

- [x] **Step 2: Run the model tests and verify they fail**

Run: `cd backend && uv run pytest tests/test_teacher_domain_models.py -q`

Expected: FAIL because the enums/models/columns do not exist yet.

- [x] **Step 3: Implement the ORM model and migration contract**

Use separate focused model files for new subsystems instead of expanding `entities.py` further. The migration must safely add `TEACHER` to PostgreSQL `user_role`, backfill existing tests as `origin=ADMIN` with nullable legacy owner, create the new tables/indexes/constraints, and preserve all existing rows/FKs. New application-created tests will require an owner even though the DB column remains nullable for legacy official content.

- [x] **Step 4: Run model tests and migration smoke checks**

Run: `cd backend && uv run pytest tests/test_teacher_domain_models.py -q`

Run the repository's existing Alembic upgrade/downgrade smoke command if present; otherwise run the smallest existing migration test target. Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/models backend/alembic/versions backend/tests/test_teacher_domain_models.py
git commit -m "Add teacher classroom governance domain model"
```

---

### Task 2: Teacher role administration, policy layer, and test ownership

**Files:**
- Create: `backend/app/services/access_policy.py`
- Modify: `backend/app/services/admin.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/api/v1/admin.py`
- Modify: `backend/app/services/tests.py`
- Modify: `backend/app/api/v1/tests.py`
- Modify: `backend/app/schemas/tests.py`
- Modify: `backend/app/api/v1/assets.py`
- Modify the existing Reading/Listening/Writing/question builder mutation routes/services that currently rely on ADMIN-only access or `ensure_draft` without ownership context.
- Test: `backend/tests/test_teacher_roles_and_test_ownership.py`
- Test regression: `backend/tests/test_admin.py`

**Interfaces:**
- Produces centralized policy methods equivalent to `require_test_create`, `require_test_edit`, `require_version_mutable`, `require_classroom_manage`, `require_assignment_view`, and `require_admin_moderation` that later services call before mutations/reads.
- `TestService.create_test(..., actor)` records `origin` and `owner_user_id`; teacher list/read responses expose only owned private/draft content plus otherwise-readable content, while ordinary USER behavior remains published-access only.

- [x] **Step 1: Write failing authorization tests**

Cover ADMIN promotion USER→TEACHER; public registration remaining USER; teacher creation of an owned test; USER create forbidden; teacher editing own draft allowed; teacher editing another teacher's test forbidden; teacher mutating an approved/published version forbidden; ADMIN override retained; and demotion returning `TEACHER_HAS_ACTIVE_RESOURCES` when active teacher resources/pending moderation exist.

- [x] **Step 2: Run the focused authorization tests and verify failure**

Run: `cd backend && uv run pytest tests/test_teacher_roles_and_test_ownership.py tests/test_admin.py -q`

Expected: new tests FAIL on missing role/policy/ownership behavior while existing ADMIN tests still pass or expose intentional contract changes.

- [x] **Step 3: Implement policy-based Builder authorization**

Keep `AdminUser` for genuinely ADMIN-only endpoints such as official Writing grading. For Builder/content mutation endpoints, use authenticated users plus the centralized resource policy; do not replace `AdminUser` with unrestricted `CurrentUser`. Thread actor/resource checks through asset and Reading/Listening/Writing/question mutations so a teacher cannot bypass ownership by calling a lower-level builder endpoint directly.

- [x] **Step 4: Run focused backend tests**

Run: `cd backend && uv run pytest tests/test_teacher_roles_and_test_ownership.py tests/test_admin.py tests/test_writing_builder.py tests/test_asset_access.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/services backend/app/api/v1 backend/app/schemas backend/tests
git commit -m "Add teacher role and owned Builder access"
```

---

### Task 3: Version moderation and official/community visibility

**Files:**
- Create: `backend/app/schemas/content_governance.py`
- Create: `backend/app/repositories/content_governance.py`
- Create: `backend/app/services/content_governance.py`
- Create: `backend/app/api/v1/content_governance.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/services/tests.py`
- Modify: `backend/app/api/v1/tests.py`
- Modify: `backend/app/api/v1/presenters.py` if ownership/origin/moderation metadata belongs in existing test/version DTOs.
- Test: `backend/tests/test_test_version_moderation.py`
- Test regression: `backend/tests/test_api_contract.py`

**Interfaces:**
- Produces teacher `submit_moderation(version_id, scope, note, actor)`, `cancel_request(request_id, actor)`, ADMIN `approve/reject/revoke`, and `version_access(version, user)` helpers used by library/classroom tasks.
- A version with any PENDING moderation request is locked against content mutation. First successful teacher approval transitions the version to immutable `PUBLISHED`; later PUBLIC approval may reuse the same published version. PUBLIC approval grants global community visibility and classroom eligibility; CLASSROOM approval grants only classroom eligibility.

- [x] **Step 1: Write failing moderation/state-machine tests**

Cover submit/cancel; duplicate pending request conflict; draft lock while review pending; owner-only submit; ADMIN-only review; approve/reject idempotency/concurrency semantics; PUBLIC/CLASSROOM independence; PUBLIC⇒classroom eligibility; public visibility only after PUBLIC approval; legacy/admin official published tests staying globally visible; revocation rules; and v2 approval preserving v1-bound history while preventing mutation of published versions.

- [x] **Step 2: Run moderation tests and verify failure**

Run: `cd backend && uv run pytest tests/test_test_version_moderation.py tests/test_api_contract.py -q`

Expected: FAIL on missing moderation APIs/service/visibility policy.

- [x] **Step 3: Implement moderation service and API**

Persist every submission as an audit row instead of overwriting prior decisions. Use transactional row locking or the project's equivalent concurrency pattern for approve/reject/cancel/revoke. When a newer version becomes the active published version, preserve the prior version and every referencing attempt/session; archive it only for future content selection, never rewrite historical foreign keys. Notify the teacher through the Notification service interface introduced in Task 4; until Task 4 lands, keep notification emission behind a small injectable/no-op interface rather than coupling moderation to raw notification inserts.

- [x] **Step 4: Run moderation and library regressions**

Run: `cd backend && uv run pytest tests/test_test_version_moderation.py tests/test_api_contract.py tests/test_asset_access.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/schemas/content_governance.py backend/app/repositories/content_governance.py backend/app/services/content_governance.py backend/app/api/v1/content_governance.py backend/app/api/v1/router.py backend/app/services/tests.py backend/app/api/v1/tests.py backend/app/api/v1/presenters.py backend/tests/test_test_version_moderation.py backend/tests/test_api_contract.py
git commit -m "Add teacher test moderation workflow"
```

---

### Task 4: Classrooms, invitations, membership, and notifications

**Files:**
- Create: `backend/app/schemas/classrooms.py`
- Create: `backend/app/repositories/classrooms.py`
- Create: `backend/app/services/classrooms.py`
- Create: `backend/app/api/v1/classrooms.py`
- Create: `backend/app/schemas/notifications.py`
- Create: `backend/app/repositories/notifications.py`
- Create: `backend/app/services/notifications.py`
- Create: `backend/app/api/v1/notifications.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/services/auth.py` (or the exact existing post-auth hook) to bind pending invitations idempotently after matching-email registration/login.
- Test: `backend/tests/test_classrooms_and_notifications.py`

**Interfaces:**
- Produces classroom CRUD/archive/restore, invitation create/cancel/accept/decline, member remove/leave, `NotificationService.create_once(...)`, list/unread-count/read/read-all, and `bind_pending_invitations(user)`.
- Notifications are unique/idempotent per recipient + event type + entity identity; notification actions always reload and authorize the underlying invitation/classroom/moderation entity.

- [x] **Step 1: Write failing classroom/invitation/notification tests**

Cover one-owner TEACHER classroom creation; USER create forbidden; other-teacher management forbidden; archive read-only semantics; ADMIN archive/restore; invite existing and unknown email; duplicate invite prevention; explicit Accept/Decline; email mismatch rejection; double-Accept concurrency; leave/remove preserving historical membership; unknown-email invitation binding on later login; repeated login creating no duplicate notification; unread count; mark-one/read-all; and notification entity IDs not bypassing authorization.

- [x] **Step 2: Run classroom tests and verify failure**

Run: `cd backend && uv run pytest tests/test_classrooms_and_notifications.py -q`

Expected: FAIL because classroom/notification APIs do not exist.

- [x] **Step 3: Implement classroom and notification services**

Use transactional membership/invitation resolution. Do not hard-delete classroom or membership history. Archived classrooms reject new invites/member changes/assignments/starts. Keep email delivery out of scope. Wire moderation approve/reject notifications through `NotificationService.create_once` now that the service exists.

- [x] **Step 4: Run classroom plus auth regressions**

Run: `cd backend && uv run pytest tests/test_classrooms_and_notifications.py tests/test_admin.py -q`

Add the smallest existing auth test file if needed for login/registration hooks. Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/schemas/classrooms.py backend/app/repositories/classrooms.py backend/app/services/classrooms.py backend/app/api/v1/classrooms.py backend/app/schemas/notifications.py backend/app/repositories/notifications.py backend/app/services/notifications.py backend/app/api/v1/notifications.py backend/app/api/v1/router.py backend/app/services/auth.py backend/tests/test_classrooms_and_notifications.py
git commit -m "Add classrooms invitations and notifications"
```

---

### Task 5: Classroom assignments and durable attempt provenance

**Files:**
- Extend: `backend/app/schemas/classrooms.py`
- Extend: `backend/app/repositories/classrooms.py`
- Extend: `backend/app/services/classrooms.py`
- Extend: `backend/app/api/v1/classrooms.py`
- Modify: `backend/app/services/attempts.py`
- Modify: `backend/app/services/test_sessions.py`
- Modify: `backend/app/schemas/attempts.py` only if an internal assignment-start adapter DTO is needed; do not let the normal public attempt-start API accept arbitrary assignment provenance.
- Test: `backend/tests/test_classroom_assignments.py`
- Test regression: `backend/tests/test_focused_attempts.py`
- Test regression: existing TestSession/full-mock tests.

**Interfaces:**
- Produces `create_assignment`, `archive_assignment`, assignment list/detail, and `start_assignment(assignment_id, request, actor)`.
- `start_assignment` derives `test_version_id`, classroom, teacher and provenance from the assignment. Support both module/focused attempt starts and full-mock/TestSession starts by adapting to existing services; the browser never attaches an assignment to an existing attempt/session.

- [x] **Step 1: Write failing assignment/provenance tests**

Cover assignment only from active owned classroom; teacher-owned version requires CLASSROOM or PUBLIC approval; ADMIN official published tests are assignable; revoked/archived versions and archived classrooms reject new assignments/starts; only active members may start; retries create separate attempts/sessions; provenance is persisted; arbitrary normal `/attempts` or `/test-sessions` calls cannot forge assignment provenance; and old submissions remain readable after membership ends.

- [x] **Step 2: Run focused assignment tests and verify failure**

Run: `cd backend && uv run pytest tests/test_classroom_assignments.py tests/test_focused_attempts.py -q`

Expected: FAIL on missing assignment/start/provenance behavior.

- [x] **Step 3: Implement assignment start orchestration**

Reuse `AttemptService` and `TestSessionService` for the actual exam lifecycle instead of creating parallel attempt logic. Pass trusted provenance internally from `start_assignment`; keep the existing normal start DTOs backward compatible. For full mock, store assignment provenance on `TestSession`; for standalone/focused module work, store it on `Attempt`.

- [x] **Step 4: Run assignment and lifecycle regressions**

Run the new assignment test plus the smallest existing attempt/TestSession regression set that covers full module, focused unit and full mock. Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/schemas/classrooms.py backend/app/repositories/classrooms.py backend/app/services/classrooms.py backend/app/api/v1/classrooms.py backend/app/services/attempts.py backend/app/services/test_sessions.py backend/app/schemas/attempts.py backend/tests/test_classroom_assignments.py backend/tests/test_focused_attempts.py
git commit -m "Add classroom assignments and attempt provenance"
```

---

### Task 6: Teacher read-only assignment results

**Files:**
- Create: `backend/app/services/classroom_results.py`
- Extend: `backend/app/schemas/classrooms.py`
- Extend: `backend/app/api/v1/classrooms.py`
- Reuse, without weakening: existing attempt review/history presenters/services in `backend/app/services/attempts.py`, `backend/app/schemas/attempts.py`, Writing AI read models, and scoring/history services.
- Test: `backend/tests/test_teacher_assignment_results.py`

**Interfaces:**
- Produces assignment result summary and per-student attempt/session detail endpoints that authorize strictly through assignment provenance + classroom owner.
- Result detail is read-only and may include existing Listening/Reading answers/correctness/bands, Writing submission, existing manual/official score and existing AI result/feedback already associated with the authorized attempt.

- [x] **Step 1: Write failing teacher-result privacy tests**

Cover teacher can read own assignment-originated result after student leaves; teacher cannot read another teacher's assignment; same student + same test done as personal practice remains private; USER cannot use teacher result endpoints; and teacher cannot call existing ADMIN Writing score mutation even for an owned-classroom submission.

- [x] **Step 2: Run the result/privacy tests and verify failure**

Run: `cd backend && uv run pytest tests/test_teacher_assignment_results.py tests/test_writing_attempts.py -q`

Expected: FAIL on missing teacher result endpoints while ADMIN grading regression stays protected.

- [x] **Step 3: Implement provenance-scoped read-only result service**

Reuse existing review/read models after first authorizing `(assignment.classroom.teacher_id == actor.id)` and matching the attempt/session provenance. Do not add a broad `allow_any_user=True` path for teachers and do not expose a teacher-wide student history endpoint.

- [x] **Step 4: Run privacy and grading regressions**

Run: `cd backend && uv run pytest tests/test_teacher_assignment_results.py tests/test_writing_attempts.py tests/test_attempt_scoring_history.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/services/classroom_results.py backend/app/schemas/classrooms.py backend/app/api/v1/classrooms.py backend/tests/test_teacher_assignment_results.py
git commit -m "Add read-only teacher assignment results"
```

---

### Task 7: Minimal frontend role, classroom, moderation, Builder, and notification UX

**Files:**
- Modify: `frontend/src/lib/api/auth.ts`
- Modify: `frontend/src/lib/api/admin.ts`
- Modify: `frontend/src/lib/api/tests.ts`
- Create: `frontend/src/lib/api/classrooms.ts`
- Create: `frontend/src/lib/api/content-governance.ts`
- Create: `frontend/src/lib/api/notifications.ts`
- Modify: `frontend/src/components/ui/global-header.tsx`
- Modify: `frontend/src/components/ui/app-shell.tsx`
- Modify: `frontend/src/lib/i18n/translations.ts`
- Modify: `frontend/src/features/auth/admin-user-actions.tsx`
- Reuse/refactor existing `frontend/src/features/test-builder/*` so TEACHER gets an owner-scoped Builder entry point without entering the ADMIN dashboard.
- Create minimal role-neutral/teacher pages under `frontend/src/app/teacher/` for owned tests and classrooms, and ADMIN moderation pages under `frontend/src/app/admin/` using existing shared components where practical.
- Create: `frontend/src/features/classrooms/*` focused components for classroom detail, invitations, assignments and read-only result navigation.
- Create: `frontend/src/features/notifications/notification-center.tsx`
- Test: `frontend/tests/teacher-classroom-ui.test.tsx`
- Test: `frontend/tests/notification-center.test.tsx`
- Test regression: existing auth/admin/i18n shell tests.

**Interfaces:**
- Auth Zod schema accepts `USER | TEACHER | ADMIN` and renders a localized teacher role label.
- Teacher navigation exposes Builder/Classrooms; ADMIN keeps Admin/Builder and gets moderation; USER sees neither teacher nor admin authoring actions.
- Header notification bell shows backend unread count; opening the panel does not mark all read; actions call real invitation endpoints.

- [x] **Step 1: Write failing UI/API contract tests**

Cover TEACHER parsing; role-specific nav; ADMIN role promotion control; USER/TEACHER/ADMIN action visibility; teacher owner-only Builder links; classroom invitation Accept/Decline; classroom assignment list/start; read-only teacher result label; moderation approve/reject actions ADMIN-only; Official vs Community attribution in Library; notification unread count plus mark-one/read-all; and EN/VI translations for all new chrome.

- [x] **Step 2: Run only the new/relevant Vitest files and verify failure**

Run: `cd frontend && npm test -- --run tests/teacher-classroom-ui.test.tsx tests/notification-center.test.tsx`

Expected: FAIL on missing role/schema/components.

- [x] **Step 3: Implement the minimal approved UI**

Keep layout simple; do not start an unrelated redesign. Reuse existing Builder and attempt-review components, add clear `Official` versus `Community · contributed by <teacher>` labeling, show archived classroom/history read-only states, and never expose mutation controls on teacher result views.

- [x] **Step 4: Run frontend focused tests and typecheck**

Run the new tests plus the smallest existing auth/admin/i18n shell tests, then `cd frontend && npm run typecheck`. Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add frontend/src frontend/tests
git commit -m "Add teacher classroom and moderation UI"
```

---

### Task 8: Documentation, security regression sweep, and final verification

**Files:**
- Modify: `README.md` or the project's existing developer/user documentation entry point only where teacher/classroom setup belongs.
- Create or update: `docs/teacher-classrooms.md` if no suitable existing doc exists.
- Update API/docs/tests only for intentional contract changes discovered in Tasks 1–7.

**Interfaces:**
- Documents the three roles, ownership/Official-vs-Community semantics, moderation scopes, classroom invitation lifecycle, assignment provenance/privacy rule, archive behavior, and the v1 non-goals (no email, no co-teacher, no teacher grading mutations, no realtime notification requirement, no attempt limit).

- [x] **Step 1: Add/refresh focused regression assertions for the five Review Focus cases**

Ensure each Review Focus item is pinned by a concrete backend/frontend test from the owning task; add only missing assertions, not duplicate suites.

- [x] **Step 2: Run the focused backend suite**

Run the new teacher/classroom/moderation/result tests plus targeted `test_admin.py`, `test_api_contract.py`, `test_asset_access.py`, `test_writing_builder.py`, focused attempt/TestSession tests, and Writing grading/history regressions. Expected: PASS.

- [x] **Step 3: Run static checks**

Run Ruff on changed Python files, relevant frontend Vitest tests, `npm run typecheck`, relevant ESLint scope if supported, and `git diff --check`. Do not run Playwright/E2E/browser/dev server/build unless a focused failure requires it.

- [x] **Step 4: Update documentation and inspect the final diff**

Confirm there are no generated/cache artifacts, no accidental relaxation of ADMIN-only Writing grading, no public registration path that can self-assign TEACHER, and no teacher result query authorized by `student_id + test_version_id` alone.

- [x] **Step 5: Commit and push**

```bash
git add docs README.md backend frontend
git commit -m "Document teacher classroom workflows"
git status
git push origin main
```

Final report must include final commit SHAs, migration revision, exact focused test commands/pass counts, ownership/moderation behavior, invitation/notification behavior, assignment provenance/privacy behavior, UI routes added, deliberate v1 non-goals, and confirmation that `origin/main` contains the implementation and the working tree is clean.

## Implementation record — 2026-10-11

Baseline after fetching and fast-forwarding main: `ad2201783bd39cd4127204d9d3d358a2506dc0c0`. The actual starting Alembic head was `20261011_0023`; the single new head is `20261011_0024`.

Tasks 1–7 were implemented with focused failing tests before their production changes. Backend tasks were grouped into domain (`20d09c9`), role/ownership (`321d4e6`), moderation/classrooms/notifications (`d07b6e5`) and assignment provenance/read-only results (`6a29080`). Frontend workflows/localization are in `cec1213`; documentation follows in the final commit.

Implementation choices within the approved architecture:

- Assignment and result schemas/services/routes live in focused `classroom_assignments` and `classroom_results` files rather than enlarging the classroom service.
- Full Mock provenance lives only on its `TestSession`; standalone/focused provenance lives on `Attempt`. A database check rejects child attempts with a second assignment identity.
- Owner cancellation uses the durable moderation state `CANCELLED`, distinct from reviewer rejection. Version lifecycle states are unchanged.
- The OCR CLI now requires `--owner-user-id ADMIN_UUID`; imports cannot create content under an invented actor.
- A final independent review identified and rechecked two fixes: personal Library/Practice uses server `public_only` eligibility even for authors, and result/moderation/notification lists expose older records through pagination. ADMIN overview Builder counts retain their previous meaning.

The five Review Focus cases are pinned by concrete tests:

| Case | Regression |
| --- | --- |
| Concurrent invitation acceptance | `test_classrooms_and_notifications.py::test_concurrent_accept_creates_exactly_one_membership` |
| Known foreign resource IDs do not bypass ownership | `test_teacher_roles_and_test_ownership.py`, `test_classrooms_and_notifications.py::test_other_teacher_cannot_manage_members_invites_or_known_classroom_ids`, `test_teacher_assignment_results.py::test_result_paths_scope_assignment_classroom_and_student_without_cross_resource_leaks` |
| PUBLIC revocation retains an independent CLASSROOM approval | `test_classroom_assignments.py::test_revoking_public_keeps_classroom_starts_until_final_approval_is_revoked` |
| v2 approval preserves frozen v1 history | `test_test_version_moderation.py::test_classroom_v2_replaces_public_v1_and_preserves_attempt_history` |
| Repeated authentication binds invitations once, without joining | `test_classrooms_and_notifications.py::test_future_auth_binds_pending_email_once_without_auto_join` |

Final focused commands are reproduced in [teacher-classrooms.md](../../teacher-classrooms.md#focused-verification). Results on the final source tree:

- Backend: **355 passed** across 27 affected test files, with no failures or warnings.
- Frontend: **269 passed** across 20 affected test files.
- `npm run typecheck`: passed.
- Ruff check and format check: passed on all **57** changed/new Python files.
- Targeted ESLint: passed on all **75** changed/new TS/TSX files.
- Fresh database upgrade from zero, empty-domain downgrade to `20261011_0023`, and re-upgrade: passed; one Alembic head. A focused test also verifies downgrade refusal preserves teacher-origin content after its owner's role changes.
- Working/index diff whitespace checks passed before commits. The final remote SHA and clean Git status are verified after push and reported to the user.

No browser, Playwright/E2E, dev server, build, live model/GPU, Modal or deployment was run. Test content is fictional and no new dependency was added. The final independent review reported no remaining Critical or Important findings after the two fixes.
