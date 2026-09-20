# Fantasy Galaxy Visual System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply a cohesive fantasy-galaxy visual system to the complete IELTS Studio frontend while preserving every existing behavior and data boundary.

**Architecture:** Keep the current Next.js component and route structure, introduce the visual system through semantic CSS tokens and shared presentation classes, then make small markup-only refinements that give those styles clear structural hooks. Preserve the existing `data-theme` mechanism and derive the calmer Candidate `--exam-*` layer from the same theme tokens.

**Tech Stack:** Next.js 16.3.5, React 19.3, TypeScript 5.9, Tailwind CSS 4, plain CSS custom properties, Vitest, Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-20-fantasy-galaxy-visual-system-design.md`

## Global Constraints

- Preserve the visible product name `IELTS Studio`; fantasy galaxy is the visual direction, not a rename.
- Frontend-only changes: no backend API, database model, migration, evaluator, lifecycle, or persistence changes.
- Continue using the existing `data-theme="light"` and `data-theme="dark"` implementation.
- Use CSS gradients, layered surfaces, and restrained glow only; add no raster galaxy asset, particle system, WebGL, animation library, or continuously animated effect.
- Preserve all Text Completion, highlight, autosave, timer, navigation, flags, Listening audio, History, publish-validation, archive, and immutable-version behavior.
- Keep Candidate Reading and Listening substantially calmer than dashboard, admin, and builder surfaces.
- Maintain semantic HTML, keyboard navigation, ARIA labels, focus-visible states, WCAG-conscious contrast, reduced-motion handling, and responsive behavior.
- Make one focused commit at the end, as explicitly requested; do not create interim commits.

## Review Focus

- A stored `light` or `dark` preference must still initialize without hydration mismatch; keep the existing theme script and cover it with the root-layout test.
- Candidate question navigation must remain horizontally scrollable and keep separate current, answered, unanswered, and flagged states; cover required selectors in the exam CSS test and retain the existing behavior test.
- Completion sentence layout and gap inputs must remain inline and must not display per-gap limits; retain completion tests and assert the compact classes remain styled.
- Narrow viewports must not hide primary actions or introduce page-level horizontal overflow; cover major responsive selectors in the visual-system CSS test and inspect mobile-sized screenshots.
- Destructive actions must remain visually subordinate but keyboard-visible; assert danger-ghost and global focus-visible rules in the visual-system CSS test.

---

## File map

- `frontend/src/app/globals.css`: owns semantic tokens, atmospheric shell, shared primitives, page systems, builder hierarchy, Candidate restraint, review treatment, responsive rules, and reduced-motion behavior.
- `frontend/src/components/ui/app-shell.tsx`: supplies shell decoration hooks while preserving navigation and product name.
- `frontend/src/components/ui/icons.tsx`: supplies lightweight inline SVG icons for hero/pathway presentation where existing icons are insufficient.
- `frontend/src/app/page.tsx`: composes the redesigned dashboard hero, summary metrics, and learning pathways.
- `frontend/src/app/library/page.tsx`: gives published Reading and Listening cards semantic structural classes and metadata hierarchy.
- `frontend/src/app/history/page.tsx` and `frontend/src/features/history/attempt-history-list.tsx`: present attempt records and the reusable empty state with clear action priority.
- `frontend/src/app/admin/tests/page.tsx`, `frontend/src/app/admin/tests/[testId]/page.tsx`, and existing builder components: add only presentation hooks needed by the shared admin/builder system.
- `frontend/src/features/reading/reading-runner.tsx`, `frontend/src/features/listening/listening-runner.tsx`, `frontend/src/features/test-builder/draft-preview.tsx`: add editorial and Candidate-specific class hooks without changing state or event flow.
- `frontend/src/features/reading/reading-review.tsx` and `frontend/src/features/listening/listening-review.tsx`: add review hierarchy hooks while retaining renderer data.
- `frontend/tests/visual-system-css.test.ts`: locks semantic token, accessibility, responsive, Candidate, and restrained-effect requirements.
- Existing focused tests: guard all behaviors named in the specification.

### Task 1: Semantic tokens, shell, and shared primitives

**Files:**
- Create: `frontend/tests/visual-system-css.test.ts`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/ui/app-shell.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Test: `frontend/tests/visual-system-css.test.ts`
- Test: `frontend/tests/root-layout.test.tsx`
- Test: `frontend/tests/theme-toggle.test.tsx`

**Interfaces:**
- Consumes: the existing `document.documentElement.dataset.theme` contract and current shared class names.
- Produces: the semantic CSS variables listed in the spec plus stable `.app-shell`, `.app-header`, `.app-sidebar`, `.surface-card`, `.btn-*`, `.field`, `.select-field`, `.status-*`, `.empty-state`, `.dialog-*`, and focus styles used by all later tasks.

- [ ] **Step 1: Write the failing visual-system contract test**

Create a Vitest test that reads `src/app/globals.css` and asserts both theme blocks contain `--app-bg`, `--app-bg-elevated`, `--surface-hover`, `--surface-glass`, `--accent-violet`, `--accent-cyan`, `--glow-accent`, and `--glow-violet`. Assert the stylesheet includes `:focus-visible`, `@media (prefers-reduced-motion: reduce)`, the five button variants, responsive shell rules, and no `url(` background asset.

- [ ] **Step 2: Run the contract test and confirm it fails for missing semantic variables**

Run: `npm test -- visual-system-css.test.ts`

Expected: failure naming the first missing token, while the existing test harness loads successfully.

- [ ] **Step 3: Replace the root theme values with the compact semantic token system**

Define light and dark values from the design spec, retain compatibility aliases such as `--paper`, `--reading`, `--listening`, and derive `--exam-*` values within the same two theme blocks. Use deep navy rather than black in dark mode and cool near-white rather than neutral grey in light mode.

- [ ] **Step 4: Implement shell atmosphere and normalized shared primitives**

Use two or three static radial gradients on the app shell/body and small pseudo-element details. Restyle header, sidebar, active navigation, cards, buttons, fields, badges, dialogs, empty states, notices, and focus rings using only semantic tokens. Keep most surfaces opaque and reserve translucency for shell chrome and overlays.

- [ ] **Step 5: Add nonsemantic decoration hooks without changing navigation behavior**

Add `aria-hidden` shell/brand decoration only where CSS cannot express it through existing pseudo-elements. Keep `IELTS Studio`, navigation URLs, labels, active-route logic, and theme toggle unchanged. Update metadata description only if needed to describe the learning platform without renaming it.

- [ ] **Step 6: Run shell and theme tests**

Run: `npm test -- visual-system-css.test.ts root-layout.test.tsx theme-toggle.test.tsx`

Expected: all selected tests pass.

### Task 2: Home, Library, and History

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/library/page.tsx`
- Modify: `frontend/src/app/history/page.tsx`
- Modify: `frontend/src/features/history/attempt-history-list.tsx`
- Modify: `frontend/src/components/ui/icons.tsx`
- Modify: `frontend/src/app/globals.css`
- Test: `frontend/tests/attempt-history-list.test.tsx`

**Interfaces:**
- Consumes: Task 1 tokens and shared primitives; existing `getTests`, `getHistory`, `getVersion`, `StartAttempt`, and attempt deletion APIs.
- Produces: `.home-hero`, `.home-metrics`, `.learning-path-grid`, `.learning-path-card`, `.practice-grid`, `.practice-card`, `.history-list`, and `.history-row` structural hooks.

- [ ] **Step 1: Add presentation assertions to the History component test**

Extend the existing test to assert an attempt row exposes the Continue or Review link as the primary action and Delete remains a `btn-danger-ghost`. Assert the empty collection renders the shared empty-state title rather than a bare paragraph.

- [ ] **Step 2: Run the focused History test and confirm the new empty-state assertion fails**

Run: `npm test -- attempt-history-list.test.tsx`

Expected: the new empty-state expectation fails before markup is updated.

- [ ] **Step 3: Recompose Home as a learner portal**

Keep the existing server data calls. Render a hero with the current product identity, concise value proposition, `/library` primary CTA, and `/admin/tests` secondary CTA. Present counts as compact metrics, then add four pathway cards for Tests, Reading, Listening, and History using existing routes and inline SVG icons.

- [ ] **Step 4: Refine Library card hierarchy**

Keep one card per published module and preserve `StartAttempt`. Add module-specific semantic classes, version/module metadata, a quiet version-detail link, and a clear action region. Do not synthesize progress data that the API does not provide.

- [ ] **Step 5: Refine History rows and empty state**

Use `EmptyState` for no attempts. Group test/module/version/date metadata, status, elapsed time, and primary Continue/Review action into responsive row sections. Preserve delete dialog behavior and API calls exactly.

- [ ] **Step 6: Style the three learner pages from shared tokens**

Implement hero atmosphere, compact metrics, pathway cards, module-specific practice cards, and responsive history rows. Use only localized gradients and ensure destructive actions are visually quiet.

- [ ] **Step 7: Run learner-page focused tests**

Run: `npm test -- attempt-history-list.test.tsx root-layout.test.tsx`

Expected: all selected tests pass.

### Task 3: Admin library, test detail, and Builder workspace

**Files:**
- Modify: `frontend/src/app/admin/tests/page.tsx`
- Modify: `frontend/src/app/admin/tests/[testId]/page.tsx`
- Modify: `frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx`
- Modify: `frontend/src/features/test-builder/test-library-list.tsx`
- Modify: `frontend/src/features/test-builder/builder-workspace-navigation.tsx`
- Modify: `frontend/src/features/test-builder/version-actions.tsx`
- Modify: `frontend/src/features/test-builder/reading-builder.tsx`
- Modify: `frontend/src/features/test-builder/listening-builder.tsx`
- Modify: `frontend/src/features/test-builder/question-group-editor.tsx`
- Modify: `frontend/src/app/globals.css`
- Test: `frontend/tests/test-library-list.test.tsx`
- Test: `frontend/tests/builder-workspace-navigation.test.tsx`
- Test: `frontend/tests/builder-workspace-page.test.tsx`
- Test: `frontend/tests/version-actions.test.tsx`

**Interfaces:**
- Consumes: all current builder API calls, lifecycle provider, registry editors, preview paths, and publish validation result data.
- Produces: polished admin cards/rows, a clearly ranked builder toolbar, module-aware local navigation, and parent/child surface hierarchy without altering callbacks or payloads.

- [ ] **Step 1: Extend existing component tests with presentation contracts**

Assert the admin library still exposes Active/Archived status tabs, search, primary create/continue/edit actions, and quiet destructive actions. Assert builder navigation continues to render Created/Not created states and an `aria-current` active row. Assert VersionActions retains Validate, Publish/Edit, and Delete draft behavior.

- [ ] **Step 2: Run the focused admin/builder tests before markup changes**

Run: `npm test -- test-library-list.test.tsx builder-workspace-navigation.test.tsx builder-workspace-page.test.tsx version-actions.test.tsx`

Expected: existing behavioral assertions pass; any newly added structural assertion fails only for its missing class or grouping.

- [ ] **Step 3: Apply shared admin hierarchy**

Refine headings, toolbar density, status filters, test cards, version rows, and metadata grouping with semantic class hooks. Preserve all archive, restore, clone, permanent-delete, and routing behavior.

- [ ] **Step 4: Refine builder shell and toolbar**

Style Draft state, validation, preview links already present in module builders, Publish/Edit, and deletion with a clear action hierarchy. Keep the toolbar sticky on desktop and stacked on narrow screens.

- [ ] **Step 5: Refine module navigation and overview**

Use Reading cyan and Listening violet accents for selected/created states. Keep Writing disabled and do not implement it. Reduce nested-card weight through spacing and surface levels rather than markup rewrites.

- [ ] **Step 6: Refine passage, section, group, and editor presentation**

Keep passage/listening section cards as parent containers, group summaries as compact rows, and editors as focused work surfaces. Restyle Instruction, content, answer configuration, advanced fields, alternatives, and completion sentence/gap tokens without changing editor data flow or focus handlers.

- [ ] **Step 7: Run all builder behavior tests**

Run: `npm test -- builder-route.test.tsx builder-workspace-navigation.test.tsx builder-workspace-page.test.tsx draft-preview.test.tsx question-registry.test.tsx test-library-list.test.tsx text-completion-canvas.test.tsx version-actions.test.tsx`

Expected: all selected tests pass, including Text Completion identity, sentence structure, alternatives, and navigation-related cases already encoded in the suite.

### Task 4: Candidate Reading, Listening, navigation, and Preview

**Files:**
- Modify: `frontend/src/features/reading/reading-runner.tsx`
- Modify: `frontend/src/features/listening/listening-runner.tsx`
- Modify: `frontend/src/features/listening/audio-player.tsx`
- Modify: `frontend/src/features/test-builder/draft-preview.tsx`
- Modify: `frontend/src/features/questions/question-group-instruction.tsx`
- Modify: `frontend/src/features/questions/renderers.tsx`
- Modify: `frontend/src/app/globals.css`
- Test: `frontend/tests/exam-theme-css.test.ts`
- Test: `frontend/tests/reading-instructions.test.tsx`
- Test: `frontend/tests/reading-navigation.test.tsx`
- Test: `frontend/tests/listening-player.test.tsx`
- Test: `frontend/tests/draft-preview.test.tsx`
- Test: `frontend/tests/selectable-text.test.tsx`

**Interfaces:**
- Consumes: Candidate payloads, registry renderer contracts, timer helpers, autosave callbacks, flag/highlight APIs, audio element behavior, and existing navigation refs.
- Produces: `.exam-passage`, `.exam-passage-body`, `.exam-question-panel-heading`, and calm Candidate styling derived from `--exam-*` tokens.

- [ ] **Step 1: Strengthen Candidate CSS contracts**

Extend `exam-theme-css.test.ts` to assert the Candidate shell uses `--exam-*` tokens, Reading passage and question panes have distinct opaque surfaces, the footer strip remains single-row horizontally scrollable, the four chip states remain styled, instruction text preserves whitespace, and completion gaps remain compact inline controls.

- [ ] **Step 2: Run Candidate tests and confirm new class assertions fail**

Run: `npm test -- exam-theme-css.test.ts reading-instructions.test.tsx reading-navigation.test.tsx listening-player.test.tsx draft-preview.test.tsx selectable-text.test.tsx`

Expected: only newly introduced structural/CSS assertions fail.

- [ ] **Step 3: Add editorial Reading hooks**

Replace presentation-only utility groupings in passage markup with semantic classes while preserving `SelectableText`, target IDs, split panes, independent scrolling, active-question tracking, passage selection, question navigation, flags, highlights, autosave, timer, and submission code exactly.

- [ ] **Step 4: Apply calm Candidate styling**

Use opaque editorial Reading surfaces, restrained header/footer chrome, quiet instructions, accessible controls, and focus-only glow. Do not place galaxy decoration behind passage text or question cards.

- [ ] **Step 5: Polish Listening player and section presentation**

Use a raised violet/blue player surface with practical control grouping. Preserve the single shared audio element, all player labels, seek, volume, speed, skip, and playback behavior.

- [ ] **Step 6: Align Draft Preview with Candidate rendering**

Reuse the same passage, question, instruction, player, and navigation presentation with a small preview status treatment. Preserve the existing no-save preview behavior.

- [ ] **Step 7: Run Candidate and regression tests**

Run: `npm test -- exam-theme-css.test.ts reading-instructions.test.tsx reading-navigation.test.tsx listening-player.test.tsx draft-preview.test.tsx selectable-text.test.tsx text-completion-canvas.test.tsx timer.test.ts word-boundaries.test.ts`

Expected: all selected tests pass.

### Task 5: Review, dialogs, highlights, responsive polish, and full verification

**Files:**
- Modify: `frontend/src/features/reading/reading-review.tsx`
- Modify: `frontend/src/features/listening/listening-review.tsx`
- Modify: `frontend/src/components/ui/confirm-dialog.tsx` only if a semantic hook is required
- Modify: `frontend/src/features/highlighting/selectable-text.tsx` only if a semantic hook is required
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/tests/visual-system-css.test.ts`
- Test: all `frontend/tests/**/*.test.*`

**Interfaces:**
- Consumes: finalized review DTOs, shared question renderers, current dialog callbacks, and portal-based highlight popovers.
- Produces: educational review rows, unified overlay surfaces, and final responsive/accessibility guarantees.

- [ ] **Step 1: Add review and responsive expectations to the CSS contract**

Assert review correct/wrong states use semantic soft colors and borders, dialog/popover surfaces use shared tokens, mobile breakpoints cover learner rows and Candidate chrome, and reduced-motion remains present.

- [ ] **Step 2: Run the contract test and verify the new assertions fail before final styling**

Run: `npm test -- visual-system-css.test.ts`

Expected: newly added review/responsive assertions fail.

- [ ] **Step 3: Refine Reading and Listening review hierarchy**

Keep current answer-key data and renderers. Present score/section navigation clearly and separate Your answer, Correct answer, and Explanation with typography and subtle semantic borders rather than full saturated panels.

- [ ] **Step 4: Unify dialogs, validation panels, and highlight popovers**

Use the shared raised surface, line, shadow, radius, and action-alignment system. Preserve portals, hydration safety, delete-all behavior, and all existing labels and callbacks.

- [ ] **Step 5: Complete responsive and accessibility styling**

Check 1440 px, 1024 px, 768 px, and 390 px widths. Ensure shell navigation, hero, cards, history rows, builder toolbar/local navigation, passage/section cards, Candidate header/footer, and dialogs remain usable without page-level horizontal overflow. Verify light/dark contrast and keyboard-visible focus.

- [ ] **Step 6: Run the complete frontend verification suite**

Run from `frontend/`:

```text
npm test
npm run lint
npm run typecheck
npm run build
```

Expected: every command exits with code 0. Fix implementation regressions rather than removing or weakening tests.

- [ ] **Step 7: Perform visual browser verification**

Inspect Home, Library, History, Admin, available Builder/Candidate/Review screens in both themes and desktop/mobile viewports. Confirm the dashboard identity is expressive while Candidate screens remain calm. Record any environment-limited screen in the final visual-debt note.

- [ ] **Step 8: Inspect the repository diff and whitespace**

Run from the repository root:

```text
git status --short
git diff --check
git diff --stat
git diff
```

Confirm only the design spec, plan, task-related frontend source, and tests changed. Confirm no `.env`, `.env.local`, secret, storage binary, backend file, migration, or unrelated file is included.

- [ ] **Step 9: Stage only task files and verify the staged diff**

Stage explicit task-related paths, then run:

```text
git diff --cached --check
git diff --cached --stat
git diff --cached
```

Expected: clean whitespace check and one focused redesign diff.

- [ ] **Step 10: Commit and push**

Run:

```text
git commit -m "feat: introduce fantasy galaxy visual system"
git push
```

Expected: one commit on `main`, pushed to `origin/main` without force. If authentication blocks the push, stop after reporting the exact blocker.
