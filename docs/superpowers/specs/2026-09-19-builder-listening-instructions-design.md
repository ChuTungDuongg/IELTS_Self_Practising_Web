# Điều hướng Builder, âm thanh Listening dùng chung và hướng dẫn Reading

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Điều hướng Builder, âm thanh Listening dùng chung và hướng dẫn Reading. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/domains/questions/registry.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/authoring.md); [kiểm toán và giới hạn](../../DOCS_AUDIT.md). Kết quả kiểm thử/đo hiệu năng bên dưới thuộc lần thực hiện gốc, không phải lần chạy lại trong đợt kiểm toán này.

## Phạm vi

Thay đổi này giữ nguyên kiến trúc Next.js/FastAPI/PostgreSQL và danh tính ổn định của phần/câu hỏi hiện có. Nó sửa điều hướng không gian Builder, chuyển quyền sở hữu âm thanh Listening từ từng `ListeningPart` sang `TestModule` Listening, thêm `yes_no_not_given` và tập trung hóa việc hiển thị hướng dẫn nhóm câu hỏi.

## Điều hướng Builder

Tuyến chỉnh sửa chuẩn vẫn là `/admin/tests/[testId]/versions/[versionId]/edit`. Tham số truy vấn `workspace` chọn `overview`, `reading` hoặc `listening`. Trang máy chủ xác thực tham số và chỉ hiển thị không gian tương ứng. Điều hướng dùng Next.js `Link`, nên lựa chọn được lưu trong URL và tồn tại qua `router.refresh()`. Writing tiếp tục là vùng giữ chỗ không tương tác cho đến khi có Writing Builder.

## Âm thanh Listening dùng chung

`TestModule.audio_asset_id` cho phép null và chỉ dùng cho mô-đun Listening. `ListeningPart.audio_asset_id` bị loại bỏ sau khi xác thực migration và điền dữ liệu cũ. DTO Builder, bài thi đang diễn ra và xem lại cung cấp một tài sản âm thanh Listening ở cấp mô-đun; các phần riêng lẻ không còn cung cấp âm thanh.

Migration xử lý dữ liệu cũ như sau:

- không có âm thanh ở phần nào: âm thanh mô-đun tiếp tục là null;
- có một âm thanh khác biệt duy nhất trong toàn mô-đun: sao chép nó sang mô-đun;
- nhiều tham chiếu đến cùng âm thanh: sao chép ID dùng chung một lần;
- có nhiều hơn một âm thanh khác biệt: dừng với lỗi rõ ràng trước khi xóa cột cũ.

Endpoint gắn âm thanh nhắm tới mô-đun Listening, kiểm tra quyền sở hữu bản nháp và loại/phiên bản tài sản, đồng thời chỉ thay đổi khóa ngoại của mô-đun. Thay thế hoặc gỡ âm thanh không được lan truyền xóa sang phần hay câu hỏi. Giao diện thí sinh và xem lại gắn một trình phát bên ngoài nội dung từng phần, nên chuyển phần không gắn lại hoặc khởi động lại trình phát.

## YES / NO / NOT GIVEN

`yes_no_not_given` là loại riêng trong registry frontend và backend. Nó dùng kiểu trả lời cơ sở chọn một phương án với các giá trị chuẩn `YES`, `NO` và `NOT_GIVEN`. Chuẩn hóa chấp nhận quy ước dấu gạch dưới/khoảng trắng hiển thị hiện có, còn lưu trữ và chấm điểm dùng giá trị chuẩn.

## Kiến trúc hướng dẫn

Mỗi định nghĩa trong registry câu hỏi frontend sở hữu một bộ sinh hướng dẫn. Bộ sinh nhận nhóm cùng số bài đọc theo ngữ cảnh và trả về lời giới thiệu cùng các giải thích có nhãn nếu cần. `group.instruction` đã lưu vẫn được dùng làm nội dung ghi đè tùy chỉnh. Các giá trị mặc định được sinh không bị lưu trùng trong cơ sở dữ liệu.

`QuestionGroupInstruction` là thành phần hiển thị hướng dẫn duy nhất. Builder Preview, Reading Runner và Reading Review dùng nó đúng một lần cho mỗi nhóm. Số bài đọc dùng `order_index + 1` tính từ chỉ số bắt đầu bằng không của bài đọc. Hướng dẫn điền chỗ trống lấy giới hạn từ/số từ cấu hình câu hỏi; khi các câu có giới hạn khác nhau, dùng lời hướng dẫn yêu cầu thí sinh tuân theo giới hạn được cấu hình cho từng câu trả lời.

## Tương thích và xác thực

Các phiên bản đã xuất bản tiếp tục bất biến. Nhân bản sao chép tham chiếu âm thanh cấp mô-đun. Kiểm tra bảo toàn tài sản bao gồm âm thanh cấp mô-đun. DTO bài thi đang diễn ra tiếp tục loại trừ đáp án. Hướng dẫn tùy chỉnh hiện có và toàn bộ UUID ổn định được bảo toàn.
