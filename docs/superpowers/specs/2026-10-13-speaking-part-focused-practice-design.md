# Speaking Part-Focused Skill Practice Design

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Speaking Part-Focused Skill Practice Design. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/speaking_attempts.py).
> Đọc cùng [current module/guide](../../modules/speaking.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Status

Conversational design approved on 2026-10-13; written specification awaiting final user review before implementation planning.

This is an architectural extension of the existing focused-practice and Speaking runtime. It adds Speaking to **Skill Practice** as Part 1 / Part 2 / Part 3 units, reuses the existing recorder/recovery/transcript/AI stack, and introduces a free-navigation practice flow for Part 1 and Part 3 without weakening exam/full-mock restrictions.

## Goal

Add Speaking to `/practice` so a learner can choose an authored Speaking Part from a published test and practice that whole Part as one focused attempt.

The experience must provide:

- **Part 1**: Guided practice or Free question practice;
- **Part 2**: Guided practice only;
- **Part 3**: Guided practice or Free question practice;
- existing microphone preflight, recorder, segmented audio persistence, recovery, Listen/Retry, transcript and AI assessment;
- server-authoritative content scope and recording state;
- focused-practice history/review semantics that never masquerade as a completed full Speaking module.

## Non-goals

This change does not:

- add a second Speaking runner or media stack;
- add adaptive AI-examiner questions;
- add classroom assignment authoring for whole Speaking Parts;
- alter Full Mock or exam-mode navigation/retry restrictions;
- change IELTS Speaking scoring prompts/calibration merely to force Part scoring;
- turn a Part-level AI/final practice score into a full-module Speaking band;
- add focused Speaking records to full-module Analytics;
- invoke live ASR/LLM/GPU services during implementation verification.

## Current architecture

The existing system already has authored `SpeakingPart` records for Parts 1/2/3 and ordered `SpeakingPrompt` records. Public `VersionDetail` data already exposes speaking parts and their prompts, so Skill Practice discovery does not need a second content API.

Focused attempts currently support `SPEAKING_PROMPT` through `Attempt.focused_speaking_prompt_id`. `AttemptScopeGuard`, API schemas, history labels and `SpeakingRepository.prompts()` therefore scope a focused Speaking attempt to one prompt. The current Speaking runner is sequential: finishing the active response durably commits it, locks it, and advances progress to the next prompt. Practice mode allows Listen/Retry for the current response; exam/full-mock mode does not.

The design extends these existing boundaries rather than bypassing them.

## 1. Focused Part domain model

Add a new focused unit kind:

```text
SPEAKING_PART
```

Add nullable attempt state:

```text
focused_speaking_part_id -> speaking_parts.id
speaking_practice_flow: GUIDED | FREE
```

Keep the existing fields and semantics:

```text
focused_speaking_prompt_id
speaking_mode: PRACTICE | EXAM
```

`SPEAKING_PROMPT` remains supported for historical attempts and existing integrations. New Skill Practice starts use `SPEAKING_PART` only.

`speaking_mode` and `speaking_practice_flow` are intentionally separate concepts:

- `speaking_mode=PRACTICE` controls Practice capabilities such as replay/retry;
- `speaking_mode=EXAM` keeps exam restrictions;
- `speaking_practice_flow=GUIDED` controls sequential Part practice;
- `speaking_practice_flow=FREE` enables learner-directed prompt navigation within the selected Part.

A focused Speaking attempt must target exactly one of `focused_speaking_prompt_id` or `focused_speaking_part_id`, never both.

For backward compatibility, `speaking_practice_flow` is nullable on historical/full-module/prompt-focused records. For a new `SPEAKING_PART` Practice request, omitted flow defaults to `GUIDED`; `FREE` must be explicit. The backend rejects a non-null `speaking_practice_flow` where it is not meaningful rather than letting unrelated Speaking attempts inherit Free semantics accidentally.

## 2. Migration

Create one Alembic migration after the current single head. It must:

- add nullable `attempts.focused_speaking_part_id` with a `RESTRICT` foreign key to `speaking_parts.id`;
- add nullable/bounded `attempts.speaking_practice_flow` using repository conventions;
- replace the focused-scope CHECK constraint so a focused Speaking attempt may have exactly one prompt target or one part target while all Reading/Listening/Writing exclusivity rules remain intact;
- preserve all historical prompt-focused attempts without guessing their parent-Part intent;
- preserve a single Alembic head.

The migration must be tested on a freshly migrated PostgreSQL schema. Do not rely only on ORM metadata-created test tables.

## 3. Attempt start contract and validation

The new request shape is conceptually:

```json
{
  "test_version_id": "...",
  "module": "SPEAKING",
  "scope": "FOCUSED_UNIT",
  "focused_unit": { "kind": "SPEAKING_PART", "id": "..." },
  "speaking_mode": "PRACTICE",
  "speaking_practice_flow": "FREE",
  "timer": { "mode": "COUNT_UP" }
}
```

Existing `SPEAKING_PROMPT` requests remain valid.

Backend validation is authoritative. For new Part-focused starts:

- the selected Part must belong to the exact Speaking module of the requested published test version;
- Part 1 accepts `GUIDED` or `FREE`;
- Part 2 accepts `GUIDED` only;
- Part 3 accepts `GUIDED` or `FREE`;
- `SPEAKING_PART + EXAM` is rejected for this Skill Practice contract;
- Speaking focused practice uses count-up at the attempt level; authored prompt preparation/response timings remain authoritative inside the runner;
- missing, foreign-version and foreign-module IDs receive the existing safe invalid-target treatment.

Frontend disabling is convenience only; these rules must also be enforced by the backend.

## 4. Server-authoritative Part scope

`SpeakingRepository.prompts(attempt)` becomes:

```text
if focused_speaking_part_id:
    return every prompt in that Part, ordered by prompt.order_index
elif focused_speaking_prompt_id:
    return that one prompt (legacy/current compatibility)
else:
    return the complete Speaking module
```

Every Speaking mutation continues to prove the prompt belongs to the attempt's scoped prompt set. A Part 1 attempt must not be able to begin, record, upload, retry, replay, select or finalize a Part 2/3 prompt even if a client manually sends its UUID.

The browser must never send an authoritative list of allowed prompt IDs.

## 5. Skill Practice discovery and cards

`/practice` becomes a four-skill browser:

```text
Reading
Listening
Writing
Speaking
  All parts
  Part 1
  Part 2
  Part 3
```

Published `VersionDetail.speaking_parts` supplies the units. Each Speaking card represents one entire Part, not one prompt. It shows concise information such as:

```text
SPEAKING
Part 1
Introduction and Interview
8 questions
IELTS Cambridge 11 Test 1 · Version 13
```

Part 1 and Part 3 expose a compact practice-style selector:

```text
Guided practice
Free question practice
```

Part 2 exposes Guided only. Speaking cards use the existing semantic Speaking color/style and do not add a new visual language.

The existing Reading/Listening/Writing cards and timer behavior remain unchanged. Speaking does not show the generic focused minute selector; it starts with `COUNT_UP` and uses authored prompt timing inside the Speaking engine.

## 6. Guided Part practice

Guided practice reuses the existing Speaking runner and current durable sequencing semantics.

Part 1 and Part 3 run the prompts in authored order:

```text
prompt -> record -> durable finish acknowledgement -> next prompt
```

Part 2 preserves its meaningful sequence:

```text
preparation -> long turn -> authored follow-up(s) -> finish
```

Existing microphone preflight, chunk transport, retry/replay permissions, recovery grace, scratch-note behavior, timers and backend acknowledgement requirements remain in force.

No free question picker is shown in Guided mode. Existing Guided behavior may continue auto-entering the current prompt after preflight according to the current runner contract.

## 7. Free question practice

Free mode is available only for focused Part 1 and Part 3 Practice attempts.

The runner shows an accessible prompt picker, for example:

```text
[1] [2✓] [3] [4✓] [5] ...
```

plus Previous/Next convenience controls. A learner may navigate in any order, for example Q1 -> Q5 -> Q3 -> Q8. Each prompt maintains independent server-backed response state such as unanswered, selected, recording, committed and retried.

Unlike Guided mode, selecting a Free prompt must **not** automatically start recording. The learner explicitly presses `Record`. This preserves the intended self-practice workflow: choose a question, think/read it, record when ready, then navigate freely.

A committed prompt is revisit-able in Free mode. The learner may return to it, listen to its committed take and retry it. Retrying one prompt must not erase another prompt's recording.

This is a deliberate exception to Guided Practice's prior-prompt lock UX; it applies only when the attempt itself is persisted as `FREE`.

### 7.1 Free state contract

The current sequential runtime cannot simply reuse "finish last canonical prompt => submit attempt". Free mode needs an explicit safe idle/browsing state or equivalent server representation.

Conceptually:

```text
BROWSING / IDLE
  -> select prompt
QUESTION_ENTER / READY
  -> explicit Record
PREPARING? -> STARTING? -> RECORDING
  -> durable finish
BROWSING / IDLE
```

Exact phase naming may follow existing conventions, but the semantics are required:

- a new Free attempt is not forced to begin Q1 automatically;
- finishing Q8 first must **not** complete the attempt merely because Q8 is last in authored order;
- committing one response returns to a safe state from which another allowed prompt can be selected;
- attempt completion is a separate explicit `Finish practice` operation;
- canonical prompt order still drives picker labels and Previous/Next, not completion authority.

The public Speaking state for a Free Part must include enough bounded server data to reconstruct the picker after refresh, for example the selected prompt plus a prompt navigation summary containing prompt ID/order and safe status (`UNANSWERED`, `COMMITTED`, current). The frontend must not infer authoritative completion from its local component state.

### 7.2 Switching while recording

Free navigation must never silently discard an active recording. If the learner selects another question while capture is active, show a confirmation with equivalent actions:

```text
Continue recording
Stop & switch
```

`Stop & switch` must:

1. stop the physical recorder;
2. flush/close pending chunk transport;
3. finalize the current response through the server;
4. wait for the durable backend acknowledgement;
5. only then activate the requested prompt.

There is no optimistic prompt switch before acknowledgement.

If persistence fails, stay on the current prompt and show the normal actionable save/retry error.

### 7.3 Server prompt selection

Free navigation needs an explicit server-authoritative operation/state transition to select a prompt from the attempt's scoped Part. It must not be implemented as a frontend-only rewrite of `SpeakingPromptProgress.prompt_id` assumptions.

The server permits selection only from a safe non-recording state, except that the client may first execute the acknowledged `Stop & switch` flow above. It rejects targets outside the Part.

Exact route naming follows existing Speaking API conventions; no generic arbitrary-progress mutation endpoint is introduced.

### 7.4 Replaying and retrying committed prompts

The existing sequential runtime treats previously committed responses as locked. Free mode deliberately needs a narrow server-authorized exception for committed prompts within the selected Part.

Selecting a committed prompt must be able to expose its committed response for replay without reopening unrelated prompts or bypassing Part scope.

If the learner chooses Retry on a committed Free response, the previous committed take must remain the valid fallback until a replacement take is durably committed. A failed/abandoned retry must not destroy the last good recording. On successful replacement commit, update the response's active committed take/fingerprint atomically and mark the superseded take according to existing provenance conventions.

This behavior is Free-only; Guided, Exam and Full Mock lock semantics do not change.

## 8. Part 2 rule

Part 2 is always Guided. Its cue-card preparation, long-turn response and related follow-up sequence are treated as one coherent practice flow.

The backend rejects `Part 2 + FREE`; the frontend does not offer that option. Do not add a question picker that jumps directly into the middle of Part 2.

## 9. Completion semantics

Guided Part practice completes through the existing sequential flow when the selected Part's prompt sequence is complete.

Free Part practice completes only through an explicit `Finish practice` action. It may finish without answering every prompt, but it must require at least one durably committed response and must reject completion while an unresolved active recording/recovery transition is in progress.

Completion must not manufacture responses for unanswered prompts. Review presents them as `Not answered` based on the Part's authored prompt list.

The attempt is a single focused attempt for the Part, not one attempt per question.

## 10. Refresh, recovery and persistence

`FREE`/`GUIDED` is persisted on the Attempt; it is not React-only state.

After refresh, the backend remains authoritative for:

- selected Part and flow;
- selected/current prompt and phase;
- committed responses and active take numbers;
- interrupted/recovery state;
- prompt eligibility and picker statuses.

The UI reconstructs the picker from backend state. Existing segmented-audio recovery remains unchanged: a crash/reload does not fabricate audio, reset response quota or switch to a different prompt.

If a crash occurs during a Free retry, the existing committed take remains the fallback unless/until the replacement take was durably committed.

## 11. Review

Part-focused review shows the selected Part's full authored prompt list and response status, while audio/transcript controls exist only for answered prompts.

Example:

```text
Speaking · Part 1
Free practice

Q1  27s
Q2  Not answered
Q3  31s
```

Guided review identifies Guided practice. Legacy `SPEAKING_PROMPT` attempts continue to render their existing prompt-focused label rather than being silently reinterpreted as a Part attempt.

Unanswered prompts are informational; they do not receive fabricated audio/transcripts/feedback.

## 12. History and Analytics

Part-focused attempts belong to Focused Practice history. Presentation should distinguish Part 1/2/3 and, where useful, Guided/Free.

They must not:

- occupy the full Speaking module slot in By-skill/By-test grouping;
- count as a completed full Speaking module;
- contribute a Part practice band as the full Speaking band;
- contribute to a Full Mock overall;
- enter full-module Speaking Analytics as if they were a complete test.

Existing focused-attempt exclusions are extended to `SPEAKING_PART`.

## 13. Transcript and audio review

Transcript generation remains per committed response. A learner does not need to answer every prompt in a Free Part before generating/viewing transcript data for answered prompts.

Raw audio remains private and governed by the existing media authorization. There is no new media storage format or merged full-Part audio asset requirement.

## 14. AI assessment

A focused Part may use the current Speaking AI pipeline when its committed evidence is assessable. The UI must identify the result as Part practice, e.g.:

```text
AI Assessment · Part 1 practice
Advisory
```

The scorer may still return FC/LR/GRA/PR criterion assessments for the evidence actually present, but a Part result is not a complete IELTS Speaking test band.

If a Free attempt contains too little usable evidence, retain current unassessable behavior rather than fabricating a score. No AI prompt/calibration changes are introduced solely to force Part-level scoring.

## 15. Human/personal final score semantics

The recently added provenance-aware subjective grading remains authoritative.

A personal focused Speaking Part may retain a saved human/self-assessed practice score if supported by the current final-score flow. However, that score remains attached to the focused attempt and must not be promoted into:

- a full-module `attempt.band_score` where existing focused semantics keep it null;
- Full Mock overall;
- full Speaking Analytics.

AI results remain advisory and are never auto-promoted by run completion.

Classroom students/teachers retain the subjective grading boundaries introduced by `Add provenance-aware subjective skill grading`.

## 16. Classroom compatibility

This feature is for `/practice`. It does not add a new classroom UI for assigning a whole Part.

Existing `SPEAKING_PROMPT` assignment/start contracts remain backward-compatible. Shared API schemas may learn the `SPEAKING_PART` discriminator where required for common typing, but implementation must not silently broaden classroom assignment behavior.

Assignment provenance, teacher-only classroom final grading and private personal-practice boundaries must not regress.

## 17. Accessibility, responsive UX and i18n

New visible copy is localized in EN + VI.

The Free picker must:

- use semantic buttons with clear current/completed/unanswered state not conveyed by color alone;
- be keyboard operable;
- preserve visible focus;
- horizontally scroll or wrap safely on narrow screens without page overflow;
- keep recording status and timer accessible;
- respect reduced-motion settings for any subtle state transition.

Recording-navigation confirmation must be keyboard/touch accessible and reuse the project's dialog conventions.

## 18. Backward compatibility

The implementation must preserve:

- old full-module Speaking attempts;
- old focused `SPEAKING_PROMPT` attempts;
- existing Practice and Exam semantics;
- Full Mock no-replay/no-retry/no-back restrictions;
- existing audio chunks/takes/recovery behavior;
- existing transcript cache/authorization;
- existing Speaking AI advisory semantics;
- current provenance-aware Writing/Speaking final grading;
- Reading/Listening/Writing focused practice.

No historical attempt is rewritten from prompt scope to part scope.

## 19. Risks and mitigations

### Free navigation bypasses current sequential lock assumptions

Mitigation: add explicit server transitions for Free prompt selection and keep the Part-scoped allowed-prompt set authoritative. Do not mutate progress locally in React.

### Finishing the authored last prompt could accidentally submit a Free attempt

Mitigation: branch completion semantics on persisted `speaking_practice_flow`. Free response commit returns to browsing/safe state; only explicit `Finish practice` submits the attempt.

### Navigating during recording can lose audio

Mitigation: require stop -> flush/close -> durable finish ACK -> switch. Never discard a current recording implicitly.

### Retrying an already committed answer can lose the last good recording

Mitigation: preserve the committed take until the replacement is durably committed; switch the active committed take atomically.

### Part practice can pollute full-skill statistics

Mitigation: retain `scope=FOCUSED_UNIT`, extend history/review labels, and add explicit regression coverage that focused Part scores do not promote to full-module band/Analytics/Full Mock.

### Migration can break historical scope constraints

Mitigation: make Part targeting additive, keep `focused_speaking_prompt_id`, test real upgrade constraints, and verify a single Alembic head.

## 20. Remote CI baseline gate

Implementation MUST begin by inspecting the current `origin/main` GitHub Actions result and actual failing job logs before feature coding.

At specification time, the feature baseline before documentation commits is:

```text
0a4a757c0788a2c0ce63ea671295770a12062bad
Add provenance-aware subjective skill grading
```

The push CI run `38346177088` is **red**. The failure is in unit-test stages, not lint/typecheck/migration-head checks:

- Backend Ruff lint: pass.
- Backend Ruff format: pass.
- Fresh PostgreSQL Alembic upgrade: pass.
- Single Alembic head verification: pass.
- Backend tests: **6 failed, 367 passed**. The observed common failure for the new subjective-grading tests is `sqlite3.OperationalError: no such table: attempt_speaking_scores`, indicating a test-schema/fixture path that did not include the new Speaking final-score table even though CI's migrated PostgreSQL upgrade itself passed.
- Frontend typecheck: pass.
- Frontend ESLint: pass.
- Frontend unit tests: **3 failed, 281 passed**. One confirmed failure is in `tests/speaking-history-classroom.test.tsx`, where `getByRole("button", { name: "Use AI score as starting point" })` now matches multiple buttons after the subjective-grading UI change. The remaining frontend failures must be read from the actual remote log rather than guessed.
- The separate `Golden path E2E` workflow for the same SHA completed successfully, but it does not override the red CI workflow.

The implementation plan must therefore enforce this sequence:

1. fetch latest `origin/main` and inspect remote Actions for that exact SHA;
2. if main is still red, reproduce/fix the baseline CI failures first (or verify a newer main already fixed them);
3. do not stack this feature on unexplained red CI;
4. run the focused regression set while implementing the feature;
5. after push, inspect GitHub Actions for the final SHA;
6. do not declare completion while the relevant CI workflow is red;
7. if remote CI fails, inspect the actual log, fix the root cause and push a normal follow-up commit; never force-push merely to hide failure.

## 21. Test strategy

Backend coverage should include at minimum:

- `SPEAKING_PART` request/schema contract;
- default `GUIDED` behavior when Part flow is omitted and invalid flow placement rejection;
- Part belongs to exact published version/module;
- Part 1/3 Guided + Free accepted;
- Part 2 Free rejected;
- `SPEAKING_PART + EXAM` rejected for this flow;
- real migration + scope CHECK behavior;
- Part repository returns all and only Part prompts in canonical order;
- out-of-Part prompt begin/media/retry/replay/select/finalize rejected;
- legacy `SPEAKING_PROMPT` behavior retained;
- Guided progression retained;
- Free starts without auto-recording and allows explicit Record;
- Free out-of-order selection and picker-state reconstruction;
- committing authored-last prompt does not auto-submit a Free attempt;
- explicit Free finish requires >=1 committed response, permits unanswered prompts, and rejects unresolved active capture;
- committed prompt replay/retry works only in Free Part scope;
- failed committed-response retry preserves the prior committed recording;
- switch-while-recording cannot bypass durable finalization;
- refresh/recovery retains Part/flow/current state;
- review contains selected Part and unanswered entries only;
- focused Part remains excluded from full-module History/Analytics/Full Mock band promotion;
- subjective grading/provenance regression coverage remains green.

Frontend Vitest/RTL coverage should include at minimum:

- Speaking appears in Skill Practice with All parts / Part 1 / Part 2 / Part 3 filters;
- cards use `SPEAKING_PART` start payload;
- Part 1/3 offer Guided and Free;
- Part 2 offers Guided only;
- Speaking uses count-up rather than generic minute presets;
- Guided runner has no Free picker;
- Free picker does not auto-start recording;
- explicit Record starts the selected prompt;
- Free picker navigates out of order;
- completed/unanswered/current statuses are accessible;
- revisit retains replay/retry behavior;
- active-recording navigation asks for confirmation;
- `Stop & switch` waits for persistence acknowledgement before moving;
- failed persistence leaves the user on the current prompt;
- explicit Finish Practice behavior and >=1-response guard;
- refresh reconstruction uses backend state;
- existing Speaking exam/full-mock restrictions do not change.

No browser/Playwright is required for implementation verification unless a later failure genuinely cannot be diagnosed with unit/component tests. Do not invoke Modal, live ASR, live LLM or GPU services for this task.

## 22. Acceptance criteria

The feature is complete only when:

1. Skill Practice lists Speaking Part 1/2/3 from published versions.
2. Starting a card creates one Part-focused Practice attempt.
3. Part 1/3 support both Guided and Free flows; Part 2 is Guided only.
4. Guided behavior remains equivalent to the existing sequential Speaking practice within the selected Part.
5. Free mode permits safe out-of-order selection and does not auto-start recording.
6. Free mode permits revisit, Listen and safe Retry while preserving recordings per prompt and the last good committed take on failed replacement.
7. Navigating during active capture cannot lose/skip unacknowledged recording persistence.
8. Finishing a response in Free mode never auto-submits merely because it is the last authored prompt; explicit Finish Practice controls completion.
9. Backend rejects any prompt outside the selected Part.
10. Refresh/recovery reconstructs the persisted flow, selected prompt and response/picker state.
11. Review/history identify the Part and flow correctly; unanswered Free prompts are represented without fabrication.
12. Part-level AI/human scores remain advisory/focused and never become a full Speaking module or Full Mock band.
13. Legacy prompt-focused and full-module Speaking attempts still work.
14. Current classroom/provenance-aware final grading remains intact.
15. Alembic remains one head and the new migration passes against a fresh PostgreSQL database.
16. The pre-existing red CI baseline is resolved before feature completion.
17. GitHub Actions for the final pushed SHA is inspected and the relevant CI workflow is green.

## 23. Execution constraints for the later implementation plan

- Never use Astra.
- At most two non-nested subagents, and only if their non-Astra model can be guaranteed; otherwise execute inline.
- Prefer focused backend/frontend unit/component tests while developing.
- No manual browser/Playwright, Modal deployment, live ASR, live LLM or GPU invocation for this work.
- Preserve BandPilot branding and the recently completed Writing/Speaking subjective-grading/AI work.
- Use normal commits and safe fast-forward integration; never force-push.
