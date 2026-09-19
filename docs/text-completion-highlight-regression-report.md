# Text Completion and highlight regression report

Implemented against the existing working tree at HEAD `2d4d7c0`. Previous sentence-block, preview, and Reading navigation changes were preserved. No reset, migration, or commit was performed.

## Findings and fixes

1. **Multi-click editor root cause.** The large white editor was a non-editable container with no whitespace focus behavior. Only the individual TEXT spans accepted input, including tiny empty spans.
2. **Caret lifecycle.** Stable keys did not prevent React from reconciling changed text children inside `contentEditable`. Every input also ran segment normalization, which removed empty segments and could merge away active segment identities. Ordinary nonempty spans were not necessarily remounted, but text reconciliation and structural normalization could disrupt selection.
3. **Editing architecture.** A stable `EditableText` span lets the browser own its text node and selection. A layout effect synchronizes only when the DOM text differs from the model. Input updates `segment.text` without structural normalization. Whitespace clicks focus the final TEXT segment at its end; a trailing editable segment is created only when structurally needed. Empty single-text sentences have a full-width hit area. Direct text clicks retain native caret placement. Structural operations clear stale caret references; add/split actions focus once after rendering, without timers.
4. **Q? cause.** A GAP refers to an absent Question UUID. Display numbering cannot repair it. Historical Reading update code created new ORM questions without the submitted `id`; the latest existing commit had already corrected this. That fix was preserved and verified.
5. **Exact lifecycle divergence.** In the old Reading path, and the still-broken Listening path, adding a new question during group update passed validation with the submitted UUID, then ORM creation assigned a different UUID while JSONB GAP references retained the submitted UUID. Version cloning also allocated new question IDs without remapping copied GAP references. Frontend normalization compounded broken drafts by dropping unmatched questions.
6. **Question identity.** Reading create/update retains its existing submitted-ID behavior. Listening update now explicitly supplies the submitted ID for new questions. Modern normalization preserves supplied IDs; visible numbering and ordering do not create identities.
7. **GAP identity.** Save/refetch preserves GAP IDs and question references. A new version necessarily receives distinct question primary keys; cloning now applies an explicit old-to-new UUID map to structured `question_id` references, leaving the source frozen version untouched. This remapping is restricted to version cloning.
8. **Save validation.** Builder detects missing/unresolved GAP links, orphan questions, duplicate references, duplicate/missing question identities, and duplicate/missing block or segment identities. It displays readable errors and blocks Save. Order normalization preserves invalid content rather than dropping it.
9. **Existing broken drafts.** No guessed automatic relinking occurs. Authors can explicitly link a selected GAP to an unlinked surviving question, add a missing GAP for a surviving question, or create a replacement answer for a GAP whose question has been lost. The replacement requires author configuration; previously deleted answers cannot be reconstructed. An explicitly empty modern layout is no longer treated as legacy prompt-based content.
10. **Invalid HTML cause.** `SelectableText` rendered its block dialog inside its inline span, which can itself be inside `QuestionHeader`'s paragraph.
11. **Portal fix.** Both creation and removal dialogs use `createPortal(..., document.body)`. The selectable subtree contains only inline-safe content. The paragraph header remains semantic. Related label/paragraph wrappers in matching and legacy text rendering were corrected locally.
12. **SSR safety and interaction.** Dialog state starts null on both server and initial client render; `document` is guarded and portal creation occurs only after interaction. Fixed viewport positioning remains. Portal refs preserve inside/outside click handling, Escape, peer dismissal, pending buttons, and API errors. Scroll/resize dismiss stale positions. Selection alone does not persist a highlight.

## Files changed in this task

Production:
- `frontend/src/features/questions/text-completion-canvas.tsx`
- `frontend/src/features/questions/text-completion-integrity.ts` (new)
- `frontend/src/features/test-builder/question-group-editor.tsx`
- `frontend/src/features/highlighting/selectable-text.tsx`
- `frontend/src/features/questions/renderers.tsx`
- `frontend/src/app/globals.css`
- `backend/app/domains/questions/normalization.py`
- `backend/app/services/listening.py`
- `backend/app/services/tests.py`

Regression coverage:
- `frontend/tests/text-completion-canvas.test.tsx`
- `frontend/tests/selectable-text.test.tsx`
- `backend/tests/test_completion_identity.py` (new)

The existing uncommitted changes in Reading runner/navigation, draft preview, and their tests remain in place. `editors.tsx`, question types/registry, DTOs, Reading persistence/canonicalization, Reading review, passage rendering, and group instructions were audited. No domain rule was moved into React.

## Tests and results

New coverage checks stable text-node/caret identity during middle editing, whitespace/empty focus, trailing text creation, invalid-data preservation and save blocking, explicit relinking, replacement answers, reopened UUID-based answer targets, both body portals under a real TFNG paragraph, SSR markup, console nesting warnings, creation/deletion, API failure, inside/outside clicks, Escape, peer close, and scroll dismissal. PostgreSQL tests exercise Reading and Listening create/update/refetch/reorder with IDs, accepted alternatives, case sensitivity, and numeric limits preserved. Clone tests verify remapped links and unchanged source config.

| Check | Final result |
| --- | --- |
| Frontend `npm test` | 116 passed across 19 files |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm run build` | Passed, all routes generated |
| Backend full `pytest -q` | 103 passed, including PostgreSQL integration tests |
| Ruff `check app tests` | Passed |
| `git diff --check` | Passed |

The additional lost-question recovery test was first observed failing because the action was absent, then passed after implementation. Tests use real timers; no hung test process required termination.

## Live browser verification

Used the user's running frontend and backend and created the fictional local test **Completion regression QA**.

- One click in sentence text, immediate typing, and `m|jor` + `a` produced `major`.
- One click in an empty sentence surface accepted typing immediately.
- Insert GAP immediately showed Q2 and opened the correct answer controls.
- Save, full page reload, and reopen preserved both question UUIDs and GAP links; no Q? appeared.
- Correct answer `major`, alternative `important`, case-sensitive grading, maximum 3 words and 2 numbers survived reload. Edit answer still resolved by UUID.
- Cloned the published QA version into draft v2. GAPs resolved to the new version's question UUIDs. Reordered sentences, saved, fully reloaded, and confirmed the changed order and original draft UUID/answer associations.
- Started a Reading attempt, selected TFNG header text, and opened the creation dialog. Live DOM inspection confirmed `parentElement.tagName === BODY` and no paragraph ancestor.
- Selection left highlight count at zero; clicking Highlight changed it to one. Reload retained the saved highlight.
- Opened removal options; DOM inspection again showed a body portal. Escape and outside click dismissed it. Remove highlight returned count to zero.
- No invalid nesting or hydration warnings were emitted by the tested highlight flow. A fresh reopened attempt tab recorded zero console errors. An earlier temporary source-encoding build error during development was corrected before final checks.

## Preserved behavior and limitations

One block per sentence, sentence add/reorder/remove confirmation, PASSAGE layout, Reading bottom navigation/flags, and absence of per-gap technical hints in Candidate/Preview/Review are preserved. PostgreSQL remains authoritative; active exam key separation, immutable published versions, server evaluation, and semantic highlight offsets are unchanged.

Already-lost answer content cannot be inferred or recovered automatically. Structurally corrupt duplicate block/segment identities are detected and blocked rather than silently rewritten. Browser verification used Chromium; cross-browser/IME-specific testing was not performed. The independent reviewer identified the lost-question recovery issue above; that finding was fixed and tested, but the reviewer could not finish its full verdict because its usage limit was reached.

The fictional QA fixture remains locally: published v1, draft v2, and a Reading attempt. Existing user test content was not edited. Changes are uncommitted for review.
