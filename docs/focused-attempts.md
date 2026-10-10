# Focused Practice — Phases 1 and 2

Focused practice reuses `Attempt`, its owner, frozen published `TestVersion`, timer,
autosave, pause/resume, submission and review lifecycle. Phase 1 provides the scope
foundation; Phase 2 exposes Reading passages and Writing tasks in the workspace.

## Phase 2 — Reading and Writing

`/practice` (sidebar: **Skill practice**) uses the existing authenticated workspace
and published-version APIs. It lists available, non-archived frozen tests, grouped
by test/version, with Reading and Writing tabs. Test Library remains the place for
full skills and Full Mock.

Public VersionDetail summaries now include Reading passage IDs and Writing task
IDs, minimum recommended words and recommended duration. Question-group summaries
include the actual question-slot count, so unusual numbering does not imply a
fictitious continuous range. Summaries contain no answer keys or explanations.

Reading starts one passage with 20 / 25 / 30 minutes or count-up (default: 20).
Writing starts one Task 1 or Task 2 with 20 / 25 / 30 / 35 / 40 minutes or count-up
(defaults: Task 1 = 20, Task 2 = 40). Both use existing `POST /attempts`, scope
FOCUSED_UNIT and the real published unit UUID, then open `/attempt/{id}`. Pending
starts prevent duplicate clicks; failures retain the selected timer.

Existing runners and paused gates identify the focused unit. A single Writing
task has no redundant task switch. Autosave, highlights, flags, images, word count,
timers and lifecycle transitions retain their existing behavior.

Review and **Focused practice** history show Reading raw/max correct and one-decimal
accuracy when max is positive; partial results never imply an IELTS band. Focused
Writing shows **Task score** when criterion scores exist, otherwise **Not graded**.
The nullable history `task_score` uses existing `calculate_task_overall` for the
selected Writing task only, while `band_score` stays null. Other scopes/modules
return null task_score. Review preserves the exact task average to two decimals;
history formats it to one decimal. There is no weighted Writing overall for a
single task. Existing manual criteria and task-specific AI assessment remain usable
without changing scoring or provider lifecycle.

History tabs are **By skill**, **Focused practice**, **By test**, **By mock test**.
Focused records appear in Focused practice rather than By skill. Continue, Resume,
Review and standalone Delete use existing actions. By-test/Full Mock grouping,
group deletion and full-skill analytics remain unchanged.

**Focused Listening user flow is not implemented yet.** Phase 3 requires separate
audio-range design. Existing API-created focused Listening records can appear in
history as Section N with raw/max and accuracy; Phase 2 adds no Listening start UI,
audio segmentation or Builder changes.

## Phase 1 foundation (preserved)

`AttemptContext` remains STANDALONE / FULL_MOCK. The independent `AttemptScope` is
FULL_MODULE / FOCUSED_UNIT. Full Mock always creates FULL_MODULE attempts and retains
its frozen module durations and Listening → Reading → Writing progression.

Migration `20261010_0021_focused_attempt_scope` backfills historical attempts as
FULL_MODULE and adds a non-null scope plus nullable, RESTRICT foreign keys to
`reading_passages`, `listening_parts` and `writing_tasks`. Check constraints require
exactly the matching target for focused attempts, no target for full modules, and
FULL_MODULE whenever `test_session_id` is set. Downgrade refuses to remove scope
while focused records exist, preventing partial history from being reinterpreted.

Existing `POST /api/v1/attempts` requests may omit scope and still start FULL_MODULE.
A focused request adds `scope: "FOCUSED_UNIT"` and a discriminated `focused_unit`
object containing `kind` (READING_PASSAGE / LISTENING_PART / WRITING_TASK) and `id`.
The server proves the target belongs to the exact available published version and
module. Missing and foreign target IDs share the same safe error response.

Attempt and history DTOs return `scope` and `focused_unit` (null for full modules).
The focused presentation contains kind, ID, original zero-based order index,
`Passage N` / `Section N` / `Task N` label, and an optional title. Exam, paused state
and review reuse this metadata; clients need no knowledge of the three storage FKs.

`TimerRequest` checks structure only: positive countdown duration required, no
duration for count-up. Standalone start policy then validates module/scope presets:

| Scope | Countdown minutes |
| --- | --- |
| Full module | 40 / 50 / 60 / 70 |
| Focused Reading passage | 20 / 25 / 30 |
| Focused Listening section | 10 / 15 / 20 |
| Focused Writing task | 20 / 25 / 30 / 35 / 40 |

All standalone scopes also support count-up. Full Mock bypasses these standalone
presets and continues using its existing module duration contract.

`AttemptScopeGuard` centralizes unit/group membership, scoped scoring predicates
and presentation. Existing ownership/version checks run before scope checks for
answers, flags, question visits, navigation, highlights, Writing responses, manual
task scoring and AI eligibility. Exam and review return only the selected unit;
unrelated content and answer keys are never sent for clients to hide. Listening
module audio and its playback policy retain their current behavior.

Focused Reading/Listening store raw/max scores for their selected questions, with
band null even if that unit happens to contain 40 questions. Expiration uses the
same scoring path. A focused Writing task can retain its response and criterion/task
scores, but attempt-level Writing band remains null. AI prompts, calibration and
grading versions are unchanged.

Normal history items include focused records and their scope. Existing By-test
full-module slots and existing analytics exclude focused attempts. Phase 2 adds
the dedicated history view described above without introducing focused analytics.

## Validation

Phase 2 adds focused presenter/history contract tests and Vitest coverage for
practice cards, timer/start behavior, protected navigation, scoped runners/reviews,
paused gates and history actions. Full skill, Full Mock, deletion and AI assessment
regressions use the existing tests. Validation uses isolated PostgreSQL, mocked
frontend APIs, typecheck and targeted Ruff/ESLint checks, without live inference.

Phase 1 validation commands:

Executed against an isolated PostgreSQL database migrated with `uv run alembic
upgrade head`. Migration tests execute the actual upgrade/downgrade DDL inside
their rollback boundary; no metadata-created schema substitutes for migrations.

From `backend/`:

```powershell
uv run pytest tests/test_focused_attempts.py tests/test_focused_scope_migration.py tests/test_focused_attempt_contract.py tests/test_timer.py tests/test_attempt_state_machine.py tests/test_attempt_scoring_history.py tests/test_attempt_pause.py tests/test_writing_attempts.py tests/test_full_mock_sessions.py tests/test_analytics.py -q
uv run pytest tests/test_focused_attempts.py tests/test_lifecycle_refactor.py::test_generic_highlights_and_bulk_delete tests/test_lifecycle_refactor.py::test_text_completion_layout_and_answers_round_trip tests/test_lifecycle_refactor.py::test_archived_test_blocks_new_attempt_and_restore_allows_it tests/test_listening.py::test_listening_review_returns_saved_question_highlights tests/test_full_mock_history_delete.py tests/test_attempt_deletion.py tests/test_writing_ai.py -q
```

From `frontend/`:

```powershell
npx vitest run tests/focused-attempt-contract.test.ts tests/history-api.test.ts tests/attempt-lifecycle.test.ts tests/attempt-page.test.tsx tests/writing-review.test.tsx
npm run typecheck
npx eslint src/lib/api/attempts.ts src/lib/api/history.ts tests/focused-attempt-contract.test.ts
```

Ruff lint/format checks cover changed Python files; `git diff --check` covers the
complete change. No browser, E2E, live model or deployment validation is used.
