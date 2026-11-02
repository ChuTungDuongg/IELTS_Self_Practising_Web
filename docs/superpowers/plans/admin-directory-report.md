# Báo cáo triển khai danh bạ Admin

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Báo cáo triển khai danh bạ Admin. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../backend/app/services/admin_directory.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Đã triển khai phần tìm kiếm danh bạ có giới hạn của công việc 3. Capability lớp học của Admin và workspace thuộc phạm vi của tác nhân chính/backend.

## Hành vi

- `/admin/classrooms` có danh bạ giáo viên và học viên riêng, tìm kiếm phía server, chọn người, chủ lớp/trạng thái, số học viên đang tham gia và phân trang độc lập.
- Chọn giáo viên lọc lớp theo chủ sở hữu; chọn học viên lọc theo enrollment hiện tại. Người được chọn được truy vấn riêng với trang danh bạ, nên phân trang và deep link vẫn giữ đúng danh tính.
- Liên kết quan sát mở workspace `/classrooms/{id}` hiện có. Liên kết roster mở `/classrooms/{id}?tab=people`, đã phối hợp với tác nhân chính.
- Điều hướng chính và dashboard Admin trỏ tới danh bạ. Quản lý tài khoản vẫn ở `/admin`, có liên kết quay lại rõ ràng.
- Dùng typography, surface, border, spacing, accent và focus tokens hiện có của BandPilot trong cả hai theme; toàn bộ nội dung hỗ trợ Việt/Anh. Trên màn hình hẹp, danh sách lớp của người được chọn có liên kết quay lại danh bạ, không bị đặt dưới toàn bộ danh sách người.
- Không thêm control mutation cho danh bạ hoặc write endpoint mới.

## Contract backend

- `GET /admin/directory/people`: `role=TEACHER|USER`, tùy chọn `search`, `offset`, `limit` (mặc định 25, tối đa 100).
- `GET /admin/directory/people/{id}`: danh tính tối thiểu của người được chọn, giới hạn theo vai trò.
- `GET /admin/directory/classrooms`: tùy chọn `teacher_id`, `student_id`, `search`, `offset`, `limit` (mặc định 25, tối đa 100).
- Mỗi danh sách dùng một SQL count và một SQL lấy trang. Counts là correlated aggregates ngay trong truy vấn trang có giới hạn, tránh truy vấn ứng dụng cho từng hàng. Thứ tự lớp và người đều có UUID làm tiêu chí phụ khi bằng nhau.
- Đếm enrollment và chọn lớp của học viên yêu cầu membership hiện tại (`left_at IS NULL`), loại tài khoản Admin nền tảng. Tài khoản Teacher hợp lệ đang tham gia với tư cách học viên vẫn được tính, thống nhất với roster. Điều hướng danh bạ Teacher/Student giữ bộ lọc vai trò toàn cục. Giữ trạng thái lớp đã lưu trữ.
- Response gồm tên hiển thị, IDs, vai trò/trạng thái tài khoản, số lớp và metadata lớp. Không select hoặc trả email, điện thoại, tiểu sử, ngày sinh, điểm hay trường hồ sơ riêng tư khác.
- Tất cả routes dùng dependency `AdminUser` hiện có. User và Teacher nhận `403 ADMIN_REQUIRED`. Kiểm tra vai trò và giới hạn trang trước truy vấn service. Ký tự wildcard SQL trong tìm kiếm được coi là văn bản nguyên nghĩa.

## Tệp

- Backend: `app/api/v1/admin.py`, các tệp mới `app/schemas/admin_directory.py`, `app/repositories/admin_directory.py`, `app/services/admin_directory.py`, và `tests/test_admin_directory.py`.
- Frontend: các tệp mới `src/app/admin/classrooms/page.tsx`, `src/features/admin/classroom-directory.tsx`, `src/features/admin/classroom-directory.module.css`, `src/lib/api/admin-directory.ts`, `tests/admin-directory-api.test.ts`, và `tests/admin-directory.test.tsx`.
- Điều hướng/bản địa hóa: `src/components/ui/global-header.tsx`, `src/components/ui/app-shell.tsx`, `src/features/auth/admin-content.tsx`, `src/lib/i18n/en.ts`, `src/lib/i18n/vi.ts`, `tests/admin-dashboard.test.tsx`, và `tests/app-shell.test.tsx`.

## Kiểm chứng

- Tests RED xác nhận các module backend/client/component mới chưa tồn tại trước triển khai.
- `.venv/Scripts/python.exe -m pytest tests/test_admin_directory.py -q`: **9 pass**. Tệp dùng SQL sessions ghi nhận lời gọi và ASGI dependency overrides; không yêu cầu `db_session` hoặc mở kết nối database. Phạm vi gồm SQL đã biên dịch có giới hạn/bộ lọc; enrollment hiện tại (giữ Teacher tham gia học nhưng loại membership Admin cũ); cột tối thiểu; wildcard nguyên nghĩa; phân quyền API chỉ Admin; giới hạn trang; kiểm tra vai trò; serialization bảo vệ riêng tư. Regression về enrollment fail trước khi sửa hai role predicates và pass sau đó.
- Ruff theo phạm vi cho mọi tệp backend danh bạ và Admin router thay đổi: **pass**.
- `npm exec -- vitest run tests/admin-directory-api.test.ts tests/admin-directory.test.tsx tests/admin-dashboard.test.tsx tests/app-shell.test.tsx`: **102 pass**. Kiểm API filters/page size, liên kết observer/roster thật, quản lý tài khoản độc lập, giữ bản nháp VI/EN, tải người được chọn, URL không hợp lệ/lặp lại, routes dashboard/điều hướng và độ rộng shell.
- ESLint theo phạm vi cho danh bạ và tệp navigation/component/test thay đổi: **pass**.
- `npm run typecheck`: **pass**, gồm chuẩn hóa query lặp và cải thiện liên kết quay lại trên mobile ở lượt cuối.
- `git diff --check`: **pass** trên worktree dùng chung tại lúc review (chỉ có thông báo chuyển CRLF của repository).

## Giới hạn

Không cấu hình hoặc chạy PostgreSQL integration database cho phần này. Chưa kiểm database execution/query plans thực tế hoặc screenshot/layout. Tác nhân này không chạy server, browser, browser tests, production build, toàn bộ suites, tiến trình thường trú, migration, reset database, commit hay push. Giới hạn không dùng browser của yêu cầu gốc có ưu tiên cao hơn hướng dẫn screenshot của skill; bố cục được duyệt và design system BandPilot hiện có có ưu tiên cao hơn bảng màu thay thế của skill.
