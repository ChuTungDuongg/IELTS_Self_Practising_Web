# Admin Speaking Benchmark UX audit

Initial inspected commit: `ee4757d69089aeb2d3146435509918716a83f28d`. Follow-up inspected local and remote `main`: `2c1e3498af4d5d59764ef2e51b92b0529f8ec8a6` (9 November 2026).
Scope: all ten Speaking Benchmark routes, P1–P4 components, shared BandPilot navigation/tokens and the sibling Writing bank. Implementation is frontend only; no API contracts, backend rules, migrations or provider calls changed. A subsequent user instruction authorizes committing and pushing `main` and fixing failed CI. Deployment is outside this task.

## Journeys and navigation

| Journey | Workflow retained | Location after refinement |
| --- | --- | --- |
| P1 | Upload → CPU diarization → speaker confirmation → Part boundaries → question context → source-bound approval | Recordings → Preparation: Recording review / Question assistant |
| P2 | Approved revision → preflight → explicit provider estimates and consent → grading → human comparison | Recording → AI Evaluation; aggregate reports under the lab's AI Evaluation section |
| P3 | Independent human transcript → frozen experiment setup → ASR comparison / paired grading → report | Recording → Research for references; Research for experiments |
| P4 | Suggestions → independent assessments → agreement → adjudication → QA → frozen suites → release gates | Recording → Human assessment; Quality & release for dataset tools |
| Blind review | Assigned recording → independent scoring → attestation → submitted assessment | Tasks & other labs → My blind review assignments |

Before: `/admin/speaking-benchmark` had seven equally styled links (Reports, Research, Quality, Suites, Gates, Blind Assessment, Writing). Other screens repeated different subsets. A recording had six peer tabs.

After:

```text
Speaking Benchmark Lab
  Recordings                         /admin/speaking-benchmark
    Recording                        /[sampleId]
      Preparation                    Recording review / Question assistant
      Human assessment               Human reference label / Raters & consensus
        Raters & consensus           Assignments / Assessments / Agreement / Adjudication
      AI Evaluation                  Preflight, consent, history, comparisons
      Research                       Independent human transcripts
  AI Evaluation                      /reports
  Research                           /research, /research/[experimentId]
  Quality & release
    Dataset Quality                  /quality
    Evaluation Suites                /suites
    Regression Gates                 /gates
  Tasks & other labs
    My blind review assignments       /reviewer, /reviewer/[assignmentId]
    Writing benchmark bank           /admin/writing-benchmark
```

All route URLs/deep links remain. The existing global BandPilot header is retained. Mobile lab navigation and recording work areas use native selectors; local task tabs wrap. No additional sidebar or global state provider was introduced.

## Findings and implementation

`Browser` means reproduced with real components and CSS in the isolated synthetic preview. `Code` means established by source inspection; it is not a claim of a visually reproduced defect.

| Priority | Finding / evidence | Source in `frontend/src/features/speaking-benchmark/` | Change |
| --- | --- | --- | --- |
| High | Seven competing page links; Browser + Code | `sample-list.tsx` | Four primary sections, release subnavigation, task/other-lab disclosure. One upload action reveals a mounted form. |
| High | Six peer recording tabs mix preparation, scoring and research; Browser + Code | `recording-workspace.tsx` | Four work areas with task-specific navigation; all editors remain mounted. |
| High | Five blind scoring columns overlap at 390px; Browser | `blind-reviewer.tsx`, `quality/quality.module.css` | Shared labelled assessment fields, 5/3/2-column progression, full-width final field and single-column mobile comments. |
| High | Quality policy precedes results; Browser + Code | `quality/quality-dashboard.tsx` | Audit action and results first, severity filter, advanced policy and snapshot history disclosures. |
| High | Gate output omits matched coverage and reasons and styles every non-pass metric as failure; Code | `quality/gate-manager.tsx` | Extracted `gate-report.tsx`; real matched counts, differences, all four decision states, visible decision reasons/limitations. Missing values stay unavailable. |
| High | Accepting one proposal clears drafts on other proposals; Code + regression test | `question-assistant.tsx` | Clear only decided proposal drafts; display confirmed decision text/Part and distinguish accepted/rejected/unresolved proposals. |
| High | Adjudication bands alone do not mark the workspace dirty; Code + regression test | `human-adjudication-panel.tsx` | Include changed bands in dirty reporting and reset the completed form after successful adjudication. Refresh accepted question revisions without clearing another proposal's dirty guard. New lab navigation preserves discard confirmation and focus restoration. |
| Medium | Rater management, assessments, agreement and adjudication compete on one surface; Browser + Code | `human-adjudication-panel.tsx` | Context-specific persistent sections, shared `assessment-fields.tsx`; draft state remains with the owner. |
| Medium | Question provider setup dominates existing proposals; Browser + Code | `question-assistant.tsx` | Setup disclosure, concise workflow explanation, visible preflight/consent, proposal audio controls, persisted job history selector. Accept still adds to the review draft; no invented apply stage. |
| Medium | Suite creation/history/technical evidence lack clear separation; Code | `quality/suite-manager.tsx` | Distinct create/inspect surfaces, frozen binding disclosure, source/revision explanation, visible holdout warning and separate inspection/creation consent. |
| Medium | Gate configuration duplicates selectors and exposes thresholds constantly; Code | `quality/gate-manager.tsx` | Extracted `gate-source-selector.tsx`; baseline/candidate grouped, thresholds/coverage secondary, selected gate source evidence available. |
| Medium | English-only P4 labels, unassociated comment labels and hardcoded status colours; Browser + Code | P4 components and `quality/quality.module.css` | EN/VI messages, linked labels, semantic success/warning/danger tokens. Neutral counters replace individual KPI cards. |
| Medium | List/upload proportions create a large unused region; Browser + Taste inspector | `sample-list.tsx`, `lab.module.css` | Upload becomes one deliberate expandable action. File input and other unfinished fields survive collapse. |
| Medium | Narrow forms, long fingerprints and tables risk overflow; Browser + Code | Lab, research and quality CSS modules | Shrinkable fields, wrapping identifiers, local table scrolling, sticky quality identity columns, consistent 44px frequent controls. No fields are removed on mobile. |
| Low | Assignment list lacks loading/empty/retry hierarchy; Code | `assigned-reviews.tsx` | Standard page heading/navigation, explicit loading/empty state, bounded paging and retry. |
| Follow-up | QA and suite selection use only the first 25 returned samples; Code | `quality/quality-dashboard.tsx`, `quality/suite-manager.tsx` | Visible scope note. Cohort semantics deliberately remain unchanged; needs a separate selection/pagination decision. |

Shared shell and Writing bank were inspected for typography, surfaces, action placement, auth/dirty guards and theme conventions. Their existing identity was reused; unrelated learner, Classroom, Builder and exam screens were not redesigned.

## Design guidance applied

- Read [Taste](../../.agents/skills/design-taste-frontend/SKILL.md) and its complete [application-screen guidance](../../.agents/skills/design-taste-frontend/references/app-screens.md). Drew the application `framed-sheet` direction, seed `293042844`, with palette/type kept. Its quiet surfaces, underline navigation, regular data figures, restrained semantic colour and emphasis on the screen's main job informed the implementation. The user's existing-shell constraint takes precedence over creating the dealt sidebar/frame or replacing fonts. BandPilot's mark, Raleway headings, system body font, tokens and account accents remain authoritative.
- Used [UI/UX Pro Max](../../.agents/skills/ui-ux-pro-max/SKILL.md) locally: design-system query, navigation/disclosure searches, keyboard focus, long-token wrapping and Next.js stack search. Applied the relevant web guidance: labelled controls, visible focus, native mobile selectors, 44px controls, semantic tokens and responsive field grids. Its unrelated marketing layout/palette/font suggestions and Server Actions suggestion were not adopted. The disclosure search did not return a verified relevant match after narrowing; disclosure decisions came from Taste's application guidance and the repository rather than claiming a search recommendation.
- No new design-system/font/chart dependency or decorative animation was added. Motion remains existing product feedback; new navigation and disclosures work without animation.

## Changed files

- `.gitignore`
- `docs/testing/admin-speaking-benchmark-ux-audit.md`
- `frontend/src/features/speaking-benchmark/assessment-fields.tsx`
- `frontend/src/features/speaking-benchmark/assigned-reviews.tsx`
- `frontend/src/features/speaking-benchmark/blind-reviewer.tsx`
- `frontend/src/features/speaking-benchmark/evaluation/reports.tsx`
- `frontend/src/features/speaking-benchmark/human-adjudication-panel.tsx`
- `frontend/src/features/speaking-benchmark/lab-navigation.tsx`
- `frontend/src/features/speaking-benchmark/lab.module.css`
- `frontend/src/features/speaking-benchmark/navigation.module.css`
- `frontend/src/features/speaking-benchmark/persistent-sections.tsx`
- `frontend/src/features/speaking-benchmark/quality/gate-manager.tsx`
- `frontend/src/features/speaking-benchmark/quality/gate-report.tsx`
- `frontend/src/features/speaking-benchmark/quality/gate-source-selector.tsx`
- `frontend/src/features/speaking-benchmark/quality/quality-dashboard.tsx`
- `frontend/src/features/speaking-benchmark/quality/quality.module.css`
- `frontend/src/features/speaking-benchmark/quality/suite-manager.tsx`
- `frontend/src/features/speaking-benchmark/question-assistant.tsx`
- `frontend/src/features/speaking-benchmark/recording-workspace.tsx`
- `frontend/src/features/speaking-benchmark/research/research-detail.tsx`
- `frontend/src/features/speaking-benchmark/research/research-list.tsx`
- `frontend/src/features/speaking-benchmark/research/research.module.css`
- `frontend/src/features/speaking-benchmark/sample-detail.tsx`
- `frontend/src/features/speaking-benchmark/sample-list.tsx`
- `frontend/src/lib/i18n/en.ts`
- `frontend/src/lib/i18n/speaking-benchmark-quality-messages.ts`
- `frontend/src/lib/i18n/speaking-benchmark-ux-messages.ts`
- `frontend/src/lib/i18n/vi.ts`
- `frontend/tests/speaking-benchmark-quality.test.tsx`
- `frontend/tests/speaking-benchmark-ux.test.tsx`
- `frontend/tests/speaking-benchmark.test.tsx`
- `frontend/tests/ux-preview/auth.ts`
- `frontend/tests/ux-preview/index.html`
- `frontend/tests/ux-preview/main.tsx`
- `frontend/tests/ux-preview/next.tsx`
- `frontend/tests/ux-preview/playwright.config.ts`
- `frontend/tests/ux-preview/research-fixtures.ts`
- `frontend/tests/ux-preview/screens.spec.ts`
- `frontend/tests/ux-preview/vite.config.ts`
- `frontend/tests/ux-preview/workflow-fixtures.ts`
- `frontend/vitest.config.ts`

## Accessibility and state preservation

- Desktop tabs use roving focus, Arrow Left/Right, Home/End, stable tab/panel IDs, `aria-selected` and `hidden` panels. Native mobile selectors control those same mounted panels.
- New navigation has labelled landmarks and current destinations. Its utility disclosure supports Escape, returns focus to its summary and dismisses on outside click.
- Existing confirmation dialog focus trap, Escape and focus restoration remain. Recording lab links and the mobile selector honor dirty confirmation. Blind reviewer navigation also confirms before abandoning its own unsaved assessment.
- One source player remains outside recording panels. Browser tests check its DOM identity and count across work areas; existing audio regression tests check window playback boundaries and errors. Synthetic screenshots use generated silence, never private audio.
- Assessment fields have unique associated labels. Headers identify table columns; gate metric rows use row headers. Wider tables scroll locally. Semantic colours have text labels and inherit light/dark tokens; the inspector is not a complete WCAG certification or assistive-technology audit.
- Blind reviewer continues to call only its assignment-scoped APIs and display only its own submitted assessments. Human/AI references remain separated. Consent, billing recovery, holdout checks, revision/source selectors and API payloads are preserved.

## Visual evidence and reproduction

The preview in `frontend/tests/ux-preview/` renders production feature components, the actual shared shell, localization, styles and typed client parsers. Only Next routing/auth and network data are synthetic. It is not a database-backed authenticated end-to-end test. A visible fixture banner prevents scores/text being mistaken for real evidence. The test server generates silent WAV audio in memory; unknown mutations are rejected without forwarding any network request.

Run from `frontend/`:

```powershell
node node_modules/@playwright/test/cli.js test --config tests/ux-preview/playwright.config.ts
```

`UX_PHASE=before` was captured before editing the production UI. Re-running that flag on changed code does not reconstruct the original UI.

Artifacts are local and ignored by Git under `storage/ux-audit/`:

- `before/`: 28 screenshots, seven representative screens × 1440/1024/768/390px, light appearance.
- `after/`: 103 screenshots: list, detail, blind review, research list/detail, reports, quality, suites, gates and assignments; detailed AI consent/question/adjudication/create-form and dirty-draft captures. Light/Purple at all four widths; Dark/Blue, Dark/Orange/VI and Light/Green/VI at 1440/390px; empty and partial states.
- Useful comparisons: `before/list-1440-light.png` → `after/list-1440-light.png`; `before/human-390-light.png` → `after/human-390-light.png`; `before/quality-1440-light.png` → `after/quality-1440-light.png`; `before/gates-390-light.png` → `after/gates-390-light.png`.
- `taste-inspect/`: real-browser measurements and viewport screenshots. Final list inspection: **0 FAIL, 2 WARN**. Remaining warnings: installed system-font detection (`Segoe UI Variable` is BandPilot's system face) and a development preview. The earlier unequal list/upload panel warning was resolved by the expandable upload workflow.
- `taste-lint.log`: **0 FAIL, 9 WARN**. Warnings concern `box-shadow: none` declarations, the genuine floating utility menu, and missing-value em dashes across many components. These are intentional application patterns.

Screens exercised in the initial browser pass cover every route's feature component, with one correction: the report fixture's generic `/samples` matcher also caught `/reports/samples`, causing a parser error. The initial report captures therefore did not verify successful report rendering. The follow-up below fixes this matcher and replaces that evidence with valid empty and populated report captures. Before/after defects were visually inspected on the recording list and mobile blind form; additional representative review, gate, QA and localized dark screenshots were inspected manually. No claim is made that every captured pixel or every possible history/error state received manual visual review.

## Verification results

Final commands and outcomes are recorded here after the last run. Logs are retained under `storage/ux-audit/`.

| Check | Result |
| --- | --- |
| Focused P1–P4 + UX Vitest | 61 passed across 5 files |
| Full frontend Vitest | 2,032 passed across all 172 files in one complete final run (186.27s) |
| TypeScript | Passed |
| ESLint | Passed; zero errors or warnings |
| Production Next build | Passed |
| Synthetic Playwright | 4 tests passed together; all four widths, form preservation, keyboard/focus, consent, question/human tools, creation forms, accents/localization, empty/partial states; no page overflow |
| Existing browser smoke | `dashboard.spec.ts`: 1 failure in isolated API-unavailable mode. It expects the old “Practice with focus” heading and an authenticated Builder link; the unchanged guest homepage renders “Practice with purpose. Progress with confidence.” No live API/session was supplied. |
| Backend tests | Not run: no backend-facing contract or backend implementation changed |

The existing Vitest suite emits some jsdom media-method and research-fixture duplicate-key warnings; these must not be confused with a failed assertion or proof of real playback/provider accuracy. An intermediate full run exposed a timing failure in the same-page approval test. It now waits for the approval confirmation to finish before selecting AI Evaluation; mocks reset queued one-off responses between tests, and question-decision tests await the revision refresh.

## Remaining limits

- Real owner-scoped auth, PostgreSQL persistence, worker transitions, paid services, GPU execution, production browser rendering and actual model quality were not exercised by the synthetic preview.
- First-page-only QA/suite selection remains a documented product limitation. No new backend endpoint or automatic cohort expansion was introduced.
- Some existing backend diagnostic codes, provider IDs and research metric terminology remain technical. Release-affecting reasons/limitations stay visible; complete prose translation of server diagnostic payloads needs a separate shared diagnostic-copy contract.
- Browser checks used installed Edge. Safari/Firefox, real mobile hardware and screen-reader testing remain unverified.
- Commit/push to `main` is explicitly authorized by the follow-up request. GitHub Actions results for the resulting revision are reported with delivery. Existing unrelated untracked local files are excluded from the commit. No deployment was requested.

## Follow-up: readable reports and bilingual help

The user's screenshot highlighted the report's empty chart row, repeated empty tables and terse mixed-language copy. These were reproduced using the committed report components and corrected synthetic API fixtures before editing those components. No real recording, transcript, provider or database result appears in the evidence.

| Severity | Reproduced finding and source | Implemented change |
| --- | --- | --- |
| High | Three peer charts still occupy substantial space with zero pairs; `evaluation/report-charts.tsx`, `reports.tsx` | Honest empty state with a next action. With evidence, choose one chart using native keyboard-operable radios; exact values remain in its data table. Human-only distribution remains available when AI predictions are missing. |
| High | Eleven primary metric columns obscure the basic comparison; `reports.tsx` | Five main columns: criterion, paired/eligible count, mean absolute error, signed difference and within-half-band agreement. All other statistics remain under Advanced statistics. |
| Medium | Provider/version/date controls dominate routine filtering; `reports.tsx` | Three main selectors, persistent More filters disclosure, reset action and controlled date inputs. Full configuration fingerprints remain accessible. |
| Medium | Empty coverage, empty rows and pagination repeat the lack of data; `reports.tsx` | Render meaningful sections only, retain CSV/JSON export, and separate result pagination from exports. Actual zero remains zero; unavailable values remain a dash. |
| Medium | Report labels and status codes lack plain explanations; evaluation messages | Complete EN/VI report labels, explanations, loading/error/retry states, metric meanings and small-sample caution. Diagnostics remain accessible in a secondary disclosure. |
| Medium | No contextual instructions for the lab, reports or blind reviewer; `lab-navigation.tsx` | A collapsible semantic guide table for each context, with complete natural-language EN/VI instructions. Reviewer help contains no peer or AI scores. |
| Medium | Failed refresh can leave exports associated with a different filter selection; `reports.tsx` | Store successful results and their applied filters together. Explain retained results after a failure, retry without clearing evidence, and hide exports while refreshing. |
| Medium | Retrying Next after a failed page request can stall; code review and regression test | Explicit request generation refreshes even an unchanged offset. The new test failed before the fix and passed after it. |

Report information order changed from **all filters → all statistics → three charts → expanded technical tables → results/actions** to **routine filters → coverage → main differences → one chart with an explanation → recordings → secondary evidence/export**. The four-section lab navigation remains unchanged. Help is available beneath it rather than becoming another destination or permanently expanded panel.

Taste's application guidance informed the neutral overview figures, shared report surface, aligned tabular numbers, restrained chart palette and progressive disclosure. Screenshot critique also moved the chart explanation beside the desktop plot to remove an accidental empty right half; tablet/mobile stack it above the plot. The authoritative BandPilot shell, Raleway/system typography, themes and account accent tokens remain. UI/UX Pro Max's local empty-state, chart, interaction and accessibility searches informed an actionable empty state, one question per chart, chart data alternatives, labelled controls, focus indication and approximately 44px interaction targets. No additional dependency was installed.

### Follow-up file ownership

- `evaluation/reports.tsx` owns filter drafts, requests, successful evidence and pagination; `report-tables.tsx` owns metric/results/coverage presentation; `report-charts.tsx` owns the selected chart. `reports.module.css` provides the responsive local layout.
- `lab-guide.tsx` and `lab-guide.module.css` provide native disclosures and semantic tables; `lab-navigation.tsx` selects the contextual guide. `speaking-lab-guide-messages.ts`, `speaking-benchmark-evaluation-messages.ts`, `en.ts` and `vi.ts` own copy.
- `speaking-report-ux.test.tsx` adds twelve regression cases; `speaking-benchmark-evaluation.test.tsx` follows the clearer labels. `ux-preview/main.tsx`, `report-fixtures.ts` and `report-refinement.spec.ts` supply and verify explicitly synthetic evidence, including corrected report routing.

### Follow-up visual evidence

Artifacts are ignored local files under `storage/ux-audit/report-refinement/`:

- `before/`: four authentic baseline report captures (empty/populated, 1440/390px, VI/light), captured by temporarily restoring the inspected commit's production components and then restoring the edits.
- `after/`: 48 matrix/state captures: 1440/1024/768/390px, EN/VI, light/dark, empty/populated; opened guide tables; loading/error/configuration-choice/human-only states. Additional exploratory captures may also exist.
- `production/`: 32 chart/guide captures from a built, minified Vite preview at all four widths, EN/VI, light/green and dark/orange. This uses production feature code and CSS with synthetic routing/auth/data, not a live authenticated Next deployment.
- `taste-production/`: four viewport folds, full-page sheets and `report.json`. Inspector: **0 FAIL, 1 WARN** for detection of the installed `Segoe UI Variable` system face. No font replacement is warranted. Source lint: **0 FAIL, 1 WARN**, for intentional missing-value dashes.

Manually reviewed: baseline empty/populated reports, current empty desktop/mobile, populated report folds at all four widths, desktop chart composition, mobile dark chart, mobile VI/dark help and desktop EN/light help. Automated page-overflow assertions cover the full matrix; wide data tables scroll in their labelled keyboard-focusable regions, with a mobile hint. Native guide/filter disclosures preserve form values and keyboard operation. Reduced motion requires no new animation. Real screen-reader use, real mobile devices and non-Edge engines remain unverified.

### Follow-up verification

Final local results are recorded after the complete runs, rather than combining selectively rerun assertions. Logs are under `storage/ux-audit/report-refinement-*.log`.

| Check | Result |
| --- | --- |
| Focused P1–P4 and UX | 73 passed across 6 files |
| Full frontend Vitest | 2,044 passed across all 173 files in one complete final run (210.15s) |
| ESLint | Passed; zero errors or warnings |
| Production Next build and TypeScript | Passed |
| Synthetic Playwright | All 6 tests passed together (1.8m), including the existing 4 workflow tests and 2 report/help tests |
| Built fixture browser | 32 chart/help captures; all four widths, EN/VI, two themes and representative accents; no page overflow |
| Independent code review | Pagination retry finding reproduced and fixed; follow-up review found no remaining actionable issue |

No backend contracts, scoring, approval, blind-access rules, consent or billing semantics changed. No migration is needed for this UI update; local/Modal need the updated frontend to display it. Database synchronization was a separate operation and is not repeated by this change. No provider or GPU calls were made.
