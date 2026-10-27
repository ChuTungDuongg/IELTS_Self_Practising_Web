# Classroom Newsfeed

The approved Stream image is implemented within the existing Classroom workspace. Desktop widths from 1100px use a fluid 69/31 feed/sidebar split with an 18px gap, compact rounded navy surfaces in Dark Mode, type badges, one author avatar, restrained metadata, and assignment/resource previews. Tablet stacks the dashboard below the feed in two columns; mobile uses one column, wrapped filters and 44px controls. Shared BandPilot tokens preserve Light Mode, personal accents, focus indicators and reduced motion. The global navigation, Classwork, Assignments, Calendar and exam runners retain their existing designs.

## Interactions and real data

The compact composer expands the existing `PostComposer`. Announcement and Discussion actions preselect their supported API kinds. File and Link actions reuse `ResourceEditor` and existing Classwork endpoints, without creating a second post for a canonical resource activity. The header announcement action opens, scrolls and focuses the same composer. Draft, publish, editing and attachments remain supported. Successful mutations refresh the feed without a full page reload; a failed read after a successful write offers a loading retry without repeating the mutation.

Announcement/discussion cards retain edit, publish/unpublish, pin/unpin, lock/unlock, archive, delete and lazy comment threads, according to capabilities. Comment counts come from the backend; after commenting, only that post's authoritative count is read, preserving previously loaded feed pages. Assignment previews use the current assignment context for the real title, exact target and due/cut-off timestamps. Their callback opens the existing assignment workflow, including authorized student starts/resumes/results elsewhere. Resource previews use real filenames, sizes or safe HTTP link hosts and the existing authenticated reader/download flow. No storage keys or public asset bypasses are introduced.

The screenshot's reactions and online presence have no persisted data source in the existing application. They are omitted. No sample names, engagement counters, dates, scores or classroom totals are substituted. Author fallback initials use actual accessible names; a neutral Author label avoids guessing a classroom staff role from a global USER role. Times use the existing GMT+7 project formatter for consistent server/client rendering.

## Search and pagination

The existing feed endpoint adds optional `search` (at most 200 characters) and `pinned_only`. Search is case-insensitive and Vietnamese accent-insensitive, including combining marks. Parameterized PostgreSQL expressions use native functions without extensions/migrations. LIKE wildcard characters are escaped. Matching covers post titles/body, assignment title/instructions/canonical test title, and resource title/description/body/filename/URL. Existing publication/topic visibility and canonical attachment de-duplication are retained.

The bounded UNION still returns at most 20 entries plus a next-page sentinel. Its keyset remains `(pinned, created_at, kind, id)`. Cursors now bind normalized search and pinned scope in addition to classroom/status/kind; changing the query rejects an unrelated cursor. Existing cursors retain empty-search/unpinned defaults. The UI debounces search by 280ms, resets pagination on query changes, aborts obsolete requests and ignores late deep-link hydration. All and type/pinned chips use the backend query rather than filtering a loaded page.

## Sidebar sources

| Section | Source |
| --- | --- |
| Enrolled students | Authorized Classroom `active_member_count` |
| Active assignments | Existing complete assignment snapshot, ACTIVE records only |
| Upcoming deadlines | Assignment timestamps for staff; batched authorized progress with effective extensions for students |
| Shared resources | Existing complete Classwork snapshot, PUBLISHED resources in published/unassigned topics |
| Members | Classroom teacher plus up to three already loaded active member identities, only with roster permission |
| Recent activity | Three newest canonical entries from the current loaded feed view, explicitly labeled as that scope |

There is no per-metric request or extra roster request. Students do not request the staff roster. Completed/archived/closed student work and undated assignments do not appear as upcoming. Due dates and hard cut-offs stay distinct; timestamps are never automatically extended. The minute-aligned display clock updates the sidebar only and performs no network polling. Sidebar links use existing Classroom navigation; Recent Activity can reset feed filters or focus an existing entry.

Stream state stays mounted after first visit so filter, loaded pages and unsaved editor survive tab changes. Returning after Classwork revisions or assignment lifecycle changes invalidates the feed once. Locale changes and unchanged tab revisits do not refetch it. Comments, private file readers and monitoring remain loaded on demand.

## Permissions and verification

`classroomPermissions()` and FastAPI remain authoritative. Owner/co-teacher authoring uses actual capabilities. Students read published content and comment only through existing membership/deadline rules. Admin Observer has no composer, post mutations, comment submission, membership changes or assignment-management actions, including when stale frontend authoring flags are supplied. The existing observer label and read-only backend denials remain intact.

The main focused selection passed 161 frontend tests in 12 files, plus 73 DB-free backend tests (69 search/cursor/observer cases and four existing feed schema/route/cursor/tombstone cases). TypeScript, scoped ESLint, scoped Ruff lint/format and diff whitespace checks passed. Taste's source-only checker reported zero failures; its single warning matches the existing `unlock` translation key for opening comments. Focused tests cover sidebar data sources, effective deadlines, permission boundaries, search-bound pagination, cancellation, stale deep links, composer workflows, duplicate prevention, retained feed state, comments, resource readers, localization and CSS contracts at 375–1440px.

A fictional PostgreSQL integration case is included for Vietnamese search, visibility and multi-page pinned results. It was not executed against the development database. No browser, dev server, production build, E2E/full suite, database migration/reset, synthetic production data or live AI call was launched. Rendered spacing, contrast, actual 375px overflow and screenshot-level fidelity remain unverified. The approved image overrides the skills' alternative visual directions; both installed design skills informed the source review.

Changed areas: feed router/repository/service and native search helper; Stream entry/layout, composer, cards/previews/sidebar/styles; existing post/resource editor retry handling; Classroom page/workspace identity and navigation; typed feed client; focused frontend/backend tests. No new dependencies or persistence model were added.
