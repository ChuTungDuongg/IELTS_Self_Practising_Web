# Run BandPilot on Modal

After the one-time setup below, from the repository root:

```powershell
modal serve deploy/modal/app.py
```

One command makes Web and the protected LLM and Speaking ASR services available. The existing
Next.js frontend, FastAPI backend and a private PostgreSQL 17 process share one
CPU container; FFmpeg normalizes private segmented Speaking audio there. A separate L4 GPU function serves the unified
`mistralai/Ministral-3-8B-Instruct-2512` text/vision model on demand. Modal prints the public
HTTPS URL. Nginx forwards `/api/` to FastAPI and other paths to Next.js, including
unbuffered SSE. Browser API calls use `/api/v1`; server component/proxy requests
use `API_INTERNAL_BASE_URL` over loopback. Cookies use the same HTTPS origin.
No browser connects to PostgreSQL, the LLM, or the Speaking ASR provider.

`modal serve` keeps the app available while that command runs. Modal's source
watching/live reload is currently unsupported on Windows; restart the command
after source changes there. The frontend is built in production mode inside the image. For a stable
deployment that stays available after the terminal exits:

```powershell
modal deploy deploy/modal/app.py
```

Both included GPU functions have zero minimum containers and scale down after
60 idle seconds. Neither starts merely because Web starts; Ministral starts on
its first backend readiness request, while ASR starts on the first transcript
request. Web resolves their hydrated URLs automatically, including temporary
dev URLs. No URL needs copying on each restart. The private
`ielts-web-config` Secret must contain `AI_WRITING_MODAL_KEY` and
`AI_WRITING_MODAL_SECRET`; the backend reuses this proxy token for the protected
ASR endpoint. See [ai-writing.md](ai-writing.md) for LLM details.
The Web container keeps one CPU replica. Embedded demo PostgreSQL remains single-writer; external mode also retains `max_containers=1`.

When `IELTS_WEB_AI_ENABLED=true`, Web enables both Writing and Speaking AI grading.
Speaking uses the same protected Writing vLLM transport and hydrated Ministral
model by default, without a second LLM container. Optional backend-only
`SPEAKING_AI_PROVIDER` and `SPEAKING_AI_MODEL` overrides can select a different
configured Writing transport/model. The startup log reports only safe enablement,
provider/model identity and transport-presence flags; it never prints endpoint
URLs, proxy credentials or candidate content. Speaking ASR remains independent.

## Speaking ASR deployment

The included `ielts-speaking-asr` function runs faster-whisper 1.2.1 with
`Systran/faster-whisper-large-v3` pinned to revision
`edaa852ec7e145841d8ffdb056a99866b5f0a478`. It uses CTranslate2 4.8.2,
PyAV 18.1.0 (faster-whisper 1.2.1's decoder is incompatible with PyAV 19),
`int8_float16` compute, English decoding, word timestamps, T4, 4 CPU, 16 GiB host RAM,
one maximum container, and the dedicated `ielts-speaking-asr-model-cache` Volume.
The service has no public unauthenticated inference path: Modal requires proxy
authentication for its `/health` and `/transcribe` routes. Only bounded mono
16 kHz signed-16-bit normalized WAV is accepted. Raw WebM remains in private Web
storage, request WAV stays in a disposable ASR temp directory, and neither audio
nor transcript bodies are logged by application code. The model cache contains
model artifacts only. The Web image installs FFmpeg but not faster-whisper.

Production Web sets `SPEAKING_ASR_ENABLED`, `SPEAKING_ASR_PROVIDER=modal`, the
hydrated backend-only base URL, model, revision, service version and a 600-second
processing bound before FastAPI starts. `IELTS_WEB_SPEAKING_ASR_ENABLED=false`
disables this function explicitly; it otherwise follows `IELTS_WEB_AI_ENABLED`.
Local development can keep `SPEAKING_ASR_PROVIDER=local` with `backend[speech]`
and a complete local model directory. Changing model, revision or decoding
version invalidates transcript cache; rotating only the endpoint URL does not.
No database migration is needed for this deployment configuration.

For one manual smoke, prepare a short synthetic spoken English mono 16 kHz WAV
outside git, use the existing backend proxy credentials from a private dotenv,
and call the configured backend `ModalASRProvider.transcribe` once. Check that
the result has nonempty text, valid word timings and the pinned model/version.
The protected endpoint also accepts a direct `POST /transcribe` with `audio/wav`
and `Modal-Key`/`Modal-Secret` headers; keep their values out of commands, logs
and reports. Check `modal app logs ielts-practice-web` for startup failures and
`modal container list` for GPU scale-down without printing request bodies. Delete
the synthetic WAV after the check. One sentence cannot establish IELTS accuracy.

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

## Managed PostgreSQL and S3/R2 mode

The default remains the existing embedded-database/Local-Volume demo. For cloud
mode, select topology **before** invoking the existing entry point:

```powershell
$env:IELTS_MODAL_STORAGE_BACKEND='r2' # or s3
$env:IELTS_MODAL_DATABASE_MODE='external'
$env:IELTS_MODAL_CONFIG_SECRET='ielts-web-production-config'
$env:IELTS_MODAL_MODE='production'
```

Create or update that named Secret through the Modal dashboard/operator tooling.
It must contain the P3 backend settings, including `STORAGE_BACKEND` matching the
topology, external `DATABASE_URL` using `postgresql+asyncpg` and TLS (`?ssl=require`
or preferably `?ssl=verify-full` with the provider's public CA bundle),
`IELTS_AUTO_MIGRATE=false`, `IELTS_DEPLOYMENT_ENV=production`, HTTPS
`FRONTEND_ORIGIN`, a strong `JWT_SECRET`, and `AUTH_COOKIE_SECURE=true`.
For R2 add `S3_BUCKET`, `S3_REGION=auto`, its account `S3_ENDPOINT_URL`, and scoped
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. S3 uses its actual region and secure
runtime credentials or the SDK credential chain. Modal does not inherit an EC2
instance role: provide credentials through its Secret or an operator-managed
short-lived credential flow. Configure existing protected AI credentials in this
same backend Secret. Nothing sensitive belongs in `.Image.env` or Next.js.
The Next.js and Nginx child processes receive restricted environments; database,
JWT, storage and AI credentials stay with FastAPI rather than being inherited
by those processes.

For hostname-verified database TLS, put the relevant **public CA certificate or
small regional bundle** (within the 32 KiB Secret-value limit) in
`IELTS_DATABASE_CA_PEM` in the Secret. Runtime stages it to a temporary PEM,
sets `PGSSLROOTCERT` for the child processes and removes it after they stop;
the explicit migration function uses the same staging. Private keys are rejected.
Alternatively supply a readable `PGSSLROOTCERT` file through operator-prepared
runtime configuration; do not provide both sources. No asset Volume is needed
for the temporary certificate, and no database password is baked into the image.

The frozen `IELTS_MODAL_STORAGE_BACKEND` marker controls Volume mounts, while
`STORAGE_BACKEND` in the Secret selects the P3 adapter. A mismatch fails before
starting services. Cloud mode mounts no asset, database or snapshot Volume and
never starts embedded PostgreSQL; temporary FFmpeg/ZIP files remain ephemeral.
Local mode preserves a configured `STORAGE_ROOT`, defaulting to `/storage`; use
that mount or its subdirectory for durable demo files.

The public app names, HTTPS routes and `/api/v1` contracts remain unchanged.
Use a separate dev Secret with `IELTS_DEPLOYMENT_ENV=dev`, a separate database,
and a separately verified bucket/prefix for dev. A mismatched environment label
is rejected. Labels do not inspect bucket contents: the operator must verify the
actual database/bucket/prefix separation. Selecting a different namespace never
copies existing objects.

External Web startup does not run Alembic, initialize a database or restore a
snapshot. With all Web writers stopped, an authorized operator runs exactly one:

```powershell
modal run deploy/modal/app.py::migrate_database
```

This explicit function uses the selected backend Secret, requires an external
URL, and has one maximum container. Use the schema owner's credentials for the
migration, with an alternate Secret if necessary. Coordinate one operator and
one migration across app versions; do not run parallel migration commands.
Only after it succeeds should the operator start/deploy Web. No command in this
section was executed as part of offline P4 verification.

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
data. Snapshot seeding is allowed only for a newly initialized PostgreSQL
directory; an existing directory without the restore marker is not overwritten.
Local binary assets are on `ielts-web-assets`, and generated cloud assets
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

The demo's PostgreSQL Volume uses Modal Volumes v2. Keep verified logical backups
and use managed PostgreSQL for production-critical data. An external `DATABASE_URL`
skips embedded PostgreSQL; it defaults to operator-controlled migrations, even
when Local assets are retained. See the managed-mode setup above and
[Modal's Volume documentation](https://modal.com/docs/guide/volumes).

The deployment has at most one container. A Modal Dict acts only as a single-writer
deployment guard for each database; it contains no domain records. Each database
can have only one live writer. Stop production before redeploying it; stop an
existing dev session before starting another dev session. A normal dev start
does not require stopping production:

```powershell
modal app stop ielts-practice-web --yes
modal deploy deploy/modal/app.py
```

### Asset-volume isolation and durability

By default both dev and production use the existing `ielts-web-assets` Volume.
Their database guards are separate, so they do not prevent concurrent access to
that shared asset Volume. Do not treat the two environments as isolated.
`IELTS_MODAL_ASSETS_VOLUME` is an optional deployment-time override. You may
instead set `IELTS_MODAL_DEV_ASSETS_VOLUME` and
`IELTS_MODAL_PRODUCTION_ASSETS_VOLUME`; the generic override takes precedence.
`IELTS_MODAL_REQUIRE_ASSET_ISOLATION=true` refuses the legacy shared Volume in
dev. Leave it false only when deliberately retaining the legacy demo behavior.
Set the chosen names in
the shell before invoking the existing Modal entry point; leave it unset to retain
the existing Volume. A non-default name must already exist: the deployment will
not create an empty replacement implicitly. The selected name is frozen into the image so local and
remote imports agree. A new name selects a different Volume: it does **not** copy
the files referenced by the database. Before switching, stop writes, copy and
verify every referenced file using a separately reviewed procedure, retain a
backup of the original Volume and the database, and verify a rollback path.

The Web runtime explicitly calls `assets.commit()` only during graceful shutdown.
Modal also performs background commits while a container is running. Neither the
background schedule nor a PostgreSQL commit confirms that a particular upload
has been durably committed before the HTTP response. Other running containers
need a reload to observe new commits; reload cannot run while files on the Volume
are open. Concurrent writes to the same file are not coordinated. Forced
termination and concurrent containers therefore present data-loss or stale-view
risks. A periodic commit alone would not guarantee consistency with concurrent
writes or PostgreSQL; it must not be treated as a transactional backup. Retain
independent verified backups and use a write-freeze/maintenance window for
consistent snapshots. See [Modal Volume semantics](https://modal.com/docs/guide/volumes).
The startup log identifies demo durability and warns when dev uses the legacy
shared Volume. The runtime reloads Local assets once before application files
are opened, never during active serving. Shutdown stops all application processes
before explicitly committing; commit failures are raised without private provider
diagnostics. No per-upload/per-chunk durability is promised, and no custom
periodic commit service is added. Use S3/R2 for production persistent media.

With an external `DATABASE_URL`, `IELTS_AUTO_MIGRATE` defaults to `false`;
explicit `true` is rejected. Embedded demo mode defaults to `true` and still
allows an operator to set `false`. Values other than `true`/`false` fail before
process startup. The external migration function above is a separate operator
step, not a startup action. External mode never acquires the demo database guard
or commits its PostgreSQL Volume.

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
curl.exe --fail https://YOUR-WEB-URL.modal.run/api/v1/ready
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


## P4 offline verification limit

Composition/runtime tests mock the Modal SDK, subprocesses and network probes.
They verify topology, Secrets, migration selection, shutdown ordering and proxy
contracts. They do not deploy Web, run GPUs, perform a real migration, measure
Volume durability, or prove live database/bucket connectivity. See the
[four deployment profiles and EC2 guide](aws-deployment.md) and
[storage portability progress](storage-portability-work-in-progress.md).
