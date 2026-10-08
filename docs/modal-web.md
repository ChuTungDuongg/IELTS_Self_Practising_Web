# Run Next.js and FastAPI together on Modal

CURRENT hosting guide. Writing Task 1 now defaults to Hybrid TACS; Task 2 stays MTS v7. Apply Alembic migrations before serving. `AI_WRITING_TASK1_SCORER=anchor_pairwise|direct|mts` and `AI_WRITING_PAIRWISE_MAX_TREE_NODES=2` use the existing backend-only AI environment forwarding; no new GPU deployment or function is needed. The versioned anchor bank belongs to the existing PostgreSQL snapshot lifecycle. Admin curation is available at `/admin/writing-anchors`; initially empty banks use language Direct fallback with grounded Direct TA. See [the current AI overview](ai-writing.md) and [TACS guide](lces_adapt.md).

After the one-time setup below, from the repository root:

```powershell
modal serve deploy/modal/app.py
```

One command makes both Web and the protected Writing LLM available. The existing
Next.js frontend, FastAPI backend and a private PostgreSQL 17 process share one
CPU container. A separate L4 GPU function serves the unified
`mistralai/Ministral-3-8B-Instruct-2512` text/vision model on demand. Modal prints the public
HTTPS URL. Nginx forwards `/api/` to FastAPI and other paths to Next.js, including
unbuffered SSE. Browser API calls use `/api/v1`; server component/proxy requests
use `API_INTERNAL_BASE_URL` over loopback. Cookies use the same HTTPS origin.
No browser connects to PostgreSQL or to the LLM provider.

`modal serve` keeps the app available while that command runs. Modal's source
watching/live reload is currently unsupported on Windows; restart the command
after source changes there. The frontend is built in production mode inside the image. For a stable
deployment that stays available after the terminal exits:

```powershell
modal deploy deploy/modal/app.py
```

The included GPU function scales to zero after 60 idle seconds. It starts on the
first backend readiness request, not during the web image build. Web resolves its
hydrated function's URL and sets the backend `/v1` base automatically, including
temporary dev URLs. No URL needs copying on each restart. The private
`ielts-web-config` Secret must contain `AI_WRITING_MODAL_KEY` and
`AI_WRITING_MODAL_SECRET`. See [ai-writing.md](ai-writing.md) for model details.
The web/database container keeps one CPU replica running to preserve PostgreSQL.

For web only, explicitly disable AI before the same command:

```powershell
$env:IELTS_WEB_AI_ENABLED='false'
modal serve deploy/modal/app.py
```

For full AI development, enable it again:

```powershell
$env:IELTS_WEB_AI_ENABLED='true'
modal serve deploy/modal/app.py
```

`AI_WRITING_ENABLED=false` in the invoking shell also disables AI when
`IELTS_WEB_AI_ENABLED` is unset. Shell `AI_WRITING_*` overrides are forwarded as
an ephemeral Secret; they never become image environment layers. For the bundled
vLLM provider, the included function's URL/model override obsolete Secret values.
An explicitly selected OpenAI provider retains its own configuration. Missing
credentials are reported as "AI grading is not configured" before creating a run.

## One-time setup

Authenticate the Modal CLI (`modal setup`) and configure `backend/.env`
with the existing JWT settings and backend-only AI credentials. Then:

```powershell
cd backend
# Creates a consistent local PostgreSQL dump, uploads and verifies its checksum:
uv run python ../scripts/modal_database_snapshot.py
# Use the exact snapshot path printed by the command above:
uv run python ../scripts/modal_web_setup.py --snapshot <snapshot>/database.dump
cd ..
# Create only if it does not already exist:
modal volume create ielts-web-assets
modal volume put ielts-web-assets storage/audio /
modal volume put ielts-web-assets storage/images /
modal serve deploy/modal/app.py
```

The setup script copies an allowlist of JWT/AI settings to the private Modal
Secret `ielts-web-config`. It never prints values or uploads `.env`. It intentionally
does not copy local database URLs or OAuth redirect settings; configure cloud OAuth
separately if needed. Existing accounts/password hashes are restored from the
snapshot, so the normal login workflow remains in place.

The first startup initializes `/database/pgdata` on `ielts-web-postgres`, validates
the snapshot SHA-256, restores it with `pg_restore`, and applies Alembic migrations.
Later starts reuse that PostgreSQL database without importing snapshots over new
data. Local binary assets are on `ielts-web-assets`, and generated cloud assets
stay there. The original imported snapshot remains on `ielts-postgres-backups`.
The cloud database is a separate copy; local and cloud changes are not synchronized.
`modal serve` uses its own `ielts-web-postgres-dev` database, seeded from the same
snapshot, so it can run alongside the persistent deployment with one command.
Dev and production share the assets Volume; avoid editing shared assets in dev.

Only loopback PostgreSQL is trusted inside the single container; its port is not
published. Backend and Next.js also listen on loopback. Only Nginx is forwarded by
Modal. The application uses its existing authentication and role checks, while
the model endpoint additionally requires Modal proxy credentials.

## Database lifecycle

### Moving to another Modal workspace

Profiles select the account/workspace; the deployment uses the same resource
names in that selected workspace. Authenticate the destination without replacing
the source credentials, then select it after copying:

```powershell
modal token new --profile <destination-profile> --no-activate
# After verified resource migration:
modal profile activate <destination-profile>
modal serve deploy/modal/app.py
```

Stop all source Web writers before taking a filesystem copy. Migrate both
`ielts-web-postgres` and `ielts-web-postgres-dev` (Volumes v2), `ielts-web-assets`,
`ielts-postgres-backups` and `ielts-writing-model-cache`. Preserve PostgreSQL file
permissions/empty directories and Hugging Face cache symlinks, and verify file
SHA-256 plus the full entry inventory before starting the destination Web. Keep
source volumes and verified backups until the destination is confirmed usable.

Create fresh proxy credentials in the destination and recreate its private
`ielts-web-config` Secret from the existing backend configuration. Source proxy
credentials do not authorize requests to the new workspace. Preserve JWT settings
and database records; never copy the `ielts-web-database-owner` Dict's active
leases. The destination creates its own empty guard. The full-stack app resolves
its new provider URL automatically. A separately running local FastAPI instance
needs that new URL and the destination proxy pair in its ignored `.env`.

The 2026-10-08 workspace migration verified SHA-256 and inventories for all five
volumes, including 26,493,350,173 bytes of model cache and its 11 symlinks. Both
database copies, empty directories and permissions were retained. New proxy
credentials/Web Secret were provisioned; source data was preserved. The destination
`modal serve deploy/modal/app.py` subsequently started Next.js and FastAPI and
successfully read the migrated database. Its first vLLM image build took about
194 seconds; building that image did not start a GPU or perform inference.

The PostgreSQL Volume uses Modal Volumes v2 for random writes/hard links. v2 is
currently beta, and Modal does not guarantee against data loss. Keep the verified
logical snapshot; use a managed PostgreSQL service for production-critical data.
To use one, add its `DATABASE_URL` to `ielts-web-config`; the runtime then skips
local PostgreSQL. [Modal documents the storage limitations](https://modal.com/docs/guide/volumes).

The deployment has at most one container. A Modal Dict acts only as a single-writer
deployment guard for each database; it contains no domain records. Each database
can have only one live writer. Stop production before redeploying it; stop an
existing dev session before starting another dev session. A normal dev start
does not require stopping production:

```powershell
modal app stop ielts-practice-web --yes
modal deploy deploy/modal/app.py
```

Shutdown stops HTTP processes and PostgreSQL, commits Volumes, then releases the
guard. If a killed/crashed container leaves a stale guard, **first confirm every
old `ielts-practice-web` and `ielts-practice-web-dev` containers are stopped**, then:

```powershell
modal dict clear ielts-web-database-owner --yes
modal serve deploy/modal/app.py
```

Never clear the guard while its database process is running. Startup removes the
old container's PID file only after acquiring the exclusive guard. The existing
PostgreSQL WAL handles interrupted local writes; the logical snapshot provides
an independent recovery copy.

## Verification and teardown

Without opening a browser, check the URL printed by Modal:

```powershell
curl.exe --fail https://YOUR-WEB-URL.modal.run/api/v1/health
curl.exe --fail https://YOUR-WEB-URL.modal.run/
```

`/api/v1/auth/me` must return 401 without a session. Sign in with an existing
restored account to use the review; no new auth bypass is introduced. If startup
fails, use `modal app logs ielts-practice-web`. Secrets and raw inference prompts
are excluded from image build inputs and application request logging.

Stop the web deployment with `modal app stop ielts-practice-web --yes`; stopping
`modal serve` also shuts down its temporary Web and GPU functions. Volumes and
backups remain available. A legacy standalone `ielts-writing-llm` deployment is
not needed by this entry point; stop it separately after migrating any clients.


## Optional T1-B chart service

The unified Ministral vLLM service remains unchanged. DePlot runs in the separate
`deploy/modal/chart_derenderer.py` Modal app/function, with no second Web/PostgreSQL
stack. It uses a protected ASGI `/extract` endpoint accepting only bounded PNG,
JPEG or WebP bytes, PIL RGB preprocessing and a fixed extraction instruction.
The backend never exposes its URL or proxy credentials to the frontend.

Set `AI_WRITING_CHART_SPECIALIST_ENABLED=true` in the shell **before** the existing
`modal serve deploy/modal/app.py` or `modal deploy deploy/modal/app.py` command.
The entry point then includes the separate chart function and hydrates its backend
URL, checkpoint and revision. It is disabled by default; web-only mode also disables
it. Existing `AI_WRITING_MODAL_KEY`/`AI_WRITING_MODAL_SECRET` credentials must be valid
for the chart endpoint. For a separately hosted specialist, use the backend
configuration in `.env.example` instead. No production deployment was performed
for this task.

Runtime pins: Python 3.12, Transformers 5.13.0, PyTorch 2.10.0, Pillow 12.1.1,
SentencePiece 0.2.1 and FastAPI 0.135.1. Checkpoint `google/deplot` is Apache-2.0,
pinned at `6e76d62430da16986be3426bae32301fb9115397`. Model downloads use the
`ielts-deplot-model-cache` Volume. The function requests T4, 2 CPU cores and
8 GiB host RAM, with zero minimum containers, one maximum container and 60-second
scaledown. It does not share the Ministral L4 process or its GPU memory.

On 2026-10-08, [Modal pricing](https://modal.com/pricing) listed T4 as its lowest
priced GPU at $0.000164/second, versus L4 at $0.000222/second. CPU and host memory
are billed separately, as are applicable Volume/storage costs; startup and the
scaledown grace period also contribute. CPU-only inference was not benchmarked,
so no CPU latency or cost advantage is claimed.

One optional synthetic multi-pie smoke actually ran using Modal client 1.5.3 and
the pinned runtime on T4. It measured **30.247 s** model download/load and
**3.364 s** inference; peak PyTorch GPU allocation was **2,204,196,864 bytes**
(about 2.05 GiB). Overall local wall time was **145.25 s**, including first image
build/provisioning and app teardown; this is not HTTP serving latency or a warm
latency distribution. These measurements verify memory fit and practical
single-extraction compute time on the cheapest listed GPU, not chart accuracy.

The model returned malformed multi-pie table data. A single local cross-check
using that same output produced **PARSE_FAILED**, correctly retaining T1-A rather
than confirming chart data. No second extraction or repeated GPU benchmark was
run. Normal tests independently validate six matching values from the original
synthetic Region A/B fixture. Real multi-pie extraction remains a model limitation,
so the optional specialist stays disabled by default. The temporary smoke app
completed; the production Web and Ministral deployments were not changed.

The backend specialist timeout is 90 seconds by default and never exceeds 120.
Cold cache/download or queueing can exceed it; fail-open fallback keeps usable
primary grounding. One extra specialist pass is requested only for the chart/table
family. No real IELTS image, real essay grading, TinyChart or T1-C evaluation was
run. `synthetic_smoke` is an explicit manual diagnostic function, not part of normal
grading or automated tests; avoid repeated paid inference when verifying changes.
