# Review độc lập cuối cùng — 2026-10-27

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Review độc lập cuối cùng — 2026-10-27. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Phạm vi

Review các thay đổi thuộc nhiệm vụ trong worktree so với base `54ff874b41f36bb8409509d77fd17adf411e50d8`, AGENTS của repository, `docs/architecture.md`, đặc tả được cung cấp, kế hoạch triển khai và báo cáo của các tác nhân. Đã xem trực tiếp ảnh tham chiếu được duyệt. Loại trừ các tệp skill/configuration/design-reference chưa được theo dõi, không liên quan.

Phạm vi gồm xác định capability lớp học; đường ghi API trực tiếp; membership và classroom attempts cũ; chấm điểm cuối Writing/Speaking qua route cá nhân/theo lớp; tác dụng phụ của AI creation/cancellation/reads; giữ quyền teacher/co-teacher/TA; truy vấn danh bạ có giới hạn và riêng tư response; control quan sát dùng chung; tìm kiếm Classwork, an toàn lưu trữ và CSS responsive.

Đã review thêm bản sửa vị trí nút ngôn ngữ trang chủ được cho phép sau đó: hai bản dịch xác thực cùng dự trữ độ rộng nội tại trong một ô CSS grid; văn bản đo kích thước ẩn khỏi accessibility APIs và pointer interaction; nhãn liên kết hiển thị vẫn theo locale. Không phát hiện vấn đề bổ sung.

## Vấn đề còn mở

Không còn sau khi kiểm mã nguồn của các bản sửa dưới đây.

## Các bản sửa đã kiểm trong review

1. **P1 — Writing AI cancellation tin quyền sở hữu lịch sử.** `backend/app/services/writing_ai.py:385`. Admin sở hữu classroom attempt/run cũ có thể cancel mà không qua ranh giới mutation mới. Cancellation hiện tải attempt và kiểm nguồn gốc lớp trước `fail_run`.
2. **P2 — Writing AI reads có thể ghi trạng thái run cũ.** `backend/app/services/writing_ai.py:306`. Các đường list/get/event snapshot gọi `recover_stale`, có thể ghi FAILED và nối events cho run lớp cũ của Admin. Ranh giới recovery hiện kiểm nguồn gốc và giữ quan sát chỉ đọc, không ghi run đó. Đã kiểm Speaking AI snapshots: chúng biểu diễn trạng thái cũ mà không đi qua đường persist này.
3. **P2 — Controls của resource lưu trữ chồng lên nhau tại 481–640 px.** `frontend/src/features/classrooms/content/classroom-workspace.css:199`. Nút View gọn và menu archive ban đầu cùng chiếm cột 2, hàng 1. View hiện ở hàng 2 trong toàn breakpoint gọn; menu quản lý vẫn ở hàng 1.

Đây là các phát hiện đã đóng đối với source cuối được review, không phải release blockers còn mở.

## Kết luận tuân thủ đặc tả

**Đạt qua kiểm mã nguồn, với các giới hạn kiểm chứng bên dưới.** Capability Admin dùng allowlist chỉ đọc rõ ràng, ưu tiên hơn owner/staff rows cũ. Ranh giới service dùng chung từ chối ghi lớp; chính sách điểm cuối bao phủ endpoint lớp lẫn cá nhân với nguồn gốc trực tiếp/Full Mock. Chủ lớp vẫn khôi phục được lớp; phạm vi co-teacher và TA tách biệt. Quản lý tài khoản toàn cục và kiểm duyệt đề giữ chính sách riêng.

Danh bạ Admin dùng bộ lọc server, truy vấn phân trang có thứ tự xác định, kích thước trang hữu hạn và trường người/lớp tối thiểu. Liên kết observer và roster mở workspace lớp dùng chung hiện có. Giao diện Admin bỏ control quản lý, soạn nội dung, tham gia, điểm cuối và tiến độ cá nhân, nhưng giữ duyệt, tìm kiếm, mở/đóng nội dung và các góc nhìn học thuật được phép.

Source Classwork theo bố cục được duyệt: tiêu đề sách/tìm kiếm, topic dạng thư mục, trạng thái trống trung tính của observer và vùng archive gọn riêng. Tìm kiếm tiếng Việt chuẩn hóa hoa/thường/dấu, gồm đ; giữ ngữ cảnh cha/con. Thao tác archive dùng lại xóa/bỏ tham chiếu có bảo vệ và khôi phục không đổi deadline. Resources khôi phục vẫn là bản nháp.

## Kết luận chất lượng mã

**Có thể tích hợp.** Phân quyền vẫn ở FastAPI services, query logic ở repositories, frontend controls dựa trên props quyền đọc/ghi rõ ràng. Giao diện dùng chung tránh tạo riêng màn hình Admin. Không thấy thay đổi nội dung version đã publish, lịch sử attempt/điểm, schema hoặc quy tắc xóa bảo vệ lịch sử.

## Bằng chứng và giới hạn kiểm chứng

- Bằng chứng từ bên triển khai/tác nhân chính: 222 frontend tests của nhiệm vụ và 62 kiểm tra homepage/Gravity/Classwork CSS không trùng nhau pass; TypeScript và lint theo phạm vi pass. Báo cáo backend ghi 167 tests tập trung authorization/archive/AI reads/worker/SSE/cancellation và Ruff pass. Tác nhân danh bạ ghi riêng bảy backend contract tests tập trung. Tác nhân chính sẽ kiểm tập trung kết hợp sau khi đóng băng source.
- Reviewer độc lập không chạy lại suites hoặc database fixtures. `git diff --check` tập trung vào các bản sửa Writing AI và mobile CSS cuối pass, chỉ có thông báo line endings của Git.
- REST authorization tests dùng routers/services thật với database doubles có kiểm soát. PostgreSQL cách ly thực tế, row counts/concurrency/query plans và các integration tests được sửa còn chưa xác minh vì chưa có test database cách ly được chỉ định.
- Trong review này không chạy server, browser, Playwright/Cypress, production build, tiến trình thường trú, reset database, commit hoặc push. So ảnh được duyệt với source không phải kiểm screenshot UI render; hình học desktop/mobile và contrast theme thực tế vẫn chưa xác minh.

Kiểm chứng tích hợp cuối của tác nhân chính: 176 backend tests tập trung và 284 frontend tests tập trung pass; Ruff/ESLint theo tệp thay đổi, TypeScript và kiểm khoảng trắng diff pass. Không tuyên bố đã kiểm UI render hoặc PostgreSQL integration.
