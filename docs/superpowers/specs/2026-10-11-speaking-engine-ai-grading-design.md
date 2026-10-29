# Speaking Engine, Recording, Transcript & AI Grading Design

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Speaking Engine, Recording, Transcript & AI Grading Design. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/speaking_attempts.py).
> Đọc cùng [current module/guide](../../modules/speaking.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.
> Speaking instructions vẫn binding theo AGENTS; không archive hoặc vô hiệu hóa self-review amendments.

## Status

Approved conversational design captured for implementation planning. This specification introduces Speaking as the fourth first-class IELTS skill and defines its Builder, runner, recording/recovery contract, transcript workflow, hybrid AI grading architecture, review UX, and integration boundaries.

This is an architectural addition. Implementation must be phased; do not attempt the entire subsystem as one undifferentiated change.

## Goal

Add a production-quality IELTS Speaking practice/exam experience that:

- integrates Speaking into the existing test/version/attempt engine rather than as a detached demo;
- supports Part 1, Part 2, and Part 3 authoring and execution;
- records and durably persists candidate speech per prompt;
- survives browser reload/crash with bounded recovery behavior;
- provides a separate read-only per-question transcript workflow;
- provides an explicit `Grade with AI` workflow using audio + transcript evidence;
- scores the four IELTS Speaking criteria independently and holistically across the whole attempt;
- keeps AI grading advisory and observable;
- has a dynamic, responsive, state-driven UI without distracting exam-mode animation;
- leaves room for later calibration/fine-tuning against human-labelled data.

## Research basis

The design follows these public assessment/system patterns rather than treating Speaking as transcript-only LLM grading:

- Official IELTS Speaking structure and band descriptors: three parts, approximately 11–14 minutes, with Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy, and Pronunciation as the four equally weighted assessment criteria.
- ETS SpeechRater-style construct-driven automated speaking assessment: ASR plus pronunciation, prosody, fluency, grammar, vocabulary/content/discourse features, with explicit nonscorable-response filtering.
- Cambridge Speak & Improve / SLATE 2025 systems: separate acoustic and text branches, often fused with handcrafted fluency/pronunciation features.
- CASA-style public research architecture: acoustic speech branch + transcript/content branch + fusion/scoring head.
- GOPT / SpeechOcean-style pronunciation research: GOP and learned speech representations can provide pronunciation evidence, but those dataset scores must not be mapped directly to IELTS bands.
- Whisper / faster-whisper plus WhisperX-style word alignment as a practical ASR/timestamping pattern.

This project does **not** claim to reproduce a single academic paper exactly. V1 is a hybrid, descriptor-driven IELTS advisory scorer inspired by these public systems.

## Repository scope note

The current repository still contains an older `AGENTS.md` statement saying not to implement Speaking. This user request explicitly supersedes that stale scope guard. The implementation plan should include updating that repository guidance so future work does not treat Speaking as forbidden once implementation begins.

## Product decisions

- Speaking becomes a first-class skill alongside Listening, Reading, and Writing.
- A Speaking test contains exactly three logical parts: Part 1, Part 2, Part 3.
- Part 1 and Part 3 are authored as ordered prompt sequences. The Builder feels append-oriented like a linked list, but persistence uses stable IDs plus `order_index`, not `next_question_id` pointers.
- Part 2 is a dedicated long-turn/cue-card prompt type with preparation time, cue points, response time, and optional follow-up prompts.
- Prompt timers are configurable. Part 1/3 default to 60 seconds per prompt for this application workflow, but 60 seconds is not encoded as an immutable claim about official IELTS per-question timing.
- Part 2 defaults to 60 seconds preparation and up to 120 seconds speaking time.
- Candidate may press `Done / Next` before a timer expires; timeout automatically stops, persists, and advances.
- Exam/Full Mock: no replay, no retry, no return to a committed previous response.
- Focused/self-practice: candidate may listen and retry the current response before `Done / Next`; committed prior prompts stay locked.
- Reload/crash recovery resumes the interrupted prompt rather than restarting it.
- Recovery preserves a server-authoritative snapshot of the response/preparation time remaining at interruption, then grants a 7-second reconnect/preparation grace window before that remaining time resumes. The grace is not added to speaking quota and cannot be farmed with repeated refreshes.
- Speaking review exposes two separate user actions: `Generate Transcript` and `Grade with AI`.
- Transcript is read-only and shown per question/prompt only; there is no merged full-transcript UI in v1.
- `Grade with AI` reuses a valid transcript if available; otherwise it generates one internally.
- User cannot edit ASR transcript before grading.
- A clean transcript may normalize punctuation/filler formatting for analysis but must never repair grammar or silently improve what the candidate said.
- AI grading is holistic across the entire Speaking attempt. Question-level analysis is evidence/feedback only; no averaging of question scores.
- AI uses score-first grading: evidence -> tiny score-only output -> persist score -> feedback. Feedback failure must not erase a valid score.
- Pronunciation must use audio-derived evidence; a text-only LLM must not infer Pronunciation from transcript alone.
- UI/motion defaults are chosen for clarity and polish; exam UX stays restrained and accessible.

## 1. Domain model

Exact table names may follow current repository conventions, but the design requires the following concepts.

### 1.1 Speaking module and parts

Extend module typing to support Speaking as a first-class module.

```text
SpeakingModule
- id
- test_version_id
- recommended_duration_seconds nullable
- config_json

SpeakingPart
- id
- speaking_module_id
- part_number: 1 | 2 | 3
- title nullable
- instructions nullable
- order_index
```

The system should enforce one logical Part 1, one Part 2, and one Part 3 per complete Speaking module while still allowing a draft to be temporarily incomplete in Builder state.

### 1.2 Speaking prompts

```text
SpeakingPrompt
- id
- speaking_part_id
- order_index
- prompt_type: SHORT_ANSWER | LONG_TURN | FOLLOW_UP
- prompt_text
- preparation_seconds
- response_seconds
- config_json
```

`config_json` may hold cue points and part-specific presentation data, but core timer/order fields should remain queryable typed columns when practical.

Part 1 and Part 3 normally use `SHORT_ANSWER` prompts.

Part 2 uses one `LONG_TURN` prompt with cue-card configuration and optional authored follow-up prompts. Follow-ups remain explicit authored prompts in v1; no adaptive AI examiner is required.

### 1.3 Stable ordering

Adding a prompt appends it at the end by default. Reordering uses `order_index` normalization like existing Builder patterns. Do not implement a database linked list.

Stable prompt IDs survive reorder so response/history references remain durable.

## 2. Builder

Speaking Builder is integrated into the existing test/version Builder and honors existing ownership, moderation, autosave, version immutability, and teacher/admin policy.

### 2.1 Part 1 / Part 3 authoring

Each part renders a vertical ordered flow:

```text
Question card
   ↓
Question card
   ↓
+ Add question
```

Each card supports:

- prompt text;
- response time with a sensible default of 60 seconds;
- reorder;
- delete while draft is mutable;
- inline validation.

Add/reorder should use lightweight transition animation so the sequence is visually obvious.

### 2.2 Part 2 authoring

Long-turn editor supports:

- cue-card main prompt;
- list of cue points (`You should say...`);
- preparation time, default 60s;
- long-turn response time, default 120s;
- optional follow-up question sequence;
- preview of candidate presentation.

Candidate scratch notes are runtime-only attempt data and are not authored/scored content.

### 2.3 Validation

Publish/moderation validation should reject malformed complete Speaking modules, including missing required parts, duplicate part numbers, missing long-turn prompt, non-positive timers, duplicate/stale order indices after normalization, and empty required prompt text.

Draft autosave may persist incomplete intermediate state according to existing Builder conventions.

## 3. Candidate Speaking setup and runner

### 3.1 Microphone preflight

Before starting a Speaking attempt, show a microphone setup surface:

- request microphone permission once;
- select input device where browser APIs allow;
- verify `MediaRecorder` capability;
- show a lightweight realtime level meter;
- detect an obviously silent/near-silent signal;
- show chosen supported recording MIME type;
- start test only after minimum readiness checks succeed.

Do not run AI in preflight.

### 3.2 Prompt execution

For Part 1/3:

```text
QUESTION_ENTER
-> RECORDING
-> USER_DONE or TIMEOUT
-> FINALIZING / UPLOADING
-> COMPLETED
-> NEXT_QUESTION
```

The displayed prompt and countdown are the current prompt only. Candidate is not shown future questions in exam/full-mock mode.

For Part 2:

```text
QUESTION_ENTER
-> PREPARING
-> short start countdown
-> RECORDING
-> USER_DONE or TIMEOUT
-> FINALIZING / UPLOADING
-> optional authored FOLLOW_UP prompt(s)
-> COMPLETED
```

### 3.3 Done / Next behavior

`Done / Next`:

1. stops recorder;
2. flushes pending chunks;
3. finalizes response metadata;
4. waits for backend acknowledgement;
5. advances only after the response is durably accepted.

Do not advance optimistically if final persistence failed.

### 3.4 Practice vs exam/full mock

Focused/self-practice:

- current response may expose `Listen`, `Retry recording`, `Done / Next`;
- retry requires a lightweight confirmation;
- retry supersedes the previous uncommitted/current take;
- once candidate advances, prior prompt is locked.

Exam/Full Mock:

- no replay;
- no retry;
- no previous-question navigation;
- no reopening completed prompt.

## 4. Recording, assets, chunking, and response persistence

### 4.1 Storage contract

Raw audio is stored outside PostgreSQL using the existing asset/storage abstraction. PostgreSQL stores metadata, ownership/provenance, response state, chunk ordering, and asset references.

Prefer browser `audio/webm;codecs=opus` when supported, with capability-driven fallback. Do not require frontend WAV encoding.

Derived ASR/acoustic preprocessing may normalize to 16 kHz mono PCM/WAV internally.

### 4.2 Speaking response

```text
SpeakingResponse
- id
- attempt_id
- prompt_id
- active_take_number
- started_at
- completed_at nullable
- duration_ms
- status
- completion_reason: USER_DONE | TIMEOUT | INTERRUPTED
- locked
- committed_audio_fingerprint nullable
```

Practice retries preserve provenance. Superseded takes are not used for grading.

### 4.3 Chunked recording

To support crash recovery, MediaRecorder must periodically emit small chunks (target roughly 2–5 seconds; exact value selected during implementation based on browser behavior and upload overhead).

```text
SpeakingAudioChunk
- id
- response_id
- take_number
- sequence
- asset reference / storage key
- duration_ms nullable
- created_at
```

Chunk upload is idempotent by response/take/sequence. Duplicate retries must not duplicate logical audio.

The final logical response may be represented as an ordered chunk manifest or assembled derived asset; raw chunks remain provenance unless retention policy intentionally compacts them later.

## 5. Crash/reload recovery

### 5.1 Server-authoritative timing

Frontend timers are display aids. Backend owns the authoritative active phase and a recoverable remaining-time snapshot.

Conceptually:

```text
SpeakingPromptProgress
- attempt_id
- prompt_id
- state
- phase_started_at
- phase_deadline_at
- last_confirmed_remaining_ms
- interruption_count
- recovery_grace_used_for_current_interruption
- last_resumed_at nullable
```

Exact persistence may be folded into attempt/response tables if that is cleaner, but the semantics must remain explicit.

The backend updates/derives `last_confirmed_remaining_ms` from authoritative timing plus accepted heartbeats/chunks. The client must never invent a larger remaining value.

### 5.2 Recovery behavior

If browser reload/crash occurs during a valid active phase:

- preserve already uploaded chunks;
- restore the same active prompt;
- do not reset to the full original timer;
- recover the bounded remaining-time snapshot from the interruption/last server-confirmed state;
- suspend consumption of that snapshot while the browser reconnects under the recovery flow;
- grant a 7-second recovery grace countdown after the app/microphone has restored enough state to continue;
- during grace, show the restored prompt and reconnect/reinitialize microphone;
- after grace, resume the recovered remaining preparation/response time;
- resume chunk sequence/take coherently.

Example: 31 seconds remained at the last valid interruption snapshot. After recovery succeeds, the UI gives a 7-second reconnect/preparation countdown, then resumes with 31 seconds of the original response allowance remaining.

If the backend cannot establish a valid recoverable interruption state (for example, the attempt was already finalized or the saved state is inconsistent), it must fail closed rather than manufacturing extra time.

### 5.3 Anti-abuse

- grace and remaining-time recovery are server-authorized, not frontend-calculated;
- repeated refresh while restoring must not stack additional 7-second grants or repeatedly rewind remaining time;
- a completed prompt never reopens;
- each interruption/recovery transition is idempotent and auditably tied to the same prompt/take;
- record interruption/recovery events for debugging/audit without exposing sensitive logs to users.

### 5.4 Unrecoverable last chunk

A small in-memory final chunk may be lost on hard process/browser crash. That is acceptable if earlier chunks were durably uploaded. Recovery must not pretend missing audio exists. Quality analysis can surface material gaps later if necessary.

## 6. Transcript subsystem

Speaking Review exposes a separate `Generate Transcript` action.

### 6.1 Transcript job

Transcript generation runs as a durable background job or reusable processing resource, not a long synchronous request.

Pipeline:

```text
committed audio
-> quality/readability check
-> ASR
-> word-level timestamps/alignment
-> verbatim transcript
-> clean transcript
-> persist per response
```

No scoring occurs in this workflow.

### 6.2 Transcript records

Conceptually:

```text
SpeakingTranscript
- id
- response_id
- audio_fingerprint
- kind: VERBATIM | CLEAN
- text
- word_timing_json
- asr_provider
- asr_model
- asr_version
- confidence_metadata_json nullable
- status
- generated_at
```

A more normalized word table is optional if query/use cases justify it; JSON is sufficient for v1 if validated and bounded.

### 6.3 Read-only semantics

Users may view transcripts but cannot edit them before AI grading.

Verbatim transcript should preserve assessment-relevant disfluencies where the ASR pipeline can detect them, including repetitions, fillers, false starts, and partial speech signals.

Clean transcript may normalize punctuation/casing/filler presentation for semantic analysis, but must not correct grammar, vocabulary, tense, word choice, or other candidate language errors.

### 6.4 Per-question UI only

Review shows transcript under each prompt/response card. No merged full transcript view is required in v1.

A transcript failure is isolated per response where possible; one failed response must not discard transcripts already generated for other responses.

### 6.5 Reuse/invalidation

Transcript cache identity includes committed audio fingerprint + ASR/alignment model/version/config.

If committed audio changes through practice retry, stale transcript is invalid for new grading.

`Grade with AI`:

- reuses valid transcript processing already complete;
- waits/reuses an active matching transcript job instead of starting duplicate ASR;
- internally generates missing/stale transcripts when necessary.

## 7. Audio quality gate

Before scoring, evaluate whether audio is assessable.

At minimum distinguish equivalents of:

```text
AUDIO_OK
NO_SPEECH
TOO_SHORT
AUDIO_CORRUPT
VERY_LOW_SIGNAL
SEVERE_CLIPPING
BACKGROUND_DOMINANT
ASR_UNUSABLE
```

Do not convert technical audio failure into a low IELTS criterion band. If pronunciation cannot be assessed because microphone capture is unusable, return an assessment-unavailable/failure state rather than fabricating `Pronunciation = 1`.

Quality checks should be explainable and threshold-driven, but thresholds must not themselves become IELTS band rules.

## 8. Speech preprocessing and feature extraction

V1 should use replaceable provider boundaries rather than baking one research model into domain logic.

### 8.1 ASR/alignment provider

A practical default implementation may use faster-whisper/Whisper plus WhisperX-style word alignment/timestamps. Provider interfaces should make later replacement possible.

Do not require diarization for candidate-only recordings unless implementation later records examiner audio into the same stream.

### 8.2 Fluency/timing features

Compute deterministic evidence such as:

- total response/speech duration;
- speech ratio/silence ratio;
- words per minute;
- articulation rate;
- pause count and pause-duration distribution;
- long-pause count/ratio;
- filled-pause count where detectable;
- repetitions;
- false starts;
- self-corrections;
- average turn length;
- Part 2 sustained-turn duration.

These are evidence, not hard scoring formulas.

Do not implement rules like `pause_count > N => Band X`.

### 8.3 Pronunciation/acoustic evidence provider

Define a replaceable boundary such as:

```text
PronunciationEvidenceProvider
```

V1 may combine:

- speech encoder representations;
- ASR/alignment confidence and phone/word timing where reliable;
- GOP-style pronunciation evidence where applicable;
- pitch/F0, rhythm, stress, and timing features;
- connected-speech proxies;
- intelligibility/listener-effort proxies.

The provider returns bounded evidence/features, not an unreviewed dataset score mapped directly to IELTS.

Open-source research such as GOPT/SpeechOcean may inform implementation/testing, but SpeechOcean pronunciation scores must never be linearly relabelled as IELTS bands.

## 9. AI Speaking grading architecture

Speaking Review exposes a separate `Grade with AI` action. Submission itself does not automatically invoke AI grading.

### 9.1 Durable grading run

Reuse the architectural philosophy of Writing AI grading:

- persistent run record;
- background worker;
- durable progress/events;
- reconnectable SSE/JSON status;
- closing/reloading frontend does not cancel worker;
- only explicit Stop/cancel terminates the job where supported.

Conceptual phases:

```text
QUEUED
QUALITY_CHECK
TRANSCRIBING
ANALYSING_AUDIO
BUILDING_EVIDENCE
SCORING
GENERATING_FEEDBACK
COMPLETED
```

with explicit `FAILED` / `CANCELLED` outcomes.

### 9.2 Whole-performance scoring

The four IELTS criteria are evaluated independently across the complete Speaking performance:

- Fluency and Coherence (`fc`);
- Lexical Resource (`lr`);
- Grammatical Range and Accuracy (`gra`);
- Pronunciation (`pr`).

Question- or part-level metrics/evidence may support feedback, but final criterion score must not be the arithmetic mean of per-question scores or per-part scores.

### 9.3 Fluency and Coherence branch

Inputs:

- all question context and response transcripts;
- verbatim disfluency evidence;
- timing/fluency metrics;
- part boundaries and Part 2 long-turn behavior;
- official IELTS Fluency and Coherence descriptor semantics.

Assess holistic continuity, hesitation behavior, progression, discourse organization, cohesive/discourse features, and ability to sustain/develop speech.

### 9.4 Lexical Resource branch

Inputs:

- complete attempt transcripts;
- question context;
- official LR descriptor semantics.

Assess range, precision, appropriacy, paraphrase ability, collocation, idiomatic/less-common language control, and lexical limitations across the whole attempt.

### 9.5 Grammatical Range and Accuracy branch

Inputs:

- complete attempt transcripts;
- utterance/sentence segmentation;
- optional deterministic grammar-pattern evidence;
- official GRA descriptor semantics.

Assess range/flexibility of structures, accuracy, error patterns, and communicative effect. Deterministic grammar detectors may provide evidence but do not create hard score caps.

### 9.6 Pronunciation branch

Pronunciation must use audio-derived evidence. Do not let a text-only language model assign Pronunciation based only on transcript style.

Inputs should cover as available:

- segmental clarity/control;
- likely substitutions/deletions or articulation instability;
- word/sentence stress;
- rhythm;
- intonation/pitch movement;
- connected speech;
- global intelligibility and listener-effort evidence;
- consistency across the attempt.

Official IELTS Pronunciation descriptor semantics remain the scoring authority; acoustic features are evidence.

### 9.7 Score-first contract

Apply the reliability lesson from Writing AI grading.

For each criterion:

```text
criterion evidence
-> SCORE ONLY
-> durable valid score
-> feedback generation
```

Score output should be tiny, conceptually:

```json
{"score": 6.5}
```

Use strict half-band validation consistent with the project advisory scoring contract. No score offsets, generosity bias, fallback default band, or heuristic score invention.

If score stage remains invalid after bounded repair, criterion fails explicitly.

If feedback stage fails after valid score:

- preserve the score;
- preserve validated evidence;
- use a safe concise fallback feedback state/message;
- do not fabricate detailed strengths/improvements;
- record safe internal diagnostics.

### 9.8 Feedback output

Feedback is generated after and conditioned on the fixed score. It may contain:

- concise criterion explanation;
- up to a small bounded number of strengths;
- up to a small bounded number of improvements;
- references to per-question/part evidence where useful.

Feedback output must not contain an authoritative score field capable of overriding the fixed numeric score.

### 9.9 Overall band

The four criterion scores are equally weighted according to IELTS Speaking assessment structure. Reuse the project’s established half-band rounding policy only after verifying it matches the intended Speaking overall display semantics.

All automated output is clearly labelled advisory/non-official.

## 10. Grading cache/fingerprint

AI result identity must include enough provenance to prevent stale reuse, including:

```text
committed attempt audio fingerprint(s)
response/take revisions
quality-gate version
ASR provider/model/version/config
alignment version
fluency-feature extractor version
pronunciation-evidence provider/version
IELTS speaking rubric/prompt version
score/feedback contract version
```

Changing a committed practice take invalidates dependent transcript/features/AI grade for that attempt.

Reloading review with unchanged inputs reuses existing artifacts/results.

## 11. Review UX

Review is organized by Part and prompt.

Each response card may show:

- question/cue card;
- audio playback;
- duration;
- recording status/completion reason;
- transcript generation status;
- read-only transcript when ready;
- localized processing/quality errors.

Top-level actions:

```text
[ Generate Transcript ]    [ Grade with AI ]
```

Transcript state is per response, e.g. Ready / Processing / Failed.

AI result view shows:

- advisory overall band;
- four criterion score cards;
- concise criterion feedback;
- strengths/improvements;
- selected evidence/metrics where understandable;
- fluency summary metrics;
- pronunciation summary evidence;
- ability to play the relevant response while reviewing evidence.

Do not expose internal chain-of-thought or opaque model reasoning.

## 12. Dynamic UX and motion

Dynamic behavior is a product requirement, not optional final polish.

Use state-driven motion to make recording/timers/uploads/recovery understandable:

- smooth question enter/exit transition;
- animated but lightweight countdown/progress;
- live recording indicator and microphone level visualization;
- clear warning state near timer end without flashing;
- Part transition cards;
- Part 2 preparation -> 3/2/1 -> recording transition;
- `Saving...` / `Saved` state before advancing;
- recovery screen with explicit 7-second countdown;
- expandable review cards;
- live transcript and AI grading progress via durable status/events;
- criterion cards may appear progressively as results complete.

Motion principles:

- approximately 150–250ms UI transitions where appropriate;
- no parallax/particles or decorative motion that distracts during an exam;
- motion must never delay actual state/network transitions;
- respect `prefers-reduced-motion`;
- preserve keyboard/focus accessibility;
- keep layouts stable during timer/recording changes;
- honor existing dark/light/accent personalization;
- semantic error/warning/success colors are not replaced by arbitrary accent colors.

## 13. API/workflow shape

Exact route names follow repository conventions. Required capabilities include:

### 13.1 Builder/admin/teacher

- create/update/reorder/delete Speaking parts/prompts in mutable versions;
- validate Speaking module before publication/moderation;
- preview Speaking content without recording real exam data.

### 13.2 Attempt/runtime

- start Speaking attempt from allowed context;
- fetch current server-authoritative active prompt/phase/deadline;
- initialize/finalize response;
- upload idempotent audio chunks;
- recover active interrupted prompt;
- mark `Done / Next` or timeout completion;
- submit/finalize attempt.

### 13.3 Transcript

Conceptually:

```text
POST /speaking-attempts/{attempt_id}/transcript-runs
GET  /speaking-attempts/{attempt_id}/transcript-runs/{run_id}
GET  /speaking-attempts/{attempt_id}/transcript-runs/{run_id}/events
```

or equivalent reuse of a generic processing-run abstraction.

### 13.4 AI grading

Conceptually:

```text
POST /speaking-attempts/{attempt_id}/ai-grading-runs
GET  /speaking-ai-grading-runs/{run_id}
GET  /speaking-ai-grading-runs/{run_id}/events
POST /speaking-ai-grading-runs/{run_id}/stop
```

Authorization, retry/cache, event sequencing, and reconnect semantics should follow proven Writing patterns where suitable.

## 14. Full Mock, history, analytics, and classroom integration

Speaking must be integrated as a real skill, not left as a side route.

### 14.1 Full Mock

Full Mock progression becomes conceptually:

```text
Listening -> Reading -> Writing -> Speaking
```

Exact ordering/configuration should follow existing test-session architecture. Speaking child attempt/session provenance must remain linked to the parent Full Mock.

### 14.2 History

Attempt history supports:

- Speaking skill attempts;
- per-test grouping;
- Full Mock grouping;
- status and duration;
- transcript/AI result links where available;
- deletion/retention rules consistent with existing attempt ownership and media cleanup policy.

### 14.3 Classroom

Teacher-created/assigned Speaking content follows the existing ownership/moderation/version rules once Speaking is a supported module.

Assignment-originated Speaking attempts remain read-only teacher-visible only through existing assignment provenance/security boundaries. Do not grant teachers access to unrelated personal Speaking practice.

Raw audio access is sensitive content and must follow the same assignment provenance authorization, not merely `student_id + test_id`.

### 14.4 Analytics

Initial analytics may expose Speaking attempt/band history and criterion trends only after the grading contract is stable. Rich speech analytics are not required for the first engine phase.

## 15. Security, privacy, and retention

Audio is user-generated voice content and deserves stricter handling than ordinary text answers.

Requirements:

- authenticated authorized access to private audio/transcripts;
- storage paths/asset URLs must not be guessable authorization bypasses;
- avoid logging raw audio/transcripts in application logs;
- never send more audio/transcript to external providers than the configured grading/transcription workflow requires;
- document provider/data handling before enabling third-party cloud ASR;
- deleting an attempt should eventually clean up its owned audio/derived artifacts according to existing deletion semantics, unless policy requires preservation (for example classroom academic history);
- teacher review access must be provenance-based and read-only;
- raw audio remains source of truth; derived transcripts/features never overwrite it.

## 16. Concurrency and idempotency

The following must be safe under retries/double-clicks/reconnects:

- chunk upload by `(response, take, sequence)`;
- response finalization;
- timeout vs user `Done` race;
- practice retry/supersede;
- recovery grant creation;
- transcript job create/reuse;
- grading job create/reuse;
- SSE replay/reconnect;
- grading cancellation;
- transcript/grade cache invalidation after audio revision.

No duplicate chunk manifests, duplicate committed takes, duplicate active matching transcript jobs, or duplicate grading runs for the same exact fingerprint unless user explicitly forces a new supported run.

## 17. Error semantics

Use explicit domain errors, adapted to repository naming conventions, for equivalents of:

```text
SPEAKING_MODULE_INCOMPLETE
SPEAKING_PART_INVALID
SPEAKING_PROMPT_INVALID
MICROPHONE_REQUIRED
SPEAKING_RESPONSE_NOT_ACTIVE
SPEAKING_RESPONSE_ALREADY_COMPLETED
SPEAKING_RETRY_NOT_ALLOWED
SPEAKING_PREVIOUS_PROMPT_LOCKED
SPEAKING_CHUNK_SEQUENCE_CONFLICT
SPEAKING_RECOVERY_NOT_AVAILABLE
SPEAKING_AUDIO_UNASSESSABLE
TRANSCRIPT_ALREADY_CURRENT
TRANSCRIPT_GENERATION_FAILED
SPEAKING_AI_NOT_CONFIGURED
SPEAKING_AI_GRADING_FAILED
SPEAKING_AI_GRADING_CANCELLED
```

Do not expose raw provider exception text to end users.

## 18. Testing strategy

Implementation uses TDD in small phases.

### 18.1 Domain/Builder tests

- Speaking module/part/prompt serialization;
- ordering normalization;
- Part 2 cue-card validation;
- teacher/admin ownership and moderation integration;
- published version immutability.

### 18.2 Runner/state tests

- Part 1/3 `Done / Next`;
- timeout auto-advance;
- Part 2 preparation -> recording;
- practice listen/retry vs exam restrictions;
- committed previous prompt cannot reopen;
- server-authoritative timer calculations.

### 18.3 Chunk/recovery tests

- idempotent chunk upload;
- ordered reconstruction;
- crash with partial chunks;
- recover exact server-confirmed remaining-time snapshot;
- 7-second grace exactly once per valid interruption event;
- repeated reload cannot farm grace or rewind remaining time;
- finalization races.

### 18.4 Transcript tests

- per-response transcript persistence;
- read-only API/UI contract;
- clean transcript does not grammar-correct candidate text;
- matching audio fingerprint reuse;
- retry invalidates stale transcript;
- active transcript job is reused by `Grade with AI`.

### 18.5 Feature tests

- deterministic fluency metrics from synthetic/tiny fixtures;
- no hard mapping from a single metric to IELTS band;
- pronunciation provider boundary accepts audio evidence and does not accept transcript-only scoring as sufficient.

### 18.6 AI grading tests

- four independent criterion score-only calls/contracts;
- score output is tiny and half-band validated;
- feedback failure preserves valid score;
- score failure never invents/defaults a band;
- Pronunciation branch requires audio-derived evidence;
- whole-attempt scoring input includes all parts without averaging per-question scores;
- cache fingerprint changes when committed audio/model/rubric versions change;
- closing/reconnecting SSE does not cancel worker;
- explicit Stop does cancel according to contract.

### 18.7 UI tests

Focused component/state tests only where practical:

- microphone setup states;
- recording/timer status;
- practice-only retry controls;
- recovery countdown state;
- per-question transcript display;
- processing progress;
- `prefers-reduced-motion` behavior;
- localization and dark/light/accent compatibility.

Avoid browser/Playwright/E2E unless a later phase explicitly authorizes them. Existing project preference remains focused/cheap verification.

## 19. Rollout phases

Do not implement all of Speaking in one Codex task. Plan separate reviewable milestones:

### P1 — Domain + DB + Builder

- module/part/prompt schema;
- migrations;
- Builder CRUD/reorder/autosave/validation;
- teacher/admin/version governance integration;
- update stale repository scope docs/AGENTS.

### P2 — Runner + microphone + timers

- mic preflight;
- Part 1/2/3 runner;
- Done/Next and timeout;
- practice vs exam controls;
- dynamic state-driven UI.

### P3 — Chunk persistence + recovery + review

- chunk upload;
- durable responses/takes;
- 7-second recovery grace;
- audio playback review;
- history basics.

### P4 — Transcript pipeline

- audio normalization;
- ASR/alignment provider;
- transcript jobs/events;
- verbatim/clean per-question transcript;
- cache/invalidation.

### P5 — Fluency/acoustic feature pipeline

- deterministic fluency metrics;
- pronunciation/acoustic provider abstraction;
- quality gates;
- feature/evidence persistence.

### P6 — Hybrid IELTS AI Speaking scorer

- four criterion evidence builders;
- score-first contracts;
- feedback generation;
- durable grading runs/SSE;
- advisory review UI.

### P7 — Full Mock / history / classroom integration

- Full Mock child attempt integration;
- By Skill / By Test / By Mock history integration;
- classroom assignment/result provenance;
- permissions for audio/transcript review.

### P8 — Benchmark and calibration tooling

- human-labelled benchmark import format;
- offline evaluation;
- calibration/version comparison;
- model replacement experiments.

## 20. Evaluation and calibration

V1 can provide advisory descriptor-fit scoring, but reliability against human IELTS examiners is not proven by successful inference alone.

Before claiming human-level accuracy, build a labelled evaluation set and report per criterion and overall metrics such as:

- MAE/RMSE;
- Pearson/Spearman correlation;
- Quadratic Weighted Kappa;
- percentage within ±0.5 band;
- percentage within ±1.0 band;
- failure/nonscorable rate;
- subgroup checks across accent/L1/audio quality where ethically and statistically meaningful.

Public corpora such as Speak & Improve can help validate architecture/pretraining research but do not automatically provide IELTS-labelled ground truth. SpeechOcean/L2-ARCTIC are useful for pronunciation/accent research, not direct IELTS band calibration.

Benchmark fixtures must remain offline; implementation tests must not call live cloud ASR/LLMs/GPU unless explicitly requested.

## 21. Explicit v1 non-goals

- no adaptive AI examiner choosing new questions dynamically;
- no live conversational avatar/video examiner;
- no claim that 60 seconds per Part 1/3 question is an official IELTS fixed rule;
- no user editing of transcript before grading;
- no full merged transcript UI;
- no automatic grading immediately on submit;
- no direct mapping of SpeechOcean/GOPT score to IELTS Pronunciation band;
- no training/fine-tuning a production scorer before labelled-data/evaluation work;
- no per-question band averaging;
- no pronunciation score inferred from text alone;
- no rich organisation-wide Speaking analytics in the first engine milestone.

## 22. Acceptance criteria for the architecture

The implementation plan must preserve these invariants:

1. Speaking is a first-class test skill with three ordered parts.
2. Builder appends/reorders prompts using stable IDs + `order_index`.
3. Exam/current prompt is recorded with server-authoritative timing.
4. `Done / Next` commits before advancing; timeout auto-commits/advances.
5. Practice may retry current prompt; Exam/Full Mock may not replay/retry.
6. Crash recovery preserves prior chunks, restores the server-confirmed remaining-time snapshot, and gives one bounded 7-second reconnect grace before that remaining time resumes.
7. Raw audio lives in asset storage and remains source of truth.
8. Transcript is per-question, read-only, and cannot improve candidate grammar.
9. `Generate Transcript` and `Grade with AI` are separate actions; grading can reuse/generate transcript automatically.
10. AI grading is whole-attempt, four-criterion, score-first, and advisory.
11. Pronunciation requires audio-derived evidence.
12. Valid criterion score survives feedback failure; invalid score is never fabricated.
13. Durable jobs/events survive frontend reload and explicit Stop is the cancellation boundary.
14. Dynamic UI makes recording/timer/upload/recovery/AI progress understandable while respecting reduced motion/accessibility.
15. Full Mock/history/classroom integration uses existing provenance and authorization principles rather than creating parallel security models.
16. Human-examiner accuracy claims require a real labelled benchmark, not anecdotal examples.
