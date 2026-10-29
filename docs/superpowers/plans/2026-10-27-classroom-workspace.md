# Classroom 2.0 implementation plan

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Classroom 2.0 implementation plan. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [current module/guide](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **For agentic workers:** Use focused parallel tasks for the independent feed, classwork, and frontend surfaces. The user explicitly requested implementation on main without a planning approval pause.

**Goal:** Extend existing classrooms with Stream, discussions, structured Classwork, and private learning resources while preserving IELTS assignments.
**Architecture:** Add normalized tables; keep assignments canonical. Services own transactions and authorization. Classroom row locks serialize all mutations, including ordering and archival. Existing membership history permits retained reads; only active members may comment. ADMIN retains read oversight and existing management, but new authored content mutations require the owner TEACHER.
**Tech stack:** FastAPI, AsyncSession, PostgreSQL, Alembic, Next.js, React, Zod, pytest, Vitest. No additional runtime dependency.
**Spec:** User attachment `4ff7a759-10be-4718-8b56-1a62c1578ff0/Pasted text.txt`.

## Global constraints

- Preserve authentication, immutable TestVersion, assignment provenance, grading and AI flows.
- Do not run full suites, browsers, E2E, production builds or the dev stack.
- Preserve pre-existing storage deletions and untracked design files.
- Safe Markdown subset renders as React nodes; raw HTML never renders.
- DRAFT/PUBLISHED/ARCHIVED lifecycle. Student visibility requires published resource and published containing section.
- Files use generated local storage keys, bounded allowlist/sniffed types, authenticated download and compensating cleanup.
- Reordering uses full ordered ID lists under a classroom lock and an expected revision. Conflict is 409; no silent overwrite.
- English/Vietnamese and shared theme tokens; keyboard move controls supplement native drag/drop.

## Shared API contract

All below paths are relative to `/api/v1/classrooms/{classroomId}`. Dates are ISO strings, IDs UUID strings.

Common status is DRAFT | PUBLISHED | ARCHIVED. Paginated lists return `{items, next_cursor}`.

Feed: GET `/feed?cursor=&limit=20&status=`. Entries `{id, kind: ANNOUNCEMENT|DISCUSSION|ASSIGNMENT_ACTIVITY, title: string|null, body: string, status, pinned: boolean, author_id, author_name, author_role, created_at, updated_at, published_at: string|null, comment_count, resource_ids: string[], assignment_id: string|null}`. For assignments timestamps derive from the canonical assignment. POST `/posts` with `{kind, title?, body, resource_ids?, status?: DRAFT|PUBLISHED}`. GET/PATCH `/posts/{id}` (patch same optional fields plus `pinned?`, `locked?`, status). Lifecycle POST `/posts/{id}/{publish|archive|pin}` (`pin` body `{pinned}`). Comments GET/POST `/posts/{id}/comments` (`{body}`); PATCH/DELETE `/comments/{id}`. Comment `{id, post_id, author_id, author_name, body, state: VISIBLE|RETRACTED|MODERATED, created_at, updated_at}`. Soft-deleted body is blank in DTOs.

Classwork: GET `/classwork` returns `{revision: number, sections: Section[], resources: Resource[], items: Item[]}`. Section `{id,classroom_id,title,description,status,position,created_at,updated_at}`. Resource `{id,classroom_id,title,description,kind: TEXT|LINK|FILE,body: string|null,url: string|null,status,original_filename: string|null,media_type: string|null,size_bytes: number|null,created_at,updated_at}`. Item `{id,section_id: string|null,resource_id: string|null,assignment_id: string|null,position}`.

POST `/sections` `{title,description?,status?}`; PATCH `/sections/{id}` same optional fields. POST `/sections/reorder` `{ids: string[],expected_revision}`. POST `/resources` `{title,description?,kind:TEXT|LINK,body?,url?,status?,section_id?}`. PATCH `/resources/{id}` metadata/content/status. POST `/resources/upload` multipart `file,title,description?,status,section_id?`. GET `/resources/{id}` metadata; GET `/resources/{id}/file?inline=true` authenticated file. POST `/items` `{section_id: string|null,assignment_id}` places existing assignment (unique within classroom). POST `/items/reorder` `{section_id: string|null,ids: string[],expected_revision}` moves given items to target section and normalizes both source and target; IDs are the complete desired target order. GET `/sections`, GET `/resources` aliases may return `{items}`.

## Review focus

- Draft UUIDs, hidden sections and private file authorization, including former members.
- Equal timestamps across post/assignment feed pages.
- Revision conflicts and cross-classroom reorder IDs.
- Archived room read-only for every new mutation.
- File validation and cleanup after failed database writes.

## Tasks and progress

- [x] Audit existing conventions, storage, tests, migration head.
- [x] Classwork models, shared content access, resource storage and additive migration (root).
- [x] Feed/post/comment models, schemas, service/router, notifications and focused tests (feed worker).
- [x] Shared tabbed classroom UI, typed clients, safe content, composers, comments, reorder and component tests (frontend worker).
- [x] Integrate routers/models/migration; focused backend/frontend checks and review.
- [x] Documentation, diff check, scoped commit, safe push to origin/main.

## Baseline

Main HEAD: 9c0df34. Pre-existing deleted storage `.gitkeep` entries and untracked `.agents/`, `.taste-skill/`, `docs/design-references/`, `skills-lock.json` must remain untouched and unstaged. Existing dependencies are installed; no installation is planned. No isolated worktree because the requested delivery targets main in the existing checkout.

## Verification and rulings

- User additionally requested actual local database migration. Elevated database access was needed because the sandbox could not see the Docker engine. Existing PostgreSQL was healthy; no full application stack was started. An isolated test database upgraded from empty through 0036 successfully. The configured local database then upgraded from 0035 to `20261027_0036 (head)` successfully.
- Shared room read locks (`FOR SHARE`) protect multi-query content reads against concurrent publication/membership changes; all new mutations retain `FOR UPDATE`. Batch feed loading also reapplies visibility.
- Final isolated tests: 101 backend cases passed across Classwork/storage/feed/existing classroom and assignment scope. Frontend scope: 57 cases passed. Scoped Python lint passed; frontend lint/type checks passed. Independent review is clean after regression-tested fixes for image-size policy, same-class notification navigation and post controls with hidden attachments.
- Private files use the existing refresh-aware HTTP client before temporary Blob URLs, with cancellation and cleanup.
- No browser, E2E, production build or full repository test suite was run, as requested.
- Remote alignment before commit: `git fetch origin main`, divergence `0 0`.
