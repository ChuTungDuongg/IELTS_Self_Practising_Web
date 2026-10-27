# Classwork visual implementation report

## Reference and design decisions

- Read the supplied task, `design-taste-frontend` app-screen guidance, `ui-ux-pro-max`, frontend AGENTS guidance and bundled Next.js client-component documentation.
- Inspected the user's approved screenshot at `C:/Users/Admin/AppData/Local/Temp/codex-clipboard-d96b2861-114f-4f9d-88da-2acbcce89e64.png`.
- The supplied composition governs this update: outlined blue book tile, right content search, folder topic header, centered dashed topic empty state, warm archive container, count badge, scoped archive search and compact direct row actions. Existing BandPilot typography and semantic light/dark tokens remain authoritative. No alternate random design direction was substituted.
- Screen question: which classroom resources, assignments and archived work can I inspect or act on? All records and totals derive from authorized API data. No sample content was introduced.

## Implementation

- Added accent/case-insensitive Vietnamese topic/resource/assignment search, including `Đ/đ`. A topic match preserves all its children; a child match keeps its parent. Search opens matching groups, allows disclosure interaction and restores previous disclosure choices when cleared.
- Added separate assignment/resource archive search, preserving the archived group's total count and other classroom topics.
- Added shared folder/card/empty-state/archive styling with responsive search fields, compact action layout, date metadata and localized notices. Narrow student rows place dates and details on separate rows.
- Teachers see direct Restore, Delete and View details; the less-used Remove from Classwork action stays in the desktop overflow. Mobile mounts one contextual control set, without duplicated buttons. Dialog state remains outside the responsive layout.
- Observers receive details and neutral empty states without mounting mutation controls. Students retain their authorized history/result links. The root workspace supplies capability-safe flags and hides the panel's duplicate standalone create menu using `showCreateMenu={false}`.
- Reused restore/delete/reference-removal APIs and confirmations. Protected-history deletion explains the reason and surfaces safe removal. Expired deadlines are warned about and never extended. Saved mutations retry synchronization without repeating the write. Resource restoration remains DRAFT until explicitly published.

## Files

- `frontend/src/features/classrooms/content/classwork-panel.tsx`
- `frontend/src/features/classrooms/content/classwork-section.tsx`
- `frontend/src/features/classrooms/content/classwork-item-row.tsx`
- `frontend/src/features/classrooms/content/archived-assignment-actions.tsx`
- `frontend/src/features/classrooms/content/archive-action-layout.tsx` (new)
- `frontend/src/features/classrooms/content/classwork-search.ts` (new)
- `frontend/src/features/classrooms/content/classwork-icons.tsx` (new)
- `frontend/src/features/classrooms/content/content-messages.ts`
- Classwork-scoped sections of `frontend/src/features/classrooms/content/classroom-workspace.css`
- `frontend/tests/classwork-compact.test.tsx`

## Verification

- Red phase: focused Classwork tests showed five expected failures for missing search, observer archive metadata, direct teacher controls and compact action composition.
- `npx vitest run tests/classwork-compact.test.tsx tests/classroom-content.test.tsx --reporter=dot`: **67 passed**, two files.
- Scoped ESLint over the changed Classwork TS/TSX files and focused test: **passed**.
- `git diff --check`: **passed** (Git emitted existing line-ending conversion notices).
- No servers, browser, screenshots of the implemented UI, browser tests, production build, full test suite or persistent processes were run. Visual fidelity, exact responsive geometry and composed contrast in both themes remain unverified in a real browser, as required by the user's execution restrictions.
- No commit or push performed by this worker; integration/delivery belongs to the parent task.
