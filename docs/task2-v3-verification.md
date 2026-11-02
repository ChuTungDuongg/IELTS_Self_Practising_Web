# Kiểm chứng Task 2 v3 — 2026-10-08

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Kiểm chứng Task 2 v3 — 2026-10-08. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/services/mts_writing.py).
> Đọc cùng [hướng dẫn module hiện hành](ai-writing.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

1. **Nguyên nhân gốc của lỗi LR trước đây:** model sinh quote, sau đó phép so khớp exact/conservative Unicode-whitespace từ chối khác biệt dấu câu hoặc sao chép bằng `QUOTE_NOT_EXACT`. Evidence response sai lần thứ hai thoát khỏi sequential loop, khiến GRA không chạy. Kết nối provider vốn đã hoạt động.
2. **Định danh evidence:** model v3 chỉ chọn `source_id` và `assessment` ngắn bằng tiếng Việt; `focus` tùy chọn không quyết định validity và không được lưu. ID không tồn tại được repair có mục tiêu một lần, rồi chỉ criterion đó thất bại. Vẫn giữ bốn cặp evidence/scoring độc lập.
3. **Phân đoạn:** hàm thuần xác định `essay_sources.segment_essay` đánh số các paragraphs không rỗng tách bằng blank lines và chia câu thận trọng. Hàm giữ original Python character offsets và exact slices; hỗ trợ CRLF/LF, câu lặp, abbreviations/decimals, quotes, apostrophes, dashes, nhiều spaces và Unicode terminal punctuation. Mỗi segment được kiểm với `essay[start:end]`.
4. **Trích dẫn chính xác:** backend tra source map để đưa `source_id`, nguyên văn `quote` và assessment vào snapshots/SSE. v3 không gọi legacy quote matching. Câu gốc dài không còn vướng model-copy limit 600 characters trước đây. Evidence tiếng Anh không bao giờ bị dịch.
5. **Prompt/fingerprint:** `mts-task2-v3`. Cấu hình v1/v2 dùng effective v3, custom labels cũng bao gồm v3. Lịch sử hoàn tất cũ vẫn đọc được nhưng không tái sử dụng làm v3 cache. Integration tests bao phủ cả hai old versions.
6. **Finish reasons:** transport đọc và làm sạch metadata, giữ stop/length/abort/error cùng safe buckets cho other, missing, filter hoặc tool reasons. Đã đối chiếu semantics của vLLM 0.13 với primary source. Length bị từ chối ngay cả khi JSON trông hoàn chỉnh; chỉ cho phép đúng một repair ngắn hơn. Evidence tối đa 4 items, assessment tối đa 320 characters và prompt yêu cầu hai câu ngắn. Giữ guided JSON output, temperature 0/seed 0 và vLLM budget 1800 tokens hiện có. Không tăng global token budget, đổi deployment hoặc chạy GPU job.
7. **Cô lập lỗi và hoàn tất:** lưu/phát `criterion.failed`, sau đó tiếp tục traits còn lại. TA/CC thành công + LR lỗi + GRA thành công kết thúc FAILED, có ba kết quả hiển thị nhưng không có raw mean/overall. Chỉ khi cả bốn thành công mới tạo COMPLETED và aggregates. Shutdown/stale recovery cũng giữ criterion bị gián đoạn cùng các lỗi đã có trước đó.
8. **SSE/UI:** completed cards và Bands hiện ngay. Giữ đúng bốn vertical steps với styling completed/active/waiting/failed và reduced-motion support. Live counts phân biệt successes/errors/current work. Final failure notice chỉ xuất hiện ở terminal state. Persisted snapshots, sequence replay và reconnect giữ completed cards/individual failures mà không khởi động lại inference. Heartbeats chỉ phục vụ liveness.
9. **Tiếng Việt và calibration:** prompts yêu cầu rõ assessments, feedback, strengths, improvements và comparison summaries ngắn bằng tiếng Việt; safe errors/progress cũng bằng tiếng Việt. Chỉ dùng bốn official IELTS criteria. Official Task 2 descriptors hiện hành, publication cập nhật May 2023 và kiểm ngày 2026-10-08, được diễn giải trung thực, gồm lower bands và phân biệt scope/extent. Scoring so adjacent whole-band descriptors một cách holistic; half-bands là nội suy. Điểm cao cần affirmative justification ngắn trong cùng scoring interaction. Backend kiểm source IDs, comparison structure, next official whole-band value và việc không có impossible higher-band blocker tại 9. Không có hằng số trừ điểm, quy tắc đếm lỗi hoặc deterministic severity caps. Prompts yêu cầu score/feedback nhất quán. Fake tests xác nhận contract, không chứng minh real-model calibration với human scores.
10. **Kiểm chứng có chọn lọc:** các lệnh dưới đây đều pass. PostgreSQL integration dùng temporary local `postgres:17-alpine` container cách ly tại port 55433, migrate bằng Alembic migrations hiện có rồi stop. Toàn bộ automated grading dùng fake providers. Lần thử ban đầu với configured local DB không sẵn sàng được dừng và chạy lại trên DB cách ly. Initial red tests và review regressions được sửa trước final runs. Không chạy unrelated suites, browser hoặc Playwright.

```text
# backend (DATABASE_URL directed to the temporary test database)
uv run pytest tests/test_essay_sources.py tests/test_mts_writing_v3.py tests/test_mts_writing_validation.py tests/test_writing_llm_providers.py tests/test_writing_llm_readiness.py tests/test_writing_ai.py -q --tb=short
# 170 passed in 20.36s

uv run ruff check app/api/v1/writing_ai.py app/core/config.py app/domains/scoring/essay_sources.py app/domains/scoring/ai_writing_validation.py app/domains/scoring/mts_prompts.py app/providers/writing_llm/base.py app/providers/writing_llm/http.py app/providers/writing_llm/__init__.py app/schemas/writing_ai.py app/services/mts_writing.py app/services/writing_ai.py app/services/writing_ai_worker.py tests/test_essay_sources.py tests/test_mts_writing_validation.py tests/test_mts_writing_v3.py tests/test_writing_ai.py tests/test_writing_llm_providers.py tests/test_writing_llm_readiness.py
# All checks passed

# frontend
npx vitest run tests/writing-ai-assessment.test.tsx tests/writing-ai-progress.test.tsx tests/writing-review.test.tsx
# 3 files passed; 24 tests passed
npm run typecheck
# passed
npx eslint src/lib/api/writing-ai.ts src/features/writing/writing-ai-progress.tsx src/features/writing/writing-ai-assessment.tsx tests/writing-ai-assessment.test.tsx tests/writing-ai-progress.test.tsx
# passed

# repository
git diff --check
# passed (Git emits only existing LF/CRLF conversion notices)
```

11. **Các file đã thay đổi:**

- `backend/app/api/v1/writing_ai.py`
- `backend/app/core/config.py`
- `backend/app/domains/scoring/ai_writing_validation.py`
- `backend/app/domains/scoring/mts_prompts.py`
- `backend/app/providers/writing_llm/__init__.py`
- `backend/app/providers/writing_llm/base.py`
- `backend/app/providers/writing_llm/http.py`
- `backend/app/schemas/writing_ai.py`
- `backend/app/services/mts_writing.py`
- `backend/app/services/writing_ai.py`
- `backend/app/services/writing_ai_worker.py`
- `backend/tests/test_mts_writing_validation.py`
- `backend/tests/test_writing_ai.py`
- `backend/tests/test_writing_llm_providers.py`
- `backend/tests/test_writing_llm_readiness.py`
- `docs/ai-writing.md`
- `frontend/src/features/writing/writing-ai-assessment.module.css`
- `frontend/src/features/writing/writing-ai-assessment.tsx`
- `frontend/src/features/writing/writing-ai-progress.tsx`
- `frontend/src/lib/api/writing-ai.ts`
- `frontend/tests/writing-ai-assessment.test.tsx`
- `frontend/tests/writing-ai-progress.test.tsx`
- `backend/app/domains/scoring/essay_sources.py`
- `backend/tests/test_essay_sources.py`
- `backend/tests/test_mts_writing_v3.py`
- `docs/superpowers/plans/2026-10-08-task2-source-calibration.md`
- `docs/task2-v3-verification.md`

12. **Trạng thái Git:** branch `main`, HEAD ban đầu `e1a951b` chứa các local fixes trước đó. Không có staged changes; không reset, clean hoặc checkout remote. Giữ nguyên file untracked `docs/MTS.pdf` đã có. Trạng thái cuối:

```text
 M backend/app/api/v1/writing_ai.py
 M backend/app/core/config.py
 M backend/app/domains/scoring/ai_writing_validation.py
 M backend/app/domains/scoring/mts_prompts.py
 M backend/app/providers/writing_llm/__init__.py
 M backend/app/providers/writing_llm/base.py
 M backend/app/providers/writing_llm/http.py
 M backend/app/schemas/writing_ai.py
 M backend/app/services/mts_writing.py
 M backend/app/services/writing_ai.py
 M backend/app/services/writing_ai_worker.py
 M backend/tests/test_mts_writing_validation.py
 M backend/tests/test_writing_ai.py
 M backend/tests/test_writing_llm_providers.py
 M backend/tests/test_writing_llm_readiness.py
 M docs/ai-writing.md
 M frontend/src/features/writing/writing-ai-assessment.module.css
 M frontend/src/features/writing/writing-ai-assessment.tsx
 M frontend/src/features/writing/writing-ai-progress.tsx
 M frontend/src/lib/api/writing-ai.ts
 M frontend/tests/writing-ai-assessment.test.tsx
 M frontend/tests/writing-ai-progress.test.tsx
?? backend/app/domains/scoring/essay_sources.py
?? backend/tests/test_essay_sources.py
?? backend/tests/test_mts_writing_v3.py
?? docs/MTS.pdf
?? docs/superpowers/plans/2026-10-08-task2-source-calibration.md
?? docs/task2-v3-verification.md
```

13. **Phạm vi:** KHÔNG triển khai Task 1-A. Không thêm Task 1 schema, UI, prompt hoặc scoring code. Không ghi official Writing scores; giữ policy Copy-to-form và human Save tường minh hiện có. Integration tests xác nhận official score isolation. Không đổi model/deployment, thêm schema migration hoặc secrets.
14. **Công bố:** không push, stage hoặc commit.

Nguồn: [official IELTS Writing Band Descriptors](https://ielts.org/cdn/ielts-guides/ielts-writing-band-descriptors.pdf), [vLLM 0.13 finish semantics](https://github.com/vllm-project/vllm/blob/v0.13.0/vllm/v1/engine/__init__.py), [vLLM structured JSON output](https://docs.vllm.ai/en/v0.13.0/features/structured_outputs/).
