# Focused Practice — Phases 1–3

Focused practice reuses `Attempt`, its owner, frozen published `TestVersion`, timer,
autosave, pause/resume, submission and review lifecycle. Phase 1 provides the scope
foundation; Phase 2 exposes Reading passages and Writing tasks; Phase 3 completes
the user-facing flow with Listening sections and shared-recording audio ranges.

## Phase 2 — Reading and Writing

`/practice` (sidebar: **Skill practice**) uses the existing authenticated workspace
and published-version APIs. It lists units from available, non-archived frozen
tests in one compact grid, with exact test/version provenance on every card.
An internal filter panel selects Reading, Listening or Writing and derives
Passage/Section/Task filters from the published units. Client-side search matches
test titles, unit titles and Writing prompt excerpts within those filters.
The panel sits beside results on desktop and above them on smaller screens;
cards adapt to the available width. Thumbnails are deferred. Test Library remains
the place for full skills and Full Mock.

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

## Phase 3 — Listening sections and audio ranges

Listening keeps one optional recording on the module. Nullable integer
`ListeningPart.audio_start_seconds` / `audio_end_seconds` locate each section in
that recording; no files are split or duplicated for clips. Migration
`20261010_0022_listening_audio_ranges` follows `20261010_0021`. Its PostgreSQL CHECK
allows both fields null, or both present with start >= 0 and end > start, including
explicit non-null checks. Old content remains valid without ranges.

The Builder section editor saves title and both boundaries together through the
existing revision-checked part update. Enter MM:SS, capture the current absolute
playback position, or preview the selected clip in the existing shared player.
Incomplete/malformed ranges, end <= start, and end beyond known browser duration
block autosave and preview with an explanation. Duration comes from browser audio
metadata; the backend validates range structure without probing/transcoding audio.

Replacing/removing the shared recording with a different asset ID resets all
section ranges in the same transaction and advances affected section revisions.
Reattaching the same ID preserves them. A stale editor cannot restore the old
range after replacement. Version cloning and ZIP export/import preserve ranges
while remapping section IDs; older schema-v1 archives without these optional fields
still import. Publishing full Listening does not require section ranges.

Public version summaries expose section UUIDs, start/end times, actual question
counts and a module `has_audio` boolean, without storage paths or answer keys.
Skill Practice allows focused section starts regardless of recording or range
availability. The backend proves the unit belongs to the exact published
module/version and validates the normal attempt scope and timer rules; audio is
an optional enhancement, not a focused-start prerequisite.

Focused Listening starts one LISTENING_PART via the existing attempt API with
10 / 15 / 20 minutes or count-up (default: 10), then opens `/attempt/{id}`. Its
runner and review receive only the selected section. With a configured range,
playback uses absolute source positions but displays a section-relative
00:00–clip-length timeline; seeking and
skip controls stay within the range, playback pauses at its end, and Play replays
from its start. Source/clip changes stop the previous playback without autoplay.
Invalid or out-of-duration ranges produce an actionable error, not a shortened
successful clip. Existing seeking/speed restrictions still apply.

Without a section range, focused runner/review offer the full recording with the
notice: "Section audio range is not configured. Full recording is available."
Without a recording, they render no player and show: "No recording is attached.
You can continue with the questions and use an external recording if needed."
Questions and the normal attempt lifecycle remain available in both cases.

Full standalone Listening, full Listening review, and Full Mock ignore section
ranges and continue using the entire recording; Full Mock seeking stays locked.
Focused review and history show raw/max and one-decimal accuracy with no IELTS
band. Pause/resume, autosave, flags, highlights and submission use the existing
lifecycle. Full-module Listening band mapping is unchanged. Focused analytics
remain out of scope; no AI, scoring prompts, grading versions or provider behavior
change in this phase.

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
module audio remains shared; only FOCUSED_UNIT playback applies section boundaries.

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

Phase 3 adds real migration/constraint tests, range/revision/reset persistence,
clone and legacy/current ZIP round trips, safe public summaries, focused start
eligibility and scoped exam/review. Vitest covers MM:SS helpers, bounded playback,
Builder capture/preview/autosave/conflicts/reset, Listening cards/timers/start,
focused/full/Full Mock runners, review and paused gates. Tests use synthetic audio
metadata and mocked APIs; no browser, E2E or live audio/model service is used.

Phase 3 focused validation commands (backend against isolated, migrated PostgreSQL):

```powershell
# backend/
uv run pytest tests/test_listening_audio_ranges.py tests/test_focused_attempts.py tests/test_focused_scope_migration.py tests/test_focused_attempt_contract.py tests/test_api_contract.py tests/test_listening.py tests/test_asset_cloning.py tests/test_transfer.py tests/test_full_mock_sessions.py -q --tb=line
# frontend/
npx vitest run tests/listening-audio-ranges.test.tsx tests/listening-player.test.tsx tests/listening-navigation.test.tsx tests/focused-listening-review.test.tsx tests/skill-practice.test.tsx tests/practice-library.test.tsx tests/focused-reading-review.test.tsx tests/reading-navigation.test.tsx tests/writing-review.test.tsx tests/attempt-page.test.tsx tests/attempt-history-list.test.tsx tests/focused-attempt-contract.test.ts tests/history-api.test.ts
npm run typecheck
```

Ruff lint/format checks and ESLint cover the changed/new Python and TypeScript
files. `git diff --check` covers the complete change.

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
