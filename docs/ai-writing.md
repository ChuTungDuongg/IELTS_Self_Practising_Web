# BandPilot advisory AI Academic Writing

The standalone ADMIN [Writing benchmark bank](writing-benchmark-bank.md) stores
human ground truth only and exports JSONL/images/CSV for offline Task 1/Task 2
evaluation. Task 2 reuses production MTS scoring and shared score metrics. Reports
remain in CLI/Colab output; labels never enter inference and no scoring prompts,
calibration or provider defaults are changed by the bank.

Task 1 and Task 2 share the configured `mistralai/Ministral-3-8B-Instruct-2512`
model, provider adapters and existing Modal/vLLM GPU function. Task 2 retains
its text-only pipeline with the `mts-task2-v12` cache contract. Task 1
uses `mts-task1-scoring-v12`, composite `mts-task1-visual-v12`, and the unchanged
`mts-task1-visual-v3` perception contract. See
[the latency engineering case study](enhance_latency.md) for bounded concurrent
execution, serving settings, measurements and reproduction.

## Conservative task relevance (v8)

A shared text-only auxiliary classifier returns `ON_TOPIC`, `PARTIALLY_RELEVANT`
or `WHOLLY_UNRELATED`, confidence `HIGH`/`MEDIUM`/`LOW`, up to four stable essay
source IDs and a concise Vietnamese reason. The backend resolves exact essay
quotes. Only **WHOLLY_UNRELATED + HIGH** skips TA/TR evidence, scoring and feedback and
constructs a valid TA/TR **1.0** result explaining the Band 1 descriptor. CC,
LR and GRA still run independently; the existing equal-weight aggregate is unchanged.

On-topic, partial and uncertain verdicts follow normal TA/TR scoring. Weak language,
missing an overview, inaccurate numbers/trends, omissions or discussing only one
view are insufficient for wholly-unrelated classification when a meaningful task
connection remains. Ambiguity favours partial relevance. This does not detect
plagiarism, memorisation, cheating or authorship.

Task 2 starts relevance alongside linguistic criteria; only TR waits for the
decision. Task 1 first completes primary visual grounding, then reuses compact
structured context (labels/relationships/categories, without chart point/cell
values) in text-only relevance. No additional image call is made for relevance.
After a short-circuit, primary grounding metadata is retained and **claims,
verification, facts, optional DePlot, TA evidence, TA scoring and TA feedback never start**.
Otherwise the post-gate specialist/facts and claims paths may overlap before TA.
Linguistic criteria remain independent of both dependencies. UNUSABLE grounding
preserves TA's existing failure and linguistic progress; it never causes a text-only
Band 1 decision. Chart, table, map, process, system and other visual families remain supported.

Relevance uses the run-local bounded provider, a **768-token** cap and a 30-second
per-call timeout. Invalid JSON/schema/source IDs or non-stop finish reasons permit
one repair, never a third attempt. Timeout/provider/auxiliary failures fail open
and cannot fail a scoreable run. Diagnostics retain fixed reasons, safe field types,
usage and timings, without raw content or exception bodies. Evidence, score-only
and feedback use the bounded stage budgets below; finish validation stays strict. A normal healthy assessment adds one text call; a relevance repair
adds at most one more. Healthy short-circuits use ten LLM calls for Task 2 and eleven
for Task 1, including primary grounding and all nine linguistic calls. No live-model
accuracy or speed claim follows from scripted tests.

Optional `relevance` metadata is stored in the existing run result JSON and exposed
in full/partial DTOs. Durable `relevance.started`, `.completed`, `.failed` events
replay through SSE; auxiliary failure continues normal assessment. Historic runs
without relevance still parse. Effective Task 2 v12 includes old deployed version
labels through v11, so prior cached results stay readable without being reused.
Task 1 v12 fingerprints invalidate earlier scoring caches while retaining perception
v3 and the v7 TA/CC guidance. Offline benchmarks use the current contract; frozen v3/v5
retain their historical pre-gate combined-output contracts.
Task-tab cleanup still stops observation only; explicit Stop cancels grading.

## Personal focused Writing feedback

`writing_ai_practice_feedback` stores one explicit latest advisory snapshot per
`(user_id, attempt_id, writing_task_id)`: source AI run, four criterion score/feedback
pairs and creation/update timestamps. Migration `20261011_0023` follows
`20261010_0022`. PostgreSQL UPSERT converges concurrent saves onto the same row;
there is no snapshot history, DELETE endpoint or duplicate overall score.

Authenticated resource paths:

- `GET /api/v1/attempts/{attempt_id}/writing/{writing_task_id}/ai-practice-feedback`
  returns a snapshot or `null` if none was saved.
- `PUT` at the same path accepts **only** `{ "source_run_id": "UUID" }`. Extra
  fields are rejected. FastAPI validates the durable completed run through production
  result schemas and copies its four scores/feedback; browser-supplied scores are never used.

The attempt must belong to the caller, be standalone WRITING/FOCUSED_UNIT and select
that task. The source run must match the attempt/task/requester and contain a complete
validated result. Full-module/Full Mock, foreign attempts/tasks/runs, pending/running/failed
runs and malformed/incomplete results are rejected. Snapshot foreign keys cascade with
attempt/user removal. Human final grading follows attempt provenance: personal owners and ADMIN may save final criteria; classroom students cannot.

USER review exposes Save/Update only for focused Writing. The separately loaded card
shows four criterion scores, feedback, saved/update times and an advisory badge in
EN/VI. Regrading does not overwrite the card; another explicit save replaces it. An
unrelated source run shows its explanation alongside the independent linguistic scores.
Personal owners and ADMIN may copy AI criteria into the final form, edit and explicitly Save. Classroom teachers use the assignment-scoped form. Snapshot saves never modify `AttemptWritingScore`,
attempt band, History, Analytics or official Full Mock state.

Inline annotations belong to the source AI run's criterion results. The saved
practice snapshot retains its compatible score/text summary; saving it creates
no separate annotation columns or annotation history.

## Task 2: text-only assessment

This is the project's **multi-trait IELTS pipeline**, an
online adaptation rather than a faithful reproduction of an academic RMTS
experiment. Four independent criteria use the official IELTS descriptor
semantics: Task Response (`ta` for compatibility), Coherence and Cohesion,
Lexical Resource, and Grammatical Range and Accuracy. Each criterion now runs
**score-only → source evidence selection → structured feedback → public display**.
Task 1 retains its evidence → score-only → feedback flow. No other criterion's score is shared.
There is no default band, score offset, ceiling, error-count penalty, dataset
min-max scaling or outlier clipping. Whole-response descriptor fit remains the
scoring authority; generated assessments never steer Task 2 score inference.
Half-bands interpolate adjacent official whole-band profiles across
0–9, including low bands and supported Band 8/9 outcomes.

The Writing editor is a plain textarea. Its explicit Enter characters travel
unchanged through JSON submission, `AttemptWritingResponse.content` in PostgreSQL
and the scoring request; visual soft wrapping adds no newline. The former generic
segmenter treated only blank lines as paragraph boundaries, so essays using one
Enter per paragraph appeared as a single P1. Production Task 2 input now carries
internal textarea provenance: each explicit LF/CRLF/CR separates paragraphs,
with repeated empty lines ignored. The generic/Task 1 default still treats single
newlines as possible wrapped lines and blank lines as paragraph boundaries.
Nothing rewrites the student's lexical content, punctuation, spacing or database
response. Source IDs P1S1, P2S1, etc. resolve exact original slices and offsets;
repeated sentences remain independently addressable. All Task 2 inference stages
and relevance use the same source mapping.

After accepting the strict score, the auxiliary evidence request selects at most four stable
source IDs. Backend lookup resolves each ID to the exact original English slice;
the model never reproduces evidence quotations. Generated selector assessments
are replaced with neutral backend-resolved locations and do not enter score or
feedback prompts. Task 2 now parses a `RawTask2EvidenceSelection` envelope and
validates each choice independently. Explanatory assessment/focus strings are
locally bounded to the existing 320/160-character limits with the Unicode-safe
normalizer. Unknown source IDs, malformed items, blank assessments and duplicates
are omitted; at most four valid choices survive. Unknown IDs never become evidence.
If no usable choices remain, feedback receives an empty selection and the full essay.
No presentation excess or invalid individual choice causes an LLM retry.
Unrepresentable source quotes are omitted rather than clipped into invented wording.

Malformed top-level evidence JSON/schema or incomplete output still gets one
bounded repair. If the recoverable explanatory-output problem remains, Task 2
uses empty evidence and continues with its already-validated score. Evidence
quality therefore cannot block a valid Task 2 score. Auth, transport, timeout,
provider abort/error, cancellation and unexpected application/persistence failures
remain hard failures. Task 1 retains its original strict evidence contract.

The `CriterionBandScore` inference schema contains **only `score`**, for example
`{"score":6.5}`. The existing authoritative 0–9 half-band validator remains.
The score prompt contains only the question, full segmented essay and the
same criterion-specific official descriptor context. No generated evidence
assessment, strength, improvement or feedback is included. One invalid score gets one
score-only repair; a second invalid or truncated score fails the criterion.
There is no invented, inferred, default or replacement score. vLLM retains
temperature 0 and seed 0. Request IDs, timestamps and other trait scores never
enter semantic prompts; source and evidence ordering remains deterministic.

After score validation, a separate internal `RawTask2FeedbackDraft` request receives
the fixed band as immutable metadata, full essay, selected source IDs and
descriptor context. The score is not a target that feedback must rationalize:
there is no requirement to explain each half-band difference or find defects
below 9. Empty observations, limitations and improvements are valid; uncertain
claims must be omitted. This schema has no writable score or free-form summary.

The provider contract guides supported object shapes/enums while accepting raw
explanatory string lengths. Backend sanitizers validate items separately before
constructing a bounded `Task2FeedbackDraft`. At most four representative observations carry
`source_id`, `kind` (`STRENGTH`, `LIMITATION`,
`ERROR`, `OPTIONAL_REFINEMENT`), concise Vietnamese `observation`, confidence,
and optional exact `original_span`/`suggested_revision`. Observation/revision prose
is bounded to complete sentences of at most 240 characters, with no whole-response retry for length.
An oversized rewrite is omitted rather than clipped into a partial correction.
Unknown source IDs, malformed items, model-generated location prose, conflicting
Band claims, low-confidence observations, non-HIGH negative claims and unusable
optional rewrites are dropped individually. Remaining valid observations survive.
Complete prose is checked before bounding so forbidden claims cannot hide beyond
the display limit. The backend derives locations from validated source metadata.

GRA/LR ERROR claims still require an exact, non-blank source span. ERROR claims
with an invented supplied span and OPTIONAL_REFINEMENT rewrites depending on a
non-exact span are omitted. For STRENGTH/LIMITATION, an unusable optional span and
its dependent revision are removed; an otherwise valid source-linked observation
can survive. Original spans are never truncated or normalized into apparent
exactness. These checks establish source grounding, not proof that a linguistic
judgement is true.

Criterion-specific instructions require actual standard-English errors before
GRA reports a correction, including checking subjects, agreement, articles,
punctuation, copular constructions and gerund subjects. LR must not swap synonyms
merely for variety, reject accurate common/topic vocabulary or British/American
variants, or change meaning, register or collocation. CC accepts clear logical
progression without extra explicit linkers. Task Response does not require
research, studies, statistics, citations or named-country case studies: relevant
reasoning and plausible hypothetical examples may support an argument.

The backend retains the compatible public `CriterionResult` fields (`feedback`,
`strengths`, `improvements`, `evidence`) from accepted observations. It never
uses unvalidated selector assessments or a model-generated summary. Optional
rewrites use a backend-owned "Gợi ý tùy chọn: có thể diễn đạt…" template rather
than model-authored factual-error prose. Existing display limits remain one
summary of 800 characters, assembled from at most two whole observations, and
structured strengths/improvements of 240 characters each. All four accepted
observations remain in their structured lists even if they do not fit the summary.
A conflicting Band claim is dropped with its observation; an
injected top-level score field is a structural failure and receives bounded repair.
Feedback never alters the accepted numeric band.

Each stage has at most one correction. Actual completion caps are:

| Stage | Normal tokens | Length-repair tokens |
| --- | ---: | ---: |
| Evidence | 1800 | 2056 |
| Score-only | 128 | 256 |
| Feedback | 1200 | 1400 |

Other schema repairs keep the normal cap. Both adapters receive the same typed
stage options. vLLM's verified `CompletionContextExceeded` resubmission may lower
an explicit cap once without truncating input. Unsupported guided-schema string
constraints (`minLength`, `maxLength`, `pattern`, `format`) remain stripped. Guided
JSON therefore cannot guarantee display string lengths. Backend raw parsing,
item-local sanitization and bounded domain construction are authoritative; limits
are not increased and the score contract is not weakened. Prompts still request
concise descriptions, but presentation normalization never appends a repair prompt.
Feedback structural repairs append one compact correction, not the full guidance again.

If feedback still has invalid top-level JSON/schema, empty content, excessive
output or `finish_reason=length` after one repair, or local sanitization leaves no
usable observations, the criterion completes with its fixed valid score and
validated evidence. Its Vietnamese fallback says detailed
feedback is unavailable but the advisory criterion score is complete; strengths
and improvements are empty. Safe internal diagnostics distinguish `score` from
`feedback`, including `EVIDENCE_PRESENTATION_NORMALIZED`, `EVIDENCE_ITEM_DROPPED`,
`EVIDENCE_FALLBACK_USED`, `FEEDBACK_OBSERVATION_DROPPED`,
`FEEDBACK_FALLBACK_USED` and `FEEDBACK_PRESENTATION_NORMALIZED`. Diagnostics contain
only fixed reasons, safe field/index paths and types, never oversized provider text.
Intentionally empty valid drafts do not create validation errors or retries.
Auth, transport, timeout, cancellation,
explicit Stop and unexpected state/persistence failures remain hard failures.
Raw provider errors, essays, credentials, prompts and hidden reasoning are never
logged, persisted as diagnostics or streamed. Existing public SSE stages and
`CriterionResult` DTOs remain compatible. Score-stage public events are buffered
until auxiliary evidence is ready (possibly empty) to retain the existing public evidence/scoring order;
internal inference is score-first. A feedback failure cannot erase a
valid band through the recoverable-output path.

Task 2 now uses **`mts-task2-v12`**. Configured v1–v11 labels resolve to v12, and
custom labels are prefixed with v12 for cache identity. Existing v11 results remain
readable and are never reused for the new contract. Legacy combined-output
schemas/calibration helpers remain available for historical tooling, separate
from production score-only inference.

Fake-provider regressions verify reliability, isolation, schema validation and
request determinism. No local human-labelled scoring corpus was available, so
these checks do not establish improved human-examiner score agreement or real-model
feedback accuracy. No score calibration or official descriptor semantics change
is claimed, and no live-model accuracy claim is supported by fake-provider tests.
The AI score remains advisory. Descriptor guidance continues to use the
[official IELTS descriptors](https://ielts.org/cdn/ielts-guides/ielts-writing-band-descriptors.pdf)
(May 2023), as documented by the existing descriptor-fit checks.

Every criterion must be in 0–9 in steps of 0.5. FastAPI computes the Decimal
equal-weight mean and rounds it with the existing `round_to_half` helper:
`(6.5 + 6 + 7 + 6) / 4 = 6.375 → 6.5`. Both values are persisted only if all four
criteria succeed. Otherwise the run ends FAILED after attempting all criteria,
with successful results and individual failures preserved and no aggregate.
**AI Task 2 Overall** is advisory. It never updates `AttemptWritingScore`,
`Attempt.band_score`, official Writing, History or Analytics. An authorized personal owner or admin can copy
scores/feedback into the final form; explicit human Save is required. Classroom
teachers enter final criteria through the assignment form while consulting advisory results. The official Task 1 × 1 / Task 2 × 2 rule is unchanged.
Classroom students cannot use AI to gain final grading access. Speaking AI remains a separate feature.

## Shared concise feedback and inline annotations

Both tasks request zero to four useful observations per criterion, normally one
sentence of about 180 characters. High-confidence errors take priority over
recurring limitations and sparse optional refinements. There is no required
positive/negative balance, generic rubric lecture or exhaustive proofreading.
Long prose is kept only at complete sentence boundaries or omitted; summaries
never cut a word or thought, and exact spans/revisions are never clipped.

Each public criterion adds `annotations`, defaulting to `[]` for historical
results, and `feedback_status` (`PENDING`, `COMPLETED`, `UNAVAILABLE`), defaulting
to `COMPLETED` for historical DTOs. This separates an accepted band checkpoint
from finished feedback even when several criteria generate concurrently.
A `WritingAnnotation` carries a deterministic ID, criterion, kind,
source ID, original span, optional suggested revision, concise message,
confidence and an optional controlled category. ERROR requires HIGH confidence;
LOW never survives normalization. GRA owns grammar and punctuation; LR owns
spelling, word formation, word choice and collocation. Valid copular/gerund
constructions, common synonyms and accepted British/American variants are
conservatively protected. Location checks cannot prove every linguistic judgement.

The backend resolves a span inside its validated `SourceSegment`, requiring
exactly one occurrence in that source and verifying the absolute saved-essay
slice. Repeated phrases in different sources are disambiguated by source ID.
Ambiguous occurrences inside one source remain panel feedback without an inline
annotation. Public `start_offset`/`end_offset` are **UTF-16 code units into the
exact persisted essay string**, with an exclusive end. Internal source offsets
remain Python character indices. CRLF, whitespace and non-BMP characters are
preserved, so JavaScript `content.slice(start_offset, end_offset)` matches the
original span without fuzzy search or line-ending normalization.

The shared read-only `AnnotatedEssay` decorates GRA/LR only, with a restrained
error underline and a softer optional/limitation underline. Hover, keyboard focus
and tap expose the criterion, message and original → suggested revision; Escape
or Close dismisses the popover. Overlaps split into non-overlapping text segments
that can expose multiple suggestions while rendering essay text once. Semantic
styles support light/dark themes and reduced motion. Normal density is at most
four GRA plus four LR annotations; zero is valid. TA/CC stay in criterion panels.

After the accepted score checkpoint, durable `criterion.feedback.started` with
`stage=feedback` exposes `generating_feedback` activity before the provider call.
Only complete parsed and validated annotations produce individual
`criterion.feedback.annotation` events. `criterion.feedback.completed` carries
the final criterion block and `feedback_completed` activity, followed by existing
`criterion.completed`. These are semantic events, **not raw token streaming** or
partially parsed JSON. They use the existing sequence/replay storage; the client
deduplicates annotation IDs, shows live feedback and underlines, and reconciles
against the authoritative final snapshot. A selected/new run has its own state;
failed runs clear underlines while preserving accepted scores and the saved essay.

Annotations are advisory teaching evidence. Their count/severity never determines
a band, applies a hidden penalty or changes an accepted score. Official/manual
scores, Task 1 grounding, Task 2 relevance and provider settings remain unchanged.
Final annotations and events use existing JSONB storage; this redesign requires
no database migration and does not mutate historical results.

## Task 1: visual grounding before assessment

Task 1 also uses score-only inference followed by fixed-band feedback, with the
same stage budgets and recoverable feedback fallback as Task 2. Its current
composite version is **`mts-task1-visual-v12`** and scoring version is
**`mts-task1-scoring-v12`**; the visual contract remains **`mts-task1-visual-v3`**.
TA scoring retains the visual reference, deterministic facts and verified claims;
feedback selects validated claims and uses backend-owned factual display text.
Task 1 TA/CC calibration
and linguistic criterion boundaries remain intact. Frozen v3/v5 offline
benchmark services retain their original combined-output contracts and budgets.
Current benchmark configurations identify v12 accurately. Historical v7/v8
retain their combined-output prompts and budgets; report/result schemas remain readable.
The benchmark CLI defaults to `--scoring-version v12`; `both` compares frozen v5
with current v12. Frozen score-first v11 remains available explicitly, alongside v3/v5/v7/v8.
Historical report records still parse, but old versions are not reused
as a label for the new production candidate.

### Task 1 skeptical language feedback and adjacent-band calibration (v12)

Task 1 follows **candidate feedback → source/schema sanitization → skeptical LR/GRA
linguistic verification → public feedback/annotations**. The accepted score is already
fixed before verification; decisions cannot change it or trigger rescoring. Source
matching proves a quotation's location, not the truth of a language criticism.

Only sanitized LR/GRA ERROR or LIMITATION candidates trigger verification: one
batched call per affected criterion, at most four indexed decisions, 384 output
tokens and a 30-second timeout, with no auxiliary retry. TA/CC, empty candidates,
strengths and optional-only drafts add no verifier call. Independent linguistic
criteria retain the existing run-local provider concurrency limit.

The verifier assumes standard English is acceptable and rejects uncertain criticisms,
stylistic preferences and valid alternatives. ERROR requires a genuinely necessary
language correction; LIMITATION requires material or recurring evidence across the
essay. The strict decision contract contains no score, explanation or learner-visible
prose. Missing/duplicate/foreign decisions, inconsistent reasons, malformed output,
non-stop completion, timeout and provider failure omit all unverified negatives while
retaining safe strengths and the accepted band. Internal diagnostics record only
`LANGUAGE_FEEDBACK_VERIFICATION_UNAVAILABLE`; provider internals never reach the UI.

Only verified HIGH-confidence exact-span LR/GRA ERROR items may become inline
annotations. Verified material LIMITATION items stay in the criterion panel. Optional
stylistic rewrites are omitted from Task 1 public feedback, summaries, evidence and
Fix next; zero inline issues is a valid successful result. Task 2 keeps its existing
display and scoring semantics, and historical runs are not rewritten.

Task 1 scoring separately strengthens LR/GRA adjacent-band discrimination: Band 8
permits occasional slips, rewards precise natural vocabulary and mostly accurate,
task-appropriate structural range, and requires neither a thesaurus nor perfection.
CC accepts natural explicit markers and effective introduction/overview/year-detail
organisation; 6.5/7 are not compromise defaults. Language evidence represents the
whole response's quality instead of mining defects. TA guidance, visual grounding,
facts and claim verification remain intact. There are no score offsets, floors/caps,
error-count penalties or feedback-driven score adjustments. Fake-provider tests verify
these boundaries, without claiming measured live-model calibration improvement.

### Task 1 paragraph and feedback reliability (v10)

Both Writing tasks use the same plain `<textarea>`, revision autosave JSON `content`,
and `AttemptWritingResponse.content`. Explicit Enter is saved as a newline;
visual soft wrapping inserts none. Task 1 previously omitted the Task 2 internal
`paragraph_mode="textarea"` provenance and several consumers called the default
blank-line segmenter directly. Consequently four single-Enter paragraphs became P1.
Production Task 1 now carries textarea provenance, and relevance, evidence selection,
score context, structured feedback, claim extraction, verification and quote lookup
all use `request_sources(request)`. LF, CRLF and CR are accepted; blank rows do not
create empty paragraphs. Lexical content and original character offsets are unchanged;
repeated sentences have independent IDs. Generic requests without editor provenance
still treat single newlines as potential wrapped lines. Backend source metadata supplies
display locations, never model-authored paragraph/sentence labels.

The Task 1 semantic pipeline remains visual grounding/reconciliation and verified
facts/claims → criterion evidence → **score-only** → fixed score → structured feedback
→ conservative backend display. Independent linguistic criteria continue to overlap
visual grounding. Score fields, half-band validation, aggregation, retries and token
budgets are unchanged; feedback/improvement output never feeds back into scoring.
The official band profiles, adjacent-band guidance, weights and calibration thresholds
were not changed. Correct source structure and fact matching may affect a future score
through corrected input; this is not upward calibration or a promise of a higher band.

`RawTask1FeedbackDraft` is internal. Its observations carry a source ID, criterion
aspect, kind, confidence and optional exact span/revision/verified claim ID. There
is no writable score or free-form summary. `fixed_score` is immutable metadata,
not a target to rationalize; a band below 9 never requires a fabricated weakness.
Empty observation/improvement lists are valid. Unknown sources, malformed items,
non-HIGH negatives, non-exact GRA/LR errors, no-op rewrites and detectable criterion
leakage are dropped individually, leaving other valid items intact. Whole-JSON errors
get at most one repair; recoverable feedback failure preserves the accepted score.
Public `CriterionResult` adds the shared annotation default; Task 1 analysis DTOs
remain compatible. Selector assessments are not public factual feedback:
displayed evidence uses exact backend quotes and neutral backend locations.

For TA, `observation` must be null: the model chooses a verified claim rather than
writing chart numbers/trends. A strength requires SUPPORTED and a matching source.
A factual ERROR requires CONTRADICTED, an exact source span and existing deterministic
fact evidence. The backend renders fact labels, states, values or directions; arbitrary
provider-written factual prose is dropped, not rewritten into an unsupported generic
weakness. INSUFFICIENT_EVIDENCE never becomes a correction. Selected evidence and
claim extraction are not exhaustive, so they cannot establish that content is missing;
unverifiable omission advice is omitted, including an already-supported comparison.
This deliberately limits TA explanations to verifiable claims; it does not attempt
to prove every overview/selection judgement or every semantic absence.

CC feedback judges progression, grouping, real paragraphs and relationships; it does
not count linkers or demand connectors everywhere, and must not imply causation where
none is observed. LR rejects synonyms merely for variety and replacements of fixed
chart labels/necessary entity names. GRA stays with grammatical structures and
punctuation, requiring exact spans for ERROR; conceptual flow/linker advice belongs
outside GRA. Structured aspect checks and conservative detectable-prose guards enforce
these boundaries. Optional stylistic suggestions use the existing backend-owned
"Gợi ý tùy chọn" wording. Linguistic inference does not wait for visual grounding;
if visual labels are not available yet, proposed LR rewrites are conservatively
omitted rather than guessing whether they replace a fixed label. The guards cannot
mathematically prove every linguistic
judgement; uncertainty should produce fewer claims, not invented errors.

Single-series pies often store slice labels as point categories and the year in
`component.state`; the current perception prompt prefers one matrix component
with named slice series and snapshot/year categories. Both representations are
covered by regressions. Explicitly ordered matrices now retain the state interval
on stable facts as well, so an unchanged claim with its two years is addressable.
For separate single-series panels, the previous generic fact view searched for slice names
as series names, and could not compare separate year panels. The new deterministic
view uses slice labels as subjects and explicit states as categories, while retaining
point/rank facts under their original component IDs. Compatible pie pairs (explicit
four-digit years, same cohort title after removing the stated year, unit, series label,
slice-label set and axes) generate cross-year facts under stable pair identities.
Values, ranks, signed changes, directions, unchanged values and direct same-slice
cross-year comparisons are checkable. Claim extraction receives compact grounded
label/state identities, not new image interpretation or chart values to copy.
Unknown states, incompatible panels, null/unreliable points and ambiguous matches stay
INSUFFICIENT_EVIDENCE; existing reliability thresholds are unchanged. The structural
bug is reproduced with fictional fixtures, but the original 1/14 live run was not
available to establish that every insufficient verdict had this cause.

The paragraph/factual reliability work shipped in v10; v11 invalidates earlier
feedback caches while keeping that behavior and raw visual perception v3 unchanged.
Task 2 uses its separate v12 contract. Old persisted DTOs remain readable. Fake-provider regressions
prove contracts and deterministic grounding only, not live-model feedback accuracy
or improved agreement with human examiners. No live inference was used.


Only the backend loads the saved Task 1 image. It checks ownership, finalized
Writing/review eligibility, the exact frozen task/version, a non-empty response,
asset version/type, supported PNG/JPEG/WebP MIME and matching byte signature,
storage-root containment, file existence and byte size (at most the configured
upload limit, capped at 10 MiB). No remote image URL is accepted. The frontend
uses its existing prompt image; it never uploads another image for grading.

The normal run performs one image-plus-prompt perception call, followed by
text-only claim extraction and the shared evidence → score-only → feedback stages. The image
never reaches TA scoring, claim verification, CC, LR or GRA. Structurally invalid
grounding or claim extraction permits one bounded repair; harmless summary/note
length excess is clipped locally. A grounding repair is the only repeated image
call. There is no new serving flag, model, deployment or GPU allocation.

The shared provider contract represents string messages or typed text parts and
trusted image bytes. Both vLLM and the dormant OpenAI adapter serialize those
bytes to one OpenAI-compatible data URL inside the provider layer. Text-only
serialization remains unchanged. The format was checked against the pinned
[vLLM 0.13.0 multimodal client](https://github.com/vllm-project/vllm/blob/v0.13.0/examples/online_serving/openai_chat_completion_client_for_multimodal.py),
[vLLM multimodal documentation](https://docs.vllm.ai/en/v0.13.0/features/multimodal_inputs/)
and the [exact Ministral model card](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512).
Image text, prompt, essay, extracted claims and structured observations are
untrusted source data; system prompts explicitly prohibit following instructions
within them. No image bytes/base64, system prompt or hidden reasoning is persisted.

The typed `VisualReference` is a discriminated Pydantic union, mirrored by Zod:

| Existing task types | Family | Structured contents |
| --- | --- | --- |
| LINE_GRAPH, BAR_CHART, PIE_CHART, TABLE, MIXED_CHARTS | chart_table | Separate components/units, categories, series and uncertain numeric points; tables have headers/cells and pies support state labels without fake axes |
| PROCESS | process | Labelled stages, directed edges, boundaries, linear/cyclic/branched shape |
| MAP_PLAN | map | States/features, qualitative compass locations and additions/removals/replacements/relocations/expansions/unchanged features |
| OBJECT_SYSTEM_DIAGRAM | system | Components, connections/flows, inputs and outputs |
| OTHER_VISUAL | other | Conservative entities, relationships and major observations |

Labels, identifiers, relation endpoints, numbers, confidence and collection sizes
are validated; unknown/null numbers stay unknown. Backend-only Decimal arithmetic
derives values, extrema, start/end, signed absolute/percentage changes (no division
by zero), dense rankings/ties, rank changes, largest increases/decreases, stable
series, direction and crossovers between observed adjacent categories. Ordered
facts require an explicitly ordered axis. Unreliable/missing points never become
invented facts; extrema/rankings require sufficient complete observations. Facts
are bounded to 1,600 per run, and scoring context prioritizes aggregate facts
within a 120-fact limit while retaining the structured reference and claim verdicts.

Claim extraction reuses existing essay segmentation and stable source IDs. Backend
quote resolution takes exact original essay slices. Numeric assertions, comparisons,
rankings, process order, map changes and directed system relations use conservative
deterministic checks. Ambiguous/missing observations are `INSUFFICIENT_EVIDENCE`.
Claims without a structured check may use one bounded text-only semantic verification
call; failed verification leaves claims inconclusive. Verdicts are `SUPPORTED`,
`CONTRADICTED`, `INSUFFICIENT_EVIDENCE` or `NOT_APPLICABLE`, with brief Vietnamese
explanations. English source quotations remain unchanged.

Task Achievement uses that reference, deterministic facts and verdicts for holistic
assessment against original paraphrases of the
[official Academic Task 1 descriptors](https://ielts.org/cdn/ielts-guides/ielts-writing-band-descriptors.pdf)
(May 2023, PDF pages 2–4). There are no error-count penalties, score caps or a fifth
criterion. CC/LR/GRA receive only prompt/essay and their own source evidence,
without visual data or another criterion's score. Existing score normalization,
equal-weight Decimal mean and half-band rounding are reused.

Task 1 scoring v6 addresses conservative TA band compression through clearer
adjacent-descriptor discrimination, not score offsets or automatic generosity.
Band 6's attempted overview/adequate feature selection differs from Band 7's
clear overview, main patterns and clearly highlighted features. Band 7 permits
a few local omissions/lapses; Band 8 permits occasional ones when fulfilment is
sufficient and features are skilfully selected and illustrated. A permitted lapse
does not itself require the lower band, but genuinely absent essential qualities
or material content weaknesses still matter. Half-bands interpolate adjacent
descriptors; a secondary numerical slip and a wrong central trend have different
qualitative significance, never arithmetic penalties.

TA evidence selection represents overview, features, main comparisons, support
and material limitations rather than mining errors. Its four-source maximum and
source-ID contract remain intact.

Task 1 scoring v7 adds CC-specific adjacent-descriptor discrimination. Judge
whole-response progression, grouping/paragraphing and information relationships
before local devices or reference/substitution. Conventional visible connectors
can be natural; precise repeated entity names can avoid ambiguous comparisons.
Neither linker variety nor pronoun density determines a band. Band 6 needs
noticeable cohesion limitations; Band 7 allows minor local lapses, Band 8 has
easy-to-follow sequencing and well-managed cohesion, and exceptional Band 9 has
effortless progression and skilfully managed paragraphing. Half-bands interpolate
adjacent profiles, not uncertainty. Negative claims need an observable pattern
and an effect on flow; feedback need not invent improvements or meet a quota.
CC evidence represents paragraph progression, grouping, transitions, internal
sequence and actual cohesive behaviour, without band targets or connector mining.
These are descriptor-fit clarifications, never offsets, floors, caps or score bonuses.

At v7, TA prompt semantics, LR/GRA, Task 2, visual grounding/reconciliation v3,
output schemas and provider/model settings remained unchanged. The v7 composite fingerprint
prevents reuse of v6 or older scoring runs while preserving readable history.
The historical v5 prompt baseline remains frozen. The
[Task 1 benchmark](../benchmarks/writing_task1/README.md) compares that baseline
with current production prompts under the same provider/model and specialist
settings. Signed criterion bias, MAE and agreement on a labelled human-scored set
are needed to establish calibration improvement; synthetic contract tests do not prove it.

Task 1 TA now shares the 128-token score-only cap (256 for a length repair)
and the 1200-token feedback cap (1400 for a length repair). Larger grounded
inputs do not require larger score output. The provider can lower an explicit
cap to verified available context once, without removing visual/essay context.
Frozen offline baselines retain their 3072/4096 combined-output budgets.

`HIGH`/`MEDIUM` grounding supports normal factual comparison. `LOW` shows a visible
Vietnamese caution and allows only cautious TA judgment; deterministic numeric
contradictions are withheld. `UNUSABLE` or empty/failed grounding fails TA safely
while CC/LR/GRA continue. Claim-stage failure does not imply an essay error; TA can
continue from a usable reference, with a visible incomplete-verification notice.
Any failed criterion suppresses the overall score, preserves successful cards and
allows an explicit regrade.

Existing JSONB runs/events store typed Task 1 analysis alongside partial criteria;
no schema migration is necessary. SSE persists grounding started/completed/failed,
derived-facts completed, extraction/verification started/completed/failed, and the
existing criterion/run events. Snapshots and cursor replay restore confidence,
claim verdicts, partial cards and current activity. Heartbeats renew the lease and
cursor without producing visible progress.

Task 1 fingerprints add task type, image MIME and SHA-256 of actual image bytes to
prompt/essay/provider/model and the separate Task 1 prompt version. Changed image
bytes cannot reuse an old run; the worker rechecks inputs before inference. Stored
history remains readable even if the image later becomes unavailable. Task 2's
fingerprint inputs and historical parsing remain compatible.

The shared review panel now follows Task 1/2 selection, with TA/TR labels, live
visual stages, confidence notices, collapsed TA visual claim details, per-task
overall/chips, history and forced regrade. All explanatory text uses the existing
source-reference presentation helper; source IDs stay internal and exact quotations
stay selectable. Copying suggestions changes only authorized local manual form
state. Explicit human Save remains required: AI runs never write official criterion
scores, attempt band, History or Analytics. No combined AI Writing band is shown.
T1-B adds the optional DePlot cross-check described below. TinyChart, extra judge
VLMs, model voting and T1-C evaluation remain out of scope.

## Backend setup

From `backend/`:

```powershell
uv run alembic upgrade head
```

Configure the backend-only variables in `backend/.env` (see `.env.example`):

```dotenv
AI_WRITING_ENABLED=true
AI_WRITING_PROVIDER=vllm
AI_WRITING_VLLM_BASE_URL=https://YOUR-PROTECTED-ENDPOINT.modal.run/v1
AI_WRITING_VLLM_MODEL=mistralai/Ministral-3-8B-Instruct-2512
AI_WRITING_MODAL_KEY=<proxy token id>
AI_WRITING_MODAL_SECRET=<proxy token secret>
AI_WRITING_VLLM_API_KEY=
AI_WRITING_REQUEST_TIMEOUT_SECONDS=300
AI_WRITING_STARTUP_TIMEOUT_SECONDS=600
AI_WRITING_PROMPT_VERSION=mts-task2-v6
AI_WRITING_STALE_AFTER_SECONDS=90
```

Never put inference URLs or credentials in `NEXT_PUBLIC_*`. Only FastAPI calls
the provider. The optional vLLM bearer key is separate from Modal proxy auth;
the Modal deployment relies on required proxy authentication at the perimeter.
Disabled or missing configuration returns `AI_NOT_CONFIGURED` and keeps Writing
review usable. Restart FastAPI after configuration changes. Increment the prompt
version when changing rubric/prompt behavior so old cache entries stay distinct.
The base URL accepts either the endpoint origin or its `/v1` base; the transport
normalizes it once. Switching models also changes the grading fingerprint.

The OpenAI HTTP transport implements the same internal completion contract and
is dormant unless selected with a key. No OpenAI key is required for vLLM:

```dotenv
AI_WRITING_PROVIDER=openai
AI_WRITING_OPENAI_API_KEY=<backend-only key>
AI_WRITING_OPENAI_MODEL=gpt-5.6-luna
AI_WRITING_OPENAI_BASE_URL=https://api.openai.com/v1
```

The requested model name is preserved as a configurable placeholder; availability
must be checked for your account before enabling it. This transport uses Chat
Completions JSON mode with the same Pydantic validation/repair boundary. It omits
model-dependent temperature/seed options. It has been tested with fake HTTP
responses, not live OpenAI inference. See the [official API contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

## API and streaming

All endpoints use existing cookie/bearer authentication and strict attempt
ownership, including for administrators:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/attempts/{attempt_id}/writing/{task_id}/ai-grading-runs` | `{ "force": false }`; returns `run_id`, `cache_hit`, `existing_active` |
| GET | same path | Configured state and latest 20 runs for that Writing task |
| GET | `/api/v1/ai-writing-grading-runs/{run_id}` | Safe JSON snapshot and partial criterion results |
| GET | `/api/v1/ai-writing-grading-runs/{run_id}/events` | SSE replay/live events |

Only finalized Writing attempts with a non-empty saved Task 1/2 response from the
exact frozen version can start. Full Mock review restrictions also apply. Inputs
above 12,000 essay characters or 4,000 prompt characters are rejected rather than
silently truncated; the model may reject unusually token-dense smaller inputs.

A SHA-256 fingerprint covers the exact prompt, saved response, prompt version,
provider and model. Normal requests reuse a completed equivalent run or an active
equivalent run. PostgreSQL locks the attempt row during creation to serialize
duplicate requests across API processes. Explicit `force: true` always creates
a new run, preserving older completed assessments. The UI disables repeat clicks
while a request/run is active; it offers compact completed-run history.

An in-process worker owns fresh sessions for short transactions; it never borrows
the request session. Progress and events commit together, with unique monotonically
increasing `(run_id, sequence)` values. SSE sends named events with `id` sequence
numbers, honors `Last-Event-ID` and `?after=`, and disables caching/proxy buffering.
The frontend reconnects using its latest validated sequence and probes JSON through
the existing auth-refresh client. Duplicate replay events are ignored. Closing the
browser disconnects only the stream, not the worker.

Writing Task 1/2 tabs are view changes. Unmount retires the current EventSource,
clears reconnect timers and ignores late events/snapshots; it never posts `/cancel`
or aborts grading HTTP requests. On return, listing saved runs recovers the same
active run and persisted progress, or its completed result. Watching/replaying
events does not launch inference. SSE request cancellation unwinds only its poll
session; the worker is a separate `asyncio.create_task` held in the process registry.

Only confirmed **Dừng chấm** posts the cancellation endpoint. The backend commits
`AI_GRADING_CANCELLED` before cancelling the local worker; completed criteria stay
saved and later checkpoints/completion cannot rewrite the terminal run. Shutdown
and existing durable terminal-state checks are separate legitimate stop paths.
Cancellation propagates through criterion/perception work into the provider's
`httpx` stream, which closes immediately rather than draining unwanted inference.
Incomplete transfers remain failures, even if received bytes happen to form JSON.

The inspected local Modal SDK 1.5.3 HTTP proxy aborts its upstream connection on
`http.disconnect`. The same wrapper proxies both application SSE and vLLM HTTP;
an `_runtime/asgi.py` `ClientPayloadError`/`TransferEncodingError` traceback alone
does not identify which endpoint disconnected or prove grading was cancelled.
Such a traceback can accompany a proxy disconnect, including an intentional Stop;
its occurrence in the reported deployment was not reproduced with a live model.
Correlate timestamps with content-free worker logs (`source=explicit_user`,
`shutdown`, `terminal_state`) and provider cancellation logs (`operation=/models`
or `/chat/completions`). Timeout/transport failure codes are logged separately.
No exception is hidden, no incomplete completion is accepted, and no per-heartbeat
logging is added.

Provider requests remain `stream=false` for reliable structured JSON. Public
workflow events distinguish preparing, collecting evidence, validating evidence,
scoring, validating scores, generating feedback, feedback ready, retrying and terminal states. Events include
`evidence.request.started`, `evidence.validation.started`,
`criterion.scoring.validation.started`, `criterion.feedback.started`,
`criterion.feedback.annotation`, `criterion.feedback.completed` and `criterion.retrying`. Safe activity
with a stage timestamp is persisted in the existing run JSON metadata and
included in snapshots; no migration is needed. The vertical timeline reconstructs
from activity, progress and terminal status after refresh. Criterion cards appear
as soon as their individual completion event arrives; accepted bands appear at
feedback start, and validated annotation items/underlines appear before run completion.
Elapsed time is display-only,
with no estimated percentage, and subtle animation respects reduced motion.
Heartbeat events advance the replay cursor without invoking React UI callbacks.

Completed criteria commit before the next criterion starts. If LR or another
later operation fails, prior results remain visible/persisted, but no overall is
computed. Explicit Regrade starts all four criteria afresh and retains history.

A persisted heartbeat every 15 seconds renews `updated_at`. Reads/streams/new
requests mark expired leases FAILED after 90 seconds by default, emit `run.failed`,
retain partial progress and allow regrading after a process crash. Graceful shutdown
cancels workers and persists failure where the database is reachable. This MVP
does not guarantee execution across restarts; it guarantees recoverable state.

## Modal deployment

Run these commands from the repository root in an environment with Python 3.12+:

```powershell
uv tool install modal
modal setup
modal profile list
# Create backend-only proxy credentials; keep the output private:
modal workspace proxy-tokens create --json
# Copy the pair into backend/.env, then update the existing private Web Secret:
cd backend
uv run python ../scripts/modal_web_setup.py --snapshot <existing-snapshot>/database.dump
cd ..
# One temporary app: CPU Web + a separate protected GPU function:
modal serve deploy/modal/app.py
# Persistent app; stop its previous database writer first:
modal deploy deploy/modal/app.py
```

The full-stack entry point automatically resolves the GPU URL for FastAPI.
Configure the returned `Modal-Key` / `Modal-Secret` pair in the backend settings
above. For scoped workspaces, allow the token in the deployment's
environment (`modal workspace proxy-tokens allow --help`). No Modal credentials or
Hugging Face tokens belong in Git. Public model downloads require no repository
secret; if your workspace needs gated access, add a narrowly scoped Modal Secret
to the deployment instead of hard-coding a token.

For a local FastAPI client that intentionally runs outside the full-stack app,
the standalone entry point remains available:

```powershell
modal serve deploy/modal/writing_llm.py
# Or a stable, independent deployment:
modal deploy deploy/modal/writing_llm.py
```

Only this standalone workflow requires configuring the printed URL manually.
Use one model deployment for your application; the full-stack command includes
the same function rather than requiring a second standalone GPU deployment.
See [modal-web.md](modal-web.md) for database setup and web-only commands.

The application uses pinned `vllm/vllm-openai:v0.13.0`, a persistent model/cache
Volume, one L4, the model's published FP8 weights (`--dtype auto`), eager execution,
an 8,192-token model length, one concurrent sequence, and one image per prompt.
It keeps `min_containers=0` / a 60-second idle window. The
web endpoint has `requires_proxy_auth=True`. The model URL and tokens stay behind
FastAPI. Cold starts need time to download/cache weights and initialize the GPU.

L4 has 24 GB and Ada FP8 support. T4 lacks native FP8 support for this published
checkpoint. This is a conservative memory/capability choice for text and single
image input, not a throughput benchmark; recheck pricing as it changes.
Sources: [Modal supported GPUs](https://modal.com/docs/guide/gpu),
[Modal pricing](https://modal.com/pricing), [NVIDIA GPU memory](https://docs.nvidia.com/brev/reference/gpu-types),
[model serving guidance](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512),
[vLLM FP8 compatibility](https://docs.vllm.ai/en/v0.13.0/features/quantization/fp8/),
[Modal Ministral 3 example](https://modal.com/docs/examples/ministral3_inference),
[Modal proxy authentication](https://modal.com/docs/guide/webhook-proxy-auth).

One backend-side readiness request and one tiny text-only completion (proxy pair
in the ignored backend `.env` or current shell):

```powershell
cd backend
uv run python ../deploy/modal/smoke.py --base-url https://YOUR-PROTECTED-ENDPOINT.modal.run/v1
```

It sends `GET /v1/models`, verifies the exact served model, then sends one
16-token JSON-schema request through the same backend transport/auth as grading.
It prints only safe status/timing. Task 2 messages contain text only; vision
support is used by Task 1's separate grounding stage. This text smoke command
does not verify vision; Task 1 transport is covered with mocked completions.
No live multimodal smoke or real Task 1 grading was performed during T1-A.
Normal tests never contact Modal/OpenAI.
Stopping `modal serve` stops both functions in the temporary app. For a persistent
full-stack deployment, stop `ielts-practice-web`; for the standalone GPU workflow,
stop `ielts-writing-llm`. Volumes remain after stopping:

```powershell
modal app stop ielts-practice-web --yes
# Standalone GPU deployment only:
modal app stop ielts-writing-llm --yes
# Optional, destructive: deletes cached model weights after stopping the app.
modal volume delete ielts-writing-model-cache
# Revoke the deployment's proxy token when no longer needed:
modal workspace proxy-tokens delete <proxy-token-id>
```

Ministral 3 2512 is published under [Apache 2.0](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512).
Recheck the model's current license and dependencies before commercial deployment.

## PostgreSQL snapshots on Modal Volume

The local PostgreSQL database remains authoritative. To back up its current
contents to a private Modal Volume, from `backend/`:

```powershell
uv run python ../scripts/modal_database_snapshot.py --volume ielts-postgres-backups
```

This creates a consistent custom-format `pg_dump` using the existing backup
helpers, saves a local copy under ignored `backups/modal/`, creates the Volume
if needed, uploads the dump/manifest, downloads the dump and verifies SHA-256.
The manifest includes the Alembic revision. Snapshots are timestamped and never
overwrite older backups. They include database records, not external binary
assets or backend `.env` secrets. A Modal Volume stores snapshots; it does not
provide a live PostgreSQL server. Use the existing full backup tool if asset
restoration is also required.

```powershell
modal volume ls ielts-postgres-backups
modal volume get ielts-postgres-backups /<snapshot>/database.dump ./database.dump
# Restore only into an explicitly selected PostgreSQL target, then migrate it.
pg_restore --dbname=<target-database> --no-owner --no-acl ./database.dump
```

## Troubleshooting and focused verification

- **Not configured:** enable AI and supply the selected provider's URL/model and
  credentials; Modal needs both proxy token fields. Restart FastAPI.
- **Startup:** `provider.starting` is emitted before an authenticated models
  request; `provider.ready` is emitted only after the configured model is listed.
  Heartbeats continue during readiness. Default readiness budget is 600 seconds;
  normal inference stays at its existing 300-second budget.
- **150-second failure:** Modal can return HTTP 303 with a result-poll URL while
  the original request continues. The backend follows at most four same-origin,
  same-path Modal redirects as GET requests inside the original total budget.
  It never resubmits the completion POST or forwards credentials to another host.
  See [Modal's Web Function timeout contract](https://modal.com/docs/guide/webhook-timeouts).
- **Provider failures:** `AI_PROVIDER_UNREACHABLE`, `AI_PROVIDER_AUTH_FAILED`,
  `AI_PROVIDER_ENDPOINT_ERROR`, `AI_MODEL_UNAVAILABLE`,
  `AI_PROVIDER_STARTUP_TIMEOUT`, `AI_PROVIDER_TIMEOUT` and
  `AI_PROVIDER_BAD_RESPONSE` distinguish connectivity, credentials, path/model,
  startup, inference and invalid output. Check `modal app logs ielts-practice-web-dev`
  (or the deployed app name). Safe logs contain operation/code/status only.
  Failed rows and partial progress remain; Regrade creates a new retryable run.
- **Invalid assessment:** score-only remains strict with one targeted repair;
  a second invalid score emits/persists `criterion.failed`. Task 2 evidence and
  observations sanitize invalid items/presentation locally, without retrying the
  whole response. Structural/incomplete auxiliary output permits one repair,
  then empty evidence or safe feedback fallback preserves the valid score.
  Task 1 evidence remains strict. Real provider/application failures remain failures.
  Other criteria continue; the run becomes FAILED only if a criterion fails.
  Internal `usage_json.diagnostics` and safe log lines contain only stage,
  criterion, attempt, finish reason, allowlisted field/index paths and built-in
  Pydantic error types (never input, context or messages). Unknown extra-field
  names are masked as `<extra>` because names can contain untrusted content.
  Fixed reasons include `INVALID_JSON`, `SCHEMA_VALIDATION`,
  `INVALID_HALF_BAND`, `EVIDENCE_UNKNOWN_SOURCE_ID`, `EVIDENCE_SCHEMA_INVALID`,
  `SCORE_SCHEMA_INVALID`, `EVIDENCE_ITEM_TOO_LONG`,
  `TOO_MANY_EVIDENCE_ITEMS`, `PROVIDER_FINISH_LENGTH`, `EMPTY_MODEL_CONTENT`,
  `MALFORMED_COMPLETION_ENVELOPE` or `OUTPUT_TOO_LARGE`. These diagnostics are
  excluded from API/SSE. Optional metadata can produce non-fatal
  `CALIBRATION_DROPPED`, `CALIBRATION_SOURCE_DROPPED` or
  `CALIBRATION_METADATA_NORMALIZED` diagnostics, without retry or failure.
  `SCORE_CALIBRATION_INVALID` remains readable for historical v3 diagnostics only.
  Current feedback presentation limits yield `FEEDBACK_PRESENTATION_NORMALIZED`
  without another inference call; legacy combined-output tooling retains
  `SCORE_PRESENTATION_NORMALIZED`. Required semantic/structural failures still use bounded repair.
  Raw output, Pydantic input and prompts are not persisted.
  The failed criterion stops animating immediately even if JSON reconciliation
  is temporarily offline; later criteria still run. Snapshot `failures` preserves
  local failure states across reload/reconnect. Completed cards appear on each
  `criterion.completed`, before the full run finishes. Counts distinguish
  completed/failed/active criteria. Heartbeats never change visible progress.
- **Finish metadata:** safe logs/diagnostics distinguish stop, length, abort,
  error and other/missing/tool/filter reasons. vLLM 0.13's [engine contract](https://github.com/vllm-project/vllm/blob/v0.13.0/vllm/v1/engine/__init__.py)
  defines length as a token/context limit, abort as interrupted generation and
  error as an internal failure; these are not successful stop completions.
  Length is rejected even if the JSON happens to look complete, with one bounded
  repair. Unknown metadata is sanitised to `other`, never logged verbatim. The
  existing guided JSON-schema integration and temperature 0/seed 0 remain;
  current per-stage token budgets are listed above. Evidence assessments are at most 320 characters/two
  requested sentences; separate feedback is at most 800 characters, strengths and
  improvements preserve up to four accepted observations. Both tasks' internal observations are at most four,
  with 240-character descriptions; Task 2 scoring contains no generated evidence.
  No global token increase or GPU smoke job is required.
- **Interrupted run:** wait for the heartbeat lease to expire or revisit review;
  stale state becomes FAILED and Regrade is available.
- **Trace disconnected:** the client probes saved JSON and reconnects with its
  cursor. Check API cookie/CORS configuration and proxy SSE buffering.

```powershell
cd backend
uv run pytest tests/test_task2_best_effort.py tests/test_task2_grounded_feedback.py -q
uv run pytest tests/test_writing_score_first.py tests/test_writing_completion_budgets.py tests/test_vllm_context_budget.py tests/test_mts_descriptor_fit.py tests/test_writing_relevance.py -q
uv run pytest tests/test_mts_writing_v3.py tests/test_mts_writing_v4.py tests/test_mts_writing_v5.py tests/test_writing_ai.py tests/test_writing_concurrency.py tests/test_writing_ai_observer_lifecycle.py -q -m 'not integration'
uv run pytest tests/test_task1_calibration.py tests/test_writing_llm_providers.py tests/test_mts_writing_validation.py tests/test_writing_ai_output_normalization.py -q
# When a dedicated PostgreSQL test database is available, run the persisted-run checks:
uv run pytest tests/test_writing_ai.py tests/test_task1_writing_ai.py -q -m integration
cd ..
# Run Ruff against only changed Python files, including newly added ones.
$writingPythonPaths = @(git diff --name-only -- '*.py')
$writingPythonPaths += @(git ls-files --others --exclude-standard -- '*.py')
uv run --project backend ruff check $writingPythonPaths
git diff --check
```

These score-first checks use fake providers and synthetic fixtures. No browser,
Playwright, live model, deployment, server startup or broad E2E suite is required.

### Runtime investigation, 2026-10-08

The later failed run on Ministral 3 completed Task Response (7.5) and Coherence
and Cohesion (7.0). Its persisted usage records contain both LR evidence calls
(normal and repair), and events end after `criterion.started` for LR without
`criterion.evidence.completed` or LR scoring. This confirms failure in the LR
evidence JSON/schema/quote validation boundary, rather than scoring or the earlier
provider connectivity problem. The previous code collapsed validation errors and
stored no reason; it is impossible to distinguish quote mismatch from JSON/schema
failure retrospectively. No raw provider output was recovered or saved. The new
diagnostics make subsequent failures distinguishable. This update used fake
providers for verification; no additional real GPU inference was performed.

The inspected failed dev run used the previous 2410 model and stored
`PROVIDER_HTTP_ERROR` after 150 seconds, with no completed evidence or provider
usage. Its GPU endpoint was deployed, authenticated and processing the request;
the vLLM completion finished successfully after the backend had already failed.
The configured HTTP timeout was 300 seconds. The failure was classification of
Modal's 303 result-poll redirect, not missing configuration, bad credentials or
an application timeout set to 150 seconds. The old FAILED row remains unchanged.

The updated full-stack dev app was started with `modal serve deploy/modal/app.py`.
FastAPI's process environment was checked without printing secrets: enabled vLLM,
the exact unified model, the same app's protected `/v1` endpoint, both proxy fields,
300-second inference timeout and 600-second readiness timeout were all confirmed.
One real models request completed after 256.3 seconds, including initial container
startup and downloading the new weights. One tiny text-only JSON-schema completion
then passed in 4.4 seconds. vLLM reported FP8 weights using about 9.77 GiB, with
image profiling enabled. No real essay or image grading was sent. The temporary
dev app was stopped after validation; the existing production app was unchanged.

Fresh HTTP navigation through the same dev Web returned 307 to login without a
session and 200 for `/auth/me`, `/library`, `/history` and `/admin` with a valid
cookie. Current auth code was retained. Protected links still use Next's default
prefetch, and client router-cache behavior was not reproduced without a browser;
the earlier stale-prefetch hypothesis remains unconfirmed. Focused regressions
cover fresh cookie checks, validated login destinations, waiting for session
confirmation, roles and logout. No blanket prefetch/auth change was made.


## T1-B: optional chart perception cross-check

T1-A remains the primary general visual grounder. T1-B adds one independent
`google/deplot` image-to-table extraction only for LINE_GRAPH, BAR_CHART,
PIE_CHART, TABLE and MIXED_CHARTS. PROCESS, MAP_PLAN, OBJECT_SYSTEM_DIAGRAM and
OTHER_VISUAL retain T1-A; Task 2 stays text-only. No third judge model or repeated
image scoring is introduced. DePlot never receives the essay or assigns IELTS scores.

The [official model card](https://huggingface.co/google/deplot) identifies an
Apache-2.0 Pix2Struct checkpoint. We pin revision
`6e76d62430da16986be3426bae32301fb9115397`, Transformers **5.13.0**, PyTorch
**2.10.0**, Pillow **12.1.1**, SentencePiece **0.2.1** and FastAPI **0.135.1**.
The [direct Transformers API](https://huggingface.co/docs/transformers/v5.13.0/model_doc/deplot)
uses `AutoProcessor` and `Pix2StructForConditionalGeneration`, a PIL RGB image
and the fixed chart-to-table instruction. No deprecated pipeline or Google
research repository is installed. Outputs must finish within 512 generated tokens.

The backend-only `ChartDerenderingProvider` accepts trusted `ImagePart` bytes.
Its HTTP implementation submits once to the protected specialist service,
checks the reported model/revision, and bounds response bytes and time. Raw
linearized tables are parsed locally and never persisted or streamed. Parser
limits are 16,384 characters, 30 data rows, 30 value columns and 120 characters
per label. Cells use the existing finite bounded Decimal contract, explicit
VALUE/MISSING/UNPARSEABLE states and percentage units; ambiguous thousands
separators, exponent strings, code and arbitrary prose are not numbers.

Reconciliation normalizes labels with NFC, whitespace trimming/collapsing and
casefold. It accepts exact row/column or transposed correspondence, never fuzzy
semantic matches. Multi-pie regions align via the primary component state/title
and sector labels; no time axis is inferred. Mixed components and units stay
separate. A specialist cell cannot confirm two primary components. Unknown or
conflicting units are recorded as uncertainty.

Numeric comparison is exact Decimal equality, with **no tolerance**. Thus 48,
48.0 and 48% agree when percentage semantics are established. Independently
matching printed values, pie percentages and table cells may strengthen point
confidence; explicitly estimated continuous-chart values remain below the
existing exact-fact reliability threshold. One-source values retain their
original confidence; specialist-only cells do not fabricate new primary data.
Root LOW/UNUSABLE confidence is never promoted.

Disputed values become null with zero point confidence before `derive_facts()`.
Dependent exact facts and deterministic contradictions therefore cannot use them.
The primary summary is cleared of potentially stale numerical claims, and semantic
fallback is skipped for unstructured claims when disagreement exists. Other
supported facts remain usable. TA receives cautious grounded information, with
**no band penalty derived from disagreement counts**.

Specialist timeout, unavailability, malformed output or wrong model identity
falls back to the unchanged primary reference. Safe typed diagnostics contain
only model identity, bounded agreement/disagreement/unmatched/unknown counts and
allowlisted warnings. An unusable primary reference cannot be replaced by DePlot;
TA fails independently while CC/LR/GRA continue. Existing human grading remains
authoritative. Old persisted T1-A history remains readable through optional
`cross_check`; chart cache identity additionally includes enabled/provider/model,
pinned revision and parser/reconciliation contract version, alongside the visual
hash and scoring prompt version. Non-chart fingerprints omit specialist settings.

SSE stages are `chart_specialist.started`, `.completed`, `.failed` and
`chart_reconciliation.completed`, preceding existing facts/claims/criteria stages.
Snapshots persist safe diagnostics for replay. The UI describes chart confirmation,
uncertainty or graceful fallback in Vietnamese without raw tables/model internals.

Enable with backend-only `AI_WRITING_CHART_SPECIALIST_ENABLED=true` and a trusted
`AI_WRITING_DEPLOT_BASE_URL`; provider/model/revision defaults are in
`backend/.env.example`. Existing Modal proxy credentials protect both services.
The specialist is disabled by default and never required for language criteria.
The backend timeout defaults to 90 seconds (maximum 120), including cold-start
waiting. Deploy/cache/cost details and the measured smoke result are documented in
[Modal deployment](modal-web.md#optional-t1-b-chart-service). TinyChart remains a future comparison candidate; T1-C,
model voting and evaluation dashboards are not implemented.


## Human final Writing grading

AI remains advisory. Personal owners may manually self-assess or copy completed AI criteria into the final practice form, edit, then explicitly Save. Copying does not persist; annotations never enter score arithmetic. Classroom students see read-only teacher final results or “Waiting for teacher grading” (VI: “Đang chờ giáo viên chấm”). The exact classroom owner teacher may save/revise criteria through an assignment-scoped route; ADMIN retains authority.

Both standalone assignment IDs and parent Full Mock assignment IDs count as classroom provenance. Existing review locks and focused task-only band behavior remain. Review DTOs expose backend `grading` capabilities; mutation routes recheck them. See [teacher-classrooms.md](teacher-classrooms.md#human-final-subjective-grading) for the shared policy and routes. The existing focused AI practice snapshot is separate from human final grading.
