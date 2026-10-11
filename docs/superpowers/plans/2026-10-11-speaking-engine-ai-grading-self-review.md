# Speaking Implementation Plan — Self-Review Amendments

> **Binding companion to:** `docs/superpowers/plans/2026-10-11-speaking-engine-ai-grading.md`
>
> Implementation agents must read this file together with the approved design spec and the main implementation plan. These amendments resolve issues found during the required plan self-review; where wording conflicts, this file wins.

## 1. Fix the P4/P5 dependency: audio normalization belongs before ASR

The main plan currently types the P4 ASR contract as `SpeechASRProvider.transcribe(audio: NormalizedAudio)` while creating `normalize_committed_take(...) -> NormalizedAudio` later in P5. That ordering is invalid.

Amend the phase tasks as follows:

- **Task 9 (P4)** also creates the minimal `backend/app/services/speaking_audio.py` normalization boundary needed by transcription.
- Task 9 must assemble the committed ordered segment/chunk manifest and derive a bounded **16 kHz mono PCM/WAV `NormalizedAudio`** through FFmpeg (or a fake/mocked equivalent in unit tests) before calling ASR.
- Raw uploaded audio/chunks remain immutable source-of-truth artifacts; normalization creates a derived artifact/cache keyed by committed audio fingerprint + normalizer version.
- Task 9 tests must cover manifest ordering, normalizer invocation/path safety, cache identity, and ASR receiving normalized audio. Do not run a real FFmpeg/Whisper integration during routine verification.
- **Task 11 (P5)** no longer creates `speaking_audio.py` from scratch. It **extends** the P4 normalization service with the full quality-gate/readability metrics and creates `speaking_quality.py` as planned.

This preserves the intended rollout (`transcript` before richer acoustic/fluency analysis) without making P4 depend on a future P5 type.

## 2. Part 2 scratch notes are runtime-only and excluded from grading

Add this as a hard invariant to Tasks 4/5 and their tests:

- Part 2 preparation may expose a candidate scratchpad/notes field.
- Notes are attempt-runtime convenience data only; they are not authored test content.
- Notes must never be appended to the ASR transcript, criterion evidence, LLM grading prompt, pronunciation evidence, or final AI result.
- If notes are persisted for crash recovery, scope them to the attempt/current Part 2 prompt, authorize them like private attempt data, and do not expose them to grading-provider inputs.
- Exam/Full Mock recovery may restore the scratchpad, but it does not alter the 7-second recovery or speaking-time semantics.

Add a focused backend/frontend test proving a distinctive scratch-note string cannot appear in transcript/grading input built from the same attempt.

## 3. Make response-finalization races explicit

Task 4/7 tests must include the spec-required race cases, not only the happy paths:

- `Done / Next` racing the authoritative timeout commits **one** final response state.
- duplicate finalize requests are idempotent and do not create duplicate takes/chunks or advance two prompts.
- practice Retry racing finalization cannot supersede a response after it becomes committed/locked.
- recovery cannot reopen a response finalized concurrently on another request.

Use database transaction/locking/idempotency patterns already used elsewhere in the repository; never resolve these races only in frontend state.

## 4. Attempt deletion/retention must include private speech artifacts

Strengthen Tasks 6 and 17:

- Personal attempt deletion must clean up or queue cleanup for owned raw Speaking chunks/segments, assembled/normalized derived audio, transcripts, feature artifacts, and Speaking AI run artifacts according to the repository's existing deletion semantics.
- Do not leave guessable orphaned media after the database authorization row is deleted.
- If an assignment/classroom academic-history policy prevents deletion of an assignment-originated attempt, preserve the attempt and its required speech artifacts consistently rather than deleting media underneath retained history.
- Cleanup must be scoped by ownership/reference; never delete a storage object still referenced by a retained attempt/artifact.

Add focused tests to the existing attempt-deletion/history targets for: personal Speaking deletion cleanup, assignment-history preservation, and no unauthorized cross-attempt cleanup.

## 5. Security/error contract remains explicit across the new providers

During Tasks 6, 9, 11, and 14:

- never log raw audio bytes, transcript bodies, candidate scratch notes, provider request bodies, or arbitrary provider exception text;
- private storage keys/URLs are not authorization tokens;
- cloud ASR/pronunciation providers stay disabled until their data-handling configuration is documented;
- map failures to the approved domain semantics (`SPEAKING_CHUNK_SEQUENCE_CONFLICT`, `SPEAKING_RECOVERY_NOT_AVAILABLE`, `SPEAKING_AUDIO_UNASSESSABLE`, transcript-generation and AI-grading failure/cancel codes) rather than leaking backend/provider errors.

## Self-review result

With the amendments above, the plan's dependency order is coherent:

```text
P1 authored content
 -> P2 attempt/recorder state
 -> P3 durable private media + recovery
 -> P4 normalized audio + transcript
 -> P5 quality/fluency/pronunciation evidence
 -> P6 score-first AI grading
 -> P7 product integration
 -> P8 benchmark/calibration
```

The approved design's five highest-risk areas now have explicit test ownership: segmented media idempotency, recovery anti-time-farming/finalization races, private media lifecycle authorization/cleanup, nonscorable ASR/audio failures, and durable transcript/AI workers that outlive frontend observers.
