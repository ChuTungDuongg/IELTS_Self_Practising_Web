# Storage portability: offline implementation complete

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Storage portability: offline implementation complete. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/storage/operations.py).
> Đọc cùng [current module/guide](storage-architecture.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Local asset storage remains the default. S3 and R2 can be selected after the P3
offline gates described below. Changing the backend never moves existing files.

## Modal staging follow-up — 2026-10-28

A real, AI-disabled development deployment was verified with embedded PostgreSQL
17 and LocalAssetStorage on fresh, explicitly selected database/assets/snapshot
Volumes. Existing production resources were preserved. Only a synthetic snapshot
was uploaded; the ordinary local database was inspected read-only and not exported.
Alembic revision `20261028_0043` was confirmed in the running staging container.

Live HTTPS checks covered health/readiness, authenticated public catalogs,
image/audio/cover delivery, range requests, ownership failures, immutable published
versions, cloning, Transfer ZIP v1/v2, classroom resources and private segmented
Speaking. Real FFmpeg produced a one-second normalized WAV and its temporary stage
was cleaned. P5 inventory/dry-run/reconciliation verified 19 referenced objects;
a maintenance-window database/media backup was verified on Modal and again after
download. Database records, private raw/normalized audio and the backup survived
replacement of the Web container. This does not establish immediate durability
for an uncommitted upload: Modal demo Volume persistence remains asynchronous.

The test app was stopped and confirmed at zero tasks with no remaining containers.
Persistent staging Volumes and the dedicated Secret were retained for recovery.
Live S3/R2 connectivity, AI inference and production cutover remain unverified.
The detailed operational report and synthetic evidence are kept outside Git under
`.test-tmp/modal-live/`; no account credentials, dumps or recordings are committed.

CI follow-up preserves isolated PostgreSQL services and provisions a separate
disposable P5 recovery database. Actual CI failures exposed stale Builder mocks,
format drift, Python tar error mapping and an extra catalog cover query. Focused
regressions now cover those fixes. PostgreSQL health checks use TCP, and legacy
Volume guards are canonical across deployment modes. Final GitHub Actions status
is recorded in the local operational report after the fix push.

## P5 COMPLETE — Migration and recovery verified offline

Starting commit: `eeecfc6e39d604de2db234653be5c54da3c19623` (P4).
Prior gates: P2 `71272ea721a9324446c48e0d31d98ae571d71afa`,
P3 `a7ec5d0cf3f7a9599a40e9427ae793201e3be752`. The existing untracked
inventory/copy prototype was extended, not replaced by a second storage engine.

Migration supports Local/S3/R2 in both directions, including S3↔R2 and controlled
Local relocation. Independent explicit configuration, environment labels,
canonical namespace identities, overlap refusal, target confirmation and a
maintenance-window acknowledgement guard writes. Dry-run is default. Copy uses
bounded streams and 1–8 workers, checks source metadata and destination size/SHA-256,
never overwrites conflicts, and resumes by re-verifying existing bytes. Atomic
private JSON checkpoints are evidence, not a reason to skip verification.

The inventory covers all six persistent reference sources and all historical
versions/takes; cleanup-outbox keys remain separate diagnostics. Reconciliation
detects invalid/missing/corrupt objects, compares prior digests when supplied,
and optionally performs bounded paginated orphan listing without deletion.
Temporary FFmpeg/ZIP files, model caches and database directories are excluded
from ordinary asset copying. Remaining direct local access is limited to local
adapter/listing/output safety, legacy local backup, temporary staging and
deployment PostgreSQL/Volume responsibilities; no domain storage regression was found.

Portable `--portable` backup writes a versioned v2 bundle containing a real
custom PostgreSQL dump, referenced object bytes and a verified SHA-256/size/MIME
manifest. Inventory and pg_dump share an exported read-only database snapshot;
all independent writers must still be stopped because PostgreSQL and object
storage do not share a transaction. Failure leaves an explicitly incomplete
private bundle. Old local v1 backup/restore compatibility is retained.

Recovery defaults to verification/preflight. Object restoration is non-destructive,
conflicts block writes and matching objects support resumption. Database recovery
is a separate explicit command into an empty, inactive, distinct recovery database,
with reviewed target/database IDs and a pinned manifest hash. No --clean or reset
is used. Actual restored references and destination bytes must reconcile before
application recovery reports complete. Archive validation is streaming, rejects
unsafe members and bounds PAX/GNU metadata as well as ordinary object reads.

Final focused verification: **75 P5/legacy-backup tests**, including two real
PostgreSQL snapshot/dump/restore cases on a disposable tmpfs-backed PostgreSQL 17
container; **31 selected storage/domain regressions**; and **4 Classroom/cloning
integration regressions** passed. Total: **110 passed, zero failed, zero skipped**.
Two existing dependency deprecation warnings occurred in protected-media tests.
Scoped Ruff, offline lockfile, Compose config validation and diff checks passed.
Only the dedicated loopback test service was migrated/restored; no ordinary
development or production database was changed. The disposable service was removed
after verification. No cloud service was contacted, deployed or provisioned.

Runbooks: [architecture](storage-architecture.md), [migration and cutover](storage-migration.md),
[backup/restore](storage-backup-restore.md), [Modal](modal-web.md),
[AWS](aws-deployment.md). P4 topology, Secrets and replica defaults are unchanged.
Operator environments need compatible PostgreSQL client tools; the minimal AWS
Web image does not include them. Modal demo backup must preserve its one-owner
database guard, writer freeze and Volume durability limitations. Reports/manifests
contain no credentials; backups themselves contain private academic data and
must be secured and copied independently.

All implementation gates are offline. Real IAM/R2/TLS/Modal behavior, throughput,
durability, independent backup retrieval, disaster recovery and production cutover
remain separate staging/operator responsibilities. Maintenance flags attest to a
real operator-enforced freeze; they are not a distributed lock. Configuration-only
rollback after new writes is unsafe without reconciliation of the matching database
and newly referenced objects. No real asset migration or production restore occurred.

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

At the P3 gate, the legacy backup and restore CLIs supported Local only. With cloud selected they
fail before any database dump, restore or file replacement. Do not work around
this by pretending the active backend is local. P5 now supplies a maintenance-window
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

## P4 COMPLETE — Portable deployment configuration verified offline

Starting local commit: `a7ec5d0cf3f7a9599a40e9427ae793201e3be752`.
Final focused run: 122 passed, one existing symlink test skipped on this Windows
host, and two dependency deprecation warnings. Docker Compose configuration
validation, scoped Ruff, offline lockfile verification and diff checks passed.
The checks mocked Modal/processes/network probes and reused offline P3 storage
contracts. No images were built and no live database migration or cloud request
was made. P5 files remain uncommitted and outside this phase.

Modal demo keeps its original default Volume names, embedded PostgreSQL and one
Web container. Managed topology uses an external TLS database and selected S3/R2
adapter with no local persistent Volume dependency. Topology markers are frozen;
backend Secrets are validated at runtime. Dev-specific Volumes/Secrets and an
optional strict isolation setting are available without renaming or copying data.
Cloud Secrets require a matching dev/production label. Legacy demo Volume sharing
is warned explicitly.

Local asset durability remains a demo limitation: background Volume commits and
HTTP/database success are not an upload-specific durable acknowledgement. Reload
is startup-only, explicit commit follows stopped processes, and commit failures
are reported. No per-chunk commit or distributed synchronization subsystem was
added. The runtime can stage a public database CA certificate temporarily from a
Secret and removes it on shutdown. External Web startup never starts, initializes
or seeds embedded PostgreSQL; migration is an explicit operator function.

The EC2/Docker template adds HTTPS Nginx, separate backend/frontend containers,
readiness/health checks, non-root application processes, secret-file injection,
RDS CA mounting, S3 role/R2 token configuration and a separate migration profile.
Only ports 80/443 are published. Four profiles and commands are documented in
[the deployment guide](aws-deployment.md). Existing auth, API proxy, SSE, protected
media and AI transports are retained. No real deployment, database migration,
asset move or cloud call was performed. Builds and live TLS/cloud networking
remain unverified. P5 migration/inventory and backup/restore work stays separate.

## Earlier inventory/copy prototype (superseded by P5)

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
