# OpenAI Task 1 inference policy implementation record

> Execution: implement the user's detailed 2026-11-03 specification in this session, with test-first changes. No live inference, production changes, push or deployment.

**Goal:** Make Luna inference settings explicit and let Task Achievement check its extracted reference against the same trusted source image before publishing a score.

**Architecture:** Keep Chat Completions and existing rubric, facts, verifiers, score aggregation and public result contracts. Resolve OpenAI policy at the provider boundary; pass task/stage/criterion metadata through every wrapper. Only the OpenAI TA branch uses a bounded assessment envelope and independent second perception pass. vLLM retains its existing path.

**Baseline:** HEAD `f950d30c47dd4e40d7a0aba9a01b2014888ed9da`. Confirmed: Luna effort forced to none; completion cap is min(legacy cap, OpenAI cap); shared image serializer omits detail; TA score receives text only; structured perception repair requests shorter JSON and drops failed usage. Existing unrelated dirty files are preserved, including prior edits to `docs/modal-web.md`.

**Evidence limits:** No actual failed grading input/output or privately labelled benchmark bank supplied. Reasoning, image resolution, extraction/verification errors and holistic interpretation are hypotheses about TA quality, not established causes. Offline tests establish contracts, not band accuracy.

## Decisions and alternatives

- Retain Chat Completions: the official Luna model and Chat reference support the required parameters; Responses migration adds no necessary capability here.
- Separate provider policy from business output caps: 8192 low / 16384 important medium calls, 32768 bounded repair/safety ceiling. Reject incompatible old 4096 configuration rather than silently increasing a user's cap.
- Resolve conflicts before score checkpoint: an internal status/score/conflicts envelope, at most one independent image reread, then rebuild facts and claim extraction/verification and reassess. Unresolved/unreadable inputs fail TA while preserving independent criteria.
- Use existing benchmark CLI/bank for A–D dry-run plans. Block live ablation until a reliable preflight cost admission exists; finding an API key is never consent.

## Tasks

- [x] Provider/config: failing payload, policy, capability, usage, truncation, timeout and cancellation tests; implement typed policy and adapter-only detail. Keep failed/successful attempt usage exactly once; no timeout/5xx replay.
- [x] Callers/workflow: failing options propagation and TA image/conflict tests; implement envelope validation and one independent reread with refreshed facts/claims/evidence/feedback. Add explicit task/stage/attempt to Writing, Task 2 and Speaking callers.
- [x] Identity/telemetry: preserve output policy and checksum in scoring/perception identity; retain reasoning counters as an output subset; persist bounded safe status/attempt records and keep historical results readable.
- [x] Modal: test actual env forwarding and CPU-only composition, preserving secrets isolation and all existing user edits.
- [x] Benchmark: test A–D dry-run identities and opt-in gates; report missing data/quality metrics honestly.
- [x] Documentation/review: update canonical guides, run focused regressions and broader offline suite, inspect final diff and record real evidence and remaining limits.

## Review focus

- A valid JSON prefix with finish=length is never a score.
- A second schema attempt must not multiply budget repair indefinitely.
- Reconciled labels/numbers must refresh claim identities and public feedback together.
- An image/reference disagreement or unknown value must never become a student error by default.
- OpenAI-only configuration must not invalidate or change vLLM payloads/cache.

<a id="verification-record-working-tree-no-commitdeploy"></a>

## Verification record (working tree; no commit/deploy)

Tests were written and observed failing before their behavior changes. New TA workflow tests initially produced 17 expected failures (no image assessment/reconciliation), then passed. Speaking metadata, failed relevance usage, budget policy, cancellation accounting and admission-call counting each had independent red/green reproductions.

Independent review found and resolved: the inherited text relevance gate could publish TA=1 before image audit; late cancellation usage was blocked by the ordinary lease fence; benchmark counted pre-POST admission failures as calls; late invalid Speaking score could start a repair after durable Stop. The source-image branch now assesses relevance holistically, cancellation uses a one-use former-lease hash for metadata only, authoritative POST counters stay zero before send, and terminal accounting commits before stopping the scorer. No terminal score/status/event is revived.

From `backend/`, consolidated command:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_cancelled_provider_usage.py tests/test_openai_policy.py tests/test_openai_configuration_boundary.py tests/test_openai_caller_policy.py tests/test_openai_task1_assessment.py tests/test_openai_integration.py tests/test_openai_grading_contracts.py tests/test_openai_smoke.py tests/test_writing_completion_budgets.py tests/test_writing_concurrency.py tests/test_writing_ai_observer_lifecycle.py tests/test_task1_visual.py tests/test_task1_visual_numbers.py tests/test_task1_pie_claims.py tests/test_task1_grounding_contract.py tests/test_task1_grounding_regression.py tests/test_task1_feedback.py tests/test_task1_language_verification.py tests/test_speaking_ai.py tests/test_speaking_usage.py tests/test_modal_openai_policy.py tests/test_modal_openai_composition.py tests/test_modal_web_runtime.py tests/test_modal_app.py tests/test_task1_openai_ablation.py tests/test_task1_benchmark.py tests/test_task1_benchmark_metrics.py tests/test_task2_benchmark.py tests/test_task2_benchmark_cli.py -q -m 'not integration' --tb=short
```

Observed **781 passed, 1 skipped, 1 deselected**, 91.95s. A final narrower change made OpenAI relevance abort/error/unknown finishes terminal rather than schema-retry; its red cases failed at two calls, then this follow-up passed **109 tests**:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_openai_caller_policy.py tests/test_writing_relevance.py tests/test_openai_policy.py -q --tb=short
```

Full backend collection through a temporary offline prerequisite plugin: **2647 passed, 882 skipped, 2 dependency deprecation warnings**, 177.77s. Command from backend: `.venv/Scripts/python.exe C:/Users/Admin/AppData/Local/Temp/ielts_openai_offline_pytest.py` (local temporary guard, not a portable project test runner). The guard set DATABASE_URL to an unreachable local test-only address, cleared live key/test-DB variables, and skipped tests with db_session/isolated_db_session, integration markers, direct create_async_engine or isolated_staff_database prerequisites. No application/production database was contacted. PostgreSQL was unavailable and Docker daemon was not running; PostgreSQL race/SSE persistence tests are **not verified**. Initial broad attempts missed custom database prerequisites (29 setup errors and database guard failures); no application code was changed to conceal these. Final offline skips are explicit, not a claim that the complete database suite passed. Warnings concern existing FastAPI/Starlette httpx and AnyIO aliases.

Actual CLI dry-run with a temporary fictional one-pixel image/essay fixture: exit 0, one DEV sample, four planned A–D runs, `PLAN_ONLY_NO_INFERENCE`, `live_enabled=false`, requested ceiling 0.50 USD and `bound_verified=false`. Arbitrary fixture bands are not human adjudication and yield no quality result. Private Task 1/Task 2 banks contain only `.gitkeep`. A/B/C remain plan descriptors, not executable frozen transports; live A–D is rejected before provider creation until both frozen modes and reliable cost reservation exist. No MAE, bias, factual accuracy, stability, real latency or cost was measured.

Payload proof: `test_openai_grading_contracts.py::test_writing_task_pipelines_preserve_validated_results_through_openai_http[1]` decodes both HTTP image data URLs and checks exact input bytes; both grounding and TA send `image_url.detail=high`, `reasoning_effort=medium`, `max_completion_tokens=16384`. Other criteria contain no image. Policy/legacy budget tests prove OpenAI does not clamp to 128 while vLLM retains its caps.

Canonical operator documentation: `docs/ai-writing.md#openai-task1-reasoned-policy`, `docs/modal-web.md#cpu-web-openai`, `docs/writing-benchmark-bank.md#openai-luna-ablation`. Existing historical smoke artifact is unchanged and does not verify this new policy. Targeted Ruff and `git diff --check` were run; final handoff reports their actual outcome. No API inference, push, deploy, migration or production-data change.

Final independent targeted review reran all seven cancellation tests and found no remaining important issue in the reviewed Stop path. Targeted Ruff: all checks passed. `git diff --check`: exit 0 (only Git's existing Windows LF/CRLF conversion notices).

## Implementation map

| Responsibility | Files |
| --- | --- |
| Typed policy/config/payload | `backend/app/providers/writing_llm/{policy,base,openai,messages,http,__init__}.py`, `backend/app/core/config.py`, `backend/.env.example` |
| TA image assessment and refreshed dependencies | `backend/app/schemas/task1_assessment.py`, `backend/app/schemas/writing_ai.py`, `backend/app/domains/scoring/task1_prompts.py`, `backend/app/services/{task1_writing,task1_grounding,mts_writing,writing_execution,writing_relevance,task1_language_feedback}.py` |
| Shared Speaking metadata/history/accounting | `backend/app/providers/speaking_llm/configured.py`, `backend/app/services/{speaking_scorer,speaking_ai,speaking_ai_worker}.py` |
| Cancellation metadata fencing | `backend/app/services/cancelled_usage.py`, Writing/Speaking AI services/workers; `backend/tests/test_cancelled_provider_usage.py` |
| Benchmark identities/metrics/opt-in | `backend/app/evaluation/task1/{openai_ablation,models,runner,report}.py`, `backend/app/evaluation/task2/{models,runner}.py`, `backend/app/evaluation/writing/runtime.py`, `scripts/{benchmark_task1,benchmark_task2,smoke_openai}.py` |
| Modal | `deploy/modal/web_runtime.py`, `backend/tests/test_modal_openai_policy.py`, `backend/tests/test_modal_web_runtime.py` |
| Tests/docs | New OpenAI/caller/TA/ablation tests and existing provider/budget/benchmark regressions listed in the command above; canonical AI Writing/Speaking, Modal, benchmark guides, their README/audit/coverage links and this record |

No model, database schema, migration, frontend, authoritative score aggregation or copyrighted exam content was changed. Pre-existing `.gitignore`, launcher/skill files and the existing portion of `docs/modal-web.md` were preserved.

## Authorized Git handoff (2026-11-03)

After the implementation record above, the user explicitly requested commit and push to `main`. Fresh offline verification using the same prerequisite guard completed with **2651 passed, 882 skipped, 2 existing dependency warnings**, exit 0. PostgreSQL/live prerequisites remain unverified. The CI lint command, `.venv/Scripts/python.exe -m ruff check . ../scripts` from `backend/`, passed. The CI format check found four test files needing formatting; after formatting, all **506 files** passed `.venv/Scripts/python.exe -m ruff format --check app tests ../scripts`. AST comparisons confirmed formatting preserved test semantics, and a follow-up run of `test_modal_openai_policy.py`, `test_openai_configuration_boundary.py`, `test_openai_policy.py` and `test_writing_completion_budgets.py` passed **116 tests**, exit 0.

Only this task's implementation/tests/docs are staged, including only its OpenAI paragraphs in `docs/modal-web.md`. Pre-existing launcher, skill, screenshot and `.gitignore` changes remain outside this commit. No deployment or live inference was performed during this handoff.
