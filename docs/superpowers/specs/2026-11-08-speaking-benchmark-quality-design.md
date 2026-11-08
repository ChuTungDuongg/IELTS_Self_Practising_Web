# Speaking Benchmark Phase 4 — Annotation, consensus and regression gates

## Scope and inspected baseline

The operator selected the existing modular monolith and explicitly requested the
full P4 implementation without redundant design approval. Inspected local/main:
`b62bbeeeacdc2c7969c568ae425ba9b6b3d6ebd8` (P3 integrity follow-up, pushed with
separate authorization). P4 remains uncommitted unless subsequently authorized.
The operator has stopped CI monitoring; do not poll running P3 workflows.

This design implements the supplied Phase 4 task in the existing Next.js/FastAPI/
PostgreSQL/AssetStorage boundaries. No new scorer, ASR engine, diarizer, metrics
framework, microservice, automatic provider call or deployment is introduced.

## Approach and decisions

Extend P1-P3 with focused annotation, human-assessment and evaluation modules.
Reusing P3 experiments as question jobs was rejected: examiner windows are not
approved candidate response manifests. Reusing legacy human-label rows for raters
was rejected: they cannot represent blind access or source-bound independent
assessments. New narrowly scoped tables retain those separate authorities.

Use existing lexical analyzers and P3 static readiness/configuration for questions;
use the P2/P3 short-transaction, attempted-before-submission ledger pattern. Use
existing `score_metrics`, lexical/coverage metrics and candidate-cluster bootstrap
for reports. Normalized persisted provider artifacts remain the only AI input.

## Data model (additive head 0048 after actual 0047)

- `speaking_benchmark_question_jobs`: owner/sample/review/source/draft fingerprint,
  provider configuration, selected clean examiner windows, frozen admission limits,
  consent, fenced lease/status, immutable proposals and append-only decision history.
- `speaking_benchmark_question_requests`: window/config identity, physical attempt,
  result/usage, original cache reference, billing state and exact reconciliation.
- `speaking_benchmark_raters`: owner-scoped INTERNAL/EXTERNAL identities. Internal
  identity is the authenticated User FK, unique per owner; external stable key and
  provenance distinguish verifiable reports from unverified owner claims.
- `speaking_benchmark_rater_assignments`: explicit sample/review/source-bound grants
  to one internal user/rater, or external-assessment binding; revocable, no dataset grant.
- `speaking_benchmark_human_assessments`: immutable submitted revisions per assignment,
  nullable half-band values and literal Overall, independence/provenance/source/comments.
- `speaking_benchmark_adjudications`: immutable revisions with selected assessment
  IDs/revisions, explicit final bands, rationale, owner/adjudicator and policy version.
- `speaking_benchmark_quality_snapshots`: immutable evaluated configuration, exact
  selections, source/annotation fingerprints, issues and denominators.
- `speaking_benchmark_evaluation_suites`: immutable family/revision, cohort, split,
  exact label/reference selections, quality/metric policies and eligibility rules.
- `speaking_benchmark_regression_gates`: immutable suite/baseline/candidate/policy
  definitions; changing thresholds creates a new definition.
- `speaking_benchmark_regression_reports`: immutable gate evaluation snapshots,
  consumed artifact identities, metrics/decisions/missingness and timestamps.
- `speaking_benchmark_holdout_audits`: append-only authorized suite access/evaluation
  records; no inference permission is implied by an audit record.

Composite ownership/source/review foreign keys and database triggers enforce bindings,
immutable submitted records/configurations/results and valid nullable half-bands.
Deleting a sample revokes grants and fences question jobs before existing media cleanup.
Frozen suites/reports retain metadata denominators and report deleted artifacts missing.
They never retain audio bytes. External comments/notes are omitted from exports.

## Examiner question assistant

The request explicitly confirms an examiner speaker ID whose saved P1 role is
`examiner`, confirmed candidate identity and verified Part boundaries. Bind the
exact P1 review/draft/model/source fingerprints; extraction can precede approval.
Select regular diarization turns only. Reject any positive overlap with any other
speaker, unknown roles, boundary-crossing or excessive windows. Exclusive diarization
does not acoustically separate voices. Preflight lists exclusions and chosen turns.

Normalize bounded original source windows using existing `normalize_window`; do not
fabricate an approval receipt or candidate manifest. Azure STT is default; optional
configured local/Modal Whisper is opt-in. Azure PA and Luna are not question engines.
Static preflight makes no inference/readiness calls. Start requires selected windows,
audio consent, finite estimates/ceilings and separate GPU consent. Each physical call
commits ATTEMPTED before submission and persists normalized output immediately.
Unknown billing is never automatically retried; exact reconciliation renews permission.

Deterministic chronology associates preceding same-Part examiner turns to candidate
responses with a bounded gap. Interrogative openings/question punctuation suggest
questions; acknowledgements, clarifications, interruptions, multiple associations,
long gaps and Part-2 cue-card omissions stay flagged. No fabricated confidence.
Each proposal exposes source range, provider, text, association, Part/type and flags.

Human acceptance/rejection appends decision history. Accept creates a new P1 review
draft using existing validation; it never calls approve, replaces an already verified
question or invents cue points. Batch acceptance excludes ambiguous proposals.
Changing the source review requires a fresh proposal job; originals remain immutable.

## Human assessments and blind security

Owner-only routes manage identities/assignments, enter external reports, inspect
ratings and adjudicate. Internal reviewer routes resolve actor from assignment ID,
not a supplied owner ID. They return only permitted audio and verified prompts plus
the reviewer's own assessment history. They never return model scores, other raters,
adjudications, private examiner notes or aggregate results, even after submission.
The existing owner service/audio endpoints remain owner-only. Revocation/deletion
immediately blocks reviewer access. No public tokens/links are introduced.

Internal assignment to the owner is rejected as an independent blind assignment.
One user cannot impersonate multiple raters. External names are not proof: independent
eligibility requires explicit verifiable-report provenance/reference and attestation.
Submissions are immutable; expected revisions prevent concurrent correction loss.
No absent band is synthesized and Overall is never recomputed from criteria.

Adjudication references the exact latest selected submitted assessment revisions,
source/review binding and an explicit owner decision/rationale. It is never an average
label or a model-selected consensus. Pairwise human agreement reuses `score_metrics`;
kappa/correlations retain existing insufficient/degenerate sample rules.

## Explicit label policies and compatibility

`LabelSelection` is `{kind: LEGACY|INDEPENDENT|ADJUDICATED, id?: UUID,
revision?: integer}`. The source-bound resolver returns kind/id/revision/bands,
eligibility/provenance and `binding_status`. LEGACY labels are `LEGACY_UNBOUND`:
P1 has no source/review FK and must not be described as source-proven labels.

Omitting selection preserves P2 latest-verified legacy and P3 frozen legacy selection
semantics exactly. Explicit new comparison policies join selected human labels only
in report projection, without modifying experiments/runs or invoking inference.
Suites freeze resolved selections and ASR reference IDs, never silently selecting newer
labels/references on rerun. Strict QA can reject legacy unbound labels.

## Read-only dataset quality

Version `speaking-dataset-quality-v1` returns READY, NEEDS_REVIEW, BLOCKED or
INSUFFICIENT_DATA and typed issues `{code,severity,artifact,id,remediation}`.
Check source presence/SHA/approval, rights, candidate pseudonym, Parts/questions,
speaker overlap/silence flags, human provenance/disagreement/adjudication, reference
availability/uncertainty/staleness, DEV/HOLDOUT leakage, provider/score coverage,
configuration mismatch and uncertain billing. Missing data is not corruption or zero.
Explicit snapshots freeze selections, inputs and outputs. No cloud inference occurs.

## Frozen suites and regression gates

Suites freeze 1–100 approved samples, source/review/split/candidate identities,
resolved human label and reference revisions, metric/quality policy, minimum independent
candidate count (default engineering limit 10), prediction/reference coverage (default
1.0) and required quality conditions. Revisions append; they do not edit old suites.

Artifact selectors support `{kind: EXPERIMENT,id,variant_key}` and
`{kind: GRADING,configuration_fingerprint}`. Select exact source/review/configuration
matches and at most one finalized prediction per sample. Gate runs freeze consumed
run/observation IDs. Missing inference remains missing; no gate starts a provider.

Gate policy `speaking-regression-gate-v1` explicitly lists each metric, maximum
tolerable directional regression and minimum coverage/candidate requirements.
Conservative suggested limits are engineering defaults, not validated psychometric
thresholds: zero WER/CER/MAE regression, zero extra billing-unknown requests, full
required coverage, 10 independent candidates. Operators explicitly accept the policy.
Support ASR errors/preservation/coverage/latency/RTF, band MAE/agreement/bias/availability
and operational failures/usage/cache/missing artifacts. Relative differences are null
when their baseline makes a ratio undefined.

Decision precedence: incompatible source/review/reference/metric/rubric identities =>
INVALID; failed required QA/coverage or exceeded tolerable regression => FAIL;
otherwise insufficient matched independent candidates/unavailable required metrics =>
INCONCLUSIVE; only complete eligible evidence within all limits => PASS.
LEXICAL_ASR comparisons hold scorer/prompt/rubric/PA/VAD fixed; CONFIGURATION comparisons
allow declared model/prompt differences but retain rubric/scale compatibility and
confounding limitations. Candidate clusters, seeded sorted bootstrap and fixed
denominators reuse P3. No significance/winner/causal assertion is inferred.

HOLDOUT suite creation/access/evaluation requires explicit final-evaluation consent,
is audited and warns on repeated use; no split reassignment or threshold tuning.
Manual recomputation and an offline saved-JSON CLI are sufficient continuous reporting:
new completed persisted artifacts can be reevaluated explicitly without inference.

## UI and API contracts

Owner API root `/api/v1/admin/speaking-benchmark`; all mutations keep origin protection.
Bounded, stable-paginated routes: samples/{id}/question-suggestions, human-raters,
samples/{id}/rater-assignments, human-assessments, adjudications, quality,
evaluation-suites, regression-gates and regression-reports. Scoped reviewer routes
use `/reviewer-assignments/{assignment_id}` and its `/audio` and `/assessments` children.

Next pages add `/quality`, `/suites`, `/gates`, plus assigned-reviewer list/detail.
Sample workspace adds focused Question Assistant and Human Assessment panels, shared
audio playback and existing unsaved-form protection. Research links make QA/suites/
gates discoverable. Typed Pydantic/Zod DTOs retain explicit human/AI/warning distinctions,
accessible equivalent tables, existing tokens and English/Vietnamese translations.
Exports are versioned, formula-safe and exclude private notes/raw audio/provider payloads.

## Verification, flags and deployment

New question inference enable/allow-live flags default false. Read-only annotation,
quality and evaluation remain available without provider credentials. The question CPU
entrypoint shares the existing deployment topology guards, FFmpeg and optional ASR;
the regular Web image gains no model/native speech dependencies. No GPU deployment.

Use deterministic unit/security/concurrency/DB tests with synthetic audio/fake transports;
fresh disposable PostgreSQL only. Run focused P4/P1-P3, full backend (first result and
reruns separately), full frontend, TypeScript/ESLint/Ruff/build, migration roundtrip and
available offline browser flow. Record unavailable checks honestly. Rollback disables
question flags/stops consumer and keeps additive immutable history.
