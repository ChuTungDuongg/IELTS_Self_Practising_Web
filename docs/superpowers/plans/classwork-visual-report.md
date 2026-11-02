# Báo cáo triển khai giao diện Classwork

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Báo cáo triển khai giao diện Classwork. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Tham chiếu và quyết định thiết kế

- Đã đọc nhiệm vụ được cung cấp, hướng dẫn app-screen của `design-taste-frontend`, `ui-ux-pro-max`, AGENTS frontend và tài liệu client-component Next.js đi kèm.
- Đã xem ảnh được người dùng duyệt tại `C:/Users/Admin/AppData/Local/Temp/codex-clipboard-d96b2861-114f-4f9d-88da-2acbcce89e64.png`.
- Bố cục được cung cấp chi phối bản cập nhật: ô sách viền xanh, tìm kiếm bên phải, tiêu đề topic dạng thư mục, trạng thái topic trống viền đứt ở giữa, vùng archive tông ấm, count badge, tìm archive theo phạm vi và thao tác hàng gọn trực tiếp. Typography và semantic tokens sáng/tối của BandPilot hiện có vẫn có thẩm quyền; không thay bằng hướng thiết kế ngẫu nhiên khác.
- Câu hỏi màn hình cần trả lời: có thể xem hoặc thao tác resources, assignments và nội dung đã lưu trữ nào? Mọi bản ghi và tổng số lấy từ API đã phân quyền; không thêm dữ liệu mẫu.

## Triển khai

- Thêm tìm topic/resource/assignment tiếng Việt không phân biệt dấu/hoa thường, gồm `Đ/đ`. Topic khớp giữ mọi mục con; mục con khớp giữ cha. Tìm kiếm mở nhóm khớp, vẫn cho tương tác mở/đóng và khôi phục lựa chọn trước khi xóa từ khóa.
- Thêm tìm archive assignment/resource riêng, giữ tổng số nhóm archive và các topic khác trong lớp.
- Thêm styling folder/card/empty-state/archive dùng chung, ô tìm responsive, bố cục thao tác gọn, metadata ngày và thông báo bản địa hóa. Hàng học viên hẹp đặt ngày và chi tiết trên các hàng riêng.
- Giáo viên thấy trực tiếp Restore, Delete và View details; Remove from Classwork ít dùng nằm trong menu desktop. Mobile chỉ dựng một bộ control theo ngữ cảnh, không lặp nút. Dialog state nằm ngoài layout responsive.
- Observer có chi tiết và trạng thái trống trung tính, không dựng control ghi. Học viên giữ liên kết lịch sử/kết quả được phép. Workspace cha cung cấp flags bảo đảm capability và ẩn menu tạo độc lập bị lặp bằng `showCreateMenu={false}`.
- Dùng lại APIs và xác nhận restore/delete/reference-removal. Khi xóa bị bảo vệ bởi lịch sử, giải thích nguyên nhân và đưa lựa chọn bỏ tham chiếu an toàn. Cảnh báo deadline hết hạn, không gia hạn. Mutation đã lưu chỉ retry đồng bộ đọc, không lặp thao tác ghi. Resource khôi phục vẫn DRAFT cho đến khi publish rõ ràng.

## Tệp

- `frontend/src/features/classrooms/content/classwork-panel.tsx`
- `frontend/src/features/classrooms/content/classwork-section.tsx`
- `frontend/src/features/classrooms/content/classwork-item-row.tsx`
- `frontend/src/features/classrooms/content/archived-assignment-actions.tsx`
- `frontend/src/features/classrooms/content/archive-action-layout.tsx` (mới)
- `frontend/src/features/classrooms/content/classwork-search.ts` (mới)
- `frontend/src/features/classrooms/content/classwork-icons.tsx` (mới)
- `frontend/src/features/classrooms/content/content-messages.ts`
- Các phần thuộc Classwork của `frontend/src/features/classrooms/content/classroom-workspace.css`
- `frontend/tests/classwork-compact.test.tsx`

## Kiểm chứng

- Giai đoạn RED: Classwork tests tập trung có năm lỗi dự kiến do thiếu tìm kiếm, metadata archive cho observer, control giáo viên trực tiếp và bố cục thao tác gọn.
- `npx vitest run tests/classwork-compact.test.tsx tests/classroom-content.test.tsx --reporter=dot`: **67 pass**, hai tệp.
- ESLint theo phạm vi trên TS/TSX Classwork thay đổi và test tập trung: **pass**.
- `git diff --check`: **pass** (Git thông báo chuyển line endings có sẵn).
- Không chạy server, browser, screenshot UI sau triển khai, browser tests, production build, toàn bộ test suite hoặc tiến trình thường trú. Độ giống hình, hình học responsive chính xác và contrast phối hợp của hai theme còn chưa được kiểm trong browser thật, theo giới hạn thực thi của yêu cầu gốc.
- Tác nhân này không commit hoặc push; tích hợp/bàn giao thuộc nhiệm vụ cha.
