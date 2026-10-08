# Advisory AI Writing Task 2

This is an **MTS-inspired zero-shot scoring** workflow: an online IELTS Task 2
adaptation, not an exact reproduction of a research experiment. Four independent
criteria are assessed sequentially: Task Response (`ta` for compatibility),
Coherence and Cohesion, Lexical Resource, and Grammatical Range and Accuracy.
Each criterion retrieves exact essay quotations with brief public assessments,
then scores against original internal guidance. No other criterion's answer is
shared. No dataset-level min-max scaling or outlier clipping is used.

The public **Scoring Trace** contains progress, evidence and concise feedback.
Hidden reasoning, raw provider responses and internal prompts are never stored
or streamed. Question/essay/evidence are explicitly treated as untrusted data.
Quotes must be exact substrings of the saved essay. Malformed output, invalid
scores and unverified quotes get one correction retry for that individual call.

Every criterion must be in 0–9 in steps of 0.5. FastAPI computes the Decimal
equal-weight mean and rounds it with the existing `round_to_half` helper:
`(6.5 + 6 + 7 + 6) / 4 = 6.375 → 6.5`. Both values are persisted.
**AI Task 2 Overall** is advisory. It never updates `AttemptWritingScore`,
`Attempt.band_score`, official Writing, History or Analytics. An admin can copy
scores/feedback into the existing editable form; the existing explicit human
Save is still required. The official Task 1 × 1 / Task 2 × 2 rule is unchanged.
Other users retain their existing permissions and cannot use AI to gain manual
grading access. Task 1 and Speaking are outside this feature.

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
AI_WRITING_VLLM_MODEL=mistralai/Ministral-8B-Instruct-2410
AI_WRITING_MODAL_KEY=<proxy token id>
AI_WRITING_MODAL_SECRET=<proxy token secret>
AI_WRITING_VLLM_API_KEY=
AI_WRITING_REQUEST_TIMEOUT_SECONDS=300
AI_WRITING_PROMPT_VERSION=mts-task2-v1
AI_WRITING_STALE_AFTER_SECONDS=90
```

Never put inference URLs or credentials in `NEXT_PUBLIC_*`. Only FastAPI calls
the provider. The optional vLLM bearer key is separate from Modal proxy auth;
the Modal deployment relies on required proxy authentication at the perimeter.
Disabled or missing configuration returns `AI_NOT_CONFIGURED` and keeps Writing
review usable. Restart FastAPI after configuration changes. Increment the prompt
version when changing rubric/prompt behavior so old cache entries stay distinct.

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
| GET | same path | Configured state and latest 20 runs for that Task 2 |
| GET | `/api/v1/ai-writing-grading-runs/{run_id}` | Safe JSON snapshot and partial criterion results |
| GET | `/api/v1/ai-writing-grading-runs/{run_id}/events` | SSE replay/live events |

Only finalized Writing attempts with a non-empty saved Task 2 response from the
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
# Temporary development endpoint; terminates when this command exits:
modal serve deploy/modal/writing_llm.py
# Persistent production deployment, with zero idle containers:
modal deploy deploy/modal/writing_llm.py
# Create backend-only proxy credentials; keep the output private:
modal workspace proxy-tokens create --json
```

Use the URL printed by deployment, append `/v1`, and configure the returned
`Modal-Key` / `Modal-Secret` pair in the backend settings above. Development URLs
may have a `-dev` suffix. For scoped workspaces, allow the token in the deployment's
environment (`modal workspace proxy-tokens allow --help`). No Modal credentials or
Hugging Face tokens belong in Git. Public model downloads require no repository
secret; if your workspace needs gated access, add a narrowly scoped Modal Secret
to the deployment instead of hard-coding a token.

The application uses pinned `vllm/vllm-openai:v0.11.2`, a persistent model/cache
Volume, one L4, FP16 weights, eager execution, an 8,192-token model length, at most
two concurrent sequences, and `min_containers=0` / a 60-second idle window. The
web endpoint has `requires_proxy_auth=True`. The model URL and tokens stay behind
FastAPI. Cold starts need time to download/cache weights and initialize the GPU.

As checked on 2026-10-08, L4 is the lowest-priced Modal GPU with headroom for the
unquantized 8B model at this context/sequence budget: L4 has 24 GB; the cheaper
T4's 16 GB does not leave safe room for weights plus runtime/KV cache. This is a
capacity choice rather than a throughput benchmark; recheck pricing as it changes.
Sources: [Modal supported GPUs](https://modal.com/docs/guide/gpu),
[Modal pricing](https://modal.com/pricing), [NVIDIA GPU memory](https://docs.nvidia.com/brev/reference/gpu-types),
[model serving guidance](https://huggingface.co/mistralai/Ministral-8B-Instruct-2410),
[Modal proxy authentication](https://modal.com/docs/guide/webhook-proxy-auth).

One lightweight smoke inference (set the proxy pair in the current shell):

```powershell
$env:AI_WRITING_MODAL_KEY='<proxy token id>'
$env:AI_WRITING_MODAL_SECRET='<proxy token secret>'
python deploy/modal/smoke.py --base-url https://YOUR-PROTECTED-ENDPOINT.modal.run/v1
```

It sends one 16-token JSON request and prints only pass/fail. Normal tests never
contact Modal/OpenAI. For shutdown and optional cache removal:

```powershell
modal app stop ielts-writing-llm --yes
# Optional, destructive: deletes cached model weights after stopping the app.
modal volume delete ielts-writing-model-cache
# Revoke the deployment's proxy token when no longer needed:
modal workspace proxy-tokens delete <proxy-token-id>
```

Ministral 8B 2410 has its own [Mistral Research License](https://huggingface.co/mistralai/Ministral-8B-Instruct-2410).
Recheck its terms and commercial licensing before commercial deployment.

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
- **Timeout/HTTP failure:** check `modal app logs ielts-writing-llm`, GPU startup,
  proxy authorization and backend timeout. Regrade creates a new retryable run.
- **Invalid assessment:** one repair is automatic; a second failure preserves
  completed criteria and marks the run FAILED. Check the provider/model/version.
- **Interrupted run:** wait for the heartbeat lease to expire or revisit review;
  stale state becomes FAILED and Regrade is available.
- **Trace disconnected:** the client probes saved JSON and reconnects with its
  cursor. Check API cookie/CORS configuration and proxy SSE buffering.

```powershell
cd backend
uv run pytest tests/test_writing_ai.py tests/test_writing_llm_providers.py tests/test_writing_scoring.py tests/test_ielts_band.py tests/test_writing_attempts.py -q
# Run Ruff on the AI modules and touched integration files.
cd ../frontend
npm exec vitest run tests/writing-ai-assessment.test.tsx tests/writing-review.test.tsx
npm run typecheck
cd ..
git diff --check
```

No browser, Playwright or broad E2E suite is required for these checks.
