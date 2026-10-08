# T1-C human anchor bank and Trait-wise Anchor Comparative Scoring

Status: architecture approved by the administrator on 2026-10-08, incorporating
the mandatory Hybrid TACS corrections and score/feedback reliability amendment.
Native implementation is underway on `codex/t1c-hybrid-tacs`.

Date: 2026-10-08. This document translates the administrator's supplied T1-C
requirements into the existing repository's interfaces. The supplied requirements
remain authoritative if this document omits a detail.

## Intent and starting state

Introduce private administrator-entered, human-labelled Writing responses as
reproducible reference data. Task 1 production scoring will use **Hybrid TACS**:
grounded Direct Task Achievement (TA), plus Trait-wise Anchor Comparative Scoring
(TACS) for CC/LR/GRA with criterion-local Direct Rubric fallback whenever
comparison cannot resolve a supported interval. This is an **LCES-inspired**
adaptation, not an exact reproduction of original LCES.

TA never queries a production anchor ladder or calls a pairwise comparator. Its
reference is the grounded visual itself. Human TA scores are retained for
evaluation and future research, and do not gate production readiness. Task 2
production retains its existing local MTS architecture.

Local HEAD and the read-only remote-main check both returned
`a4c3f3c245495d33d79f6bf6c25e0b0778492874`. The starting branch was `main`, with
no staged, modified, or untracked files. Existing Writing grounding, DePlot,
concurrency, completion-budget handling, authentication, and calibration code
already belong to that commit and must be preserved.

The repository already has `AdminUser`/`require_admin`, a protected Next.js admin
layout, SQLAlchemy models, Alembic, persisted advisory AI runs/events, and one
Task 1 benchmark framework. No new authentication subsystem is needed. The
explicit request authorizes AI scoring work under the root engineering rules.

## Implementation boundaries and alternatives

The recommended approach adds focused anchor persistence, a pure ladder/tree
domain module, separate Direct/comparison/feedback prompt builders, and a Task 1
service that reuses the existing perception orchestration. Existing MTS remains
available behind an explicit selector and in the benchmark.

Adding more calibration rules to MTS would retain the absolute-score instability
that motivated this phase. Building a second scoring/evaluation stack would
duplicate grounding and worker behavior. Both alternatives conflict with the
supplied direction and are excluded.

One connected delivery contains four testable parts: the anchor bank, the admin
workspace, the scorer/worker cutover, and benchmark/documentation updates. These
parts have explicit interfaces below; no unrelated refactor is included.

## Persistence and lifecycle

Add `WritingAnchorSet` and `WritingHumanAnchor` models, registered through
`backend/app/models/__init__.py`, and a new migration after the current Alembic
head. The migration must introduce empty tables and preserve existing records.

An anchor set stores UUID, name, monotonically increasing version, status
(`DRAFT`, `ACTIVE`, `RETIRED`), creator, creation/update timestamps, activation
timestamp, and retirement timestamp. One global active snapshot contains both
Task 1 and Task 2 banks. Permit at most one active set and one editable draft;
use PostgreSQL partial unique indexes and serialized lifecycle transactions to
avoid concurrent creation/activation races.

An anchor stores UUID, owning set, exact Writing task UUID, four Decimal scores,
full response text, creator/timestamps, and optional note/provenance. Task number,
task type, and frozen TestVersion identity are derived through
`WritingTask -> TestModule -> TestVersion` for query/DTO purposes, avoiding
independently editable duplicate identity fields. Do not store an independent
overall label or require feedback. Compute word count for list/detail DTOs.

Use `validate_writing_criterion_score` from
`backend/app/domains/scoring/writing.py` for all four labels. Valid scores span
0.0–9.0 in 0.5 increments; PostgreSQL checks provide the corresponding persistence
guard. Reject non-finite scores. Preserve essay paragraphs and original text.

Task selection and create/update validation accept only genuine frozen Writing
tasks: currently published versions, and archived versions that were previously
published (`published_at` present). Mutable drafts are excluded. Task identity
and module ownership are verified server-side. Anchors restrict task deletion so
historical reference content remains available.

Create an initial draft when none exists. To revise an active bank, clone all its
anchors into the next draft in one transaction. Draft anchors may be added,
edited, or deleted. Activation freezes the draft and retires the prior active
snapshot atomically. Empty/sparse drafts may be activated; coverage advice never
blocks saving or activation. Retired snapshots stay immutable and queryable by
historical runs. There is no production seed or automatic anchor generation.

Enforce immutability in services and PostgreSQL guards for anchor mutations and
published set content, allowing only the controlled ACTIVE-to-RETIRED lifecycle
transition. Serialize anchor writes with activation by locking their owning set.
Retain creator identity without a user-deletion cascade that erases frozen data.

## Repository, service, and API contracts

New focused modules:

- `backend/app/models/writing_anchors.py`: persistence entities.
- `backend/app/schemas/writing_anchors.py`: admin inputs, lists, details, frozen
  task options, coverage, and internal immutable snapshot DTOs.
- `backend/app/repositories/writing_anchors.py`: set/task/anchor queries and locks.
- `backend/app/services/writing_anchors.py`: lifecycle, validation, coverage,
  task-specific and task-number-specific snapshot queries.
- `backend/app/api/v1/writing_anchors.py`: admin-only endpoints, registered in
  the existing v1 router.

Use `/api/v1/admin/writing-anchors` as the API prefix. Provide set listing,
initial/next-draft creation, activation, frozen-task search, paginated filtered
anchor listing, detail, draft create/update/delete, and active coverage. Follow
existing `AppError`, transaction, pagination, and HTTP-client conventions.

Every endpoint, including read-only task/coverage/detail routes, depends on
`AdminUser`. Tests require 401 unauthenticated, 403 normal user, and successful
admin access. No learner endpoint returns anchor essays or labels.

The scoring query boundary returns one immutable snapshot for an explicit set
ID/version. Production Task 1 queries only CC/LR/GRA, filtered by task number 1.
Research queries may filter TA/TR by exact task UUID, but are not called by the
production TA branch. All anchor retrieval lives in this repository/service
boundary. Task 1 and Task 2 language banks must never be mixed.

## Coverage and administration UI

Add `/admin/writing-anchors`, a link from the dashboard and administrator
navigation, and a typed Zod-validated HTTP client. Reuse the existing admin layout
and theme variables. Read the installed Next.js routing guidance before writing
route code, as required by `frontend/AGENTS.md`.

The workspace offers a set/version selector, status, initial/next-draft action,
activation action, search/filter controls, compact list, and detail/editor. The
task picker searches real tasks and shows test title, version, Task 1/2, task
type, and prompt preview. The response textarea preserves paragraphs. Four score
inputs show TA for Task 1 and TR for Task 2, followed by CC/LR/GRA. Only draft
anchors show mutation controls. No feedback field or manually typed task UUID.

Lists show task identity/type, word count, four labels, set/version/status, and
creation date; full essays appear only in detail/editor. Use visible loading,
empty, forbidden, validation, conflict, and request-failure states. Do not
silently retain stale coverage after activation.

Coverage uses active data, with an explicit production/research split. The
production Task 1 matrix shows CC/LR/GRA band counts and contiguous ladders.
Separate research sections show Task 1 TA labels grouped by frozen task, and
Task 2 TR/CC/LR/GRA coverage for evaluation/future TACS. Include half-band label
counts in details while only whole bands form ladders. Show EMPTY, PARTIAL,
PAIRWISE_USABLE, or RECOMMENDED_COVERAGE in text, alongside the usable ladder.
RECOMMENDED_COVERAGE means at least three anchors per band at 5/6/7/8/9; show pilot
progress separately. Task 1 production readiness depends only on CC/LR/GRA.
Missing TA labels and any Task 2 coverage never block that readiness. Research
coverage is not represented as evidence of a current production cutover.
Readiness is not conveyed only through colour.

Operational guidance: one anchor at two adjacent whole bands is the technical
minimum; a language pilot aims for two per band at 6/7/8; a mature bank aims for
about three per band at 5–9, with extra central density. TA/TR distributions are
research/evaluation information without a production ladder requirement. The practical
initial target is about 20–30 carefully human-labelled Task 1 responses, with a
similar Task 2 bank later. These are recommendations, not IELTS rules or
statistical guarantees. One Task 1 response contributes three production
pairwise labels (CC/LR/GRA) and one TA evaluation label.

An informational cost note states two model comparisons per node and at most
four pairwise calls per language criterion under the default two-node budget:
at most twelve across CC/LR/GRA before Direct fallbacks, with TA excluded. If all
three traits are comparable at their first pivot, there are six pairwise calls.
These are theoretical request counts, not measured latency/currency claims.
Layout must remain usable on narrow screens and compatible with existing dark mode.

## Pure ladder and decision-tree domain

Add a focused scoring module that consumes immutable anchor data and returns a
deterministic language-criterion result plus private diagnostic metadata.
Its production trait type is restricted to CC/LR/GRA; TA is outside this module.

Partition eligible anchors by whole criterion band; valid half-band labels stay
in the bank but are not automatically rounded into whole-band pivots. Find
contiguous runs and require at least two adjacent whole bands. Choose the widest
run; break ties by overlap with 6–8, then proximity to 7, then stable band order.
Sparse 6/8 coverage is unusable.

Use band 7 as the first pivot when available; otherwise use the lower median.
Subsequent pivots use the lower median of remaining candidate bands. This yields
7 then 8 for the supplied five-band example. Maintain lower bound, upper bound,
remaining candidates, and visited bands. Bounds arise only from actual
comparisons, never from assuming the target lies inside the ladder.

Select one representative per visited band using a cryptographic hash of target
fingerprint, criterion, band, and set identity/version, over anchors sorted by a
stable identity. Never use Python's randomized hash or query every same-band
essay. Record the selected anchor internally for reproducibility.

At every visited node schedule exactly two comparator requests through the
shared bounded provider: target/anchor, then anchor/target. Results are assembled
in that logical order even if calls overlap. Do not add comparator repairs,
third votes, second-anchor tie breaking, or hidden extra pairwise requests.

Normalize RESPONSE_1_BETTER/RESPONSE_2_BETTER into TARGET_BETTER/ANCHOR_BETTER
according to ordering. Only strict normalized agreement is accepted; any mix,
including comparable-versus-better, immediately returns POSITION_CONFLICT.

Comparable returns the pivot's Decimal band. Target-better raises the lower
bound; anchor-better lowers the upper bound. Adjacent established whole bounds
return their Decimal midpoint. Exhausting the ladder without a supported bracket
returns OUT_OF_RANGE, with no clamping or invented half-band. If another node is
needed after the configured budget, return BUDGET_EXHAUSTED. Default budget is
two, with validated configurable values 1–3 for benchmark comparison.

## Prompt boundary and Direct/feedback strategy

Pairwise output is exactly `{preference: RESPONSE_1_BETTER |
RESPONSE_2_BETTER | COMPARABLE}` with extra fields forbidden. It contains no
numeric band, rationale, chain of thought, or learner feedback.

Prompt builders accept only rubric/criterion semantics, appropriate task
contexts, and two response strings. They do not accept an anchor object, label,
set version, status, provenance, note, or trusted-anchor designation. This
structural boundary is tested at actual provider-message construction. Numeric
content legitimately present in a task/essay is not removed or mistaken for
score leakage. Treat both responses as untrusted content.

CC/LR/GRA comparisons remain text-only, with each response's appropriate task
context where needed. Neither images nor TA visual/claim analysis enter these
comparators. Production TA never compares the target against an anchor.

A0 Direct scores one criterion against the whole response and faithful rubric,
with grounded context for Task 1 TA. It returns the existing score/Vietnamese
feedback/strengths/improvements contract and an empty evidence list, avoiding
the MTS evidence-selection call. Normal cost is one scoring call per criterion;
existing bounded completion/output safety must remain effective and its actual
correction calls must be counted.

A3 Hybrid TACS always uses grounded Direct for TA, recording GROUNDED_DIRECT as
its normal mode rather than a fallback. Preserve the trusted frozen image,
primary Ministral perception, optional fail-open DePlot/reconciliation,
VisualReference, DerivedFacts, essay claim extraction/verification, task types,
and visual-confidence handling. TA descriptor-fit scoring consumes the grounded
analysis and whole essay without anchor queries, claim-count penalties,
contradiction-count deductions, hard caps, gates, or offsets.

For CC/LR/GRA, A3 uses Direct for NO_ANCHORS,
INSUFFICIENT_CONTIGUOUS_COVERAGE, OUT_OF_RANGE, POSITION_CONFLICT,
BUDGET_EXHAUSTED, or PAIRWISE_PROVIDER_FAILURE, persisting the reason. The fallback
is criterion-local. No changes to the official aggregation rule are introduced.

After trees resolve, one bounded feedback-synthesis request covers only
pairwise-successful CC/LR/GRA criteria. It receives final deterministic scores,
the target essay, and criterion rubrics. Its output schema
has feedback/strengths/improvements only, with no score fields. It cannot change
the backend score. Grounded Direct TA and fallback criteria retain their own
Direct feedback. Normal extra cost
is one synthesis call per run with pairwise successes, and zero when all
criteria use Direct. Scoring and feedback are separate reliability boundaries.
Once a tree establishes a valid deterministic score, that score remains final
even if synthesis fails. Persist the score, mode, and tree diagnostics, mark
feedback UNAVAILABLE with an allowlisted error code, and retain empty strengths
and improvements without fabricated feedback. Do not rescore, substitute Direct,
fail unrelated criteria, or invalidate an otherwise complete aggregate.

Adapt only the persisted/public CriterionResult contract: nullable feedback plus
an explicit feedback status/error, with legacy results defaulting to AVAILABLE.
AVAILABLE requires real non-blank feedback; UNAVAILABLE has no feedback text.
Direct provider output still requires feedback. The learner UI displays the
availability state, and copying AI suggestions does not erase existing human
feedback when AI feedback is unavailable. There is no hidden rescoring or
unbounded repair path.

## Production integration, reproducibility, and privacy

Preserve `Task1WritingScoringService` as the MTS A1 baseline/rollback. Add focused
Direct/Hybrid TACS implementations that reuse its perception preparation and trusted
image loading. Avoid copying/replacing the grounding subsystem. TA waits for
perception and claims; CC/LR/GRA begin independently. All completions share the
existing `BoundedWritingProvider`, including perception, claims, comparisons,
Direct, and synthesis. Preserve cancellation, durable checkpoints, heartbeats,
criterion-local failure isolation, DePlot fail-open semantics, and token budgets.

Add validated `AI_WRITING_TASK1_SCORER=anchor_pairwise|direct|mts`, defaulting to
`anchor_pairwise`, and a default two-node limit. Here `anchor_pairwise` explicitly
means Hybrid TACS: grounded Direct TA plus pairwise language traits, not four
pairwise criteria. Task 2 remains current text-only
MTS (`mts-task2-v7`). Anchor administration and reusable comparison infrastructure
support Task 2, but there is no Task 2 production cutover.

Add explicit run metadata for architecture, pinned anchor-set foreign key, node
budget, architecture prompt versions, and private per-criterion search/mode
diagnostics. Old runs retain their stored contracts and remain readable. The
anchor-set FK may point to a now-retired set; scoring that queued run still uses
the frozen set pinned at enqueue time. A no-anchor run pins the empty snapshot
decision rather than adopting a newly activated bank midway through execution.

Extend fingerprints with architecture, pairwise/direct/feedback versions, set
ID/version, node budget, frozen task identity, provider/model, essay, image
identity, unchanged visual contract, and specialist identity/config. Changing the
active set invalidates future equivalent cache reuse. Worker validation uses the
pinned execution contract rather than querying the current active set again.
The factory rejects unsupported saved prompt/visual contracts before provider
readiness or inference, using the safe AI_CONFIGURATION_CHANGED error; it never
executes current prompts under obsolete recorded versions. Null historical
execution records retain the existing legacy MTS dispatch and remain readable.
Task 1 presentation must recognize new architecture-specific version prefixes;
it must not accidentally label non-MTS Task 1 runs as Task 2.

Reuse existing persisted events with bounded anchor-search stages. Learner DTOs
and SSE payloads contain only safe progress/mode/reason data; private selected
anchor IDs, essays, labels, pivot bands, and preferences remain in internal run
metadata. Apply an explicit allowlist at presentation boundaries. Vietnamese
progress can say that reference responses are being compared without exposing
the bank. Keep timing logs content-free and count all actual requests/tokens.

All AI output remains advisory. Do not write `AttemptWritingScore`,
`Attempt.band_score`, official history/analytics, or human labels. Existing copy
suggestions still require explicit human Save to become an official grade.

## T1-C evaluation extension

Extend `backend/app/evaluation/task1/` and `scripts/benchmark_task1.py`; do not
create a second harness. Introduce explicit architecture/config identity and a
new benchmark contract version so old caches cannot be misread.

- A0 `direct`: whole-response criterion scoring.
- A1 `mts`: frozen existing MTS, including retained legacy version comparisons.
- A2 `direct-self-consistency`: three independent A0 runs, deterministic median
  per criterion, individual values/spread/variance, evaluation only.
- A3 `anchor-pairwise`: exact production **Hybrid TACS**, with grounded Direct TA
  and CC/LR/GRA trees, configurable node budget 1/2/3, actual anchor density,
  strict two-way agreement, and identical fallback rules.
- `all`: A0/A1/A2/A3. A4 ordinal/TRATES-like remains future work.

A2 pools numeric perception observations across all three repeats, recomputes
agreement against all labelled truth values, retains conservative sample
certification and reports independent observation denominators. Independent
invocations are not a decoding-diversity guarantee: the current vLLM adapter uses
temperature/seed zero and can produce three identical deterministic A0 results.

Accept either an explicitly selected active PostgreSQL snapshot or a private
human-labelled anchor manifest with provenance and exact task identity. Never
modify the production bank. Private manifest anchors are not inserted into
PostgreSQL. Do not automatically generate reference essays or labels.

Before provider calls, reject evaluated targets overlapping anchors by sample
ID or normalized essay hash. Use one shared deterministic Unicode/whitespace
normalization policy. Check the whole selected evaluation split against the
snapshot, not only the next comparator representative. Human target scores and
visual-truth annotations never enter scorer/provider requests. Private source
data, raw completions, essays, and anchor text remain excluded from reports,
checkpoints, and version control.

Retain per-criterion/overall exact, ±0.5, ±1, MAE, RMSE, signed bias, QWK when
meaningful, perception metrics, ALL/PERCEPTION_OK decomposition, calls, tokens,
specialist metrics, and latency. A3 additionally reports node mean/p50/max,
pairwise calls, visited bands, two-way agreement/conflict rates, each fallback
reason/rate, total Direct fallback, snapshot/version, and anchor density. Rates
must have explicit denominators; benchmark-only private diagnostics must not be
reused as learner payloads. Report TA accuracy against human TA truth separately
from language-tree metrics. Direct TA is not counted in the language fallback
rate or pairwise call/node denominator. Human TA labels may supply evaluation
truth but must never enter production TA messages. No real human benchmark runs
automatically. Optional one-way ablation remains future benchmark-only research;
production always compares both orders.

## Documentation deliverables

Create `docs/lces_adapt.md` with the final 27 requested sections: motivation;
original LCES high-level idea and adaptation limits; TACS adaptation; human-label
rationale; PostgreSQL model; admin workflow; coverage strategy; why TA is not
pairwise in production; final Task 1 architecture/diagram; tree search; position
bias; strict consensus; call budget; representative selection; reconstruction;
Direct fallback; feedback strategy; A0–A4; metrics; leakage; privacy/security;
latency/cost trade-off; failure modes; retained MTS; future work; interview Q&A;
and conservative CV bullets without fabricated percentages. Future work includes
Task 2 cutover, TA experiments only with supporting evidence, larger human banks,
better comparators, and A4 ordinal modeling.

Make `docs/ai-writing.md` the authoritative current overview. Update relevant
README/API summaries, `docs/modal-web.md`, benchmark README/schema/commands, and
only stale architecture portions of `docs/enhance_latency.md`; preserve its
measured results and clearly identify their MTS context. Mark version-specific
verification docs historical. Preserve old implementation plans as history,
without rewriting their past design. Retain `docs/MTS.pdf`. Delete no document
without checking inbound links and confirming it is genuinely redundant.

Classify audited documentation CURRENT/HISTORICAL/SUPERSEDED and search again
for contradictory unqualified production claims. No new real-model agreement,
latency, cost, or accuracy claim is made without measurements.

## Verification and acceptance

Use focused fake-provider and PostgreSQL tests, with synthetic essay fixtures
only in tests. Verify migration upgrade/downgrade on an isolated test database,
not by destructive operations on the administrator's live data.

Anchor/API tests cover empty DB, lifecycle, concurrent activation/write safety,
immutability, cloning, half-bands, frozen task ownership, four-score persistence,
paragraphs, admin 401/403, coverage, task separation, and research TA/TR
exact-task scope; production never calls a TA ladder query.

TA boundary tests prove no production TA comparator call or anchor-ladder query,
empty-bank independence, grounded analysis consumption, criterion-pure score
and feedback, stored human TA labels, benchmark TA evaluation, and production
readiness independent of TA coverage.

Language-tree tests pin 7 comparable -> 7.0/two calls; >7 then <8 -> 7.5/four calls;
<7 then >6 -> 6.5/four calls; forward/reverse normalization; strict conflict
with no third call; 6/8 insufficient coverage; 6/7/8 out-of-range without a
clamp; two-node exhaustion on a 5–9 ladder; deterministic representative;
structured score-metadata exclusion; provider failure; and fallback mode.

Worker/fingerprint/SSE tests cover snapshot pinning across activation,
architecture/version/cache invalidation, legacy run presentation, content-free
events, concurrency limits, trace failure/cancellation, feedback score
immutability, official-score non-mutation, and existing Task 1/Task 2 regressions.

Benchmark fake providers exercise A0/A1/A2/A3, A2 median, comparable records,
architecture-specific reports/resume/cache, leakage rejection before calls,
node-budget/density metadata, actual call accounting, and perception grouping.

Focused Vitest covers navigation, authorization, empty/create/edit/delete,
Task 1/2 labels, score validation, task picker, paragraphs, active read-only,
next-version/activation, production language readiness, research TA/Task 2
coverage, responsive/theme markup.
Run TypeScript typecheck, targeted ESLint, Ruff, and `git diff --check`.

Do not open a browser, run Playwright, run full expensive suites, repeatedly
invoke a GPU, or run the full human benchmark. An optional single pairwise smoke
is permitted only after tests pass and real local human anchors/credentials are
confirmed; it is not required for completion. No deployment or push is included.

The final implementation report must distinguish verified behavior from
unmeasured model accuracy, record starting/final git state, and cover database,
admin UX, coverage, tree/prompt/bias/budget/feedback contracts, selector,
benchmark/leakage, documentation classification, and exact focused checks. It
must confirm no fake production anchors, official-score mutation, hidden anchor
label exposure, unbounded comparisons, or push.
