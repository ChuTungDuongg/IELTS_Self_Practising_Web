# Kế hoạch source grounding và calibration Task 2

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Task 2 source grounding and calibration implementation plan. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/mts_writing.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> Thực thi trực tiếp bằng superpowers:executing-plans; giữ local checkout hiện tại.

**Mục tiêu:** Advisory Task 2 assessment đáng tin cậy với phản hồi tiếng Việt dựa trên source, bands có calibration, lỗi được cô lập và live SSE cards.

**Kiến trúc:** Pure splitter ánh xạ PnSm IDs tới original Python character spans. Evidence interaction chọn IDs; backend tra cứu để cung cấp quotes. Mỗi criterion giữ evidence/scoring interactions độc lập và một repair cho mỗi interaction sai. Scoring thêm comparative justification có giới hạn trong cùng interaction. PostgreSQL checkpoints trình bày completed results/failed criteria qua snapshots và replayable events.

**Ràng buộc:** Đặc tả Task 2 của user và chỉ dẫn calibration bổ sung có tính quyết định. Không làm Task 1, thay official scores, đổi provider deployment, push, browser, Playwright, real inference hoặc unrelated suites. Giữ historical DTO compatibility. v3 phải vô hiệu hóa v1/v2 cache fingerprints.

## Công việc

- [x] Thêm `essay_sources.segment_essay(essay)` và invariant tests cho IDs, paragraphs, CRLF/LF, abbreviations, câu lặp và Unicode punctuation.
- [x] Thêm bounded evidence selection schemas và `resolve_evidence(selection, sources)`; thay quote matching bằng ID validation/exact lookup. Thêm resolution/repair tests.
- [x] Nâng prompts/configured version thành `mts-task2-v3`. Dùng official IELTS Task 2 descriptors hiện hành, holistic adjacent-band comparison và half-band interpolation. Thêm source-backed justification summaries có giới hạn và structural consistency tests, không deterministic severity gates, deductions hoặc caps. Giữ low-temperature vLLM và budget1800tokens.
- [x] Phân loại safe provider finish metadata thành stop/length/known terminal/other, từ chối length và unsupported terminals với một repair. Thêm mocked transport tests.
- [x] Cô lập criterion provider failures, checkpoint `criterion.failed`, thử remaining traits và fail run không có aggregate nếu có trait lỗi. Lưu failures trong JSONB và expose snapshots; test fake providers và focused PostgreSQL integration.
- [x] Giữ UI bốn bước; thêm persisted local failure states/live counts, giữ immediate cards, replay và heartbeat behavior. Test SSE continuation, reload/reconnect, terminal partial results và lỗi tiếng Việt.
- [x] Cập nhật AI docs; chạy targeted pytest/Vitest, typecheck, Ruff/ESLint các file đã sửa và diff check; review diff, báo files/status cùng giới hạn kiểm chứng calibration.

**Trọng tâm review:** Câu dài không dấu câu không vướng legacy quote limits; đoạn text lặp có identity riêng; old payloads vẫn đọc được; unknown finish values không làm lộ text vào logs; một trait fail không được làm run terminal khi traits sau còn active.

**Ghi chú thực thi:** User yêu cầu rõ checkout hiện tại: không worktree, commit hoặc push. Chỉ dẫn sửa sau thay thế proposed high-band heuristics; chỉ có bốn official criteria làm scoring dimensions. Automated tests dùng fake providers để kiểm prompt/schema contracts, không thể chứng minh empirical real-model calibration. PostgreSQL verification dùng temporary isolated local container thay configured development database không khả dụng.

**Kiểm chứng cuối:**170focused pytest tests và24focused Vitest tests pass. TypeScript, Ruff/ESLint các file sửa và `git diff --check` pass. Review tìm thấy descriptors phân biệt quá cô đọng, lỗi timeline LR-failure/GRA-interruption và Band9comparison contradiction; mỗi lỗi có regression fail trước fix/pass sau fix. Đã xử lý mọi review findings. Temporary PostgreSQL container đã stop. Không browser, Playwright, GPU inference, Task 1 work, official score mutation, staging, commit hoặc push.
