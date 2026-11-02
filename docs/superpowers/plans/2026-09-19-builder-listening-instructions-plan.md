# Kế hoạch triển khai Builder, Listening và hướng dẫn câu hỏi

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Implementation plan. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/domains/questions/registry.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/authoring.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

1. Thêm frontend tests đang fail cho URL-backed Builder navigation, optional/shared audio UI, một Runner player duy nhất, YNNG rendering và instructions lấy từ registry.
2. Thêm backend tests đang fail cho module audio mutation, optional publish behavior, YNNG validation/grading/normalization, DTO shape và migration data cases.
3. Thêm Alembic migration kiểm tra/backfill `test_modules.audio_asset_id` trước khi bỏ `listening_parts.audio_asset_id`.
4. Cập nhật SQLAlchemy relationships, repository loading, services, schemas, cloning, asset preservation, validation và presentation.
5. Cập nhật frontend DTO schemas/API calls, Builder navigation/workspaces, Listening Builder, Runner và Review.
6. Mở rộng frontend/backend registries cho `yes_no_not_given`, thêm shared instruction generator/component.
7. Chạy focused tests trong lúc triển khai, sau đó toàn bộ frontend tests và backend non-integration tests. Nếu đủ thời gian, chạy lint/typecheck/build và Ruff; không browser/E2E tests.
8. Kiểm final diff và ghi giới hạn database verification nếu PostgreSQL vẫn chưa sẵn sàng.
