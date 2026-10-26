# BandPilot concurrency audit

Date: 2026-10-26. Baseline: `43fdc9d4cb0e8ba4f5e5e3f48beb06733de7b688` on `main`; fetched remote matched. Scope: targeted correctness changes within Next.js → FastAPI → PostgreSQL. Existing storage, provider infrastructure, UI, question registries, authentication contracts and advisory/human scoring boundaries remain.

Local unrelated changes (`storage` placeholders, `.agents`, `.taste-skill`, design references and skill lock) are excluded from delivery. Tests use freshly migrated, dedicated PostgreSQL 17 databases named `bandpilot_concurrency_test` and `bandpilot_concurrency_fault_test` on loopback port 5544. No development/production schema or data is modified. Provider tests use fakes; no browser sessions or paid inference.

## Confirmed defects and corrections

### C1 — Full Mock child/parent lock inversion (fixed)

- **Operation/actors:** last-module submit/timeout versus session `get`, `advance` or deletion; same `Attempt` and `TestSession` rows, separate connections.
- **Existing protection:** attempt `FOR UPDATE`, session `FOR UPDATE`, unique `(test_session_id, module_type)` partial index; Speaking already takes parent then child.
- **Failure:** generic submit held the attempt and later updated its parent. Session operations held the parent and updated/deleted its child. Both transactions could wait for the other. Timeout synchronization also used an unlocked, preloaded child snapshot.
- **Impact:** PostgreSQL deadlock aborts legitimate lifecycle operations; stale snapshots risk inconsistent finalization.
- **Evidence:** three forced overlapping transaction tests failed on baseline with `asyncpg.exceptions.DeadlockDetectedError`, including the `UPDATE test_sessions` wait. Coordination uses events and `pg_blocking_pids`, not sleeps.
- **Correction:** generic mutation loading now locks parent before attempt, matching Speaking; refresh locked ORM state. Timeout synchronization explicitly locks/refreshes child columns while retaining the parent collection. Remove the unnecessary eager-loading cycle back through sibling attempts.
- **Verification:** `test_mock_timeout_submit_and_session_operations_have_stable_lock_order[get/advance/delete]`; duplicate advance; independent Full Mock sessions. Existing module order, review locks and uniqueness constraints remain.

### C2 — Files left behind by upload rollback/cancellation (fixed for handled failures)

- **Operation/actors:** author asset upload, Speaking chunk upload and ZIP import; request cancellation or database flush failure after file creation.
- **Existing protection:** draft/attempt row locks and UUID storage names; Speaking/import had `except Exception` compensation, public upload had none.
- **Failure:** DB rollback cannot undo a file write. `asyncio.CancelledError` also bypassed `except Exception`.
- **Impact:** unreferenced files survive failed requests, including private speech recordings.
- **Evidence:** injected post-write flush failures leave public image files; cancellation leaves Speaking chunks and all three imported asset files. These assertions failed against baseline.
- **Correction:** compensation after transaction exit handles cancellation and ordinary errors, joins the public upload's file-writing thread before cleanup, and verifies committed references on a fresh session before removing operation-owned paths. Filesystem work is offloaded to a thread where appropriate.
- **Verification:** public image flush failure/cancellation and staging-thread cancellation; private chunk rollback/cancellation; import rollback/cancellation; all assert file/DB consistency using temporary storage directories.
- **Boundary:** process kill or a database outage that also prevents reference verification still requires reconciliation; see deferred risks. This is not a distributed filesystem transaction.

### C3 — Lost commit acknowledgement deletes committed media (fixed in chunk/import/version-clone paths)

- **Operation/actors:** a committing Speaking upload, ZIP import or version clone, followed by a connection error/cancellation before the caller observes success; DB rows and their physical files.
- **Existing protection:** generated paths and rollback compensation, but compensation assumed every exception meant rollback.
- **Failure:** transaction commits, context exit raises, unconditional compensation deletes files still referenced by committed rows.
- **Impact:** persisted asset/chunk records point to missing source files; recordings or cloned/imported content become unusable.
- **Evidence:** transaction wrappers commit successfully, then inject a lost-acknowledgement exception. Baseline private chunk, import and clone tests find committed rows with missing files.
- **Correction:** shared compensation checks public assets, raw Speaking chunks and normalized Speaking artifacts before unlinking; committed references win. If verification fails, retain potentially committed files and issue a content-free reconciliation warning.
- **Verification:** lost-commit-acknowledgement tests in `test_concurrency_hardening.py`, `test_speaking_media.py`, `test_transfer.py`, `test_asset_cloning.py`. Public upload covers both ordinary exception and cancellation after commit. ZIP roundtrip and asset IDs remain compatible.

### C4 — Unbounded concurrent upload allocations / synchronous copies (fixed for public upload)

- **Operation/actors:** simultaneous author image/audio uploads; RAM, event loop and Builder locks.
- **Existing protection:** 10 MB image / 100 MB audio validation in storage, applied only after `await upload.read()` allocated the entire input.
- **Failure:** each request reads arbitrarily large input before enforcing the limit, and then writes synchronously while holding authoring locks.
- **Impact:** avoidable memory exhaustion and lock/event-loop contention under moderate concurrent uploads.
- **Evidence:** baseline fails the bounded-read assertion. New storage test supplies 2 MiB with a 1 MiB limit and verifies reading stops at exactly limit + 1 byte with no output left behind.
- **Correction:** bounded stream reader uses at most 1 MiB chunks in a worker thread, before opening the authoring transaction. Existing MIME/extension/size limits and response DTO stay unchanged. Exclusive destination creation and ownership-aware copy cleanup avoid unlinking a preexisting path on creation failure.
- **Verification:** bounded read, oversize rejection, successful bytes/metadata, cancellation and rollback tests. Three additional independent-transaction tests pause the file writer while a competing transaction commits published/archived/deleted state, then verify the upload rejects the stale draft and removes its staged file. No application-wide concurrency limiter introduced.

## Existing protections retained and checked

| Area | Existing boundary and result | Evidence |
| --- | --- | --- |
| Answer/Writing autosave | Attempt lock plus per-answer/task revision. Identical committed payload replay does not increment revision; conflicting stale value returns established 409. Ownership filters remain. | Existing independent-connection `test_attempt_response_concurrency.py`; no evaluator or revision contract rewrite. |
| Autosave versus submit | Both serialize on attempt. First committed save is scored; submit-first rejects the delayed mutation. Server reads deadline after acquiring its lock. | New forced tests for both lock winners, deadline expiration while waiting, and another learner saving/submitting while the first attempt is held. |
| Frontend finalization | `RevisionAutosaveQueue.flush()` drains relevant workers; submit awaits it, reconciles ambiguous outcomes, and terminal lifecycle latch rejects delayed reopening. | Read all four requested hooks/queue/lifecycle files; existing Vitest autosave, draft recovery and lifecycle coverage retained. No frontend source change. |
| Full Mock uniqueness/order | Existing partial unique index prevents duplicate module attempts; parent serialization protects lazy next-module creation and review completion. | Existing Full Mock/Speaking history tests plus forced duplicate advance and session-isolation tests. Independent practice attempts remain supported. |
| Builder revisions/publish | Actor → test → version → resource locking, revision checks, draft/published partial unique indexes and unique version numbers. Publish waits for committed edit or editor receives immutable-version conflict. | Existing `test_test_version_concurrency.py` explicitly exercises both publish/edit interleavings and independent resource revisions. No new constraints required. |
| Moderation | Same version/test lock boundary freezes a pending submission; request row lock, terminal status check and unique notification key serialize decisions. | `test_moderation_concurrency.py`, governance tests; existing independent approval test verifies one publish and one notification. |
| Speaking media retries | Parent → attempt lock, unique segment/sequence constraints, checksum equality for identical replay, conflicting bytes rejected, closed contiguous manifest required before finalization. | Existing independently connected duplicate chunk test, manifest/finalization/recovery tests; new cancellation and ambiguous-commit tests. Durable private cleanup outbox retained. |
| Writing AI | Attempt lock deduplicates creation, `force=True` intentionally creates another run, run lock atomically claims only PENDING, terminal status guards checkpoints/completion/cancel, sequenced events serialize under run lock. | Existing Writing AI tests plus new independently connected create/claim/cancel tests with a controlled fake provider. Local task registry is only a dispatch optimization. |
| Speaking AI | DB run claim + lease token fence, heartbeat, token-checked checkpoints; committed cancellation cannot be reversed by stale worker. | Existing `test_speaking_ai_runs.py` independent create/claim, completion/cancel winners and stale restart/fencing tests. |
| ASR | Separate DB claim/lease/checkpoints, normalized-artifact/cache uniqueness, READY response reuse, restart preserves completed transcription. | Existing `test_speaking_transcript.py` independent worker claims, stale token, shutdown/recovery and replay tests. No real speech provider invoked. |
| Classroom/auth/admin | Classroom lock plus pending-invite/active-membership indexes; assignment start rechecks membership/archive/eligibility inside creation transaction; actor locks coordinate demotion. Refresh row lock permits one successor; requests reload account active status. Notifications use DB conflict handling. | Existing classroom, assignment, admin, notification and independent refresh-rotation tests; no process-local correctness locks added. |

## Recovery and remaining risks

1. **Verified recovery semantics, no rewrite:** Writing marks stale active runs FAILED (`STALE_RUN`) on get/list/create; retry creates a new run, and terminal guards fence the old one. Speaking AI/ASR recover PENDING and expired leases at startup; explicit create/retry also requeues stale work, preserving safe checkpoints. Existing APIs therefore provide a recovery path if commit preceded local task dispatch. No periodic global scanner is added. Unobserved work can wait for startup or an explicit retry; document this operational latency rather than claiming automatic continuous dispatch.
2. **Plausible/operational, deferred:** abrupt process death after file creation and before DB commit/compensation, or DB outage during ambiguity verification, can leave orphan files. Cleanup deliberately retains files whose committed status cannot be checked. A durable upload journal plus reference-aware reconciliation would address this; do not perform blind age-based deletion or silently claim crash-atomic storage. Existing Speaking cleanup outbox continues to cover committed deletions.
3. **Plausible, needs dedicated reproduction:** legacy inherited-asset repair has its own copy/exception cleanup paths in Reading/Listening/Writing; do not generalize version-clone verification to those paths. Further injected lost-commit tests are needed before expanding changes there.
4. **External side effects, deferred:** DB leases fence persisted results, not already-sent provider requests. Provider consumption immediately before crash/checkpoint can be repeated after retry without a provider-supported idempotency key. No claim of exactly-once external billing; `force=True` intentionally permits another assessment.
5. **Plausible contention, not reproduced as correctness failure:** ZIP validation/import copies and some existing storage cleanup remain synchronous; services may hold short DB transactions for content traversal. No measured pool exhaustion or unrelated-user serialization justifies a queue, global lock or pool change. Public upload's avoidable whole-file allocation is corrected directly.
6. **Auth overlap, no new defect demonstrated:** a refresh already in flight can overlap account disabling, but subsequent authenticated requests reload active account status. Existing token rotation and role/resource locks are retained; no speculative new token semantics.
7. **Preexisting schema metadata drift, deferred:** a clean Alembic upgrade and the single head (`20261013_0035`) pass, but the optional `alembic check` reports `ix_attempt_events_attempt_type` exists in migrations/database and is absent from ORM metadata. This index is already present at the baseline; no migration is changed or index dropped by this task.

## Verification and measurements

Focused regressions were first run against vulnerable paths: three real Full Mock deadlocks, public upload leak/unbounded read, two private chunk failures, two ZIP import failures and version-clone lost-acknowledgement failure. Corrected cases are rerun with existing related suites. Real concurrency uses independent PostgreSQL sessions/connections and explicit barriers; fault tests intentionally inject failures at flush or after successful commit. No task failure is silently counted as a successful result.

A bounded eight-connection save/submit smoke test forces all eight attempt locks to overlap and records distinct PostgreSQL backend PIDs, latency and persisted scores. The first measured local run used eight distinct connections: median 1306.7 ms, maximum 1310.7 ms for each save-plus-submit pair, including barrier wait, while other validation was running. This is loopback regression evidence, not a production capacity benchmark. No arbitrary global limiter or new queue infrastructure is introduced.

| Local check | Result |
| --- | --- |
| Full backend pytest | 2,603 passed, 2 skipped in 772.58 s on dedicated PostgreSQL. The additional three upload/lifecycle cases were validated separately in the 22-case focused-module run. Skips are existing Windows symlink guards (`test_modal_web_runtime.py`, `test_writing_benchmark_images.py`); no concurrency regression was skipped. |
| Focused backend lifecycle/storage/transfer suites | 78 passed; the new regression module was then extended with three upload/lifecycle interleavings and rerun: 22 passed. |
| Ruff lint and formatting | Passed; 362 Python files already formatted. |
| Frontend TypeScript and ESLint | Passed. |
| Full Vitest | 123 files, 1,406 tests passed with `--maxWorkers=2`. The first unbounded-worker run had an unrelated existing test timeout during parallel validation; the complete bounded-worker rerun passed without changing a test or timeout. |
| Alembic | Both dedicated databases upgraded cleanly to the single head `20261013_0035`; no migration changed. Optional metadata check reports the preexisting index drift documented above. |
| `git diff --check` | Passed for all delivery paths. |

Delivery is the commit containing this audit, on `main`. The user's final delivery instruction explicitly requests pushing and ending the task without monitoring CI; CI and Golden Path results for this delivery will therefore remain unverified here. No migration is needed; existing uniqueness/index guarantees are preserved.
