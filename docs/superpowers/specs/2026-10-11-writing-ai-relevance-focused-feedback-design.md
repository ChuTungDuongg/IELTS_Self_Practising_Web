# Writing AI relevance gate and focused-practice feedback snapshot

Date: 2026-10-11

Status: Approved direction, specification only

Repository inspected: `ChuTungDuongg/IELTS_Self_Practising_Web`

Baseline: `d152f3675fbf4a96c2e34d0831fcb45049ba0858` — `Improve Task 1 coherence and cohesion calibration`

This document defines two coordinated Writing-AI changes: an IELTS-compatible relevance gate for Task 1 and Task 2, and a user-owned advisory AI-feedback snapshot for focused Writing practice. It does not implement either change. Existing manual/official grading remains authoritative.

## 1. Goals

1. Detect responses that are wholly unrelated to the Writing task before spending the full TA/TR assessment path.
2. Preserve IELTS criterion independence: a wholly unrelated response receives Task Achievement/Task Response Band 1.0, while CC, LR and GRA continue to be assessed from the language actually written.
3. Fail open on uncertain or failed relevance classification so an uncertain gate can never incorrectly short-circuit a valid response.
4. Let a normal USER doing `FOCUSED_UNIT` Writing save one latest advisory AI snapshot per task containing the four AI criterion scores and criterion feedback.
5. Keep that personal snapshot completely separate from `AttemptWritingScore`, official Writing bands, official History/Analytics and the existing ADMIN copy-to-manual-form workflow.

## 2. Non-goals

- No `0/0/0/0` rule for off-topic writing.
- No new official IELTS score source and no USER permission to write manual/official Writing scores.
- No automatic copying of AI scores into `AttemptWritingScore`.
- No relevance-based penalties for CC, LR or GRA.
- No broad anti-cheating, plagiarism, memorisation or authorship detector.
- No new rule for responses of 20 words or fewer in this slice; that descriptor rule is independent of relevance gating.
- No model voting, second scoring judge, or broad calibration redesign.
- No automatic overwrite of a saved personal snapshot after regrading; replacement requires an explicit user save action.
- No snapshot history table and no delete UI in the first version.

## 3. Existing architecture that constrains the design

The current Task 2 service runs four independent evidence → scoring criterion paths through `MTSWritingScoringService`; a failure in one criterion suppresses the aggregate but preserves completed criterion results. Task 1 subclasses that service: CC/LR/GRA can run independently while TA waits for visual grounding, optional chart-specialist reconciliation, deterministic facts and claim verification.

`writing_ai_grading_runs` already owns immutable completed AI results, provider/model/prompt identity, input fingerprint, usage, diagnostics and event history. The worker persists partial criterion progress and completes the run only after all four criteria are present.

`WritingAIAssessment` already supports ADMIN-only `Chép gợi ý AI vào biểu mẫu`; `WritingReviewView.copyAISuggestions` copies AI scores and feedback into the local manual grading form, and the existing manual save API remains protected by `AdminUser`.

Focused practice is represented by persisted `Attempt.scope == FOCUSED_UNIT` plus `focused_writing_task_id`; `AttemptScopeGuard` already verifies the selected Writing task belongs to the focused attempt.

These existing boundaries are reused rather than bypassed.

## 4. Relevance contract

Add a small strict schema shared by Task 1 and Task 2 orchestration:

```text
RelevanceVerdict = ON_TOPIC | PARTIALLY_RELEVANT | WHOLLY_UNRELATED
RelevanceConfidence = HIGH | MEDIUM | LOW

WritingRelevanceAssessment
- verdict
- confidence
- source_ids: up to 4 stable essay segment IDs
- reason: concise Vietnamese explanation
```

The classifier is evidence-grounded: any returned `source_id` must resolve to the same stable `P#S#` segments already used by scoring. The backend resolves IDs; the model never needs to reproduce quotes.

Only this exact condition may short-circuit TA/TR:

```text
verdict == WHOLLY_UNRELATED
AND confidence == HIGH
```

`WHOLLY_UNRELATED + MEDIUM/LOW`, invalid JSON, unknown source IDs, provider failure, timeout, context failure or any validation failure is fail-open and continues through the existing normal TA/TR pipeline.

The persisted/public relevance status therefore distinguishes the classifier's raw result from whether a short-circuit was actually applied.

## 5. Relevance semantics and false-positive protection

`WHOLLY_UNRELATED` is reserved for responses whose communicated content does not address the assigned task at all. The gate must not use it merely because the response is weak, incomplete or inaccurate.

The following remain `ON_TOPIC` or `PARTIALLY_RELEVANT` and must continue normal scoring:

- Task 2 answers the topic but misses one instruction, discusses one side only, gives a weak/unclear position, develops ideas poorly, includes tangential detail or misunderstands part of the question.
- Task 1 attempts to describe the supplied visual but misses the overview, chooses weak key features, reports wrong numbers/trends, omits important comparisons, is short, poorly organised or linguistically weak.
- A response contains one or more off-topic paragraphs but still substantially addresses the assigned task.
- The classifier is uncertain whether apparent paraphrase or indirect discussion is relevant.

Examples of genuine `WHOLLY_UNRELATED` include a Task 1 CO2 chart answered with an essay about learning foreign languages, or a Task 2 recycling prompt answered entirely with an unrelated account of tourism.

The prompt must explicitly prefer `PARTIALLY_RELEVANT` over `WHOLLY_UNRELATED` when meaningful task connection remains or the evidence is ambiguous. It must not infer memorisation or cheating.

## 6. Task 2 orchestration

Task 2 can run relevance concurrently with CC/LR/GRA to avoid adding gate latency to linguistic feedback:

```text
prompt + essay
├─ relevance classification
├─ CC evidence → score
├─ LR evidence → score
└─ GRA evidence → score
```

If relevance does not meet the high-confidence short-circuit condition, run the existing TR (`ta`) evidence → scoring path unchanged.

If relevance is `WHOLLY_UNRELATED + HIGH`:

- do not issue TR evidence or TR scoring requests;
- create a deterministic `CriterionResult` for `ta` with score `1.0`;
- feedback states in Vietnamese that the response is wholly unrelated to the prompt and therefore fits the supplied official Task Response Band 1 profile;
- strengths/improvements stay criterion-pure and concise;
- evidence is resolved from the classifier's valid representative source IDs where available;
- emit normal criterion progress/completion events so the run remains a structurally complete four-criterion result;
- continue normal CC/LR/GRA and calculate advisory overall using the existing equal-weight aggregation.

This is descriptor application, not a numerical penalty or score cap. The existing Task 2 low-band prompt already states that wholly unrelated content fits Task Response Band 1 and that criteria are assessed independently.

## 7. Task 1 orchestration

Task 1 relevance needs visual-task context, but the first version must not add a second image/VLM call solely for relevance.

Use the existing primary visual grounding output as structured task context:

```text
image + prompt
  → existing primary visual grounding
  → structured VisualReference
  → text-only relevance classification(prompt + compact visual context + essay)
```

CC/LR/GRA remain independent and may continue concurrently.

If the relevance short-circuit is not applied, preserve the current Task 1 TA path exactly: optional specialist reconciliation, deterministic facts, claim extraction/verification, TA evidence and TA scoring.

If `WHOLLY_UNRELATED + HIGH` is confirmed after usable primary grounding:

- TA becomes deterministic Band `1.0` from the existing Task 1 Band 1 profile (`no relevant report content`);
- skip TA claim extraction, claim verification, deterministic fact derivation, optional DePlot/chart-specialist work, TA evidence and TA scoring;
- CC/LR/GRA continue normally;
- Task 1 visual grounding metadata remains available because it supplied the relevance task context;
- no false factual contradictions are created because the skipped path never compares irrelevant essay claims with chart facts.

If primary visual grounding is unusable, relevance cannot safely establish that an essay is wholly unrelated to the visual. Fail open to the existing Task 1 behavior; do not derive Band 1 solely from the text prompt if the task meaning materially depends on the image.

For non-chart Task 1 families, the same structured visual-reference approach applies.

## 8. Relevance provider behavior, repair and budgets

Create one bounded text-only structured-completion helper for relevance rather than embedding relevance logic into each criterion scorer. Reuse the existing provider abstraction, deterministic `temperature=0`/seed behavior and run-level concurrency limiter.

The relevance interaction must:

- treat prompt, essay and structured visual data as untrusted data;
- return only the strict relevance JSON contract;
- use a small dedicated output budget because the schema is tiny;
- get at most one targeted repair for malformed/invalid provider output;
- never turn a relevance failure into a run failure;
- record safe diagnostics/latency/usage without raw model content.

A repaired or failed classifier still follows the same high-confidence short-circuit rule. No third call is introduced.

## 9. Relevance persistence, events and cache identity

Extend the public/persisted AI run result with optional relevance metadata. Historical runs without the field remain readable.

Recommended result shape:

```text
relevance:
  verdict
  confidence
  reason
  evidence
  short_circuit_applied: boolean
```

Persist relevance in `result_json`, not in a new relational table. It belongs to one AI run and is immutable with that run.

Add relevance-specific activity/events only where they improve live progress clarity, for example `relevance.started`, `relevance.completed`, and `relevance.failed`; a failed event means fail-open, not a failed run. Do not overload `criterion.failed` for this auxiliary stage.

Because relevance can change the criterion execution path and result, its semantic prompt/contract must participate in AI cache identity. Bump Task 2 and Task 1 composite prompt/fingerprint versions when implementing this feature; do not change the unchanged Task 1 perception contract solely for the text relevance gate.

Historical completed runs keep their old versions and remain displayable.

## 10. Advisory overall for wholly unrelated responses

A high-confidence wholly unrelated response still produces all four criterion results:

```text
TA/TR = 1.0
CC    = normal assessment
LR    = normal assessment
GRA   = normal assessment
```

The existing equal-weight arithmetic computes the advisory task overall. No special aggregate override is added.

This value remains advisory AI output only. It never updates `AttemptWritingScore`, `Attempt.band_score`, official History or Analytics by itself.

## 11. Focused-practice personal feedback persistence

Add a new table/model dedicated to the USER's saved advisory snapshot, for example `writing_ai_practice_feedback`.

Required columns:

```text
id
user_id
attempt_id
writing_task_id
source_ai_run_id

ta_score
ta_feedback
cc_score
cc_feedback
lr_score
lr_feedback
gra_score
gra_feedback

created_at
updated_at
```

Use the same half-band constraints as AI criterion scores. Feedback uses bounded text columns or equivalent validated storage consistent with existing criterion feedback limits.

Database invariants:

- unique `(user_id, attempt_id, writing_task_id)` so there is one latest snapshot;
- `attempt_id` deletes cascade to the snapshot;
- `user_id` deletes cascade;
- `source_ai_run_id` references the source run and must not silently point to another attempt/task;
- `writing_task_id` remains a real Writing task.

Do not store a duplicated overall value; it is derivable from the four criterion scores if the UI wants to show an advisory task mean.

A second explicit save for the same user/attempt/task updates the existing row and `source_ai_run_id`; it does not append history.

## 12. Personal snapshot authorization

A normal authenticated USER may save/read a snapshot only when all of these are true:

1. the attempt belongs to that current user;
2. the attempt module is Writing;
3. `attempt.scope == FOCUSED_UNIT`;
4. `focused_writing_task_id == requested writing_task_id`;
5. the source AI run belongs to the same attempt and task;
6. the source AI run was requested by the same user and is `COMPLETED`;
7. the source run has a complete validated four-criterion result.

The frontend supplies only `source_run_id`. It never supplies criterion scores or feedback for persistence. The backend copies the validated completed run result into the snapshot so a user cannot forge advisory AI scores by modifying a request body.

Full-module Writing, Full Mock Writing, another user's attempt, another task, active/failed runs and malformed historical results are rejected.

ADMIN manual grading remains separate. The existing `PUT /attempts/{attempt_id}/writing-scores/{writing_task_id}` stays `AdminUser`-only and is not reused for personal snapshots.

## 13. Personal snapshot API

Keep the resource under the current Writing-AI route family:

```text
GET /attempts/{attempt_id}/writing/{writing_task_id}/ai-practice-feedback
PUT /attempts/{attempt_id}/writing/{writing_task_id}/ai-practice-feedback
```

`PUT` body:

```json
{"source_run_id":"<uuid>"}
```

The response contains source run ID, the four saved criterion score/feedback pairs and timestamps. GET returns a nullable envelope or a repo-consistent not-found response; implementation should choose one convention and use it consistently in the frontend. Prefer a nullable response if it avoids expected-error handling for the common 'not saved yet' state.

No DELETE endpoint is required in this version.

## 14. Review DTO integration

Do not merge personal advisory feedback into `WritingTaskScore`. That DTO represents the existing manual/official score and feedback semantics.

Either add an optional `ai_practice_feedback` field to the focused Writing review task DTO or let `WritingAIAssessment` load the dedicated resource. Prefer the dedicated Writing-AI API when it avoids expanding generic review contracts for non-focused attempts.

Whichever presentation path is selected, a missing snapshot must not affect review loading.

## 15. Frontend behavior

`WritingAIAssessment` receives enough attempt-scope and role context to choose the action explicitly.

ADMIN behavior remains:

```text
Chép gợi ý AI vào biểu mẫu
→ copy score + criterion feedback into local manual form
→ admin may edit
→ explicit Save Task N scores
→ official/manual score
```

USER focused behavior becomes:

```text
Lưu nhận xét AI vào bài luyện
→ PUT source_run_id
→ save latest personal snapshot
→ advisory only
```

After a saved snapshot exists, label the action `Cập nhật nhận xét AI đã lưu` when the displayed completed run differs from the stored source run. Regrading alone does not overwrite the saved snapshot.

Render a separate card such as `Nhận xét AI đã lưu` containing TA/TR, CC, LR and GRA score + feedback, source-run time/update time and a visible `Tham khảo · Không phải điểm chính thức` label.

A normal USER in a full-module/full-mock review gets neither ADMIN copy-to-form capability nor focused personal-save capability. Existing AI assessment viewing/regrading permissions remain otherwise unchanged.

If the source run contains a high-confidence wholly unrelated relevance result, the saved card can display the relevance explanation from the source run; relevance metadata is not duplicated into the snapshot table.

## 16. Error handling and concurrency

Personal snapshot upsert must be transactional. Concurrent duplicate saves converge on one unique row; no duplicate snapshot records are created.

If the requested source run finishes or changes state between frontend display and save, the backend rechecks the durable run row. Only a durable completed result can be copied.

Saving personal feedback never starts inference, never changes the source run, and never changes official scores.

Relevance failures are auxiliary fail-open failures. Scoring failures retain the existing criterion/run failure semantics after the gate decision.

Cancellation behavior remains unchanged: task-tab unmount only stops observation; the explicit Stop action cancels the backend run.

## 17. Prompt/versioning boundaries

Relevance semantics are a scoring-behavior change, so production cache versions must change when implemented.

Task 1:

- bump the composite Task 1 prompt/fingerprint version and scoring/relevance semantic version as appropriate;
- keep `TASK1_VISUAL_CONTRACT_VERSION = mts-task1-visual-v3` unchanged unless visual schema/perception instructions themselves are changed;
- preserve the existing v7 TA and CC calibration guidance.

Task 2:

- bump the effective Task 2 prompt contract so old cached runs without relevance cannot masquerade as new behavior;
- preserve criterion rubrics/scopes except for the minimum integration needed to expose the relevance short-circuit result.

Do not introduce score bonuses, penalties, offsets, floors or caps beyond the descriptor-defined deterministic Band 1 case for a high-confidence wholly unrelated response.

## 18. Testing strategy

Implementation must use focused TDD and cheap tests only; no browser, Playwright, live model, GPU, Modal or deployment runs are required for this feature.

Backend contract tests should cover at least:

1. Task 2 `ON_TOPIC` and `PARTIALLY_RELEVANT` preserve the existing four criterion pipeline.
2. `WHOLLY_UNRELATED + HIGH` skips TR evidence/scoring, produces TR 1.0 and still runs CC/LR/GRA.
3. `WHOLLY_UNRELATED + MEDIUM/LOW` fails open and runs normal TR.
4. malformed relevance, timeout/provider error, unknown evidence IDs and repair exhaustion fail open without failing the run.
5. Task 1 high-confidence wholly unrelated after usable grounding skips claims/facts/specialist/TA evidence/scoring but still returns TA 1.0 + normal CC/LR/GRA.
6. unusable Task 1 visual grounding does not short-circuit solely from textual relevance.
7. relevance metadata persists, replays and parses for current runs while historical runs without it remain valid.
8. cache/version fingerprint changes prevent reuse of pre-relevance completed runs.
9. USER focused own attempt can create and update exactly one personal snapshot.
10. USER full-module/full-mock, foreign attempt/task, mismatched run, active run and failed run cannot save a snapshot.
11. backend copies score/feedback from `result_json`; client-supplied forged criterion values are impossible by schema.
12. snapshot save/update does not mutate `AttemptWritingScore`, `Attempt.band_score`, History or Analytics official values.
13. attempt deletion cascades personal snapshot deletion.

Frontend tests should cover at least:

1. ADMIN still sees `Chép gợi ý AI vào biểu mẫu` and current copy behavior works.
2. USER focused sees `Lưu nhận xét AI vào bài luyện` after a completed run.
3. USER full-module/full-mock does not see the personal-save action.
4. saved snapshot card renders the four scores/feedback and advisory label.
5. a new regrade does not overwrite the saved card until explicit update.
6. relevance status for wholly unrelated writing is clearly explained without implying CC/LR/GRA are zero or the response is cheating.
7. historical runs without relevance metadata continue to render.

Run the smallest relevant pytest/Vitest files, TypeScript typecheck for changed frontend contracts, Ruff on changed Python, and `git diff --check`. Broader suites are unnecessary unless focused failures reveal a dependency.

## 19. Documentation and observability

Update `docs/ai-writing.md` with:

- relevance gate semantics and fail-open behavior;
- Task 1/Task 2 execution differences;
- Band 1 short-circuit rationale from the existing low-band descriptor profiles;
- criterion independence for CC/LR/GRA;
- personal focused-practice snapshot versus manual/official scoring;
- new version identifiers and operational call-budget implications.

Latency/usage reporting should expose the relevance stage distinctly enough to compare normal and short-circuited runs without storing prompt/essay/model output content.

## 20. Acceptance criteria

The change is complete when all of the following hold:

- A valid on-topic or partially relevant essay is never short-circuited by anything weaker than `WHOLLY_UNRELATED + HIGH`.
- Relevance-classifier failure cannot fail an otherwise scoreable run.
- A high-confidence wholly unrelated response produces TA/TR 1.0, normal CC/LR/GRA and a normal advisory aggregate; it never produces forced `0/0/0/0`.
- Task 1 avoids unnecessary post-grounding TA analysis on a confirmed wholly unrelated response.
- ADMIN manual grading/copy/save behavior is unchanged.
- A normal USER can explicitly save/update one latest AI score+feedback snapshot for their own focused Writing task.
- The personal snapshot cannot become or alter an official/manual score through this API.
- Regrading does not silently replace a saved snapshot.
- Historical AI runs and existing Writing attempts remain readable.
- No live inference, browser/E2E, deployment or unrelated feature changes are required to validate the implementation.
