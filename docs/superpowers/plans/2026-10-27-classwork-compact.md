# Compact Classwork implementation

Scope: implement the supplied Classwork redesign on main. Preserve BandPilot tokens, FastAPI APIs, capabilities, P2 progress, resource readers, revision conflicts and assignment detail/history navigation. No backend/schema changes.

The screen answers: which topic and learning activity should I open next? Real topic titles and compact resource/IELTS rows carry the hierarchy. Retain the existing achromatic-ledger composition; this component change needs no new draw or global theme.

1. Add focused regression tests for grouping/counts, disclosure state, progress metadata, historical navigation, permissions and revision-aware moves. First verify the structural regressions fail.
2. Normalize resolved content once: deduplicate canonical assignments, retain unplaced records, separate archived assignments/resources and omit inaccessible references from counts. Do not create database topics.
3. Replace nested material disclosures with one controlled topic button/region. Initially open only the first populated published topic; retain user choices through refreshes. Expand and focus hash targets once per navigation.
4. Replace embedded ProgressSummary with ClassworkAssignmentMeta using the existing progress context. At most three metadata parts, effective due date, useful finite attempt counts, no invented scores. Keep the full detail surface unchanged.
5. Preserve contextual authoring, resource readers, drop targets and keyboard Move/reorder alternatives. Use shrinkable rows, wrapping titles, shared theme tokens and visible focus at 375/768/1024/1440 source breakpoints.
6. Run targeted Vitest files, TypeScript, scoped ESLint, Taste source lint and git diff --check; inspect task diff, update classroom documentation, commit and push main without force. Continue CI monitoring for the resulting SHA.

Skill guidance: Taste app-screen lists, one quiet boundary and compact identity/subline/action rows; UI/UX Pro Max verified local matches for visible focus, unobscured focus, dragging alternatives and stable React keys. The local progressive-disclosure search and narrower retry did not return a verified matching guideline; use the supplied two-level design and native button/region semantics. Preserve actual counts and API status rather than inventing fixture content in production.

Verification limits: browser inspection, viewport screenshots, builds, local E2E, full suites and full stack launches are explicitly excluded. Responsive/theme findings are source-level only; do not assign a visual screenshot score.
