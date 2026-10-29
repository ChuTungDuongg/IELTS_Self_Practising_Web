# Portable private asset storage

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Portable private asset storage. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/storage/factory.py).
> Đọc cùng [current module/guide](modules/assets-transfer.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

PostgreSQL owns identity, ownership, lifecycle and relationships. Asset rows store
portable relative keys, never provider URLs. The application selects Local (the
default), S3 or R2 through `app/storage/factory.py` and existing `Settings`.
FastAPI authorizes private media before streaming it; no recovery command makes
Speaking media or buckets public. TestVersion identity/history is unchanged.

Persistent references are inventoried without active/published filters:

| Database source | Assets / lifecycle |
| --- | --- |
| `assets.relative_path` | Reading diagrams, Writing images, Listening audio; all draft, archived and historical versions, including unused uploads still owned by a version |
| `test_covers.relative_path` | Current test-owned covers |
| `classroom_resources.storage_key` | FILE resources, including archived resources |
| `speaking_audio_chunks.storage_key` | Private takes/chunks, including retained inactive takes; expected size/SHA-256 from PostgreSQL and MIME from segment |
| `speaking_normalized_audio.storage_key` | Retained normalized WAV/cache objects |
| `writing_benchmark_samples.task1_image_key` | Benchmark images, including draft samples |

`speaking_media_cleanup` is a pending-deletion outbox, not a live reference. Its
keys are reported separately. The table has no failure flag; a pending job is
not automatically described as failed. Reconciliation can identify jobs whose
objects still exist, but never runs cleanup. If references and cleanup overlap,
the reference remains required and must not be deleted.

FFmpeg and ZIP staging, model caches, PostgreSQL files and backups are not ordinary
asset references. Default migration/backup copies only referenced objects. An
explicit namespace listing reports potential orphans without deleting them; it
may also include legitimate temporary files, `.gitkeep` or processing remnants.
Never infer that an unreferenced object is safe to delete during live writes.

Operator tooling reuses the storage port. `migration.py` implements bounded copy,
checksums and read-only reconciliation; `operations.py` handles explicit source/
destination settings and database snapshots; `recovery.py` handles portable v2
backup bundles. The existing migration script and backup/restore entrypoints use
these modules. There is no second business storage architecture or dual-write mode.

Object operations use 1 MiB read buffers, 1–8 copy workers, bounded queued work and
the adapter's existing timeouts/retries/conditional creates. Objects are limited
to the existing 5 GiB single-object contract; backup metadata is bounded to a
64 MiB manifest / 250,000 objects. Metadata inventories remain O(number of rows).
S3 writes spool an individual object to temporary disk, so provision scratch
space for the largest object per worker. Backups additionally need disk space
for the database dump and compressed archive. No ETag is used as a digest.

Temporary cloud materialization remains explicit and bounded. Operations run
blocking SDK/PG/file work outside async database coordination; cancellation joins
an in-flight dump/archive write before releasing its exported snapshot. No new
bucket listing is added to application startup, HTTP routes or workers.

See [migration](storage-migration.md), [backup/recovery](storage-backup-restore.md),
[Modal](modal-web.md), [AWS](aws-deployment.md) and [verification status](storage-portability-work-in-progress.md).
Offline verification is separate from real IAM/R2/Modal, TLS/networking and
production restore drills. Nothing automatically migrates data when Settings change.
