# Run Next.js and FastAPI together on Modal

After the one-time setup below, from the repository root:

```powershell
modal serve deploy/modal/app.py
```

One command builds and starts the existing Next.js frontend, FastAPI backend and
a private PostgreSQL 17 process in one CPU container. Modal prints the public
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

The AI inference service is a separate protected GPU deployment documented in
[ai-writing.md](ai-writing.md). It scales to zero when idle. The web/database
container keeps one CPU replica running to preserve the PostgreSQL process.

## One-time setup

Authenticate the Modal CLI, deploy the LLM if wanted, and configure `backend/.env`
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
`modal serve` also shuts down its temporary deployment. Volumes and backups remain
available. Stop `ielts-writing-llm` separately if you no longer need AI inference.
