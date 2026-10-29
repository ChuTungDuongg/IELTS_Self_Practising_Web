# Teacher, Classroom, Content Governance & Notification Design

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Teacher, Classroom, Content Governance & Notification Design. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [current module/guide](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Status

Approved conversational design captured for implementation planning. Detailed frontend layout is intentionally deferred; this spec fixes product semantics, authorization boundaries, persistence rules, workflows, and the minimum coherent UI behavior required for v1.

## Goal

Extend the IELTS platform from USER/ADMIN into a three-role system with TEACHER accounts, teacher-owned tests, classroom membership and assignments, moderated classroom/public publication, per-user notifications, and teacher read-only visibility into assignment-originated student submissions.

The feature must preserve existing official/manual grading semantics, attempts/history, current USER behavior outside classrooms, and existing test-version references.

## Product decisions

- Roles: `USER`, `TEACHER`, `ADMIN`.
- Public registration always creates `USER`; only ADMIN may promote `USER -> TEACHER`.
- `TEACHER` keeps normal USER capabilities and gains teacher capabilities; it is not a separate account model.
- ADMIN may demote `TEACHER -> USER` only after active teacher resources and pending moderation are resolved. ADMIN may archive/disable resources first.
- Teacher-created tests remain teacher-owned after approval/public contribution.
- ADMIN-created published tests are official/global. Teacher-created PUBLIC-approved tests are community/contributed content with teacher attribution.
- Every teacher-created version must be ADMIN-reviewed before another user can use it, even for classroom-only use.
- Moderation is by content version, not by classroom.
- `CLASSROOM` and `PUBLIC` are distinct moderation scopes. PUBLIC approval implies classroom eligibility; CLASSROOM approval does not imply public visibility.
- Published/approved teacher versions are immutable. Editing requires a new draft/version and fresh moderation.
- Each classroom has exactly one teacher owner in v1; no co-teachers or ownership transfer.
- Teacher invites by email; invites may exist before the email has an account.
- V1 uses in-app notifications only; no email delivery.
- Students explicitly Accept or Decline invitations; no auto-join.
- `ClassroomAssignment` is the class-sharing and attempt-provenance object.
- Students may retry assignments; no one-attempt DB limit in v1.
- Teachers may inspect full assignment-originated submissions read-only, but never unrelated personal practice.
- Archived classrooms/resources preserve academic history read-only and disable future activity rather than deleting data.
- Notifications are generic platform resources and never authorization tokens.

## Current architecture constraints

The repository currently has USER/ADMIN roles; test creation/edit/publish is largely ADMIN-only. `Test` has no creator/owner. `TestVersion` uses `DRAFT`, `PUBLISHED`, `ARCHIVED`, with DB constraints for one draft and one published version per test.

This design keeps that content lifecycle and adds ownership, moderation, classroom access, and provenance around it. Moderation state must not be encoded into `VersionStatus`.

## 1. Roles, ownership, and policy

### 1.1 Capabilities

`USER` may use official/global tests, accept classroom invitations, use classroom assignments, manage own attempts/history, and receive notifications.

`TEACHER` additionally may create tests/drafts, edit only owned mutable content, submit owned versions for moderation, create/manage owned classrooms, invite/remove students, create assignments, and inspect assignment-originated results read-only.

`ADMIN` retains existing administrative behavior and additionally manages teacher roles, moderation, global classroom/resource archive/restore, and administrative overrides without silently transferring ownership.

### 1.2 Test ownership

Extend `Test` conceptually:

```text
owner_user_id: UUID | null
origin: ADMIN | TEACHER
```

Rules:
- new ADMIN test: `origin=ADMIN`, `owner_user_id=admin.id`;
- new TEACHER test: `origin=TEACHER`, `owner_user_id=teacher.id`;
- legacy pre-migration official tests may use `origin=ADMIN`, `owner_user_id=NULL`; never invent a historical creator;
- every new post-migration test must have an owner;
- approval/publication never changes owner/origin.

### 1.3 Policy layer

Do not replace `AdminUser` with unrestricted `CurrentUser` and scatter role checks. Introduce focused backend policy/service checks equivalent to:

```text
can_create_test(user)
can_edit_test(user, test, version)
can_manage_classroom(user, classroom)
can_assign_version(user, classroom, version)
can_read_version(user, version, context)
can_view_assignment_attempt(user, assignment, attempt)
can_submit_moderation(user, version, scope)
can_moderate(user)
```

Frontend visibility is UX only; backend authorization is authoritative.

### 1.4 Demotion

`TEACHER -> USER` must conflict while teacher-only active resources remain, including active classrooms, pending moderation, or resources policy requires ADMIN to archive/disable first.

Already approved public historical content may remain public with attribution after demotion once other teacher resources are validly resolved. Role changes never cascade-delete academic history.

## 2. Content lifecycle and moderation

### 2.1 VersionStatus remains content lifecycle

Keep:

```text
DRAFT
PUBLISHED
ARCHIVED
```

`PUBLISHED` means immutable active content usable according to ownership/moderation/access rules; it does not inherently mean global visibility.

ADMIN-created published official versions remain globally visible according to existing official behavior.

### 2.2 One active published version per test

Preserve the existing invariant of at most one `PUBLISHED` version per `Test`.

When a newer teacher draft is approved for either CLASSROOM or PUBLIC:
- the newer version becomes the active `PUBLISHED` version;
- the previous active `PUBLISHED` version becomes `ARCHIVED` in the same transaction;
- old attempts/history continue referencing the archived version unchanged.

Because moderation is version-scoped, visibility/access follows the newly active version's approvals. Example: if v1 was PUBLIC-approved and v2 is approved only for CLASSROOM, v1 is archived and the test stops being globally visible until v2 itself receives PUBLIC approval. This explicit replacement behavior is intentional and avoids multiple simultaneously active published versions.

### 2.3 Moderation records

Add a separate audit entity:

```text
TestVersionModeration
- id
- test_version_id
- scope: CLASSROOM | PUBLIC
- status: PENDING | APPROVED | REJECTED | REVOKED
- submitted_by_user_id
- reviewed_by_user_id nullable
- submit_note nullable
- review_note nullable
- submitted_at
- reviewed_at nullable
- revoked_at nullable
- revoked_by_user_id nullable
- revoke_reason nullable
```

Each submission creates a new row; do not overwrite historical requests.

Rules:
- at most one `PENDING` request per `(test_version_id, scope)`;
- any pending moderation locks the version content;
- owner teacher may cancel own PENDING request; if no other pending request remains, a draft becomes editable again;
- approve/reject/revoke are concurrency-safe and valid only from allowed prior states.

### 2.4 Scope semantics

`CLASSROOM APPROVED`:
- version is/continues active `PUBLISHED` and immutable;
- eligible for classroom assignments;
- not visible in the global Community Library.

`PUBLIC APPROVED`:
- version is/continues active `PUBLISHED` and immutable;
- visible system-wide as community/contributed content;
- also eligible for classroom assignments.

A teacher may submit directly for PUBLIC without prior classroom approval, or may later submit the same CLASSROOM-approved version for PUBLIC review.

### 2.5 Revocation

PUBLIC revocation removes future global/community visibility but preserves attempts/history. Classroom eligibility may remain if CLASSROOM approval is still active.

CLASSROOM revocation prevents future classroom assignment/start paths that depend only on CLASSROOM approval; if PUBLIC approval remains active, classroom eligibility remains through PUBLIC approval.

Moderation changes future access, never academic history.

## 3. Classroom domain

### 3.1 Classroom

```text
Classroom
- id
- teacher_id
- name
- description nullable
- status: ACTIVE | ARCHIVED
- archived_at nullable
- created_at
- updated_at
```

Rules:
- exactly one active TEACHER owner;
- no hard delete in v1;
- owner teacher may archive own classroom;
- ADMIN may archive/restore any classroom;
- archived classroom is historical/read-only: no new invitations, memberships, assignments, or assignment starts; existing history remains readable under normal permissions.

### 3.2 Invitation

```text
ClassroomInvitation
- id
- classroom_id
- invited_email
- invited_email_normalized
- invited_user_id nullable
- invited_by_user_id
- status: PENDING | ACCEPTED | DECLINED | CANCELLED
- created_at
- responded_at nullable
- cancelled_at nullable
```

Rules:
- normalize email exactly as auth/user lookup does;
- no duplicate pending invite for the same classroom/email;
- no invite for an already-active member;
- prevent inviting the classroom owner into their own classroom;
- if account exists, bind `invited_user_id` and create in-app notification;
- if account does not exist, persist by normalized email only;
- on matching registration/login, bind pending invitations and create missing notification idempotently;
- never auto-accept or auto-join.

Accept is transactional: lock invitation, validate PENDING, recipient/email, ACTIVE classroom and no active membership; create membership; mark ACCEPTED; notify teacher; commit once.

### 3.3 Membership

```text
ClassroomMembership
- id
- classroom_id
- user_id
- joined_at
- left_at nullable
- removed_by_user_id nullable
```

`left_at IS NULL` means active. Never delete membership history. At most one active membership per classroom/user. A later rejoin creates a new membership period. Student may leave voluntarily; teacher may remove; neither action deletes old assignment submissions.

A TEACHER remains a normal user and may be a student/member in another teacher's classroom.

## 4. Assignment and attempt provenance

### 4.1 ClassroomAssignment

```text
ClassroomAssignment
- id
- classroom_id
- test_version_id
- created_by_user_id
- title nullable
- note nullable
- status: ACTIVE | ARCHIVED
- created_at
- archived_at nullable
```

Teacher can assign when:
- classroom ACTIVE and owned by current teacher;
- version is active `PUBLISHED`/immutable;
- either the version is teacher-owned with active CLASSROOM or PUBLIC approval, or it is an official ADMIN/system published version;
- ADMIN/system official tests may therefore be assigned without teacher moderation because they are already official content.

No additional moderation is required per classroom.

### 4.2 Provenance

Assignment-started activity must carry durable assignment provenance created only by backend assignment-start logic.

Standalone/module attempts should reference the originating assignment where applicable. For Full Mock, provenance may live on `TestSession` and be inherited by child attempts, or be duplicated only if existing query patterns require it. Implementation planning must choose the least duplicated model that preserves an unambiguous security predicate.

A browser must not attach an arbitrary existing attempt to a classroom after creation.

### 4.3 Retry

Multiple attempts/sessions per student per assignment are allowed. Keep the full history; summaries may highlight latest/current attempt.

### 4.4 Teacher visibility boundary

Teacher may read an attempt only when it originated from an assignment owned by that teacher's classroom:

```text
attempt originates from assignment
AND assignment.classroom.teacher_id == current_teacher.id
```

Never authorize from `student_id + test_version_id` alone. Personal practice on the same test remains private. Historical assignment-originated submissions remain teacher-readable after membership ends.

## 5. Teacher result view

Read-only access may include:
- status/timestamps;
- Listening/Reading submitted answers, correctness, score/band;
- Writing submission text;
- existing Writing AI result/feedback attached to that attempt where the normal data contract permits;
- existing official/manual Writing score if already present.

Teacher may not edit answers, delete attempts, mutate official/manual scores, invoke ADMIN-only grading mutations, or inspect unrelated personal practice. Frontend clearly labels teacher attempt review as read-only.

## 6. Notification subsystem

Use a generic per-user notification model with localizable event data:

```text
Notification
- id
- user_id
- type
- payload_json
- entity_type
- entity_id
- read_at nullable
- created_at
```

`type + payload_json` is the durable event contract; frontend EN/VI localization renders title/message. Payload should contain only safe display metadata required for rendering (for example classroom/test display names), not authorization state or secrets.

Initial types may include:
- `CLASSROOM_INVITED`;
- `CLASSROOM_INVITATION_ACCEPTED`;
- `CLASSROOM_INVITATION_DECLINED`;
- `TEST_CLASSROOM_APPROVED`;
- `TEST_CLASSROOM_REJECTED`;
- `TEST_PUBLIC_APPROVED`;
- `TEST_PUBLIC_REJECTED`;
- `CLASSROOM_ARCHIVED`.

Rules:
- `read_at IS NULL` means unread;
- header shows unread count;
- opening the panel does not mark everything read;
- support mark-one and mark-all-read;
- actions always load and authorize the real target entity;
- notification/entity IDs never grant permission;
- invitation-notification creation on registration/login is idempotent;
- no generic WebSocket/SSE requirement in v1; fetch/refetch is sufficient;
- no email delivery in v1.

## 7. API/workflow shape

Exact route naming follows current conventions, but required resource actions are:

### 7.1 Tests

Reuse existing Builder/test routes.

`POST /tests`:
- ADMIN => official owned test;
- TEACHER => teacher owned test;
- USER => forbidden.

Existing mutate/create-version/delete/validate flows become policy-based where appropriate. Teacher mutations are owner-scoped and mutable-version-scoped; ADMIN retains global administrative control.

### 7.2 Moderation

Teacher:

```text
POST /test-versions/{version_id}/moderation-requests
POST /test-moderation-requests/{request_id}/cancel
```

ADMIN:

```text
GET  /admin/test-moderation-requests
GET  /admin/test-moderation-requests/{id}
POST /admin/test-moderation-requests/{id}/approve
POST /admin/test-moderation-requests/{id}/reject
POST /admin/test-moderation-requests/{id}/revoke  (or equivalent scoped revocation action)
```

Approval transaction validates PENDING state and the locked target version, applies active-version replacement when first publishing a newer version, records moderation result, creates notification, and commits atomically.

### 7.3 Classrooms/memberships

```text
GET  /classrooms
POST /classrooms
GET  /classrooms/{id}
PATCH /classrooms/{id}
POST /classrooms/{id}/archive
GET  /classrooms/{id}/members
POST /classrooms/{id}/members/{user_id}/remove
POST /classrooms/{id}/leave
```

ADMIN has global archive/restore capability.

### 7.4 Invitations

```text
POST /classrooms/{id}/invitations
POST /classroom-invitations/{id}/cancel
GET  /me/classroom-invitations
POST /classroom-invitations/{id}/accept
POST /classroom-invitations/{id}/decline
```

### 7.5 Assignments/results

```text
GET  /classrooms/{id}/assignments
POST /classrooms/{id}/assignments
GET  /classrooms/{id}/assignments/{assignment_id}
POST /classrooms/{id}/assignments/{assignment_id}/archive
GET  /me/classrooms/{id}/assignments
POST /classroom-assignments/{assignment_id}/start
GET  /classrooms/{classroom_id}/assignments/{assignment_id}/results
GET  /classrooms/{classroom_id}/assignments/{assignment_id}/students/{student_id}/attempts
```

Assignment start derives classroom, test version, current user, membership, and provenance from server-side assignment state. Do not trust browser-supplied ownership/access IDs when derivable.

### 7.6 Notifications

```text
GET  /notifications
GET  /notifications/unread-count
POST /notifications/{id}/read
POST /notifications/read-all
```

## 8. Concurrency and transactions

These operations must be transaction-safe and duplicate/conflict-safe:
- invitation acceptance and active membership creation;
- moderation submit/approve/reject/revoke;
- active published-version replacement;
- assignment creation;
- assignment start/provenance creation;
- teacher promotion/demotion validation;
- classroom archive/restore;
- idempotent notification creation for pending invites.

Double-click/concurrent requests must not create duplicate memberships, duplicate pending moderation, duplicate publication transitions, or duplicate notifications.

## 9. Domain errors

Use explicit domain semantics, with names adapted to existing conventions, including equivalents of:

```text
TEACHER_REQUIRED
TEST_OWNERSHIP_REQUIRED
VERSION_IMMUTABLE
MODERATION_ALREADY_PENDING
VERSION_NOT_CLASSROOM_APPROVED
VERSION_NOT_PUBLIC_APPROVED
CLASSROOM_NOT_FOUND
CLASSROOM_ARCHIVED
CLASSROOM_OWNERSHIP_REQUIRED
INVITATION_NOT_FOUND
INVITATION_ALREADY_RESOLVED
INVITATION_EMAIL_MISMATCH
ASSIGNMENT_NOT_ACCESSIBLE
ACTIVE_MEMBERSHIP_REQUIRED
TEACHER_HAS_ACTIVE_RESOURCES
```

## 10. Minimum frontend behavior; detailed layout deferred

Implementation must provide coherent surfaces for:
- ADMIN promote/demote teacher with conflict feedback;
- TEACHER using the existing Builder for owned tests and seeing ownership/moderation state;
- TEACHER classroom/member/invitation/assignment management and read-only results;
- ADMIN moderation queue/detail/actions;
- USER invitation Accept/Decline, classroom/assignment views, and assignment start;
- Test Library distinction between official ADMIN/system content and public community teacher content;
- global notification bell with unread count/list/read actions;
- archived resources rendered as historical read-only rather than deleted;
- all new visible chrome in current EN/VI localization.

Detailed dashboard layout, visual hierarchy, realtime notifications, deadlines, attempt limits, co-teachers, email delivery, teacher grading, and organization tenancy are outside v1.

## 11. Compatibility and migration

- Preserve current USER flows and official ADMIN/system tests.
- Preserve all existing attempt/session/history references and IDs.
- Legacy tests without creators migrate safely as `origin=ADMIN`, system-owned (`owner_user_id=NULL`); do not invent ownership.
- Existing published version references remain valid even when the version later becomes ARCHIVED after a newer approval.
- Do not rewrite historical attempts or official/manual Writing scores.
- Preserve Builder/import/export/assets/versioning except where ownership/access metadata is required.
- Review draft import/ZIP import paths so newly imported tests receive owner/origin from the authenticated importer and do not silently become unowned.
- PostgreSQL enum migration for `UserRole.TEACHER` must be safe for existing data.

## 12. Security invariants

1. USER cannot self-promote to TEACHER.
2. TEACHER cannot edit another teacher's content.
3. TEACHER cannot mutate approved/published versions.
4. Teacher content is unusable by other users until an appropriate ADMIN approval exists.
5. CLASSROOM approval never grants global visibility.
6. PUBLIC approval grants community visibility and classroom eligibility.
7. Teacher cannot read student personal practice outside assignment provenance.
8. Notification presence never grants authorization.
9. Archived/revoked resources stop future actions while preserving academic history.
10. Backend policy, not frontend visibility, is authoritative.

## 13. Explicit non-goals

- Email invitation delivery.
- Co-teachers/multiple classroom owners.
- Classroom ownership transfer.
- Assignment deadlines.
- Attempt-count limits.
- Teacher manual grading/editing of official Writing scores.
- Generic realtime WebSocket/SSE notifications.
- Organization/school tenants.
- Paid courses/subscriptions.
- Full classroom analytics beyond assignment status/result views.

## 14. Acceptance path

```text
ADMIN promotes USER -> TEACHER
TEACHER creates test + draft
TEACHER submits CLASSROOM moderation
ADMIN approves
new version becomes active PUBLISHED/immutable and classroom-eligible
TEACHER creates classroom
TEACHER invites email
USER logs in and receives in-app invitation
USER accepts -> membership
TEACHER creates assignment from approved teacher version or official ADMIN version
USER starts through assignment
attempt/session stores assignment provenance
TEACHER sees full assignment result read-only
same teacher version may later be submitted for PUBLIC moderation
ADMIN approves PUBLIC
version appears globally as community content with teacher attribution
```

All historical academic data remains stable if membership, classroom, approval, publication, or teacher role state changes later.