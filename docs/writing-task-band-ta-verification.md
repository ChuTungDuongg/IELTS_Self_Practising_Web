# Bàn giao Writing task band và chẩn đoán TA — 2026-11-03

Nền kiểm tra: c1fc40f, đã bao gồm f0ee0ff. Thay đổi ở managed worktree riêng, branch codex/writing-task-bands-ta-diagnostics; checkout gốc và các tệp untracked có sẵn được giữ nguyên. Ở lần bàn giao đầu chưa commit/push. Theo yêu cầu tiếp theo, thực hiện commit/push branch và theo dõi CI; không merge, deploy, gọi grading API thật hoặc sửa điểm production.

## 1. Phần A đã triển khai

- calculate_task_overall vẫn trả raw mean. Review score.overall/history.task_score không đổi nghĩa; task_band dẫn xuất bằng round_to_half tại DTO, không thêm cột database.
- Với 5/5/4/4.5: API trả raw 4.625 và task_band 4.5. Header/card/reload/history cùng hiển thị band 4.5, giữ nguyên bốn tiêu chí. Payload cũ dùng một helper half-up chung; thiếu tiêu chí không có band; zero hiển thị 0.0.
- Đủ tám mốc bắt buộc: 4.625→4.5; 4.75→5.0; 6.25→6.5; 6.75→7.0; 7.125→7.0; 7.875→8.0; 0→0.0; 9→9.0.
- Focused attempt.band_score giữ null; không trở thành toàn kỹ năng/IELTS overall/Full Mock. Đủ hai task vẫn lấy raw 6.125/6.25 để tính weighted 6.208333… và final 6.0, được kiểm cả service, DTO và reload.
- Task 1 dùng TA — Task Achievement; Task 2 dùng TR — Task Response, gồm nhận xét và accessible labels; backend key ta giữ nguyên.
- Chi tiết gradebook chỉ sửa trình bày điểm Writing FOCUSED_UNIT đang hiển thị cùng raw mean; không đổi query/analytics/grade selection/CSV hoặc semantics task_score.
- Giữ manual/advisory authority, copy AI chỉ điền form, capability, feedback streaming, partial results, cancellation và card AI một cột.

## 2. Phần B: điều đã và chưa xác minh

Người yêu cầu xác nhận không có case/run ID hoặc nguồn nhãn TA 8.0. Thư mục dataset/report local không có mẫu thật; không tái hiện được TA8→7. Không dùng overall 8 làm TA8 hoặc tự sinh ground truth.

Đã xác nhận selector assessment đi vào TA scoring trước khi chấm toàn bài; đây chỉ là cơ chế có thể gây anchoring, chưa phải nguyên nhân lỗi đã được chứng minh. Đã đối chiếu descriptor IELTS chính thức và các guidance hiện có; không thêm prompt trùng lặp hay thiên hướng nâng band. Code/schema normalization/persistence/SSE/UI giữ điểm tiêu chí; các giá trị giả 4/7/8 không bị tự đổi sau validation.

Chưa thể phân loại một lượt thật thành deploy/config cũ, cache cũ, đọc sai ảnh, verify sai claim hoặc áp dụng rubric sai. Chưa có kiểm chứng số liệu/đơn vị/trục/legend/key feature/map/process/approximation của case thật.

## 3. Thay đổi TA thực tế

- Production chỉ bổ sung audit checksum ảnh, cờ thực sự dùng ảnh tại TA và validated_score; không đổi prompt, reasoning policy/detail, score, evidence validation hay reconciliation.
- scripts/diagnose_writing_run.py đọc transaction READ ONLY và xuất allowlisted metadata của run đã lưu; không xuất essay/prompt/ảnh/base64/secret/raw provider response/chain-of-thought. Metadata thiếu là unknown; cache_hit cần đối chiếu create-run response, không suy từ default hiện tại.
- DEV task1-ta-evidence-v1: selector_assessments và source_ids_only chỉ khác evidence.assessment tại TA scoring; giữ source IDs/trích dẫn trong toàn bài, ảnh, rubric, facts/claims, policy, evidence selection và feedback. Task 2/Speaking/vLLM production không đổi.
- CLI, run_benchmark và evaluate khóa mọi inference của mode thử nghiệm, kể cả injected factory. HOLDOUT bị chặn. Chỉ dry-run DEV; test scorer giả không chứng minh chất lượng IELTS.
- Production versions giữ mts-task1-visual-v12 / mts-task1-scoring-v12 / openai_task1_reasoned_v1 / source-image-envelope-v1. Diagnostic version task1-ta-audit-v1, experiment identity ta_evidence_mode tách cache. Không tự sửa lịch sử.

## 4. Kết quả kiểm tra thực tế

| Kiểm tra | Kết quả |
| --- | --- |
| Backend focused: writing_scoring, ielts_band, focused_attempts, writing_attempts, evidence_ablation, diagnostics, openai_ablation | **136 passed** trên PostgreSQL test riêng |
| Tập Task 1/OpenAI rộng hơn và score-first/completion-budget | **742 passed** ở lượt trước |
| Backend toàn repo | **3483 passed, 88 skipped, 2 failed** do thiếu TEST_DATABASE_URL trong guard của hai test concurrency |
| Hai test concurrency sau cấu hình đúng TEST_DATABASE_URL bằng DATABASE_URL của DB test riêng | **2 passed**; không sửa code classroom |
| Frontend toàn repo với --maxWorkers=2 | **1916 passed / 166 files** |
| Frontend focused sau các chỉnh nhãn/spacing và thêm zero/9 history | **157 passed / 7 files** |
| Playwright Writing focused Task 1 và Task 2 | **2 passed**, lưu form→API→reload→history; ảnh 1440×1000 và 390×844 |
| Ruff app/tests + hai CLI, ESLint frontend, git diff --check | **Passed** |
| npm run typecheck sau Next dev type generation | Lần đầu lộ lỗi baseline themeInitializationScript; sau yêu cầu commit/push và CI xanh, chuyển nguyên script sang module personalization riêng; **typecheck passed**, 78 test theme/localization/Writing liên quan passed |
| TA evidence CLI dry-run trên 1 fixture hư cấu | **2 planned scoring runs, 0 inference, 0 evaluated pairs** |

Hai failure backend ban đầu là test_assignment_scheduling_lifecycle.py::test_concurrent_start_near_limit_is_serialized và test_classroom_staff_gradebook.py::test_concurrent_staff_invitations_are_serialized. Chúng dừng tại assert TEST_DATABASE_URL == cấu hình database trước khi chạy nghiệp vụ; chạy lại đúng cấu hình đã qua. Không tuyên bố lệnh full-suite ban đầu xanh.

Lượt frontend toàn repo đầu tiên có assertion TA cũ (đã cập nhật thành TR) và một timeout classroom khi chạy song song. Classroom qua khi chạy riêng; lượt toàn repo với hai worker qua. Có warning jsdom HTMLMediaElement.pause và warning deprecation Starlette/anyio; không phải inference thật.

Typecheck trước khi có generated Next dev types đã qua. Sau browser checks, lỗi baseline nêu trên lộ ra; git diff xác nhận layout.tsx không đổi, export đó có ngay trong c1fc40f. Không xóa generated evidence. Theo yêu cầu tiếp theo phải đạt CI xanh, đã chuyển nguyên script sang features/personalization/theme-initialization.ts, cập nhật imports trong layout và tests; không đổi chuỗi script hay hành vi theme. Typecheck với generated types đã qua sau sửa.

Artifacts local (git-ignored): .test-tmp/writing-band-verification/ chứa logs và evidence-plan/report.json; frontend/test-results/ chứa screenshots. Lượt full frontend chạy trước khi thêm hai regression history 0/9; lượt focused cuối bao phủ cả hai. Các regression API 0/9 và module double-rounding được kiểm trong lượt focused cuối. Không cộng các số test chồng lặp thành một tổng.

## 5. Dữ liệu/điều kiện còn thiếu

Chưa đo MAE TA, signed bias, tỷ lệ sai lệch ≤0.5, false factual feedback, repeat stability, truncation/error rate, latency/usage/cost của model thật. Không điền 0 giả hoặc gọi dry-run là benchmark chất lượng. Cần DEV nhiều mức có nhãn TA độc lập đáng tin, ảnh đúng nguồn và nguyên văn/đoạn văn; các reference/facts/claims/feedback cùng lượt. Live cần cho phép rõ, giá hiện hành và pre-request cost reservation cho mọi arm/repair/in-flight call. HOLDOUT chỉ dùng đánh giá cuối.

## 6. Tệp, cấu hình và rollback

Cấu hình production không đổi, không migration. CLI mới: --ta-evidence-ablation --dry-run --split dev và diagnose_writing_run.py --run-id UUID. DB cổng 55439 và hai database ielts_test/ielts_visual_test chỉ phục vụ kiểm thử cách ly; không dùng database ứng dụng.

Để rollback code, bỏ riêng các thay đổi được liệt kê dưới đây trong worktree này hoặc archive worktree bằng Codex để giữ snapshot phục hồi. Không reset/stash checkout gốc, không downgrade database, không viết lại điểm lịch sử. Phần A độc lập với các file evaluation/diagnostics của B. Nếu triển khai sau này, frontend/backend phải dùng cùng DTO additive; client cũ vẫn nhận raw fields với nghĩa cũ.

### Danh sách tệp thay đổi

- [.github/workflows/e2e.yml](../.github/workflows/e2e.yml)
- [frontend/src/app/layout.tsx](../frontend/src/app/layout.tsx)
- [frontend/src/features/personalization/theme-initialization.ts](../frontend/src/features/personalization/theme-initialization.ts)
- [frontend/tests/root-layout.test.tsx](../frontend/tests/root-layout.test.tsx)
- [frontend/tests/localization-matrix.test.tsx](../frontend/tests/localization-matrix.test.tsx)
- [backend/app/evaluation/task1/diagnostics.py](../backend/app/evaluation/task1/diagnostics.py)
- [backend/app/evaluation/task1/evidence_ablation.py](../backend/app/evaluation/task1/evidence_ablation.py)
- [backend/app/evaluation/task1/models.py](../backend/app/evaluation/task1/models.py)
- [backend/app/evaluation/task1/report.py](../backend/app/evaluation/task1/report.py)
- [backend/app/evaluation/task1/runner.py](../backend/app/evaluation/task1/runner.py)
- [backend/app/evaluation/writing/runtime.py](../backend/app/evaluation/writing/runtime.py)
- [backend/app/schemas/attempts.py](../backend/app/schemas/attempts.py)
- [backend/app/services/attempts.py](../backend/app/services/attempts.py)
- [backend/app/services/task1_writing.py](../backend/app/services/task1_writing.py)
- [backend/tests/test_focused_attempts.py](../backend/tests/test_focused_attempts.py)
- [backend/tests/test_task1_diagnostics.py](../backend/tests/test_task1_diagnostics.py)
- [backend/tests/test_task1_evidence_ablation.py](../backend/tests/test_task1_evidence_ablation.py)
- [backend/tests/test_task1_openai_ablation.py](../backend/tests/test_task1_openai_ablation.py)
- [backend/tests/test_writing_attempts.py](../backend/tests/test_writing_attempts.py)
- [backend/tests/test_writing_scoring.py](../backend/tests/test_writing_scoring.py)
- [docs/ai-writing.md](../docs/ai-writing.md)
- [docs/focused-attempts.md](../docs/focused-attempts.md)
- [docs/superpowers/plans/2026-11-03-writing-task-bands-ta-diagnostics.md](../docs/superpowers/plans/2026-11-03-writing-task-bands-ta-diagnostics.md)
- [docs/writing-benchmark-bank.md](../docs/writing-benchmark-bank.md)
- [docs/writing-task-band-ta-verification.md](../docs/writing-task-band-ta-verification.md)
- [frontend/src/features/classrooms/lms/gradebook.tsx](../frontend/src/features/classrooms/lms/gradebook.tsx)
- [frontend/src/features/history/attempt-history-list.tsx](../frontend/src/features/history/attempt-history-list.tsx)
- [frontend/src/features/writing/task-band.ts](../frontend/src/features/writing/task-band.ts)
- [frontend/src/features/writing/writing-review.tsx](../frontend/src/features/writing/writing-review.tsx)
- [frontend/src/lib/api/exam.ts](../frontend/src/lib/api/exam.ts)
- [frontend/src/lib/api/history.ts](../frontend/src/lib/api/history.ts)
- [frontend/src/lib/i18n/en.ts](../frontend/src/lib/i18n/en.ts)
- [frontend/src/lib/i18n/vi.ts](../frontend/src/lib/i18n/vi.ts)
- [frontend/tests/attempt-history-list.test.tsx](../frontend/tests/attempt-history-list.test.tsx)
- [frontend/tests/e2e/writing-focused-band.spec.ts](../frontend/tests/e2e/writing-focused-band.spec.ts)
- [frontend/tests/focused-attempt-contract.test.ts](../frontend/tests/focused-attempt-contract.test.ts)
- [frontend/tests/writing-ai-assessment.test.tsx](../frontend/tests/writing-ai-assessment.test.tsx)
- [frontend/tests/writing-ai-practice-feedback.test.tsx](../frontend/tests/writing-ai-practice-feedback.test.tsx)
- [frontend/tests/writing-grade-details.test.tsx](../frontend/tests/writing-grade-details.test.tsx)
- [frontend/tests/writing-review.test.tsx](../frontend/tests/writing-review.test.tsx)
- [frontend/tests/writing-task-band.test.ts](../frontend/tests/writing-task-band.test.ts)
- [scripts/benchmark_task1.py](../scripts/benchmark_task1.py)
- [scripts/diagnose_writing_run.py](../scripts/diagnose_writing_run.py)


## Theo dõi CI sau yêu cầu commit/push

- Chuẩn hóa đúng Ruff formatter từ backend/ như workflow; 514 file đã qua format check, chỉ 12 file trong bản sửa cần định dạng.
- Sửa export không hợp lệ của Next layout bằng chuyển script sang module personalization; 78 test theme/localization/Writing qua và npm run typecheck qua với generated dev types.
- Kiểm lại 102 backend unit/contract tests không cần database: passed. Backend integration và E2E đã có bằng chứng ở các lượt trên; GitHub CI chạy bộ backend/frontend đầy đủ cho commit đã push.
- Thêm writing-focused-band.spec.ts vào danh sách Golden path E2E hiện có.
- Workflow CI chạy trên pull_request hoặc push main; mở draft PR cho branch để kích hoạt checks. Không tự merge hoặc deploy. Trạng thái cuối được xác minh trên đúng SHA qua GitHub Actions.
