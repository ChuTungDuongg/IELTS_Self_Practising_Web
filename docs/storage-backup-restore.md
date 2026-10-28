# Portable backups and isolated recovery

The original `scripts/backup.py` / `scripts/restore.py` local v1 format is retained.
Legacy cloud invocations still fail before changes. Add `--portable` for the new
executable provider-neutral v2 workflow. These are distinct from Test Transfer ZIP
schema v1/v2, which is unchanged.

Use a reviewed checkout, backend Python dependencies and PostgreSQL client tools
compatible with the source server (normally the same major version). Portable
operations use host `pg_dump`/`pg_restore`, with credentials in process environment,
not command arguments or reports. They do not automatically exec into a normal
development database container. The old local workflow retains its existing
verified Compose fallback. The AWS Web image deliberately has no PG client tools;
run operations from a separately prepared, secured operator environment with
the matching tools, not by assuming `docker compose exec backend pg_dump` exists.

## Consistency and contents

Stop/drain **all** writers as described in [migration](storage-migration.md).
`--maintenance-window` is mandatory for portable backup. It acknowledges an
operator-enforced write freeze, not a distributed lock. PostgreSQL inventory and
pg_dump share an exported read-only repeatable-read snapshot, and references are
checked again after copying. Objects use immutable keys, but storage and PostgreSQL
do not share a transaction. An external writer can invalidate a maintenance claim;
this is not an online atomic cross-system backup. Freeze cleanup/deletion too.

A completed private directory contains:

- `database.dump`: custom-format PostgreSQL logical backup, SHA-256 verified.
- `storage.tar.gz`: streaming archive of referenced objects only, not an entire
  bucket, with portable keys and original bytes.
- `manifest.json`: explicit `format_version: 2`, source backend/environment and
  hashed identities, per-object sizes/SHA-256/MIME/categories, file digests,
  consistency acknowledgement and `complete: true` only after verification.

Pending cleanup keys are diagnostics, not objects required for recovery. Orphans,
temporary FFmpeg/ZIP files, model caches and database directories are excluded.
All historical live references are included; this is broader than a public catalog
or Test Transfer ZIP. The backup contains private records and answer keys: protect
it as sensitive data, use restrictive operator permissions, encrypt at rest using
your backup platform, and retain an independently verified copy off the Web host.
No encryption key or credential is embedded in the manifest.

Failure/cancellation leaves a private `.backup-incomplete-*` directory and
`complete:false` manifest with a sanitized failure type. It is never promoted to
a completed backup. Keep it for investigation; rerun backup into a new bundle.
No source objects are deleted. Dump failures cannot become database-only success.
An in-flight dump/archive thread is joined before releasing its snapshot. Allow
space for the dump/archive and the adapter's per-object temporary spool.

## Create and verify

Set explicit `DATABASE_URL` and `SOURCE_*` as documented in the environment matrix
in [migration](storage-migration.md). From `backend/`:

```sh
uv run python ../scripts/backup.py --portable --source s3 --backup-root /secure/backups --maintenance-window --report /secure/backup-report.json
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --verify-only --report /secure/verify-report.json
```

Use `--source local` or `r2` with its independent configuration as appropriate.
Installed backend packages also support equivalent commands without repository
scripts: `python -m app.storage.recovery_cli backup ...` and
`python -m app.storage.recovery_cli restore ...` (omit `--portable` there).

Verification streams both files and every archive member. It rejects missing,
extra, duplicate, case-colliding, traversal, link, sparse, wrong-size or corrupt
entries without extracting archive paths. Manifest bounds are 64 MiB / 250,000
objects; each object follows the 5 GiB storage contract. The report records the
manifest SHA-256: retain that value independently in a trusted backup catalog.
Checksums detect corruption, **not** a malicious party able to rewrite both bundle
and manifest. Restore only trusted backups; PostgreSQL dumps can execute SQL code.
Inspect unfamiliar dumps in quarantine. PostgreSQL documents both
[exported snapshots](https://www.postgresql.org/docs/current/app-pgdump.html) and
[restore trust/behavior](https://www.postgresql.org/docs/current/app-pgrestore.html).

## Isolated restore, separately controlled database operation

Create a fresh private recovery bucket/prefix or local directory. Set
`DESTINATION_ENVIRONMENT=recovery` and explicit `DESTINATION_*` values. The
destination must differ from the backup source. Existing matching bytes can be
reused; any differing key blocks **all writes in that run**. Never use the active
application bucket as an accidental recovery destination. The tool never deletes
objects or replaces conflicts; a failed run can be resumed after investigation.

Provision an empty recovery PostgreSQL database yourself. Set
`RESTORE_DATABASE_URL` explicitly (not the ordinary application URL) and
`RESTORE_ENVIRONMENT=recovery`. Its name must contain the `recovery`, `restore`
or `test` token. It must differ from the source and application database, contain
no user relations and have no other sessions. Restrict access so no application
can race the preflight. The tool never creates/resets a database or starts a server.

```sh
# Full read-only preflight; emits destination target_id, database_id and manifest hash.
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --destination r2 --database-preflight --report /secure/preflight.json
# Recover object bytes first; complete remains false until database reconciliation.
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --destination r2 --restore-objects --confirm-target REVIEWED_TARGET_ID --confirm-backup REVIEWED_MANIFEST_SHA256 --maintenance-window --allow-cross-environment --report /secure/restore-objects.json
# Separate, explicit database restore after every destination object is verified.
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --destination r2 --restore-database --confirm-target REVIEWED_TARGET_ID --confirm-database REVIEWED_DATABASE_ID --confirm-backup REVIEWED_MANIFEST_SHA256 --maintenance-window --allow-cross-environment --report /secure/restore-database.json
# Resume verification if restore committed but its acknowledgement/report was lost:
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --destination r2 --reconcile-database --report /secure/restored-references.json
```

Database recovery uses one pg_restore transaction, `--no-owner --no-acl`, no
`--clean`, no `--create` and no schema downgrade. Recreate roles/grants separately
under operator control. Before restoring, all objects must already match the
bundle. Afterwards the actual restored database reference set and metadata must
match the manifest and readable destination objects. Only then can application
recovery report `complete:true`. A successful object upload alone is insufficient.
If database commit succeeds but follow-up verification fails, keep writers stopped;
objects/database remain for inspection and `--reconcile-database` can retry safely.
Never retry pg_restore into a populated database: its empty-target gate will refuse.

## Deployment profiles and rollback

Local development uses durable local roots and compatible client tools. Modal
demo operators must use a controlled maintenance environment with access to the
**same** embedded database and committed asset Volume, preserving the one-owner
database guard. Do not mount/start a second embedded PostgreSQL owner. Exporting
only the `/snapshots` legacy database dump is not a complete application backup.
Stage/commit a verified v2 bundle independently and retain original Volumes; do
not rely on Web shutdown alone for backup durability. A root mount symlink resolves
to its canonical namespace for explicit target identity; asset listing rejects
symlinks/junctions within that namespace.

Modal managed and AWS production use an operator host/job with secure access to
the external TLS database and configured private S3/R2. No tool depends on the
host being Modal/AWS. Existing P4 topology/Secrets/replica defaults remain unchanged.
This phase does not add an automatic Modal backup endpoint, scheduled job or
cloud deployment. In production, rehearse retrieval of independent backups and
the database/client-CA configuration, not just creation on the same host.

Retain source assets and their matching database backup before cutover. Rollback
before new writes may reuse them; after new writes it needs a new maintenance
window and reconciliation or an explicitly approved recovery point/data-loss
decision. See [cutover/rollback](storage-migration.md). Offline tests verify actual
PostgreSQL snapshot/dump/isolated restore and fake S3-backed object recovery;
live provider permissions, storage durability, throughput and disaster-recovery
drills remain separate operator-controlled staging gates.
