# Horizontal shell, paper themes, and system UI localization

Date: 2026-10-10

Status: Approved direction, specification only

Repository inspected: `ChuTungDuongg/IELTS_Self_Practising_Web`

Baseline: `0ffe61c333e46a9c61a4a8588b66f455fd452147` — `Refine focused practice browsing`

This document defines the next frontend architecture change. It does not implement that change or authorize work beyond the approved frontend scope. The deliverable for this specification task is this document alone.

## 1. Context and current state

Inspection followed a fresh fetch of `origin/main`; the remote and local baseline matched. The following findings determine the design:

| Area | Current implementation | Design implication |
| --- | --- | --- |
| Root composition | `frontend/src/app/layout.tsx` renders `AuthProvider` → `AppShell`, with server `lang="en"` and `data-theme="light"`. | Add browser-local locale context around the existing composition; keep server data fetching and auth boundaries. |
| Workspace shell | `components/ui/app-shell.tsx` owns brand, context label, auth actions, theme, navigation, and logout confirmation. CSS uses a 72px header and a permanent 248px sidebar. | Replace the global sidebar with one horizontal primary navigation and a modest header/footer split. |
| Navigation | Signed-in users see five workspace links; ADMIN users additionally see Admin, Builder, and Transfer. Guests see Overview. `/admin` is exact-match; Builder covers `/admin/tests/*`. | Preserve destinations, visibility, non-home `prefetch={false}`, and active-route distinctions. |
| Immersive attempts | AppShell returns only `<main className="exam-shell">` for paths starting `/attempt/`. Reading, Listening, Writing, paused attempts, and Full Mock modules all enter through this route. | Preserve the bypass before constructing workspace chrome. |
| Other routes | `/review/[attemptId]` and `/test-session/[sessionId]` use the normal shell. Builder preview uses the normal shell but its `DraftPreview` renders `.exam-runner` and a local `.exam-footer`. | Reviews/transitions receive the shared footer; draft previews exclude it without changing their current header or runner layout. |
| Typography | Body uses Segoe UI/system sans at 15px. Shared H1 is 32–46px/760; buttons are 13px/750; many badges/kickers use 800 weight, uppercase, and wide tracking. | Retain the system font approach; simplify weights, case, and hierarchy on workspace pages. |
| Themes | `globals.css` defines shared tokens and explicit `--exam-*` tokens. Light mode has blue/violet backgrounds and layered gradients; dark mode already flattens many surfaces but uses cool graphite. | Warm both workspace palettes and remove ambient lighting, while preserving exam resolved values. |
| Theme persistence | `ielts-theme`, root `data-theme`, inline bootstrap, and `ThemeToggle` restoration exist. The bootstrap currently follows `prefers-color-scheme` when no theme is stored. | Keep keys/attributes and early theme bootstrap; explicitly default to light instead of introducing implicit system mode. |
| Server pages | Overview, Library, Practice, History, Analytics, and Admin fetch through `serverApiRequest`; existing interactive feature views consume DTOs. | Translate presentation at client boundaries; do not move API fetching into the browser. |
| Practice browser | Skill Practice has local skill/unit filters, search, persistent mounted cards, timers, and focused start controls. | Its filter panel is feature navigation, not the global sidebar; preserve selection, search behavior, card identity, and pending attempt guards. |
| Shared primitives | `PageHeading`, `EmptyState`, `ModuleBadge`, `StatusBadge`, icons, SVG `AppLogo`, and `ConfirmDialog` already exist. | Extend/reuse them; preserve dialog focus, pending behavior, and semantic variants. |
| Validation | Vitest/RTL, TypeScript, ESLint, and CSS token/contrast tests exist. Some CSS tests require the old sidebar, glow, sizes, or galaxy styling. | Update obsolete visual assertions deliberately; retain accessibility, theme, and exam protection checks. |

Inspection covered the required UI primitives, root layout/CSS, auth provider, all requested main page families, nested Admin/Builder routes, Transfer, profile/auth/session routes, attempts/reviews/transitions/previews, and relevant frontend tests. The installed Next client-boundary guide confirms that browser context belongs in client components and server-to-client props must remain serializable. No localization or theme package is currently installed.

## 2. Goals

1. Give normal pages one horizontal navigation, more useful content width, and a restrained shared footer.
2. Establish a readable, sentence-case typography and button hierarchy across workspace and Admin chrome.
3. Use warm paper in light mode and warm graphite in dark mode, with quiet borders and small semantic accents.
4. Support English and Tiếng Việt for application UI through a small typed internal dictionary and a browser-local preference.
5. Preserve existing routes, role restrictions, domain rules, authored content, and the isolated exam experience.

IELTS Studio retains its name, existing SVG planet identity, and distinguishable Reading/Listening/Writing accents. Paper/editorial inspiration does not imply copying another product's branding or interface.

## 3. Non-goals

- No exam-runner redesign, new runner navigation, or change to layout, exam tokens, timers, autosave, highlighting, flags, playback rules, question-content rendering behavior, submission, review answers, Full Mock behavior, scoring, or the attempt state machine. Existing common/static runner strings and accessible labels are included in localization; this does not authorize changes to those behaviors.
- No Test Library functional changes or Skill Practice logic changes; no thumbnail system.
- No backend changes, migrations, database preferences, locale columns, API locale headers, translated database content, or backend theme state.
- No `/en/*` or `/vi/*` routes, locale cookies, SEO localization, or authored IELTS content translation.
- No new authentication, Speaking implementation, AI behavior, or AI service calls.
- No theme modes beyond light/dark, system/auto mode, downloaded font binaries, design-system dependencies, localization packages, or CSS framework replacement.
- No mobile drawer, animation framework, or full translation of specialized nested Builder editors in this first pass.

## 4. Navigation architecture

Use one `<nav aria-label={t("nav.primary")}>` in the global header. Desktop links are text-first; remove redundant per-link icons from this compact navigation. Keep the brand mark. Preserve link order and destinations:

| English label | Vietnamese label | Destination | Visibility |
| --- | --- | --- | --- |
| Overview | Tổng quan | `/` | Everyone |
| Test library | Thư viện đề | `/library` | Signed in |
| Skill practice | Luyện từng kỹ năng | `/practice` | Signed in |
| Attempt history | Lịch sử luyện tập | `/history` | Signed in |
| Analytics | Thống kê | `/analytics` | Signed in |
| Admin | Quản trị | `/admin` | ADMIN |
| Builder | Biên soạn đề | `/admin/tests` | ADMIN |
| Transfer | Chuyển đề | Existing `TRANSFER_ROUTE` (`/transfer`) | ADMIN |

Do not turn translated labels into route paths or identifiers. Navigation records use stable hrefs and translation keys. Auth loading retains the existing conservative visibility: no privileged links before user resolution. Session errors remain visible and do not masquerade as a logged-out state. Existing server role checks in Admin and Transfer layouts remain authoritative; hiding links is not authorization.

Preserve exact matching for `/` and `/admin`, and descendant matching for the remaining existing destinations. In particular `/admin/tests/...` activates Builder, not Admin. Do not introduce a new global active destination for `/profile`, `/review/...`, or `/test-session/...`; their own heading/back action supplies context.

Remove the header's `Workspace / current section` context block, sidebar `Workspace` label, and sidebar promotional note. The active link plus the page H1 supplies context without duplicate navigation. Keep existing page-specific back links, test/version provenance, and Builder workspace navigation; do not add a second global breadcrumb.

Header actions have a stable order: language, theme, user/profile, logout. Signed-out actions replace user/logout with Login and Register in that order. User display names remain authored/user data; the displayed role label can translate while the API role stays `USER` or `ADMIN`. Reuse the current logout confirmation, one-request guard, disabled pending state, focus restoration, and failure handling. Locale changes never trigger auth requests, logout, redirects, or `router.refresh()`.

## 5. Shell component structure and page composition

Recommended composition:

```text
RootLayout (server: metadata, theme bootstrap, current footer year)
└── LocaleProvider (client)
    └── AuthProvider (existing client lifecycle)
        └── AppShell (route boundary)
            ├── /attempt/*: main.exam-shell → existing page only
            └── normal route: div.app-shell
                ├── GlobalHeader
                │   ├── existing Brand/AppLogo
                │   ├── PrimaryNavigation
                │   └── HeaderActions: LocaleSwitcher, ThemeToggle, account controls
                ├── main.app-content#main-content → existing page
                └── AppFooter (except inspected Builder preview route)
```

Keep `AppShell` in its current file. Add `global-header.tsx` and `app-footer.tsx` under `components/ui/`. `PrimaryNavigation`, `HeaderActions`, and the compact `LocaleSwitcher` can be local functions in the header file, not separate component files. GlobalHeader owns the existing auth/logout UI; AppShell owns route inclusion and page placement. Keep `ThemeToggle`, `ConfirmDialog`, and primitives reusable. Do not extract a new exam component merely to rename the existing bypass.

Normal shell uses one column and `min-height: 100dvh` (with `100vh` fallback), with header, growing main, and footer in normal flow. The footer rests below short content through the growing main; it is never fixed over content. Dialog overlays preserve their existing behavior and sit outside the primary navigation.

Content dimensions are border-box maxima including shell padding:

| Page family | Outer maximum | Inner constraint |
| --- | --- | --- |
| Overview, review, normal detail pages | 1280px | Descriptive prose ≤72ch; existing review panes remain intact. |
| Library, Skill Practice, History, Analytics, Admin lists, Builder, Transfer | 1440px | Keep current grids/local navigation; use the extra room without changing their logic. |
| Profile and ordinary forms | 1280px | Form body ≤920px, field groups retain responsive columns. |
| New-test form | 1280px | Form body ≤720px. |
| Login/Register | 1280px | Auth panel ≤480px. |
| Full Mock transition | 1280px | Existing transition body ≤720px. |

Use a small explicit pathname-to-width classification in AppShell, not a new layout framework. Builder previews keep their current inner runner dimensions and receive no workspace typography overrides inside `.exam-runner`. Attempts receive none of these widths or padding.

Shell horizontal padding: 32px at ≥1440px, 24px at 768–1439px, 16px below 768px. Main top/bottom padding: 40/48px on large screens, 32/40px on medium screens, 24/32px on small screens. Header/footer inner widths cap at 1440px with the same horizontal padding. Content stays centered.

Use a 4px spacing base: 8px related text/control gaps, 12px compact groups, 16px form fields and narrow card gaps, 24px ordinary card padding/grid gaps, 32px between sections, and 48px between major overview sections. Compact practice cards keep their existing 16px padding and feature density. PageHeading has 24px bottom margin, 8px eyebrow-to-title gap, and 12px title-to-description gap. Forms use 16px between fields and 24px between groups/actions. Actions wrap below a heading when needed; avoid fixed title heights and compulsory empty eyebrows.

## 6. Footer behavior

AppFooter is a semantic `<footer>` with a top border, paper surface, 24px vertical padding, and small muted copy. Its content is:

- `IELTS Studio` (unchanged product name).
- Localized `Practice & authoring` / `Luyện tập và biên soạn đề`.
- `© {year} IELTS Studio`, using the current year supplied by RootLayout at server render.
- A locale indication, `English` or `Tiếng Việt`, without a second selector or flags.

No invented legal, social, contact, or documentation links. On desktop, identity/description sit left and copyright/locale right; below 768px these groups stack with a 12px gap. The footer remains outside the page's feature content and never duplicates `.exam-footer`.

Route decisions are grounded in the inspected routing:

| Route | Global header | Global footer | Reason |
| --- | --- | --- | --- |
| `/attempt/*` | No | No | Existing immersive route for focused/full practice, Full Mock modules, paused gate, and terminal redirect. |
| `/admin/tests/[testId]/versions/[versionId]/preview` | Yes, existing Admin shell | No | DraftPreview renders an exam runner and its own exam footer. Only suppress the new global footer; do not redesign preview or remove its current header. |
| `/review/[attemptId]` | Yes | Yes | Finalized answer/score review currently uses workspace composition. |
| `/test-session/[sessionId]` | Yes | Yes | Transition/results card uses normal shell; an active attempt redirects to `/attempt/*`. |
| `/session/restore`, `/login`, `/register`, `/profile`, `/transfer`, other inspected workspace/Admin routes | Yes | Yes | These are ordinary pages or guards, not immersive runners. |

Keep the existing `/attempt/` prefix condition. Match the preview exclusion by complete pathname shape, for example `^/admin/tests/[^/]+/versions/[^/]+/preview/?$`; query parameters such as `?module=listening` do not affect it. Do not exclude all Admin, review, session, or practice paths by broad substring checks. No other current route needs an exclusion.

## 7. Typography system

Retain a Segoe-first, locally available sans-serif stack:

```css
"Segoe UI Variable", "Segoe UI", ui-sans-serif, system-ui,
-apple-system, BlinkMacSystemFont, sans-serif
```

Remove the incidental `Inter` fallback rather than implying that a downloaded font exists. Use this same stack for normal-page text, headings, labels, and controls. The paper effect comes from spacing and colors, not a new serif or font dependency. System fallbacks support Vietnamese diacritics; do not set fixed text heights or tight line boxes.

| Role | Size | Weight | Line height | Letter spacing | Case |
| --- | --- | --- | --- | --- | --- |
| Body | 16px | 400 | 1.6 | 0 | Natural sentence case |
| Small/meta/help | 13px | 400; 500 for emphasis | 1.5 | 0 | Sentence case |
| Navigation | 14px | 500; 600 active | 1.4 | 0 | Sentence case |
| Buttons | 14px | 600 | 1.4 | 0 | Sentence case |
| Page eyebrow/context | 13px | 500 | 1.5 | 0.01em | Sentence case |
| Page title / H1 | 32px desktop, 28px small | 600 | 1.2 | -0.02em | Sentence case |
| Section title / H2 | 22px desktop, 20px small | 600 | 1.3 | -0.01em | Sentence case |
| Card title / H3 | 18px | 600 | 1.35 | -0.01em | Authored case for content titles |
| Form labels | 14px | 500 | 1.4 | 0 | Sentence case |
| Status/badge | 12px | 500 | 1.4 | 0 | Sentence case |
| Compact module badge | 12px | 600 | 1.4 | 0.02em maximum | Uppercase allowed only here |

Apply the scale to shared headings, normal overview hero text, feature headings, and Admin chrome, preserving heading semantics. Authored titles are displayed verbatim; CSS must not force their capitalization. Preserve deliberate emphasis within authored content and exam-specific fonts/sizes. Numeric score/metric values can remain larger than body text and use tabular numerals; do not change their meaning or formatting.

Remove forced uppercase and 0.07–0.17em tracking from workspace eyebrows, branding tagline, statuses, version labels, learning-path copy, validation chrome, and common card kickers. `.page-context-kicker`, `.authoring-eyebrow`, and `.history-eyebrow` converge on the eyebrow scale; their optional small contextual border remains. Avoid normal UI weights above 600 except a local, justified numeric emphasis at 700. Status display strings use translation keys; API enum values are unchanged.

All existing button variants share 14px/600 type, 8px radius, 40px minimum height on normal desktop pages, 44px on small-screen header/actions, 14px horizontal padding, and an 8px icon gap. Icon buttons are at least 40px, 44px on small screens, and have accessible names. Text can wrap for long Vietnamese actions. Keep semantic variants:

| Variant | Treatment |
| --- | --- |
| Primary | Flat product accent, contrast token text; one main action per local group. |
| Secondary | Raised paper surface, strong enough outline, ink text. |
| Ghost | Transparent surface, ink/muted readable text; neutral hover. |
| Danger | Flat danger token and matching contrast text. |
| Danger ghost | Danger text; danger-soft hover; no glow. |
| Module action | Existing Reading/product, Listening, and Writing variant relationships remain; flat semantic color and theme-specific contrast text. |

Preserve disabled/pending semantics, link-versus-button behavior, loading labels, and focus indicators. Replace hover lifts/colored shadows with a surface/border change and a 120–160ms color transition. Do not change shared runner button metrics through these workspace rules.

## 8. Light paper theme

Retain existing token names so consumers do not need a new theme architecture. These values define the workspace target palette:

| Token | Light value | Use |
| --- | --- | --- |
| `--app-bg`, `--paper` | `#f5f2eb` | Warm ivory page background |
| `--app-bg-elevated` | `#eee9df` | Secondary shell backing |
| `--surface` | `#fcfaf5` | Paper cards/panels |
| `--surface-raised` | `#fffdf8` | Inputs, dialogs, raised elements |
| `--surface-soft` | `#eeeae1` | Quiet grouped areas |
| `--surface-hover` | `#e8e3d9` | Neutral interactive hover |
| `--surface-glass` | `#fcfaf5` | Opaque header/toolbar surface |
| `--ink` | `#292620` | Warm ink |
| `--ink-soft` | `#4c473e` | Secondary text |
| `--muted` | `#686155` | Help/meta text |
| `--line` | `#ddd6c9` | Decorative dividers/card edges |
| `--line-strong` | `#8f8575` | Input/control outlines |
| `--accent` | `#5261a8` | Restrained existing indigo identity |
| `--accent-strong` | `#434f90` | Primary hover/emphasis |
| `--accent-soft`, `--surface-tint` | `#e7e9f3` | Small selected areas |
| `--accent-contrast` | `#ffffff` | Filled accent/module action text |
| `--reading`, `--accent-cyan` | `#286f82` | Reading semantic teal-blue |
| `--listening`, `--accent-violet` | `#725b91` | Listening semantic violet |
| `--writing` | `#99562e` | Writing semantic warm brown-orange |
| `--success` / `--success-soft` | `#277052` / `#e7f0e9` | Successful state |
| `--warning` / `--warning-soft` | `#8a581d` / `#f5ebd9` | Warning state |
| `--danger` / `--danger-soft` | `#a83c50` / `#f7e8eb` | Destructive/error state |
| `--danger-contrast` | `#ffffff` | Filled danger text |

Module badges use their semantic text over an 8% semantic-color mix with paper; selected filters can use the same tint plus a visible marker. Use 2–3px solid accents on relevant cards, not colored card bodies. Preserve success/warning/error meaning independently of module identity. Informational notices remain neutral.

Decoration audit and decisions, applied to workspace surfaces in both themes:

| Current treatment | Decision |
| --- | --- |
| Body radial gradients and `.app-shell::before` atmosphere | Remove; use solid app background. |
| `.app-header`, Builder/Library glass blur | Replace with opaque paper and bottom border; no backdrop blur needed for normal chrome. |
| Sidebar gradients/context note | Remove with the global sidebar. |
| `.home-hero` radial layers and decorative diagonal `::after` | Remove; retain its composition on a paper surface. |
| Home planet mark/interactive scene | Keep existing SVG identity and interaction; remove ambient `.home-orbit-glow`, reduce core shading to quiet solid/token surfaces, and remove colored drop-shadow. No new animation or illustration. |
| Learning-path/card accent gradients | Replace with short solid product/module accents. |
| Empty-state, History heading, passage header, Listening/Writing Builder panel gradients | Replace with surface or surface-soft. Preserve functional/editor layout. |
| Button/theme hover glows and editor colored elevation | Remove; neutral hover and minimal shadow. |
| Functional progress bars, chart marks, selected/focus indicators | Keep semantic color; do not remove information-bearing visuals. |
| Exam/highlight/answer renderer treatments | Preserve current behavior and resolved exam appearance; outside this cleanup. |

Normal cards have no shadow unless they are actually raised. Light `--shadow-sm`: `0 1px 3px rgb(41 38 32 / 0.07)`; `--shadow-md`: `0 4px 12px rgb(41 38 32 / 0.08)`; dialog `--shadow-lg`: `0 12px 32px rgb(41 38 32 / 0.16)`. Use sm for raised cards, md only for a genuinely raised overlay, lg for modal/dialog. Preserve existing token definitions `--glow-accent`/`--glow-violet` as neutral `--shadow-sm` aliases during compatibility cleanup, with no workspace colored-glow consumers. Card radius is 12px, ordinary fields/buttons 8px, dialogs 14px, semantic badges may retain pill shape.

## 9. Dark paper theme

Use `:root[data-theme="dark"]` and `color-scheme: dark`, with the same hierarchy and layout as light mode:

| Token | Dark value |
| --- | --- |
| `--app-bg`, `--paper` | `#201e1b` |
| `--app-bg-elevated` | `#25221e` |
| `--surface` | `#292622` |
| `--surface-raised` | `#312d28` |
| `--surface-soft` | `#35312c` |
| `--surface-hover` | `#3c3731` |
| `--surface-glass` | `#292622` |
| `--ink` | `#f1ece2` |
| `--ink-soft` | `#d2cbc0` |
| `--muted` | `#b4aa9a` |
| `--line` | `#494239` |
| `--line-strong` | `#8d8070` |
| `--accent` | `#a4afd9` |
| `--accent-strong` | `#b5bfe2` |
| `--accent-soft`, `--surface-tint` | `#333748` |
| `--accent-contrast`, `--danger-contrast` | `#201e1b` |
| `--reading`, `--accent-cyan` | `#94bac4` |
| `--listening`, `--accent-violet` | `#b4a4ce` |
| `--writing` | `#d2ab8b` |
| `--success` / `--success-soft` | `#a3c3ad` / `#26372d` |
| `--warning` / `--warning-soft` | `#d5b887` / `#3b3022` |
| `--danger` / `--danger-soft` | `#dda4aa` / `#3c292d` |

Keep surfaces warm charcoal rather than blue-black, and use soft off-white rather than maximum white throughout. Module badge tints use the same 8% recipe, and filled actions use dark contrast text. Hover accent is slightly lighter; don't add luminance-changing glow. Dark shadow levels: sm `0 1px 3px rgb(0 0 0 / 0.16)`, md `0 4px 12px rgb(0 0 0 / 0.20)`, lg `0 12px 32px rgb(0 0 0 / 0.30)`. Other decoration decisions match section 8.

Maintain the explicit light/dark exam palette described in section 13. The warmer workspace tokens must not silently recolor Candidate controls, highlights, or panes.

## 10. Locale and i18n architecture

Support exactly `type Locale = "en" | "vi"`, default `en`, storage key `ielts-locale`. Theme and locale are separate browser-local preferences; neither is tied to the authenticated user. No dependency, network translation request, database state, API header, route prefix, cookie, or generated translation pipeline is needed.

Small file boundary:

```text
frontend/src/lib/i18n/
├── en.ts                 # English dictionary; canonical flat dotted keys
├── vi.ts                 # Vietnamese dictionary with identical key shape
├── types.ts              # Locale, TranslationKey, TranslationDictionary
├── translations.ts       # dictionaries and pure lookup/interpolation
└── locale-provider.tsx   # LocaleProvider, hooks, and UiText client boundary
```

Use flat keys such as `nav.skillPractice`, `common.save`, `practice.sectionNumber`, and `history.tabs.focused`. English values are ordinary strings. English keys define the TypeScript union; Vietnamese uses `satisfies TranslationDictionary` with values widened to string, not to English literal values:

```ts
// Illustrative contract, not implementation added by this specification.
type Locale = "en" | "vi";
type TranslationKey = keyof typeof en;
type TranslationDictionary = Record<TranslationKey, string>;
// vi satisfies TranslationDictionary; dictionary map satisfies
// Record<Locale, TranslationDictionary>.
```

`types.ts` imports the English dictionary for its type only; `en.ts` has no dependency on the provider. Missing/extra Vietnamese keys and unknown call-site keys are compile errors. Keep English and Vietnamese bundled locally; this two-language UI does not need lazy dictionary loading.

API:

```ts
const { locale, setLocale } = useLocale();
const { t } = useTranslation();
t("nav.skillPractice");
t("practice.sectionNumber", { number: 2 });
```

`t` accepts a `TranslationKey` and optional scalar `Record<string, string | number>` parameters. Use named `{number}`, `{count}`, `{title}` placeholders, replacing them as plain strings; React escapes the result. No HTML messages, dynamic eval, rich-text parser, or arbitrary backend strings as keys. Where English needs singular/plural, use explicit singular/plural keys selected from the existing count; Vietnamese supplies both corresponding values. Preserve current numeric/date/time formatting and timer calculations. A defensive lookup fallback may return the English value if a dictionary value is unexpectedly unavailable, but TypeScript is the primary completeness check.

The provider exposes stable hooks, initializes state to `en`, restores a validated storage value after hydration, and sets `document.documentElement.lang` when locale changes. `setLocale` updates context immediately and persists best-effort. The compact selector is two buttons labeled `EN` and `VI` in a localized language group, with full accessible names `English` / `Tiếng Việt`, respective `lang` attributes, and `aria-pressed` for the selected language. Use no flags. A locale switch changes copy without navigating or resetting feature state.

## 11. Translation scope and server/client boundaries

Phase 1 translation covers the following system copy, including common/static runner controls. Both languages must provide complete keys for this scope; specialized Builder-editor copy remains the explicit deferred exception below. Authored IELTS content is excluded throughout.

| Surface | Included system UI | Data preserved verbatim |
| --- | --- | --- |
| Global shell | Navigation, brand accessible name, product description, language/theme labels, Login/Register/Logout, role display labels, logout dialog and pending labels, footer description | Product name, display name |
| Common primitives | Save, Cancel, Delete, Edit, Search, Retry, Continue, Resume, Review, Start, Submit, Back; loading, common empty states, generic labels and action accessible names | IDs, enum codes, routes |
| Common runner/review/preview/Full Mock transition UI | Existing Pause, Resume, Continue, Submit, Review, Exit/Leave, Back; Time remaining/Time elapsed; Questions/Question and generated Section/Passage/Task labels; common timer/state labels, confirmation dialogs, static error/fallback text, and generic audio-player controls/accessible labels such as play/pause, seeking, volume, and playback speed | All authored IELTS content, answers/responses, answer keys/explanations from test data, attempt IDs/payloads, timer values and playback state |
| Overview | Hero/system prose, pathway labels/descriptions, metric labels, goal labels, common actions | Profile values, user content, numeric metrics |
| Library and published detail | Page headings/descriptions, default description fallbacks, version/module/count/timer labels, Open test, back link, start controls, locally constructed readiness warnings | Authored test/module titles and descriptions, frozen DTOs |
| Skill Practice | Headings, skill/unit filters, All passages/sections/tasks, generated Section/Task labels, timers, start/pending/error fallback copy, question/word summaries, search labels, empty states, audio availability helpers | Test/passage/section titles, prompt excerpts, question content, target IDs |
| History | Four tab labels, statuses, version/scope/timer/count labels, empty states, Resume/Review/Delete actions and confirmations | Test/unit titles, frozen references, scores, raw/max and no-band semantics |
| Analytics | Page and panel headings, generic filters, metric labels, Compare/action/empty-state copy, accessible chart/control labels | Authored/API labels containing test content, numeric values and chart data |
| Profile/auth/session restore | Page/form labels, common validation fallback/pending copy, Login/Register form chrome, restore/loading text | User-entered fields, server auth decisions |
| Admin | Dashboard/page labels, user-list tabs/search/pagination, status/role display labels, common user actions/dialogs, guard heading and explanation | Names, emails, user records, counts |
| Builder/Transfer first pass | Major page labels/descriptions, test list/search/tabs, New test and metadata-form labels, version lifecycle/Preview/Publish/Clone/Archive actions, save-status chrome, Builder workspace tabs, module overview labels, top-level module create/delete dialogs, Transfer import/export/file selection and common result labels | Authored titles/descriptions, prompts, passages, questions, options, instructions, asset names/content |

Highly specialized Builder copy is deferred: nested question-type editors, registry-specific instructional explanations, answer-key guidance, completion canvas/tooltips, diagram marker tools, and audio-range editor/clip-capture guidance. Their generic shared dialog/action primitives may use translations, but this phase does not traverse every specialized string. Range functionality, clone/ZIP preservation, lifecycle mutations, and registry architecture remain intact. Do not translate instruction templates that form IELTS question content merely because they live in a frontend registry.

Common/static runner system copy is translated during this phase through the shared dictionaries. Apply the same keys where those existing controls occur in Reading, Listening, and Writing runners, paused gates, answer review, DraftPreview, and Full Mock transitions. Translate only existing application-owned strings and accessible labels; do not add controls, change layout, replace renderers, or localize authored exam metadata/content. Generic audio-player UI can translate while clipping, seeking permissions, playback speed behavior, and Full Mock audio policy remain unchanged.

Wire translations into the existing client components at their text/accessible-label slots. Keep the runner instance, attempt/card keys, answer stores, timer timestamps, audio element/source/position/speed, highlights, flags, autosave and request lifecycles stable. Locale or `t` must not become a key or dependency that reinitializes an attempt, resets state, recreates audio, or restarts requests. A locale change updates presentation only: it must not issue a domain mutation, change an attempt payload, navigate, or remount the attempt.

Translate local static error/fallback copy in included surfaces, using existing status/code branches where present. Pass unknown server diagnostic messages through unchanged; do not infer a translation from arbitrary message strings or change backend contracts. Existing Vietnamese-only session-restore fallback is brought into the same English-default dictionary scope.

**Server boundaries:** retain async route components, `serverApiRequest`, `notFound`/redirect behavior, and server role guards. A client provider does not translate literal text already produced by a server component. Use an explicit small `UiText` component (exported with the provider) for static text slots and a minimal client presentation boundary where multiple translated attributes/labels are needed. `UiText` takes a key and scalar values and renders escaped text, not a wrapper element.

Allow `PageHeading` and `EmptyState` text slots to accept `ReactNode` rather than only `string`, so server pages can pass `<UiText message="pages.practice.title" />` or a raw authored title in the same existing primitive. Native `aria-label`, placeholders, and button text are translated inside the relevant existing client feature view; server-heavy overview/library chrome may use one cohesive client presentation component per feature, receiving the same serializable DTOs. Never pass a translation function across the server/client boundary, mark async fetching pages `use client`, or move server auth/API imports into a client component.

For shared module/status badges, retain enum-to-style mapping and allow translated display labels at workspace and common runner system-UI call sites. Separate stable enum/skill/unit identifiers from visible translated labels. In Skill Practice, generate labels from existing metadata at render time, preserving its normalized target values, search matching inputs/algorithm, mounted-card keys, and attempt payloads. Locale is not a React remount key; switching it must not lose a chosen timer, pending request, search, editor draft, or dialog state. Existing metadata labels used for search remain stable in this phase so translation does not become a search redesign.

Never translate authored test titles/descriptions, passage titles or Reading passage text, Listening authored content, question prompts, answer options, Writing prompts/excerpts or responses, administrator-authored test instructions, manually authored section/task content, answer keys/explanations originating from test data, or user-entered fields. These values remain byte-for-byte unchanged in data and display-equivalent in their existing content slots. Generated system labels such as `Question {number}`, `Section {number}`, `Passage {number}`, or `Task {number}` can translate; an authored title must never be treated as such a label. Do not mutate DTOs to replace content or write localized strings through save APIs. The locale changes the application interface, not IELTS test content; do not infer or rewrite authored-content language from the selected UI locale.

## 12. Responsive behavior

Choose **wrapping horizontal navigation at every size**, with no drawer, popup menu, or horizontal clipping. One navigation DOM/list adapts through CSS; do not maintain hidden desktop/mobile copies.

| Width | Header arrangement | Navigation and actions |
| --- | --- | --- |
| ≥1440px | Brand, nav, actions across one header row when they fit; 72px minimum height, automatic actual height. | All visible links in existing order. Nav may wrap inside its allocated area for longer Vietnamese labels; controls do not disappear. |
| 768–1439px | Brand/actions first row, primary nav full-width second row. | Nav wraps naturally, 8px horizontal/4px vertical gaps; actions wrap within their group if needed. Sticky header remains one unit with auto height. |
| <768px | Brand first row, actions next row, wrapped primary nav below. Header uses normal flow rather than sticky positioning. | Actions wrap in the same DOM order; every visible destination is a link in the wrapped list with a 44px minimum target. No menu state, animation, or scroll-only navigation. |

Keep the brand name but omit the redundant header tagline at all widths; the footer supplies the product description. Constrain the visible account name to 120px on desktop/medium and 96px on small screens with ellipsis, while retaining its full accessible text. Navigation labels wrap at word boundaries and are never ellipsized. At 320px, ADMIN and Vietnamese navigation can occupy several rows; this is an accepted readability tradeoff, and the non-sticky small header keeps content accessible on short screens.

Page headings/actions stack naturally, footer groups stack, and content padding follows section 5. Existing Practice filters, grids, History tabs, Builder local navigation, and review layouts retain their feature-specific responsive rules. Change old `.app-sidebar`/`.sidebar-*` rules and header column assumptions; do not remove `.practice-filter-panel` or `.builder-local-nav`. Use CSS media queries, not `window.innerWidth`, to choose initial markup.

## 13. Exam-route isolation

AppShell performs its existing `/attempt/` bypass before rendering GlobalHeader/AppFooter. LocaleProvider remains outside it and is available to existing runner components for common/static system copy and accessible labels during this phase. This context access does not require a new runner language control or shell element. No global navigation, footer, width restriction, padding, or new fixed element can enter an attempt.

Keep the existing exam token values at the inspected baseline:

| Exam token | Light | Dark |
| --- | --- | --- |
| `--exam-bg` | `#eef2f8` | `#101319` |
| `--exam-surface` | `#ffffff` | `#191e27` |
| `--exam-surface-alt` | `#f5f7fb` | `#1e242e` |
| `--exam-text` | `#172039` | `#e8ecf3` |
| `--exam-muted` | `#626e88` | `#a1abba` |
| `--exam-border` | `#d6deeb` | `#364050` |
| `--exam-control-bg` | `#ffffff` | `#2a3342` |
| `--exam-control-text` | `#172039` | `#edf0f7` |
| Base `--exam-accent` | `#256ea5` | Resolved existing `#9aa6e8` |
| Listening accent | Existing `#7957d5` | Existing `#b1a2cf` |
| Writing accent | Existing `#cb6d30` | Existing `#d5a17d` |
| Highlight background/text | `#f4dc86` / `#252137` | `#cbb674` / `#191820` |

Root exam variables remain explicit; dark base `--exam-accent` must not follow the new workspace `--accent`. Existing `.listening-exam`/Writing accent relationships and exam controls must resolve to the baseline module colors, not the new muted workspace colors. Freeze the existing inherited shared-token dependencies under `.exam-shell` and `.exam-runner` in both themes (including module/accent, ink/surface/line, status/highlight, contrast/shadow tokens actually consumed there). This scoped compatibility layer also protects Builder previews, which live inside AppShell. Preserve current 15px inherited exam body size, runner button metrics, question group styles, focus/navigation states, and established responsive rules; scope workspace typography overrides to exclude runner descendants.

This is CSS compatibility protection, not a renderer/token architecture refactor. Audit existing references rather than blindly replacing `--exam-*` with workspace aliases. Paused gates under `.exam-shell` retain their existing readable appearance. Review answer content and renderer behavior remain unchanged; ordinary review headings/surfaces can inherit the paper workspace chrome without altering correctness highlights, raw/max, accuracy, or band semantics.

Only static UI strings/accessible labels are wired to shared translations inside runners; translated text must fit the existing controls without changing exam layout, styling, or tokens. The shared ThemeToggle also receives localized generic accessible copy, with its placement and exam styles intact. Full standalone Listening and Full Mock audio policies, optional focused audio fallback, clipping, seeking, speed, timers, autosave, highlighting, flags, scoring, attempt state transitions/security behavior, and authored content are untouched. Switching locale cannot reset answers/timer/audio state, remount the attempt, restart requests, or change attempt payloads.

## 14. Accessibility

- Use header, one primary navigation landmark, the existing shell main landmark, and the global footer landmark on normal pages. New header/footer components introduce no nested main landmark. Add a keyboard-visible skip link to `#main-content`; do not inject it into an exam runner. Existing feature-owned runner/preview/review structural markup remains unchanged; static system text/accessible labels can translate within it.
- Active navigation uses `aria-current="page"`, 600 weight, and a visible underline/bottom marker in addition to color. Preserve visible focus rings and correct anchor semantics.
- Language controls use a named group and ordinary buttons with `aria-pressed`; full language names remain available to assistive technology. After switching, root `lang` updates to `en`/`vi`. Common runner controls and their accessible labels follow that locale; do not keep a blanket English language boundary around translated runner UI. Preserve authored content and its existing language metadata. Any English boundary for deferred specialized Builder copy applies only to that copy.
- Theme button uses localized action labels such as `Use dark theme` / `Use light theme` (`Dùng giao diện tối` / `Dùng giao diện sáng`), matching the next action. Icons are decorative; visible labels and accessible names stay synchronized.
- Keep logout dialog semantics, initial cancel focus, Tab containment, Escape/pending rules, and return focus. A language change while it is open updates copy without recreating the dialog.
- Translate existing common runner confirmation dialogs, timer/state labels, generated navigation labels, and generic audio-control accessible names together with their visible system copy. Preserve current dialog focus/pending behavior and control semantics; localization adds no new navigation or player behavior.
- Small-screen links/actions meet 44px target height. Wrapped navigation remains reachable in DOM order with ordinary Tab/Shift+Tab; no menu roles or arrow-key widget behavior are needed. Long Vietnamese labels and 200% text zoom must not be clipped by fixed heights.
- Require ≥4.5:1 for normal text, ≥3:1 for large text and meaningful control/focus outlines against adjacent surfaces. Quiet decorative dividers need not serve as control outlines: use `--line-strong` for interactive boundaries. Avoid applying opacity to muted text that lowers contrast.
- Proposed text/control pairs and 8% badge mixes were checked arithmetically during specification. Light primary/white is 5.78:1; light Reading/Listening/Writing badges are 4.91/4.99/4.86:1. Dark muted/raised is 5.96:1 and dark accent/action text is 7.69:1. Strong control border examples are 3.57:1 light and 3.06:1 dark on hover. Muted light text is dark enough for the hover surface; semantic success/warning/danger text on its soft background exceeds 5:1 in light and 6:1 in dark. Later validation checks actual rendered color mixes, hover states, and focus rings as well.
- Preserve reduced-motion support. Feedback states include readable text/icons and semantics rather than relying solely on color. Retain existing alert/status roles where they communicate errors or pending work.

## 15. State persistence and hydration

**Locale:** SSR and the first client render both use `en`, including translated headings and selector state. Never read localStorage during module evaluation, render, or a state initializer. A provider mount effect reads `ielts-locale`, accepts only `en`/`vi`, updates state and root `lang`, and completes restoration. Do not write the default before restoration finishes. A stored Vietnamese preference therefore replaces English copy after hydration; a brief English first paint is accepted. No locale bootstrap rewrites server-rendered text, no cookie/server lookup, and no broad hydration-warning suppression.

The same restoration or an in-session locale switch can update common runner copy after an attempt is mounted. Neither operation may recreate/reset the runner, answers, timer timestamps, audio state, or requests; the provider and attempt identity remain stable.

**Theme:** retain `ielts-theme`, `data-theme`, two CSS palettes, and the trusted inline theme initialization location. RootLayout still renders `data-theme="light"`. The bootstrap selects a valid stored light/dark preference or **light** if absent/invalid/unavailable. Remove the existing `matchMedia` default branch; OS preference must not silently select a third policy. It may set only the root theme attribute before paint, with the existing narrowly scoped root `suppressHydrationWarning`. It does not change child text or structure.

ThemeToggle's initial React markup/state is deterministic light. Its post-hydration layout effect reconciles with the bootstrap/root value and updates the accessible next-action label; clicks update the root attribute and its own state immediately, then persist best-effort. No new theme provider/package is necessary. Preserve existing CSS label visibility if retained, but keep the accessible action label in sync. Runner toggles continue working without a GlobalHeader.

**Failures:** catch reads/writes separately for each preference. Missing/invalid storage values use en/light. Failed writes still allow a switch for the current document. Preference failures do not produce error banners, break auth, or block practice. Keep the preference across client route transitions and logout; do not key providers or pages by locale/theme. Cross-tab synchronization is outside this phase; each tab can restore on its own mount/refresh.

**Other SSR data:** pass the current footer year from the server to AppShell/AppFooter, using the same value in initial client markup rather than independently calling the client clock. Auth loading and server page data behavior remain unchanged. Do not branch responsive structure on client measurements or translate by mutating the DOM.

## 16. Testing strategy

The later implementation uses focused Vitest/RTL and CSS contract checks. This document change itself needs substantive self-review and `git diff --check`, not application test execution.

| Test area | Required focused coverage |
| --- | --- |
| AppShell/header | One horizontal primary nav, no global aside/sidebar, guest/USER/ADMIN links, stable destinations/order/prefetch policy, active Overview/Admin/Builder/Transfer, profile no invented active link, account loading/errors, existing logout guard/dialog behavior. |
| Footer/routes | Footer on normal route and review/transition/auth routes; no header/footer on attempts; no global footer but retained header on exact Builder preview path, including query/trailing slash; non-preview Builder still has footer; existing shell main retained with no extra main introduced by header/footer. |
| Locale | Default English under SSR/initial render, valid Vietnamese restoration, selection and live copy updates, persistence/remount, invalid values, throwing reads/writes, root lang, typed dictionary parity, plain parameter interpolation, both singular/plural branches where used. |
| Content/state | Authored titles, prompts/excerpts/options and user names unchanged; language change preserves Practice filters/search/timer/pending guard and Builder draft/dialog state; unchanged focused attempt payload and no new HTTP request caused by locale choice. |
| Runner localization/state | In a mounted attempt, switch EN → VI → EN through the shared provider and verify common visible controls, timer/state labels, confirmation text, generated unit/question labels, and generic audio accessible labels update where present. Assert authored passage/title/instruction/prompt/option/response fields, plus keys/explanations where existing finalized review data includes them, remain byte-for-byte unchanged and their rendered content stays display-equivalent. Assert the same runner and audio element (when present) remain mounted, edited answers and timer timestamps remain intact, audio position/speed/state is retained, requests are not restarted, and attempt payloads are unchanged. Use a provider test harness to switch locale without adding production shell chrome. |
| Theme | Existing `ielts-theme`, correct root attribute, both click directions, saved preference restoration, no-saved light even when mocked OS preference is dark, invalid/unavailable storage, localized next-action name, deterministic server markup/limited bootstrap mutation. |
| Responsive semantics | One nav/list at every breakpoint, visible-role link semantics, no duplicate desktop/mobile nav or drawer; CSS assertions for wrap, small non-sticky header, padding and target sizes. RTL does not claim to verify actual pixel layout. |
| Visual compatibility | Tokens present in both themes, flat workspace backgrounds, reduced glows/shadows, readable text/control/semantic contrast using existing luminance helper, retained focus/reduced-motion rules, frozen exam values/inherited dependencies and runner sizes. |

Extend existing `auth.test.tsx`, `root-layout.test.tsx`, and `theme-toggle.test.tsx`; add focused shell/footer and locale tests as needed. Update `visual-system-css.test.ts` and `dark-theme-css.test.ts` assertions that require the old sidebar, brand glow, fixed typography, or galaxy naming. Retain useful semantic/contrast checks and `exam-theme-css.test.ts` safeguards. Reuse `skill-practice.test.tsx`, relevant practice/library, History, Admin/Builder navigation, and preview tests only for changed presentation boundaries. Add focused locale-switch cases to the existing Reading/Listening/Writing runner tests and relevant shared dialog/player tests, using fictional fixtures and mocked audio rather than real playback. Verify `/attempt/*` still has no global header/footer and CSS/structure contracts preserve exam layout, styling, and tokens. No unrelated suite expansion.

Later validation is targeted `npx vitest run <changed-area test files>`, `npm run typecheck`, `npx eslint <changed TS/TSX files>`, and `git diff --check`. Use CSS/type/lint contracts rather than large DOM snapshots or pixel typography tests. No browser, Playwright, E2E, Next dev server, backend suite, real audio, or AI calls are required. Exact test file selection belongs to the implementation change, not a detailed implementation plan in this spec.

## 17. Risks and compatibility concerns

| Risk | Required mitigation |
| --- | --- |
| More available width after removing 248px sidebar | Explicit 1280/1440px maxima and inner form/prose limits; preserve existing feature grid behavior. |
| ADMIN/Vietnamese links exceed a single row | Automatic wrapping, explicit medium/small arrangements, no text clipping, non-sticky small header. |
| Client context cannot translate server literal strings | Explicit UiText/client presentation boundaries; preserve server fetching, serializable DTOs, and auth guards. |
| Shared token/CSS changes leak into exams | Freeze resolved exam and inherited dependencies; exclude runner descendants from workspace type/button changes; targeted CSS regression checks. |
| Locale change resets an attempt or restarts work | Stable feature/card/provider/attempt keys and runner/audio instances; no locale/translation dependencies in initialization, timer, autosave, playback, or request lifecycles. Preserve answers, timer timestamps, pending starts, editor drafts, and payloads. |
| System copy is confused with authored exam content | Translate only application-owned static strings/generated labels; preserve test-data titles, instructions, prompts/options, responses, keys/explanations and language metadata verbatim. |
| Translated runner labels accidentally trigger visual redesign | Wire text/accessible-label slots only; preserve existing controls, layout, exam tokens, focus behavior, and playback/state-machine rules; targeted CSS/structure and state-preservation tests. |
| Changing strings accidentally changes identifiers/search | Retain API enums/targets and existing search inputs/algorithm; localize only displayed system labels. |
| Existing CSS tests enforce obsolete aesthetics | Replace precise obsolete expectations with approved token/structure checks; preserve contrast, exam, responsive, and semantic assertions. |
| Storage is blocked or corrupt | Deterministic defaults, validated restoration, best-effort writes; no error UI for preference failures. |
| Theme baseline contains implicit OS behavior | Explicit saved-or-light bootstrap decision and regression test; preserve valid saved dark preferences. |
| Preview receives duplicate footers | Exact preview path exclusion while retaining existing Admin guards/header and local exam footer. |
| Partial specialized translation looks inconsistent | Clearly bounded common/major Builder scope; only the specified specialized Builder-editor copy remains deferred. Common/static runner controls are included, while authored IELTS content is always excluded. |

No dependency/lockfile, generated asset, migration, API schema, or copyrighted-content change is needed. Existing published version immutability, frozen historical references, server evaluation/deadlines, structured question registries, Builder range data, and role authorization are unaffected.

## 18. High-level rollout sequence

1. Establish typed English/Vietnamese dictionaries, browser-local LocaleProvider, and minimal client text boundaries.
2. Split AppShell/Header/Footer responsibilities while preserving auth/route behavior.
3. Replace global sidebar with wrapping horizontal navigation and add the shared footer with exact exclusions.
4. Apply paper theme tokens together with exam compatibility protection and saved-or-light theme initialization.
5. Apply workspace typography, buttons, surface/gradient cleanup, content widths, and spacing.
6. Translate shell/common primitives and existing common/static runner controls, dialogs, timer/state copy, generated labels, and accessible action labels without changing runner behavior.
7. Translate the selected main-page and common Admin/Builder/Transfer presentation scope, retaining authored data and server fetching.
8. Complete focused regression validation and remove obsolete global-sidebar styling/assertions.

This is architectural sequencing only. It does not introduce implementation tasks, begin product changes, or request backend work.

## 19. Acceptance criteria

For the later frontend implementation:

1. Normal pages have one horizontal primary navigation and no permanent global Workspace sidebar; existing routes/order/role visibility and guards remain intact.
2. Header context duplication is removed, existing local feature navigation/back links remain, and locale/theme/account actions follow the specified order.
3. Navigation wraps at the defined sizes without a drawer, duplicate DOM, clipped destinations, or responsive hydration branching.
4. Footer content is real, restrained, localized, and uses the current server-supplied year. It appears on ordinary pages, is absent on `/attempt/*` and exact Builder preview routes, and does not replace a local exam footer.
5. Typography, sentence case, button metrics/variants, spacing, and page-family width limits follow sections 5 and 7 while authored title case remains untouched.
6. Light uses the warm paper palette and dark uses warm graphite; module/status colors stay distinguishable, gradients/glows are removed or reduced as specified, and readable contrast/focus indicators remain.
7. Theme uses only light/dark, the existing storage key/root attribute, valid saved preferences, and an explicit light fallback; no auto/system mode or new package is introduced.
8. EN/VI system UI uses typed local dictionaries, default en, `ielts-locale`, accessible selector state, and best-effort restoration/persistence without routes/cookies/backend preferences.
9. Both dictionaries cover the phase-1 translation table, including page headings/actions/empty states, common Builder/Admin chrome, and existing common/static runner controls, generated labels, timer/state copy, dialogs, error/fallback text, and generic audio UI/accessible labels. Specialized Builder-editor copy remains deferred; authored IELTS content remains untranslated.
10. Server API fetching, guards, serialization boundaries, API enums, authored IELTS content, and user-entered fields remain unchanged. Switching language preserves active feature state and causes no domain mutation or new auth fetch.
11. Initial server/client markup is deterministic; locale restores after hydration, theme bootstrap is restricted to its root attribute, and storage failure does not block use.
12. Attempts remain isolated from global chrome and workspace widths/styles. Runner localization changes only static UI strings/accessible labels. Baseline exam tokens, layout, inherited appearance, question behavior, audio policies, timers, autosave, highlighting, flags, Full Mock behavior, scoring, and the attempt state machine remain stable.
13. Focused frontend tests, typecheck, targeted ESLint, and diff checks pass; no browser/E2E/dev server/backend/AI validation is required.
14. No functional Library/Practice redesign, thumbnail system, migration, new authentication/Speaking/AI behavior, font binary, or new dependency is included.
15. Focused EN/VI-switch tests prove common runner controls update, authored IELTS data remains byte-for-byte unchanged/display-equivalent, the attempt/runner/audio instances are not recreated, answers and timer/audio state remain intact, requests do not restart, and payloads do not change. Attempt header/footer exclusion and exam CSS/layout contracts continue to pass without browser/E2E validation.

For this specification deliverable: repository inspection is recorded, all requested decisions and boundaries are resolved, and only this document is committed and pushed. Product implementation stops outside the scope of this task.
