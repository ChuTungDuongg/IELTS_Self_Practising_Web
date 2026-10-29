# Storage migration and reconciliation

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Storage migration and reconciliation. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/storage/migration.py).
> Đọc cùng [current module/guide](modules/assets-transfer.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

These are operator commands, not startup tasks. Run from a reviewed checkout
with Python 3.12+ and backend dependencies (`cd backend`, then `uv run python
../scripts/migrate_asset_storage.py ...`). No command provisions a bucket,
changes application configuration, deletes sources or overwrites differing bytes.
Cloud tests use the real S3 adapter with offline fake clients, not live buckets.

## Independent configuration

The tool never reads `backend/.env`. Export `DATABASE_URL` explicitly for the
source reference inventory. Only PostgreSQL URLs are accepted; remote URLs must
use `?ssl=require`, `verify-ca` or preferably `verify-full`. Supply certificate
paths through `PGSSLROOTCERT` (and client certificate variables when needed).
Other URL query options are refused, avoiding target overrides.

Each storage side uses its own prefix; replace `SIDE` with `SOURCE` or `DESTINATION`:

| Environment variable | Local | S3 | R2 |
| --- | --- | --- | --- |
| `SIDE_ENVIRONMENT` | Required: `development`, `staging`, `production` or `recovery` | Same | Same |
| `SIDE_STORAGE_ROOT` | Required absolute durable directory | Unused | Unused |
| `SIDE_S3_BUCKET` | Unused | Existing private bucket | Existing private bucket |
| `SIDE_S3_REGION` | Unused | Actual region | `auto` |
| `SIDE_S3_ENDPOINT_URL` | Unused | Normally omitted | HTTPS account `.r2.cloudflarestorage.com` endpoint |
| `SIDE_S3_KEY_PREFIX` | Unused | Safe relative prefix, or explicit bucket root | Same |
| `SIDE_AWS_ACCESS_KEY_ID`, `SIDE_AWS_SECRET_ACCESS_KEY` | Unused | Optional explicit pair | Required scoped token pair |
| `SIDE_AWS_SESSION_TOKEN` | Unused | Optional temporary credential | If applicable |
| `SIDE_USE_AWS_CHAIN=true` | Unused | Required opt-in if using IAM/normal SDK chain rather than explicit credentials | Unused |

Prototype `SIDE_S3_ACCESS_KEY_ID`, `SIDE_S3_SECRET_ACCESS_KEY` and
`SIDE_S3_SESSION_TOKEN` aliases remain accepted. Prefer AWS-named variables.
Do not export production credentials for a development operation. Use separate
roles/tokens and verified database/bucket/prefix combinations. An IAM-chain opt-in
may discover ambient AWS credentials, including an EC2 role; verify that identity
out of band. Never put tokens, DSNs or private reports into Git or shell history.

The dry-run report exposes a stable destination `target_id` derived from its
namespace, not credentials. Verify the actual root/bucket/account/prefix with the
operator's configuration, then confirm that ID explicitly before writes. A label
cannot prove account ownership. Cloud commands use HeadBucket to refuse a missing
or inaccessible bucket; an intentionally empty namespace still requires explicit
confirmation. Local overlapping directories and overlapping prefixes in the same
cloud bucket are refused, including AWS regional/global endpoint aliases.

## Commands

Example shell configuration (all values are fictional; use secrets for real values):

```sh
export DATABASE_URL='postgresql+asyncpg://operator@127.0.0.1:5433/ielts'
export SOURCE_ENVIRONMENT=development SOURCE_STORAGE_ROOT=/srv/bandpilot/storage
export DESTINATION_ENVIRONMENT=staging DESTINATION_S3_BUCKET=fictional-staging-assets
export DESTINATION_S3_REGION=us-east-1 DESTINATION_S3_KEY_PREFIX=staging/media
export DESTINATION_USE_AWS_CHAIN=true
```

From `backend/`:

```sh
# Inventory: metadata only; no bucket listing by default.
uv run python ../scripts/migrate_asset_storage.py --source local --inventory-only --report /secure/inventory.json
# Default dry-run reads/hashes sources and checks existing destination bytes.
uv run python ../scripts/migrate_asset_storage.py --source local --destination s3 --workers 2 --report /secure/migration.json
# Only after reviewing the destination target_id and stopping ALL writers:
uv run python ../scripts/migrate_asset_storage.py --source local --destination s3 --workers 2 --copy --confirm-target REVIEWED_TARGET_ID --maintenance-window --allow-cross-environment --report /secure/migration.json
# Reconfigure SOURCE_* to the destination, keeping the source PostgreSQL inventory:
uv run python ../scripts/migrate_asset_storage.py --source s3 --reconcile --expected-report /secure/migration.json --report /secure/reconcile.json
# Optional, potentially expensive listing (paginated for S3/R2), never deletion:
uv run python ../scripts/migrate_asset_storage.py --source s3 --reconcile --list-orphans --listing-limit 100000 --report /secure/orphans.json
```

Local→S3/R2, S3/R2→Local, S3→R2, R2→S3, distinct S3 namespaces and Local→Local
all use the same engine. Reports must be private `.json` files outside both local
asset roots. Preserve reports/checkpoints outside backups and source assets.

Every result records key, size, SHA-256, source/destination backend and status.
`copied` and `identical` mean bytes were verified, not merely accepted by PutObject.
`would_copy` is a successful preview, **not** a completed migration. Missing,
corrupt, invalid, inaccessible or conflicted objects produce exit 1. CLI argument
errors use argparse exit 2. No required unverified object can yield `complete=true`.
An interrupted run retains an atomic checkpoint; rerun the same command to resume.
The tool always re-hashes existing objects rather than trusting checkpoint claims.
Failed writes/unknown acknowledgements may leave destination candidates; identical
ones are safely reused, differing ones block progress and require investigation.

Reconciliation checks expected database sizes and Speaking SHA-256 where stored.
`--expected-report` adds hashes recorded in a prior migration for every current
reference. Without a known digest it measures a baseline, not proof of original
content. It reports invalid keys, missing objects and integrity failures. Cleanup
keys and potential orphans remain diagnostics; no historical rows are modified.
Listings are bounded by `--listing-limit`; `listing_truncated=true` means orphan
inventory is incomplete even if all referenced objects passed verification.

## Cutover and rollback

This implementation requires a maintenance window for a **verified final copy**.
`--maintenance-window` is an explicit operator attestation, not an application-wide
lock. Stop Web writers and every independent/background writer: Speaking recording,
normalization/transcription/AI workers, Classroom uploads, cover replacement,
imports/exports, benchmarks and cleanup. Drain in-flight requests/jobs before
proceeding. Prevent scheduled jobs and other instances from restarting. No tool
can prove that an uncooperative writer elsewhere has stopped.

1. Take and verify a PostgreSQL + asset backup; retain it independently.
2. Preview migration; investigate all missing/conflicted/invalid records.
3. Freeze/drain all writers, then execute copy and final reconciliation.
4. Require full verified coverage of the current reference inventory and no
   unresolved errors. Retain the final manifest/report and source storage.
5. Change backend-only storage configuration explicitly; never change keys.
6. Restart under the new configuration and verify health plus authorized covers,
   diagrams, Listening seeking, Speaking playback, Classroom and historical review.
7. Resume writes only after operator acceptance. Keep the source and database
   backup through the agreed retention window.

Before new writes, rollback can restore the matching configuration/database snapshot
and preserved source. After new writes, configuration-only rollback is **unsafe**:
freeze again and reconcile/copy all newly referenced objects plus the matching
database state, or perform an explicitly approved recovery accepting data loss.
Never delete new objects, downgrade schemas or overwrite conflicting bytes as an
automatic rollback. Live provider permissions, large-file behavior and rollback
must still be rehearsed in a separate staging environment.
