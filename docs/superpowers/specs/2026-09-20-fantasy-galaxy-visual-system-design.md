# Fantasy Galaxy Visual System Design

**Date:** 2026-09-20
**Status:** Approved for implementation

## Purpose

Redesign the existing IELTS Studio frontend as a cohesive, premium learning platform inspired by a calm magical observatory. The visual identity uses deep cosmic navy, indigo, sapphire, violet, and cyan starlight while preserving the current product name, application architecture, and all behavior.

The redesign must feel polished because of hierarchy, typography, spacing, surface depth, and consistent interaction patterns. It must not depend on copied branding or layouts, raster galaxy imagery, particles, WebGL, or excessive glow and glass effects.

## Scope and constraints

The work is frontend-only. It covers the application shell, navigation, dashboard, learner library, attempt history, admin test library, test detail, builder workspace, Reading and Listening builders, draft preview, Candidate Reading and Listening, review screens, shared dialogs, popovers, empty states, badges, forms, buttons, and question renderers.

The redesign does not change backend APIs, database models, migrations, persistence, evaluation, publishing, attempt lifecycle, or question data structures. It specifically preserves:

- one-sentence-per-block Text Completion authoring;
- caret and focus behavior in the completion canvas;
- stable GAP and Question UUID identity and correct numbering after reload;
- alternative text answers and advanced answer settings;
- multiline completion instructions;
- validation and publish flows;
- autosave and timestamp-derived timers;
- bottom question navigation and flags;
- semantic-offset highlights, hydration-safe popovers, and Delete all highlights;
- shared Listening audio and player behavior;
- History Continue, Review, and Delete actions;
- archive, immutable version, and frozen-attempt lifecycle behavior.

## Visual direction

IELTS Studio becomes a quiet cosmic observatory for study rather than a gaming or cyberpunk interface.

- Dark mode is the hero experience: midnight navy foundations, layered blue surfaces, subtle translucent borders, and localized cyan/violet illumination.
- Light mode uses cool near-white foundations, crisp elevated surfaces, soft indigo shadows, and the same accent language.
- Atmospheric depth comes from a small number of CSS radial gradients and lightweight pseudo-elements. Decorative star details appear only in shell and feature surfaces, never around long-form Reading content.
- Most cards remain opaque or nearly opaque. Glass treatment is reserved for navigation, sticky toolbars, dialogs, and a few hero surfaces.
- Motion is limited to 120–220 ms hover, focus, active-navigation, and dialog transitions, with `prefers-reduced-motion` support.

## Semantic token architecture

The existing `data-theme="light"` and `data-theme="dark"` architecture remains authoritative. `globals.css` defines a compact semantic token set:

- Background: `--app-bg`, `--app-bg-elevated`
- Surfaces: `--surface`, `--surface-raised`, `--surface-soft`, `--surface-hover`, `--surface-glass`
- Text: `--ink`, `--ink-soft`, `--muted`
- Lines: `--line`, `--line-strong`
- Brand: `--accent`, `--accent-strong`, `--accent-soft`, `--accent-violet`, `--accent-cyan`
- Semantic: `--success`, `--warning`, `--danger` and their restrained soft variants
- Effects: `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--glow-accent`, `--glow-violet`

Compatibility aliases may remain for existing specialized variables such as Reading, Listening, highlight, and exam tokens. Page-specific values are derived from semantic tokens instead of introducing unrelated colors.

Candidate exam surfaces retain a dedicated `--exam-*` token layer derived from the active theme. This is not a second theme implementation; it is a semantic subset that limits atmosphere and maximizes readability.

## Shared presentation system

Existing primitives remain the primary boundaries. `PageHeading`, `StatusBadge`, `ModuleBadge`, `EmptyState`, `ConfirmDialog`, `ThemeToggle`, and AppShell receive consistent treatments through shared classes and tokens.

Buttons use five variants: primary, secondary, ghost, danger, and icon. Destructive actions stay compact and visually quieter than primary workflow actions. Forms share consistent height, padding, border, placeholder, focus, disabled, and validation states. Cards use moderate radii, subtle borders, restrained shadows, and only localized accent highlights.

Typography establishes reusable eyebrow, page title, subtitle, section title, card title, body, metadata, label, and status levels. Long Reading text prioritizes editorial line length, paragraph spacing, and line height over brand spectacle.

## Application shell and navigation

The desktop shell keeps its header-and-sidebar structure while gaining the fantasy-galaxy atmosphere. The shell backdrop supplies static navy, cyan, and violet light layers. The raised header and sidebar use controlled translucency, and active navigation receives a single luminous accent. The current IELTS Studio name and route structure remain unchanged.

Responsive behavior keeps the compact horizontal navigation pattern below the existing breakpoint. Navigation labels remain available at tablet widths and icon-only treatment is limited to small screens with accessible labels preserved.

## Learner-facing pages

### Home

The dashboard becomes a product-led learning portal. A generous hero communicates the value proposition and offers a primary practice CTA plus a secondary authoring/history route. Summary metrics remain available but no longer dominate. Below the hero, four pathway cards organize Test Library, Reading, Listening, and History/Progress with disciplined module accents.

### Library

Published modules appear as scan-friendly test cards with module identity, title, description, version metadata, and a prominent Start action. Reading uses cyan/blue; Listening uses violet. Card decoration remains restrained, with module identity expressed through a small top accent and localized glow.

### History

Attempts become compact practice-record rows. Test title, module, version/date, status, elapsed time, and the primary Continue/Review action form the scan path. Delete remains a danger-ghost action and never competes with resumption or review.

## Admin and builder

Admin pages use the same design system with slightly denser information layout. Status filters, search, Create Test, draft/published/archived distinctions, and version rows receive clearer hierarchy.

The Builder preserves all working components and data flows. Its sticky toolbar clarifies Draft, Validate, Preview, Publish, and deletion priorities. The local structure navigation shows selected workspace and Created/Not created states with module accents. Main canvas surfaces reduce nested-card weight through spacing, softer group backgrounds, and clearer parent/child depth.

Reading passages and Listening sections remain the strongest containers. Question groups become compact summary rows. Editors use visual sections for Instruction, Content, Answer configuration, and Advanced settings where the existing markup allows this without behavioral restructuring. Text Completion sentence blocks remain clean editing canvases with compact gap tokens and subtle selected states.

## Candidate exam and preview

Candidate mode deliberately suppresses the dashboard atmosphere. It uses calm navy or cool-white foundations, opaque editorial surfaces, restrained borders, and minimal glow limited to controls and focus.

Reading keeps the split-pane structure. Passage typography receives comfortable measure, line height, paragraph spacing, and heading scale. Questions use quiet group separation and clear instructions. Header, timer, save state, highlight controls, theme toggle, footer navigation, question chips, flags, and Submit retain current behavior.

Listening may carry slightly more violet/blue identity in the raised audio player. Playback, seek, volume, speed, and time controls remain practical and do not imitate entertainment streaming products.

Draft Preview shares Candidate rendering but identifies itself with a restrained preview state and remains functionally isolated from saved answers.

## Review, dialogs, and highlights

Review surfaces remain educational. Correct and wrong answers use subtle tinted borders rather than filled green/red panels. Your answer, Correct answer, and Explanation become distinct typographic rows while preserving the original question layout.

Dialogs, highlight popovers, dropdown-style surfaces, and validation panels share surface, border, radius, shadow, spacing, and action alignment. Highlight colors remain readable and not overly saturated in either theme.

## Accessibility, responsiveness, and performance

- Preserve semantic HTML, keyboard navigation, ARIA labels, and existing focus behavior.
- Maintain visible `focus-visible` rings with WCAG-conscious contrast.
- Keep controls at practical touch sizes and prevent horizontal page overflow.
- Preserve builder productivity on desktop while stacking or scrolling local navigation gracefully on smaller screens.
- Use CSS gradients and pseudo-elements only; no new image or animation dependency.
- Avoid continuous animation and disable nonessential transitions for reduced-motion users.

## Verification

Implementation is complete only after:

- visual inspection of Home, Library, History, Admin, Builder, Candidate, Preview, and Review where data is available;
- light and dark theme inspection;
- desktop and responsive viewport inspection;
- `npm test`;
- `npm run lint`;
- `npm run typecheck`;
- `npm run build`;
- `git diff --check` and `git diff --cached --check`;
- final diff inspection confirming no backend, environment, secret, or unrelated changes.
