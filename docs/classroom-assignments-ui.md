# Quản lý bài giao trong lớp học

> **Kiểm toán tài liệu: CURRENT.** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Quản lý bài giao trong lớp học. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../frontend/src/features/classrooms).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/classrooms.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/đo hiệu năng bên dưới thuộc lần thực hiện gốc, không phải lần chạy lại trong đợt kiểm toán này.

Bản thiết kế Assignments đã được phê duyệt được triển khai bên trong không gian Classroom hiện có. Trên máy tính từ 1100px, bảng tạo bài co giãn chiếm 29% nằm cạnh cột quản lý 71%, cách nhau 18px. Các hàng đang hoạt động dùng ký hiệu kỹ năng gọn, nhãn mục tiêu, huy hiệu trạng thái, ngày lịch đầy đủ và thao tác kết quả/ngữ cảnh. Hàng đã lưu trữ có nền đỏ rượu vang tiết chế cùng điều khiển khôi phục, xóa vĩnh viễn và chi tiết. Token ngữ nghĩa dùng chung hỗ trợ cả hai giao diện; stylesheet chỉ áp dụng cho thẻ này.

Bộ máy bài giao hiện có tiếp tục là nguồn chuẩn. Lựa chọn đề xác định bản sửa đổi đã xuất bản đủ điều kiện mà không hiển thị số bản sửa đổi kỹ thuật. Giáo viên phải chọn kỹ năng thực tế hoặc Full Mock đủ điều kiện; đơn vị luyện tập tập trung lấy từ metadata VersionDetail được phân quyền. Lập lịch giữ thời điểm mở, hạn nộp, hạn đóng tuyệt đối, giới hạn lượt làm bài và chính sách nộp muộn trong vùng mở rộng. Thao tác ghi có chặn gửi trùng, phản hồi đang xử lý/lỗi/thành công và làm mới Classwork/Assignments/tiến độ chuẩn. Nếu đọc lại thất bại sau khi tạo thành công, chỉ thử tải lại, không lặp lại việc tạo.

Thao tác giao bài IELTS ở đầu trang hiển thị và đưa tiêu điểm tới cùng biểu mẫu tạo bài. Trên di động, thao tác mở biểu mẫu ban đầu được thu gọn. Sau lần truy cập đầu tiên, thẻ Assignments vẫn được gắn khi ẩn để tìm kiếm, bộ lọc và dữ liệu biểu mẫu chưa lưu tồn tại qua điều hướng thẻ. Trình theo dõi và chỉnh lịch chỉ được gắn khi có yêu cầu. Nhân sự không tải tiến độ học viên cho từng hàng; huy hiệu trạng thái mở chỉ lên lịch cập nhật tại ranh giới thời gian kế tiếp.

Tìm kiếm tiêu đề/ghi chú/đề/mục tiêu thực hiện cục bộ, không phân biệt hoa thường và dấu tiếng Việt. Tìm kiếm bao phủ toàn bộ danh sách bài giao mà endpoint hiện tại chưa phân trang trả về. Bộ lọc All/Active/Archived ẩn các nhóm rỗng không liên quan. Tiến độ học viên do API cung cấp tiếp tục quyết định việc bắt đầu, tiếp tục và liên kết kết quả. Giáo viên và đồng giảng viên chỉ nhận điều khiển quản lý qua `assignments.manage`; Admin Observer không gắn biểu mẫu tạo và không có điều khiển thay đổi dữ liệu. Khả năng backend tiếp tục là nguồn chuẩn.

## Chính sách xóa rõ ràng

Người dùng đã xác nhận hai lần rằng xóa vĩnh viễn phải xóa toàn bộ bài làm, điểm và dữ liệu liên quan của học viên, kể cả bài giao đã hoàn thành. Chỉ dẫn này ghi đè diễn đạt bảo vệ lịch sử trong đặc tả hình ảnh được cung cấp. Xác nhận giao diện và thông báo lưu trữ nêu hậu quả không thể đảo ngược bằng VI/EN. Gỡ vị trí trong Classwork là thao tác riêng vẫn giữ bài giao và bài làm; khôi phục giữ phiên bản đóng băng, mục tiêu, lượt làm bài và lịch mà không kéo dài ngày.

Xóa cứng được phân quyền xóa lượt làm trực tiếp và Full Mock, phiên làm bài, bản ghi đánh giá/AI phụ thuộc, gia hạn, lịch sử chính sách, thông báo bài giao và tham chiếu nội dung/kế hoạch trong một giao dịch. Kế hoạch giữ danh tính và tăng bản sửa đổi khi hoạt động bị ảnh hưởng bị gỡ. Khóa phương tiện Speaking riêng tư được đưa vào hàng đợi dọn dẹp bền vững hiện có trước khi hàng dữ liệu biến mất; worker cục bộ chỉ bị hủy sau cam kết. Phiên bản đề và tài sản đã xuất bản dùng chung được giữ lại. Xóa tài nguyên gỡ liên kết khỏi bài đăng/kế hoạch mà không xóa các bài đăng/kế hoạch đó.

Migration `20261028_0042` thay trigger lịch sử chính sách để từ chối UPDATE nhưng cho phép DELETE. Migration không xóa dữ liệu. Triển khai trước khi dùng endpoint xóa mới; nếu chưa triển khai, PostgreSQL vẫn từ chối xóa sự kiện chính sách. Downgrade khôi phục hạn chế DELETE trước đây. Sau khi người dùng cho phép rõ ràng việc áp dụng migration này, cơ sở dữ liệu cục bộ hiện tại đã được nâng từ `0041` lên `0042`; kiểm tra chỉ đọc xác nhận trigger đang chạy chỉ còn `BEFORE UPDATE`. Không bài giao nào bị xóa để xác minh. Traceback do người dùng cung cấp xác nhận trigger cũ gây lỗi DELETE 500 được trình duyệt hiển thị như lỗi mạng.

## Giới hạn xác minh

Phạm vi Vitest có trọng tâm bao gồm cấu trúc bố cục, số lượng lưu trữ/đang hoạt động, tìm kiếm tiếng Việt, lọc trạng thái, trạng thái rỗng, quyền tạo, hành vi biểu mẫu máy tính/di động, mục tiêu chính xác cho cả bốn kỹ năng, điều kiện Full Mock, lập lịch, gửi trùng, thành công/lỗi/thử tải lại, tuyến kết quả, mở rộng lịch, tải theo dõi khi cần, bản địa hóa và hợp đồng CSS ở 375/768/1024/1100/1440px. Các kiểm thử observer, tiến độ học viên, lưu trữ/khôi phục và vòng đời lớp học hiện có vẫn thuộc tập được chọn.

Kiểm thử backend không cần cơ sở dữ liệu kiểm tra câu lệnh PostgreSQL giới hạn phạm vi, metadata xóa lan truyền, thứ tự hàng đợi phương tiện riêng tư, từ chối quyền, hủy sau cam kết và SQL nâng cấp/hạ cấp migration. Các kiểm tra này không thay thế kiểm thử tích hợp PostgreSQL. Trường hợp tích hợp cơ sở dữ liệu đã cập nhật được giữ lại nhưng không chạy trên cơ sở dữ liệu phát triển. Không mở trình duyệt, chụp giao diện triển khai, chạy máy chủ phát triển, bản dựng production, E2E, toàn bộ bộ kiểm thử hoặc gọi AI thật. Khoảng cách điểm ảnh, tương phản hiển thị và hành vi kích thước màn hình vẫn cần rà soát trực quan thủ công.

Xác minh cuối cùng đạt 156 kiểm thử frontend có trọng tâm, 87 kiểm thử backend không cần cơ sở dữ liệu, TypeScript, ESLint theo phạm vi, Ruff kiểm tra/định dạng theo phạm vi và `git diff --check`.

Thay đổi trang chủ đi kèm xử lý mất mạng bằng thông báo thử lại được bản địa hóa và nội dung trang giới thiệu công khai, không tạo số liệu tài khoản giả hoặc nuốt lỗi API không liên quan. Bản sửa kích thước ngôn ngữ/đăng nhập trang chủ hiện có được giữ nguyên.

## Nhóm tệp

- Cấu trúc bài giao: `frontend/src/features/classrooms/assignment-list.tsx`, `assignment-form.tsx`, `assignments/assignment-row.tsx`, `assignments/assignment-status.tsx`, `assignments/assignment-sync.tsx`, `assignments/creation-panel.tsx`, `assignments/start-assignment.tsx`, `assignments/messages.ts`, `assignments/assignments.css`, `content/classroom-workspace.tsx`, `scheduling/assignment-management.tsx`.
- Giao diện thao tác phá hủy: `frontend/src/features/classrooms/content/archived-assignment-actions.tsx`, `content-action.tsx`, `content-messages.ts`.
- Khôi phục trang chủ: `frontend/src/app/page.tsx`, `frontend/src/components/home/overview-content.tsx`, `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Vòng đời backend: `backend/app/api/v1/classroom_assignments.py`, `backend/app/services/classroom_assignments.py`, `classroom_classwork.py`, `classroom_deletion.py`, `writing_ai_worker.py`, `speaking_transcript_worker.py`, `backend/alembic/versions/20261028_0042_classroom_hard_delete.py`.
- Kiểm thử frontend: `assignments-tab.test.tsx`, `assignments-css.test.ts`, `assignment-target-ui.test.tsx`, `classroom-content.test.tsx`, `classwork-compact.test.tsx`, `home-user-metric.test.tsx` trong `frontend/tests/`.
- Kiểm thử backend: `test_classroom_hard_delete_unit.py`, `test_classroom_archive_unit.py`, `test_classroom_removal_activities.py` trong `backend/tests/`.
- Tài liệu: tài liệu này và `docs/classroom-archive-calendar.md`.
