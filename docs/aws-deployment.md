# Portable deployment profiles

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Portable deployment profiles. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../deploy/aws/compose.yml).
> Đọc cùng [current module/guide](handbook/infrastructure.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

P4 supplies configuration and offline checks. No AWS/Modal infrastructure was
created, no image was built, and no live deployment or migration was performed.
P2/P3 remain the application/storage foundation.

| Profile | PostgreSQL | Persistent assets | Entry point / proxy | Migration policy |
| --- | --- | --- | --- | --- |
| Local development | Existing Compose PostgreSQL on host port 5433 | `STORAGE_BACKEND=local`, host `storage/` | Existing Next/FastAPI development commands from README | Operator `uv run alembic upgrade head` against the intended local database |
| Modal demo | Embedded PostgreSQL 17; original dev/production database Volumes | Local `/storage`, original `ielts-web-assets` unless explicitly overridden | `deploy/modal/app.py`, Next + FastAPI + Nginx on the existing Modal HTTPS URL | Embedded startup migration default retained; one Web container and database guard |
| Modal managed | External PostgreSQL via private Secret, TLS required | S3 or R2; no local asset Volume | Same Modal entry point, backend-only Secret and frozen topology markers | Web migration disabled; operator runs `migrate_database` once before starting writers |
| AWS EC2/Docker | External RDS or managed PostgreSQL, TLS | S3 instance role or private R2 token | `deploy/aws/compose.yml`, TLS Nginx → Next/FastAPI | Explicit `tools` profile migration container; no Web startup migrations |

Local profile keeps the existing `docker-compose.yml`, ignored `backend/.env`,
and frontend `.env.local`; it needs no cloud account. Existing auth/CORS settings
and `STORAGE_ROOT` remain valid. See [README](../README.md) for local commands.
See [Modal guide](modal-web.md) for demo/managed commands, Volume names and
environment isolation. For cloud profiles, only temporary processing data lives
in container filesystems. Changing a bucket/prefix does not copy referenced bytes.

## EC2/Docker configuration

The template runs three application containers with restart policies and health
checks. Only Nginx exposes host ports 80/443. Backend/frontend ports are reachable
on the private Compose network. No production database runs in these containers.
No user media Volume is mounted: P3 Settings require `s3` or `r2`. Backend runs
as a non-root user with a read-only root filesystem and bounded `/tmp` scratch;
frontend cache remains ephemeral. Configure host capacity for the declared
memory/CPU limits and workload. Do not raise worker/replica counts as part of setup.

Before operating, separately prepare an EC2 Linux host with Docker Compose,
managed PostgreSQL, private storage, DNS and a valid TLS certificate. These are
operator prerequisites, not resources created by this repository. Restrict host
ingress to HTTPS/HTTP redirection and necessary administration; permit database
access only from the application host's security group. Do not publish port 5432.

From the repository root, make private copies of the examples:

```sh
cp deploy/aws/compose.env.example deploy/aws/compose.env
cp deploy/aws/backend.env.example deploy/aws/backend.env
```

Build from a reviewed commit checkout so unrelated uncommitted work does not
enter image inputs. Fill the ignored files from secure runtime configuration/secret management.
`compose.env` holds non-secret routing and file paths. `backend.env` is injected
only into backend and migration containers; frontend receives no DB/cloud/AI
credentials. Limit its file permissions to the operator. Docker administrators
can inspect container environments; restrict host/Docker access accordingly.

Set `SITE_DOMAIN`, `DB_CA_FILE`, `TLS_DIRECTORY` and a revision-specific
`BANDPILOT_IMAGE_TAG`. Mount an independently obtained certificate chain and
private key as `fullchain.pem`/`privkey.pem`; make the key readable by Nginx's
UID/GID 101 without making it public (for example, an operator-managed group
and mode 0640). Provide a database CA bundle readable by backend UID 10001.
Bind mounts refuse missing paths rather than creating empty directories.
Certificate acquisition/renewal is outside this template. Reload/recreate proxy
after safely renewing certificates; test this procedure in staging.

Use a URL-encoded database password and a URL such as
`postgresql+asyncpg://user:ENCODED_PASSWORD@host/database?ssl=verify-full`. The container sets
`PGSSLROOTCERT=/run/secrets/database-ca.pem` from `DB_CA_FILE`. Use the managed
database provider's CA and correct hostname. RDS documents
[PostgreSQL TLS and certificate validation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html).
The runtime accepts TLS-required modes; prefer hostname verification in production.
Alembic configuration preserves percent-encoded credentials.

Compose sets HTTPS `FRONTEND_ORIGIN`, secure cookies and
`IELTS_AUTO_MIGRATE=false`. Generate a unique `JWT_SECRET` of at least 32
characters; preserve the existing JWT settings when retaining sessions. Keep
default cookie names. Set the existing Google OAuth credentials and callback to
`https://YOUR_DOMAIN/api/v1/auth/oauth/google/callback` if OAuth is enabled.
Existing protected AI endpoint credentials stay in `backend.env`; AI is disabled
in the example until explicitly configured. This task did not alter AI services.

Browser requests use `/api/v1`; Next server requests use
`http://backend:8000/api/v1`. Nginx preserves paths, auth/cookies, byte ranges and
unbuffered SSE, forwards HTTPS, and permits 310 MiB request bodies for the existing
300 MiB ZIP limit plus multipart overhead. Align proxy limits if app upload limits
are changed. The API remains authoritative for upload size and authorization.

## Storage credentials

For S3, use `S3_BUCKET`, its actual `S3_REGION`, and optional `S3_KEY_PREFIX`.
Prefer an EC2 instance role with the example
[bucket/prefix policy](../deploy/aws/s3-iam-policy.example.json); replace its
fictional bucket and prefix. It grants object read/write/delete only under that
prefix. Bucket-level ListBucket permits negative HEAD checks to distinguish
missing objects from access denial; use a dedicated private bucket. See
[S3 HeadObject permissions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html).
No ACL, public bucket, Object Lock or KMS dependency is introduced.

The SDK uses the normal credential chain. Make IMDSv2 reachable from the backend
container when using the host role; container networking can require metadata
response hop limit 2. Apply instance policy deliberately and test it in staging;
see [EC2 metadata configuration](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-new-instances.html).
Frontend and proxy never receive static storage credentials; an instance role
is host-wide infrastructure, so restrict workload/metadata access appropriately.

For R2 set `STORAGE_BACKEND=r2`, `S3_REGION=auto`, its HTTPS account endpoint,
and scoped `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in backend runtime secrets.
Keep the bucket private. Use separate verified databases and buckets/prefixes for
dev/staging/production. No switch automatically migrates Local/Modal assets.

## Controlled rollout and migration

The following are operator commands, documented but **not executed in P4**:

```sh
# Does not expand backend secret-file values into console output:
docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml config --no-env-resolution --quiet
docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml build backend frontend
# During a write-free maintenance window, after verified independent backups:
docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml --profile tools run --rm --no-deps migrate
docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml up -d backend frontend proxy
```

Run only one migration operator at a time, with all prior Web writers stopped.
Use a separate schema-owner secret file for the migration when needed, selected
through `BANDPILOT_BACKEND_ENV`; restore the application-role file for Web.
The tools profile never starts automatically and Web never invokes Alembic.
No reset/restore is performed by startup. Keep the previous image and a tested
rollback plan; an old image is safe only with a compatible schema. Cloud database
restore and asset rollback follow [P5 recovery](storage-backup-restore.md), never an automatic downgrade.

`/api/v1/health` remains liveness; `/api/v1/ready` does a bounded read-only database
probe and returns a generic 503 on failure. Compose gates frontend/proxy startup
on health. Docker restart policies handle exited processes; an unhealthy running
container does not automatically restart solely because of health status.
Monitor it and investigate dependency errors. Health checks do not prove bucket
permissions or verify every stored object. Validate login/logout, OAuth, SSE,
uploads, playback seeking and AI transports in a real staging environment.

## Remaining operations

Images and Nginx have only static configuration checks here; no Docker build or
live TLS, AWS IAM/RDS, R2, Modal durability or cloud networking test was performed.
P5 supplies [inventory/copy/resume/reconciliation](storage-migration.md) and
[portable backup/isolated restore](storage-backup-restore.md). Run these from a
secured operator environment with backend dependencies and matching PostgreSQL
client tools; the minimal Web image does not install pg_dump/pg_restore. Supply
independent SOURCE_/DESTINATION_ settings and role/token access, not frontend
credentials. Legacy backup still refuses cloud mode; use the explicit portable
workflow. Rehearse write-freeze consistency, independent backup retrieval and
rollback in staging. Keep real cutover separate from offline implementation.
