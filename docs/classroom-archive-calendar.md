# Classroom archives and interactive calendar

## Archive lifecycle and API

`POST /classrooms/{classroom_id}/assignments/{assignment_id}/restore` authenticates and locks the actor, classroom and scoped assignment. It requires `assignments.manage` and an active classroom. It changes only `ARCHIVED` to `ACTIVE`, clears `archived_at` and advances the content revision. Repeated restoration is idempotent.

The frozen TestVersion, assigned target, original schedule/cut-off, attempt limit, late policy, `classwork_hidden`, placements and academic history remain unchanged. Normal start/deadline/moderation checks still apply. The confirmation warns about elapsed due/cut-off times; teachers can then open assignment details and use the existing schedule editor.

Resources and topics use the existing PATCH endpoints with `{ "status": "DRAFT" }`. The UI requires confirmation and never republishes children or copies resource/file records. An archived parent remains hidden until the teacher explicitly restores and publishes it. Resources can be relocated through the existing topic selector; restoring a resource to DRAFT under an archived topic is safe because it remains hidden.

Permanent assignment deletion uses the existing DELETE endpoint. The owner explicitly approved deleting all linked student attempts, Full Mock sessions, scores, AI feedback, recordings, policy events, extensions, assignment notifications and learning-plan references, even when students have completed work. The confirmation states that this is irreversible. Shared TestVersion records and exam assets are not deleted. Remove from Classwork remains a separate, non-destructive alternative. Resource deletion also removes post/plan links automatically while retaining those posts/plans.

`DELETE /classrooms/{classroom_id}/assignments/{assignment_id}/classwork` extends the existing safe removal to canonical assignments which have no placement row. It sets `classwork_hidden`, removes only scoped Classwork associations, advances the content revision, and returns the normal Classwork snapshot. It accepts optional `expected_revision`, with the same `CLASSWORK_CHANGED` conflict as item removal. The original DELETE-by-item endpoint remains available. Restoring an assignment does not undo this deliberate removal; explicitly placing it in a topic does.

Content operations require `content.manage`; assignment operations require `assignments.manage`. Global administrator oversight remains read-only, including the former archive bypass. Students, unrelated teachers and revoked staff cannot perform these mutations. Archived classrooms reject writes. Alembic revision `20261028_0042` removes the DELETE restriction from the policy-event immutability trigger; UPDATE remains forbidden. Apply this migration before using permanent deletion. It does not delete existing data.

## UI synchronization

Archived groups remain collapsed initially, use semantic secondary surfaces, and retain accurate counts. One contextual menu provides restore/removal/deletion; assignment details are linked once in the row. Dialogs describe consequences and retain the existing keyboard/focus behavior. Duplicate mutations are guarded. A successful write followed by a failed reload offers a reload retry without repeating the write.

The workspace keeps a canonical assignment snapshot. Assignment mutations load Classwork and assignments once each, refresh authorized progress, and invalidate the calendar from assignment lifecycle/schedule metadata. Content-only mutations reload only Classwork. Topic disclosure survives these updates. A visited calendar remains mounted across tab changes, preserving selection, view and filter without repeating identical requests. Stream reloads through its existing authorized feed when reopened.

## Calendar data and dates

The default month grid runs Monday through Sunday and includes adjacent days. Month, seven-day week and list views use the same AVAILABLE, DUE and CUTOFF events. Filters apply to all views, selected-day details and month statistics. Monthly assignment counts deduplicate IDs. Staff see schedule statistics; only authorized API progress is shown for students. Assignment targets and the existing detail callback are reused.

Each visible grid covers at most six weeks, within the existing 93-day API limit. All 50-event pages are loaded sequentially under one AbortSignal. The first total bounds pagination. Changed totals, incomplete pages or duplicate event identities fail with Retry rather than silently displaying an incomplete month. Responses from aborted/older ranges cannot overwrite the current range. There is no per-day fetching. Day cells render at most three event chips plus an overflow control; the selected-day panel exposes the complete day.

Date-only values are constructed from local year/month/day components. Day and month navigation uses calendar arithmetic, not fixed 24-hour additions. API bounds are local midnights converted to UTC, with an exclusive end; grouping uses the viewer's device timezone. This retains student extension semantics supplied by the backend. Date buttons distinguish today from selection and support arrows, Home and End. Details stack below the grid on smaller screens; mobile week view stacks seven day sections. Colors come from the existing light/dark tokens.

## Verification and limits

Focused tests cover real ASGI route serialization without a server/database, scoped capabilities, restoration idempotence, frozen metadata/schedule preservation, scoped hard-deletion references, safe removal, DRAFT restoration, duplicate-write guards, canonical refresh counts, retained calendar selection, pagination, cancellation, stale responses, filters, summary counts, keyboard navigation and CSS layout contracts at 375/768/1024/1440px. Date arithmetic was checked in the local timezone, America/New_York and Pacific/Honolulu.

The measured pagination fixture loads all 123 events with offsets 0, 50 and 100. A workspace regression asserts one Classwork reload and one assignment-list reload per restoration; revisiting Calendar does not fetch again. These are deterministic request/behavior checks, not browser latency measurements.

No browser, local development server, full stack, production build, Playwright/Cypress, full test suite or live AI call was launched. The later hard-delete repair applied only migration `0042` after the user's explicit approval, with a read-only check of the resulting trigger; no real assignment was deleted for verification. Visual browser verification and PostgreSQL integration execution remain unverified. Remote CI waiting was deferred at the user's request.

The installed Taste Skill and UI/UX Pro Max informed compact contextual actions, consequence-specific confirmations, clear selection, semantic data marks and responsive detail placement. The user's approved navy palette, typography and existing shell take precedence over the skill's alternative style suggestions. No redesign, charting/calendar dependency or additional preference context was introduced.

## Changed areas

- Backend: assignment/classwork routers and services; `test_classroom_archive_unit.py`.
- Frontend clients: `classrooms.ts`, `classroom-content.ts`.
- Archive UI: assignment list; Classwork panel, sections and rows; archived assignment actions; content messages; workspace synchronization.
- Calendar UI: existing entry point, focused panel, date/data helpers, localized messages and calendar stylesheet.
- Tests: assignment scheduling, Classwork, workspace, calendar date/CSS contracts.

The companion homepage commit adds guest VI/EN and target-theme icon controls through the existing PersonalizationProvider. It retains `ielts-locale`, `ielts-theme` and accent persistence, account precedence and deterministic SSR/bootstrap. Its focused tests cover blocked storage, hydration, authentication links, no guest preference requests, and retained scene identity/manual pause/scroll. Existing dark gradients and text palette were retained; CTA shine and header registration colors now adapt to dark mode.
