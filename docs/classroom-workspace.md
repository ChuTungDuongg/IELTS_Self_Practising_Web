# Classroom workspace UX

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

Verification uses focused Vitest component/API/CSS tests, TypeScript, scoped ESLint, PostgreSQL authorization/result tests and `git diff --check`. Taste app source lint reported **0 FAIL**. Reviewed warnings: real floating menu shadow is intentional, `box-shadow: none` is a scanner false positive, `unlock` is the existing key for opening comments, zero-padding formats dates and dashes represent missing values.

On 2026-10-27 the seven focused frontend files passed **78 tests**, plus TypeScript and scoped ESLint. The eight-file backend regression run passed 99 tests; its remaining query-count test passed after correcting fixture insert order. The final P4-only run passed all **14 tests**, and the real two-connection staff race passed again after making the database safety guard compatible with CI. All 39 task-related Python files passed scoped Ruff lint/format. Fresh 0038/0039 migration round-trip and the actual local 0039 head/API 200 check passed.

The user explicitly prohibited browser launches, screenshot/viewport inspection, E2E, production builds, full suites and live AI calls. None ran. Responsive and theme review is source-level; rendered contrast, pixel layout and actual browser interactions still need manual review. No pixel-perfect or browser-verified claim is made.
