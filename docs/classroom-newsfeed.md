# Bảng tin lớp học

> **Kiểm toán tài liệu: CURRENT.** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Bảng tin lớp học. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../backend/app/repositories/classroom_feed_search.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/classrooms.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/đo hiệu năng bên dưới thuộc lần thực hiện gốc, không phải lần chạy lại trong đợt kiểm toán này.

Hình Stream đã được phê duyệt được triển khai trong không gian Classroom hiện có. Màn hình máy tính từ 1100px dùng tỷ lệ bảng tin/thanh bên co giãn 69/31 với khoảng cách 18px, bề mặt xanh hải quân bo tròn gọn ở Dark Mode, huy hiệu loại, một ảnh đại diện tác giả, metadata tiết chế và xem trước bài giao/tài nguyên. Máy tính bảng xếp bảng tổng quan dưới bảng tin thành hai cột; di động dùng một cột, bộ lọc xuống dòng và điều khiển 44px. Token BandPilot dùng chung bảo toàn Light Mode, màu nhấn cá nhân, chỉ báo tiêu điểm và giảm chuyển động. Điều hướng toàn cục, Classwork, Assignments, Calendar và trình làm bài giữ thiết kế hiện có.

## Tương tác và dữ liệu thực

Vùng soạn gọn mở rộng `PostComposer` hiện có. Thao tác Announcement và Discussion chọn trước loại tương ứng mà API hỗ trợ. Thao tác File và Link tái sử dụng `ResourceEditor` và endpoint Classwork hiện có, không tạo bài đăng thứ hai cho một hoạt động tài nguyên chuẩn. Thao tác thông báo ở đầu trang mở, cuộn và đưa tiêu điểm tới cùng vùng soạn. Vẫn hỗ trợ bản nháp, xuất bản, chỉnh sửa và đính kèm. Thay đổi thành công làm mới bảng tin mà không tải lại toàn trang; nếu đọc thất bại sau ghi thành công, cung cấp thử tải lại mà không lặp thao tác ghi.

Thẻ thông báo/thảo luận giữ chỉnh sửa, xuất bản/gỡ xuất bản, ghim/bỏ ghim, khóa/mở khóa, lưu trữ, xóa và chuỗi bình luận tải khi cần theo khả năng được cấp. Số bình luận lấy từ backend; sau khi bình luận, chỉ đọc lại số lượng chuẩn của bài đăng đó và giữ các trang bảng tin đã tải. Xem trước bài giao dùng ngữ cảnh bài giao hiện tại để lấy tiêu đề thật, mục tiêu chính xác và mốc hạn nộp/hạn đóng tuyệt đối. Callback mở luồng bài giao hiện có, bao gồm bắt đầu/tiếp tục/kết quả được phân quyền của học viên ở nơi khác. Xem trước tài nguyên dùng tên tệp, dung lượng hoặc máy chủ liên kết HTTP an toàn thực tế và luồng đọc/tải xuống có xác thực hiện có. Không thêm khóa lưu trữ hay đường bỏ qua tài sản công khai.

Phản ứng và trạng thái trực tuyến trong ảnh chụp không có nguồn dữ liệu lưu trữ trong ứng dụng hiện tại nên bị lược bỏ. Không thay bằng tên mẫu, số tương tác, ngày, điểm hay tổng lớp học giả. Chữ cái thay ảnh đại diện dùng tên thực được phép truy cập; nhãn Author trung tính tránh suy đoán vai trò nhân sự lớp học từ vai trò USER toàn cục. Thời gian dùng bộ định dạng GMT+7 hiện có của dự án để máy chủ và máy khách hiển thị nhất quán.

## Tìm kiếm và phân trang

Endpoint bảng tin hiện có thêm `search` tùy chọn (tối đa 200 ký tự) và `pinned_only`. Tìm kiếm không phân biệt hoa thường và dấu tiếng Việt, kể cả dấu tổ hợp. Biểu thức PostgreSQL có tham số dùng hàm gốc, không cần extension/migration. Ký tự đại diện LIKE được escape. Phạm vi khớp gồm tiêu đề/nội dung bài đăng, tiêu đề/hướng dẫn/tên đề chuẩn của bài giao và tiêu đề/mô tả/nội dung/tên tệp/URL của tài nguyên. Giữ nguyên quyền hiển thị xuất bản/chủ đề và loại trùng đính kèm chuẩn.

UNION có giới hạn vẫn trả tối đa 20 mục cộng một mục đánh dấu trang kế tiếp. Bộ khóa phân trang vẫn là `(pinned, created_at, kind, id)`. Con trỏ nay gắn với tìm kiếm đã chuẩn hóa và phạm vi ghim bên cạnh lớp học/trạng thái/loại; đổi truy vấn sẽ từ chối con trỏ không tương ứng. Con trỏ hiện có giữ mặc định tìm kiếm rỗng/không giới hạn ghim. Giao diện trì hoãn tìm kiếm 280ms, đặt lại phân trang khi truy vấn đổi, hủy yêu cầu lỗi thời và bỏ qua đồng bộ liên kết sâu đến muộn. Bộ chọn All và loại/ghim dùng truy vấn backend thay vì lọc trang đã tải.

## Nguồn dữ liệu thanh bên

| Mục | Nguồn |
| --- | --- |
| Học viên đã tham gia | `active_member_count` của Classroom được phân quyền |
| Bài giao đang hoạt động | Ảnh chụp đầy đủ bài giao hiện có, chỉ bản ghi ACTIVE |
| Hạn sắp tới | Mốc thời gian bài giao cho nhân sự; tiến độ được phân quyền lấy theo lô kèm gia hạn có hiệu lực cho học viên |
| Tài nguyên dùng chung | Ảnh chụp đầy đủ Classwork hiện có, tài nguyên PUBLISHED trong chủ đề đã xuất bản/chưa gán |
| Thành viên | Giáo viên lớp cùng tối đa ba danh tính thành viên đang hoạt động đã tải, chỉ khi có quyền danh sách lớp |
| Hoạt động gần đây | Ba mục chuẩn mới nhất từ chế độ bảng tin đang tải, ghi nhãn rõ phạm vi này |

Không có yêu cầu riêng cho từng chỉ số hoặc yêu cầu danh sách lớp bổ sung. Học viên không yêu cầu danh sách dành cho nhân sự. Bài làm học viên đã hoàn thành/lưu trữ/đóng và bài giao không có ngày không xuất hiện trong phần sắp tới. Hạn nộp và hạn đóng tuyệt đối tiếp tục khác nhau; không tự động gia hạn mốc thời gian. Đồng hồ hiển thị đồng bộ theo phút chỉ cập nhật thanh bên, không thăm dò mạng. Liên kết thanh bên dùng điều hướng Classroom hiện có; Recent Activity có thể đặt lại bộ lọc bảng tin hoặc đưa tiêu điểm tới mục hiện có.

Trạng thái Stream tiếp tục được gắn sau lần truy cập đầu tiên để bộ lọc, trang đã tải và trình soạn chưa lưu tồn tại khi chuyển thẻ. Quay lại sau thay đổi bản sửa đổi Classwork hoặc vòng đời bài giao sẽ vô hiệu hóa bảng tin một lần. Đổi ngôn ngữ và truy cập lại thẻ không đổi không tải lại dữ liệu. Bình luận, trình đọc tệp riêng tư và theo dõi tiếp tục được tải theo nhu cầu.

## Quyền và xác minh

`classroomPermissions()` và FastAPI tiếp tục là nguồn chuẩn. Biên soạn của chủ sở hữu/đồng giảng viên dùng khả năng thực tế. Học viên đọc nội dung đã xuất bản và bình luận chỉ qua quy tắc thành viên/hạn thời gian hiện có. Admin Observer không có vùng soạn, thao tác ghi bài đăng, gửi bình luận, thay đổi thành viên hay quản lý bài giao, kể cả khi frontend cung cấp cờ biên soạn lỗi thời. Nhãn observer hiện có và từ chối ghi ở backend vẫn giữ nguyên.

Tập kiểm thử chính có trọng tâm đạt 161 kiểm thử frontend trong 12 tệp, cộng 73 kiểm thử backend không cần cơ sở dữ liệu (69 trường hợp tìm kiếm/con trỏ/observer và bốn trường hợp schema/tuyến/con trỏ/dấu xóa bảng tin hiện có). TypeScript, ESLint theo phạm vi, Ruff kiểm tra/định dạng theo phạm vi và kiểm tra khoảng trắng diff đều đạt. Công cụ chỉ kiểm tra mã nguồn của Taste báo không có lỗi; cảnh báo duy nhất tương ứng khóa dịch `unlock` hiện có dùng mở bình luận. Kiểm thử bao quát nguồn thanh bên, hạn có hiệu lực, ranh giới quyền, phân trang gắn tìm kiếm, hủy, liên kết sâu lỗi thời, luồng soạn, ngăn trùng, giữ trạng thái bảng tin, bình luận, trình đọc tài nguyên, bản địa hóa và hợp đồng CSS ở 375–1440px.

Có trường hợp tích hợp PostgreSQL dùng dữ liệu hư cấu cho tìm kiếm tiếng Việt, quyền hiển thị và kết quả ghim nhiều trang. Trường hợp này không chạy trên cơ sở dữ liệu phát triển. Không mở trình duyệt, chạy máy chủ phát triển, bản dựng production, E2E/toàn bộ bộ kiểm thử, migration/đặt lại cơ sở dữ liệu, dữ liệu production tổng hợp hoặc gọi AI thật. Khoảng cách hiển thị, tương phản, tràn màn hình 375px thực tế và độ giống ảnh chụp chưa được xác minh. Hình ảnh đã phê duyệt ghi đè hướng thiết kế thay thế của các kỹ năng; cả hai kỹ năng thiết kế đã cài đều được dùng khi rà soát mã nguồn.

Khu vực thay đổi: router/repository/service bảng tin và hàm tìm kiếm gốc; mục/bố cục Stream, vùng soạn, thẻ/xem trước/thanh bên/kiểu dáng; xử lý thử lại của trình biên tập bài đăng/tài nguyên hiện có; danh tính và điều hướng trang/không gian Classroom; HTTP client bảng tin có kiểu; kiểm thử frontend/backend có trọng tâm. Không thêm thư viện phụ thuộc hoặc mô hình lưu trữ.
