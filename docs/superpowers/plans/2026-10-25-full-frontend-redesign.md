# Full frontend redesign implementation plan

> **Documentation audit: SUPERSEDED.** Historical reference; không phải contract hiện hành.
> Mục đích: Full frontend redesign implementation plan. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../frontend/src/components/ui/app-shell.tsx).
> Đọc cùng [current module/guide](../../modules/shared-platform.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **For agentic workers:** Use superpowers:executing-plans to implement these tasks in place. The user's detailed execution brief authorizes proceeding through implementation without an approval stop. Do not commit or push.

**Goal:** Give every existing BandPilot screen a cohesive, readable, responsive presentation while preserving domain behavior.

**Architecture:** Retain Next.js, React, TypeScript, Tailwind v4 and the existing global CSS/component structure. Add a deliberately scoped presentation stylesheet after the legacy stylesheet, using shared semantic tokens. Refine presentation components only where CSS cannot improve the interaction. No API, backend, grading, authentication, timing, persistence or content-schema changes.

**Tech stack:** Existing Next.js 16 / React 19, CSS and CSS modules, Vitest / Testing Library, TypeScript and ESLint. No new dependencies.

**Spec:** User's full application redesign brief, supplied 2026-10-25 in `C:/Users/Admin/.codex/attachments/de1042bb-58c3-4860-b138-dd8b06c943b4/Pasted text.txt`.

## Design direction

Taste app-screen rules apply. Use the editorial workspace direction: aligned content edges, an understated header, 24–32px page titles, one readable sans family for controls and the existing serif for passages/essays. Preserve BandPilot's mark, interactive orbit and personalized accent palette. Flat white surfaces on a neutral light ground; graphite surfaces on a true neutral dark ground. One spacing scale (4/8/12/16/24/32/48), radii 6/10/14, neutral control borders, visible focus, restrained feedback only. Existing branding is the explicit exception to Taste's violet/indigo preference. No invented figures, progress or exam content.

## Global constraints and rulings

- No browser, Playwright, Cypress, E2E, full test suite, production build, commit or push.
- Typecheck, targeted component tests, lightweight ESLint and `git diff --check` only.
- Work in the existing checkout as requested; preserve the pre-existing untracked `.agents/` and `skills-lock.json`.
- Styling applies to existing Speaking screens only; no new Speaking phase or scoring work.
- Preserve the source/query contracts, module restrictions, exam seeking, highlight offsets, autosave, identifiers, question registries and every existing control.
- Do not hide authoring controls on mobile; reflow instead. Do not apply body-wide overflow locks.
- Browser inspection and screenshot scoring are explicitly waived by the user's validation restriction. Do not claim visual verification.
- Pure CSS polish uses static CSS validation and existing focused tests. New interactive behavior gets focused tests first; no tests that merely mirror cosmetic declarations.

## Review focus

1. Mobile navigation: opening, Escape, focus restoration and route selection must leave all role-specific destinations accessible.
2. Examination layouts: independent desktop panes, accessible source/questions on narrow screens, no disabled media restrictions accidentally changed.
3. Themes: semantic variables must reach exams, portaled highlights, dialogs and CSS modules with no theme-dependent rendering.
4. Real data: chart dates and empty states must remain honest; existing failures must never expose raw exception text.
5. Authoring and reviews: all question families, controls, annotations, grading and stored evaluations remain present.

## Route inventory and coverage checklist

All actual `src/app/**/page.tsx` routes, grouped by their presentation owners:

- [x] Home/dashboard: `/` — overview, goals, metrics, learning pathways and interactive orbit.
- [x] Account: `/login`, `/register`, `/session/restore`, `/profile`, `/settings/personalization`.
- [x] Learning: `/library`, `/library/[versionId]`, `/practice`.
- [x] Examination: `/attempt/[attemptId]` — Reading, Listening, Writing, Speaking; all centralized question renderers and highlighting.
- [x] Mock and review: `/test-session/[sessionId]`, `/review/[attemptId]`, `/history`.
- [x] Progress: `/analytics`.
- [x] Administration: `/admin`, `/admin/users/[userId]`, `/admin/moderation`, `/admin/moderation/[requestId]`, `/admin/writing-benchmark`.
- [x] Test management: `/admin/tests`, `/admin/tests/new`, `/admin/tests/[testId]`, `/teacher/tests`, `/teacher/tests/new`.
- [x] Builders/previews: `/admin/tests/[testId]/versions/[versionId]/{edit,preview}`, `/teacher/tests/[testId]/versions/[versionId]/{edit,preview}`.
- [x] Classrooms: `/classrooms`, `/classrooms/[classroomId]`, `/teacher/classrooms`, `/teacher/classrooms/[classroomId]`.
- [x] Classroom results: both `/classrooms` and `/teacher/classrooms` variants of `/[classroomId]/assignments/[assignmentId]/results` and `/results/[attemptId]`.
- [x] Transfer: `/transfer`.
- [x] Shared: header/footer, headings, buttons, fields, badges, dialogs, personalization overlay, notification menu, highlight popovers, loading/empty/error states, pagination, search, filters and tabs.

## Task 1 — Shared foundation and shell

Files: `src/app/layout.tsx`, new `src/app/design-system.css`, `src/components/ui/global-header.tsx`, `src/components/ui/app-shell.tsx`, `src/components/ui/app-footer.tsx`, localized messages, focused shell test.

- [x] Inspect existing component interfaces and installed Next CSS guidance.
- [x] Add a focused failing mobile navigation test, then implement disclosure, keyboard close and focus handling without changing route access logic.
- [x] Establish semantic surface/text/control/status tokens in both themes; keep personalized accents and support legacy variable aliases.
- [x] Unify buttons, fields, panels, floating surfaces, focus and reduced motion; keep all existing interfaces.
- [x] Reflow navigation on tablet/mobile; retain labels and every role-specific destination.
- [x] Verify shell test plus TypeScript.

## Task 2 — Home, learning and account screens

Files: overview component, practice browser and library components, auth/account CSS selectors, translations and focused component tests.

- [x] Keep the orbit interactive; rebalance hero around actual learning actions and goal data.
- [x] Add useful direct skill links with URL-backed initial selection; verify skill selection from the URL and ordinary filter behavior.
- [x] Improve library scanning, module metadata, start controls, progress strip and empty states.
- [x] Refine login/register, restoration, profile and personalization using existing behavior and controls.
- [x] Add lightweight reusable route loading/error presentation according to the installed Next conventions, with a focused retry test.
- [x] Verify targeted home/library/account tests.

## Task 3 — Exams, full mock and review

Files: Reading/Writing runner presentation, shared presentation stylesheet, existing question/editor markup only if needed, Writing feedback CSS modules, annotated essay CSS module.

- [x] Inspect Reading, Listening, Writing and Speaking shells, question renderers, all navigation, timers, autosave, audio, highlights and review markup.
- [x] Polish exam headers, source/question panes, answer controls, navigation, save/flag/status feedback, audio player and media frames.
- [x] Provide a small-screen Reading pane switch while keeping both DOM regions mounted and retaining their independent scroll positions; focused interaction test before implementation.
- [x] Improve writing prompt/editor and feedback hierarchy, criterion panels, evidence, progress, saved evaluations and annotations. Display all AI text through existing safe rendering.
- [x] Refine Speaking and full mock transition/results styling without behavior changes.
- [x] Verify focused Reading/Listening navigation, Writing runner/AI feedback and full mock component contracts.

## Task 4 — Progress, history and management

Files: analytics component, history/test-builder/classroom/admin/transfer selectors, benchmark module CSS, focused analytics test.

- [x] Use the supplied timestamps in an accessible, labelled band trend; preserve API data and calculations. Test date labels and keyboard-accessible data before implementation.
- [x] Refine history grouping and result summaries while retaining all actions and dialogs.
- [x] Inspect and polish test listings, every module builder, question-family editors, validation/autosave, media, preview, import/export, admin users/moderation and classroom workflows.
- [x] Refine benchmark bank and distribution, consistent tables/pagination and tablet/mobile reflow.
- [x] Verify analytics, history, builder navigation and representative editor component tests.

## Task 5 — Consistency, verification and reporting

- [x] Review changed selectors and components against every route group above; mark coverage accurately.
- [x] Check theme parity, meaningful status labels, keyboard focus, touch sizes, text wrapping, responsive pane access, opaque overlays and reduced motion.
- [x] Run TypeScript, ESLint on changed TS/TSX files and `git diff --check`.
- [x] Run only focused unit/component test batches relevant to changed interactions; record exact commands/results.
- [x] Request one fresh code review of the complete uncommitted diff; fix material findings and re-run their focused checks.
- [x] Report source changes separately from browser-unverified visual layout. Keep this plan as the progress and continuation record.

## Execution record

- Preparation: read Taste Skill and app-screen reference, root/frontend AGENTS, local Next CSS/loading/error documentation; inspected route inventory and existing tokens/components. Baseline typecheck and four representative component files started before edits.
- Ruling: the detailed brief explicitly directs implementation after planning; proceed without the skill's optional design/plan approval questions. No new authentication or scoring work is authorized.
- Ruling: work in place with no Git mutations. Isolation and commit workflows would contradict the user's requested reviewable uncommitted changes and current workspace intent.


## Final coverage and verification record

All 37 existing page routes are covered by the shared presentation sheet and the application-area selectors listed above. The account and management flows retain their existing components and behavior. Targeted markup/interaction changes were limited to navigation, active-attempt continuation, direct skill selection, Reading pane switching, readable trend data, and load/retry feedback. Writing assessment and benchmark CSS modules were refined separately.

Taste direction: editorial-greeting, seed 25102026, with existing palette/type preserved. The product-specific material is the learner's actual current attempt and four skill targets; the existing orbit retains its pointer interaction. The existing horizontal navigation is retained instead of introducing a sidebar. No screenshots or visual score are claimed.

Checks performed (frontend directory, direct Node entry points because npm is not on this host's PATH):

| Focused batch | Result |
| --- | --- |
| app-shell, Reading navigation, Listening navigation, Writing AI assessment baseline | 214 passed before edits |
| Reading navigation, skill practice, analytics, navigation disclosure | 65 passed at that checkpoint |
| Home metrics/continuation and skill practice | 45 passed |
| Analytics dates, text table, localization and failure/retry feedback | 5 passed |
| app-shell, library, root layout, personalization | 132 passed with one obsolete shell-menu expectation; expectation updated for the new authorized Menu control and shell rechecked below |
| page feedback, Listening navigation, Listening player, Writing runner | 97 passed |
| Writing AI assessment, annotated essay, benchmark bank, mock transition | 103 passed |
| Builder navigation, teacher/classroom UI, attempt history, transfer | 57 passed |
| Final responsive CSS contracts, menu disclosure, shell, Reading navigation | 107 passed |
| Listening navigation after responsive fixes, alongside shell/CSS contracts | 133 passed and 1 stale-element assertion failed; assertion corrected and menu/CSS contracts separately rechecked: 5 passed |
| TypeScript, final run | passed, no errors |
| ESLint on all changed TS/TSX sources and tests | passed, no errors or warnings |
| Lightning CSS compilation of the shared stylesheet and three changed CSS modules (proper CSS-module mode) | passed, no warnings |
| New semantic text/surface token contrast, calculated from source | light primary 15.55:1; light secondary 5.03:1; dark primary 14.61:1; dark secondary 6.38:1 |
| git diff --check | passed |

The source Taste lint reported 0 FAIL and 36 WARN. Warnings scan declarations such as box-shadow: none and backdrop-filter: none as patterns; actual shadows are limited to floating panels and the subtle selected segment. This is a source check, not the prohibited browser inspector.

### Fresh review and fixes

A fresh read-only reviewer examined the tracked diff, new source files, constraints and legacy CSS. All four actionable P2 findings were reproduced and fixed:

1. Desktop Menu visibility: shared icon display overrode the earlier hiding rule. Reordered the hiding rule; regression checks desktop and phone active styles.
2. Stale menu state: returning to a previously opened path re-expanded navigation. Moved disclosure state into a header bar keyed by pathname; the away-and-back interaction now remains closed.
3. Listening flag clipping: fixed mobile chip tracks exceeded narrow Listening columns. Retained flexible number tracks, 32px flag tracks and a two-column mobile question grid, with 44px control height.
4. Tablet filters: legacy three-column filter styles squeezed into the 180px sidebar. Added an explicit one-column sidebar baseline; mobile keeps its separate compact composition.

Final: all four review regressions RED→GREEN. No deferred code-review findings.

### Rulings and remaining limits

- Ruling: execute in the current checkout without commits, branches or worktrees, as the brief requests direct, reviewable implementation. All pre-existing untracked user files were preserved.
- Ruling: use the existing brand/personalized hues and typography rather than replacing user preferences; carry Taste through surface hierarchy, scale, spacing, data emphasis and restrained controls.
- Ruling: native CSS/source checks and focused component tests replace browser inspection under the user's explicit restriction. Remaining cost: actual viewport geometry, scrolling/selection, media layout, and pixel contrast need a later human/browser visual pass.
- Ruling: route loading errors now remain errors instead of fabricated zero totals/empty collections. Partial practice loads retain successful content and display retry feedback. No API contracts changed.
- Not run: browser inspector/screenshots, browser/E2E tests, full test suite or production build. No claims are made about their results.
- Continuation: when browser validation is authorized, inspect all route families at 1440, 768 and 390px in both themes; prioritize long Reading passages, Listening maps/audio dock, Writing evidence/annotations, builders, classroom results and open overlays. Preserve current changes and use this document as the coverage map.
