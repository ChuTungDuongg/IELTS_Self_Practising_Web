# Admin Speaking Benchmark Lab — Phase 1

Baseline inspected: `7ed863b568f614ba7942f4f3130fefcac5857e82`. Existing untracked design/agent files are outside this change. This feature owns private benchmark samples, not learner attempts or the gradebook.

## Decisions

- Four additive PostgreSQL entities: owner-scoped samples, fenced CPU jobs, append-only review revisions, append-only human-label revisions. Approved manifests remain frozen in their review revision. Sample deletion uses the existing media-cleanup outbox before authorization rows disappear.
- Private original MP3/WAV objects use `AssetStorage.put_stream`, opaque keys under `benchmark/speaking/`, and the existing authenticated Range delivery. Bounded multipart spooling, actual ffprobe/decode validation and SHA-256 precede a DRAFT sample. Reserve a cleanup outbox entry before writing bytes; attach and remove the reservation in the same sample transaction.
- A separately launched worker claims PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`. Expiring leases, heartbeat tokens and fenced completion prevent stale results. CPU-only retries are bounded; cancellation stops the isolated subprocess. No Torch import, model installation, paid provider construction or HTTP background inference in FastAPI.
- Reuse `LocalDiarizer` and `propose_responses`. Extract pure manifest approval validation from `replay_segment_review` for both CLI and API. An explicit candidate confirmation, real questions, verified Part boundaries, an explicit long turn and overlap-free source windows are required. Suggestions never approve themselves.
- Local web/worker share PostgreSQL and AssetStorage. A separate remote CPU container entrypoint requires external PostgreSQL and R2/S3; embedded Modal PostgreSQL and local Volume storage are rejected. Existing Modal Web image is unchanged. Model assets are prepared once in a private persistent cache and inference stays offline.
- Native admin list/upload and detail workspace: one source audio player, speaker interval lanes, window playback, explicit review save/approve and separate human-label save. Existing BandPilot shell, tokens, controls, translations and AdminGuard are retained. Backend ownership and revision checks are authoritative.

## UI inventory and intent

An admin works through private 12–14 minute recordings, speaker identities, overlapping turns, three Parts, actual prompt context, selected candidate windows and independently sourced half-band labels. The detail screen answers: “Which parts of this recording are safe to add to the dataset?” Its distinctive element is the source-relative speaker timeline beside explicit human verification. There are no predicted bands, artificial KPI cards or invented dataset counts. Existing brand typography/palette take precedence over new art direction.

## Verification boundaries

Use disposable PostgreSQL, fake diarizer fixtures, synthetic audio and real FFmpeg where available. Test owner isolation, upload bounds, job claims/fencing/cancellation, replay-compatible approval, immutable history, provenance and authenticated ranges. Run a real CPU smoke only if an eligible authorized recording and pinned assets are present; report unmeasured throughput/accuracy explicitly. No paid inference, cloud deployment, commit or push is authorized by this task.
