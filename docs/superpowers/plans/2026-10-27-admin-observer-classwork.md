# Kế hoạch Admin Observer và giao diện Classwork đã duyệt

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Kế hoạch Admin Observer và giao diện Classwork đã duyệt. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **Dành cho tác nhân triển khai:** thực hiện các phần độc lập với phạm vi rõ ràng, review từng phần và kiểm chứng tích hợp. Yêu cầu gốc cho phép triển khai, commit và push an toàn lên origin/main.

**Mục tiêu:** buộc quản trị viên nền tảng chỉ được quan sát lớp học và dùng chung giao diện Classwork đã duyệt giữa các vai trò.

**Kiến trúc:** FastAPI xác định capability cụ thể của lớp học và từ chối thao tác ghi tại ranh giới service. Next.js dùng workspace hiện có với props phân biệt quyền đọc/ghi. Danh bạ Admin dùng truy vấn có giới hạn; lưu trữ vẫn giữ cơ chế bảo vệ lịch sử và đồng bộ lại dữ liệu.

**Công nghệ:** FastAPI, SQLAlchemy/PostgreSQL, Next.js, React, Zod, pytest, Vitest.

**Đặc tả:** tệp người dùng cung cấp `Pasted text.txt` (CODEX TASK — Match Approved Classwork Design + Enforce Strict Admin Observer Mode).

## Ràng buộc chung

- Giữ PostgreSQL là nguồn dữ liệu có thẩm quyền; giữ TestVersions bất biến, attempts, phạm vi truy cập, lịch và nguồn gốc điểm số.
- Admin chỉ quan sát lớp học, kể cả khi có bản ghi membership/staff cũ.
- Giữ quyền quản lý tài khoản nền tảng và kiểm duyệt đề toàn cục được cấp riêng.
- Dùng API và workspace dùng chung hiện có; hỗ trợ tiếng Việt/Anh và cả hai theme.
- Không khởi động server, browser, browser tests, production build, tiến trình thường trú; không reset database hoặc chạy toàn bộ test suite.
- Giữ các tệp skills/design chưa được theo dõi. Chỉ commit tệp thuộc nhiệm vụ; push origin/main không dùng force.

## Trọng tâm review

- Route Writing/Speaking cá nhân cũng phải từ chối Admin chấm điểm cuối cùng cho bài của lớp học.
- Quyền xem danh sách thành viên không bao hàm quyền quản lý thành viên.
- Chủ lớp vẫn có thể khôi phục lớp đã lưu trữ mà không cần quyền Admin.
- Tìm kiếm giữ các mục con khớp với topic và tìm nội dung tiếng Việt không phân biệt hoa/thường hoặc dấu.
- Chi tiết bài giao đã lưu trữ vẫn truy cập được, không dựng control ghi; không lặp thao tác trên mobile.

### Công việc 1: Phân quyền backend

**Tệp:** `backend/app/services/classroom_capabilities.py`, các service lớp học, `grading_policy.py` và backend tests tập trung.

- [x] Thêm capability/service/REST tests đang fail cho việc từ chối Admin và cách ly giáo viên/đồng giảng viên/học viên.
- [x] Cho phép rõ ràng đọc roster/điểm/analytics; tách xem roster khỏi sửa thành viên.
- [x] Bỏ bypass tạo assignment và chấm điểm; rà mọi mutation của lớp và quyền khôi phục của chủ lớp.
- [x] Chạy tests tập trung và Ruff; ghi điều kiện database còn thiếu, không chạm dữ liệu thật.

### Công việc 2: Giao diện Classwork dùng chung

**Tệp:** components và CSS Classwork trong `frontend/src/features/classrooms/content/`, cùng component tests tập trung.

- [x] Thêm tests tìm topic/resource/assignment và thao tác lưu trữ của giáo viên so với người quan sát.
- [x] Thêm header sách/tìm kiếm, topic dạng thư mục, trạng thái trống trung tính và vùng lưu trữ gọn với tokens hiện có.
- [x] Hiện trực tiếp Restore/Delete/Details cho giáo viên và thao tác theo ngữ cảnh trên mobile; giữ xác nhận và xóa an toàn cho lịch sử.
- [x] Chạy Vitest tập trung và ESLint theo phạm vi. Yêu cầu gốc loại trừ kiểm chứng bằng browser/screenshot.

### Công việc 3: Danh bạ Admin và kết nối chế độ quan sát

**Tệp:** route/service/schema danh bạ Admin, frontend clients có kiểu, UI danh bạ, components chi tiết/workspace/header/membership của lớp và tests.

- [x] Triển khai tìm giáo viên/học viên/lớp có giới hạn, hiển thị chủ lớp và số người đang tham gia.
- [x] Tách quyền roster/classroom/member/content/assignment/grade/analytics xuyên suốt workspace dùng chung.
- [x] Hiển thị chỉ báo quan sát và roster chỉ đọc; bỏ control soạn nội dung, tiến độ cá nhân và chấm điểm của Admin.
- [x] Chạy frontend/API tests tập trung, typecheck và lint theo phạm vi.

### Công việc 4: Tích hợp và bàn giao

- [x] Review mọi đường dẫn thay đổi theo ma trận quyền và bố cục được cung cấp.
- [x] Chạy các kiểm tra được phép cùng `git diff --check`, xem diff và commit theo nhóm hợp lý.
- [x] Chuẩn bị các commit đúng phạm vi và push an toàn lên origin/main; ghi bằng chứng commit/push thực tế trong phản hồi bàn giao gốc.

## Bằng chứng kiểm chứng cuối cùng

- 176 backend tests tập trung pass, gồm 51 trường hợp từ chối qua REST; không chạy database fixtures.
- 284 frontend tests tập trung pass trên 16 tệp.
- Ruff/ESLint cho tệp thay đổi, TypeScript và kiểm tra khoảng trắng đều pass.
- Review độc lập không còn vấn đề sau khi sửa AI cancellation/read recovery và hàng resource dạng gọn.
- Yêu cầu bổ sung: nút VI/EN ở trang chủ giữ vị trí nhờ kích thước nội tại của cả hai nhãn xác thực đã dịch; giữ accessible labels và điều hướng.
- Theo giới hạn của yêu cầu gốc, không chạy browser rendering, production build hoặc tích hợp PostgreSQL thật.
