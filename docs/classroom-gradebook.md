# Nhân sự lớp học và bảng điểm Gradebook (P3)

> **Kiểm toán tài liệu: CURRENT (đã sửa từ NEEDS UPDATE).** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Nhân sự lớp học và bảng điểm Gradebook (P3). Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../backend/app/services/classroom_capabilities.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/classrooms.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/đo hiệu năng bên dưới thuộc lần thực hiện gốc, không phải lần chạy lại trong đợt kiểm toán này.

P3 mở rộng P1/P2. Vai trò USER/TEACHER/ADMIN toàn cục và quyền sở hữu Builder tiếp tục độc lập với nhân sự lớp học. Chủ sở hữu vẫn là `classrooms.teacher_id`; không có hàng nhân sự cho chủ sở hữu.

## Quyền và vòng đời nhân sự

`ClassroomStaff` lưu trạng thái lời mời rõ ràng và bốn cờ TA tùy chọn có kiểu, không dùng từ điển quyền tự do. Enum `Capability` tập trung xác định vai trò lớp học hiện tại của người thực hiện trên từng yêu cầu. Chủ sở hữu có mọi khả năng của lớp học. Đồng giảng viên có thể quản lý học viên, nội dung, thảo luận, bài giao/gia hạn, điểm, phân tích và kế hoạch cải thiện; họ không được đổi cài đặt/quyền sở hữu lớp hoặc nhân sự. TA luôn có `grades.view`/`grades.edit`; `content.manage`, `discussion.moderate`, `analytics.view` và `learning_plans.manage` là cờ phải được chủ sở hữu chủ động bật. Học viên chỉ thấy lớp học được phân quyền và bài làm của mình.

Quyền ADMIN hiện tại là giám sát lớp học chỉ đọc: danh sách lớp, điểm và phân tích, được xác định bởi ADMIN_OBSERVER trong classroom_capabilities.py. ADMIN không được tạo/lưu trữ bài giao, sửa điểm hoặc tham gia qua tư cách thành viên cũ. Thao tác ghi của chủ sở hữu/đồng giảng viên/TA yêu cầu khả năng hiện hành cụ thể; quản lý lớp học vẫn chỉ dành cho chủ sở hữu.

Chỉ tài khoản đang hoạt động đã tồn tại mới được mời. Đồng giảng viên yêu cầu vai trò toàn cục TEACHER; TA yêu cầu USER hoặc TEACHER. Người nhận phải chủ động chấp nhận/từ chối lời mời. Chủ sở hữu có thể hủy, đổi vai trò/cờ và thu hồi quyền. Chỉ mục duy nhất có điều kiện cho phép một bản ghi nhân sự đang chờ hoặc đã chấp nhận cho mỗi lớp/tài khoản. Khóa người thực hiện/lớp tuần tự hóa lời mời và thay đổi vai trò cạnh tranh. Mỗi chuyển trạng thái nối thêm người thực hiện, vai trò, trạng thái và cờ vào lịch sử nhân sự được cơ sở dữ liệu bảo vệ. Quyền nhân sự đã chấp nhận được kiểm tra lại; vai trò đã cache không cấp quyền sau thu hồi.

Chấp nhận lời mời đóng tư cách học viên đang hoạt động trong cùng giao dịch. Bài nộp lịch sử vẫn tồn tại và có thể tìm thấy, còn nhân sự không được tính như học viên đang hoạt động bình thường trong chỉ số hoàn thành. Đăng ký lại làm học viên yêu cầu gỡ quyền nhân sự và lời mời học viên mới theo quy trình thường. Chặn hạ vai trò/vô hiệu hóa TEACHER toàn cục khi lời mời/tư cách đồng giảng viên vẫn yêu cầu TEACHER. Vô hiệu hóa tài khoản tiếp tục chặn truy cập có xác thực. Lớp đã lưu trữ cho phép đọc dữ liệu giữ lại và chặn thay đổi nhân sự.

Điều kiện giao bài lớp học vẫn yêu cầu nội dung chính thức hoặc nội dung giáo viên đã được phê duyệt của chủ sở hữu. Đồng giảng viên nhận endpoint metadata đề đủ điều kiện giao có giới hạn; việc này không cấp quyền Builder, đáp án chưa xuất bản, quyền chỉnh sửa hay bỏ qua kiểm duyệt.

## Điểm và cách lựa chọn

Gradebook dùng chung nguồn gốc lượt gốc, chấp nhận lịch sử bất biến và SQL nhóm học viên/trạng thái của P2. Attempt được giao trực tiếp là lượt gốc; TestSession Full Mock là một lượt gốc và các lượt con chỉ xuất hiện trong chi tiết kỹ năng. Luyện tập cá nhân và lượt gốc bị từ chối/chưa hoàn tất không cung cấp điểm được chấp nhận. Kết quả giữ lại không phụ thuộc việc hiện còn tham gia lớp hay không.

Điểm khách quan là điểm gốc do backend lưu. Writing/Speaking yêu cầu bản ghi chốt điểm của con người tương ứng; tuyệt đối không đọc lượt chạy AI. Thiếu điểm người chấm là `PENDING_HUMAN`, không bao giờ là không điểm. Đơn vị luyện tập tập trung không cung cấp band toàn mô-đun. Writing tập trung có thể hiển thị điểm trung bình gốc của task, ghi nhãn rõ là điểm task. Tổng Full Mock chỉ dùng bộ tổng hợp bốn kỹ năng gốc khi có đủ bốn band cuối hợp lệ; phiên ba kỹ năng cũ giữ chi tiết mà không bịa điểm tổng bốn kỹ năng.

Mỗi bài giao mặc định `LATEST_ACCEPTED`. `FIRST_ACCEPTED` chọn lần hoàn thành được chấp nhận sớm nhất. `BEST_ACCEPTED` chỉ xếp hạng trong bối cảnh đánh giá đồng nhất (kỹ năng, phạm vi đầy đủ/tập trung, đơn vị tập trung ổn định; hoặc thứ tự mô-đun Full Mock đã lưu). Band/điểm thô khách quan gốc hiện có hoặc trung bình task Writing tập trung quyết định thứ hạng; thiếu điểm so sánh được sẽ chuyển xác định sang lần hoàn thành mới nhất. Bối cảnh không đồng nhất dùng lượt được chấp nhận mới nhất và trả rõ `mixed_context_fallback`. Lọc một kỹ năng có thể tạo tập so sánh được. Ngày và UUID phá hòa. Sửa chính sách lựa chọn không đổi lịch sử lịch/gia hạn và nội dung đề; kiểm tra revision ngăn ghi trạng thái lỗi thời.

Ma trận phân trang học viên (mặc định 30, tối đa 100) và cột bài giao (20). Tìm kiếm, lọc bài giao, kỹ năng, hoàn thành và sắp tên thực hiện phía máy chủ. Sắp điểm yêu cầu lọc bài giao và kỹ năng để không ngụ ý xếp hạng chéo kỹ năng. Hồ sơ học viên phân trang tóm tắt bài giao và lịch sử lượt gốc thành công; số trạng thái mô tả trang bài giao đang hiển thị. Trang kết quả/chấm điểm hiện có tiếp tục là nguồn chuẩn.

CSV dùng cùng kiểm tra quyền, bộ lọc và cách xác định điểm được chọn. Một lần xuất có giới hạn chứa tối đa 200 học viên và 20 cột bài giao từ offset yêu cầu; cần lấy các trang sau cho lớp lớn hơn. Nội dung gồm cách lựa chọn, kỹ năng, band cuối/điểm thô cho phép null, nguồn gốc bài nộp và chấm điểm. Thứ tự cột ổn định. Escape CSV của Python, UTF-8 BOM và escape công thức bảng tính/ký tự điều khiển bảo vệ tên và tiêu đề xuất ra. Không chứa luyện tập cá nhân hoặc đáp án.

## API

Các đường dẫn nằm dưới `/api/v1`:

| Đường dẫn | Thao tác |
| --- | --- |
| `/me/classroom-staff-invitations` | GET lịch sử lời mời của chính mình có giới hạn |
| `/classrooms/{id}/staff` | GET danh sách/lịch sử nhân sự; POST lời mời của chủ sở hữu |
| `/classrooms/{id}/staff/{staffId}` | PATCH vai trò/cờ có kiểu của chủ sở hữu; DELETE hủy/thu hồi |
| `/classrooms/{id}/staff/{staffId}/{accept,decline}` | POST phản hồi của người nhận |
| `/classrooms/{id}/assignable-tests` | GET metadata đề đã xuất bản được phân quyền, có giới hạn để giao |
| `/classrooms/{id}/gradebook` | GET ma trận có phân trang |
| `/classrooms/{id}/gradebook/export` | GET CSV có xác thực và giới hạn |
| `/classrooms/{id}/assignments/{assignmentId}/grade-policy` | PATCH cách lựa chọn kèm revision kỳ vọng |
| `/classrooms/{id}/students/{studentId}/academic-profile` | GET hồ sơ lưu giữ chỉ thuộc lớp học |

`GET /classrooms/{id}` nay trả vai trò/khả năng theo ngữ cảnh. API thành viên/nội dung/bài giao/kết quả/lập lịch/chấm điểm lớp học hiện có kiểm tra từng khả năng cụ thể. Stream hỗ trợ bộ lọc `content_kind` phía máy chủ được gắn vào con trỏ phân trang.

## Cải tổ UX/UI lớp học

[Tái cấu trúc không gian làm việc với hai kỹ năng thiết kế](classroom-workspace.md) đã hoàn thành bổ sung luồng nội dung ưu tiên chủ đề, thao tác/tạo theo ngữ cảnh, chế độ ma trận/danh sách thích ứng và tích hợp [phân tích/kế hoạch học tập P4](classroom-learning-analytics.md). Ở mốc xác minh lịch sử đó, 0038 và 0039 được báo đã áp dụng cục bộ. Kho mã được kiểm tra hiện có Alembic head 20261028_0043; đợt kiểm toán này không kiểm tra revision cơ sở dữ liệu đang chạy. Xác minh P3 gốc bên dưới ghi lại ảnh chụp riêng của giai đoạn.

Khung khóa học dùng chung gồm đầu trang gọn với dữ liệu thực, một hàng thẻ cuộn, một vùng nội dung co giãn, không có thanh bên cố định rỗng hoặc bộ chọn phần trùng. Lưu trữ/khôi phục/rời lớp nằm trong vùng quản lý mở theo ngữ cảnh. Tạo mở biểu mẫu bài giao có trọng tâm; lập lịch hiển thị dần chi tiết. Nhân sự thấy tổng quan bài giao/thành viên thực và điều hướng trực tiếp Gradebook/People/tài liệu. Học viên thấy luồng học tập, không có thẻ quản trị nhân sự.

Mục bảng tin có tiêu đề dự phòng nổi bật, thời gian bản địa hóa có ngữ nghĩa, loại nội dung rõ và các hạn được nhóm. Classwork giữ truy cập tài nguyên gốc và sắp thứ tự bằng bàn phím/kéo, đồng thời giải thích khóa học rỗng bằng thao tác tạo phần đầu tiên. Gradebook dùng khung cuộn nội bộ, cột học viên cố định, tiêu đề bảng có ngữ nghĩa và chi tiết kết quả mở rộng. Màn hình nhỏ giữ phần tràn thẻ/bảng trong khung và dùng thao tác 44px. Cả hai ngôn ngữ và token sáng/tối dùng chung tiếp tục được sử dụng.

Tiếp nối thiết kế: `design-taste-frontend`, achromatic-ledger seed 2734, giữ bảng màu/kiểu chữ hiện có; làn kỹ năng IELTS và nguồn gốc điểm đã chấp nhận/đang chờ tạo bản sắc sản phẩm. Màn hình khóa học trả lời “Tiếp theo cần dạy hoặc hoàn thành việc gì?” và Gradebook trả lời “Bài làm được chấp nhận nào đã có điểm cuối?” Theo giới hạn xác minh của nhiệm vụ, không dùng trình duyệt, E2E, bản dựng production hay toàn bộ bộ kiểm thử; hành vi thích ứng được kiểm tra mã nguồn/đơn vị và không tuyên bố đã xác minh trực quan trên trình duyệt.

## Migration

Migration bổ sung `20261027_0038` theo sau P2 `0037`, thêm `classroom_staff`, `classroom_staff_events` chỉ cho nối thêm, chỉ mục/ràng buộc và `classroom_assignments.grade_selection`. Không ghi lại nội dung đề, nguồn gốc, bộ đếm thời gian hay điểm. Downgrade chỉ dành cho miền tính năng chưa được dùng và từ chối khi còn dữ liệu nhân sự/chính sách được giữ lại. Áp dụng qua quy trình triển khai Alembic bình thường sau khi xác minh migration trên môi trường cô lập.
