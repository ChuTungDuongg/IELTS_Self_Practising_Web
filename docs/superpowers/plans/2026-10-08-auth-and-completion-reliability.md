# Độ tin cậy của xác thực và hoàn tất Writing

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Auth and Writing completion reliability. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/auth.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/identity.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Baseline: 7a23d5b88fe17efd64c2443892dbc42c5fff3d47; local main sạch.
Triển khai đặc tả hai bugs đã được cung cấp, không đổi refresh security, IELTS guidance, Task 1 perception hoặc semantics đánh giá T1-B/T1-C.

1. Xác nhận cả hai refresh owners hiện có, output schema và caps của provider. Kiểm backend one-time token rotation và concurrency tests hiện tại.
2. Thêm frontend regressions đang fail cho proxy401 restoration, single refresh ownership, login guards khi loading/authenticated, safe destinations, full replacement navigation, restoration failure và protected sidebar prefetch. Giữ logout. Triển khai shared destination helper và unprotected restoration route dùng browser API client hiện có. Proxy chỉ kiểm access, không rotate tokens.
3. Thêm backend tests đang fail tại completion request boundaries thực. Bổ sung typed CompletionOptions với max_tokens tùy chọn; giữ tên adapter parameters bên trong providers. Evidence và scoring dùng bounded budgets riêng; chỉ length-specific bounded repair mới có thêm headroom. Giữ mọi validation rules và historical persisted scoring DTOs; inference requests chỉ dùng bốn score fields.
4. Forward options qua evaluation instrumentation hiện có, cập nhật fake providers theo interface mà không đổi benchmark identity/scoring rules. Kiểm success dùng một scoring call, length failure tối đa hai calls và các repairs khác không có length headroom.
5. Chạy focused frontend auth/proxy/restoration tests, typecheck, scoped ESLint; backend auth/concurrency, MTS/provider, Task 1/Task 2 regressions; đúng CI Ruff lint/format commands và git diff --check. Review combined diff độc lập. Không browser, Playwright, real GPU requests, full benchmark hoặc push.

Frontend và backend được giao triển khai độc lập. Agent cha sở hữu integration review/verification, gồm refresh concurrency không đổi.

Trọng tâm review: phân biệt access401 với transient failures; unsafe destinations/restore loops; không hiện Login form khi session chưa được xác định hoặc đã authenticated; length retry khác semantic repair; guided provider schema thực và tất cả completion wrappers.
