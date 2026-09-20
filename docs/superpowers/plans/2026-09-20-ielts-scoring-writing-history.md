# IELTS Scoring, Writing, and History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add product-rule IELTS band scoring, a persistent Writing builder/exam/review workflow, manual Writing grading, and backend-aggregated attempt history without regressing Reading or Listening.

**Architecture:** Extend the existing SQLAlchemy/Pydantic service layer and additive REST DTOs. Keep score conversion, Writing validation, response persistence, aggregate selection, and overall rounding in FastAPI; add focused Next.js components that consume those contracts and reuse the current builder, timer, asset, review, and visual systems.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy asyncio, PostgreSQL, Alembic, pytest, Next.js 16, React 19, TypeScript 5.9, Zod 4, Vitest, Testing Library, Tailwind/CSS.

**Spec:** `docs/superpowers/specs/2026-09-20-ielts-scoring-writing-history-design.md`

## Global Constraints

- Reading and Listening use the exact shared product mapping in the spec; raw scores 0–2 and every non-40 module have `band_score = null`.
- `attempts.band_score` is nullable `NUMERIC(2,1)` and `raw_score`/`max_score` remain unchanged.
- Published versions are immutable; attempts retain frozen version references.
- Writing has exactly fixed Task 1/order 0 and Task 2/order 1 when initialized; only Task 1 accepts a `WRITING_TASK_IMAGE`.
- Writing responses use plain text and `AttemptWritingResponse`; backend word count is authoritative.
- Writing has no objective raw/max score and no automatic band score.
- Overall is computed by the backend from exactly three bands and rounded to 0.5 with decimal half-up behavior.
- Active exam DTOs never expose objective answer keys.
- Do not implement Speaking, authentication, or automated Writing scoring.
- Preserve the local `frontend/next-env.d.ts` modification and do not stage or overwrite it.
- Add no copyrighted exam content and no new runtime dependency.

## Review Focus

- A timer-expired objective attempt must be scored before finalization even when no explicit submit request caused the transition; Task 2 adds an integration test for it.
- A cloned Writing task may retain the repository's existing shared image reference, but a newly attached image must belong to the editable draft; Task 3 tests both behaviors.
- A failed explicit or pre-submit Writing save must leave the attempt unsubmitted and show a retryable error; Task 6 tests it.
- Deleting the attempt selected by a history group must refresh the server-produced selection and overall rather than recomputing in React; Task 7 tests refresh behavior.
- Empty or partial Writing drafts must remain editable and follow current publish-warning philosophy, while invalid task identity and Task 2 images remain blocking; Task 3 tests both classes.

---

### Task 1: Band Scoring Domain and Persistence

**Files:**
- Create: `backend/app/domains/scoring/ielts_band.py`
- Create: `backend/tests/test_ielts_band.py`
- Create: `backend/alembic/versions/20260920_0007_attempt_band_score.py`
- Modify: `backend/app/domains/scoring/__init__.py`
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/schemas/attempts.py`

**Interfaces:**
- Produces: `listening_raw_to_band(int, int) -> float | None`
- Produces: `reading_raw_to_band(int, int) -> float | None`
- Produces: `round_to_half(Decimal) -> Decimal`
- Produces: `project_overall_band(float | Decimal | None, float | Decimal | None, float | Decimal | None) -> float | None`
- Produces: `Attempt.band_score` and `AttemptResponse.band_score`

- [ ] **Step 1: Write the pure scoring tests**

```python
PRODUCT_BANDS = {
    40: 9.0, 39: 9.0, 38: 8.5, 37: 8.5, 36: 8.0, 35: 8.0,
    34: 7.5, 33: 7.5, 32: 7.0, 30: 7.0, 29: 6.5, 27: 6.5,
    26: 6.0, 23: 6.0, 22: 5.5, 20: 5.5, 19: 5.0, 16: 5.0,
    15: 4.5, 13: 4.5, 12: 4.0, 10: 4.0, 9: 3.5, 7: 3.5,
    6: 3.0, 5: 3.0, 4: 2.5, 3: 2.5, 2: None, 0: None,
}

@pytest.mark.parametrize("raw, expected", PRODUCT_BANDS.items())
def test_reading_and_listening_use_product_table(raw, expected):
    assert reading_raw_to_band(raw, 40) == expected
    assert listening_raw_to_band(raw, 40) == expected
```

Also assert non-40 returns `None`, invalid raw/max combinations raise `ValueError`, missing overall inputs return `None`, the examples produce 7.0/7.0/7.5, and `round_to_half(Decimal("7.25")) == Decimal("7.5")`.

- [ ] **Step 2: Run the scoring test and verify it fails**

Run: `Set-Location backend; uv run pytest tests/test_ielts_band.py -q`

Expected: import failure for `app.domains.scoring.ielts_band`.

- [ ] **Step 3: Implement the immutable threshold table and Decimal rounding**

```python
_PRODUCT_THRESHOLDS = (
    (39, 9.0), (37, 8.5), (35, 8.0), (33, 7.5), (30, 7.0),
    (27, 6.5), (23, 6.0), (20, 5.5), (16, 5.0), (13, 4.5),
    (10, 4.0), (7, 3.5), (5, 3.0), (3, 2.5),
)
```

Validate input before checking `max_score == 40`, return the first matching threshold, and use `ROUND_HALF_UP` after multiplying by two.

- [ ] **Step 4: Add the model field, response field, and migration**

Use `sa.Numeric(precision=2, scale=1)` in the migration and `Numeric(2, 1)` with `Decimal | None` in SQLAlchemy. Add `band_score: float | None` to `AttemptResponse` and `HistoryItem`.

- [ ] **Step 5: Run focused tests and migration SQL validation**

Run: `Set-Location backend; uv run pytest tests/test_ielts_band.py -q; uv run alembic upgrade head --sql | Out-Null`

Expected: scoring tests pass and Alembic renders without an exception.

- [ ] **Step 6: Commit the scoring domain**

```powershell
git add backend/app/domains/scoring backend/app/models/entities.py backend/app/schemas/attempts.py backend/alembic/versions/20260920_0007_attempt_band_score.py backend/tests/test_ielts_band.py
git commit -m "feat: add IELTS band scoring domain"
```

### Task 2: Attempt Finalization and Backend History Aggregates

**Files:**
- Modify: `backend/app/services/attempts.py`
- Modify: `backend/app/repositories/attempts.py`
- Modify: `backend/app/schemas/attempts.py`
- Modify: `backend/tests/test_timer.py`
- Create: `backend/tests/test_attempt_scoring_history.py`

**Interfaces:**
- Consumes: Task 1 scoring helpers and `Attempt.band_score`
- Produces: async attempt synchronization that scores before finalization
- Produces: `HistoryGroup` and `AttemptList.groups`

- [ ] **Step 1: Write objective finalization and serialization tests**

Create a published 40-question fictional objective module, save boundary-count correct answers, submit it, and assert raw/max/band in `AttemptResponse`, review, and history. Add a timer-expiry case that calls `get()` after the deadline and asserts `AUTO_SUBMITTED` plus the same score fields. Add a Writing `_score` case asserting all three score fields are null.

- [ ] **Step 2: Write history grouping tests**

Create multiple finalized attempts for the same version/module with distinct finish times, plus attempts on another version. Assert groups never merge versions, select the latest finalized attempt per skill, retain all rows in `items`, require all three bands for overall, and apply the Task 1 example results.

- [ ] **Step 3: Run tests and verify failures**

Run: `Set-Location backend; uv run pytest tests/test_attempt_scoring_history.py tests/test_timer.py -q`

Expected: missing band fields/groups and unscored timer finalization failures.

- [ ] **Step 4: Refactor synchronization and scoring**

Change `_synchronize_state` to `async`, await it from `get`, activity, answer, flag, highlight, Writing save, and submit paths, and call `_score` before every terminal transition it initiates. `_score` switches explicitly on `ModuleType`: objective modules calculate raw/max/band; Writing clears them.

- [ ] **Step 5: Add history schemas and aggregate construction**

```python
class HistoryGroup(BaseModel):
    test_id: UUID
    test_version_id: UUID
    test_title: str
    version_number: int
    reading: HistoryItem | None = None
    listening: HistoryItem | None = None
    writing: HistoryItem | None = None
    overall_band_score: float | None = None
```

Select latest non-`IN_PROGRESS` items by `finished_at` then `started_at`, compute overall with the shared domain helper, and return `AttemptList(items=..., groups=..., total=...)`.

- [ ] **Step 6: Run focused backend tests**

Run: `Set-Location backend; uv run pytest tests/test_attempt_scoring_history.py tests/test_timer.py tests/test_attempt_state_machine.py -q`

Expected: all pass.

- [ ] **Step 7: Commit attempt scoring and history domain**

```powershell
git add backend/app/services/attempts.py backend/app/repositories/attempts.py backend/app/schemas/attempts.py backend/tests/test_attempt_scoring_history.py backend/tests/test_timer.py
git commit -m "feat: score finalized attempts and aggregate history"
```

### Task 3: Writing Builder Backend and Validation

**Files:**
- Create: `backend/app/services/writing.py`
- Create: `backend/app/api/v1/writing.py`
- Create: `backend/tests/test_writing_builder.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/repositories/tests.py`
- Modify: `backend/app/schemas/content.py`
- Modify: `backend/app/services/reading.py`
- Modify: `backend/app/services/tests.py`
- Modify: `backend/tests/test_version_validation.py`

**Interfaces:**
- Produces: `BuilderWritingTask`, `WritingTaskWrite`, and `BuilderModule.writing_tasks`
- Produces: `PUT /writing/tasks/{task_id}`
- Extends: existing generic module creation to initialize fixed Writing tasks atomically

- [ ] **Step 1: Write Writing builder service tests**

Test atomic module initialization and defaults, updates to prompt/word minimum/duration, Task 1 valid image attachment, wrong type and wrong version rejection, Task 2 image rejection, published-version immutability, image removal cleanup, and module deletion.

- [ ] **Step 2: Write validation and clone tests**

Assert a partial Writing draft saves and reports readiness warnings; invalid numbers/orders and Task 2 images are blocking; cloning preserves both tasks and existing image references; repository loading exposes image metadata.

- [ ] **Step 3: Run tests and verify failures**

Run: `Set-Location backend; uv run pytest tests/test_writing_builder.py tests/test_version_validation.py -q`

Expected: missing DTO/service/route behavior.

- [ ] **Step 4: Extend the builder contract and relationship loading**

Add the explicit `WritingTask.image_asset` relationship, load it from `version_detail_query`, present it through `ReadingService._present_version`, and default `writing_tasks=[]` additively.

- [ ] **Step 5: Add atomic initialization and task update validation**

When `ModuleCreate.module_type == WRITING`, append the two fixed task records before flushing. `WritingTaskWrite` contains only `prompt`, `minimum_recommended_words`, `recommended_duration_seconds`, and `image_asset_id`. The service derives identity from the stored task and enforces the Task 1/Task 2 asset rules.

- [ ] **Step 6: Extend publish validation**

Check module ownership, task number/order uniqueness and allowed pairs, image type/ownership, and Task 2 prohibition as errors. Emit readiness warnings for missing tasks, blank prompts, and nonstandard recommendation values without preventing partial drafts from being saved.

- [ ] **Step 7: Run focused builder tests and OpenAPI contract test**

Run: `Set-Location backend; uv run pytest tests/test_writing_builder.py tests/test_version_validation.py tests/test_api_contract.py -q`

Expected: all pass, including the new Writing task route in OpenAPI.

- [ ] **Step 8: Commit Writing builder backend**

```powershell
git add backend/app/api/v1/writing.py backend/app/api/v1/router.py backend/app/models/entities.py backend/app/repositories/tests.py backend/app/schemas/content.py backend/app/services/reading.py backend/app/services/tests.py backend/app/services/writing.py backend/tests/test_writing_builder.py backend/tests/test_version_validation.py backend/tests/test_api_contract.py
git commit -m "feat: add Writing builder backend"
```

### Task 4: Writing Response, Review, and Manual Grade APIs

**Files:**
- Modify: `backend/app/schemas/attempts.py`
- Modify: `backend/app/schemas/content.py`
- Modify: `backend/app/repositories/attempts.py`
- Modify: `backend/app/services/attempts.py`
- Modify: `backend/app/api/v1/attempts.py`
- Create: `backend/tests/test_writing_attempts.py`

**Interfaces:**
- Produces: `WritingResponseUpdate`, `WritingResponse`, `WritingScoreUpdate`
- Produces: `ExamWritingTask` in `AttemptExam.writing_tasks`
- Produces: `WritingAttemptReview`
- Produces: Writing save, Writing review, and manual score endpoints

- [ ] **Step 1: Write Writing response lifecycle tests**

Start a published Writing attempt, assert empty saved content in the exam DTO, save both tasks, verify Unicode word counts, update one response through upsert, reload the exam DTO, submit, and assert responses remain while raw/max/band remain null.

- [ ] **Step 2: Write ownership and grading validation tests**

Reject saves on objective attempts, wrong-version tasks, and finalized attempts. Accept every half-band from 0 through 9 on finalized Writing; reject -0.5, 7.25, 9.5, in-progress grading, and grading objective attempts. Assert review/history immediately reflect the saved band.

- [ ] **Step 3: Run tests and verify failures**

Run: `Set-Location backend; uv run pytest tests/test_writing_attempts.py -q`

Expected: missing API/service methods and schemas.

- [ ] **Step 4: Implement response upsert and active DTO presentation**

Use PostgreSQL `insert(...).on_conflict_do_update` on `(attempt_id, writing_task_id)`, call backend `count_words`, update activity time, and add `WRITING_UPDATED` metadata. Present every version task with stored content defaulting to `""` and word count `0`.

- [ ] **Step 5: Implement Writing review and manual grade**

Build the review from frozen version tasks plus response lookup, include Task 1 image metadata, validate band with Decimal so 0.5 increments are exact, persist `Attempt.band_score`, and return the updated review or attempt response.

- [ ] **Step 6: Verify answer-key isolation and API contracts**

Run: `Set-Location backend; uv run pytest tests/test_writing_attempts.py tests/test_api_contract.py tests/test_writing_text.py -q`

Expected: all pass; active schemas contain no answer-key field for Writing.

- [ ] **Step 7: Commit Writing attempt APIs**

```powershell
git add backend/app/api/v1/attempts.py backend/app/repositories/attempts.py backend/app/schemas/attempts.py backend/app/schemas/content.py backend/app/services/attempts.py backend/tests/test_writing_attempts.py backend/tests/test_api_contract.py
git commit -m "feat: persist and grade Writing attempts"
```

### Task 5: Writing Builder and Draft Preview Frontend

**Files:**
- Create: `frontend/src/features/test-builder/writing-builder.tsx`
- Create: `frontend/tests/writing-builder.test.tsx`
- Modify: `frontend/src/lib/api/builder.ts`
- Modify: `frontend/src/lib/api/assets.ts`
- Modify: `frontend/src/lib/routes.ts`
- Modify: `frontend/src/features/test-builder/builder-workspace-navigation.tsx`
- Modify: `frontend/src/features/test-builder/draft-preview.tsx`
- Modify: `frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx`
- Modify: `frontend/src/app/admin/tests/[testId]/versions/[versionId]/preview/page.tsx`
- Modify: `frontend/tests/builder-workspace-navigation.test.tsx`
- Modify: `frontend/tests/builder-workspace-page.test.tsx`
- Modify: `frontend/tests/draft-preview.test.tsx`

**Interfaces:**
- Consumes: Task 3 builder DTO and task update endpoint
- Produces: `createWritingModule`, `updateWritingTask`, and Writing workspace UI

- [ ] **Step 1: Update frontend contract fixtures and write failing UI tests**

Add `writing_tasks: []` to existing builder fixtures. Test Writing navigation link/status, module initialization, fixed two-task rendering, editable prompts/minimums/durations, Task 1 upload/replace/remove/preview, absence of Task 2 upload controls, deletion confirmation, and Writing draft preview content.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `Set-Location frontend; npm test -- writing-builder.test.tsx builder-workspace-navigation.test.tsx builder-workspace-page.test.tsx draft-preview.test.tsx`

Expected: missing schemas, route acceptance, and components.

- [ ] **Step 3: Extend Zod contracts and API functions**

Add `builderWritingTaskSchema`; default `writing_tasks`, passages, and listening parts to empty arrays; extend `builderPreviewPath` with `writing`; keep `uploadAsset("images", ...)` for Writing task images.

- [ ] **Step 4: Implement the focused Writing builder**

Reuse `BuilderLifecycleProvider`, existing buttons, `ConfirmDialog`, `uploadAsset`, module deletion, and `router.refresh`. Use controlled task editor cards and send one complete task update per Save/image mutation.

- [ ] **Step 5: Enable workspace, overview, and preview routing**

Add `writing` to `BuilderWorkspace`, enable its row, render Writing-specific overview task counts, select `WritingBuilder`, accept `?module=writing`, and render a noninteractive two-task preview.

- [ ] **Step 6: Run focused frontend tests**

Run: `Set-Location frontend; npm test -- writing-builder.test.tsx builder-workspace-navigation.test.tsx builder-workspace-page.test.tsx draft-preview.test.tsx`

Expected: all pass.

- [ ] **Step 7: Commit Writing builder frontend**

```powershell
git add frontend/src/features/test-builder/writing-builder.tsx frontend/src/features/test-builder/builder-workspace-navigation.tsx frontend/src/features/test-builder/draft-preview.tsx frontend/src/lib/api/builder.ts frontend/src/lib/api/assets.ts frontend/src/lib/routes.ts frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx frontend/src/app/admin/tests/[testId]/versions/[versionId]/preview/page.tsx frontend/tests/writing-builder.test.tsx frontend/tests/builder-workspace-navigation.test.tsx frontend/tests/builder-workspace-page.test.tsx frontend/tests/draft-preview.test.tsx
git commit -m "feat: add Writing builder workspace"
```

### Task 6: Writing Runner and Review Frontend

**Files:**
- Create: `frontend/src/features/writing/writing-runner.tsx`
- Create: `frontend/src/features/writing/writing-review.tsx`
- Create: `frontend/tests/writing-runner.test.tsx`
- Create: `frontend/tests/writing-review.test.tsx`
- Modify: `frontend/src/lib/api/attempts.ts`
- Modify: `frontend/src/lib/api/exam.ts`
- Modify: `frontend/src/features/exam/start-attempt.tsx`
- Modify: `frontend/src/app/library/page.tsx`
- Modify: `frontend/src/app/attempt/[attemptId]/page.tsx`
- Modify: `frontend/src/app/review/[attemptId]/page.tsx`
- Modify: `frontend/src/features/reading/reading-review.tsx`
- Modify: `frontend/src/features/listening/listening-review.tsx`

**Interfaces:**
- Consumes: Task 4 exam/review/save/grade contracts
- Produces: Writing candidate and Writing review experiences
- Extends: objective review headers with `band_score`

- [ ] **Step 1: Write runner tests**

Test both task tabs, Task 1 image, restored server text, local word count updates, 750 ms debounced autosave, immediate Save, error state, save-before-submit ordering, and prevention of submit after a failed save.

- [ ] **Step 2: Write review and routing tests**

Test response/prompt/image/word count display, all 19 half-band options, save-score API invocation and updated display, Writing-specific attempt/review routing, and objective review headers showing band plus raw/max.

- [ ] **Step 3: Run focused tests and verify failures**

Run: `Set-Location frontend; npm test -- writing-runner.test.tsx writing-review.test.tsx`

Expected: missing API functions and components.

- [ ] **Step 4: Extend exam and attempt API schemas**

Add `band_score` to attempt schema, Writing task schema to exam payload, `saveWritingResponse`, `getWritingReview`, and `saveWritingScore`. Parse responses with Zod rather than unchecked casts.

- [ ] **Step 5: Implement Writing runner**

Reuse timer offset helpers and activity heartbeat. Maintain per-task content, dirty revisions, debounce handles, and saved/error state. An explicit Save cancels the timer and persists immediately. Submit awaits a successful current-task save before calling `submitAttempt`.

- [ ] **Step 6: Implement Writing review and routing**

Render frozen prompts, optional Task 1 image, plain response text, and word count. Use a select generated from `Array.from({ length: 19 }, (_, index) => index / 2)`. Route `WRITING` explicitly before the Reading fallback.

- [ ] **Step 7: Add Writing to the published library**

Allow `StartAttempt` to accept all three modules, default Writing to 3,600 seconds, render Writing metadata using task count, and retain existing objective cards unchanged.

- [ ] **Step 8: Run focused tests**

Run: `Set-Location frontend; npm test -- writing-runner.test.tsx writing-review.test.tsx word-count.test.ts`

Expected: all pass.

- [ ] **Step 9: Commit candidate and review UI**

```powershell
git add frontend/src/features/writing frontend/src/lib/api/attempts.ts frontend/src/lib/api/exam.ts frontend/src/features/exam/start-attempt.tsx frontend/src/app/library/page.tsx frontend/src/app/attempt/[attemptId]/page.tsx frontend/src/app/review/[attemptId]/page.tsx frontend/src/features/reading/reading-review.tsx frontend/src/features/listening/listening-review.tsx frontend/tests/writing-runner.test.tsx frontend/tests/writing-review.test.tsx
git commit -m "feat: add Writing runner and manual review"
```

### Task 7: Two-Mode Attempt History Frontend

**Files:**
- Modify: `frontend/src/lib/api/history.ts`
- Modify: `frontend/src/features/history/attempt-history-list.tsx`
- Modify: `frontend/src/app/history/page.tsx`
- Modify: `frontend/tests/attempt-history-list.test.tsx`

**Interfaces:**
- Consumes: Task 2 `AttemptList` with server-produced groups
- Produces: By skill and By test tabs without frontend score aggregation

- [ ] **Step 1: Expand fixtures and write failing history tests**

Test stable IDs and bands, tab switching, all individual attempts in By skill, exact-version grouping in By test, server-provided overall display, incomplete overall dash, selected latest module links, objective raw/unavailable-band copy, Writing Not graded, Continue/Review, and delete refresh.

- [ ] **Step 2: Run the history test and verify failures**

Run: `Set-Location frontend; npm test -- attempt-history-list.test.tsx`

Expected: schema and tab/group rendering failures.

- [ ] **Step 3: Extend the history Zod contract**

Model `HistoryItem`, `HistoryGroup`, and the response with `items`, `groups`, and `total`. Do not add a client-side overall helper.

- [ ] **Step 4: Refactor the history component into two views**

Keep delete state and confirmation shared. Render score copy by module and eligibility. Synchronize state when refreshed server props arrive so deleting a selected aggregate attempt updates both tabs from backend data.

- [ ] **Step 5: Run history tests**

Run: `Set-Location frontend; npm test -- attempt-history-list.test.tsx`

Expected: all pass.

- [ ] **Step 6: Commit history redesign**

```powershell
git add frontend/src/lib/api/history.ts frontend/src/features/history/attempt-history-list.tsx frontend/src/app/history/page.tsx frontend/tests/attempt-history-list.test.tsx
git commit -m "feat: add grouped attempt history views"
```

### Task 8: Visual Integration and Full Verification

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/tests/builder-route.test.tsx`
- Modify: `frontend/tests/listening-player.test.tsx`
- Modify: `frontend/tests/reading-instructions.test.tsx`
- Modify: `frontend/tests/reading-navigation.test.tsx`
- Modify: `frontend/tests/version-actions.test.tsx`

**Interfaces:**
- Consumes: all previous UI components and existing CSS tokens
- Produces: responsive, dark-mode-compatible Writing and history layouts

- [ ] **Step 1: Add responsive visual rules**

Extend existing builder/module tone selectors for Writing, add Writing task/editor/runner/review and history tab/group classes, use `min-width: 0`, wrapping grids, and textarea sizing that does not cause horizontal overflow.

- [ ] **Step 2: Run the complete backend validation suite**

Run: `Set-Location backend; uv run ruff check .; uv run ruff format --check .; uv run pytest -q; uv run alembic upgrade head --sql | Out-Null`

Expected: every command exits 0.

- [ ] **Step 3: Run the complete frontend validation suite**

Run: `Set-Location frontend; npm run lint; npm run typecheck; npm test; npm run build`

Expected: every command exits 0.

- [ ] **Step 4: Inspect the final diff and protected file**

Run: `git diff --check; git status --short; git diff -- frontend/next-env.d.ts`

Expected: no whitespace errors; `frontend/next-env.d.ts` remains only the pre-existing local modification and is not staged by this work.

- [ ] **Step 5: Commit final integration fixes**

```powershell
git add frontend/src/app/globals.css backend frontend/src frontend/tests docs/superpowers/plans/2026-09-20-ielts-scoring-writing-history.md
git commit -m "feat: complete IELTS Writing and score history flow"
```
