# Note Completion Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a semantic, inline Note Completion authoring workflow with stable mixed text/gap segments and faithful candidate rendering.

**Architecture:** Add dedicated Note layout types, integrity/order helpers, editor, and renderer while retaining the legacy structured editor for other completion families. Normalize legacy NOTE nodes in FastAPI before Pydantic validation, and validate exact question/GAP identity in both draft and publish paths.

**Tech Stack:** Next.js/React/TypeScript, Vitest/Testing Library, FastAPI/Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-note-completion-authoring-design.md`

## Global Constraints

- Do not implement Speaking, authentication, AI scoring, or unrelated question-type redesigns.
- Do not add a rich-text dependency or persist the authoring token `{{gap}}`.
- Keep answer keys outside layout JSON and candidate payloads.
- Preserve stable UUIDs and global Reading/Listening numbering.
- Keep Form, Flow-chart, Summary, Sentence, Text, Table, and Diagram behavior unchanged.

## Review Focus

- Pasting `{{gap}}{{gap}}` or tokens at the beginning/end of a segment must preserve empty boundary text and create two distinct linked questions.
- A drag within the same block and a drag across blocks must move exactly one existing GAP object without losing surrounding text.
- Empty authoring blocks may exist locally but must not autosave or pass backend persisted validation.
- Legacy normalization must be deterministic across repeated loads and must not merge adjacent legacy nodes.
- Removing a block containing multiple gaps must remove exactly those questions and renumber the survivors from the supplied base number.

---

### Task 1: Backend Note model and legacy normalization

**Files:**
- Modify: `backend/tests/test_question_registry.py`
- Modify: `backend/app/domains/questions/registry.py`
- Modify: `backend/app/domains/questions/normalization.py`
- Modify: `backend/app/services/reading.py`
- Modify: `backend/app/services/tests.py`

**Interfaces:**
- Consumes: existing `StructuredCompletionGroupConfig`, `_stable_uuid`, `QuestionGroupWrite`, and TEXT evaluator.
- Produces: Pydantic `NoteSegment`/`NoteBlock` validation and `_normalize_note_layout(config, group_id)` returning canonical `layout.blocks`.

- [ ] **Step 1: Write failing backend tests** for optional title, TEXT+GAP+TEXT blocks, indent/style/UUID validation, duplicate/unknown/orphan references, and deterministic legacy node normalization without merging.
- [ ] **Step 2: Verify RED** with `.\.venv\Scripts\python.exe -m pytest tests/test_question_registry.py -q`; failures must show NOTE blocks are not yet modeled or normalized.
- [ ] **Step 3: Implement minimal backend models and normalization** with discriminated TEXT/GAP validation, block uniqueness, indent `0..3`, title `<=300`, non-empty persisted blocks, stable UUIDv5 legacy conversion, and NOTE-specific reference checks in draft and publish services.
- [ ] **Step 4: Verify GREEN** with `.\.venv\Scripts\python.exe -m pytest tests/test_question_registry.py tests/test_completion_identity.py tests/test_listening.py tests/test_reading_publish_regression.py tests/test_transfer.py -q`.

### Task 2: Frontend Note types, registry, integrity, and renderer

**Files:**
- Create: `frontend/src/features/questions/note-completion.ts`
- Create: `frontend/src/features/questions/note-completion-renderer.tsx`
- Create: `frontend/tests/note-completion.test.tsx`
- Modify: `frontend/src/features/questions/types.ts`
- Modify: `frontend/src/features/questions/registry.tsx`
- Modify: `frontend/src/features/test-builder/question-group-editor.tsx`

**Interfaces:**
- Consumes: backend canonical `layout.blocks`, `questionTarget`, `SelectableText`, and Builder base question number.
- Produces: `NoteCompletionLayout`, `noteCompletionIntegrityErrors(group)`, `normalizeNoteCompletionOrder(group, layout, base)`, and `NoteCompletionRenderer`.

- [ ] **Step 1: Write failing frontend tests** for the zero-question default, optional title, Preview/Candidate/Review rendering, heading/bullet/indent presentation, inline answer input, correct `onAnswer` UUID, canonical order, exact integrity validation, and hidden generic Add question action.
- [ ] **Step 2: Verify RED** with `npm test -- tests/note-completion.test.tsx`; failures must be caused by the missing dedicated Note implementation.
- [ ] **Step 3: Implement minimal types, pure helpers, registry definition, QuestionGroupEditor routing, and dedicated renderer**. Keep other structured completion definitions in their existing registry loop.
- [ ] **Step 4: Verify GREEN** with `npm test -- tests/note-completion.test.tsx tests/question-registry.test.tsx tests/table-completion.test.tsx`.

### Task 3: Inline Note authoring canvas

**Files:**
- Create: `frontend/src/features/questions/note-completion-editor.tsx`
- Modify: `frontend/tests/note-completion.test.tsx`
- Modify: `frontend/src/features/questions/registry.tsx`
- Modify: `frontend/src/app/globals.css`

**Interfaces:**
- Consumes: `NoteCompletionLayout`, `normalizeNoteCompletionOrder`, `noteCompletionIntegrityErrors`, `EditorProps`, and `ConfirmDialog`.
- Produces: `NoteCompletionEditor` with local TEXT-segment conversion, caret insertion, cross-block GAP movement, block controls, selected-gap inspector, and confirmed destructive actions.

- [ ] **Step 1: Add failing interaction tests** for one-token typing, two-token paste, surrounding-text edits preserving existing IDs/keys, explicit caret insertion, same/cross-block drag, style changes, Enter block creation, gap removal, and confirmed block removal with affected question numbers.
- [ ] **Step 2: Verify RED** with `npm test -- tests/note-completion.test.tsx`; each interaction must fail on a missing observable behavior rather than a test setup error.
- [ ] **Step 3: Implement the editor minimally** using one browser-owned `contentEditable` span per TEXT segment, segment-local token splitting, stable GAP buttons, semantic toolbar controls, and debounced Builder state updates through `onChange` only.
- [ ] **Step 4: Verify GREEN** with `npm test -- tests/note-completion.test.tsx tests/text-completion-canvas.test.tsx tests/table-completion.test.tsx`.

### Task 4: Full verification and regression repair

**Files:**
- Modify only files implicated by failing checks introduced by Tasks 1–3.

**Interfaces:**
- Consumes: all production and test interfaces above.
- Produces: a clean typecheck/lint/backend suite and a documented distinction for any unchanged baseline failure.

- [ ] **Step 1: Run frontend verification** with `npm test`, `npm run typecheck`, and `npm run lint`; compare the Table title timeout against the recorded clean-main baseline.
- [ ] **Step 2: Run backend verification** with `.\.venv\Scripts\python.exe -m pytest` and `.\.venv\Scripts\python.exe -m ruff check app tests`.
- [ ] **Step 3: For each introduced failure, write or retain the smallest reproducing test, verify RED, implement the minimal fix, and rerun the owning suite to GREEN.**
- [ ] **Step 4: Inspect `git diff --check`, changed-file scope, candidate DTO behavior, and answer-key isolation before final review.**
