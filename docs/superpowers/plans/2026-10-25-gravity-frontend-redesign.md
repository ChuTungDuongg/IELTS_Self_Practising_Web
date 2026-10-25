# Gravity IELTS frontend implementation checklist

Spec: `docs/design-references/ielts_gravity_codex_master_prompt.md` (all 940 lines, including original appendix).

## Direction and boundaries

BandPilot keeps its compass brand, real learning data, Next.js/React/TypeScript and current API clients. The homepage translates Gravity's cobalt → lime → rose sphere choreography into four claims: purposeful practice, four skills, learning from review, and full mock preparation. The existing CSS globe is decorative only; consolidate it into one lazy Three.js scene. Internal screens use the same slate surfaces, rounded controls and precise typography without WebGL or scroll effects. Existing account accents, locale and light/dark preferences stay authoritative.

The master brief explicitly overrides Taste's normal prohibitions on gradients, mono labels and glass for the reference-led homepage. No random direction replaces the user's selected reference. The user subsequently authorized browser testing, a Modal-to-Docker data sync, and committing/pushing the finished changes directly to `main`. E2E automation, production builds and long suites remain outside the requested checks. Preserve the pre-existing uncommitted homepage 401 fix and its regression tests. Leave unrelated `.agents/`, `.taste-skill/`, `skills-lock.json`, and the supplied design reference untouched.

## Checklist

- [x] A: Read master prompt, original appendix, Taste Skill and repository rules.
- [x] A: Inventory all 37 page routes, shared shell, theme, globe, runner/review/editor surfaces and focused tests.
- [x] B: Shared slate/cobalt foundation, legible dark theme, controls, shell, focus and states.
- [x] C: Managed Three.js dependency and typed deterministic physics core.
- [x] C: Client-only renderer, glass/matte materials, lighting, cluster → drop/bounce → heart → lens release, pointer momentum.
- [x] C: Four responsive IELTS sections, real routes, existing personalized metrics/goals/continuation and footer.
- [x] C: Static/no-JS/WebGL fallback, reduced motion, pause, hidden/offscreen suspension, cleanup and low-power quality.
- [x] D: Auth, profile and personalization.
- [x] D: Library/practice, analytics and dashboard.
- [x] D: Reading, Listening, Writing, Speaking, mock and review.
- [x] D: History, admin/test builder, benchmark, classrooms/governance and transfer.
- [x] E: Focused unit/component checks, TypeScript, lightweight lint, CSS checks and diff whitespace validation.
- [x] E: Route coverage and honest final limitations report.
- [x] Follow-up: synchronize the stopped Modal development database and assets to local Docker, with a local backup before replacement.
- [x] Follow-up: verify all 47 table counts and all 154 asset file sizes against the export; confirm Alembic head `20261013_0035`.
- [x] Follow-up: observe authenticated homepage/history HTTP 200 after the user's normal login.
- [x] Follow-up: inspect actual browser screenshots at 1440×900, 768×1024 and 390×844; fix footer stacking, ticker wrapping, hero text interference and canvas bleed into the study workspace. Verify the ticker pause/resume control.
- [ ] Remaining device verification: normal-motion WebGL on a real GPU, touch performance/FPS/memory, visual theme/language parity and authenticated exam/editor screens. The browser used for inspection requests reduced motion and correctly stays on the static fallback.

Git delivery is the final operation, explicitly authorized on `main`; the final chat response records its actual outcome.

## Implementation units

1. `components/home/gravity/physics.ts`: deterministic body generation, reference mode thresholds, heart sampling, collision and boundary solver; focused numeric tests.
2. `components/home/gravity/scene.ts`: renderer and resource lifecycle; fixed timestep, capped quality and DOM event ownership. `gravity-field.tsx` lazy-loads it only after preference checks; static artwork remains behind it.
3. `gravity-landing.tsx` + `gravity-home.css`: four real IELTS sections, native scroll, IO reveals, local motion control; `overview-content.tsx` retains real workspace content. English/Vietnamese copy through existing dictionaries.
4. Existing `design-system.css` layout contracts extended by `gravity-product.css`: shared and area-specific presentation; preserve runner layout/persistence/media APIs and editor behavior. Writing/benchmark CSS modules consume the same tokens.
5. Focused tests cover physics phases/collisions/heart/pointer, no-session homepage regression, fallback/preferences/lifecycle, navigation and existing runner workflows. No GPU/browser performance or screenshot claims.

## Route coverage

All 37 routes received a source/component review and the shared presentation pass. Follow-up browser checks cover the homepage and login; the user's authenticated homepage also loaded successfully. Most internal route files intentionally remain unchanged: their existing components inherit the refined tokens and area-specific rules. The route inventory is not a claim that all 37 routes received browser validation.

| Actual area | Page routes | Implemented presentation |
| --- | ---: | --- |
| `/` | 1 | Four Gravity sections; procedural spheres; real skill links; saved attempt continuation; personalized goals and metrics; guest invitation instead of unavailable zero metrics; footer ticker and wordmark. |
| `/login`, `/register`, `/session/restore`, `/profile`, `/settings/personalization` | 5 | Split auth composition; form spacing and readable validation; existing password minimum described accessibly; account cards, modal, accent choices and session states. |
| `/library`, `/library/[versionId]`, `/practice` | 3 | Test cards, metadata, skill filters, detail headings and full mock entry; all four skill query links use the existing practice filter. |
| `/history`, `/analytics` | 2 | Tabs, attempt rows/cards, confirmations, real statistics, chart surrounds, comparison and error/empty states. |
| `/attempt/[attemptId]`, `/review/[attemptId]`, `/test-session/[sessionId]` | 3 | Reading/Listening/Writing/Speaking typography and controls, calm timer/save status, passage/question surfaces, score hierarchy, mock transitions and reviews. Writing pane scroll keeps its Save action reachable in short windows. |
| `/admin`, `/admin/users/[userId]`, `/admin/tests`, `/admin/tests/new`, `/admin/tests/[testId]`, version edit/preview, `/admin/writing-benchmark`, moderation list/detail, `/transfer` | 11 | Stats, tables, local editor navigation, content groups, answer key controls, validation, benchmark list/editor, distribution, governance cards and transfer panels. |
| `/teacher/tests`, `/teacher/tests/new`, version edit/preview | 4 | Same shared builder/control vocabulary, including all four module editors and previews. |
| `/classrooms`, `/teacher/classrooms`, both detail routes, both assignment results list/detail families | 8 | Shared headings, cards, tables, notices, dialogs and pagination; existing role and result boundaries preserved. |

## Important files

- `frontend/src/components/home/gravity/{physics.ts,scene.ts,load-scene.ts,gravity-field.tsx,gravity-landing.tsx}` own physics, GPU lifecycle, lazy loading, enhancement and IELTS content respectively.
- `frontend/src/app/gravity-home.css` owns the reference-led homepage; `gravity-product.css` extends the existing shared design system for internal screens.
- `components/home/overview-content.tsx` retains actual metrics/goals and separates signed-in data from the guest invitation. `app/page.tsx` retains the earlier no-session startup fix.
- `components/ui/{app-shell,app-footer}.tsx`, `features/auth/auth-form.tsx`, and the existing Writing assessment/annotation and benchmark CSS modules adapt their actual surfaces.
- `lib/i18n/{en,vi}.ts` provide the new copy through the current locale system. `app/layout.tsx` imports the styles and self-hosted display font.
- `frontend/package.json` and `package-lock.json`: one `three@0.186.1` runtime copy, `@types/three`, and `@fontsource-variable/raleway@5.3.0`. No competing UI/physics/animation framework.

## Reference adaptations and fallbacks

- Physics retains camera FOV 38 / z 11, ACES exposure 1.15, reference radius/mass distribution, 22% glass probability, 4 contact passes, reference attraction/damping/pointer momentum and scroll thresholds. Seed 25102026 makes the procedural field reproducible.
- Native document scrolling drives section-relative progress, so taller phone sections remain synchronized. No wheel interception and no scroll effects in exam/workspace routes.
- The canvas is sticky inside the homepage story rather than globally fixed. It cannot remain behind the study workspace, other routes or exams. The old `BrandOrbit` file is retained but no longer mounted; its decorative pointer interaction is consolidated into the field.
- Desktop/mobile/low-power counts: 96/54/32. Geometry segments: 48/28/20. DPR caps: 1.75/1.25/1. Desktop shadow maps use 1024². Low-power mode omits studio environment generation and shadows. Glass/matte materials and procedural studio lighting/reflections remain.
- Physics runs at a fixed 60 Hz, with at most three catch-up ticks. Rendering pauses while hidden/offscreen or manually paused, and sleeps after every sphere has passed the lens. Scroll-back restores the field; released bodies are parked to prevent unbounded positions.
- Static CSS spheres, all headings and links are server-rendered. Reduced motion and Save-Data skip loading Three.js. GPU/import failures and an 8-second initialization timeout leave the static field usable. There is no blocking loader or fictitious progress counter.
- Pause/Resume and Scatter buttons give keyboard/touch access to the interaction. The footer ticker has its own pause control. Media preference changes and Strict Mode remounts release resources correctly; a manual pause survives preference changes.
- Renderer, materials, shared sphere/floor geometries, environment target, shadow map, rAF, listeners and observers are disposed, including initialization failure. Unit tests use a mock GPU and do not claim driver/device verification.
- Raleway is self-hosted (Latin 48,264 bytes; Vietnamese 11,384 bytes), with existing system body and mono fallbacks. No runtime Google Fonts/CDN request or external photos/models/textures. Procedural artwork follows the user's selected reference; no stock-photo quota or random Taste direction replaces it.
- The optional palette drawer is intentionally omitted: the existing account accent/theme controls remain the only global preference system. Reference colors apply to the homepage scene; user accents still govern product controls.

## Verification record

All allowed checks below passed. Batches overlap; counts must not be added as unique tests.

| Check | Result |
| --- | --- |
| Homepage, auth, shell, initial physics (4 focused files) | 137 passed |
| Reading/Listening navigation, player, Writing runner, mock transition, responsive contracts (6 files) | 126 passed |
| Writing AI assessment, history, builder autosave, benchmark page (4 files) | 115 passed |
| Speaking runner, teacher/classroom UI, transfer, analytics, personalization (5 files) | 76 passed |
| Final physics, scene lifecycle, mock-GPU resource ownership, server rendering, homepage and responsive contracts (6 files) | 36 passed |
| Stylesheet package export and referenced font-file regression (1 file) | 2 passed; original missing subset imports reproduced as failures before the fix |
| TypeScript `tsc --noEmit` | Passed after final code changes |
| ESLint on changed TS/TSX and focused tests | Passed after final code changes |
| Lightning CSS: 2 new sheets + 3 changed CSS modules | Parsed successfully, zero warnings |
| Lockfile inspection | Exactly one Three.js runtime copy |
| Source color contrast | Light body 14.95:1, secondary 5.31:1; dark body 14.50:1, secondary 7.84:1; hero ink 11.41:1 and copy 6.82:1 against its blue field; footer secondary 9.24:1 |
| `git diff --check` | Passed; Git reports normal LF→CRLF notices only |

Regression tests reproduced and fixed guest API/zero-metric handling, offscreen resume, manual-pause preference changes, and long-held release stability. Focused tests do not replace browser layout, rendering or real data verification.

During the user's local preview, Next.js reported missing `@fontsource-variable/raleway/latin.css` and `vietnamese.css`. The installed variable-font package exposes `index.css`, not those subset entry files. `layout.tsx` now imports the package's supported root entry; its Unicode ranges cover Latin and Vietnamese and browsers load the needed font subsets. The earlier TypeScript/lint/CSS parsing checks did not detect this module-resolution error. A new focused regression resolves every layout stylesheet import and verifies all referenced font binaries. The existing local server's `/login` and `/` both returned HTTP 200 after the fix, without a module-not-found response; the homepage response contains the Gravity story markup. This is HTTP/SSR verification, not browser validation.

## Local preview follow-up, 2026-10-25

The original local database was at `20261012_0032`, behind the backend models and their Speaking score table/practice columns. The authenticated homepage failed through `getHistory`. The user requested synchronizing Modal data into Docker. The latest stopped `modal serve` app used workspace `tungduong156glis` and the `ielts-web-postgres-dev` volume. A temporary CPU-only export mounted that database and `ielts-web-assets` read-only, copied the stopped PostgreSQL data to temporary storage, and produced a logical PostgreSQL dump and asset archive. The source volumes were not modified.

Both local servers were offline during backup/restore. The pre-sync database and assets are preserved under the ignored path `backups/modal-to-local/20261025-sync/local-before/2026-10-25T125544Z-ee53dd5d`. The downloaded export is under the ignored sibling `source/`. Checksums passed before restore. The restored database has schema `20261013_0035`, 3 users, 4 tests and 10 attempts. All 47 public table counts matched before subsequent login/session activity, and all 154 exported asset files (234,120,157 bytes) existed at the correct sizes. `alembic upgrade head` confirmed no further migration was needed. The existing server pair was restarted using `npm run dev`.

After the user's normal login, the local server logs show HTTP 200 for `/api/v1/history`, `/api/v1/tests`, `/api/v1/auth/profile`, `/api/v1/admin/stats` and `/`. No catch-all was added to conceal backend errors. No credentials, database dumps, exam content or binary assets are part of the frontend commit.

Actual screenshots exposed CSS defects that unit checks had missed: the legacy footer's flex row arranged all new sections side by side, the inherited text width constrained the ticker, and the sticky artwork's negative margin allowed it to paint beyond the story. The footer now stacks its sections, the ticker stays on one line with nonshrinking separators, and `overflow: clip` bounds the artwork without creating a competing scroll container. An initial-hero mask reserves the lower area for readable text in both canvas and fallback modes. The shared-sheet cascade regression includes the legacy rules and checks these conflicts.

The user then requested a smaller footer and an actually moving loop. The ticker is now capped at 26px and the wordmark at 112px, with tighter spacing and an adjacent Play/Pause button. The existing global reduced-motion rule forced all CSS animations to 0.01ms and one iteration; that made the former Resume button ineffective. The footer now follows the motion preference automatically, but explicit Play opts only this ticker into its full 26-second infinite loop. Pause retains the current position. A narrowly scoped override preserves duration/iteration count for explicit ticker controls while leaving the global accessibility reset intact elsewhere.

Final follow-up checks: 44 focused tests across eight files passed, including the footer's reduced-motion opt-in and the actual shared-sheet duration/iteration conflict. TypeScript and lint on changed TS/TSX/tests passed. Browser checks at desktop, tablet and phone widths showed readable hero copy and no document-level horizontal overflow. Final desktop and phone screenshots confirmed the smaller footer and one-line ticker. Computed transforms changed while playing and stayed at the same matrix while paused; the explicit Play control works with reduced motion enabled. The browser's reduced-motion mode kept Three.js unloaded, as intended; this does not verify live GPU rendering. Screenshots are saved outside the repository in the task's visualization directory.

Remaining verification: normal-motion sphere/heart/scroll timing on real hardware; real touch and device GPU/FPS/memory; browser screenshots of both languages/themes and authenticated runner/editor screens; production bundling and hosted Modal behavior. No E2E automation, production build or backend source modification was performed. The supplied reference and unrelated working files remain untouched.
