# Classroom learning analytics and improvement plans

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Classroom learning analytics and improvement plans. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/services/classroom_learning.py).
> Đọc cùng [current module/guide](modules/analytics.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

P4 extends the [Gradebook](classroom-gradebook.md), using the existing IELTS result records, P2 submission decisions and classroom capabilities. It adds no scoring engine, exam lifecycle, AI provider, embedding infrastructure or forecast.

## Scope and authorization

Teacher analytics requires `analytics.view`: owner/co-teacher have it, a TA needs the explicit flag, and ADMIN retains oversight. Classroom participants may read their own progress. Student drill-down contains only that classroom's assignment-originated records, including retained history. Personal practice stays private even when it uses the same TestVersion. Every request rechecks access.

Plan management requires `learning_plans.manage`. Gradebook staff may inspect classroom plans; students may read only their own. Active plans require an active account and student membership, excluding classroom staff. A former student who becomes a TA keeps historical work without counting as a current student. Archived rooms reject mutations.

## Results and periods

The repository reuses `selected_grades` and historical P2 root acceptance. Score selection runs across an assignment's accepted history first, and the selected root must then fall within the half-open range `[start, end)`. Default range: 90 days; maximum: 366 days. Changing the Gradebook selection policy can change the analytics sample. Both surfaces intentionally interpret an assignment consistently.

A standalone Attempt is one root. A Full Mock TestSession is one assignment submission and contributes each finalized component once to its corresponding skill summary. Session children never become separate submissions. Only published or historically archived TestVersions contribute performance. Reading/Listening use persisted objective results; Writing/Speaking require human final records. Missing grades remain null. Focused work can contribute question/criterion evidence, but cannot supply a full-module band. Full Mock overall requires four available skill bands and the native IELTS calculation.

Completion, missing work and eligible requirements use P2's current cohort/submission semantics across all assignments, independently of the performance date filter. The UI explains this distinction. Completion rate is accepted assignments / eligible requirements. On-time rate is on-time accepted / all accepted. Empty denominators yield null percentages.

## Evidence and repeated practice

Reading/Listening categories come from the structured question registry. Finalized objective attempts need persisted scores. Responses with null correctness are excluded; missing finalized responses count as unanswered and incorrect. DTOs contain no question text, responses or answer keys. Multiple-answer question accuracy uses native whole-question correctness, rather than replacing partial-credit raw scoring.

The question sample is the latest scored exposure per `(learner, question UUID)` in the selected roots/range. Repeated versions do not create new independent evidence. `questions_attempted` includes deduplicated finalized unanswered questions; `questions_correct`, `unanswered` and accuracy share that denominator. Additional occurrences are reported as `repeated_exposures`. Class samples represent learner/question pairs, not that many different authored questions.

Recent means the last 30 days ending at the range end; historical means the earlier portion. Question trends require five samples in both periods and express percentage-point differences, otherwise null. Writing criteria separate Task 1 and Task 2. Speaking criteria separate full-module and exact focused contexts. Human criterion samples are deduplicated per learner/task/version context, keeping the latest. Criterion trends require three samples in both periods. AI advisory output is excluded.

Skill summaries/history contain valid full-module bands separately for Reading, Listening, Writing and Speaking. Distinct-version counts expose repeated assessment use. Student charts use assessment timestamps and a fixed 0–9 scale, with dated text histories. One-point histories stay textual. Class summaries avoid joining different students' scores into one progression line.

## Deterministic practice priorities

| Rule | Minimum evidence | Trigger | Severity/confidence |
| --- | --- | --- | --- |
| Question type | 10 distinct learner/question pairs, 5 recent | Recent accuracy below 60% | High severity below 40%; high confidence needs 30 distinct and 10 recent, otherwise medium |
| Human criterion | 3 recent distinct assessments | Recent mean at least 0.5 below the skill target, or explicit 6.0 reference without a goal | High severity for a gap of 1 band; high confidence needs 8 recent samples |
| Full-module skill | 3 recent distinct versions and an explicit skill target | Recent mean at least 0.5 below target | Moderate severity, medium confidence |

Sparse data produces no weakness. Priorities sort by severity, confidence, descending sample size, skill and category, capped at 20. Responses expose observed value, baseline, reason and sample size. These are documented practice rules, not diagnoses, statistical certainty or predictions of future IELTS gains.

Recommendations inspect the latest 100 active assignments in the student's classroom. Existing P2 membership, publication/moderation, availability, deadlines and attempt limits determine eligibility. Already accepted assignments are excluded. Structured skill/question metadata must match the observed gap. Uncompleted versions rank ahead of completed versions, then weakness priority, unstarted work, creation date and UUID break ties. Results are deduplicated to six real assignment links with deterministic reasons. No suitable content yields an honest empty state; nothing is automatically assigned. Public-library discovery is outside this phase.

## Targets and learning plans

Targets validate half bands from 0 through 9. Four existing per-skill profile columns are reused; `users.target_overall_band` stores an optional explicit overall planning target. Without that explicit value, the existing derived profile target is displayed. Saving targets maintains the profile's derived `target_band`. Goals never alter scores or grading rules.

Normalized plans store student/classroom, author/updater, title, target skill, focus, description, status, revision and timestamps. Each plan contains 1–30 unique references to existing assignments/resources. Composite database foreign keys enforce same-classroom activities. Active plans accept published student-visible resources and active assignments. Hidden resources show an unavailable label without exposing their title.

Assignment completion comes from accepted submissions. An enrolled student may mark a visible non-assessment resource as studied; this separate self-reported marker cannot complete an IELTS assignment. `COMPLETED` requires every linked activity to be complete. Editing uses expected revisions (409 when stale). Archived plans and inactive item rows retain history. Plan pages default to 30, maximum 50.

## API

Paths are under `/api/v1`. Timestamp ranges require timezone awareness; `completion_offset` pages assignment aggregates by 20.

| Path | Method / permission |
| --- | --- |
| `/me/learning-goals` | GET/PUT own targets |
| `/classrooms/{id}/my-progress` | GET own classroom dashboard |
| `/classrooms/{id}/my-recommendations` | GET own recommendations |
| `/classrooms/{id}/analytics` | GET `analytics.view` |
| `/classrooms/{id}/students/{studentId}/analytics` | GET `analytics.view`, classroom cohort/history |
| `/classrooms/{id}/learning-plans` | GET own or staff-authorized classroom/student plans, limit/offset |
| `/classrooms/{id}/students/{studentId}/learning-plans` | POST `learning_plans.manage` |
| `/classrooms/{id}/students/{studentId}/learning-plans/{planId}` | PUT `learning_plans.manage`, expected revision |
| `/classrooms/{id}/learning-plans/{planId}/items/{itemId}/complete-resource` | POST active plan's enrolled student, visible resource only |

Typed frontend clients in `lib/api/classroom-learning.ts` validate Zod responses and convert Decimal target strings at the HTTP boundary. Repositories own aggregate SQL; services own access, scope and rules. There is no attempt-per-student query loop.

## Migration and deliberate bounds

Alembic `20261027_0038` adds scoped staff/Gradebook policy. `20261027_0039` adds the overall target plus plans/items. Both were migrated on the actual local database, verified at `20261027_0039 (head)`. Fresh isolated upgrade and empty-data downgrade through 0037/re-upgrade passed. Downgrade guards retain staff, nondefault grade policies, plans and explicit targets. The audit enum addition remains additive. Model constraints match the existing prefixed migration naming convention.

Responses cap at 60 trend points/skill, 20 recent assessments, 200 criterion groups (truncation flag), 20 completion aggregates/page, 50 attention students and six recommendations. The recommendation pool is bounded and classroom-only. Archived-plan filtering occurs within the displayed page. Large deployments may eventually need cached aggregates; no background analytics infrastructure was added. See [workspace UX](classroom-workspace.md) for design and browser-verification limits.
