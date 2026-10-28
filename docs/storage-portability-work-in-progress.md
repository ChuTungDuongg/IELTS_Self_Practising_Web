# Storage portability: work in progress

Local asset storage remains the default. S3 and R2 can be selected after the P3
offline gates described below. No live cloud deployment, bucket access or real
asset migration was performed. Changing the backend never moves existing files.

## P3 COMPLETE — Configurable Local/S3/R2 verified offline

Starting local commit: `71272ea721a9324446c48e0d31d98ae571d71afa`.
Final focused verification: 98 offline configuration/SDK/contract/backup tests
passed, plus 99 selected domain/integration tests passed on disposable PostgreSQL.
One existing symlink test was skipped because this Windows host cannot create
symlinks; Linux CI covers that guard. Scoped Ruff, `uv lock --check --offline`
and `git diff --check` passed. S3/R2 are now selectable; local remains the default.
No application environment was switched, real cloud request made, or asset moved.

### Storage selection

Set backend-only environment variables in `backend/.env` or runtime secrets:

| Setting | Local | AWS S3 | Cloudflare R2 |
| --- | --- | --- | --- |
| `STORAGE_BACKEND` | `local` (default) | `s3` | `r2` |
| `STORAGE_ROOT` | durable local directory | unused for persistent media | unused for persistent media |
| `S3_BUCKET` | unused | required private bucket name | required private bucket name |
| `S3_REGION` | unused | actual AWS region | `auto` |
| `S3_ENDPOINT_URL` | unused | normally omitted | `https://<account-id>.r2.cloudflarestorage.com` |
| `S3_KEY_PREFIX` | unused | optional safe relative namespace | optional safe relative namespace |
| credentials | none | IAM role or standard AWS SDK chain; optional explicit AWS variables | required scoped token access/secret pair in `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |

`AWS_SESSION_TOKEN` is supported for temporary credentials. Credentials are
server-only, redacted in Settings and errors, and never embedded in frontend
configuration or asset rows. Use separate buckets or prefixes for environments;
changing a prefix also changes the physical object namespace. No fallback to
local storage occurs on configuration, permission or provider failures.

Startup validates settings and initializes the configured client in a worker
thread. It does not probe or create buckets; invalid credentials/permissions are
reported when the SDK resolves credentials or the first authorized object
operation runs. Local startup creates `audio` and `images`; cloud startup does
not touch `STORAGE_ROOT`. SDK clients are reused per configuration. Synchronous
object I/O runs in worker threads; cancelled writes are joined before rollback
compensation, and cancelled stream-open operations close their eventual body.
The adapter uses private Put/Get/Head/Delete operations, conditional create,
Content-Type and Content-Length, SigV4, 5s connect/60s read timeouts and at most
four total SDK attempts. Uploads spool bounded chunks to ephemeral disk rather
than buffering whole recordings. No ACLs, KMS or ETag-as-checksum assumptions are
required. SDK optional checksum headers are restricted to required operations
for S3 compatibility. ZIP continues to verify application-level SHA-256.

The existing backup and restore CLIs support Local only. With cloud selected they
fail before any database dump, restore or file replacement. Do not work around
this by pretending the active backend is local. P5 needs a maintenance-window
PostgreSQL backup plus a referenced-object inventory, copied bytes, SHA-256 and
size checks, missing-object detection, provider-aware restore and rollback.

Offline gates cover local/S3 contracts, boto3 Stubber calls, R2 configuration,
factory and startup selection, protected ranges, Speaking normalization/ASR,
Classroom authorization/downloads, clone/cleanup, ZIP v1/v2 cross-provider
round-trips and failure compensation on disposable PostgreSQL. Live staging
still must verify real IAM/R2 permissions, endpoints/TLS, provider retry behavior,
large uploads/seeking, latency, and independently restorable backups before
production cutover. No offline test proves that a particular live bucket is ready.

References: [R2 S3 compatibility](https://developers.cloudflare.com/r2/api/s3/api/),
[boto3 configuration](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html).

## P2 COMPLETE — Offline storage domain integration verified

Speaking chunk and normalized-WAV persistence, protected playback, Classroom
resources, covers, test assets, cloning, cleanup, and Transfer ZIP reads/writes
use storage operations. Normalization stores an opaque `speaking-derived/` key;
FFmpeg and analysis receive bounded temporary files. Cache validation distinguishes
missing or corrupt objects from provider outages. File-consuming worker threads
finish before their temporary file is removed, including on cancellation; local
ASR can therefore take longer than its requested timeout while a running thread
finishes. Playback streams authorized chunks with single-range support.

An offline PostgreSQL run exercised the real TransferService with Local and the
S3-compatible adapter with a fake client in all four source/destination
combinations, for both ZIP v1 and v2. It checked media bytes, cover bytes,
SHA-256 and size metadata, UUID remapping, published versions, unrelated private
media exclusion, repeated imports, storage failures, database flush failure and
compensating cleanup. Existing focused tests also cover malformed archives,
missing/corrupt covers, clone rollback, authorization, recovery and Speaking
concurrency. Two independent-session normalized-audio tests check concurrent
cache insertion and a lost commit acknowledgement. No live S3/R2 was contacted.

The focused P2 integration gates passed offline, including remote missing and
corrupt object rejection, end-to-end Classroom and transcription worker use with
the fake S3 client, and S3-backed clone cleanup. The application storage factory validates cloud configuration before selection. These tests do not establish production
cloud readiness or verify a live AWS/R2 service.

### Safely running the PostgreSQL tests

Provision a **separate, disposable**, loopback-only PostgreSQL database whose
name contains the `_test` token. Set `TEST_DATABASE_URL` to its asyncpg URL;
it must differ in host/port/database from the application `DATABASE_URL`. The
new fixture validates this before connecting and never resets or migrates a
database. For CI, `P2_TEST_DATABASE_URL` selects the separate service without
changing the existing concurrency tests' `TEST_DATABASE_URL`.

Apply migrations only to the explicitly provisioned test database, using a
single command with `DATABASE_URL` temporarily set to that test URL; restore
the normal value before running the new tests. For example, in PowerShell after
starting a disposable PostgreSQL service on a verified loopback port:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://p2tester:fictional@127.0.0.1:PORT/ielts_p2_test'
# In a separate process, set DATABASE_URL to that same disposable test URL and run:
uv run alembic upgrade head
# With DATABASE_URL restored to the ordinary app configuration:
uv run pytest tests/test_transfer_cross_storage.py tests/test_speaking_normalized_storage.py -q
```

Never use this setup on an existing application database. CI provisions a second
PostgreSQL service and migrates that service separately. The completed local
checks used an unnamed-volume, short-lived container and removed that container
afterwards. Test database credentials above are fictional.

### Filesystem audit

Local-only paths retained intentionally: FFmpeg input/output and normalized-WAV
staging, ZIP validation/import and export staging, model caches, and the local
adapter and explicit local benchmark input fixtures. Startup directory creation
is now restricted to local mode. The local backup/restore tool explicitly refuses
cloud mode until P5 provides cloud-aware operations. The domain services inspected
do not resolve persistent assets to local paths. Modal Volume durability remains unresolved.

P4/P5 remain deferred: Modal durability and cloud deployment configuration,
migration-CLI enhancements, and cloud backup/restore. Live staging validation
remains pending.

P4 prerequisite audit: application S3/R2 selection is implemented. Modal cloud
configuration and durability have not been completed or verified.
The uncommitted P4 runtime work offers the backward-compatible `IELTS_AUTO_MIGRATE=false` switch
for an externally coordinated database migration and preserves a configured
local `STORAGE_ROOT`; non-default asset Volumes must already exist. The default
demo still mounts its existing asset Volume and runs startup migrations. These
changes do not establish asset durability or AWS deployment readiness. Modal cloud
storage wiring, production container configuration, IAM and deployment verification
remain outstanding.

## Inventory and copy prototype

An uncommitted `scripts/migrate_asset_storage.py` prototype inventories references in `assets`,
`test_covers`, `classroom_resources`, `speaking_audio_chunks`,
`speaking_normalized_audio` and `writing_benchmark_samples`. It does not copy
unreferenced files or pending cleanup jobs. The database is read using a
read-only repeatable-read transaction; this is not an atomic snapshot of object
storage. Freeze uploads, deletes and background media processing while taking
the inventory and copying, and perform a final verified pass before cutover.

The operator must explicitly supply `DATABASE_URL` and source and destination
configuration in the environment. Each side is prefixed with `SOURCE_` or
`DESTINATION_`: local uses `STORAGE_ROOT` (absolute path); S3/R2 uses
`S3_BUCKET`, `S3_REGION`, optional `S3_ENDPOINT_URL`, `S3_KEY_PREFIX`,
`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` and `S3_SESSION_TOKEN`. R2 requires
an HTTPS endpoint; S3 can use the AWS SDK credential-provider chain. Keep these
values in a secure runtime environment and never commit credentials. The utility
does not change application settings, delete sources, or overwrite conflicts.
It checks size and SHA-256 instead of ETag. It defaults to a dry run; `--copy`
is required for writing and `--workers` is bounded to 1–8. A nonzero exit or
any missing, conflicted, failed or unverified object blocks cutover.

The utility is not a complete backup: make a separate PostgreSQL logical backup
and verify that every referenced object has an independently restorable copy.
Keep the original storage and database snapshot until restore and rollback have
been tested. Resume is safe for successfully copied matching objects, but a
conflicting or partially copied destination requires operator investigation and
is never overwritten automatically. Do not run against production until the
full integration and operational procedure have been reviewed.
