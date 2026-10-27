# Classroom staff and Gradebook (P3)

P3 extends P1/P2. Global USER/TEACHER/ADMIN roles and Builder ownership stay independent of classroom staff. The owner remains `classrooms.teacher_id`; there is no owner staff row.

## Permissions and staff lifecycle

`ClassroomStaff` stores explicit invitation state and four typed optional TA flags, not a free-form permission dictionary. The centralized `Capability` enum resolves the actor's current classroom role on every request. Owners have all classroom capabilities. Co-teachers may manage students, content, discussions, assignments/extensions, grades, analytics and improvement plans; they cannot change classroom settings/ownership or staff. TAs always have `grades.view`/`grades.edit`; `content.manage`, `discussion.moderate`, `analytics.view` and `learning_plans.manage` are opt-in owner-controlled flags. Students only see their authorized classroom and own work.

ADMIN retains management/read/grading oversight and existing assignment creation/archival; ADMIN does not gain authorship of another teacher's new learning content or staff management. P2 scheduling/extension edits remain an owner/co-teacher operation. Owner-only settings/archive calls are not replaced by broad staff checks.

Only existing active accounts can be invited. Co-teachers require global TEACHER; TAs require USER or TEACHER. Invitations require the recipient's explicit accept/decline. The owner can cancel, change role/flags and revoke access. A partial unique index permits one pending or accepted staff record per room/account. Actor/room locks serialize competing invitations and role changes. Every transition appends actor, role, status and flags to database-protected staff history. Accepted staff access is checked afresh; revocation does not grant access through a cached role.

Acceptance closes active student memberships in the same transaction. Historical submissions survive and remain discoverable, while staff are not ordinary active students in completion metrics. Re-enrollment as a student requires removing staff access and a new normal student invitation. Global TEACHER demotion/deactivation is blocked while a Co-teacher invitation/membership still requires TEACHER. Account deactivation continues to prevent authenticated access. Archived classrooms permit retained reads and block staff mutations.

Classroom assignment eligibility still requires official content or the owner's approved teacher content. Co-teachers receive a bounded assignable-test metadata endpoint; this does not grant Builder access, unpublished keys, editing rights or moderation bypasses.

## Scores and selection

Gradebook shares P2's root provenance, immutable historical acceptance and cohort/status SQL. Direct assigned Attempts are roots; Full Mock TestSessions are single roots and their children appear only in the skill breakdown. Personal practice and rejected/unfinished roots never supply accepted grades. Retained results do not depend on current enrollment.

Objective scores are stored native backend scores. Writing/Speaking require the corresponding human-final records; AI runs are never consulted. A missing human grade is `PENDING_HUMAN`, never zero. Focused units never supply full-module bands. Focused Writing may show its native task average, distinctly labeled as a task score. Full Mock overall uses the native four-skill aggregator only when all four valid final bands exist; legacy three-skill sessions retain breakdowns without a fabricated four-skill overall.

Each assignment defaults to `LATEST_ACCEPTED`. `FIRST_ACCEPTED` chooses the earliest accepted completion. `BEST_ACCEPTED` ranks only a homogeneous assessment context (skill, full/focused scope, stable focused unit; or persisted Full Mock module order). Available native bands/raw objective scores or focused Writing task averages determine rank; missing comparable scores fall back deterministically to latest completion. Heterogeneous contexts use latest accepted and explicitly return `mixed_context_fallback`. Filtering one skill can produce a comparable selection. Dates and UUIDs break ties. Schedule/extension history and exam content are not changed by selection policy edits; revision checks prevent stale writes.

The matrix paginates students (default 30, maximum 100) and assignment columns (20). Search, assignment, skill, completion and name sorting are server-side. Score sorting requires an assignment and skill filter so a cross-skill ranking is never implied. Student profiles paginate assignment summaries and successful root history; status counts describe the displayed assignment page. Existing result/grading pages remain canonical.

CSV uses the same permission checks, filters and selected score resolution. A bounded export contains at most 200 students and 20 assignment columns starting at the requested offsets; request subsequent pages for a larger class. It includes selection, skill, nullable final band/raw score, submission and grading provenance. Column order is stable. Python CSV escaping, a UTF-8 BOM and spreadsheet formula/control-character escaping protect exported names and titles. It contains no personal practice or answer keys.

## API

Paths are under `/api/v1`:

| Path | Operations |
| --- | --- |
| `/me/classroom-staff-invitations` | GET own bounded invitation history |
| `/classrooms/{id}/staff` | GET staff roster/history; POST owner invitation |
| `/classrooms/{id}/staff/{staffId}` | PATCH owner role/typed flags; DELETE cancel/revoke |
| `/classrooms/{id}/staff/{staffId}/{accept,decline}` | POST recipient response |
| `/classrooms/{id}/assignable-tests` | GET bounded authorized published assignment metadata |
| `/classrooms/{id}/gradebook` | GET paginated matrix |
| `/classrooms/{id}/gradebook/export` | GET bounded authenticated CSV |
| `/classrooms/{id}/assignments/{assignmentId}/grade-policy` | PATCH selection with expected revision |
| `/classrooms/{id}/students/{studentId}/academic-profile` | GET retained classroom-only profile |

`GET /classrooms/{id}` now returns contextual role/capabilities. Existing classroom member/content/assignment/result/scheduling/grading APIs check their specific capabilities. The Stream supports a server-side `content_kind` filter bound into pagination cursors.

## Classroom UX/UI overhaul

The completed [dual-skill workspace refactor](classroom-workspace.md) adds topic-first content workflows, contextual creation/actions, responsive matrix/list views and integrated [P4 learning analytics/plans](classroom-learning-analytics.md). Both 0038 and 0039 are applied to the actual local database; the current head is 0039. The original P3 verification below records its phase-specific snapshot.

The shared course shell uses a compact real-data header, one scrolling tab row, one fluid content plane and no empty permanent sidebars or duplicate section selectors. Archive/restore/leave live in a contextual management disclosure. Creation opens a focused assignment form; scheduling uses progressive disclosure. Staff see a real assignment/member overview and direct Gradebook/People/material navigation. Students see learning workflows without staff administration tabs.

Feed entries have prominent title fallbacks, a semantic localized timestamp, explicit content type and grouped deadlines. Classwork retains native resource access and keyboard/drag ordering and explains the empty course with a first-section action. Gradebook uses an internal scroll frame, sticky student column, semantic table headers and expandable result details. Small screens keep tab/table overflow inside their frames and use 44px actions. Both locales and shared light/dark tokens remain in use.

Design continuation: `design-taste-frontend`, achromatic-ledger seed 2734, existing palette/type retained; IELTS skill lanes and accepted/pending score provenance provide the product identity. The course screen answers “What needs teaching or completion next?” and Gradebook answers “Which accepted work has a final grade?” No browser, E2E, production build or full suite is used under this task's verification limits; responsive behavior is source/unit checked and visual browser verification is not claimed.

## Migration

Additive `20261027_0038` follows P2 `0037`, adding `classroom_staff`, append-only `classroom_staff_events`, indexes/constraints and `classroom_assignments.grade_selection`. Exam content, provenance, timers and scores are not rewritten. Downgrade is only for an unused feature domain and refuses retained staff/policy data. Apply through normal Alembic deployment after isolated migration verification.
