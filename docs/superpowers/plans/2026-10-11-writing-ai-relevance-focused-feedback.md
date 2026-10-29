# Writing AI relevance and focused feedback implementation

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Writing AI relevance and focused feedback implementation. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/mts_writing.py).
> Đọc cùng [current module/guide](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Approved specification: [Writing AI relevance gate and focused-practice feedback snapshot](../specs/2026-10-11-writing-ai-relevance-focused-feedback-design.md).

Starting baseline: `f5b1ea83a7faf4cf8643c084475eb5f964b3d1d0`.

1. Reproduce and correct the stale descriptor-fit budget assertion: Task 1 TA is 4096; other scores remain 3072. Run its focused tests.
2. Add failing relevance schema/helper and Task 1/2 orchestration tests. Implement conservative text-only classification, stable source lookup, one repair, fail-open diagnostics and deterministic TA/TR 1.0 only for HIGH + WHOLLY_UNRELATED. Keep linguistic work independent; defer Task 1 claims/facts/specialist until after grounding and the gate.
3. Cover durable relevance result/event replay and historical parsing. Bump Task 1 composite/scoring to v8 and effective Task 2 to v8; keep visual v3 and existing calibration/budgets. Update fake providers and regression expectations only for intentionally changed execution.
4. Add failing focused snapshot integration/API tests for ownership, scope, source-run validation, forged bodies, replacement/concurrent UPSERT, deletion cascade and official-score isolation. Add one table after Alembic head `20261010_0022`; expose nullable GET and source-run-only PUT.
5. Add failing frontend API/RTL tests for ADMIN behavior, USER focused save/update, full/mock exclusion, saved advisory card, relevance, historical results and task-tab observation safety. Implement dedicated EN/VI strings and CSS using the existing review/assessment components.
6. Update `docs/ai-writing.md` and current benchmark version metadata without editing the approved spec or frozen v5 prompts. Run focused Writing pytest/Vitest regressions, changed-file Ruff/ESLint, typecheck and `git diff --check`. Review logical commits, push `origin/main`, verify remote HEAD and clean working tree.

Validation uses fake providers and an isolated local PostgreSQL test database. No browser, E2E, dev server, live inference, Modal, GPU or deployment.

## Completed validation

Initial CI reproduction: `uv run pytest tests/test_mts_descriptor_fit.py -q --tb=short` produced the four reported Task 1 failures. Correcting the assertion gave 95 passing tests, without changing production scoring budgets.

From `backend/` (isolated PostgreSQL on localhost:55433):

```powershell
uv run pytest tests/test_writing_relevance.py tests/test_writing_ai_practice_feedback.py tests/test_writing_ai.py tests/test_task1_visual.py tests/test_task1_writing_ai.py tests/test_task1_calibration.py tests/test_writing_completion_budgets.py tests/test_mts_descriptor_fit.py tests/test_writing_concurrency.py tests/test_task1_benchmark.py tests/test_writing_ai_observer_lifecycle.py tests/test_mts_writing_v3.py tests/test_mts_writing_v4.py tests/test_mts_writing_v5.py tests/test_writing_ai_output_normalization.py tests/test_task1_grounding_regression.py tests/test_task1_grounding_contract.py tests/test_mts_writing_validation.py -q --tb=short
```

688 passed. After adding five visual-family/compact-context cases and strengthening the real mismatched-attempt case:

```powershell
uv run pytest tests/test_writing_ai_practice_feedback.py tests/test_writing_relevance.py -q --tb=short
uv run pytest tests/test_mts_descriptor_fit.py tests/test_chart_cross_check.py -q --tb=short
```

75 passed and 159 passed respectively; these sets overlap the combined run. The chart regression now checks that unusable primary grounding starts no specialist work, while TA failure and linguistic results remain intact.

Migration upgrade, downgrade to `20261010_0022` and re-upgrade passed. Exactly one head: `20261011_0023`. Optional `alembic check` reported only the pre-existing model/migration mismatch for `ix_attempt_events_attempt_type`, created in migration `20260921_0010`; no snapshot-table drift was reported. This unrelated index was left unchanged.

From `frontend/`:

```powershell
npx vitest run tests/writing-ai-practice-feedback.test.tsx tests/writing-ai-assessment.test.tsx tests/writing-ai-progress.test.tsx tests/writing-ai-api.test.ts tests/writing-review.test.tsx tests/writing-routing.test.tsx tests/focused-attempt-contract.test.ts
npm run typecheck
npx eslint src/features/writing/writing-ai-assessment.tsx src/features/writing/writing-ai-progress.tsx src/features/writing/writing-review.tsx src/features/writing/writing-ai-practice-feedback.tsx src/lib/api/writing-ai.ts src/lib/i18n/en.ts src/lib/i18n/vi.ts tests/writing-ai-api.test.ts tests/writing-ai-practice-feedback.test.tsx
```

108 tests passed across seven files; TypeScript and targeted ESLint passed. Ruff check/format check passed on changed/new Python files using `backend/pyproject.toml`; `git diff --check` passed. The approved spec and frozen v5 prompts were not edited. Tests establish orchestration, persistence/security and UI behavior, not live-model accuracy or pixel-perfect browser layout.

Post-push CI found one additional legacy HTTP mock in `test_vllm_context_budget.py` (1 failed, 1456 passed). The focused command `uv run pytest tests/test_vllm_context_budget.py -q --tb=short` reproduced it. The mock now returns the dedicated relevance schema without consuming scoring overrides, while retaining the five scoring inferences, two TA inferences, exact context clamps and one scoring repair. Relevance is counted separately as one 768-token completion; no provider/scoring production change was needed.
