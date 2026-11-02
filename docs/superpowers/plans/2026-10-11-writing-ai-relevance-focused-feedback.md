# Triển khai relevance và focused feedback cho Writing AI

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Writing AI relevance and focused feedback implementation. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/mts_writing.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Đặc tả đã duyệt: [Writing AI relevance gate và focused-practice feedback snapshot](../specs/2026-10-11-writing-ai-relevance-focused-feedback-design.md).

Baseline: `f5b1ea83a7faf4cf8643c084475eb5f964b3d1d0`.

1. Tái hiện và sửa stale descriptor-fit budget assertion: Task 1 TA là4096; các scores khác vẫn3072. Chạy focused tests tương ứng.
2. Thêm relevance schema/helper và Task 1/2 orchestration tests đang fail. Triển khai conservative text-only classification, stable source lookup, một repair, fail-open diagnostics và deterministic TA/TR1.0 chỉ khi HIGH+WHOLLY_UNRELATED. Giữ linguistic work độc lập; Task 1 claims/facts/specialist đợi sau grounding và gate.
3. Bao phủ durable relevance result/event replay và historical parsing. Tăng Task 1 composite/scoring lênv8 và effective Task 2 lênv8; giữ visualv3 cùng calibration/budgets hiện có. Chỉ cập nhật fake providers/regression expectations cho execution chủ đích đổi.
4. Thêm focused snapshot integration/API tests đang fail cho ownership, scope, source-run validation, forged bodies, replacement/concurrent UPSERT, deletion cascade và official-score isolation. Thêm một bảng sau Alembic head `20261010_0022`; expose nullable GET và source-run-only PUT.
5. Thêm frontend API/RTL tests đang fail cho ADMIN behavior, USER focused save/update, full/mock exclusion, saved advisory card, relevance, historical results và task-tab observation safety. Dùng review/assessment components hiện có để thêm EN/VI strings/CSS riêng.
6. Cập nhật `docs/ai-writing.md` và current benchmark version metadata, không sửa approved spec/frozenv5prompts. Chạy focused Writing pytest/Vitest, changed-file Ruff/ESLint, typecheck và `git diff --check`. Review logical commits, push `origin/main`, xác minh remote HEAD và working tree sạch.

Validation dùng fake providers và local PostgreSQL test database cách ly. Không browser, E2E, dev server, live inference, Modal, GPU hoặc deployment.

## Kiểm chứng đã hoàn tất

Tái hiện CI ban đầu: `uv run pytest tests/test_mts_descriptor_fit.py -q --tb=short` tạo bốn Task 1 failures đã báo. Sửa assertion cho95tests pass, không đổi production scoring budgets.

Từ `backend/` với PostgreSQL cách ly tại localhost:55433:

```powershell
uv run pytest tests/test_writing_relevance.py tests/test_writing_ai_practice_feedback.py tests/test_writing_ai.py tests/test_task1_visual.py tests/test_task1_writing_ai.py tests/test_task1_calibration.py tests/test_writing_completion_budgets.py tests/test_mts_descriptor_fit.py tests/test_writing_concurrency.py tests/test_task1_benchmark.py tests/test_writing_ai_observer_lifecycle.py tests/test_mts_writing_v3.py tests/test_mts_writing_v4.py tests/test_mts_writing_v5.py tests/test_writing_ai_output_normalization.py tests/test_task1_grounding_regression.py tests/test_task1_grounding_contract.py tests/test_mts_writing_validation.py -q --tb=short
```

688tests pass. Sau khi thêm năm visual-family/compact-context cases và tăng kiểm tra real mismatched-attempt case:

```powershell
uv run pytest tests/test_writing_ai_practice_feedback.py tests/test_writing_relevance.py -q --tb=short
uv run pytest tests/test_mts_descriptor_fit.py tests/test_chart_cross_check.py -q --tb=short
```

Lần lượt75 và159tests pass; các tập này overlap combined run. Chart regression hiện kiểm unusable primary grounding không khởi động specialist work, đồng thời giữ TA failure và linguistic results.

Migration upgrade, downgrade về `20261010_0022` và re-upgrade pass. Chỉ một head: `20261011_0023`. `alembic check` tùy chọn chỉ báo model/migration mismatch có sẵn cho `ix_attempt_events_attempt_type`, được tạo ở migration `20260921_0010`; không có snapshot-table drift. Giữ nguyên index không thuộc scope này.

Từ `frontend/`:

```powershell
npx vitest run tests/writing-ai-practice-feedback.test.tsx tests/writing-ai-assessment.test.tsx tests/writing-ai-progress.test.tsx tests/writing-ai-api.test.ts tests/writing-review.test.tsx tests/writing-routing.test.tsx tests/focused-attempt-contract.test.ts
npm run typecheck
npx eslint src/features/writing/writing-ai-assessment.tsx src/features/writing/writing-ai-progress.tsx src/features/writing/writing-review.tsx src/features/writing/writing-ai-practice-feedback.tsx src/lib/api/writing-ai.ts src/lib/i18n/en.ts src/lib/i18n/vi.ts tests/writing-ai-api.test.ts tests/writing-ai-practice-feedback.test.tsx
```

108tests pass trong bảy files; TypeScript/scoped ESLint pass. Ruff check/format check pass cho Python files đã sửa/thêm theo `backend/pyproject.toml`; `git diff --check` pass. Không sửa approved spec/frozenv5prompts. Tests xác nhận orchestration, persistence/security và UI behavior, không chứng minh live-model accuracy hoặc pixel-perfect browser layout.

CI sau push tìm thêm một legacy HTTP mock trong `test_vllm_context_budget.py` (1failed,1456passed). Lệnh `uv run pytest tests/test_vllm_context_budget.py -q --tb=short` tái hiện được. Mock hiện trả dedicated relevance schema mà không tiêu scoring overrides, vẫn giữ năm scoring inferences, hai TA inferences, exact context clamps và một scoring repair. Relevance được đếm riêng là một completion768tokens; không cần đổi provider/scoring production code.
