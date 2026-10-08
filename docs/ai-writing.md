# Advisory AI Academic Writing

Task 1 and Task 2 share the configured `mistralai/Ministral-3-8B-Instruct-2512`
model, provider adapters and existing Modal/vLLM GPU function. Task 2 retains
its text-only MTS pipeline and `mts-task2-v6` cache contract. Task 1 adds the
multimodal grounding pipeline below, with its own `mts-task1-visual-v2` version.

## Task 2: text-only assessment

This is an **MTS-inspired zero-shot scoring** workflow: an online IELTS Task 2
adaptation, not an exact reproduction of a research experiment. Four independent
criteria are assessed sequentially: Task Response (`ta` for compatibility),
Coherence and Cohesion, Lexical Resource, and Grammatical Range and Accuracy.
Each criterion selects stable source IDs with brief Vietnamese assessments,
then scores against faithful paraphrases of the current official IELTS Task 2
band descriptors. No other criterion's answer is
shared. No dataset-level min-max scaling or outlier clipping is used.

The public **Scoring Trace** contains progress, evidence and concise feedback.
Hidden reasoning, raw provider responses and internal prompts are never stored
or streamed. Question/essay/evidence are explicitly treated as untrusted data.
Before inference, a deterministic pure helper divides the original essay into
non-empty paragraphs (blank-line boundaries) and conservative sentences. It
handles CRLF/LF, closing quotation marks, abbreviations, decimals and Unicode
punctuation. Each `PnSm` source stores paragraph/sentence indices, start/end
character offsets and the exact `essay[start:end]` text, without rewriting it.
The model selects up to four allowed IDs; the backend resolves each ID to that
original slice and emits `source_id`, `quote` and Vietnamese `assessment`.
Optional model `focus` never determines validity and is not persisted. The model
never needs to reproduce punctuation or whitespace. Legacy v1/v2 quote recovery
helpers are isolated and documented; source-ID inference never calls them.
Each evidence/scoring interaction gets at most one targeted correction, then
fails that criterion safely if still invalid; remaining criteria continue.

Prompt version **`mts-task2-v6`** requires natural Vietnamese for assessments,
feedback, strengths and improvements, while preserving original English quotes.
Old v1/v2/v3/v4/v5 assessments remain history and are never reused by v6. Deployed secrets
still naming older versions use effective v6 for fingerprinting/execution. Custom labels
are prefixed by v6 so they cannot accidentally reuse the previous contract.

Both `mts-task2-v6` and `mts-task1-visual-v2` tighten descriptor discrimination:
compare the plausible whole-band profile with its immediate neighbours, requiring
sustained whole-response evidence for higher-level qualities. Isolated strong
sentences and isolated weaknesses do not represent the whole essay. Uncertainty
is neither rounded upward by default nor resolved by an automatic lower-band rule.
Half-bands remain interpolation. Criterion-specific guidance keeps TA/TR separate
from CC/LR/GRA. No score subtraction, caps, error-count formulas or new scoring
metadata validators were added; the four-field score contract is unchanged.

Scoring guidance was checked against the [official IELTS descriptors](https://ielts.org/cdn/ielts-guides/ielts-writing-band-descriptors.pdf)
on 2026-10-08 (current publication: May 2023, Task 2 pages 7–9). Only the four
official criterion scopes are used. Scoring compares adjacent whole-band
descriptors holistically; half-bands interpolate, with affirmative descriptor-fit
support for high scores. The scoring interaction requests only four fields:
`score`, concise Vietnamese `feedback`, and bounded Vietnamese `strengths` and
`improvements`. A brief adjacent-descriptor comparison may inform feedback; it
is prompt guidance, not an additional validity gate. No error-count deductions,
severity-to-band rules, caps or calibration constants alter the model's score.
Prompts require consistent score/feedback. Fake-provider tests verify this
contract, not real-model accuracy.

Legacy or unsolicited `calibration` metadata is parsed independently after core
validation. Missing/malformed metadata never retries or fails a valid criterion.
Unknown calibration support/blocker IDs discard only those items; malformed
explanations can discard the optional metadata. The next whole-band label is
derived from the accepted score (`floor(score) + 1`, or none at 9), without changing
that score. Safe `CALIBRATION_*` diagnostics are non-fatal and never user errors.
Primary evidence IDs remain strict. Optional metadata is excluded from public
results and guided scoring schemas. vLLM receives a copy of the JSON schema with
unsupported `pattern`, `minLength`, `maxLength`, and `format` constraints removed;
full backend Pydantic validation remains authoritative. Token budgets and timeouts
are unchanged. Invalid core results or truncated completions still get one repair.

Provider output is parsed as `RawScoringOutput`: a valid half-band, non-blank
text feedback, and lists containing only strings. Unknown extra fields remain
forbidden; only known legacy `calibration` metadata is tolerated. Text length
and bullet counts are display constraints, not IELTS score validity gates.
After semantic validation, a pure helper strips outer whitespace, removes blank
bullets, keeps at most three meaningful bullets and clips long text to the
existing 800/240-character bounds. Clipping preserves an original Unicode
prefix, prefers nearby sentence/word boundaries, and appends an ellipsis; it
never changes scores, generates new text, or calls another model. The bounded
`ScoringOutput` is then used for persisted/public criterion results. Guided
schemas still request maxItems and concise text, but cannot enforce vLLM's
unsupported string lengths. `SCORE_PRESENTATION_NORMALIZED` with safe field/type
details is non-fatal and internal only. Missing/blank required feedback, invalid
scores, non-string/non-list fields, invalid JSON and truncation still repair/fail.

Every criterion must be in 0–9 in steps of 0.5. FastAPI computes the Decimal
equal-weight mean and rounds it with the existing `round_to_half` helper:
`(6.5 + 6 + 7 + 6) / 4 = 6.375 → 6.5`. Both values are persisted only if all four
criteria succeed. Otherwise the run ends FAILED after attempting all criteria,
with successful results and individual failures preserved and no aggregate.
**AI Task 2 Overall** is advisory. It never updates `AttemptWritingScore`,
`Attempt.band_score`, official Writing, History or Analytics. An admin can copy
scores/feedback into the existing editable form; the existing explicit human
Save is still required. The official Task 1 × 1 / Task 2 × 2 rule is unchanged.
Other users retain their existing permissions and cannot use AI to gain manual
grading access. Speaking remains outside this feature.

## Task 1: visual grounding before assessment

Only the backend loads the saved Task 1 image. It checks ownership, finalized
Writing/review eligibility, the exact frozen task/version, a non-empty response,
asset version/type, supported PNG/JPEG/WebP MIME and matching byte signature,
storage-root containment, file existence and byte size (at most the configured
upload limit, capped at 10 MiB). No remote image URL is accepted. The frontend
uses its existing prompt image; it never uploads another image for grading.

The normal run performs one image-plus-prompt perception call, followed by
text-only claim extraction and the shared evidence/scoring pairs. The image
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
[official Academic Task 1 descriptors](https://ielts.org/cdn/Guides/ielts-writing-band-descriptors.pdf)
(May 2023, pages 3–5). There are no error-count penalties, score caps or a fifth
criterion. CC/LR/GRA receive only prompt/essay and their own source evidence,
without visual data or another criterion's score. Existing score normalization,
equal-weight Decimal mean and half-band rounding are reused.

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

Provider requests remain `stream=false` for reliable structured JSON. Public
workflow events distinguish preparing, collecting evidence, validating evidence,
scoring, validating scores, retrying and terminal states. New events are
`evidence.request.started`, `evidence.validation.started`,
`criterion.scoring.validation.started` and `criterion.retrying`. Safe activity
with a stage timestamp is persisted in the existing run JSON metadata and
included in snapshots; no migration is needed. The vertical timeline reconstructs
from activity, progress and terminal status after refresh. Criterion cards appear
as soon as their individual completion event arrives. Elapsed time is display-only,
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
- **Invalid assessment:** each evidence/scoring operation permits one targeted
  repair. A second failure emits/persists `criterion.failed` and continues with
  the next criterion. The run becomes FAILED after all four have been attempted.
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
  Presentation limits yield `SCORE_PRESENTATION_NORMALIZED` without another
  inference call. Required semantic/structural failures still use bounded repair.
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
  Length is rejected even if the JSON happens to look complete, with one shorter
  repair. Unknown metadata is sanitised to `other`, never logged verbatim. The
  existing guided JSON-schema integration, temperature 0/seed 0 and 1800-token
  vLLM budget remain. Evidence assessments are at most 320 characters/two
  requested sentences; score feedback is at most 800 characters, strengths and
  improvements at most three each. No global token increase or GPU smoke job was
  needed. Scoring context references selected IDs rather than duplicating quotes.
- **Interrupted run:** wait for the heartbeat lease to expire or revisit review;
  stale state becomes FAILED and Regrade is available.
- **Trace disconnected:** the client probes saved JSON and reconnects with its
  cursor. Check API cookie/CORS configuration and proxy SSE buffering.

```powershell
cd backend
uv run pytest tests/test_chart_cross_check.py tests/test_task1_visual.py tests/test_task1_writing_ai.py tests/test_essay_sources.py tests/test_mts_writing_v3.py tests/test_mts_writing_v4.py tests/test_mts_writing_v5.py tests/test_writing_ai.py tests/test_mts_writing_validation.py tests/test_writing_ai_output_normalization.py tests/test_writing_llm_providers.py tests/test_writing_llm_readiness.py tests/test_deplot_deployment.py tests/test_modal_app.py tests/test_modal_web_runtime.py -q
# Run Ruff on the AI modules and touched integration files.
cd ../frontend
npx vitest run tests/writing-ai-assessment.test.tsx tests/writing-ai-progress.test.tsx tests/writing-review.test.tsx
npm run typecheck
cd ..
git diff --check
```

No browser, Playwright or broad E2E suite is required for these checks.

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
