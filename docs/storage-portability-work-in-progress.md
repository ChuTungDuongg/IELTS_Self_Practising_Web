# Storage portability: work in progress

Cloud storage is **not enabled** in the application. `STORAGE_BACKEND` must remain
`local` until protected delivery, Speaking, Classroom, test editing, transfer
imports, cleanup and backup/restore have all been integrated and verified. The
S3 client and migration utilities are experimental and have only offline tests.
Do not use them for a production cutover yet.

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
the fake S3 client, and S3-backed clone cleanup. The application storage factory
remains fail-closed for cloud providers. These tests do not establish production
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
adapter. The local backup/restore tool and startup directory initialization still
assume a filesystem; they are deployment/operations work for P3/P5 and must be
addressed before cloud activation. The domain services inspected do not resolve
persistent assets to local paths. Modal Volume durability remains unresolved.

P3/P4 remain deferred: enabling S3/R2, live-cloud checks, Modal durability and
cloud configuration, migration-CLI enhancements, and cloud backup/restore.

P4 prerequisite audit: P3 remains incomplete, and Settings and the storage
factory reject cloud mode. Modal therefore cannot yet use external asset storage.
The uncommitted P4 runtime work offers the backward-compatible `IELTS_AUTO_MIGRATE=false` switch
for an externally coordinated database migration and preserves a configured
local `STORAGE_ROOT`; non-default asset Volumes must already exist. The default
demo still mounts its existing asset Volume and runs startup migrations. These
changes do not establish asset durability or AWS deployment readiness. Cloud
storage, production container configuration, IAM and deployment verification
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
