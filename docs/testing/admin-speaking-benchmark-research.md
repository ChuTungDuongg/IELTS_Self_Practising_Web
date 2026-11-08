# Admin Speaking Benchmark Research — Phase 3

Baseline inspected: `ba458360eb9a42f2237ef66b3c28daa098864b4e`. This is an additive
modular-monolith extension of [Phase 1](admin-speaking-benchmark.md) and
[Phase 2](admin-speaking-benchmark-evaluation.md). Implementation and verification
are offline. Real recognition quality and band improvement remain **UNVERIFIED**.

Follow-up audit inspected local HEAD and freshly fetched `origin/main` at
`00e295f05a3e8a793e0a6481c1db5e2cafe973c6`, where Phase 3 was already implemented.
Current working-tree corrections and fresh verification are recorded below
separately from the original implementation's historical results.

## Architecture and authority

```mermaid
flowchart TD
  UI[Admin Research / Human transcripts] --> API[FastAPI: ADMIN and owner scope]
  API --> DB[(PostgreSQL: references / experiments / variants / observations)]
  DB --> R[Separate research CPU worker: lease + request admission]
  R --> A[ASR-only: existing Azure PA / Azure STT / optional Whisper]
  R --> P[Paired: sequential immutable P2 grading runs]
  P --> G[Existing P2 worker / production SpeakingScorer]
  A --> S[Private approved source windows / AssetStorage / FFmpeg]
  G --> S
  DB --> M[Pure comparison metrics / CSV / JSON]
  H[Independent human transcripts and examiner labels] --> M
```

Research never changes learner transcripts, gradebook scores, approved reviews or
P2 predictions. The API only persists/admit jobs. Neither imports, page views,
preflight nor reports submit inference. ASR-only does not require OpenAI or VAD.
Paired grading uses P2 and its physical OpenAI transport ledger, including internal
schema and length repairs; there is no new grading algorithm.

Only explicitly selected, approved review revisions are valid inputs. Each window
is bound to source SHA, review fingerprint, exact segment ID/start/end and normalized
PCM. No fake replay manifests or approval receipts are constructed. An interview's
examiner turns must be removed by Phase 1 approval before either mode can execute.

## Schema and history

Additive Alembic head `20261108_0047`, following `20261108_0046`, adds four tables:

| Table | Purpose |
| --- | --- |
| `speaking_benchmark_asr_references` | Append-only source/review/window-bound draft/verified human transcripts |
| `speaking_benchmark_experiments` | Frozen cohort, mode, providers, protocol, initial evaluation selections and consent |
| `speaking_benchmark_experiment_variants` | Per-sample/provider configuration, durable state, lease, optional P2 run link |
| `speaking_benchmark_asr_observations` | Physical ASR attempts and immutable normalized results/cache receipts |

Composite owner/sample/review foreign keys, unique revisions/submission keys and
PostgreSQL triggers protect source bindings, frozen configuration and finalized
results. Completed observations cannot be overwritten. Approved revisions remain
P1 artifacts. Sample deletion fences research and grading, hides the sample, and
retains the existing retryable private-media cleanup/tombstone policy. Derived
references/variants/observations cascade with the sample; experiment configuration
retains a source-bound missing-data denominator, without retained audio or transcripts.

## Human transcription protocol

Open a sample's **Human transcripts** tab. Select its exact approved response,
listen using the existing authenticated source player and enter what was spoken.
Keep fillers, repetitions, repairs, incomplete sentences, wrong word choices and
grammar such as “Yesterday I go”. Never restore fluent grammar or invent unclear
words. Saving appends a draft revision; independent review and verification append
another revision. A stale expected revision returns a conflict.

Verification requires `independent_human_transcriber` provenance, a nonblank
transcriber/source reference, nonempty text and an explicit audio-review assertion.
`ai_draft` and `unverified` cannot be marked verified. If an AI draft is manually
corrected and independently reviewed, save a new human-provenance revision; the
prior AI provenance stays in history. Verification is an administrator's attestation,
not automated proof of transcriber independence. A distinct second account is not
required; cross-admin isolation remains in force.

Annotations use zero-based normalized token positions with an exclusive end:
`filler`, `repetition`, `self_correction`, `incorrect_grammar`. API uncertainty spans
use source milliseconds and distinguish uncertain, unintelligible and questionable
reference quality. The editor supports each type with exact source start/end
millisecond controls and preserves existing spans when editing text. Adding the
first span defaults to the whole approved window; adjust its bounds after replay.
Any such annotation excludes that window from WER/CER/preservation metrics.
This avoids making up words or silently excluding only difficult tokens. Raw text
and uncertainty remain visible. Optional accent/speed labels require voluntary
metadata confirmation; no sensitive attributes are inferred from audio.

Human transcripts and bands are joined **only in report projection**. They do not
enter provider kwargs, hotwords, prompts, scorer evidence, model selection or cache
identity. “Use latest verified” recalculates reports without changing inference.
The experiment's original reference/label revision selection remains immutable.

## Modes, identities and scheduling

**ASR_ONLY:** explicitly select candidate windows and one or more variants of
`azure_pa`, `azure_stt`, `faster_whisper_local`, `faster_whisper_modal`. Azure silence
timeout overrides are supported in 100–5000 ms; compare separate experiments or API
variant keys for different thresholds. No semantic segmentation or text correction
is introduced. Whisper uses the existing fixed decoding policy; arbitrary decoding
options are rejected rather than silently ignored. Model/locale/revision/options,
audio normalization, source/review/windows and PCM identity are frozen.

**PAIRED_GRADING:** select the complete approved attempt. Only lexical provider may
differ. PA, VAD, quality, scorer/model/prompt/rubric and normalization remain fixed.
Silence overrides are rejected in this mode. P2's active-run uniqueness stays intact;
variants wait and schedule serially per sample. Existing matching finalized P2
artifacts and exact provider checkpoints can be reused. PA and VAD cache identities
exclude lexical/scorer changes; lexical identity includes its own model/config.
Criterion scores are reused only when their actual production evidence matches.
The research worker polls linked P2 runs with a bounded wait; run the P2 worker too.

P2 cache consumption persists an immutable nonbillable checkpoint receipt in the
consuming run, linked through `reused_from` to the original artifact. The receipt
retains the exact stage/identity/result and carries no duplicate provider usage.
Paired transcript reports read only the linked run's artifacts, never a newer
unrelated hypothesis with the same provider name. Historical P2 runs lacking a
receipt show unavailable per-window evidence; their frozen band predictions remain
available. No historical prediction is backfilled or rewritten.

Changing a reference/label changes metrics only. Changing a scorer prompt does not
invalidate unchanged PA/VAD/lexical observations. Changing an ASR model creates a
new variant identity. No completed historical transcript or prediction is rewritten.

## Billing, interruption and recovery

Both environment-level research flags default false. Start requires a fresh static
preflight fingerprint, every selected provider's admission estimate, explicit audio
consent, summed audio/request limits and accepted total estimate ceiling. Paired
mode adds LLM consent; Modal GPU and HOLDOUT each require separate explicit consent.
Cloud estimates must be positive; local CPU may be zero. These numbers are operator
admission estimates, **not prices, measured charges or invoice caps**.

Before each physical ASR submission, `ATTEMPTED` commits in a short transaction.
Successful normalized evidence and observed usage commit immediately. Network/timeout,
lost response and incomplete streams remain `INTERRUPTED_BILLING_UNKNOWN`; partial
recognized text is retained but cannot claim reliable accuracy. There is no automatic
billable retry. Lease tokens and expiry fence completion and subsequent submissions.
A late response may settle its exact attempt after cancellation, never restart work.

An ASR interrupted experiment requires exact observation-ID reconciliation, an operator
reason and renewed complete consent; permission applies once to the same stage/identity.
Past authorization records and old uncertain attempts remain auditable. P2 interruption
uses its existing exact-checkpoint reconciliation in the sample's AI Evaluation, then
**Resume tracking after P2 reconciliation** in Research. Reports/imports never perform
this action automatically. A cancelled research experiment is not silently restarted;
create a separately authorized experiment if needed, preserving unknown-request guards.

Research cancellation and linked active P2 cancellation commit atomically while
holding the sample locks. A process failure after commit cannot leave the linked
run admitted to submit more requests. In-flight responses may settle their own
attempt's accounting only. A cache receipt cannot reconcile an unknown physical
request; replacement checks require an actual later completed physical attempt.
P2 recovery retains research attribution. Summaries distinguish physical calls,
cache receipts, reused finalized runs, unknown billing and unavailable usage.

## Metrics and interpretation

Protocol: `admin-speaking-research-v1`. Normalization:
`asr-research-nfc-casefold-words-v2` applies Unicode NFC, casefold, the existing word
tokenizer (including within-word apostrophes), removes other punctuation and collapses
whitespace. CER uses that normalized text with single spaces. Raw transcripts stay
unchanged. No grammar or LLM correction. Legacy replay CLI v1 normalization remains
unchanged. Bounded Levenshtein alignment uses the existing diagonal-first tie policy;
different equally minimal alignments can distribute S/D/I differently.

Reference annotation bounds and provider-disagreement comparisons use this same
NFC token stream. A historical reference with invalid post-normalization offsets
returns unavailable accuracy (`REFERENCE_ANNOTATION_BOUNDS_INVALID`) until a corrected
revision is saved; reports do not fail or silently move its annotation.

WER retains exact substitution/deletion/insertion/reference-word counts. Micro WER
is total errors / total reference words; sample macro WER averages response WER per
sample then averages samples. Speaker macro groups known candidate pseudonyms. Filler
and adjacent repetition detection plus manual repair/grammar spans share existing
preservation logic. Insertion counts are hallucination **proxies**, not semantic proof.

Without verified independent references, WER/CER/preservation are unavailable.
Provider disagreement is explicitly not accuracy. Empty references have no WER
denominator. Missing/failed/unknown results retain their selected-window denominator.
Coverage measures recognized intervals, timing validity, untimed words and uncertainty;
recognized interval coverage is not verified speech/VAD coverage.

Reports retain comparable and eligible references, exact word counts, unavailable and
failed counts, mean/p95 latency, real-time factor and physical usage. Cached latency
is the original observation's latency, not a new recognition measurement. Host process
CPU and optional RSS are recorded when measurable; remote CPU/memory/GPU consumption
is unavailable unless a future provider contract supplies it. Do not infer dollars.

Paired provider differences use matched samples and identical reference/label revisions.
Band arithmetic reuses P2 `score_metrics`: MAE/RMSE/bias/exact/±0.5/±1.0, Pearson,
Spearman and 19-category QWK with their existing minimum/undefined rules. Missing
criteria or Overall remain null. The actual human Overall is not recalculated.
Bootstrap intervals use 2,000 seeded percentile resamples of **candidate clusters**,
equal candidate weighting, and at least ten known independent pseudonyms. Otherwise
CI is unavailable. Sample means and speaker means are distinguished. These descriptive
intervals do not establish causality or a winner.

Candidate clusters are sorted before seeded resampling, so database query order
and process hash seeds cannot change the interval for the same selected data.

Lower WER does not guarantee lower band error: omitted repairs, recognized grammar,
question context, timing coverage and LLM variability can affect grading differently.
PR still uses fixed PA acoustic evidence and cannot be attributed to a different lexical
ASR engine. No automatic tuning, calibration, ranking or model training is performed.

DEV/HOLDOUT membership and selected metadata are frozen. Candidate pseudonyms spanning
both sets produce leakage warnings. HOLDOUT requires a frozen configuration and explicit
final-evaluation consent; execution time is recorded. Repeated holdout tuning is not
automated or made statistically valid by this tooling.

## APIs and exports

All routes are under `/api/v1/admin/speaking-benchmark`, require `AdminUser`, owner
scope and existing mutation-origin security. UUID guessing does not grant access.

- `GET/POST samples/{id}/asr-references`, `POST .../{reference_id}/verify`;
  GET supports review/segment/revision history pagination.
- `GET research/cohort`: approved reviews/windows, optional owner-scoped sample/split.
- `GET/POST research/experiments`; `GET research/experiments/{id}`.
- `POST .../{id}/preflight`, `/start`, `/cancel`, `/reconcile`, `/resume-paired`.
- `GET .../{id}/results`, `/export.csv`, `/export.json`.

Results/exports support the same split, Part, provider key, duration, voluntary accent,
speed, response-length, verified human Overall and frozen/latest reference filters.
Provider/model/scorer identities are frozen per experiment; choose another experiment
for another model/rubric. Lists and response rows are bounded and stably paginated.

JSON exports include versioned frozen configuration, source/model identities, selected
reference and label revisions, metric/missing-data counts, paired/band metrics, usage
and latency. CSV rows contain the same core provenance and lexical/coverage metrics
with structured cells, per-sample band comparisons and band aggregates. Formula-leading CSV values
are escaped. Default exports omit audio bytes, raw speech text, word payloads, storage
keys, credentials, private paths and examiner notes. The authenticated comparison UI
exposes normalized hypotheses and word timings separately. No export invokes inference.

## Local setup and commands

Use a **disposable** PostgreSQL database for migration/testing. Never point test commands
at the application database. Preserve P1's pinned diarization runtime; research does
not install PyTorch/Pyannote. From repository root:

```powershell
uv sync --project backend --frozen --extra azure-speech
# Paired only: also install --extra speech-vad and configure the pinned VAD asset.
# Optional local Whisper only: --extra speech, complete local model, bounded memory runtime.

# Set DATABASE_URL to a separately provisioned disposable database before this command.
Push-Location backend
uv run alembic upgrade head
Pop-Location

uv run --project backend uvicorn app.main:app --app-dir backend --port 8000
npm --prefix frontend run dev

# Research is disabled by default. No startup command bypasses per-experiment consent.
uv run --project backend python scripts/speaking_benchmark_research_worker.py --once
uv run --project backend python scripts/speaking_benchmark_research_worker.py --poll-interval 5
# Paired: run this separate consumer as well.
uv run --project backend python scripts/speaking_benchmark_grading_worker.py --poll-interval 5
```

Alembic's script location resolves from its configured working directory: the reliable
migration form is `cd backend; uv run alembic upgrade head`. Run that only with the
intended disposable URL during development. Web and workers must share the same
database/private AssetStorage. FFmpeg/ffprobe must resolve; Windows uses the existing
`tools/speaking_diarization` resolver when necessary. Worker supports `--once`, positive
`--limit` and finite positive `--poll-interval`; SIGTERM/SIGINT perform fenced shutdown.

On Windows, a PATH lookup may return `ffmpeg.EXE` even when the installed file is
named `ffmpeg.exe`. The sibling `ffprobe.exe` lookup is case-insensitive. The
follow-up audit exercises both PATH lookup and the existing absolute-path resolver
with generated WAV/MP3, without downloading decoder binaries or speech models.

Before separately authorized live operation, explicitly configure
`SPEAKING_BENCHMARK_RESEARCH_ENABLED=true`,
`SPEAKING_BENCHMARK_RESEARCH_ALLOW_LIVE=true`, `SPEAKING_ASR_ENABLED=true`, and only the
selected providers' credentials/billing policy. Azure regular STT and PA are distinct
models; neither is assumed better. Paired mode additionally requires P2 readiness,
OpenAI and pinned VAD, including existing independent-provider permissions/budgets.
No API key belongs in frontend environment variables or exports.

Optional local Whisper requires complete local weights/tokenizer, no automatic download.
Static memory admission rejects a model.bin larger than one third of configured worker
memory; this is a conservative estimate, not a hard RSS guarantee. Use an isolated
container/OS memory and CPU limit for actual enforcement. The standard research CPU
image does not install Whisper. Modal GPU requires the existing dedicated endpoint,
configured proxy key/secret, operator GPU opt-in and separate UI consent. Merely selecting
it cannot deploy/start a service. Arbitrary Whisper decode options are not supported.

## Deployment topology and rollback

`deploy/speaking-benchmark-research.Dockerfile` is a separate CPU entrypoint with Azure
SDK/FFmpeg only. It can run in a separately configured CPU container, including Modal
with reachable external PostgreSQL and shared private S3/R2. Bound CPU/memory and use
persistent private model caches if adding optional local models. No deployment was run.

**Modal embedded PostgreSQL/local Volume mode is unsupported for remote research or P2
workers.** Containers do not share loopback databases or local filesystem snapshots.
Readiness rejects this topology; this feature does not migrate production mode or mount
an embedded DB concurrently. Existing Modal Web CPU image and P1 CPU worker remain intact.

Rollback: stop research consumers and disable both research flags. Keep additive schema
and immutable history. Existing in-flight requests may still be billed; reconcile them
explicitly. Do not downgrade a database containing research data as a routine rollback.

## Offline verification and first live study

The deterministic suite uses synthetic PCM, disposable PostgreSQL and fake Azure,
Whisper/OpenAI transports. Real FFmpeg normalization, source validation, persistence,
production evidence/scorer projection and P2 orchestration are exercised. Browser UI
verification uses a loopback fixture API which cannot forward inference requests.
Verification on 2026-11-08:

| Check | Observed result |
| --- | --- |
| Final P3, P2 worker/billing and migration suite | 42 passed, 66.06 s |
| Broader Speaking P1/P2/P3, replay, lexical and hybrid regression | 205 passed, 9 skipped, 167.82 s |
| Full backend suite on separate fresh disposable databases | 3,935 passed, 16 skipped, 1 failed, 1,464.06 s |
| Failed Windows normalization group rerun six times in isolation | 18 passed; no failure reproduced |
| Full frontend suite | 2,004 passed across 170 files, 226.37 s |
| Final research/P1/P2 frontend focused suite | 33 passed across 3 files, 7.98 s |
| Backend Ruff and formatting | Passed; 624 files checked |
| Frontend typecheck, ESLint and production build | Passed |
| Disposable Alembic round trip | 0046 → 0047 → 0046 → 0047 passed; one head |
| Browser workflow at 1440 / 768 / 390 px | Passed; one source player, no page overflow or JavaScript errors |
| Personalisation accent / appearance combinations | 20 passed: all 10 accents in light and dark mode |
| Offline browser create/authorize/results/reference save and verify | Passed against a loopback-only synthetic API; no inference forwarding |

The full Windows backend run reported `ASSET_PATH_INVALID` from the unchanged local
storage containment check in `test_concurrent_normalization_uses_one_referenced_object`.
The same three-test normalization group passed all six repeat runs. This intermittent
failure is recorded rather than hidden or attributed to a proven Phase 3 defect.
Skipped tests require separately provisioned integrations; skips are not live verification.
The final CI status belongs to the exact pushed commit and is reported separately.

Research controls use the existing Personalisation accent tokens: solid primary actions,
soft secondary actions, neutral disabled controls and visible keyboard focus. Desktop
and mobile controls retain a minimum 44 px height. Light/dark layouts and accent switching
were checked in the browser. Shared navigation and existing account preferences remain
the authority; no page-specific palette or new preferences are stored.

```powershell
$env:DATABASE_URL="postgresql+asyncpg://benchmark_test:benchmark_test@127.0.0.1:5546/bandpilot_p3_primary_test"
$env:TEST_DATABASE_URL=$env:DATABASE_URL
$env:P2_TEST_DATABASE_URL="postgresql+asyncpg://benchmark_test:benchmark_test@127.0.0.1:5546/bandpilot_p3_final_isolated_test"
# All URLs must be disposable. P2_TEST_DATABASE_URL must differ from DATABASE_URL.
$tests=@(rg --files backend/tests -g 'test_admin_speaking_benchmark_research*.py')
uv run --project backend pytest @tests -q --tb=short
npm --prefix frontend test -- --run tests/speaking-benchmark-research.test.tsx
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

First live A/B procedure, **only after a separate explicit operator authorization**:
1. Use DEV recordings with permission and independently transcribed verified references.
2. Approve candidate identity/windows in P1; choose exact revision, initially 1–2 short
   windows and a summed-provider duration ceiling such as 120 seconds.
3. Freeze ASR_ONLY with Azure PA and Azure STT, unchanged locale/silence/normalization.
4. Review static preflight, actual selected window count and per-provider request count;
   enter current operator estimates and accepted ceiling. Explicitly authorize in UI.
5. Start one research worker with `--once`/`--limit 2`. Review ledger before any repetition.
   A timeout requires reconciliation; never blindly restart an uncertain physical request.
6. Export results, report human-reference count/S/D/I/coverage/latency/usage and missing
   results. This small pilot establishes operation, not a statistically valid winner.
7. Only with separate LLM consent, freeze PAIRED_GRADING on complete approved attempts,
   fixed P2 model/prompt/rubric/PA/VAD, then run both workers. Compare matched human labels.
8. Add more independent candidates before cluster intervals; keep HOLDOUT for the frozen
   final configuration. Optional Modal Whisper requires separate GPU authorization.

No real WER improvement, Vietnamese-accent accuracy, provider throughput/cost, semantic
fairness, grading calibration, cloud network/IAM/durability or GPU behavior is claimed
from fixtures. Human reference quality and pseudonym independence remain dataset duties.

## Follow-up integrity audit — working tree on `00e295f`

The original implementation request did not authorize commit, push, deployment,
production migrations or live paid requests. The subsequent operator request
authorizes committing/pushing these fixes to main and repairing CI; deployment,
production migrations and paid inference remain outside that authorization.
Audit work was on `codex/speaking-research-integrity`. Unrelated
untracked user files were left untouched. The four-table migration already existed at this inspected
commit; the fixes reuse its fields and the P2 checkpoint `reused_from` column.

Corrected and regression-tested behavior:

- Only the linked P2 run supplies a paired hypothesis. A newer unrelated observation
  cannot replace it; missing historical cache receipts remain missing evidence.
- Consumed cache artifacts have durable nonbillable receipts, deduplicated per stage
  and identity. Physical call/usage totals exclude them in P2 and research reports.
- Cache receipts cannot clear physical billing uncertainty. Recovery retains research
  attribution and unknown-request counts. Cancellation fences research and linked P2
  work in one transaction, including a simulated failure immediately after commit.
- Reference bounds, WER/CER and provider disagreement use the same NFC policy. Invalid
  historical annotation offsets produce an unavailable reason. Seeded candidate
  bootstrap intervals are invariant to input order.
- The editor preserves exact uncertainty kinds/windows and unsaved text across locale
  changes. Reference history loading blocks editing and rapid response switching.
- Windows `.EXE` PATH discovery correctly resolves the sibling `ffprobe.exe`.

Fresh verification (synthetic audio/fake inference only):

| Check | Observed result |
| --- | --- |
| Full frontend suite on final UI | 2,009 passed, 170 files, 161.11 s |
| Final broader Speaking P1/P2/P3, replay, ASR/lexical, hybrid and Modal contracts | 280 passed, 1 skipped, 142.17 s |
| Final P1/P2/P3 frontend focused suite | 38 passed, 3 files, 7.52 s |
| Real WAV/MP3 decoder suite and uppercase-suffix regression | 11 passed, 5.16 s |
| Frontend TypeScript, ESLint and production build | Passed |
| Backend Ruff lint/format | Passed, 605 app/test files formatted |
| Fresh databases upgraded from empty | Two disposable databases passed |
| Separate disposable Alembic round trip | Empty → 0047 → 0046 → 0047; single head |
| Independent review of integrity fixes | Findings corrected; final review found no further issue |

The final backend skip is `test_source_cannot_escape_private_root_even_through_symlinks`:
this Windows host does not permit symlink creation. The first broader backend run
passed 271 tests with 9 skips. Enabling the installed
Windows FFmpeg directory exposed the `.EXE` lookup defect (26 failures sharing that
cause); it was reproduced with a new failing unit test and corrected. The final
broader run passed 280 tests with only that host-permission skip. Neither intermediate failures
nor the original implementation's historical full-suite results are a claim about
the final working tree.

Commands used for the broader regression (repository root, three **disposable**
PostgreSQL databases; no application database was used):

```powershell
# Make the already-installed ffmpeg.exe AND ffprobe.exe directory available.
# Do not install/download speech models for this suite.
$env:PATH = "<installed-ffmpeg-bin>;" + $env:PATH
$env:DATABASE_URL = "postgresql+asyncpg://research_test:research_test@127.0.0.1:5547/bandpilot_p3_audit_test"
$env:P2_TEST_DATABASE_URL = "postgresql+asyncpg://research_test:research_test@127.0.0.1:5547/bandpilot_p3_isolated_test"
$tests = @(rg --files backend/tests -g 'test_admin_speaking*.py' -g 'test_speaking_asr*.py' -g 'test_speaking_lexical_asr.py' -g 'test_speaking_replay*.py' -g 'test_speaking_hybrid*.py' -g 'test_modal_speaking_hybrid.py')
uv run --project backend pytest @tests -q --tb=short -rs
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

This audit did not rerun the entire backend suite or browser layout/screenshot QA.
The synthetic end-to-end database tests exercise both experiment modes; actual
Azure/Whisper/OpenAI quality, real billing and remote deployment remain unverified.


---

## Phase 4 Quality, Consensus and Regression Gates

Phase 4 builds directly upon the ASR references and experiment artifacts of Phase 3 to provide multi-rater IELTS ground truth, dataset QA (`speaking-dataset-quality-v1`), frozen evaluation suites, and continuous evaluation regression gates (`speaking-regression-gate-v1`). See [Phase 4 Quality and Gates](admin-speaking-benchmark-quality-and-gates.md).
