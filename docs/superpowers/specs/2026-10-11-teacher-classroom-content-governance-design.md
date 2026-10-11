# Teacher, Classroom, Content Governance & Notification Design

## Status

Approved conversational design captured for implementation planning. Frontend visual polish and detailed information architecture are intentionally deferred; this spec fixes the backend/product semantics, security boundaries, and minimum UI behavior required for implementation.

## Goal

Extend the IELTS platform from USER/ADMIN into a three-role system with TEACHER accounts, teacher-owned tests, classroom membership and assignments, moderated classroom/public publication, per-user notifications, and teacher read-only visibility into assignment-originated student submissions.

The feature must preserve existing test versioning, attempts/history, official/manual grading semantics, and current USER behavior outside classrooms.

## Product decisions

- Roles become `USER`, `TEACHER`, `ADMIN`.
- Public registration always creates `USER`; only ADMIN can promote `USER -> TEACHER`.
- `TEACHER` retains normal USER capabilities and gains teacher capabilities; it is not a separate account model.
- ADMIN may demote `TEACHER -> USER` only after active teacher resources/pending moderation are resolved. ADMIN can archive/disable classroom/resources first.
- Teacher-created tests remain owned by the teacher even after system-wide contribution approval.
- ADMIN-created tests are official/global content. Teacher-created public-approved tests are community/contributed content and retain teacher attribution.
- Every teacher-created version must be ADMIN-reviewed before other users can use it, including classroom-only use.
- Moderation is by content version, not by classroom. Once a version is approved for classroom use, the teacher can assign the same version to any owned classroom without another review.
- `CLASSROOM` approval and `PUBLIC` approval are distinct moderation scopes. Public approval is stricter and requires a separate request unless the request itself is directly for PUBLIC.
- `PUBLIC` approval implies classroom eligibility. `CLASSROOM` approval does not imply public eligibility.
- Published/approved teacher versions are immutable. Editing requires a new draft/version and fresh moderation.
- Each classroom has exactly one teacher owner in v1. No co-teacher or ownership-transfer workflow.
- Teacher invites students by email. Invitations can exist before the email has an account.
- V1 is in-app notifications only; no external email delivery.
- Students must explicitly Accept or Decline classroom invitations. No auto-join.
- Classroom sharing uses `ClassroomAssignment`; the assignment is the access/provenance object for class work.
- Students may retry assignments; no DB-level one-attempt limit in v1.
- Teachers can inspect full assignment-originated submissions read-only. They cannot inspect unrelated personal practice even if the student used the same test version.
- Teacher review is read-only in v1; teachers cannot mutate student answers, official/manual Writing scores, or attempts.
- Archived classrooms/resources preserve historical academic data read-only. Archive disables future activity instead of deleting history.
- Notifications are a generic platform subsystem and never act as authorization tokens.

## Current architecture constraints

The current repository has `UserRole.USER` and `UserRole.ADMIN`; test creation/edit/publish routes are largely ADMIN-only. `Test` currently has no creator/owner field. `TestVersion` already supports `DRAFT`, `PUBLISHED`, and `ARCHIVED`, with database constraints for one draft and one published version per test.

This design keeps the existing content lifecycle and adds ownership/access/moderation around it instead of overloading `VersionStatus` with teacher-review states.

## 1. Roles, ownership, and policy model

### 1.1 Role capabilities

`USER`:
- use official/global tests;
- use classroom assignments for classrooms where they are an active member;
- manage their own attempts/history;
- receive notifications and classroom invitations.

`TEACHER`:
- all USER behavior;
- create tests and drafts;
- edit only teacher-owned mutable content;
- submit owned versions for classroom/public moderation;
- create/manage owned classrooms;
- invite/remove students;
- create assignments from eligible approved versions;
- inspect assignment-originated student attempts/submissions read-only.

`ADMIN`:
- existing administrative behavior;
- promote/demote teacher roles;
- global content/classroom moderation and archive/restore controls;
- review/approve/reject/revoke teacher moderation requests;
- administrative override of teacher-owned resources without silently transferring ownership.

### 1.2 Test ownership

Extend `Test` conceptually with:

```text
owner_user_id: UUID | null
origin: ADMIN | TEACHER
```

Rules:
- ADMIN-created new test: `origin=ADMIN`, `owner_user_id=admin.id`.
- TEACHER-created test: `origin=TEACHER`, `owner_user_id=teacher.id`.
- Legacy pre-migration official tests may use `origin=ADMIN`, `owner_user_id=NULL` to represent system-owned historical content; do not guess a historical creator.
- New tests after migration must have an owner.
- Public approval never changes `owner_user_id` or `origin`.

### 1.3 Policy layer

Do not scatter role-only checks through routes. Introduce focused authorization/policy logic equivalent to:

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

Frontend button visibility is UX only; backend policy is authoritative.

### 1.4 Teacher demotion

`TEACHER -> USER` must fail with a domain conflict while teacher-only active resources remain, including at least:
- active classrooms;
- pending moderation requests;
- teacher-owned resources that policy requires ADMIN to archive/disable first.

Already public-approved historical content may remain public with attribution after demotion if ADMIN has put the rest of the teacher resources into a valid state.

No role change cascade-deletes academic history.

## 2. Content lifecycle and moderation

### 2.1 Keep VersionStatus focused on content lifecycle

Keep:

```text
DRAFT
PUBLISHED
ARCHIVED
```

Do not add `PENDING_CLASSROOM_REVIEW`, `PUBLIC_APPROVED`, etc. to `VersionStatus`.

`PUBLISHED` means the version is immutable and usable according to its ownership/moderation/access rules. It does not universally mean system-wide visibility.

ADMIN-created published official versions remain globally visible according to existing official behavior.

### 2.2 Moderation records

Add a separate moderation entity conceptually:

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

Each submission is a new audit row. Do not overwrite rejected/approved historical rows.

Database/policy rules:
- at most one `PENDING` request per `(test_version_id, scope)`;
- version with any pending moderation request is content-locked;
- teacher may cancel their own pending request, which unlocks the draft if no other pending request remains;
- approval/rejection must be concurrency-safe and only operate from `PENDING`.

### 2.3 Scope semantics

`CLASSROOM APPROVED`:
- version becomes/continues `PUBLISHED` and immutable;
- eligible for classroom assignment by its owner teacher;
- not global community content.

`PUBLIC APPROVED`:
- version becomes/continues `PUBLISHED` and immutable;
- visible system-wide as community/contributed content;
- also eligible for classroom assignment.

`PUBLIC APPROVED` implies classroom eligibility; `CLASSROOM APPROVED` does not imply public visibility.

A version may be classroom-approved and later have an independent public request.

### 2.4 Revocation

ADMIN may revoke an existing approval.

PUBLIC revocation:
- removes future global/community-library visibility;
- does not delete existing attempts/history;
- classroom eligibility may remain when an active CLASSROOM approval still exists.

CLASSROOM revocation:
- prevents new assignments and new starts that depend only on that classroom approval;
- does not delete completed/in-progress historical academic data;
- if PUBLIC approval remains active, classroom eligibility still exists via PUBLIC approval.

Moderation changes future accessibility; it never deletes academic history.

## 3. Classroom domain model

### 3.1 Classroom

Conceptual model:

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
- exactly one teacher owner;
- owner must be an active TEACHER when creating/managing an active classroom;
- no hard-delete workflow in v1;
- teacher may archive their own classroom;
- ADMIN may archive/restore any classroom;
- archived classroom is historical/read-only.

Archived means:
- no new invitations;
- no new assignments;
- no new assignment starts;
- no teacher membership changes;
- existing members/teacher can still inspect history according to permissions;
- existing submissions/history remain intact.

### 3.2 Invitations

Conceptual model:

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
- normalize email consistently with auth/user lookup;
- prevent duplicate pending invitations for the same classroom/email;
- prevent invite when already an active member;
- if account exists, bind `invited_user_id` and create an in-app invitation notification;
- if account does not exist, persist invitation by normalized email only;
- when a matching account later registers/logs in, bind pending invitations idempotently and create missing in-app notifications;
- never auto-join;
- Accept/Decline must validate the authenticated user's identity/email against the invitation.

Acceptance is transactional:
- lock/validate pending invitation;
- validate classroom ACTIVE;
- validate recipient;
- create active membership;
- mark invitation ACCEPTED;
- create teacher notification;
- commit once.

### 3.3 Membership

Conceptual model:

```text
ClassroomMembership
- id
- classroom_id
- user_id
- joined_at
- left_at nullable
- removed_by_user_id nullable
```

`left_at IS NULL` is an active membership.

Do not delete membership rows when a student leaves/is removed. Historical periods must remain auditable. A later rejoin creates a new membership period rather than resurrecting the old row.

At most one active membership exists per `(classroom_id, user_id)`.

Students may voluntarily leave. Leaving/removal does not delete assignment submissions/history.

## 4. Assignment and attempt provenance

### 4.1 ClassroomAssignment

An assignment is both the teacher's sharing action and the provenance boundary for teacher-visible work.

Conceptual model:

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

Teacher can create an assignment only when:
- classroom is ACTIVE;
- teacher owns the classroom;
- version is PUBLISHED/immutable;
- version has an active CLASSROOM approval or active PUBLIC approval;
- teacher has authority to assign that version (normally own teacher content, plus official/global content if product policy permits).

No extra moderation per classroom after version approval.

### 4.2 Attempt provenance

Assignment-started activity must carry durable assignment provenance.

For standalone/module attempts, `Attempt` should reference the originating classroom assignment where applicable.

For Full Mock, provenance may live on `TestSession` and be inherited by child attempts, or be duplicated only if existing query patterns justify it. Implementation planning must choose the least duplicated design while preserving an unambiguous security predicate.

The backend, not the browser, owns provenance creation when the student starts through the assignment route. An arbitrary existing attempt cannot be attached to a classroom later by sending an assignment ID.

### 4.3 Retry behavior

V1 allows multiple starts/attempts per student per assignment. No one-attempt unique constraint.

Teacher result summaries may display latest completed/current status while preserving the full attempt list.

### 4.4 Teacher visibility boundary

Teacher may view a student attempt only when it originated from a `ClassroomAssignment` owned by that teacher's classroom.

Equivalent security rule:

```text
attempt originates from assignment
AND assignment.classroom.teacher_id == current_teacher.id
```

Do not authorize by `student_id + test_version_id` alone.

If a student separately practices the same test outside the assignment, that attempt remains private from the teacher.

Historical assignment submissions remain visible to the teacher even after the student's membership ends, because provenance is the assignment relationship, not current membership.

## 5. Teacher result view

Teacher classroom result access is read-only.

Teacher may inspect assignment-originated:
- attempt/session status and timestamps;
- Listening answers, correctness, score/band;
- Reading answers, correctness, score/band;
- Writing submission text;
- existing Writing AI feedback/result associated with that attempt where the normal data contract permits;
- existing official/manual Writing score if already present.

Teacher may not:
- edit student answers;
- delete attempts;
- change official/manual scores;
- run ADMIN-only grading mutations;
- inspect unrelated personal practice history.

Frontend should clearly identify the teacher attempt view as read-only.

## 6. Notification subsystem

Create a generic per-user notification resource, not a classroom-only table.

Conceptual model:

```text
Notification
- id
- user_id
- type
- title/title_key
- message/message_key
- entity_type
- entity_id
- read_at nullable
- created_at
```

Initial event types may include:
- `CLASSROOM_INVITED`;
- `CLASSROOM_INVITATION_ACCEPTED`;
- `CLASSROOM_INVITATION_DECLINED`;
- `TEST_CLASSROOM_APPROVED`;
- `TEST_CLASSROOM_REJECTED`;
- `TEST_PUBLIC_APPROVED`;
- `TEST_PUBLIC_REJECTED`;
- `CLASSROOM_ARCHIVED`.

Notification rules:
- `read_at IS NULL` means unread;
- header shows unread count;
- opening notification UI does not automatically mark all read;
- support marking one and marking all read;
- resolving notification actions always loads and authorizes the real target entity;
- notification/entity IDs never grant permission by themselves;
- pending-invite notification creation on login/registration must be idempotent;
- v1 does not require WebSocket/SSE; normal fetch/refetch is sufficient;
- no email delivery in v1.

## 7. API shape

Exact route naming should follow current project conventions, but the intended resource/actions are:

### 7.1 Tests and ownership

Reuse current test builder routes rather than creating a separate teacher builder.

`POST /tests`:
- ADMIN creates official-owned test;
- TEACHER creates teacher-owned test;
- USER forbidden.

Existing mutate/create-version/delete/validate flows move from ADMIN-only to policy-based access where appropriate. Teacher access is always owner-scoped and mutable-version-scoped; ADMIN retains global administrative control.

### 7.2 Moderation

Teacher:

```text
POST /test-versions/{version_id}/moderation-requests
POST /test-moderation-requests/{request_id}/cancel
```

Request body contains scope (`CLASSROOM` or `PUBLIC`) plus optional note.

ADMIN:

```text
GET  /admin/test-moderation-requests
GET  /admin/test-moderation-requests/{id}
POST /admin/test-moderation-requests/{id}/approve
POST /admin/test-moderation-requests/{id}/reject
POST /admin/test-moderation-requests/{id}/revoke   (or equivalent approval-revocation action)
```

Approval transaction must validate request still PENDING and version still matches the locked review target, then freeze/publish if this is the first approval and notify the teacher.

### 7.3 Classrooms

General resource endpoints:

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

ADMIN additionally has global archive/restore capability.

### 7.4 Invitations

```text
POST /classrooms/{id}/invitations
POST /classroom-invitations/{id}/cancel
GET  /me/classroom-invitations
POST /classroom-invitations/{id}/accept
POST /classroom-invitations/{id}/decline
```

### 7.5 Assignments and results

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

Assignment start derives classroom/test/user context server-side from the assignment and active membership. Browser-provided IDs must not be trusted when derivable.

### 7.6 Notifications

```text
GET  /notifications
GET  /notifications/unread-count
POST /notifications/{id}/read
POST /notifications/read-all
```

## 8. Concurrency and transactional requirements

The following operations must be transaction-safe and idempotent/conflict-safe where appropriate:
- invitation acceptance;
- active membership creation;
- moderation submission;
- moderation approve/reject/revoke;
- assignment creation;
- assignment start/provenance creation;
- teacher promotion/demotion validation;
- classroom archive/restore.

Double-click or concurrent requests must not create duplicate memberships, duplicate pending moderation requests, duplicate publication transitions, or duplicate notifications.

## 9. Domain errors

Use explicit domain errors instead of collapsing all failures into generic authorization errors. Expected error categories include equivalents of:

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

Names may adapt to established project conventions, but semantics must remain clear and testable.

## 10. Minimum frontend behavior (visual design deferred)

Detailed UI information architecture is intentionally not specified in this design round. Implementation must provide only the minimum coherent surfaces required by the approved product behavior:

- ADMIN user management can promote/demote TEACHER with conflict feedback.
- TEACHER can access existing Builder for owned tests and see ownership/moderation state.
- TEACHER can create/manage classrooms, invitations, assignments, and read-only results.
- ADMIN can review classroom/public moderation requests.
- USER can see classroom invitations, Accept/Decline, classroom assignments, and start assignment attempts.
- Global Test Library distinguishes official ADMIN content from public community teacher content.
- Global header includes notification unread count and notification list/actions.
- Archived resources render historical data read-only instead of disappearing as deleted data.
- New visible chrome follows the current EN/VI localization system.

No detailed page layout, dashboard visual hierarchy, realtime notification transport, deadlines, assignment limits, co-teachers, email notifications, or teacher grading UI are required in v1.

## 11. Compatibility and migration requirements

- Preserve existing USER flows and current official ADMIN-created tests.
- Preserve existing attempts/test sessions/history and published-version references.
- Legacy tests without recorded creators must migrate safely as system/legacy official content; do not invent a creator.
- Existing published version IDs referenced by attempts must remain valid.
- Do not rewrite historical attempts or official/manual Writing scores as part of classroom migration.
- Preserve current test import/export/builder/asset/versioning behavior unless ownership/access metadata must be added to maintain authorization.
- Review transfer/import behavior so newly imported tests receive correct owner/origin according to the authenticated importer instead of silently becoming unowned.

## 12. Security invariants

1. USER cannot self-promote to TEACHER.
2. TEACHER cannot edit another teacher's content.
3. TEACHER cannot mutate a published/approved version.
4. TEACHER content is not usable by other users until an appropriate ADMIN approval exists.
5. CLASSROOM approval does not grant global visibility.
6. PUBLIC approval grants global/community visibility and classroom eligibility.
7. Teacher cannot view student personal practice outside assignment provenance.
8. Notification presence never grants authorization.
9. Archived/revoked resources stop future actions but preserve historical academic data.
10. Role/resource checks are backend-authoritative.

## 13. Explicit non-goals for v1

- Email invitation delivery.
- Co-teachers or multiple classroom owners.
- Teacher ownership transfer.
- Assignment deadlines.
- Attempt-count limits.
- Teacher manual grading/editing of official Writing scores.
- WebSocket/SSE realtime generic notifications.
- Organization/school tenants.
- Paid courses/subscriptions.
- Full classroom analytics beyond assignment result/status views.

## 14. Acceptance summary

A complete v1 supports this end-to-end path:

```text
ADMIN promotes USER -> TEACHER
TEACHER creates test + draft
TEACHER submits CLASSROOM moderation
ADMIN approves
version is immutable/published + classroom-eligible
TEACHER creates classroom
TEACHER invites email
USER logs in and receives in-app invitation
USER accepts -> membership
TEACHER creates assignment from approved version
USER starts through assignment
attempt/session stores assignment provenance
TEACHER sees full assignment result read-only
same version may later be submitted for PUBLIC moderation
ADMIN approves PUBLIC
version appears globally as community content with teacher attribution
```

All historical attempt data remains stable if memberships, classrooms, approvals, or teacher role state later change.