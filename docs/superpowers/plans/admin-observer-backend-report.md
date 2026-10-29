# Backend Admin Observer Report — 2026-10-27

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Backend Admin Observer Report — 2026-10-27. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [current module/guide](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Root causes

- `resolve_capabilities()` subtracted a handful of mutable capabilities from `ALL`, leaving administrators with classroom management, member management and final-grade editing.
- `ClassroomAssignmentService.create()` explicitly skipped assignment authorization for administrators.
- `AccessPolicy.require_classroom_manage()` returned early for administrators.
- `ClassroomService.restore()` required global Admin moderation instead of classroom ownership.
- `GradingPolicy` granted administrators classroom final-grade flags and accepted classroom final grading through personal Writing/Speaking endpoints.
- Participant operations could trust historical membership or attempt ownership. A legacy Admin enrolment could therefore comment, leave/respond to invitations, complete resource plan items, start assignments, or mutate old classroom attempts independently of authoring capabilities.

## Implementation

- Added `roster.view`, with an explicit Admin observer allowlist of `roster.view`, `grades.view`, `analytics.view`. Admin global role takes precedence over historical ownership/staff rows.
- Roster listing requires `roster.view`; invitations and membership management still require `members.manage`. Owner and co-teacher receive roster access. Existing TA base and optional permissions are preserved; TA receives no new member-management permission.
- Classroom mutation actor locks reload the account then reject Admin with `CLASSROOM_OBSERVER_READ_ONLY` (HTTP 403). This boundary covers settings, classroom lifecycle, memberships/invitation responses, staff operations, content/resources, topics/order, posts/comments, schedules/extensions, grade-selection policy and learning plans.
- Classroom creation keeps its existing teacher-only check. Automatic invitation binding inside authentication explicitly retains its prior path; this does not accept an invitation or create membership.
- Removed assignment-creation and classroom-management Admin bypasses. Existing assignment archive/restore/delete capability checks and protected-history checks remain intact.
- Restoring a classroom now requires `classroom.manage`, meaning an active owner teacher; co-teachers and Admin cannot restore it. Existing active-owner validation and lifecycle locks remain.
- Classroom final grading denies Admin before writing, including personal routes and Full Mock parent assignment provenance. Admin classroom grading flags are always false, even when `assignment_authorized=True` is supplied. Separate personal-attempt platform grading authority remains intact.
- Added a classroom-attempt mutation guard for old Admin enrolments. It detects direct or parent-session assignment provenance and reloads the acting account. Applied to locked Attempt and Full Mock lifecycle operations, Speaking runtime/media/recovery, standalone history removal, Writing AI creation/cancellation/adoption and Speaking transcript/AI mutation authorization. Ordinary personal practice and student/teacher workflows continue through their existing policies.
- Review follow-up: Writing AI list/get/snapshot may recover a stale run while reading. Recovery now checks classroom provenance before persisting failure state/events; Admin classroom observation returns the stored run without mutation. Ordinary student classroom recovery and personal recovery remain enabled.
- Active classroom member counts now join account roles and exclude legacy Admin membership rows. Ordinary teacher accounts enrolled as students remain included.
- Speaking AI/transcript stale-source reads already construct failure DTOs without changing persisted run state; focused tests now verify both paths.

## Mutation audit

| Domain | Enforcement |
| --- | --- |
| Classroom create | Teacher-only role gate |
| Settings/archive/restore | Reloaded classroom mutation actor gate; owner checks / `classroom.manage` |
| Member invite/cancel/remove/leave/accept/decline | Shared mutation gate; existing capability/recipient checks |
| Staff invite/change/revoke/respond | Shared classroom mutation actor gate; existing staff capability/eligibility rules |
| Topics/resources/files/placement/reorder/removal | `ContentAccess` shared mutation gate; existing content/assignment capability rules |
| Announcements/discussions/publish/archive/pin/delete | Shared content mutation gate |
| Comment create/edit/delete/moderation | Shared mutation gate and explicit participant check |
| Assignment create/archive/restore/delete | Explicit assignment capability check; existing history safeguards |
| Assignment schedule/individual extension | Shared mutation gate and assignment/extension capability |
| Gradebook selection policy | Shared mutation gate and assignment capability |
| Writing/Speaking final scores, personal and scoped routes | Provenance-aware `GradingPolicy`; Admin denied |
| Learning-plan create/update/resource completion | Shared mutation gate and existing plan/student rules |
| Assignment start, module and Full Mock | Fresh actor participant gate inside lifecycle transaction |
| Existing legacy Admin attempts | Provenance guard on locked mutation loading; ordinary read-only review routes remain available |
| AI grading/transcription creation, cancellation and practice adoption | Provenance guard at mutating attempt authorization |
| Global account administration/test moderation | Unchanged; no classroom permission inherited from these policies |

## Files changed by backend authorization worker

Production services:

- `backend/app/services/classroom_capabilities.py`
- `backend/app/services/access_policy.py`
- `backend/app/services/classrooms.py`
- `backend/app/services/classroom_content_access.py`
- `backend/app/services/classroom_assignments.py`
- `backend/app/services/grading_policy.py`
- `backend/app/services/attempts.py`
- `backend/app/services/test_sessions.py`
- `backend/app/services/speaking_attempts.py`
- `backend/app/services/speaking_transcript.py`
- `backend/app/services/writing_ai.py`
- `backend/app/services/writing_ai_practice_feedback.py`

Tests:

- New `backend/tests/test_classroom_admin_observer_unit.py`
- New `backend/tests/test_classroom_admin_observer_rest.py`
- New `backend/tests/test_classroom_observer_ai_reads.py`
- Updated obsolete Admin error-code expectation in `backend/tests/test_classroom_classwork_unit.py`
- Updated owner restoration / Admin denial expectations in `backend/tests/test_classrooms_and_notifications.py`
- Updated obsolete personal-route Admin classroom final-grading expectation in `backend/tests/test_subjective_grading.py`
- Extended the database double in `backend/tests/test_writing_ai_observer_lifecycle.py` with owner-scoped personal attempt loading, matching the new provenance authorization dependency; its real worker/SSE/cancellation behavior remains exercised.

The Admin directory API/schema/repository work belongs to the root worker and is outside this change ownership.

## Verification evidence

The required `backend/tests/conftest.py` was inspected first. It reads the configured `DATABASE_URL` and performs schema work inside a rollback-only transaction. No `TEST_DATABASE_URL` is configured in this session, so no PostgreSQL integration fixture was executed and no database was reset, migrated, or touched.

Red-phase evidence:

- Initial new authorization unit file: 12 failed, 2 passed, exposing mutable Admin capabilities, owner-policy bypass, comments with old membership, participant mutation entry, personal final-grade provenance, assignment start and owner restoration.
- Added assignment-creation bypass test: failed because creation did not raise authorization error.
- Added legacy attempt engine tests: 3 failed because Attempt, Full Mock and Speaking loaders permitted Admin classroom writes.
- Added legacy AI creation/adoption tests: 3 failed because the requests reached lifecycle/scope validation instead of returning authorization denials.
- Read-side recovery review regressions: 6 Admin classroom list/get/snapshot cases failed because reads rewrote stale runs; 9 ordinary student/personal cases already passed. Active-member SQL regression failed because the query counted memberships without excluding Admin accounts.

Final focused command from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_classroom_observer_ai_reads.py tests/test_classroom_admin_observer_unit.py tests/test_classroom_admin_observer_rest.py tests/test_classroom_classwork_unit.py tests/test_classroom_archive_unit.py tests/test_writing_ai_observer_lifecycle.py -q
```

Result after review follow-up: **167 passed in 12.87s**.

The new REST matrix exercises 51 handcrafted requests through real FastAPI routers and services with database-boundary doubles. It covers settings/lifecycle, membership and staff operations, assignments, protected archive actions, topics/resources/order, announcements/comments, schedules/extensions, grade policy, learning plans and both personal/scoped Writing/Speaking final-score endpoints. Every request returned 403, existing ORM row snapshots remained unchanged, and no add/flush/delete/execute operation occurred.

The unit cases cover Admin override precedence, permitted oversight flags, roster separation, teacher owner restore, co-teacher capabilities, TA optional capabilities, student/unrelated-teacher isolation, direct/parent grading provenance, legacy attempt mutations and preservation of separate personal platform grading authority.

The 17 read-side AI cases cover Admin direct/parent assignment origins, student classroom recovery, personal Admin/student recovery across list/get/snapshot, and Speaking AI/transcript stale-source DTO isolation. Existing Writing AI worker/SSE/recovery/cancellation lifecycle tests also pass.

Scoped Ruff was run against all 19 owned Python files: **All checks passed**. Scoped `git diff --check` passed with only Git line-ending notices. No browser, server, production build, persistent process, full suite or PostgreSQL integration run was performed.

## Remaining verification limits

- The REST no-write assertions use controlled database-boundary doubles; actual PostgreSQL rollback/row-count and concurrency coverage remains unexecuted because no explicitly isolated test database was available.
- The two updated existing PostgreSQL integration test files were not executed.
- The broad attempt guard adds a fresh account read for classroom attempt mutations and a parent-origin lookup for Full Mock attempts. Stale Writing AI recovery additionally reloads its attempt before any state write. Query-count/concurrency integration checks were not run.
- A final audit found Writing AI run cancellation could still trust legacy ownership. A separate regression failed before the same provenance guard was added; cancellation now denies Admin classroom requests as well.
- No commit or push was performed by this worker.
