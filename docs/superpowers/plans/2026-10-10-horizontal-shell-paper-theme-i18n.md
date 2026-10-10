# Horizontal Shell, Paper Theme & EN/VI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the permanent workspace sidebar with horizontal navigation, add a shared footer, introduce a warm paper/graphite visual system, and add typed English/Vietnamese system UI localization without changing authored IELTS content or exam behavior.

**Architecture:** RootLayout remains a server component and wraps the existing AuthProvider/AppShell tree in one client LocaleProvider. AppShell composes a horizontal GlobalHeader and AppFooter on workspace routes while preserving its existing exam-route bypass; CSS supplies responsive composition and explicitly protects current exam values from the new workspace palette. Typed bundled dictionaries translate system text through existing client views and small server/client presentation boundaries, without changing data fetching or feature identity.

**Tech Stack:** Next.js, React, TypeScript, CSS, Vitest, React Testing Library

**Spec:** `docs/superpowers/specs/2026-10-10-horizontal-shell-paper-theme-i18n-design.md`

## Global Constraints

- Frontend only. No dependencies, backend/API/schema/DB/migration changes, font downloads, binary assets, or external services. Read `frontend/AGENTS.md` and relevant bundled Next.js guides before writing implementation code.
- Exactly `en | vi`, default `en`, storage key `ielts-locale`. Exactly light/dark, storage key `ielts-theme`; saved valid theme wins, otherwise light. No system/auto mode, locale routes, cookies, flags, cross-tab synchronization, or generated translations.
- Translate application-owned static UI and accessible labels. Preserve authored test titles/descriptions, passage titles/text, Listening content, question prompts/options, administrator instructions, Writing prompts/responses, manually authored section/task content, answer keys/explanations and user values. Locale changes the interface, not IELTS content.
- Include common static runner/review/preview/paused-gate/Full Mock transition controls now. No runner redesign, new runner controls, blanket English runner boundary, or changes to exam layout/tokens, timers, autosave, highlighting, flags, playback policies, scoring, security, or attempt state transitions.
- Preserve Full Listening, Full Mock, optional focused Listening audio, clipping, seeking/speed permissions and raw/max + accuracy with no focused Band. No Skill Practice or Test Library business-logic changes, AI changes, authentication redesign, or Speaking implementation. Existing Speaking target fields may receive translated labels only.
- Keep published versions/frozen DTOs, routes, enum codes, IDs, payloads, validation branches and server guards intact. Translate local fallback branches; unknown server diagnostics and authored/API labels pass through unchanged.
- Locale/theme never become page/card/attempt keys or dependencies that reset stores, recreate audio, navigate, or restart requests. SSR and first client text are English; locale restoration happens after hydration. Root theme bootstrap may change only `data-theme`, using the existing narrow root hydration suppression.
- Preserve specialized Builder editors and range functionality. Defer their nested help, answer-key guidance, completion/diagram tools and audio-range guidance. IELTS instruction templates are excluded content, not a future translation backlog.
- Verification uses targeted Vitest/RTL, CSS contracts/contrast arithmetic, typecheck, targeted ESLint and `git diff --check`. No browser, manual browser checks, Playwright/E2E, dev server, backend suites, AI calls, Modal, or real audio. DOM/CSS tests do not claim pixel-level rendering proof.
- Test/ESLint/typecheck commands below run with working directory `frontend/`; Git commands run from the repository root. Use existing installed packages and scripts (`test: vitest run`, `typecheck: tsc --noEmit`). Mock HTTP and media APIs; use fictional fixtures only. Reset preference storage/root attributes and restore mocks/fake timers per test.
- Each implementation commit includes only its listed changes and tests. Update obsolete assertions when their owning task changes behavior, preserving useful assertions; do not leave earlier tasks broken until Task 12. Run `npm run typecheck`, targeted `npx eslint <changed .ts/.tsx paths>` and root `git diff --check` before each commit.

## Review Focus

1. **ADMIN + Vietnamese + long names:** all eight primary links remain in one navigation landmark and can wrap without clipping or hiding actions. Owned by Task 3 `admin Vietnamese navigation preserves all routes` and Task 5 `header wraps at approved breakpoints`.
2. **Blocked/corrupt preference storage:** reads/writes/getter failures and invalid values produce usable en/light defaults; current-document switches still work. Owned by Tasks 1–2 `locale storage failures are non-fatal` and `theme bootstrap defaults to light`.
3. **Locale switch during an active attempt:** copy updates while runner/audio identity, drafts, timer timestamps and request counts remain stable. Owned by Task 11 `locale switch preserves active attempt state` for Reading, Listening and Writing.
4. **Dark workspace tokens leaking into exams:** frozen light/dark exam and inherited shared properties resolve identically for attempt, paused gate and embedded preview. Owned by Task 6 `paper tokens cannot change resolved exam colors or controls`.
5. **Exact preview footer exclusion:** Builder preview keeps its header/local exam footer but loses only the global footer; edit/detail/review/transition routes retain it. Owned by Task 4 `only exact Builder preview suppresses the global footer`.

## File Map

Paths below are relative to the repository root. New presentation files group a coherent feature's copy/attributes; existing fetching routes keep their fetching and guards. `PrimaryNavigation`, `HeaderActions` and `LocaleSwitcher` stay local to `global-header.tsx`. Icons, AppLogo, route constants, API clients, question registries/renderers, timer/autosave engines and server role layouts are reused without restructuring.

| Create | Single responsibility |
| --- | --- |
| `frontend/src/lib/i18n/en.ts`, `vi.ts` | Flat, paired system-copy dictionaries; English defines keys, Vietnamese supplies string values. |
| `frontend/src/lib/i18n/types.ts` | Locale/key/dictionary/parameter/function types. |
| `frontend/src/lib/i18n/translations.ts` | Pure translation/interpolation and common enum-to-message mappings. |
| `frontend/src/lib/i18n/locale-provider.tsx` | Client preference context, hooks and wrapper-free UiText. |
| `frontend/src/components/ui/global-header.tsx` | Single horizontal primary navigation and existing auth/preferences actions. |
| `frontend/src/components/ui/app-footer.tsx` | Product description, server-supplied year and locale indication. |
| `frontend/src/components/home/overview-content.tsx` | Overview presentation from existing serializable server results. |
| `frontend/src/features/practice/library-content.tsx` | Library list/detail presentation, including translated native attributes. |
| `frontend/src/features/auth/admin-content.tsx` | Admin dashboard/user-detail presentation from existing server results. |
| `frontend/tests/locale-test-utils.tsx` | Shared test-only provider/switch harness that preserves child identity. |
| `frontend/tests/translations.test.ts`, `locale-provider.test.tsx` | Dictionary, interpolation, hydration and persistence contracts. |
| `frontend/tests/app-shell.test.tsx`, `app-footer.test.tsx`, `shell-layout-css.test.ts` | Role/route/chrome/width/responsive shell contracts. |
| `frontend/tests/common-localization.test.tsx`, `workspace-localization.test.tsx`, `runner-localization.test.tsx`, `localization-matrix.test.tsx` | Focused bilingual presentation and state-preservation regressions. |

| Modify | Single responsibility in this change |
| --- | --- |
| `frontend/src/app/layout.tsx` | Provider placement, deterministic theme bootstrap and server footer year. |
| `frontend/src/app/globals.css` | Horizontal shell, paper palette, scale/rhythm and explicit exam compatibility. |
| `frontend/src/components/ui/app-shell.tsx` | Route exclusions, content width and shell composition. |
| `frontend/src/components/ui/theme-toggle.tsx` | Deterministic reconciliation and localized next-action copy. |
| `frontend/src/components/ui/page-heading.tsx`, `empty-state.tsx` | ReactNode text slots for server UiText/raw authored content. |
| `frontend/src/components/ui/module-badge.tsx`, `status-badge.tsx` | Optional translated display labels with enum-based styling retained. |
| `frontend/src/components/ui/confirm-dialog.tsx` | Localized default common labels, existing focus/pending behavior intact. |
| `frontend/src/components/home/interactive-planet.tsx` | Existing generic accessible copy only; motion/identity untouched. |
| `frontend/src/features/auth/auth-provider.tsx` | Translate only locally owned session-error fallback at presentation, retaining request lifecycle. |
| `frontend/src/app/page.tsx`, `library/page.tsx`, `library/[versionId]/page.tsx` | Retain server loading/guards and hand presentation to cohesive client views. |
| `frontend/src/app/practice/page.tsx`, `history/page.tsx`, `analytics/page.tsx`, `transfer/page.tsx` | Server static headings via UiText. |
| `frontend/src/app/profile/page.tsx` | Existing client form copy; input values and request effects intact. |
| `frontend/src/app/login/page.tsx`, `register/page.tsx`, `session/restore/page.tsx` | Static Suspense fallback copy only. |
| `frontend/src/features/auth/auth-form.tsx`, `session-restore.tsx` | Auth/restore chrome and local fallback copy. |
| `frontend/src/features/practice/skill-practice.tsx`, `start-focused-practice.tsx` | Filter/card/start text without changing filtering, targets or timers. |
| `frontend/src/features/history/attempt-history-list.tsx` | Four tabs, status/action/confirmation copy. |
| `frontend/src/features/analytics/analytics-dashboard.tsx` | Generic metrics/filter/chart/control labels; chart data unchanged. |
| `frontend/src/features/exam/start-attempt.tsx`, `start-full-mock.tsx` | Start/timer/readiness presentation; attempt requests unchanged. |
| `frontend/src/features/exam/focused-attempt.ts` | Pure display helpers accept an optional translator; score arithmetic unchanged. |
| `frontend/src/features/test-builder/content-summary.tsx` | Typed generated unit headings, shared summary presentation and raw authored excerpts. |
| `frontend/src/app/admin/page.tsx`, `admin/users/[userId]/page.tsx` | Server loading/guards retained, AdminContent presentation boundary. |
| `frontend/src/app/admin/tests/page.tsx`, `admin/tests/new/page.tsx`, `admin/tests/[testId]/page.tsx`, `admin/tests/[testId]/versions/[versionId]/edit/page.tsx` | Major Builder route text only. |
| `frontend/src/features/auth/admin-guard.tsx`, `admin-user-list.tsx`, `admin-user-actions.tsx` | Existing guard/list/common user-action copy. |
| `frontend/src/features/test-builder/test-library-list.tsx`, `new-test-form.tsx`, `test-details-heading.tsx`, `version-actions.tsx`, `builder-workspace-navigation.tsx`, `builder-lifecycle.tsx`, `autosave-link.tsx` | First-pass list/metadata/version/tab/save-state chrome, preserving lifecycle logic. |
| `frontend/src/features/test-builder/reading-builder.tsx`, `listening-builder.tsx`, `writing-builder.tsx`, `module-duration-editor.tsx`, `listening-section-editor.tsx` | Top-level module/create/delete/duration labels only; nested tools/guidance deferred. |
| `frontend/src/features/transfer/transfer-portal.tsx` | Existing import/export/file/common result copy. |
| `frontend/src/features/reading/reading-runner.tsx`, `reading-review.tsx` | Static runner/review strings and accessible labels only. |
| `frontend/src/features/listening/listening-runner.tsx`, `listening-review.tsx`, `audio-player.tsx` | Static controls/fallback copy; existing three playback states unchanged. |
| `frontend/src/features/writing/writing-runner.tsx`, `writing-review.tsx` | Static controls/review chrome; prompts/responses/assessment data preserved. |
| `frontend/src/features/exam/pause-attempt-control.tsx`, `paused-attempt-gate.tsx`, `draft-recovery-notices.tsx`, `test-session-transition.tsx`, `terminal-attempt-redirect.tsx`, `use-exam-submit.ts` | Existing common static state/error/action copy, without locale-dependent lifecycle effects. |
| `frontend/src/features/test-builder/draft-preview.tsx` | Common preview controls/generated labels only. |
| `frontend/src/features/highlighting/selectable-text.tsx` | Existing highlight action/dialog/error labels only; selected text and semantic offsets untouched. |
| `frontend/src/features/questions/renderers.tsx`, `note-completion-renderer.tsx`, `table-completion-renderer.tsx`, `diagram-labelling-renderer.tsx` | Generic Question accessible names and empty answer-selector placeholders only; authored content, IELTS option values and renderer layout unchanged. |

Existing test files to modify are named in each task's **Files** block. No app route for attempt/review/test-session/preview needs a localization-driven fetching or dispatch change; their existing tests remain regression targets. Specialized question editor files are not translation targets. ListeningSectionEditor is included only for top-level section chrome; its range fields, capture/preview controls, validation guidance and range behavior remain deferred/unchanged.

## Locked Shared Interfaces

Task 1 owns these exports; later tasks must consume these names and types:

```ts
// en.ts / vi.ts: named exports en and vi; types.ts imports en as a type.
export type Locale = "en" | "vi";
export type TranslationKey = keyof typeof en;
export type TranslationDictionary = Record<TranslationKey, string>;
export type TranslationParams = Record<string, string | number>;
export type TranslationFunction = (
  key: TranslationKey, params?: TranslationParams,
) => string;

// translations.ts
export function translate(
  locale: Locale, key: TranslationKey, params?: TranslationParams,
): string;
export const moduleTranslationKeys: Record<"READING" | "LISTENING" | "WRITING", TranslationKey>;
export const statusTranslationKeys: Readonly<Record<string, TranslationKey>>;

// locale-provider.tsx ("use client")
export function LocaleProvider(props: { children: ReactNode }): ReactElement;
export function useLocale(): { locale: Locale; setLocale(locale: Locale): void };
export function useTranslation(): { t: TranslationFunction };
export function UiText(props: {
  message: TranslationKey; params?: TranslationParams;
}): ReactElement;
```

English uses `as const`; Vietnamese uses `satisfies TranslationDictionary`, not English literal-value types. UiText returns a fragment of escaped text. Context defaults to English with a no-op setter outside a provider, keeping existing isolated English component tests compatible; production always supplies the root provider. No HTML translation API. `translate` replaces named `{parameter}` tokens, retains an unresolved token if a parameter is absent, and defensively falls back to English for a missing runtime dictionary entry. Singular/plural use explicit keys selected by existing counts. No number/date-format changes.

Task 2 produces `AppShell({ children, currentYear }: { children: ReactNode; currentYear: number }): ReactElement`; RootLayout supplies the year once on the server. Task 3 produces `GlobalHeader({ pathname }: { pathname: string }): ReactElement`. Task 4 produces `AppFooter({ year }: { year: number }): ReactElement`. All are named exports; none is keyed by a preference.

Task 8 widens PageHeading's `eyebrow?: ReactNode`, `title: ReactNode`, `description?: ReactNode` and EmptyState's `title: ReactNode`, `description: ReactNode`; other props stay unchanged. ModuleBadge adds `label?: ReactNode` to its existing module prop; StatusBadge adds `label?: ReactNode` to its existing status prop. They remain server-compatible, use the override when supplied, and retain English fallback display for unconverted/deferred callers.

Task 9's client presentation exports are fixed:

```ts
export function OverviewContent(props: {
  publishedCount: number; resumableCount: number; testCount: number;
  isAdmin: boolean; adminStats: AdminStats | null; profile: Profile | null;
}): ReactElement;
export function LibraryContent(props: {
  items: Array<{
    test: TestSummary; version: TestSummary["versions"][number]; detail: VersionDetail;
  }>;
}): ReactElement;
export function LibraryVersionContent(props: {
  test: TestSummary; version: VersionDetail;
}): ReactElement;
```

Use type-only imports of existing DTOs. Server routes still choose published versions, fetch records, apply role branches and call notFound. The views preserve existing calculation/ordering rules; no API function/server module enters them. Task 10's `AdminDashboardContent` props are `{ stats: AdminStats | null; users: AdminUserList | null; search: string; status: "active" | "deactivated"; offset: number }`; `AdminUserDetailContent` props are `{ detail: AdminUserDetail }`, both returning ReactElement from `admin-content.tsx`. Preserve the existing user-list key `${status}:${search}:${offset}`.

Task 9 extends only the pure display helpers:

```ts
export function focusedUnitLabel(
  attempt: Pick<AttemptResponse, "scope" | "focused_unit">,
  t?: TranslationFunction,
): string | null;
export function accuracyLabel(
  raw: number | null, max: number | null, t?: TranslationFunction,
): string | null;
```

Default translator is English. Generate unit labels from the existing `kind` and `order_index + 1`; keep any authored `title` verbatim beside the label, and preserve null/empty behavior. Never parse/translate a server label or title to discover its kind. Accuracy keeps the same null guard and `(raw / max * 100).toFixed(1)` calculation. Existing request/runner/player interfaces are otherwise unchanged.

## Tasks

### Task 1: Typed i18n foundation

**Files:**
- Create: `frontend/src/lib/i18n/en.ts`, `vi.ts`, `types.ts`, `translations.ts`, `locale-provider.tsx`.
- Test (create): `frontend/tests/translations.test.ts`, `locale-provider.test.tsx`, `locale-test-utils.tsx`.

**Interfaces:**
- Consumes: React context/effects and existing Vitest/RTL setup.
- Produces: All Task 1 exports in Locked Shared Interfaces; `LocaleControls` test-only component using useLocale and `renderWithLocale(ui: ReactElement): RenderResult` in `locale-test-utils.tsx`, which renders one provider with stable children plus those controls.

- [ ] **Step 1: Write the failing test**

Name tests `dictionaries have identical complete keys`, `interpolates scalar parameters as plain text`, `locale starts in English without render-time storage`, `restores only en or vi after mount`, and `locale storage failures are non-fatal`. Assert `Pause` / `Tạm dừng`, `Question {number}` / `Câu hỏi {number}` with number 2, absent-token retention, escaped `<img>` parameter, no read in SSR, VI restore/root lang, invalid/null => en, no default write before restore, and throwing storage getter/getItem/setItem. A failed write still updates UI/lang; no banner appears. A child mount counter remains one after toggles. Use renderToString plus hydrateRoot for deterministic first markup, not a snapshot.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/translations.test.ts tests/locale-provider.test.tsx`

Expected: FAIL because the dictionary/provider exports do not exist.

- [ ] **Step 3: Implement the minimal change**

Implement the locked signatures and seed paired `common.*`, `shell.*`, `theme.*`, `footer.*` and runner control keys needed by early tests. Grow both dictionaries alongside their consumers in later tasks. Use state initialized to en, one mount restoration effect, validated exact values and separately caught persistence writes. Update root lang in an effect; never inspect storage at import/render/state initialization or overwrite saved VI with default EN. Keep setLocale stable, derive t from current locale, and render UiText as a fragment. Define enum maps once, preserving codes and styling. The test harness switches the same provider instance rather than rerendering keyed children.

- [ ] **Step 4: Run focused tests**

Run: `npx vitest run tests/translations.test.ts tests/locale-provider.test.tsx`

Expected: PASS, including restoration, escaping and mount identity; typecheck validates Vietnamese key parity.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/lib/i18n frontend/tests/translations.test.ts frontend/tests/locale-provider.test.tsx frontend/tests/locale-test-utils.tsx
git commit -m "Add typed English and Vietnamese UI translations"
```

### Task 2: Root layout and preference hydration

**Files:**
- Modify: `frontend/src/app/layout.tsx`, `frontend/src/components/ui/app-shell.tsx`, `theme-toggle.tsx`, `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test: `frontend/tests/root-layout.test.tsx`, `theme-toggle.test.tsx`, `auth.test.tsx`, `locale-provider.test.tsx`, `builder-route.test.tsx`, `profile.test.tsx`, `skill-practice.test.tsx`, `transfer-portal.test.tsx`.

**Interfaces:**
- Consumes: LocaleProvider/useTranslation from Task 1; unchanged AuthProvider and `themeInitializationScript` export.
- Produces: Required AppShell currentYear prop; deterministic two-theme bootstrap and ThemeToggle next-action labels.

- [ ] **Step 1: Write the failing test**

Extend root-layout tests: provider nesting is LocaleProvider → AuthProvider → AppShell; server lang/text/theme remain en/light even with stored VI/dark; server supplies a frozen test year (2026). Evaluate the trusted bootstrap against mocked storage: saved light/dark wins; absent, corrupt and throwing reads select light even if mocked OS prefers dark; script contains no matchMedia or locale text rewriting. ThemeToggle starts with deterministic light markup, reconciles root dark after mount, shows `Use light theme`, toggles despite setItem failure and never writes/reads locale storage. Update every existing AppShell fixture in auth, builder-route, profile, skill-practice and transfer-portal tests with `currentYear={2026}` so the intermediate commit typechecks.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/root-layout.test.tsx tests/theme-toggle.test.tsx tests/auth.test.tsx tests/locale-provider.test.tsx tests/builder-route.test.tsx tests/profile.test.tsx tests/skill-practice.test.tsx tests/transfer-portal.test.tsx`

Expected: FAIL on missing provider/year and existing implicit OS-dark branch.

- [ ] **Step 3: Implement the minimal change**

Wrap the existing tree without moving server API loading into clients. Pass `new Date().getFullYear()` from RootLayout to AppShell, which accepts it before footer integration. Keep the inline bootstrap in its trusted existing position and root-only suppressHydrationWarning; select saved valid theme or light in the catch/default branches. ThemeToggle initializes React state light, uses a post-hydration layout effect to reconcile data-theme and updates state/root synchronously on click before best-effort storage. Localize the next-action visible/accessible label without adding a theme provider or changing runner placement. Keep AuthProvider mounted across preference changes.

- [ ] **Step 4: Run focused tests**

Run: `npx vitest run tests/root-layout.test.tsx tests/theme-toggle.test.tsx tests/auth.test.tsx tests/locale-provider.test.tsx tests/builder-route.test.tsx tests/profile.test.tsx tests/skill-practice.test.tsx tests/transfer-portal.test.tsx`

Expected: PASS with no hydration-text suppression or preference-driven auth request.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/app/layout.tsx frontend/src/components/ui/app-shell.tsx frontend/src/components/ui/theme-toggle.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/root-layout.test.tsx frontend/tests/theme-toggle.test.tsx frontend/tests/auth.test.tsx frontend/tests/locale-provider.test.tsx frontend/tests/builder-route.test.tsx frontend/tests/profile.test.tsx frontend/tests/skill-practice.test.tsx frontend/tests/transfer-portal.test.tsx
git commit -m "Make locale and theme hydration deterministic"
```

### Task 3: Global header and horizontal navigation

**Files:**
- Create: `frontend/src/components/ui/global-header.tsx`.
- Modify: `frontend/src/components/ui/app-shell.tsx`, `frontend/src/app/globals.css`, `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test (create): `frontend/tests/app-shell.test.tsx`; modify `frontend/tests/auth.test.tsx` and affected shell expectations in `dark-theme-css.test.ts`.

**Interfaces:**
- Consumes: AppShell currentYear, existing useAuth/logout, ThemeToggle, AppLogo/icons, `TRANSFER_ROUTE`, useLocale/useTranslation.
- Produces: GlobalHeader(pathname); local PrimaryNavigation/HeaderActions/LocaleSwitcher functions, one nav and stable route-based item identity.

- [ ] **Step 1: Write the failing test**

Add `guest user and admin navigation preserve routes`, `admin active matching is exact`, `admin Vietnamese navigation preserves all routes`, and `attempt routes bypass global chrome`. Guests get Overview plus Login/Register; loading/error never exposes privileged links. USER gets `/`, `/library`, `/practice`, `/history`, `/analytics`; ADMIN adds `/admin`, `/admin/tests`, `/transfer` in that order. `/admin` matches exactly; Builder matches descendants without also activating Admin. Assert all non-home links keep prefetch false, one Primary landmark, aria-current and stable link nodes across EN/VI. Assert no global aside, duplicate Workspace/current-section context or Built for focus note. Retain logout single-call/pending/cancel/focus tests. A long display name stays accessible. Locale controls have EN/VI, full language names, lang and aria-pressed, no flags/menu role.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/app-shell.test.tsx tests/auth.test.tsx tests/dark-theme-css.test.ts`

Expected: FAIL on the current sidebar, absent locale buttons and header context.

- [ ] **Step 3: Implement the minimal change**

Move shell header/auth/logout presentation into GlobalHeader, preserving its guarded pending ref and ConfirmDialog lifecycle. Use route href as nav key and dictionary keys for labels; keep local functions in this file. Brand is the existing planet + IELTS Studio, without repeated tagline. Render brand, one text-first nav and actions; actions order locale, theme, user, logout, with guest auth alternatives. Preserve session errors and role visibility. AppShell retains its early `/attempt/` main.exam-shell return and otherwise composes header/main. Remove only global sidebar markup/rules; keep Practice filters and Builder local navigation. Supply minimal one-column/header flex styling now; Task 5 adds the exact responsive contracts. Replace removed-sidebar assertions in the affected dark CSS test now.

- [ ] **Step 4: Run focused tests**

Run: `npx vitest run tests/app-shell.test.tsx tests/auth.test.tsx tests/dark-theme-css.test.ts`

Expected: PASS for routes, roles, EN/VI nav, logout and attempt bypass.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/components/ui/global-header.tsx frontend/src/components/ui/app-shell.tsx frontend/src/app/globals.css frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/app-shell.test.tsx frontend/tests/auth.test.tsx frontend/tests/dark-theme-css.test.ts
git commit -m "Replace the workspace sidebar with horizontal navigation"
```

### Task 4: Shared footer and exact route exclusions

**Files:**
- Create: `frontend/src/components/ui/app-footer.tsx`.
- Modify: `frontend/src/components/ui/app-shell.tsx`, `frontend/src/app/globals.css`, `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test (create): `frontend/tests/app-footer.test.tsx`; modify `frontend/tests/app-shell.test.tsx`, `root-layout.test.tsx`.

**Interfaces:**
- Consumes: Server currentYear, useLocale/useTranslation and usePathname.
- Produces: AppFooter(year); local `isBuilderPreview(pathname: string): boolean` in AppShell, using `^/admin/tests/[^/]+/versions/[^/]+/preview/?$`.

- [ ] **Step 1: Write the failing test**

Add `only exact Builder preview suppresses the global footer`: attempt IDs (including paused/terminal children) get no header/footer; exact preview with optional trailing slash gets global header and existing local .exam-footer only. Builder edit/detail/list/new, `/review/id`, `/test-session/id`, `/session/restore`, auth/profile/transfer and misleading paths containing `preview` retain global footer. Query selection does not change pathname matching. Assert product name, 2026 prop, `Practice & authoring` / `Luyện tập và biên soạn đề` and English/Tiếng Việt indication; no invented legal/social links. SSR and first client footer use the same year.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/app-footer.test.tsx tests/app-shell.test.tsx tests/root-layout.test.tsx tests/draft-preview.test.tsx`

Expected: FAIL because the shared footer and exact preview exclusion do not exist.

- [ ] **Step 3: Implement the minimal change**

Compose AppFooter after growing main on all normal routes, excluding only the exact regex above. Keep attempts on their existing early bypass and preserve DraftPreview's local footer untouched. Footer uses server year, product identity/description and locale indication, with no second selector. Add opaque surface/top border, 24px vertical padding, desktop left/right groups and small stacked groups with 12px gap. No client clock, auth-dependent footer omission or broad substring matching.

- [ ] **Step 4: Run focused tests**

Run: `npx vitest run tests/app-footer.test.tsx tests/app-shell.test.tsx tests/root-layout.test.tsx tests/draft-preview.test.tsx`

Expected: PASS across exact exclusions and ordinary routes.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/components/ui/app-footer.tsx frontend/src/components/ui/app-shell.tsx frontend/src/app/globals.css frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/app-footer.test.tsx frontend/tests/app-shell.test.tsx frontend/tests/root-layout.test.tsx
git commit -m "Add the shared footer with exam route exclusions"
```

### Task 5: Shell widths and responsive composition

**Files:**
- Modify: `frontend/src/components/ui/app-shell.tsx`, `global-header.tsx`, `frontend/src/app/globals.css`.
- Test (create): `frontend/tests/shell-layout-css.test.ts`; modify `frontend/tests/app-shell.test.tsx`, affected width assertions in `visual-system-css.test.ts`.

**Interfaces:**
- Consumes: One header/nav/footer DOM and exact exclusion predicates.
- Produces: Local `contentWidth(pathname: string): "standard" | "wide"`, classes `.app-content-standard` / `.app-content-wide`; CSS-only breakpoint composition.

- [ ] **Step 1: Write the failing test**

Add `page family selects the approved width` and `header wraps at approved breakpoints`. Standard outer width is 1280 for Overview/review/ordinary detail/forms; wide 1440 for Library list, Practice, History, Analytics, Admin lists/dashboard, Builder workspaces and Transfer. Explicit published `/library/[id]`, `/admin/users/[id]` and `/admin/tests/[id]` detail routes and `/admin/tests/new` stay standard; version edit/preview stay wide. Profile inner 920, new-test inner 720, auth inner 480 and transition inner 720. Assert border-box maxima include padding and descriptive prose <=72ch; attempts get no width class/padding. Read CSS declarations to prove >=1440, 768–1439 and <768 rules, wrapping/auto heights, no nav overflow clipping or nowrap, small non-sticky header, username maxima 120/96, one nav DOM and no width-dependent JS. RTL keeps all eight Vietnamese ADMIN links plus actions in DOM with long text; this is a structural test, not a claim of measured wrapping.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/shell-layout-css.test.ts tests/app-shell.test.tsx tests/visual-system-css.test.ts`

Expected: FAIL on missing width classes and current shell spacing/responsive rules.

- [ ] **Step 3: Implement the minimal change**

Classify paths locally with the named detail/new-form exceptions before wide families; no route registry abstraction. Use min-height:100vh fallback followed by 100dvh, one column, main flex-grow, centered border-box containers. Header/footer max 1440. Horizontal/top/bottom main padding: desktop 32/40/48, medium 24/32/40, small 16/24/32. Desktop has a 72px minimum header height, automatic actual height and can fit brand/nav/actions on one row while wrapping naturally with VI. Medium keeps the sticky header as one auto-height unit, brand/actions first then nav with 8px horizontal/4px vertical gaps. Small uses brand, actions, wrapped nav below with no sticky positioning; at 320px several rows are allowed and targets remain 44px. Use one nav and flex/grid CSS, no drawer or window.innerWidth. Keep full username accessible while visual text ellipsizes; nav labels wrap at words without ellipsis. Apply inner form maxima/prose <=72ch to existing classes and replace fixed global-sidebar width assertions, preserving feature-local layout rules.

- [ ] **Step 4: Run focused tests**

Run: `npx vitest run tests/shell-layout-css.test.ts tests/app-shell.test.tsx tests/visual-system-css.test.ts`

Expected: PASS for widths, breakpoint source contracts and reachable long-language navigation.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/components/ui/app-shell.tsx frontend/src/components/ui/global-header.tsx frontend/src/app/globals.css frontend/tests/shell-layout-css.test.ts frontend/tests/app-shell.test.tsx frontend/tests/visual-system-css.test.ts
git commit -m "Apply responsive horizontal shell widths and spacing"
```

### Task 6: Paper theme tokens and explicit exam compatibility

**Files:**
- Modify: `frontend/src/app/globals.css`.
- Test: `frontend/tests/visual-system-css.test.ts`, `dark-theme-css.test.ts`, `exam-theme-css.test.ts`, `shell-layout-css.test.ts`.

**Interfaces:**
- Consumes: Approved spec palette/shadow tables and current stylesheet's shared/exam consumers.
- Produces: Exact light/dark paper tokens, scoped frozen exam values, opaque surfaces and neutral shadows; no component API change.

- [ ] **Step 1: Write the failing test**

Replace old palette expectations with the complete approved light/dark token tables, including light bg `#f5f2eb`, muted `#686155`, writing `#99562e`, line-strong `#8f8575`; dark bg `#201e1b`, muted `#b4aa9a`, writing `#d2ab8b`, line-strong `#8d8070`. Add `paper tokens cannot change resolved exam colors or controls`: capture current root/shared values used by .exam-shell/.exam-runner before editing, resolve their scoped light/dark declarations and compare after. Cover embedded Builder preview and paused gate; dark exam-accent must resolve to `#9aa6e8`, never new workspace `#a4afd9`. Freeze all --exam-* and highlight values, module accents, control/button/focus values and 15px exam body. Workspace contrast tests cover normal/hover text >=4.5 and meaningful border/focus >=3, including 8% module mixes and status soft fills; exam checks preserve the existing baseline rather than redesigning controls. Remove only superseded atmosphere/glow expectations.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts`

Expected: FAIL on current galaxy palette and unprotected inherited exam aliases.

- [ ] **Step 3: Implement the minimal change**

Copy every exact workspace value from the spec's palette tables; preserve established token names and compatible aliases. Copy approved neutral shadows: light sm/md/lg offsets 0 1px 3px / 0 4px 12px / 0 12px 32px with rgb(41 38 32) alpha .07/.08/.16; dark same offsets rgb(0 0 0) alpha .16/.20/.30. Glass is opaque; deprecated glow aliases become neutral shadow-sm. Freeze current shared properties actually inherited by exam-shell/runner (ink/surfaces/lines/module/status/contrast/shadows) with explicit scoped light/dark values. Keep --exam-bg/surface/alt/text/muted/border/control-bg/control-text/accent and highlights at the spec's frozen exam values; detach dark exam-accent from workspace accent. Apply compatibility inside nested preview as well as attempts, without new ExamShell or renderer rewrites.

Remove body/shell ambient radials, shell atmospheric pseudo-element, header/toolbar blur, hero ambient/diagonal decoration, colored shadows and decorative card gradients in both themes. Keep the SVG planet and motion classes; remove ambient orbit glow, use a quiet solid core and no colored drop-shadow. Flatten card accents/empty/history/Builder/passage decoration to approved surfaces; preserve functional progress/charts/selection/focus/correctness/highlights. Retain existing exam responsive rules and explicit control appearance; ordinary review chrome can use paper surfaces.

- [ ] **Step 4: Run focused tests**

Run: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts tests/app-logo.test.tsx tests/interactive-planet.test.tsx`

Expected: PASS with palette/contrast arithmetic and current exam baseline preserved, plus intact SVG/motion behavior.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/app/globals.css frontend/tests/visual-system-css.test.ts frontend/tests/dark-theme-css.test.ts frontend/tests/exam-theme-css.test.ts frontend/tests/shell-layout-css.test.ts
git commit -m "Introduce paper and graphite themes with exam isolation"
```

### Task 7: Typography, buttons and shared visual primitives

**Files:**
- Modify: `frontend/src/app/globals.css`, `frontend/src/features/test-builder/content-summary.tsx`.
- Test: `frontend/tests/visual-system-css.test.ts`, `dark-theme-css.test.ts`, `exam-theme-css.test.ts`, `shell-layout-css.test.ts`.

**Interfaces:**
- Consumes: Workspace/exam token separation and existing primitive classes.
- Produces: Approved workspace font/scale/button/radius/rhythm contracts; no component prop change yet.

- [ ] **Step 1: Write the failing test**

Assert Segoe-first local stack with no Inter/font fetch; body 16/400/1.6, meta 13/400 or emphasis 500/1.5, nav 14/500 and active600/1.4, buttons14/600/1.4, eyebrow13/500/1.5/.01em, H1 32 (small28)/600/1.2/-.02em, H2 22 (small20)/600/1.3/-.01em, H3 18/600/1.35/-.01em, label14/500/1.4, status12/500/1.4 and module12/600/1.4/tracking<=.02em. Assert sentence case except short module labels, no uppercase authored-content rule, buttons radius8/min40 and small header target44, no hover transform/glow, cards12/fields8/dialogs14. Retain exam body15 and its existing metrics. Check PageHeading bottom24, eyebrow gap8, description12; form fields16/groups24; gaps follow the 4px scale, with compact Practice gap16 intact.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts`

Expected: FAIL on old weights/tracking/uppercase and control radii.

- [ ] **Step 3: Implement the minimal change**

Apply the exact scale above to normal workspace selectors, excluding .exam-shell/.exam-runner descendants and preserving compatibility overrides from Task 6. Use `"Segoe UI Variable", "Segoe UI", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif`. Remove ContentSummary's uppercase/tracking utility treatment from generated headings rather than case-transforming authored strings. Flatten primary/secondary/ghost/danger/danger-ghost/Listening/Writing buttons; padding14, icon gap8, 120–160ms color/surface transition, no lift. Default cards have no shadow; raised cards sm, overlays md, dialogs lg. Apply field/form/heading rhythm and gaps8/12/16/24/32/48 in their approved contexts. Limit 700 to meaningful metrics; preserve tabular numeric values and focus/reduced-motion support.

- [ ] **Step 4: Run focused tests**

Run: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts tests/builder-workspace-page.test.tsx tests/skill-practice.test.tsx`

Expected: PASS; useful old CSS assertions are replaced intentionally, not discarded wholesale.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/app/globals.css frontend/src/features/test-builder/content-summary.tsx frontend/tests/visual-system-css.test.ts frontend/tests/dark-theme-css.test.ts frontend/tests/exam-theme-css.test.ts frontend/tests/shell-layout-css.test.ts
git commit -m "Apply the workspace typography and primitive scale"
```

### Task 8: Shell and common copy localization

**Files:**
- Modify: `frontend/src/components/ui/global-header.tsx`, `app-shell.tsx`, `app-footer.tsx`, `theme-toggle.tsx`, `page-heading.tsx`, `empty-state.tsx`, `module-badge.tsx`, `status-badge.tsx`, `confirm-dialog.tsx`; `frontend/src/components/home/interactive-planet.tsx`; `frontend/src/features/auth/auth-provider.tsx`; `frontend/src/lib/i18n/en.ts`, `vi.ts`, `translations.ts`.
- Test (create): `frontend/tests/common-localization.test.tsx`; modify `frontend/tests/app-shell.test.tsx`, `app-footer.test.tsx`, `theme-toggle.test.tsx`, `status-badge.test.tsx`, `auth.test.tsx`, `interactive-planet.test.tsx`, `translations.test.ts`.

**Interfaces:**
- Consumes: Task 1 hooks/UiText and enum maps; header/footer already use keys from Tasks 3–4.
- Produces: Locked ReactNode slots/optional badge labels; translated common default dialog labels and complete shell copy.

- [ ] **Step 1: Write the failing test**

Add `common primitives accept translated nodes and raw authored titles`, `open logout dialog changes language without recreation`, and `locale switch does not recheck auth`. Keep user display name unchanged; role labels, next-theme action, language group, brand accessible name, footer description and logout title/description/pending/cancel update together. Switch with dialog open: same dialog node, cancel remains focused, Tab/Escape/pending rules preserved and logout request remains single-call. Assert enum styles/unknown fallback survive optional badge labels. SSR PageHeading/EmptyState can receive UiText fragments or raw strings without wrapper/layout changes. Unknown server session diagnostics remain exact; only the owned fallback translates. Theme and locale storage remain independent.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/common-localization.test.tsx tests/app-shell.test.tsx tests/app-footer.test.tsx tests/theme-toggle.test.tsx tests/status-badge.test.tsx tests/auth.test.tsx tests/interactive-planet.test.tsx tests/translations.test.ts`

Expected: FAIL on string-only primitive props and remaining static shared dialog/accessibility copy.

- [ ] **Step 3: Implement the minimal change**

Widen only locked text slots and add optional badge display labels; keep markup/classes/styles and enum inputs unchanged. ConfirmDialog translates Cancel/Working defaults at render, still honoring explicit caller overrides and preserving effects keyed to open/pending/callbacks. Finish common/shell dictionaries and presentation slots, including theme/accessibility/skip-link labels. Keep skip link on normal shell only, targeting existing main `id="main-content"`. AuthProvider stores a distinguishable owned fallback state versus raw diagnostic and resolves the fallback at presentation; t/locale never enter auth loading/logout/refresh effect or callback dependencies. Translate the planet's existing generic accessible copy without changing pointer/reduced-motion effects. No arbitrary string-to-translation matching, function passed through server props or broadly clientified primitive.

- [ ] **Step 4: Run focused tests**

Run the Step 2 command plus `npx vitest run tests/root-layout.test.tsx tests/locale-provider.test.tsx`.

Expected: PASS for common EN/VI UI, SSR boundaries, focus and stable auth identity.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/components/ui/global-header.tsx frontend/src/components/ui/app-shell.tsx frontend/src/components/ui/app-footer.tsx frontend/src/components/ui/theme-toggle.tsx frontend/src/components/ui/page-heading.tsx frontend/src/components/ui/empty-state.tsx frontend/src/components/ui/module-badge.tsx frontend/src/components/ui/status-badge.tsx frontend/src/components/ui/confirm-dialog.tsx frontend/src/components/home/interactive-planet.tsx frontend/src/features/auth/auth-provider.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/src/lib/i18n/translations.ts frontend/tests/common-localization.test.tsx frontend/tests/app-shell.test.tsx frontend/tests/app-footer.test.tsx frontend/tests/theme-toggle.test.tsx frontend/tests/status-badge.test.tsx frontend/tests/auth.test.tsx frontend/tests/interactive-planet.test.tsx frontend/tests/translations.test.ts
git commit -m "Localize shared shell and common UI copy"
```

### Task 9: Main workspace page localization

**Files:**
- Create: `frontend/src/components/home/overview-content.tsx`, `frontend/src/features/practice/library-content.tsx`.
- Modify: `frontend/src/app/page.tsx`, `library/page.tsx`, `library/[versionId]/page.tsx`, `practice/page.tsx`, `history/page.tsx`, `analytics/page.tsx`, `profile/page.tsx`, `login/page.tsx`, `register/page.tsx`, `session/restore/page.tsx`; `frontend/src/features/auth/auth-form.tsx`, `session-restore.tsx`; `frontend/src/features/practice/skill-practice.tsx`, `start-focused-practice.tsx`; `frontend/src/features/history/attempt-history-list.tsx`; `frontend/src/features/analytics/analytics-dashboard.tsx`; `frontend/src/features/exam/start-attempt.tsx`, `start-full-mock.tsx`, `focused-attempt.ts`; `frontend/src/features/test-builder/content-summary.tsx`; `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test (create): `frontend/tests/workspace-localization.test.tsx`; modify `frontend/tests/home-user-metric.test.tsx`, `practice-library.test.tsx`, `skill-practice.test.tsx`, `attempt-history-list.test.tsx`, `analytics-dashboard.test.tsx`, `profile.test.tsx`, `auth.test.tsx`, `auth-session-restore.test.tsx`, `translations.test.ts`.

**Interfaces:**
- Consumes: UiText/ReactNode server slots, useTranslation, badge overrides and common enum maps.
- Produces: Locked OverviewContent/LibraryContent/LibraryVersionContent and optional translator display helpers. ContentSummary's existing SummaryUnit becomes exported with `heading: { message: "common.passageNumber" | "common.sectionNumber" | "common.taskNumber"; params: { number: number } }`; other fields stay unchanged. Both pure summary builders return that type; ContentSummary is a client presentation component and keys units by message+number, not translated text.

- [ ] **Step 1: Write the failing test**

Add `workspace locale changes copy without changing selected state` and `generated labels translate while authored titles stay exact`. Exercise Overview headings/goals, Library list/detail/empty/readiness, Practice filters/search/counts/timers/audio helpers, all four History tabs/actions/statuses, Analytics generic labels, Profile/auth/restore chrome. Store a Practice query, skill/unit filter and nondefault timer; switch and assert unchanged selected cards/IDs/request input. Preserve History tab and open delete dialog, Analytics selection and Profile input draft. Fictional title `Section 2` remains exactly `Section 2` when authored, while generated Section 2 becomes `Phần 2`; include accents/HTML-like text/prompt excerpts/options. Compare serialized DTO fixtures before/after. Locally built fallback description translates only when authored description is null. Mock server routes once and assert switches do not rerun fetchers or startAttempt. Auth/restore effects do not restart; default restore text becomes English rather than current Vietnamese-only copy.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/workspace-localization.test.tsx tests/home-user-metric.test.tsx tests/practice-library.test.tsx tests/skill-practice.test.tsx tests/attempt-history-list.test.tsx tests/analytics-dashboard.test.tsx tests/profile.test.tsx tests/auth-session-restore.test.tsx tests/translations.test.ts`

Expected: FAIL on remaining English literals and untyped generated summary headings.

- [ ] **Step 3: Implement the minimal change**

Move only Overview and Library presentation into the locked cohesive client files so their native aria-labels and labels can use t. Keep async fetching, published-version filtering, role-conditioned stats/profile loading, guard/notFound and serializable DTOs on the server. Other server pages pass UiText for headings and Suspense fallbacks; existing client features translate at their current slots. Preserve sort/search algorithms and original searchable authored data; never derive filter matching from newly translated labels. Use route/enum/UUID identity instead of translated titles for generated list keys.

Cover every included row of spec section 11 for these pages. Add paired `pages.*`, `practice.*`, `history.*`, `analytics.*`, `profile.*`, `auth.*` keys and shared generated unit/count/accuracy keys. Keep field values, raw scores and date formats intact. Summary builders carry heading descriptors rather than English strings; only application-owned type/category labels map to keys locally in summary/card presentation, leaving registry instruction templates and editor helpers untouched. Extend focusedUnitLabel/accuracyLabel as locked, with English default and current mathematical behavior. Client start views construct translated readiness prose from existing modules/counts but retain identical availability/timer/request rules. Local fallback/error state stores a key/branch, rendering through t; unknown server messages stay raw and t never enters request dependencies.

- [ ] **Step 4: Run focused tests**

Run the Step 2 command plus `npx vitest run tests/auth.test.tsx tests/builder-workspace-page.test.tsx tests/focused-reading-review.test.tsx tests/focused-listening-review.test.tsx` to cover shared-summary/helper English compatibility.

Expected: PASS with state/content/payload preservation and unchanged focused availability/scoring.

- [ ] **Step 5: Commit**

```bash
git --literal-pathspecs add -- frontend/src/components/home/overview-content.tsx frontend/src/features/practice/library-content.tsx frontend/src/app/page.tsx frontend/src/app/library/page.tsx 'frontend/src/app/library/[versionId]/page.tsx' frontend/src/app/practice/page.tsx frontend/src/app/history/page.tsx frontend/src/app/analytics/page.tsx frontend/src/app/profile/page.tsx frontend/src/app/login/page.tsx frontend/src/app/register/page.tsx frontend/src/app/session/restore/page.tsx frontend/src/features/auth/auth-form.tsx frontend/src/features/auth/session-restore.tsx frontend/src/features/practice/skill-practice.tsx frontend/src/features/practice/start-focused-practice.tsx frontend/src/features/history/attempt-history-list.tsx frontend/src/features/analytics/analytics-dashboard.tsx frontend/src/features/exam/start-attempt.tsx frontend/src/features/exam/start-full-mock.tsx frontend/src/features/exam/focused-attempt.ts frontend/src/features/test-builder/content-summary.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/workspace-localization.test.tsx frontend/tests/home-user-metric.test.tsx frontend/tests/practice-library.test.tsx frontend/tests/skill-practice.test.tsx frontend/tests/attempt-history-list.test.tsx frontend/tests/analytics-dashboard.test.tsx frontend/tests/profile.test.tsx frontend/tests/auth.test.tsx frontend/tests/auth-session-restore.test.tsx frontend/tests/translations.test.ts
git commit -m "Localize main workspace pages and practice controls"
```

### Task 10: Admin, Builder and Transfer first-pass localization

**Files:**
- Create: `frontend/src/features/auth/admin-content.tsx`.
- Modify: `frontend/src/app/admin/page.tsx`, `admin/users/[userId]/page.tsx`, `admin/tests/page.tsx`, `admin/tests/new/page.tsx`, `admin/tests/[testId]/page.tsx`, `admin/tests/[testId]/versions/[versionId]/edit/page.tsx`, `transfer/page.tsx`; `frontend/src/features/auth/admin-guard.tsx`, `admin-user-list.tsx`, `admin-user-actions.tsx`; `frontend/src/features/test-builder/test-library-list.tsx`, `new-test-form.tsx`, `test-details-heading.tsx`, `version-actions.tsx`, `builder-workspace-navigation.tsx`, `builder-lifecycle.tsx`, `autosave-link.tsx`, `reading-builder.tsx`, `listening-builder.tsx`, `writing-builder.tsx`, `module-duration-editor.tsx`, `listening-section-editor.tsx`; `frontend/src/features/transfer/transfer-portal.tsx`; `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test: `frontend/tests/admin-dashboard.test.tsx`, `admin-user-list.test.tsx`, `admin-user-detail.test.tsx`, `test-library-list.test.tsx`, `version-actions.test.tsx`, `builder-workspace-navigation.test.tsx`, `builder-workspace-page.test.tsx`, `builder-autosave.test.tsx`, `module-duration-editor.test.tsx`, `transfer-portal.test.tsx`, `workspace-localization.test.tsx`, `translations.test.ts`.

**Interfaces:**
- Consumes: Locked AdminContent DTO props, shared summaries/keys and unchanged BuilderLifecycle/context APIs.
- Produces: Complete `admin.*`, `builder.*`, `transfer.*` first-pass keys; no editor/lifecycle/request API changes.

- [ ] **Step 1: Write the failing test**

Add bilingual assertions to existing feature fixtures for dashboard/guard/user roles and common dialogs; test-list tabs/search, new-test metadata, version Preview/Validate/Publish/Clone/Archive, Builder workspace tabs/module overview/create/delete/duration/save status and Transfer file/import/export/result controls. Switch while a metadata draft, Builder selected workspace, autosave pending request and Transfer selected file/version exist: values, keys, in-flight calls and file identity remain unchanged. Names/emails/test titles/descriptions/asset names/server validation diagnostics stay raw. A representative specialized editor's instructional text and authored template remain unchanged; shared Cancel may translate. Do not assert that every nested editor string is localized.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/admin-dashboard.test.tsx tests/admin-user-list.test.tsx tests/admin-user-detail.test.tsx tests/test-library-list.test.tsx tests/version-actions.test.tsx tests/builder-workspace-navigation.test.tsx tests/builder-workspace-page.test.tsx tests/builder-autosave.test.tsx tests/module-duration-editor.test.tsx tests/transfer-portal.test.tsx tests/workspace-localization.test.tsx tests/translations.test.ts`

Expected: FAIL on the included first-pass English literals, with specialized-editor baseline assertions still passing.

- [ ] **Step 3: Implement the minimal change**

Use AdminContent for coherent dashboard/detail native attributes and mixed system/user labels. Keep Admin/Transfer server layouts, search/offset validation, fetching/redirect/notFound and user-list key intact. Builder/Transfer server headings use UiText; existing clients use t in text slots. Modify BuilderLifecycle only its save-status presentation; keep queues/refs/callback dependencies/transitions unchanged. Translate top-level module and section create/delete labels in the listed editors without traversing question-group/answer-key/completion/diagram/audio-range guidance. Preserve strings used to initialize/persist test content, including ListeningSectionEditor's fallback title in fields(); translating a displayed label must not change a created title or mutation input. No registry, clone/ZIP, audio capture/reset, validation or specialized tool changes. Preserve authored instruction templates byte-for-byte; deferred specialized copy may retain its existing language, with no blanket English boundary surrounding translated controls. Reuse paired common actions rather than duplicating their keys.

- [ ] **Step 4: Run focused tests**

Run the Step 2 command plus `npx vitest run tests/builder-route.test.tsx tests/reading-builder-sync.test.tsx tests/listening-audio-ranges.test.tsx tests/writing-builder.test.tsx` as targeted invariants for touched top-level editor files.

Expected: PASS, including save/lifecycle/selection preservation and intact audio-range functionality.

- [ ] **Step 5: Commit**

```bash
git --literal-pathspecs add -- frontend/src/features/auth/admin-content.tsx frontend/src/app/admin/page.tsx 'frontend/src/app/admin/users/[userId]/page.tsx' frontend/src/app/admin/tests/page.tsx frontend/src/app/admin/tests/new/page.tsx 'frontend/src/app/admin/tests/[testId]/page.tsx' 'frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx' frontend/src/app/transfer/page.tsx frontend/src/features/auth/admin-guard.tsx frontend/src/features/auth/admin-user-list.tsx frontend/src/features/auth/admin-user-actions.tsx frontend/src/features/test-builder/test-library-list.tsx frontend/src/features/test-builder/new-test-form.tsx frontend/src/features/test-builder/test-details-heading.tsx frontend/src/features/test-builder/version-actions.tsx frontend/src/features/test-builder/builder-workspace-navigation.tsx frontend/src/features/test-builder/builder-lifecycle.tsx frontend/src/features/test-builder/autosave-link.tsx frontend/src/features/test-builder/reading-builder.tsx frontend/src/features/test-builder/listening-builder.tsx frontend/src/features/test-builder/writing-builder.tsx frontend/src/features/test-builder/module-duration-editor.tsx frontend/src/features/test-builder/listening-section-editor.tsx frontend/src/features/transfer/transfer-portal.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/admin-dashboard.test.tsx frontend/tests/admin-user-list.test.tsx frontend/tests/admin-user-detail.test.tsx frontend/tests/test-library-list.test.tsx frontend/tests/version-actions.test.tsx frontend/tests/builder-workspace-navigation.test.tsx frontend/tests/builder-workspace-page.test.tsx frontend/tests/builder-autosave.test.tsx frontend/tests/module-duration-editor.test.tsx frontend/tests/transfer-portal.test.tsx frontend/tests/workspace-localization.test.tsx frontend/tests/translations.test.ts
git commit -m "Localize Admin Builder and Transfer workspace chrome"
```

### Task 11: Static exam and runner control localization

**Files:**
- Modify: `frontend/src/features/reading/reading-runner.tsx`, `reading-review.tsx`; `frontend/src/features/listening/listening-runner.tsx`, `listening-review.tsx`, `audio-player.tsx`; `frontend/src/features/writing/writing-runner.tsx`, `writing-review.tsx`; `frontend/src/features/exam/pause-attempt-control.tsx`, `paused-attempt-gate.tsx`, `draft-recovery-notices.tsx`, `test-session-transition.tsx`, `terminal-attempt-redirect.tsx`, `use-exam-submit.ts`; `frontend/src/features/test-builder/draft-preview.tsx`; `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Modify (shared static controls only): `frontend/src/features/highlighting/selectable-text.tsx`; `frontend/src/features/questions/renderers.tsx`, `note-completion-renderer.tsx`, `table-completion-renderer.tsx`, `diagram-labelling-renderer.tsx`.
- Test (create): `frontend/tests/runner-localization.test.tsx`; modify `frontend/tests/reading-navigation.test.tsx`, `listening-navigation.test.tsx`, `listening-player.test.tsx`, `writing-runner.test.tsx`, `writing-review.test.tsx`, `focused-reading-review.test.tsx`, `focused-listening-review.test.tsx`, `pause-attempt-control.test.tsx`, `test-session-transition.test.tsx`, `draft-preview.test.tsx`, `translations.test.ts`.
- Test (modify shared-control cases): `frontend/tests/selectable-text.test.tsx`, `question-registry.test.tsx`, `note-completion.test.tsx`, `table-completion.test.tsx`, `diagram-labelling.test.tsx`.

**Interfaces:**
- Consumes: Stable provider/test harness, t/UiText, common keys, optional-translator display helpers.
- Produces: Complete common `runner.*` / `audio.*` keys; existing runner props, ListeningAudioPlayer src/clip/policy/ref/onDuration and public useExamSubmit return shape remain unchanged.

- [ ] **Step 1: Write the failing test**

Add table-driven `locale switch preserves active attempt state` for all three real runners, copying minimal fictional payload builders from their existing test files into runner-localization.test.tsx and mocking HTTP/media; never import a test file as a fixture module. Switch EN → VI → EN through the provider harness outside the attempt shell; do not add a runner locale selector. Assert existing Pause/Resume/Continue/Submit/Review/Exit-or-Leave/Back slots, Time remaining/Time elapsed, Question(s), generated Passage/Section/Task, saving/state/error/dialog copy and player accessible names update where those slots exist. Representative VI labels: `Tạm dừng`, `Tiếp tục`, `Nộp bài`, `Thời gian còn lại`, `Thời gian đã dùng`, `Câu hỏi 2`, `Phần 2`. Labels do not create missing controls.

Before switching, type an answer/Writing response, select a unit, set a flag/highlight and advance fake time. Compare runner/input/audio node identity, preserved response/draft revision, selected unit, timestamp-derived timer and highlights/flags after the switch. Observe lifecycle/store creation with spies, not merely a wrapper counter; queued save and initial navigation/activity calls retain counts/payloads, and switching emits no request or router action. Preserve audio currentTime/rate/volume/mute and play/pause/load call counts using mocked media; no real playback. Repeat for provider restoration after mount, pending autosave and an open common dialog. Keep fake timers from introducing unrelated periodic requests during the assertion interval.

Capture authored title/passage blocks/Listening section content/prompts/options/admin instruction/Writing prompt/response/keys/explanations before/after and compare exact strings/serialized fixture plus display text; authored `Section 2` stays English while generated label translates. Extend runner/review Listening fixtures for clip+audio, audio without clip, and no audio: same clip/policy/source behavior, translated neutral fallback notices, questions still present. Preserve full standalone allowSeeking/allowSpeed and Full Mock restrictions. Cover paused gate, review/preview generated controls, focused raw/max/accuracy/no Band and Full Mock transition polling/advance counts. AppShell tests separately prove no global chrome on full/focused/paused attempts.

In existing shared-control tests, switch locale with a highlight popover open: its action/dialog/error labels and generic Question accessible names/empty selector placeholders update, but selected text, offsets, highlight ID, popover node/focus and answer values remain exact. IELTS answer choices such as TRUE/FALSE/NOT GIVEN, option text, diagram annotations, instruction templates and authored table/note content remain unchanged. These assertions cover the same static-system boundary inside reused renderers, not specialized Builder-editor translation.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/runner-localization.test.tsx tests/reading-navigation.test.tsx tests/listening-navigation.test.tsx tests/listening-player.test.tsx tests/writing-runner.test.tsx tests/writing-review.test.tsx tests/focused-reading-review.test.tsx tests/focused-listening-review.test.tsx tests/pause-attempt-control.test.tsx tests/test-session-transition.test.tsx tests/draft-preview.test.tsx tests/translations.test.ts tests/selectable-text.test.tsx tests/question-registry.test.tsx tests/note-completion.test.tsx tests/table-completion.test.tsx tests/diagram-labelling.test.tsx`

Expected: FAIL on untranslated runner/player UI; current lifecycle/scoring/playback assertions stay valid.

- [ ] **Step 3: Implement the minimal change**

Wire t into existing static text/accessible-label slots only. Preserve JSX hierarchy/classes, exam tokens/layout, authored rendering, input names/IDs, UUID keys, lifecycle hooks, timer calculations, autosave stores, flag/highlight handlers and attempt/player props. Pass t to display helpers; distinguish generated labels from authored titles by existing kind/order data. Translate only owned static fallback branches; arbitrary server messages/warnings and authored instructions remain raw. In the listed shared renderers translate only generic Question names/empty selector placeholders; do not translate question-registry content, answer values/IELTS choices, authored annotation text or change answer primitives. SelectableText translates only its existing application-owned labels and local error branches; its semantic-offset and portal/event lifecycle stays intact.

For static errors currently stored as English strings, store the existing branch's message key rather than translated output; resolve it at render. In useExamSubmit keep submitError's public string|null shape, but store its two owned fallback keys internally and resolve with current t outside the submit callback. Do not add t/locale to mutation/effect dependencies, timer/store/source derivation or audio reset effects. Audio player's reset effects remain dependent on src and start/end/duration/clip-error/preview-request only; translating labels does not change these values or audio node identity. Keep focused audio fallback semantics and use neutral notices. Review score labels/accuracy may translate, but raw/max/band/null arithmetic and authored explanations do not. No global header/footer or new preferences widget enters `/attempt/*`.

- [ ] **Step 4: Run focused tests**

Run the Step 2 command plus `npx vitest run tests/app-shell.test.tsx tests/attempt-page.test.tsx tests/reading-instructions.test.tsx tests/writing-routing.test.tsx tests/draft-answer-autosave.test.tsx tests/revision-autosave.test.ts tests/exam-draft-recovery.test.ts tests/timer.test.ts tests/exam-theme-css.test.ts`.

Expected: PASS for EN/VI controls, byte/display-equivalent authored data, stable state/requests/audio and current exam behavior. No browser/E2E requirement.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/features/reading/reading-runner.tsx frontend/src/features/reading/reading-review.tsx frontend/src/features/listening/listening-runner.tsx frontend/src/features/listening/listening-review.tsx frontend/src/features/listening/audio-player.tsx frontend/src/features/writing/writing-runner.tsx frontend/src/features/writing/writing-review.tsx frontend/src/features/exam/pause-attempt-control.tsx frontend/src/features/exam/paused-attempt-gate.tsx frontend/src/features/exam/draft-recovery-notices.tsx frontend/src/features/exam/test-session-transition.tsx frontend/src/features/exam/terminal-attempt-redirect.tsx frontend/src/features/exam/use-exam-submit.ts frontend/src/features/test-builder/draft-preview.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/runner-localization.test.tsx frontend/tests/reading-navigation.test.tsx frontend/tests/listening-navigation.test.tsx frontend/tests/listening-player.test.tsx frontend/tests/writing-runner.test.tsx frontend/tests/writing-review.test.tsx frontend/tests/focused-reading-review.test.tsx frontend/tests/focused-listening-review.test.tsx frontend/tests/pause-attempt-control.test.tsx frontend/tests/test-session-transition.test.tsx frontend/tests/draft-preview.test.tsx frontend/tests/translations.test.ts
git add -- frontend/src/features/highlighting/selectable-text.tsx frontend/src/features/questions/renderers.tsx frontend/src/features/questions/note-completion-renderer.tsx frontend/src/features/questions/table-completion-renderer.tsx frontend/src/features/questions/diagram-labelling-renderer.tsx frontend/tests/selectable-text.test.tsx frontend/tests/question-registry.test.tsx frontend/tests/note-completion.test.tsx frontend/tests/table-completion.test.tsx frontend/tests/diagram-labelling.test.tsx
git commit -m "Localize static runner controls without resetting attempts"
```

### Task 12: Visual and regression contract consolidation

**Files:**
- Modify: `frontend/src/app/globals.css` only for a gap demonstrated by a new focused contract.
- Test: `frontend/tests/visual-system-css.test.ts`, `dark-theme-css.test.ts`, `exam-theme-css.test.ts`, `shell-layout-css.test.ts`, `app-shell.test.tsx`.

**Interfaces:**
- Consumes: Final shell markup, exact paper/graphite tokens and frozen exam baseline.
- Produces: Consolidated readable CSS contracts, no giant snapshots or new visual architecture.

- [ ] **Step 1: Write the failing test**

Add `final workspace hover focus and reduced-motion contracts` for every button variant and card/field surface actually changed, including mixed badge/status contrast, 44px small actions, no colored glows/ambient gradients/blur, nav marker/focus/ordinary Tab order and no duplicate nav. Add an explicit source contract that workspace typography/selectors cannot override exam descendants' frozen metrics and embedded preview values. Preserve existing completion-gap, instruction white-space, question-strip scroll, history padding, responsive Writing/review and highlight correctness assertions. Retitle galaxy/old-sidebar test descriptions and remove obsolete expectations only where replacement contracts now prove the new requirement.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts tests/app-shell.test.tsx`

Expected: FAIL for a newly exposed missed cascade/hover/focus rule. If the completed earlier tasks already satisfy the new assertions, record PASS and retain the regression tests; do not manufacture a failure or gratuitous CSS change.

- [ ] **Step 3: Implement the minimal change**

Fix only evidenced cascade/selector gaps to match the approved values, within globals.css. Keep test parsing/contrast helpers local to current files unless existing duplication directly prevents accurate assertions; no CSS framework/tool dependency or broad cleanup. Cross-check obsolete assertions were replaced at owning tasks and all useful exam/feedback/reduced-motion tests remain. Pure test consolidation needs no production edit when already green.

- [ ] **Step 4: Run focused tests**

Run the Step 2 command plus `npx vitest run tests/app-logo.test.tsx tests/interactive-planet.test.tsx tests/draft-preview.test.tsx tests/reading-navigation.test.tsx tests/listening-navigation.test.tsx tests/writing-runner.test.tsx`.

Expected: PASS; record CSS/DOM proof without claiming browser pixel verification.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/tests/visual-system-css.test.ts frontend/tests/dark-theme-css.test.ts frontend/tests/exam-theme-css.test.ts frontend/tests/shell-layout-css.test.ts frontend/tests/app-shell.test.tsx
git commit -m "Consolidate shell theme and exam regression contracts"
```

If an evidenced CSS correction was necessary, add `frontend/src/app/globals.css` explicitly before this commit.

### Task 13: Final cross-feature verification

**Files:**
- Test (create): `frontend/tests/localization-matrix.test.tsx`.
- Modify: No production file by default; a failing matrix case must be fixed in its already named owning file/task, without extending scope.

**Interfaces:**
- Consumes: Real AppShell, LocaleProvider, feature views and test harness; mock only existing auth/API/media boundaries.
- Produces: A focused cross-feature matrix and recorded verification evidence.

- [ ] **Step 1: Write the failing test**

Add `role locale theme route matrix preserves chrome and feature identity` using representative table rows rather than every redundant Cartesian combination. Include guest/en/light/auth, USER/vi/dark/Practice, USER/en/dark/History and review, ADMIN/vi/light/Builder edit/Transfer, ADMIN/vi/dark/exact preview, and en→vi in full/focused Reading/Listening/Writing and Full Mock transition fixtures. Assert expected role links/exclusions, same child identities, selected Practice/History/Builder state, logout dialog focus/single request and independent preference persistence across route transitions/logout. Refresh/mount with saved VI/dark, invalid/throwing storage and server year to cover hydration without a browser. Reuse feature fixtures in their existing test files when importing them would couple test execution; the matrix should be short and add cross-feature composition assertions rather than duplicate every renderer test.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/localization-matrix.test.tsx`

Expected: FAIL only if the new integration matrix exposes a missing composition guarantee. Earlier tasks should already satisfy it; an immediate PASS is valid final verification and must not trigger invented behavior changes.

- [ ] **Step 3: Implement the minimal change**

Resolve an evidenced integration failure in its owning file with its owning regression test, then rerun that task's focused checks. Otherwise make no product edit. Audit the changed-file diff: frontend only, static runner controls included, specialized Builder help still deferred, authored data excluded, exact preview/attempt exclusions, stable IDs/keys/effect dependencies, explicit exam compatibility, no new dependencies/generated files/secrets or domain payload changes. Confirm each included spec surface has both dictionary keys and call sites; key parity alone does not prove string coverage.

- [ ] **Step 4: Run focused tests**

Run these explicit batches from `frontend/`, preserving the existing Vitest setup and mocks:

```bash
npx vitest run tests/translations.test.ts tests/locale-provider.test.tsx tests/root-layout.test.tsx tests/theme-toggle.test.tsx tests/common-localization.test.tsx tests/app-shell.test.tsx tests/app-footer.test.tsx tests/auth.test.tsx tests/auth-session-restore.test.tsx tests/localization-matrix.test.tsx
npx vitest run tests/workspace-localization.test.tsx tests/home-user-metric.test.tsx tests/practice-library.test.tsx tests/skill-practice.test.tsx tests/attempt-history-list.test.tsx tests/analytics-dashboard.test.tsx tests/profile.test.tsx tests/admin-dashboard.test.tsx tests/admin-user-list.test.tsx tests/admin-user-detail.test.tsx tests/test-library-list.test.tsx tests/version-actions.test.tsx tests/builder-workspace-navigation.test.tsx tests/builder-workspace-page.test.tsx tests/builder-autosave.test.tsx tests/module-duration-editor.test.tsx tests/transfer-portal.test.tsx
npx vitest run tests/runner-localization.test.tsx tests/reading-navigation.test.tsx tests/reading-instructions.test.tsx tests/listening-navigation.test.tsx tests/listening-player.test.tsx tests/writing-runner.test.tsx tests/writing-review.test.tsx tests/focused-reading-review.test.tsx tests/focused-listening-review.test.tsx tests/pause-attempt-control.test.tsx tests/test-session-transition.test.tsx tests/draft-preview.test.tsx tests/attempt-page.test.tsx tests/writing-routing.test.tsx tests/draft-answer-autosave.test.tsx tests/revision-autosave.test.ts tests/exam-draft-recovery.test.ts tests/timer.test.ts
npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts tests/status-badge.test.tsx tests/app-logo.test.tsx tests/interactive-planet.test.tsx tests/builder-route.test.tsx tests/reading-builder-sync.test.tsx tests/listening-audio-ranges.test.tsx tests/writing-builder.test.tsx tests/selectable-text.test.tsx tests/question-registry.test.tsx tests/note-completion.test.tsx tests/table-completion.test.tsx tests/diagram-labelling.test.tsx
npm run typecheck
```

For targeted lint, from the repository root use PowerShell to collect only this rollout's changed TS/TSX files, then run installed ESLint in frontend:

```powershell
$rolloutFiles = @(git diff --name-only 74f89315256610d35b7a061e751dcb687c07c019 -- frontend)
$rolloutLintPaths = @($rolloutFiles | Where-Object { $_ -match '\.tsx?$' } | ForEach-Object { $_ -replace '^frontend/', '' })
$rolloutLintPaths = @(@($rolloutLintPaths) + 'tests/localization-matrix.test.tsx' | Sort-Object -Unique)
Push-Location frontend
try { npx eslint -- $rolloutLintPaths } finally { Pop-Location }
git diff --check 74f89315256610d35b7a061e751dcb687c07c019
git diff --check
```

The explicit matrix lint path covers it while untracked. If no other unstaged change exists, still inspect the rollout diff against the baseline above. Expected: all listed tests PASS, typecheck/ESLint exit 0 and no diff whitespace errors. Do not broaden into the entire test suite, browser/E2E or services. Record actual counts/commands, not assumed results.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/tests/localization-matrix.test.tsx
git commit -m "Verify locale theme and shell integration"
```

Include any necessary, reviewed integration fix and its regression test with explicit paths. This plan does not itself authorize deployment or product publication; follow the implementation session's Git instructions after verification.

## Spec Coverage and Review Gates

| Approved specification area | Owning tasks |
| --- | --- |
| Goals, non-goals, existing constraints and route inventory | Global Constraints; Tasks 3–5, 9–11 |
| Horizontal shell/components/navigation/auth behavior | Tasks 2–5, 8 |
| Content widths, spacing and responsive composition | Tasks 5, 7, 12 |
| Shared footer and route exclusions | Task 4; matrix in Task 13 |
| Exact paper/graphite palette, elevation and decoration cleanup | Tasks 6–7, 12 |
| Typography, buttons, fields, headings and semantic states | Tasks 6–7, 12 |
| Typed dictionaries, locale controls and server/client boundaries | Tasks 1–2, 8–10 |
| Translation table and specialized Builder deferral | Tasks 8–11; Global Constraints |
| Amended common/static runner localization and authored-content exclusion | Task 11; state/content regressions in Tasks 9–10, 13 |
| Exam-route isolation and frozen inherited/exam values | Tasks 3–6, 11–13 |
| Accessibility, focus, contrast, language and reduced motion | Tasks 1, 3–8, 11–13 |
| Hydration/preferences/year/state persistence | Tasks 1–2, 4, 8–11, 13 |
| Testing strategy, risks and five high-risk state classes | Review Focus and each owning test; Tasks 12–13 |
| Acceptance criteria and frontend-only implementation boundary | All task checks plus Task 13 diff audit |

The final review verifies signatures against Locked Shared Interfaces, both dictionary key parity and included call-site coverage, no authored string conversion, no blanket runner translation deferral, no runner redesign, no locale-driven reinitialization/request dependencies, no specialized-editor expansion, exact route exclusions and preserved exam appearance. Verification tasks may already be green; capture evidence instead of introducing unnecessary changes. This document is an implementation plan only; preparing it does not start any task above.
