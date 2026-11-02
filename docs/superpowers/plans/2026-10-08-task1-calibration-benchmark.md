# Kế hoạch triển khai calibration và evaluation Task 1

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Task 1 calibration and evaluation implementation plan. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/mts_writing.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Triển khai đặc tả hai phần được cung cấp trên 78a742d. Giữ Task 1 perception contract hiện tại, DePlot tùy chọn theo fail-open, source grounding và Task 2 v6. Không thêm judge khác hoặc production score correction.

1. Thay Task 1 guidance được sửa chuỗi từ Task 2 bằng bốn criterion scopes, feedback boundaries riêng và phần diễn giải descriptors gốc. Test độ phù hợp whole-response/adjacent-profile và half-band interpolation trước khi đổi builders. Giữ shared MTS engine và Vietnamese output contracts.
2. Version production Task 1 scoring change thành mts-task1-visual-v4. Báo perception v3 và scoring v4 riêng, không persistence migration. Giữ benchmark-only v3 guidance sau protected prompt-builder hooks; production chỉ tiếp tục dùng v4.
3. Thêm backend/app/evaluation/task1: strict versioned JSONL sample schema, local-image loading, deterministic score/perception metrics, service-level runner, private content-addressed checkpoints và JSON/Markdown/CSV reports. Human scores/annotations chỉ phục vụ evaluation, không làm scorer inputs.
4. Thêm python -m scripts.benchmark_task1 với dev/holdout selection tường minh, limit, dry-run, output, resume, scoring-version v3/v4/both và specialist off/on/both. Chỉ so matching samples, tách primary perception, reconciled perception, scores, failure rates, latency và usage.
5. Thêm benchmark README, generated manifest schema và ignored private/report directories. Không commit benchmark essays, target labels hoặc binary images. Tests dùng synthetic examples tự viết; xác nhận plumbing chứ không chứng minh calibration hiệu quả trên dữ liệu thật.
6. Kiểm bằng focused prompt/metric/manifest/runner-cache/Task 1 perception/Task 2 regression tests, Ruff, CLI dry-run và git diff --check. Review thay đổi đã tích hợp. Không tự chạy real labelled benchmark, bật adjudicator, commit hoặc push.

Phân công độc lập: Task 1 guidance và pure metrics giao hai agents riêng. Agent cha sở hữu manifests, orchestration, reports, CLI, documentation và integration verification.
