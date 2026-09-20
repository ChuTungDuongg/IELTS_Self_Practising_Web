# IELTS Scoring, Writing, and History Design

**Date:** 2026-09-20

**Status:** Approved

## Purpose

Extend the existing IELTS practice application without replacing its Next.js → FastAPI → PostgreSQL architecture. The change adds backend-owned IELTS band scoring, a complete Writing builder and attempt flow, persistent manual Writing grading, and two coordinated history views while preserving all existing Reading and Listening behavior.

## Product Rules

- PostgreSQL remains authoritative. React never owns scoring or domain validation.
- Published `TestVersion` records remain immutable and historical attempts remain attached to their frozen version.
- Reading and Listening raw scores remain visible alongside official bands.
- Reading and Listening receive an official band only when `max_score == 40`.
- Reading and Listening use the same exact application product-rule table:

  | Raw score | Band |
  |---|---:|
  | 39–40 | 9.0 |
  | 37–38 | 8.5 |
  | 35–36 | 8.0 |
  | 33–34 | 7.5 |
  | 30–32 | 7.0 |
  | 27–29 | 6.5 |
  | 23–26 | 6.0 |
  | 20–22 | 5.5 |
  | 16–19 | 5.0 |
  | 13–15 | 4.5 |
  | 10–12 | 4.0 |
  | 7–9 | 3.5 |
  | 5–6 | 3.0 |
  | 3–4 | 2.5 |
  | 0–2 | no official band (`null`) |

- Writing never receives an objective raw or maximum score. Its band is nullable until manually graded.
- Writing manual bands range from 0.0 through 9.0 in 0.5 increments.
- The project overall is the mean of exactly Reading, Listening, and Writing bands. It exists only when all three bands exist and is rounded to the nearest 0.5 using decimal half-up behavior. An exact quarter-band tie rounds upward for these non-negative scores.
- Speaking and automated Writing scoring remain out of scope. The existing `WritingScoringProvider` protocol stays intact for future work.

## Existing Architecture Findings

The Reading and Listening builders share a `BuilderVersion` DTO and the generic module creation endpoint. Their question behavior is centralized in matching frontend and backend registries. All requested Listening templates are already registered and covered by editors, exam renderers, review renderers, validators, evaluators, and tests, so no Listening type will be recreated.

`WritingTask`, `AttemptWritingResponse`, `WRITING_TASK_IMAGE`, backend and frontend word counters, and the Writing scoring provider protocol already exist. Writing tasks are already cloned by the version service, but builder payloads and candidate payloads do not expose them. `WritingTask` also lacks an explicit asset relationship.

The attempt service currently scores only explicit submissions. Timer expiry and AFK interruption finalize without scoring. Review routing handles Listening specially and otherwise assumes Reading. History is a flat list without stable test/version identifiers or band scores.

## Persistence and Migration

Add a new Alembic migration after revision `20260919_0006`. It adds nullable `attempts.band_score NUMERIC(2,1)` and preserves all existing score columns and data. The downgrade drops only this new column.

The SQLAlchemy `Attempt` model stores the value as `Decimal | None`; public Pydantic DTOs expose `float | None`. No score-source column is added because it is not required for the current manual workflow.

Add `WritingTask.image_asset` as a relationship using its existing `image_asset_id` foreign key. No parallel Writing tables are introduced.

## Scoring Domain

Create a focused backend scoring module containing:

- `listening_raw_to_band(raw_score: int, max_score: int) -> float | None`
- `reading_raw_to_band(raw_score: int, max_score: int) -> float | None`
- `round_to_half(value: Decimal) -> Decimal`
- `project_overall_band(reading, listening, writing) -> float | None`

Both raw-to-band functions delegate to the same immutable product-rule table but remain distinct public functions so Reading and Listening policy can diverge later without caller changes. Inputs outside `0 <= raw_score <= max_score` raise `ValueError`; a non-40 maximum returns `None`; raw scores 0–2 return `None`.

The attempt service assigns an objective band after computing raw and maximum scores. It explicitly clears all three score fields for Writing. Backend-triggered finalization is made asynchronous so objective scoring occurs before a timer-expired or AFK-interrupted attempt becomes final.

## Writing Builder Domain

`BuilderVersion` gains a `writing_tasks` list on each module. A builder task contains stable ID, fixed task number, fixed order index, prompt, optional image ID and image metadata, recommended minimum words, and recommended duration.

Creating a `WRITING` module through the existing generic module endpoint atomically creates:

- Task 1: number 1, order 0, 150 words, 1,200 seconds, optional image.
- Task 2: number 2, order 1, 250 words, 2,400 seconds, no image.

The Writing task update API exposes only editable fields. Task number and order cannot be changed through the API. Task 1 may reference one `WRITING_TASK_IMAGE` owned by the current draft version. Task 2 rejects any non-null image ID. Replacement and removal reuse existing unreferenced-asset cleanup behavior.

Drafts may be incomplete. Publishing validation treats missing tasks, blank prompts, and nonstandard readiness values as warnings where consistent with existing partial Reading/Listening policy. Invalid task identities, duplicate task numbers/orders, Task 2 images, wrong asset types, cross-version newly attached assets, and Writing tasks owned by non-Writing modules are blocking structural errors. At least one meaningful module remains required by the existing version validator.

Cloning continues to copy Writing tasks and preserve image references using the repository’s existing shared-asset semantics. New attachments to a cloned draft must still be assets uploaded for that draft.

## Writing Attempt API and Lifecycle

The generic active exam DTO gains `writing_tasks`. Candidate task rows include prompt, optional Task 1 image metadata, minimum words, recommended duration, saved content, and authoritative saved word count. They contain no answer keys.

`PUT /attempts/{attempt_id}/writing/{writing_task_id}` accepts plain text content. The backend:

1. locks and synchronizes the attempt;
2. requires an in-progress Writing attempt;
3. verifies that the task belongs to the attempt’s exact version and Writing module;
4. computes word count with the existing backend helper;
5. upserts `AttemptWritingResponse`;
6. updates `last_active_at`; and
7. records `WRITING_UPDATED` with the task ID in event metadata.

The Writing runner uses the existing timestamp-derived timer. Local word count is display feedback only. It restores server responses on load, debounces autosave, provides an immediate visible Save action, and saves the active task successfully before calling the standard submit endpoint. A failed final save prevents submission and shows a retryable error.

Writing submission finalizes through the normal attempt state machine with `raw_score`, `max_score`, and `band_score` left null.

## Writing Review and Manual Grading

Add a Writing-specific review payload and route. It contains every Writing task in order, prompt, Task 1 image metadata, saved response or an empty response, and server word count. It does not contain objective answer structures.

`PUT /attempts/{attempt_id}/writing-score` accepts a constrained band. The backend requires:

- a Writing attempt;
- a status other than `IN_PROGRESS`;
- a value from 0.0 through 9.0; and
- a multiple of 0.5.

The score persists to `Attempt.band_score`. The review UI provides a constrained selector, explicit Save control, success/error state, and immediate display of the saved band. The protocol for future automated scoring remains unchanged.

## History Contract

Keep one `/history` endpoint and extend its response rather than adding duplicate endpoints. It returns:

- `items`: every attempt in current reverse-chronological order;
- `groups`: backend-produced aggregates keyed by exact `test_version_id`; and
- `total`.

Each item includes `test_id`, `test_version_id`, title, version number, module, status, timestamps, raw score, maximum score, and band score.

For each test/version group, the backend selects the latest attempt whose status is not `IN_PROGRESS` for each module, ordered by `finished_at` and then `started_at`. Older attempts remain in `items`. The group exposes the selected Reading, Listening, and Writing items plus the backend-computed three-skill overall.

The frontend renders two tabs over this single payload:

- **By skill:** all individual attempts, with Continue for active attempts, Review for finalized attempts, deletion, official-band-unavailable copy for non-40 objective attempts, and Not graded for Writing without a band.
- **By test:** one card per exact test version, selected module scores, overall only when all three bands exist, and links to the selected individual attempts.

After deletion, the page refreshes from the backend so group selection and overall values are never recomputed independently in React.

## Frontend Integration

Enable `writing` in `BuilderWorkspace`, routing, overview metrics, and preview routing. Add focused Writing builder, runner, and review components rather than expanding Reading/Listening components with scattered module conditionals.

The practice library includes published Writing modules and starts them through the existing attempt start API. Writing uses the same 60-minute default timer infrastructure and the existing timer presets.

Draft preview renders both task prompts, Task 1 image when present, and each task’s word/duration recommendations. It has no candidate response editor and no Task 2 image placeholder.

New styles extend the existing visual tokens, controls, cards, module tones, dark mode, and responsive breakpoints. The long-form textarea uses a comfortable minimum height and resizes vertically without page-level horizontal overflow at 390, 768, 1024, and 1440 pixels.

## Compatibility and Error Handling

- Existing Reading and Listening payload fields remain unchanged; new fields are additive and default to empty/null in frontend schemas.
- Published content cannot be mutated through Writing endpoints.
- Active candidate payloads never expose answer keys.
- Save, upload, grading, and delete errors remain retryable and use existing notice/dialog styles.
- The existing local `frontend/next-env.d.ts` modification is preserved and excluded from task edits.
- No copyrighted exam content or new runtime dependency is added.

## Test Strategy

Tests are added before or alongside each implementation slice:

1. Pure scoring table boundaries, invalid inputs, non-40 behavior, decimal half-up rounding, and three-skill overall requirements.
2. Migration/model/schema serialization and objective finalization, including backend-triggered finalization.
3. Writing module initialization, task validation, asset ownership/type checks, cloning, and version validation.
4. Writing response upsert, authoritative word count, resume payload, submission semantics, and manual grade validation.
5. History identifiers, selected latest finalized attempts, band serialization, and backend overall calculation.
6. Writing builder, runner autosave/explicit save, review grading, draft preview, routing, and both history tabs.
7. Full backend tests and lint, full frontend tests, TypeScript typecheck, ESLint, and production build.

