# Lưu trữ lớp học và lịch tương tác

> **Kiểm toán tài liệu: CURRENT.** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Lưu trữ lớp học và lịch tương tác. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../backend/app/services/classroom_deletion.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/classrooms.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/đo hiệu năng bên dưới thuộc lần thực hiện gốc, không phải lần chạy lại trong đợt kiểm toán này.

## Vòng đời lưu trữ và API

`POST /classrooms/{classroom_id}/assignments/{assignment_id}/restore` xác thực và khóa người thực hiện, lớp học và bài giao trong phạm vi. Thao tác yêu cầu `assignments.manage` và lớp học đang hoạt động. Nó chỉ đổi `ARCHIVED` thành `ACTIVE`, xóa `archived_at` và tăng bản sửa đổi nội dung. Khôi phục lặp lại có tính lũy đẳng.

TestVersion đóng băng, mục tiêu được giao, lịch/hạn đóng gốc, giới hạn lượt làm bài, chính sách nộp muộn, `classwork_hidden`, vị trí nội dung và lịch sử học tập giữ nguyên. Các kiểm tra bắt đầu/hạn thời gian/kiểm duyệt bình thường vẫn áp dụng. Xác nhận cảnh báo hạn nộp/hạn đóng đã qua; sau đó giáo viên có thể mở chi tiết bài giao và dùng trình chỉnh lịch hiện có.

Tài nguyên và chủ đề dùng endpoint PATCH hiện có với `{ "status": "DRAFT" }`. Giao diện yêu cầu xác nhận và không tự xuất bản lại nội dung con hoặc sao chép bản ghi tài nguyên/tệp. Mục cha đã lưu trữ tiếp tục bị ẩn cho đến khi giáo viên chủ động khôi phục và xuất bản. Có thể di chuyển tài nguyên bằng bộ chọn chủ đề hiện có; khôi phục tài nguyên về DRAFT dưới chủ đề đã lưu trữ là an toàn vì nó vẫn bị ẩn.

Xóa vĩnh viễn bài giao dùng endpoint DELETE hiện có. Chủ sở hữu đã cho phép rõ ràng việc xóa mọi lượt làm bài học viên liên kết, phiên Full Mock, điểm, phản hồi AI, bản ghi âm, sự kiện chính sách, gia hạn, thông báo bài giao và tham chiếu kế hoạch học tập, kể cả khi học viên đã hoàn thành. Xác nhận nêu rõ không thể đảo ngược. Không xóa bản ghi TestVersion và tài sản đề dùng chung. Remove from Classwork vẫn là lựa chọn riêng không phá hủy. Xóa tài nguyên cũng tự gỡ liên kết bài đăng/kế hoạch nhưng giữ các bài đăng/kế hoạch đó.

`DELETE /classrooms/{classroom_id}/assignments/{assignment_id}/classwork` mở rộng thao tác gỡ an toàn hiện có tới bài giao chuẩn không có hàng vị trí. Nó đặt `classwork_hidden`, chỉ gỡ liên kết Classwork trong phạm vi, tăng bản sửa đổi nội dung và trả ảnh chụp Classwork bình thường. Thao tác nhận `expected_revision` tùy chọn, với xung đột `CLASSWORK_CHANGED` giống gỡ mục. Endpoint DELETE theo mục ban đầu vẫn có. Khôi phục bài giao không đảo ngược việc gỡ chủ động này; phải chủ động đặt vào chủ đề.

Thao tác nội dung yêu cầu `content.manage`; thao tác bài giao yêu cầu `assignments.manage`. Quyền giám sát quản trị viên toàn cục tiếp tục chỉ đọc, kể cả đường bỏ qua lưu trữ trước đây. Học viên, giáo viên không liên quan và nhân sự bị thu hồi quyền không được thực hiện thay đổi này. Lớp đã lưu trữ từ chối ghi. Alembic revision `20261028_0042` bỏ hạn chế DELETE khỏi trigger bất biến sự kiện chính sách; UPDATE vẫn bị cấm. Áp dụng migration trước khi xóa vĩnh viễn. Migration không xóa dữ liệu hiện có.

## Đồng bộ giao diện

Nhóm đã lưu trữ ban đầu được thu gọn, dùng bề mặt phụ theo ngữ nghĩa và giữ số lượng chính xác. Một menu ngữ cảnh cung cấp khôi phục/gỡ/xóa; chi tiết bài giao được liên kết một lần trong hàng. Hộp thoại mô tả hậu quả và giữ hành vi bàn phím/tiêu điểm hiện có. Có chặn thao tác ghi trùng. Nếu ghi thành công rồi tải lại thất bại, cung cấp thử tải lại mà không lặp thao tác ghi.

Không gian làm việc giữ ảnh chụp bài giao chuẩn. Thay đổi bài giao tải Classwork và danh sách bài giao mỗi loại một lần, làm mới tiến độ được phân quyền và vô hiệu hóa lịch theo metadata vòng đời/lịch bài giao. Thay đổi chỉ nội dung chỉ tải lại Classwork. Trạng thái mở chủ đề được giữ qua cập nhật. Lịch đã truy cập tiếp tục được gắn qua chuyển thẻ, giữ lựa chọn, chế độ xem và bộ lọc mà không lặp yêu cầu giống nhau. Khi mở lại, Stream tải lại qua bảng tin được phân quyền hiện có.

## Dữ liệu lịch và ngày

Lưới tháng mặc định từ thứ Hai đến Chủ nhật, gồm ngày tháng liền kề. Chế độ tháng, tuần bảy ngày và danh sách dùng cùng sự kiện AVAILABLE, DUE và CUTOFF. Bộ lọc áp dụng cho mọi chế độ, chi tiết ngày chọn và thống kê tháng. Đếm bài giao tháng loại trùng ID. Nhân sự thấy thống kê lịch; học viên chỉ thấy tiến độ API được phân quyền. Tái sử dụng mục tiêu bài giao và callback chi tiết hiện có.

Mỗi lưới hiển thị tối đa sáu tuần, trong giới hạn API 93 ngày hiện có. Mọi trang 50 sự kiện được tải tuần tự dưới một AbortSignal. Tổng đầu tiên giới hạn phân trang. Tổng thay đổi, trang thiếu hoặc danh tính sự kiện trùng gây lỗi với Retry thay vì âm thầm hiển thị tháng thiếu dữ liệu. Phản hồi khoảng ngày cũ/đã hủy không được ghi đè khoảng hiện tại. Không tải theo từng ngày. Ô ngày hiển thị tối đa ba chip sự kiện cộng điều khiển xem thêm; bảng ngày được chọn cung cấp đầy đủ nội dung ngày.

Giá trị chỉ ngày được tạo từ thành phần năm/tháng/ngày cục bộ. Điều hướng ngày/tháng dùng phép tính lịch, không cộng cố định 24 giờ. Giới hạn API là nửa đêm cục bộ đổi sang UTC, với điểm cuối loại trừ; nhóm ngày dùng múi giờ thiết bị người xem. Cách này giữ ngữ nghĩa gia hạn học viên từ backend. Nút ngày phân biệt hôm nay với lựa chọn và hỗ trợ phím mũi tên, Home và End. Chi tiết xếp dưới lưới trên màn hình nhỏ; chế độ tuần di động xếp bảy mục ngày. Màu lấy từ token sáng/tối hiện có.

## Xác minh và giới hạn

Kiểm thử có trọng tâm bao quát tuần tự hóa tuyến ASGI thật không cần máy chủ/cơ sở dữ liệu, khả năng theo phạm vi, tính lũy đẳng khôi phục, bảo toàn metadata đóng băng/lịch, tham chiếu xóa cứng trong phạm vi, gỡ an toàn, khôi phục DRAFT, chặn ghi trùng, số lần làm mới chuẩn, giữ ngày chọn, phân trang, hủy, phản hồi lỗi thời, bộ lọc, số tổng hợp, điều hướng bàn phím và hợp đồng CSS ở 375/768/1024/1440px. Phép tính ngày đã được kiểm tra ở múi giờ cục bộ, America/New_York và Pacific/Honolulu.

Bộ dữ liệu phân trang đo được tải đủ 123 sự kiện tại offset 0, 50 và 100. Kiểm thử hồi quy không gian làm việc xác nhận mỗi lần khôi phục chỉ tải lại Classwork một lần và danh sách bài giao một lần; quay lại Calendar không tải lại. Đây là kiểm tra yêu cầu/hành vi xác định, không phải đo độ trễ trình duyệt.

Không mở trình duyệt, chạy máy chủ phát triển cục bộ, toàn bộ hệ thống, bản dựng production, Playwright/Cypress, toàn bộ bộ kiểm thử hoặc gọi AI thật. Bản sửa xóa cứng sau đó chỉ áp dụng migration `0042` sau khi người dùng cho phép rõ ràng, cùng kiểm tra chỉ đọc trigger kết quả; không xóa bài giao thật để xác minh. Xác minh trực quan trên trình duyệt và thực thi tích hợp PostgreSQL chưa được thực hiện. Theo yêu cầu người dùng, không chờ CI từ xa.

Taste Skill và UI/UX Pro Max đã cài được dùng để xây dựng thao tác ngữ cảnh gọn, xác nhận theo hậu quả, lựa chọn rõ ràng, ký hiệu dữ liệu có ngữ nghĩa và bố trí chi tiết thích ứng. Bảng màu hải quân, kiểu chữ và khung hiện có đã được người dùng phê duyệt được ưu tiên hơn gợi ý kiểu thay thế của kỹ năng. Không thêm thiết kế lại, thư viện biểu đồ/lịch hoặc ngữ cảnh tùy chọn bổ sung.

## Khu vực thay đổi

- Backend: router và service bài giao/Classwork; `test_classroom_archive_unit.py`.
- Client frontend: `classrooms.ts`, `classroom-content.ts`.
- Giao diện lưu trữ: danh sách bài giao; bảng Classwork, phần và hàng; thao tác bài giao đã lưu trữ; thông điệp nội dung; đồng bộ không gian làm việc.
- Giao diện lịch: điểm vào hiện có, bảng tập trung, hàm ngày/dữ liệu, thông điệp bản địa hóa và stylesheet lịch.
- Kiểm thử: lập lịch bài giao, Classwork, không gian làm việc, hợp đồng ngày/CSS của lịch.

Commit trang chủ đi kèm thêm điều khiển biểu tượng VI/EN và giao diện đích cho khách qua PersonalizationProvider hiện có. Nó giữ `ielts-locale`, `ielts-theme` và lưu màu nhấn, ưu tiên tài khoản và SSR/bootstrap xác định. Kiểm thử có trọng tâm bao gồm lưu trữ bị chặn, hydration, liên kết xác thực, không gửi yêu cầu tùy chọn khách và giữ danh tính cảnh/tạm dừng thủ công/cuộn. Gradient tối và bảng màu văn bản hiện có được giữ; hiệu ứng sáng CTA và màu đăng ký đầu trang nay thích ứng Dark Mode.
