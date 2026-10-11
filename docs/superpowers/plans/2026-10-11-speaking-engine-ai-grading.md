# Speaking Engine, Recording, Transcript & AI Grading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Speaking as the fourth first-class IELTS skill, including Part 1/2/3 Builder support, crash-resilient per-prompt recording, read-only per-question transcription, hybrid audio+text AI grading, dynamic review UX, Full Mock/history/classroom integration, and benchmark tooling.

**Architecture:** Keep Speaking inside the existing `TestVersion -> TestModule -> Attempt` architecture. Store authored Speaking parts/prompts as structured versioned content, but store candidate recordings as private attempt media outside PostgreSQL with database manifests and authorization. Build speech processing behind replaceable ASR/alignment/acoustic provider interfaces; grading is holistic by criterion and uses the already-proven score-first pattern from Writing (`evidence -> score-only -> persist -> feedback`).

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL/Alembic, Pydantic, local asset storage, browser MediaRecorder/Web Audio APIs, FFmpeg preprocessing, optional faster-whisper/alignment/audio-analysis dependencies, existing structured LLM providers, Next.js 16, React 19, TypeScript, Zod, Vitest/RTL.

**Spec:** `docs/superpowers/specs/2026-10-11-speaking-engine-ai-grading-design.md`

**Planning base:** `origin/main` was `d606bfaedf871bbc45326223cf4f1d74f54399e9` when this plan was written. Every execution phase starts with `git fetch origin && git pull --ff-only origin main`; adapt migration revision IDs to the actual current Alembic head instead of assuming this SHA remains current.

## Global Constraints

- Speaking is a first-class module beside Reading, Listening, and Writing; do not implement it as a detached demo.
- The stale root `AGENTS.md` line `Do not implement Speaking.` is superseded by the approved spec and must be replaced at implementation start with a scoped Speaking invariant, while unrelated historical plan documents remain historical.
- Part 1 and Part 3 use ordered prompts. Part 2 uses a long-turn cue card plus optional authored follow-ups. Persistence uses stable IDs + `order_index`, not linked-list pointers.
- Part 1/3 application default response time is 60 seconds; Part 2 defaults to 60 seconds preparation and 120 seconds response. These are configurable product defaults, not claims of a fixed official IELTS per-question limit.
- Practice allows Listen/Retry only for the current uncommitted response. Exam/Full Mock never allows replay, retry, previous-question navigation, or reopening a committed response.
- Server time/state is authoritative. Browser timers and animations are presentation only.
- Reload/crash recovery restores the same prompt and last server-confirmed remaining-time snapshot, grants exactly one 7-second reconnect/preparation grace for that interruption, then resumes the original remaining time. Repeated refresh must not stack grace or rewind time.
- Raw candidate audio is private attempt data. Reuse the physical storage abstraction, but do **not** shoehorn candidate recordings into the published-content `Asset` authorization model tied to `test_version_id`.
- Prefer `audio/webm;codecs=opus` where supported, with capability-driven fallback. Frontend must not encode WAV. Speech preprocessing may derive 16 kHz mono PCM/WAV.
- Upload small MediaRecorder chunks (target 2–5 seconds). Because a hard crash creates a new MediaRecorder container/session, model one logical take as one or more ordered recording segments, each containing idempotent ordered chunks.
- `Generate Transcript` and `Grade with AI` are separate user actions. Grading may reuse or internally generate a valid transcript, but it must not create duplicate ASR work for the same fingerprint.
- Transcript is read-only, per-question only. A clean transcript may normalize punctuation/casing/filler presentation but must never grammar-correct or silently improve what the candidate said.
- Technical/audio failures are nonscorable states, not low IELTS bands.
- Fluency metrics are evidence only. Never create hard band rules such as `pause_count > N => Band X`.
- Pronunciation requires audio-derived evidence. A transcript-only LLM must never invent a Pronunciation score.
- No per-question or per-Part score averaging. Criterion scores are holistic across the whole Speaking attempt; question-level analysis exists only for evidence/feedback.
- Preserve the Writing AI score-first implementation at `d606bfae...`; do not regress or rewrite Writing to build Speaking.
- Speaking criterion AI scores remain advisory half-band values (`0..9` in `0.5` increments) as approved. Store `raw_mean`; use the project `round_to_half` presentation policy for the advisory Speaking overall unless a later calibration/version explicitly changes it. Never claim examiner-certified rounding/accuracy.
- Full Mock eventually becomes Listening -> Reading -> Writing -> Speaking. The four-skill project overall is available only when all four module bands exist.
- Teacher/classroom ownership, moderation, assignment provenance, immutable published versions, and read-only teacher result access keep their existing governance semantics.
- UI is state-driven and polished: realtime mic level, timer progress, light 150–250ms transitions, save/recovery/transcript/AI progress, theme/accent support, and `prefers-reduced-motion`. No parallax, particles, or motion that delays state/network transitions.
- Heavy speech dependencies must not make ordinary backend unit tests load models. Put them behind provider factories/optional dependency groups and test with fakes/stubs/tiny fixtures.
- Keep verification focused and cheap per user preference: no browser automation, Playwright/E2E, dev server, real microphone, real ASR/acoustic model download, live LLM/GPU/Modal, or deployment runs. Use focused pytest/Vitest, targeted Ruff/ESLint, TypeScript typecheck, and `git diff --check`.
- TDD for behavior changes: write focused failing test, run and confirm RED, implement minimally, rerun GREEN, then commit. Do not batch all phases into one commit.

## File Structure

New backend responsibilities should stay focused rather than expanding `entities.py` and Writing-specific modules indefinitely:

- `backend/app/models/speaking.py` — authored Speaking content plus response/take/progress/media metadata.
- `backend/app/models/speaking_transcript.py` — transcript runs/events/transcripts.
- `backend/app/models/speaking_ai.py` — AI grading runs/events/results metadata.
- `backend/app/schemas/speaking.py` — Builder, runner, response, recovery, review DTOs.
- `backend/app/schemas/speaking_ai.py` — transcript/feature/grading schemas.
- `backend/app/repositories/speaking.py`, `speaking_transcript.py`, `speaking_ai.py` — persistence only.
- `backend/app/services/speaking_builder.py` — authoring/validation/order semantics.
- `backend/app/services/speaking_attempts.py` — prompt state machine, practice/exam rules, finalization.
- `backend/app/services/speaking_media.py` — private chunk/segment storage and playback authorization.
- `backend/app/services/speaking_transcript.py` — transcript orchestration/cache.
- `backend/app/services/speaking_audio.py` — FFmpeg normalization + quality/preprocessing helpers.
- `backend/app/services/speaking_features.py` — deterministic fluency/prosody evidence.
- `backend/app/services/speaking_ai.py`, `speaking_ai_worker.py` — score-first grading orchestration + durable worker lifecycle.
- `backend/app/providers/speaking_asr/` — ASR/alignment provider protocol + optional implementation.
- `backend/app/providers/speaking_pronunciation/` — audio-derived pronunciation evidence protocol + baseline alignment/prosody implementation.
- `backend/app/domains/scoring/speaking_prompts.py` — descriptor/evidence/score/feedback prompt contracts.
- `frontend/src/features/speaking/` — preflight, recorder hook/controller, runner, review, transcript and AI panels.
- `frontend/src/lib/api/speaking.ts`, `speaking-ai.ts` — typed/Zod network contracts.

Do not create all files up front. Create each when its owning task reaches GREEN.

## Review Focus

1. Duplicate/out-of-order chunk retries after a flaky network must produce exactly one ordered logical recording; a resumed MediaRecorder session must start a new segment rather than corrupting the previous WebM container.
2. Refresh/reconnect loops during an active answer must never gain more speech time: the backend restores one bounded remaining snapshot and one 7-second grace per valid interruption, while completed prompts stay closed.
3. Private candidate audio/transcripts must be inaccessible by ID to unrelated users/teachers; assignment teachers may read only assignment-originated work under the existing provenance predicate.
4. ASR/audio failure must not silently become a valid LR/GRA/Pronunciation score. Missing/stale transcript or acoustic evidence must be explicit and criterion/run failure behavior must be deterministic.
5. Navigation/reload while transcription or AI grading is running must disconnect only observation; backend work continues and SSE/JSON reconciliation resumes without duplicate processing or lost persisted scores.

---

# P1 — Domain + DB + Builder

### Task 1: Enable Speaking scope and authored persistence

**Files:**
- Modify: `AGENTS.md`
- Modify: `backend/app/models/enums.py`
- Create: `backend/app/models/speaking.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<next_revision>_speaking_content.py`
- Modify: `backend/app/schemas/content.py`
- Create: `backend/app/schemas/speaking.py`
- Test: `backend/tests/test_speaking_builder.py`

**Interfaces:**
- Produces `ModuleType.SPEAKING`, `SpeakingPromptType = SHORT_ANSWER | LONG_TURN | FOLLOW_UP`, `SpeakingPart`, `SpeakingPrompt`, and Builder DTOs nested under the existing `TestModule`/Builder response.
- `SpeakingPart` belongs to one SPEAKING `TestModule`; unique `(module_id, part_number)` for part 1/2/3. `SpeakingPrompt` has stable UUID, `order_index`, `prompt_text`, `preparation_seconds`, `response_seconds`, bounded `config_json` for cue points/presentation data.

- [x] **Step 1: Write failing model/Builder contract tests**

Add tests proving `ModuleType.SPEAKING` is accepted; three parts can be represented; duplicate part numbers are rejected; stable prompt IDs survive reorder; draft content can be incomplete; and Builder serialization exposes `speaking_parts` without changing Reading/Listening/Writing DTOs.

- [x] **Step 2: Run and verify RED**

Run: `cd backend && uv run pytest tests/test_speaking_builder.py -q`

Expected: FAIL because Speaking enum/models/schemas do not exist.

- [x] **Step 3: Implement enum, focused model file, schema, migration, and repository guidance**

Before migration creation run `uv run alembic heads`; generate from the actual single current head. Replace only the stale root `AGENTS.md` Speaking prohibition with an invariant that Speaking work follows the approved spec/plan. Do not rewrite old historical plan docs that said Speaking was out of scope for those older tasks.

- [x] **Step 4: Run GREEN + model lint**

Run: `cd backend && uv run pytest tests/test_speaking_builder.py -q && uv run ruff check app/models/enums.py app/models/speaking.py app/schemas/speaking.py tests/test_speaking_builder.py`

- [x] **Step 5: Commit**

```bash
git add AGENTS.md backend/app/models backend/app/schemas backend/alembic/versions backend/tests/test_speaking_builder.py
git commit -m "Add Speaking content domain model"
```

### Task 2: Speaking Builder CRUD, validation, version cloning, and transfer

**Files:**
- Create: `backend/app/repositories/speaking.py`
- Create: `backend/app/services/speaking_builder.py`
- Create: `backend/app/api/v1/speaking.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/api/v1/reading.py` only where the shared Builder response is assembled
- Modify: `backend/app/api/v1/tests.py`
- Modify: version-clone service(s) that clone Reading/Listening/Writing module content
- Modify: `backend/app/api/v1/transfer.py` and its service/schema files as needed
- Test: `backend/tests/test_speaking_builder.py`
- Test: existing clone/transfer tests

**Interfaces:**
- Produces Builder mutations for part/prompt create/update/delete/reorder plus `validate_speaking_module(module_id)`.
- Validation on publish/moderation requires parts 1/2/3, exactly one Part 2 `LONG_TURN`, non-empty prompt text, positive timers, unique normalized order, and legal prompt types by part. Draft autosave remains permissive for incomplete intermediate state.

- [x] **Step 1: Add failing API/service tests** for append order, reorder normalization, Part 2 cue points/default 60/120 timers, configurable Part 1/3 60s default, malformed publish rejection, owner/published immutability policy, clone preserving IDs only where existing clone semantics require new IDs, and ZIP export/import round-trip.
- [x] **Step 2: Run RED:** `cd backend && uv run pytest tests/test_speaking_builder.py tests/test_asset_cloning.py -q` plus the existing transfer test file.
- [x] **Step 3: Implement minimal repository/service/routes and wire publish validation.** Reuse `require_content_author`/current access policy; never add a Speaking-specific teacher bypass.
- [x] **Step 4: Run GREEN + Ruff** on touched files.
- [x] **Step 5: Commit:** `git commit -am "Add Speaking Builder API and validation"` (stage new files explicitly first).

### Task 3: Dynamic Speaking Builder UI

**Files:**
- Modify: `frontend/src/lib/api/builder.ts`
- Create: `frontend/src/features/test-builder/speaking-builder.tsx`
- Create: `frontend/src/features/test-builder/speaking-prompt-editor.tsx`
- Modify: `frontend/src/features/test-builder/builder-editor-page.tsx`
- Modify: `frontend/src/features/test-builder/builder-workspace-navigation.tsx`
- Modify: `frontend/src/features/test-builder/content-summary.tsx`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/lib/i18n/en.ts`
- Modify: `frontend/src/lib/i18n/vi.ts`
- Create: `frontend/tests/speaking-builder.test.tsx`

**Interfaces:**
- Builder workspace union becomes `overview | reading | listening | writing | speaking`; module type unions include `SPEAKING`.
- `SpeakingBuilder` presents Part 1/2/3, append-at-end questions, reorder/delete, Part 2 cue points + timers + optional follow-ups, and uses existing autosave lifecycle.

- [x] **Step 1: Write failing RTL tests** for workspace navigation, creation, append/reorder, Part 2 defaults, autosave payload, frozen published/under-moderation behavior, focus moving to a newly added card, and reduced-motion-compatible class/state behavior.
- [x] **Step 2: Run RED:** `cd frontend && npx vitest run tests/speaking-builder.test.tsx`.
- [x] **Step 3: Implement UI/API schemas.** Use existing semantic theme tokens; add lightweight 150–250ms enter/reorder transitions and `prefers-reduced-motion`, no new animation library.
- [x] **Step 4: Run GREEN + typecheck/targeted ESLint:** `npx vitest run tests/speaking-builder.test.tsx && npm run typecheck` then ESLint touched files.
- [x] **Step 5: Commit:** `git commit -m "Add Speaking Builder workspace"`.

**P1 gate:** stop and review. Do not start runner work until P1 tests are green and Builder/publish/clone/transfer contracts are coherent.

---

# P2 — Runner + Recording State + Timers

### Task 4: Speaking attempt state machine and current-prompt API

**Files:**
- Extend: `backend/app/models/speaking.py`
- Create: `backend/alembic/versions/<next_revision>_speaking_attempt_state.py`
- Create: `backend/app/services/speaking_attempts.py`
- Extend: `backend/app/repositories/speaking.py`
- Extend: `backend/app/schemas/speaking.py`
- Extend: `backend/app/api/v1/speaking.py`
- Modify: `backend/app/services/attempts.py`
- Modify: `backend/app/services/attempt_scope.py`
- Test: `backend/tests/test_speaking_attempts.py`

**Interfaces:**
- Produces `SpeakingResponse`, `SpeakingResponseTake`, and `SpeakingPromptProgress`.
- Service entry points conceptually: `get_state(attempt_id)`, `begin_prompt(...)`, `heartbeat(...)`, `finish_current_response(..., completion_reason)`, `retry_current_response(...)`.
- Progress stores active prompt/phase, authoritative phase timestamps/deadline, `last_confirmed_remaining_ms`, interruption generation/count, grace-used state, and last resume time.

- [x] **Step 1: Write failing state tests** for ordered Part 1→Part 2 prep→long turn/follow-up→Part 3 flow; current prompt only; Done/Next; timeout; locked committed response; practice retry allowed only current prompt; exam/full-mock retry/replay forbidden; focused Speaking prompt target; and client remaining-time values never increasing server state.
- [x] **Step 2: Run RED:** `cd backend && uv run pytest tests/test_speaking_attempts.py tests/test_focused_attempts.py -q`.
- [x] **Step 3: Implement state machine using `TimerService.now()` and DB state.** Do not add `setInterval` semantics server-side. Keep the overall `Attempt` lifecycle generic while Speaking prompt progress is its child state.
- [x] **Step 4: Run GREEN + Ruff.**
- [x] **Step 5: Commit:** `git commit -m "Add Speaking attempt state machine"`.

### Task 5: Browser preflight, recorder abstraction, and runner UI state

**Files:**
- Create: `frontend/src/lib/api/speaking.ts`
- Create: `frontend/src/features/speaking/speaking-recorder.ts`
- Create: `frontend/src/features/speaking/use-speaking-recorder.ts`
- Create: `frontend/src/features/speaking/speaking-preflight.tsx`
- Create: `frontend/src/features/speaking/speaking-runner.tsx`
- Modify: `frontend/src/app/attempt/[attemptId]/page.tsx`
- Modify: shared attempt destination/routing helpers as needed
- Modify: `frontend/src/app/globals.css`, i18n files
- Create: `frontend/tests/speaking-preflight.test.tsx`
- Create: `frontend/tests/speaking-runner.test.tsx`
- Modify: `frontend/tests/attempt-page.test.tsx`

**Interfaces:**
- `SpeakingRecorder` wraps native `MediaRecorder`, `navigator.mediaDevices`, and Web Audio level sampling; production code receives state callbacks/chunk callbacks rather than manipulating UI directly.
- Runner state mirrors backend phases: question enter, preparing, recording, finalizing/uploading, completed, restoring.

- [x] **Step 1: Add failing tests** with fake `MediaRecorder`, `mediaDevices`, `AudioContext`, and fake timers: permission denied; supported MIME selection preferring WebM/Opus; level meter; current question only in exam; Part 2 preparation + start countdown; Done/Next and timeout; no exam retry/replay; practice Retry confirmation; no advance before persistence callback resolves; reduced-motion behavior.
- [x] **Step 2: Run RED:** `cd frontend && npx vitest run tests/speaking-preflight.test.tsx tests/speaking-runner.test.tsx tests/attempt-page.test.tsx`.
- [x] **Step 3: Implement native-browser recorder abstraction and state-driven UI.** Do not add third-party waveform/recording dependency; use lightweight level bars from analyser data.
- [x] **Step 4: Run GREEN + `npm run typecheck` + targeted ESLint.**
- [x] **Step 5: Commit:** `git commit -m "Add Speaking preflight and runner state UI"`.

**P2 gate:** runner/state tests must pass with mocked recorder/network. It is not yet crash-durable until P3; do not market/enable production Speaking flow until P3 completes.

---

# P3 — Private Chunk Upload + Recovery + Review

### Task 6: Private segmented audio persistence and authorization

**Files:**
- Extend: `backend/app/models/speaking.py`
- Create: `backend/alembic/versions/<next_revision>_speaking_audio_chunks.py`
- Create: `backend/app/services/speaking_media.py`
- Extend: `backend/app/repositories/speaking.py`
- Extend: `backend/app/api/v1/speaking.py`
- Modify: `backend/app/storage/local.py`
- Modify: `backend/app/core/config.py`, `.env.example`, `backend/.env.example` only for new bounded Speaking settings
- Test: `backend/tests/test_speaking_media.py`

**Interfaces:**
- Add `SpeakingAudioSegment(response_take_id, segment_index, mime_type, ...)` and `SpeakingAudioChunk(segment_id, sequence, storage_key, sha256, byte_size, ...)` with unique idempotency constraints.
- One practice take may have multiple segments after crash/recovery. A new MediaRecorder process/session always starts a new segment; chunks are ordered only within the segment. Final logical audio fingerprint hashes ordered segment/chunk hashes + committed take identity.
- Private playback/read endpoint authorizes attempt owner or an existing assignment-authorized teacher result view; unrelated IDs never grant access.

- [x] **Step 1: Write failing tests** for WebM MIME acceptance, size limits, duplicate `(segment,sequence)` retry idempotency, conflicting duplicate hash rejection, out-of-order arrival yielding ordered manifest, new segment after recovery, superseded practice take exclusion, final fingerprint determinism, and owner/teacher/unrelated-user playback authorization.
- [x] **Step 2: Run RED:** `cd backend && uv run pytest tests/test_speaking_media.py tests/test_asset_access.py tests/test_classroom_assignments.py -q`.
- [x] **Step 3: Implement private storage manifests.** Reuse `LocalAssetStorage` filesystem safety but store under a private Speaking namespace; do not create public content `Asset` rows for candidate audio. Extend MIME handling for browser WebM/Opus.
- [x] **Step 4: Run GREEN + Ruff.**
- [x] **Step 5: Commit:** `git commit -m "Add private Speaking chunk storage"`.

### Task 7: Interruption/recovery protocol with one 7-second grace

**Files:**
- Extend: `backend/app/services/speaking_attempts.py`
- Extend: `backend/app/api/v1/speaking.py`
- Extend: `backend/app/schemas/speaking.py`
- Extend: `backend/app/core/config.py`
- Test: `backend/tests/test_speaking_recovery.py`

**Interfaces:**
- Produces explicit `interrupt`/`resume` semantics or equivalent idempotent state transitions keyed by current prompt/take + interruption generation.
- Resume response returns server-authorized `remaining_ms`, `recovery_grace_seconds=7`, current prompt/take/next segment identity, and whether recovery is allowed.
- Add a bounded reconnect eligibility window setting (conservative default chosen in implementation, documented and tested); this bounds abuse/outage recovery but never changes the visible 7-second grace contract.

- [x] **Step 1: Write failing tests** for 31s snapshot → 7s grace → 31s resumed; repeated refresh during same generation not stacking grace; stale resume token/generation rejected; completed prompt not reopened; late/unrecoverable interruption fails closed; heartbeat/chunk confirmation can decrease but never increase remaining; concurrent resume idempotency.
- [x] **Step 2: Run RED:** `cd backend && uv run pytest tests/test_speaking_recovery.py -q`.
- [x] **Step 3: Implement transaction-safe recovery.** Persist audit-safe state only; do not log transcript/audio bodies.
- [x] **Step 4: Run GREEN + Ruff.**
- [x] **Step 5: Commit:** `git commit -m "Add Speaking crash recovery protocol"`.

### Task 8: Connect chunk transport/recovery to runner and build review playback

**Files:**
- Extend: `frontend/src/lib/api/speaking.ts`
- Extend: `frontend/src/features/speaking/speaking-recorder.ts`
- Extend: `frontend/src/features/speaking/speaking-runner.tsx`
- Create: `frontend/src/features/speaking/speaking-review.tsx`
- Modify: attempt/review routing destination files
- Modify: `frontend/src/app/globals.css`, i18n files
- Extend: `frontend/tests/speaking-runner.test.tsx`
- Create: `frontend/tests/speaking-review.test.tsx`

**Interfaces:**
- Recorder emits chunks every configured ~2–5 seconds, retries upload idempotently, flushes before finalization, and opens a new segment after recovery.
- Review renders Part 1/2/3 response cards with question/cue card, duration, authorized audio player, and later transcript/AI placeholders.

- [ ] **Step 1: Write failing frontend tests** for chunk retry, upload ACK before next prompt, hard-reload resume snapshot/grace countdown, new segment on resumed recorder, failed final upload staying on same prompt, practice Listen/Retry vs exam hidden controls, and per-question review playback.
- [ ] **Step 2: Run RED** with only Vitest/mocks.
- [ ] **Step 3: Implement transport/recovery/review UI.** Recovery page shows restored state + 7→1 countdown and pauses original remaining timer during grace.
- [ ] **Step 4: Run GREEN + typecheck/targeted ESLint.**
- [ ] **Step 5: Commit:** `git commit -m "Connect Speaking recording recovery and review"`.

**P3 gate:** Speaking exam/practice recording must now be durably usable without transcript/AI. Verify no private media exposure and no time farming before P4.

---

# P4 — Transcript Pipeline

### Task 9: ASR provider contract, transcript persistence, durable transcript runs

**Files:**
- Create: `backend/app/providers/speaking_asr/base.py`
- Create: `backend/app/providers/speaking_asr/faster_whisper.py`
- Create: `backend/app/providers/speaking_asr/__init__.py`
- Create: `backend/app/models/speaking_transcript.py`
- Create: `backend/alembic/versions/<next_revision>_speaking_transcripts.py`
- Create: `backend/app/repositories/speaking_transcript.py`
- Create: `backend/app/services/speaking_transcript.py`
- Extend: `backend/app/schemas/speaking_ai.py`
- Extend: `backend/app/api/v1/speaking.py`
- Modify: `backend/app/main.py` for worker shutdown if a background task registry is used
- Modify: `backend/pyproject.toml` to add optional `speech` extras instead of loading heavy dependencies in base tests
- Test: `backend/tests/test_speaking_transcript.py`

**Interfaces:**
- `SpeechASRProvider.transcribe(audio: NormalizedAudio) -> ASRResult` returns verbatim text, word timestamps/confidence metadata, provider/model/version.
- Persist `SpeakingTranscriptRun` + monotonic events and two transcript records per successful response (`VERBATIM`, `CLEAN`) keyed by audio fingerprint + ASR/alignment version/config.
- Matching active/completed runs are reused; different fingerprint/version invalidates cache.

- [ ] **Step 1: Write failing tests** using a fake provider: per-response isolation, one failed response does not delete successful transcripts, matching active run reuse, cache hit, retry-audio invalidation, word timing validation, and clean normalization preserving grammar errors (e.g. `He go to school` must not become `He goes...`).
- [ ] **Step 2: Run RED:** `cd backend && uv run pytest tests/test_speaking_transcript.py -q`.
- [ ] **Step 3: Implement provider abstraction + durable job with fake-friendly factory.** The optional faster-whisper adapter is import-lazy; ordinary app/test import succeeds without the speech extra installed. No diarization in v1.
- [ ] **Step 4: Run GREEN + Ruff.** Do not download/run a real Whisper model.
- [ ] **Step 5: Commit:** `git commit -m "Add durable Speaking transcription pipeline"`.

### Task 10: Transcript action, SSE/reconciliation, and per-question read-only UI

**Files:**
- Extend: `frontend/src/lib/api/speaking.ts`
- Create/extend: `frontend/src/lib/api/speaking-ai.ts`
- Create: `frontend/src/features/speaking/speaking-transcript-panel.tsx`
- Extend: `frontend/src/features/speaking/speaking-review.tsx`
- Create: `frontend/tests/speaking-transcript.test.tsx`
- Create: `frontend/tests/speaking-api.test.ts`

**Interfaces:**
- Review exposes `Generate Transcript` separately from `Grade with AI`.
- Event watcher follows Writing semantics: sequence monotonicity, duplicate suppression, JSON snapshot reconciliation, view cleanup disconnects observation only.

- [ ] **Step 1: Write failing tests** for button state, per-question Ready/Processing/Failed, read-only transcript, no merged Full Transcript, SSE duplicate/reconnect handling, and navigation cleanup not calling cancel.
- [ ] **Step 2: Run RED.**
- [ ] **Step 3: Implement typed/Zod API + live panel.**
- [ ] **Step 4: Run GREEN + typecheck/ESLint.**
- [ ] **Step 5: Commit:** `git commit -m "Add Speaking transcript review UI"`.

**P4 gate:** transcription can be used without grading; transcript cannot be edited and failures remain per response.

---

# P5 — Audio Quality + Fluency + Pronunciation Evidence

### Task 11: Audio normalization and quality gate

**Files:**
- Create: `backend/app/services/speaking_audio.py`
- Create: `backend/app/services/speaking_quality.py`
- Modify: `backend/app/core/config.py`, env examples for FFmpeg path/timeouts/quality thresholds as needed
- Test: `backend/tests/test_speaking_audio.py`

**Interfaces:**
- `normalize_committed_take(...) -> NormalizedAudio` assembles ordered segments/chunks through FFmpeg into derived 16 kHz mono PCM/WAV without mutating raw source.
- `assess_audio_quality(...) -> AudioQualityResult` emits at least `AUDIO_OK`, `NO_SPEECH`, `TOO_SHORT`, `AUDIO_CORRUPT`, `VERY_LOW_SIGNAL`, `SEVERE_CLIPPING`, `BACKGROUND_DOMINANT`, `ASR_UNUSABLE`.

- [ ] **Step 1: Write failing tests** around subprocess command construction/path safety and tiny synthetic/fixture metadata; nonscorable conditions must be explicit and never return a band.
- [ ] **Step 2: Run RED.**
- [ ] **Step 3: Implement bounded FFmpeg wrapper/quality contract.** Keep raw assets immutable; derived artifacts may be cached by fingerprint/version.
- [ ] **Step 4: Run GREEN + Ruff.** No external FFmpeg/model integration run is required; mock subprocess where appropriate.
- [ ] **Step 5: Commit:** `git commit -m "Add Speaking audio quality preprocessing"`.

### Task 12: Deterministic fluency and audio-derived pronunciation evidence

**Files:**
- Create: `backend/app/services/speaking_features.py`
- Create: `backend/app/providers/speaking_pronunciation/base.py`
- Create: `backend/app/providers/speaking_pronunciation/alignment_prosody.py`
- Create: `backend/app/providers/speaking_pronunciation/__init__.py`
- Extend: `backend/app/schemas/speaking_ai.py`
- Test: `backend/tests/test_speaking_features.py`

**Interfaces:**
- `extract_fluency_features(audio, verbatim_transcript, words) -> FluencyEvidence` computes duration, speech/silence ratio, WPM, articulation rate, pauses, long pauses, filler/repetition/false-start/self-correction signals, average turn length, Part 2 sustained duration.
- `PronunciationEvidenceProvider.analyse(audio, transcript, alignment) -> PronunciationEvidence` provides audio-derived alignment/segmental-clarity proxies, low-confidence/unaligned spans, stress/rhythm/intonation/pitch-energy/prosody summaries, and intelligibility/listener-effort proxies. These are evidence, never direct IELTS band mappings.

- [ ] **Step 1: Write failing deterministic feature tests** for known timestamp fixtures, divide-by-zero/empty speech, long-pause distribution, disfluency preservation, Part 2 duration, and provider-unavailable/low-evidence states.
- [ ] **Step 2: Run RED.**
- [ ] **Step 3: Implement pure feature code + replaceable pronunciation provider.** Baseline may use ASR/forced-alignment confidence plus acoustic/prosodic features; do not call SpeechOcean/GOPT scores “IELTS bands” and do not use transcript text alone for PR.
- [ ] **Step 4: Run GREEN + Ruff.** No real acoustic model/GPU invocation.
- [ ] **Step 5: Commit:** `git commit -m "Add Speaking fluency and pronunciation evidence"`.

**P5 gate:** preprocessing outputs explainable evidence only. Review specifically that no threshold accidentally became a band rule.

---

# P6 — Hybrid IELTS Speaking AI Scorer

### Task 13: Speaking grading schemas, descriptors, score-first criterion service

**Files:**
- Create: `backend/app/domains/scoring/speaking_prompts.py`
- Create: `backend/app/services/speaking_ai.py`
- Create: `backend/app/providers/speaking_llm/base.py`
- Create: `backend/app/providers/speaking_llm/configured.py`
- Create/extend: `backend/app/schemas/speaking_ai.py`
- Modify: `backend/app/domains/scoring/__init__.py`
- Test: `backend/tests/test_speaking_ai.py`

**Interfaces:**
- Traits: `fc`, `lr`, `gra`, `pr`.
- Each criterion pipeline: evidence bundle -> `CriterionBandScore {score}` (tiny JSON; 0.5 increments) -> durable valid score -> `CriterionFeedback {feedback,strengths,improvements}`.
- FC consumes timing/verbatim/semantic evidence; LR/GRA consume transcript evidence; PR refuses to score without acceptable audio-derived pronunciation evidence.
- `speaking_overall(criteria) -> (raw_mean, overall_band)` uses equal weights and project half-band presentation policy, while result remains labelled advisory.

- [ ] **Step 1: Write failing tests** for descriptor evidence separation, whole-attempt input, no per-question averaging, 0.5 validation, tiny score token cap, one bounded score repair, feedback cannot override score, feedback failure retaining score with safe fallback, score failure never fabricating a default, PR missing acoustic evidence => explicit unavailable/failure, and equal-weight overall arithmetic.
- [ ] **Step 2: Run RED:** `cd backend && uv run pytest tests/test_speaking_ai.py -q`.
- [ ] **Step 3: Implement scorer using a Speaking LLM adapter that delegates to the configured structured LLM provider contract without renaming/refactoring Writing provider internals.** Keep Speaking prompt/version namespace independent so cache/version bumps never alter Writing v9 history.
- [ ] **Step 4: Run GREEN + Ruff.** Use fake completions only.
- [ ] **Step 5: Commit:** `git commit -m "Add score-first Speaking criterion scorer"`.

### Task 14: Durable AI grading runs, cache, cancellation, and SSE

**Files:**
- Create: `backend/app/models/speaking_ai.py`
- Create: `backend/alembic/versions/<next_revision>_speaking_ai_runs.py`
- Create: `backend/app/repositories/speaking_ai.py`
- Create: `backend/app/services/speaking_ai_worker.py`
- Create: `backend/app/api/v1/speaking_ai.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/main.py`
- Extend: `backend/app/core/config.py`, env examples
- Extend: `backend/tests/test_speaking_ai.py`

**Interfaces:**
- Run states/events expose `QUEUED/PENDING`, `QUALITY_CHECK`, `TRANSCRIBING`, `ANALYSING_AUDIO`, `BUILDING_EVIDENCE`, `SCORING`, `GENERATING_FEEDBACK`, terminal COMPLETED/FAILED/CANCELLED semantics.
- Cache fingerprint includes committed audio fingerprint/take + ASR/alignment versions + feature extractor/pronunciation provider versions + rubric/prompt/model versions.
- `Grade with AI` reuses matching transcript run/result or waits on matching active ASR work; it does not launch duplicate transcription.
- SSE uses monotonic `(run_id, sequence)` events, `Last-Event-ID`/`after` reconciliation, no proxy caching, and browser disconnect never cancels worker. Explicit Stop is the only user cancellation.

- [ ] **Step 1: Add failing persistence/API tests** for cache hit, stale-audio miss, duplicate active run, transcript reuse, worker surviving request/SSE disconnect, explicit cancel, restart/stale-run handling, score checkpoint durability before feedback, and event sequence uniqueness.
- [ ] **Step 2: Run RED.**
- [ ] **Step 3: Implement run repository/worker/router modeled on Writing’s durable semantics but in Speaking-specific tables/modules.** Avoid broad Writing refactors.
- [ ] **Step 4: Run GREEN + Ruff.** No live provider/model.
- [ ] **Step 5: Commit:** `git commit -m "Add durable Speaking AI grading runs"`.

### Task 15: Dynamic AI assessment UI

**Files:**
- Extend: `frontend/src/lib/api/speaking-ai.ts`
- Create: `frontend/src/features/speaking/speaking-ai-progress.tsx`
- Create: `frontend/src/features/speaking/speaking-ai-assessment.tsx`
- Extend: `frontend/src/features/speaking/speaking-review.tsx`
- Modify: `frontend/src/app/globals.css`, i18n files
- Create: `frontend/tests/speaking-ai-api.test.ts`
- Create: `frontend/tests/speaking-ai-assessment.test.tsx`

**Interfaces:**
- Review keeps two actions: Generate Transcript and Grade with AI. Grade button works without prior transcript button.
- Assessment displays advisory overall + FC/LR/GRA/PR, evidence/feedback, fluency/Part 2/pronunciation analysis, and live stage progress. Valid criterion scores already persisted remain visible even if later feedback fails.

- [ ] **Step 1: Write failing tests** for staged progress, SSE reconnect/duplicate suppression, Stop calling cancel, component unmount not cancelling, feedback fallback display, quality-unassessable messaging, advisory label, theme/reduced-motion behavior.
- [ ] **Step 2: Run RED.**
- [ ] **Step 3: Implement UI following Writing watcher semantics without coupling Speaking contracts to Writing trait names.**
- [ ] **Step 4: Run GREEN + `npm run typecheck` + targeted ESLint.**
- [ ] **Step 5: Commit:** `git commit -m "Add Speaking AI assessment UI"`.

**P6 gate:** no claim of examiner accuracy. Confirm PR cannot succeed from text-only evidence and score checkpoint survives feedback failure.

---

# P7 — Full Mock + History + Classroom

### Task 16: Four-skill Full Mock and overall scoring

**Files:**
- Modify: `backend/app/services/test_sessions.py`
- Modify: `backend/app/domains/module_durations.py`
- Modify: `backend/app/domains/scoring/ielts_band.py`
- Modify: `backend/app/domains/scoring/__init__.py`
- Modify: `backend/app/schemas/test_sessions.py`
- Test: existing TestSession/full-mock tests + `backend/tests/test_full_mock_history_delete.py`
- Modify: `frontend/src/lib/api/exam.ts`
- Modify: Full Mock transition components/tests

**Interfaces:**
- `MODULE_ORDER = (LISTENING, READING, WRITING, SPEAKING)`.
- `project_overall_band(reading, listening, writing, speaking)` returns `None` until all four exist and uses existing IELTS overall half-band policy.
- Full Mock completes after final Speaking attempt, not Writing.

- [ ] **Step 1: Write failing backend/frontend tests** for four required modules/durations, Writing→Speaking transition, session completion after Speaking, missing Speaking rejection, four-band overall, and history deletion still deleting whole session safely.
- [ ] **Step 2: Run RED.**
- [ ] **Step 3: Implement order/duration/overall changes.** Choose a sensible Speaking recommended module duration default compatible with the authored prompt timers; do not use the old 11–14 minute official duration as a rigid per-attempt database invariant.
- [ ] **Step 4: Run GREEN + typecheck/Ruff as applicable.**
- [ ] **Step 5: Commit:** `git commit -m "Integrate Speaking into Full Mock"`.

### Task 17: History, focused practice, analytics, classroom assignment results and privacy

**Files:**
- Modify: `backend/app/services/history.py`, `backend/app/api/v1/history.py` if module-specific presentation needs extension
- Modify: `backend/app/services/classroom_assignments.py`, `backend/app/api/v1/classroom_assignments.py`
- Modify: analytics schemas/services only where skill enumerations are explicit
- Modify: frontend history/classroom result APIs and components
- Extend: `frontend/src/features/speaking/speaking-review.tsx` for teacher read-only mode
- Tests: `backend/tests/test_classroom_assignments.py`, `backend/tests/test_focused_attempts.py`, history/analytics tests; frontend history/classroom tests

**Interfaces:**
- Personal history exposes Speaking attempts with audio/transcript/AI summary under normal owner authorization.
- Teacher read-only view can inspect assignment-originated Speaking responses/audio/transcripts/attached advisory result only through the existing assignment provenance predicate; personal practice on the same version remains private.
- Focused Speaking practice can target a prompt/part according to the approved attempt scope without weakening exam behavior.

- [ ] **Step 1: Add failing privacy/integration tests** for teacher assignment access vs unrelated personal practice, membership removal preserving historical assignment read access, focused retry semantics, history rendering/deletion, and explicit Speaking analytics enumeration where present.
- [ ] **Step 2: Run RED.**
- [ ] **Step 3: Implement integration using existing provenance/access policy; no new teacher-wide student lookup shortcut.**
- [ ] **Step 4: Run GREEN + frontend typecheck/targeted lint.**
- [ ] **Step 5: Commit:** `git commit -m "Integrate Speaking history and classroom results"`.

**P7 gate:** verify all four skills coexist; old three-skill historical sessions remain readable rather than being retroactively invalidated. New Full Mock starts require Speaking.

---

# P8 — Benchmark + Calibration Tooling

### Task 18: Human-labelled Speaking evaluation harness and documentation

**Files:**
- Create: `backend/app/benchmarks/speaking.py` (or follow existing benchmark package conventions)
- Create: `backend/scripts/evaluate_speaking.py`
- Create: `backend/tests/test_speaking_benchmark.py`
- Create: `docs/ai-speaking.md`
- Modify: README/roadmap docs only where Speaking status is currently listed as future

**Interfaces:**
- Evaluation input manifest references local/private audio by path or controlled fixture ID plus human FC/LR/GRA/PR/overall labels; never commit copyrighted/private candidate recordings.
- Report per-criterion and overall MAE, RMSE, Pearson/Spearman when sample size permits, Quadratic Weighted Kappa, within ±0.5/±1.0, failure/nonscorable rate, and optional subgroup slices only when sample sizes are responsible.
- Store scorer/provider/prompt/ASR/acoustic version metadata with every evaluation output so calibration changes are reproducible.

- [ ] **Step 1: Write failing metric/manifest tests** with synthetic labels/predictions, including missing/nonscorable rows and deterministic metric output.
- [ ] **Step 2: Run RED:** `cd backend && uv run pytest tests/test_speaking_benchmark.py -q`.
- [ ] **Step 3: Implement offline evaluation CLI and docs.** Explain that Speak & Improve/SpeechOcean/L2-ARCTIC may inform research but are not direct IELTS-labelled ground truth; do not add automatic dataset downloads or redistribution.
- [ ] **Step 4: Run GREEN + Ruff.**
- [ ] **Step 5: Commit:** `git commit -m "Add Speaking grading benchmark tooling"`.

---

## Phase Verification Commands

At the end of each phase, run only the focused tests touched by that phase plus cheap static checks; do not open a browser or run live speech/LLM infrastructure. Typical commands:

```bash
cd backend
uv run pytest tests/test_speaking_builder.py -q                 # P1
uv run pytest tests/test_speaking_attempts.py -q                # P2
uv run pytest tests/test_speaking_media.py tests/test_speaking_recovery.py -q  # P3
uv run pytest tests/test_speaking_transcript.py -q              # P4
uv run pytest tests/test_speaking_audio.py tests/test_speaking_features.py -q   # P5
uv run pytest tests/test_speaking_ai.py -q                       # P6
# P7: focused full-mock/history/classroom targets named above
uv run pytest tests/test_speaking_benchmark.py -q                # P8
uv run ruff check <touched backend files>

cd ../frontend
npx vitest run <phase-specific speaking test files>
npm run typecheck
npx eslint <touched frontend files>

cd ..
git diff --check
```

If a focused command reveals a pre-existing unrelated failure, report it by name instead of expanding into a long unrelated suite. Do not claim a phase is verified unless its named tests/static checks actually passed.

## Recommended Commit/Review Gates

Implement P1 through P8 sequentially. Each numbered task has its own commit; each phase ends with a review before the next phase. The architecture has strong interface dependencies (content IDs -> attempt state -> media manifests -> transcripts -> features -> scoring -> product integration), so do not dispatch later phases against unstable earlier interfaces.

Before every phase:

```bash
git fetch origin
git pull --ff-only origin main
git status --short
```

Require a clean tree before starting, preserve any upstream work such as Writing AI v9, and never force-push `main`.

## Self-Review Coverage

- Spec §§1–2: Tasks 1–3 (content domain, Builder, validation, dynamic authoring).
- Spec §§3–5: Tasks 4–8 (preflight, runner, practice/exam rules, chunking, recovery, review).
- Spec §§6–8: Tasks 9–12 (transcript, quality, ASR/alignment, fluency/acoustic evidence).
- Spec §§9–12: Tasks 13–15 (holistic four-criterion score-first grading, durable runs/cache/SSE, AI UI).
- Spec §§13–18: covered across Tasks 6–17 (privacy, retention provenance, dynamic UX, errors/config, Full Mock/classroom/history).
- Spec §19 rollout: preserved exactly as P1–P8 review gates.
- Spec §20 benchmark/calibration: Task 18.

The five Review Focus risks are explicitly exercised in Tasks 6/7 (chunking/recovery), Task 6/17 (private authorization), Tasks 9/11/13 (ASR/audio failure), and Tasks 9/14/15 (durable background work and reconnect).
