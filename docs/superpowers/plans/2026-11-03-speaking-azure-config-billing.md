# Azure Speaking configuration and billing safety

Start: `de3271b` on `codex/speaking-hybrid-v1`; do not reset the existing hybrid work.
Scope: provider/config/Secret/Modal wiring and billing failure handling, reusing the pipeline.
Canonical credential names remain `SPEAKING_AZURE_KEY/REGION/LOCALE`; no duplicate aliases.

- [x] Red/green tests for fail-closed billing, stable quota errors and safe reason codes.
- [x] Pin one configured key/region, no retry/fallback, checkpoint terminal failures.
- [x] Explicit `azure` ASR provider and CPU-only composition; retain legacy Modal/local adapters.
- [x] Forward backend-only credentials and policy through setup/launcher; test disabled ASR.
- [x] Prepare missing ignored dotenv fields without changing existing values.
- [x] Document canonical command, Secret refresh, operator tier declaration and rollback.
- [x] Run offline/native, worker, UI and regression checks; record live limitations.

Billing: default `ALLOW_PAID=false`, mode `unknown` blocks submission. Operator declares
`free_only` only for a resource/requested features verified outside the worker; `paid` also
requires explicit allow-paid. No ARM, pricing-tier mutation or fallback. SDK 429 remains
ambiguous unless the provider exposes a recognized subcode. No automatic retry.

Latest user instruction: no push or deployment; no live Azure/OpenAI calls.

## Actual verification

- Backend offline regression: **302 passed, 1 skipped** in 124.52s on dedicated
  PostgreSQL/Docker databases. Skip: Windows host cannot create a symlink.
- Final SDK cancellation fence/config/billing recheck: **47 passed** in 1.84s.
- Frontend Speaking suite: **154 passed**; ESLint and full TypeScript check passed.
- Ruff check/format, locked dependency validation and `git diff --check` passed.
- Actual Debian/Python 3.12 Docker native probe: `CPU_NATIVE_PROBE_OK`, no network,
  zero provider calls, GPU false. Fresh rebuilt CPU backend: `CPU_BACKEND_STARTUP_OK`,
  health/readiness passed against an isolated migrated DB, zero provider calls.
- User filled the ignored local key directly; real launcher `--provider openai --check`
  passed without displaying credentials or making provider requests. This validates
  configuration presence/policy/asset checks, not Azure authentication or account features.
- Topology mocks guard imports, app includes, URL resolution and GPU arguments for
  Azure/OpenAI; explicit Modal rollback and disabled ASR remain tested.
- No new browser visual pass, live Azure/OpenAI benchmark, Modal Secret update or
  Modal cloud build/deploy was performed. Cloud/F0 prosody/billing: **LIVE_UNVERIFIED**.

Canonical workflow and Secret replacement command are in
[Modal documentation](../../modal-web.md#azure-configuration-secrets-and-canonical-command).
