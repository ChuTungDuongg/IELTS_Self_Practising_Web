# Classroom assignment scheduling (P2)

P3 extends schedule/extension management to authorized Co-teachers through the centralized classroom capability policy. Owner settings/staff management remain separate; TAs do not gain assignment or extension mutation rights. The same historical decision query now supplies Gradebook and classroom analytics. See [the P3 contract](classroom-gradebook.md).

P2 extends the existing assignment, immutable TestVersion and native IELTS engines. The new code does not set a second exam timer or change marking. The Classroom workspace adds an agenda Calendar, shared student progress, schedule editing, monitoring and individual exceptions.

## Policy and historical decisions

`ClassroomAssignment` adds timezone-aware `available_from`, `due_at`, `cutoff_at`, nullable `max_attempts`, `allow_late_submission`, and `policy_revision`. Instants are normalized to UTC. Inputs must include a timezone; numeric epoch values and naive dates are rejected. Validation requires availability strictly before due/cut-off, due at or before cut-off, and a positive integer limit. The current authoring bounds are 10,000 base starts and 10,000 additional starts.

Legacy rows receive null windows/limit and `allow_late_submission=true`, preserving their original unrestricted scheduling. Availability opens inclusively. Due and cut-off are inclusive: a finish exactly at due is on time; exactly at cut-off may be accepted late. New starts strictly after cut-off are blocked. With late submission disabled, starts and submissions strictly after due are blocked/not accepted. With no cut-off, late work may remain open indefinitely.

Every directly assigned standalone/focused Attempt consumes one start; every directly assigned TestSession consumes one start. Full Mock children consume no extra starts. Abandoned/unfinished starts count; personal practice and other assignments do not. Native resume links never create a new root. Checks run inside AttemptService/TestSessionService's existing creation transaction under actor, content-version, classroom, assignment and membership locks. Counting plus creation is serialized, including competing module/Full Mock requests. The existing moderation/ownership check remains authoritative.

Successful course submissions are root Attempts with SUBMITTED/AUTO_SUBMITTED and a finished timestamp. INTERRUPTED/ABANDONED are never successful submissions. A Full Mock requires parent COMPLETED, a finished timestamp, all expected children, and all children SUBMITTED/AUTO_SUBMITTED; finishing one module cannot satisfy the assignment. Native Speaking finalization and timer auto-submission use these same read rules. IELTS attempts/results remain available even when course acceptance fails.

Historical decisions are derived from an **append-only normalized policy timeline**, rather than changing engine completion code or adding a parallel exam state machine. `classroom_assignment_policy_events` records the actor, reason, revision, server `clock_timestamp()`, base schedule and individual override changes. A PostgreSQL trigger rejects UPDATE/DELETE on these events. For each successful root, SQL resolves the last base and student event effective at or before its authoritative `finished_at`. Later changes cannot relabel a past completion, including changing late acceptance or granting/revoking an extension. Pre-P2 completions with no earlier event use the unrestricted legacy policy. In-progress work uses policy changes effective before it completes. Historical acceptance is independent of when progress is first read.

The progress read model prioritizes the most recent accepted submission, then active work, then the most recent rejected successful submission. A successful accepted result stays satisfied while another retry is unfinished or rejected. `accepted`/`late` describe that chosen completion; current effective deadlines are displayed separately. Availability (SCHEDULED/OPEN/OVERDUE/CLOSED/ARCHIVED) and submission status are independent. MISSED requires closure and cohort eligibility. New active members joining after closure are not labeled missing for prior work. Monitoring includes current active memberships plus former students who actually have roots for the assignment; former members without work are excluded. Historical results retain their existing assignment-scoped authorization.

## Extensions and authorization

`classroom_assignment_extensions` has one mutable current exception per assignment/student and retains creation/update attribution; each change also appends an immutable event. Explicit `override_due` / `override_cutoff` booleans distinguish inheritance from removal: false inherits, true with null removes that deadline. Non-null overrides may extend a finite base deadline, never shorten it or introduce a new deadline on an unrestricted base. The resulting policy must satisfy date ordering. Additional starts add to a finite limit and leave unlimited policies unlimited. Revocation returns future decisions to the current base; completed decisions remain historical.

Only the owner TEACHER can edit new scheduling policy or manage exceptions; ADMIN retains existing assignment/classroom management and read oversight, including monitoring/history. Students read only their own effective progress. An extension can be granted/updated only for an active enrolled student. Revocation of an existing former member's exception remains possible while the classroom/assignment is active. Classroom/assignment archival blocks new policy changes and starts while preserving native in-progress work and history.

Schedule updates require `expected_revision`. Extension changes also advance the assignment revision, so a stale schedule form gets 409 instead of overwriting changes. No-op saves produce neither audit events nor notifications. If a proposed base edit invalidates an existing extension, the edit is rejected with 422 until that exception is deliberately adjusted/revoked. `test_version_id` cannot be patched. The UI confirms schedule changes and explains effects on work in progress.

## API contracts

All paths below are under `/api/v1/classrooms/{classroomId}` and use explicit DTOs.

| Path | Behavior |
| --- | --- |
| `POST /assignments` | Existing creation extended with optional scheduling fields |
| `PATCH /assignments/{id}` | Owner schedule/metadata update, required expected_revision, optional reason; TestVersion immutable |
| `GET /assignment-progress` | Authenticated actor's own progress; limit 1–100, offset, optional list of at most 100 assignment_ids |
| `GET /assignments/{id}/progress` | Actor's single-assignment progress |
| `GET /assignments/{id}/monitoring` | Owner/ADMIN cohort and summary, status/search filters, limit 1–100 and offset |
| `GET /assignments/{id}/extensions` | Staff current exceptions |
| `PUT/DELETE /assignments/{id}/extensions/{studentId}` | Owner grant/update or revoke |
| `GET /assignments/{id}/schedule-history` | Staff audit pages, limit 1–100 and offset |
| `GET /assignment-calendar` | Aware start/end, half-open range up to 93 days, limit 1–100 and offset |

Progress includes availability/submission status, effective deadlines/limit, root usage, remaining starts, can_start and structured denial code, active root resume links, selected completion/result link and acceptance. No exam content, scores or answer keys are copied into progress responses. Monitoring aggregates in SQL and loads extensions for the selected page in bulk; query count does not grow per student. Calendar events are range-filtered SQL projections of assignments (availability/due/cut-off), using per-student overrides for student views. There are no copied calendar-event rows.

## Notifications and operation

Assignment creation, material schedule changes, and individual exception changes create backend in-app events in the same transaction. Extension events reach only the affected active enrolled account. UUID-based event keys reuse the existing unique recipient-event constraint; repeated no-op updates do not notify. Notification links open the authorized assignment in the existing workspace.

The repository has durable AI workers but no general periodic scheduler. Deadline reminders therefore use a bounded, idempotent **one-shot CLI**:

```powershell
# From backend/, using that deployment's normal DATABASE_URL/.env
.venv/Scripts/python.exe -m app.assignment_reminders --limit 100
```

The job considers active classrooms/assignments and active enrolled accounts, sends due-soon reminders within 24 hours of the effective due date and one overdue reminder after it, and skips already satisfied requirements. Student-specific due dates, revocations and new enrollments are respected. Duplicate prevention includes recipient, assignment, reminder kind and effective due instant; retries and repeated runs do not duplicate events. It uses server time and existing PostgreSQL/local services. The JSON report includes processed/emitted and batch_full; a full batch means another invocation may be needed to drain a backlog. Different deployment workers may run the job safely because event insertion is idempotent.

**Periodic reminders are not deployed automatically by this change.** Configure the host scheduler after deployment. On a Linux deployment at `/opt/bandpilot`, using its existing backend `.env`, install this crontab entry for the application account (adjust installation/log paths to the actual host):

```cron
*/15 * * * * cd /opt/bandpilot/backend && .venv/bin/python -m app.assignment_reminders --limit 1000 >> /opt/bandpilot/assignment-reminders.log 2>&1
```

On Windows, configure Task Scheduler to repeat every 15 minutes, executable `C:\Users\Admin\IELTS_Self_Practising_Web\backend\.venv\Scripts\python.exe`, arguments `-m app.assignment_reminders --limit 1000`, and **Start in** `C:\Users\Admin\IELTS_Self_Practising_Web\backend`. Use the account/environment that owns the backend configuration. Enable task failure monitoring/log collection. No FastAPI background thread, Redis, Celery, email or external calendar connection is introduced. Immediate assignment notifications and deadline/start checks operate without scheduler configuration.

## Migration and limits

Alembic revision `20261027_0037` follows P1 `20261027_0036`. It adds the assignment fields, extension and event tables, notification enum labels and composite root-progress indexes. Existing exam/version/attempt data is not rewritten. Empty-feature downgrade is supported; downgrade refuses scheduling history or configured policies. Additive PostgreSQL notification labels remain after downgrade, following existing convention.

The agenda is a bounded list rather than a month grid. Status reads do not synchronize exam timers; resuming native work performs the engine's normal synchronization. A session containing abandoned/interrupted modules is retained and does not satisfy the course submission requirement. Each page exposes a selected completion and links to the existing results/history surfaces for other attempts. Reminder periodic execution requires the host configuration above. [P3 Gradebook and scoped staff](classroom-gradebook.md) and [P4 analytics, deterministic recommendations and plans](classroom-learning-analytics.md) now build on these same decisions. Attendance and AI-powered recommendations remain outside this scope.

Verification uses fictional fixtures, isolated PostgreSQL, focused pytest/Vitest and static checks. No browser, E2E, full test suite, production build or full development stack is used; visual behavior remains unverified in a browser.

### Verified scope (2026-10-27)

- Fresh PostgreSQL upgrade through 0037, empty P2 downgrade to 0036 and re-upgrade all succeeded. The configured local database was upgraded from 0036 and verified at `20261027_0037 (head)`.
- Focused backend: **145 passed**, covering new policy/scheduling/lifecycle tests plus existing classroom assignments, memberships/notifications, P1 Stream/Classwork/private resources and native Full Mock sessions. Real two-connection races confirm the start limit; native focused Reading auto-submission and Speaking completion are exercised. Monitoring pages use a constant query count; history rejects direct database updates.
- Focused frontend: **65 passed** across assignment scheduling, P1 content/API, teacher controls/API/pagination and notification center. TypeScript, scoped ESLint/Ruff and task-scoped `git diff --check` passed.
- One-shot CLI smoke check on the isolated test database returned a successful JSON batch report. No host scheduler was installed and no automatic periodic delivery is claimed.
