# Classroom workspace UX

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Classroom workspace UX. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../frontend/src/features/classrooms).
> Đọc cùng [current module/guide](modules/classrooms.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

The redesign keeps BandPilot global navigation, fonts, accents and semantic light/dark tokens. Stream, Classwork, Assignments and Calendar separate learning workflows; People/Gradebook/Analytics follow classroom capabilities, and My Progress shows personal classroom progress. Existing notification post links and assignment deep links are preserved.

## Dual-skill design audit

Both installed skills were read and applied: `.agents/skills/ui-ux-pro-max/SKILL.md` and `.agents/skills/design-taste-frontend/SKILL.md`, including Taste's app-screen reference. Local UI/UX Pro Max searches executed:

- `education LMS SaaS classroom productivity dashboard --design-system --variance 2 --motion 2 --density 7 -p "BandPilot Classroom"`
- `dashboard navigation information hierarchy --domain ux`
- `progressive disclosure form complexity --domain ux`
- `keyboard focus modal dialog --domain ux`
- `responsive dashboard layout --stack nextjs`
- `accessible data tables --domain ux`

The search recommended Minimalism/Swiss styling and warned against hidden assignments, cluttered navigation and poor mobile behavior. Its generic landing-page layout and playful education fonts did not fit the existing adult IELTS app, so BandPilot's brand and working-screen architecture take precedence. No dependency, animation framework, global MASTER.md or second theme was added.

Taste's app direction is `achromatic-ledger`, seed 2734, preserving palette/type. The combined direction is Minimalist Editorial Education SaaS: compact header, one content plane, flat surfaces, aligned numeric tables and contextual controls. Actual topics, IELTS assignments, deadlines and separate skill records supply the product identity. Metrics are text rather than decorative tiles; empty states do not invent data.

## Workflows

The header shows the classroom, actual teacher/member count and status. Its authorized Create menu opens announcement, topic, resource or assignment creation directly. Settings/management and archive sit in the secondary menu. Archived rooms remain readable with mutation controls suppressed.

Classwork defaults to content. Add content opens one focused topic/resource/assignment-placement workflow only after selection. No eligible assignment produces an explicit empty state and an authorized creation action, instead of a select containing only a dash. Unplaced activities use a secondary grouping; no fake topic or empty grouping appears. Labels use Topic / Chủ đề học while backend Section names stay unchanged.

Topics collapse and expose one contextual management menu. Resource edit/publication/archival/movement controls are disclosed. Native drag-and-drop and keyboard alternatives retain the P1 revision-aware APIs. Conflicts reload the current order and explain how to retry.

### Compact Classwork follow-up

Classwork now renders one topic button with an accurate combined item count and one controlled content region. Only the first published topic with active content starts open; empty, unplaced and historical groups start closed. Stable topic IDs preserve disclosure choices across content/progress refreshes. Section, assignment, resource and item hash navigation expands the target group and focuses its heading or row. Existing assignment query links still open the assignment detail tab.

Resolved resources and canonical assignments are normalized once, with duplicate and unresolved references excluded from counts. Archived assignments appear once in a separate collapsed history group, including assignments absent from the Classwork placement snapshot. Authorized archived resources have their own collapsed group. Canonical unplaced active assignments remain movable through the existing placement API. No synthetic section is persisted.

Before: topic heading → always-open material disclosure → full ProgressSummary per assignment. After: topic button/count → compact resource or assignment rows → existing reader/detail/result workflow on demand. ClassworkAssignmentMeta uses P2 provider data and at most three parts: type/skill, current status and meaningful effective due date or finite used starts. It never invents scores, repeats hard cut-offs or renders unlimited zero-use counters. ProgressSummary remains unchanged for other screens. Staff retain contextual editing, publication, archive, revision-aware reorder and Move controls, including collapsed-topic drop targets.

This follow-up retains Taste's existing achromatic-ledger composition without a redraw or new theme. App-screen guidance permits the single quiet topic border and row separators. UI/UX Pro Max local matches informed stable keys, keyboard focus and alternatives to dragging. The disclosure search and retry did not produce a verified matching dataset entry; the supplied design and button/region semantics are used explicitly. Focused frontend verification passed 69 tests, including 29 new compact-Classwork cases; TypeScript and scoped ESLint passed. The P2 concurrency fixture was also isolated: its 21-test lifecycle/domain/listing sequence passed. Browser, viewport and rendered-contrast checks remain excluded by the user's execution limits.

Stream groups filters and New post, emphasizes titles/type/author/localized dates, resolves activity titles from real assignment metadata and groups deadlines. Comments and secondary actions are disclosed. Discussion moderation uses its own capability independently of content authorship.

Assignments use a compact single list, closed-by-default creation, progressive schedule settings and the existing progress/continue/results/monitoring/extensions flows. Archive actions use the existing confirmation dialog. Calendar retains the real P2 deadline agenda. People hides settings/invite forms until requested and retains distinct staff/student/invitation surfaces.

Gradebook has a sticky identity column, internal scrolling, CSV export and student-list alternative. Profiles retain canonical result/grading links and add authorized analytics/plans. My Progress and Analytics use the same flat metric strip, separate skill histories, evidence tables, real practice links and honest missing-data states.

## Accessibility and responsiveness

Tabs have associated tabpanels, selected state, roving focus and Arrow/Home/End support. Native disclosures are keyboard operable. Action menus close on Escape, restore focus to their summary and stay open for embedded destructive confirmations. Existing confirmation dialogs trap and return focus; creation editors focus their first field. Loading/error/retry and aborted stale requests prevent misleading state. Pending mutations disable repeat actions and retain conflict messages.

There are no permanent sidebars. Tabs and tables scroll within their own bounds. Shrinkable columns, wrapping titles and 1024/768/480 rules cover desktop/tablet/narrow-phone layouts. Mobile form text stays 16px and touch controls at least 44px tall. Focus, textual status, labels, reduced motion and theme tokens are preserved. Charts have dated textual history alternatives.

## Executed checks and limits

### Safe removal, resource activities and teacher-directed assignments

Classwork keeps the compact topic/row structure described above. Its contextual menus now distinguish Delete resource, Delete topic and Remove from Classwork, with consequence-specific confirmations and repeat-submit protection. Post menus use the same accessible icon disclosure. Content management and assignment management are checked separately; students and default Teaching Assistants cannot delete managed learning content, and Admin oversight does not imply authorship. Archived classrooms remain read-only.

Deleting a topic transactionally moves its contents to the unplaced group and advances the classroom revision. Published resources under a hidden topic stay hidden after the topic is removed. Resource deletion rejects **any** retained post or learning-plan reference, including historical references, with `RESOURCE_REFERENCED`; staff must clean up an authorized reference or archive the resource. Safe file removal commits database changes first, rechecks durable references, then removes the unreferenced binary. A filesystem cleanup failure is logged and can leave an inaccessible orphan for maintenance; it does not undo a committed deletion. Deleted posts retain their comments and notification provenance through `deleted_at`, leave the feed, and old links show an unavailable-content message.

Removing an assignment placement preserves its canonical assignment, schedule, attempts, sessions and grades. `classwork_hidden` plus the snapshot's `removed_assignment_ids` prevent the canonical unplaced fallback from immediately restoring it; authorized reattachment clears this state. Canonical DELETE is intentionally conservative: attempts, sessions, policy audit, extensions, notifications or learning plans block it with `ASSIGNMENT_HISTORY_PROTECTED`. Current assignments normally have policy audit and should use Archive or Remove from Classwork; the UI does not disguise either action as Delete.

Stream derives `RESOURCE_ACTIVITY` from the same resource and placement records. Publication timestamps are backfilled for existing published resources; drafts, hidden parent topics and archived/deleted content obey the existing visibility rules. One bounded post/assignment/resource UNION, kind-aware cursor and React identity preserve ordering and pagination. The hydration queries recheck current classroom/status/topic visibility, so a stale selected key cannot reveal newly hidden resource content. A resource attached to a published, undeleted post is suppressed as a standalone entry in the mixed feed; the resource filter still shows its canonical activity. Readers use the existing authenticated file route. Reordering and metadata edits create no resource notifications or copied posts.

New HTTP assignments require an explicit immutable `target`: MODULE plus full module/focused unit, or FULL_MOCK. The teacher chooses a logical Test, a valid skill, scope and a real unit from classroom-authorized published metadata. Supported focused units reuse Reading Passage, Listening Part, Writing Task and Speaking Prompt engines; Speaking Part is not offered. Full Mock requires the existing four modules and positive durations. Missing, foreign or incompatible units are rejected server-side. `require_assignment_start()` compares the target inside the existing start transaction before P2 policy checks; changed module, scope, unit or root mode receives `ASSIGNMENT_TARGET_MISMATCH`. Full Mock remains one root session/start, and native scoring, timers and human-final provenance are unchanged.

Students see one assigned target and Start action, retaining valid presentation choices, Resume and Results. Target context accompanies Classwork, Stream, monitoring, both Gradebook views and learning analytics. Recommendations match the assigned skill and focused question/task context. Legacy null-target assignments retain flexible starts and frozen historical references. A different target requires a replacement assignment; the database trigger rejects edits even before student work starts.

New APIs under `/classrooms/{id}`: DELETE `posts/{id}`, `resources/{id}`, `sections/{id}`, `items/{id}` (placement removal) and `assignments/{id}` (protected canonical deletion); GET `assignment-versions/{id}` supplies safe, scoped target options. Classwork DELETE clients send `expected_revision` and handle conflicts through the existing refresh flow. Migrations `20261027_0040` and `0041` add removal/publication metadata and validated object-or-null target storage with an immutable-target trigger. Both were applied to the actual local database, now at `0041`; an isolated empty database passed upgrade → downgrade to `0039` → upgrade, without downgrading the application database. Downgrades reject retained removal/target state rather than silently discarding it.

### Technical revision presentation

Ordinary Library, test detail, Skill Practice, Classroom assignment builder/display, History, student/admin attempt summaries and Analytics no longer show technical TestVersion numbers. Discovery groups by logical Test and chooses the highest eligible published number, with a stable ID tie-breaker, **only among versions already returned by the authorized workflow**. Draft, archived or unapproved revisions cannot win that selection. Explicit historical detail, start, review and deletion routes keep their original frozen IDs. Builder and moderation retain revision operations; technical numbers are available in collapsed advanced revision history rather than prominent labels. Transfer contracts, counters, database relations and score comparability remain intact.

Taste's app-screen list hierarchy and quiet surfaces were retained. UI/UX Pro Max guidance informed visible focus, labeled icon menus, keyboard disclosure/Move alternatives, progressive forms, retry states and 44px controls. No global theme or dependency changed. Final verification remains focused unit/integration tests, TypeScript, scoped ESLint/Ruff and source-level accessibility/responsive review; no browser, E2E, build, full suite, full stack or live AI was run. Taste source lint reported zero failures; warnings are existing overlay shadows, a `box-shadow: none` false positive, the comment `unlock` key, date padding and missing-value dashes. CI monitoring was disabled at the user's request.

The final 16-file frontend selection passed **211 tests**, with **5 additional Builder route tests** passing (**216 distinct cases**); the four changed Classroom files also passed their **47-test** follow-up after the last touch-target/target-label adjustments. The Reading E2E source selector was updated to the human-facing Draft link without executing E2E. The ten-file backend selection passed 158 cases; its new legacy-deletion test initially expected 200 from an existing 201 creation endpoint, then passed after correcting that expectation (**159 distinct cases verified**). TypeScript, scoped ESLint, all 27 changed Python files' Ruff lint/format, migration round-trip and `git diff --check` passed. The P2 real-connection race now uses an isolated, migrated disposable database so it cannot leave committed fixtures in the shared test database.

Verification uses focused Vitest component/API/CSS tests, TypeScript, scoped ESLint, PostgreSQL authorization/result tests and `git diff --check`. Taste app source lint reported **0 FAIL**. Reviewed warnings: real floating menu shadow is intentional, `box-shadow: none` is a scanner false positive, `unlock` is the existing key for opening comments, zero-padding formats dates and dashes represent missing values.

On 2026-10-27 the seven focused frontend files passed **78 tests**, plus TypeScript and scoped ESLint. The eight-file backend regression run passed 99 tests; its remaining query-count test passed after correcting fixture insert order. The final P4-only run passed all **14 tests**, and the real two-connection staff race passed again after making the database safety guard compatible with CI. All 39 task-related Python files passed scoped Ruff lint/format. Fresh 0038/0039 migration round-trip and the actual local 0039 head/API 200 check passed.

The user explicitly prohibited browser launches, screenshot/viewport inspection, E2E, production builds, full suites and live AI calls. None ran. Responsive and theme review is source-level; rendered contrast, pixel layout and actual browser interactions still need manual review. No pixel-perfect or browser-verified claim is made.
