# Phân tích học tập lớp học và kế hoạch cải thiện

> **Kiểm toán tài liệu: CURRENT.** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Phân tích học tập lớp học và kế hoạch cải thiện. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../backend/app/services/classroom_learning.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/analytics.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/đo hiệu năng bên dưới thuộc lần thực hiện gốc, không phải lần chạy lại trong đợt kiểm toán này.

P4 mở rộng [Gradebook](classroom-gradebook.md), dùng bản ghi kết quả IELTS, quyết định bài nộp P2 và khả năng lớp học hiện có. Không thêm bộ máy chấm điểm, vòng đời bài thi, nhà cung cấp AI, hạ tầng embedding hoặc dự báo.

## Phạm vi và phân quyền

Phân tích dành cho giáo viên yêu cầu `analytics.view`: chủ sở hữu/đồng giảng viên có sẵn, TA cần bật cờ rõ ràng và ADMIN giữ quyền giám sát. Người tham gia lớp có thể đọc tiến độ của mình. Chi tiết học viên chỉ chứa bản ghi bắt nguồn từ bài giao của lớp đó, kể cả lịch sử lưu giữ. Luyện tập cá nhân tiếp tục riêng tư dù dùng cùng TestVersion. Mỗi yêu cầu đều kiểm tra lại quyền truy cập.

Quản lý kế hoạch yêu cầu `learning_plans.manage`. Nhân sự Gradebook có thể xem kế hoạch lớp; học viên chỉ được đọc kế hoạch của mình. Kế hoạch đang hoạt động yêu cầu tài khoản hoạt động và tư cách học viên, không gồm nhân sự lớp học. Học viên cũ trở thành TA giữ bài làm lịch sử nhưng không tính là học viên hiện tại. Lớp đã lưu trữ từ chối thay đổi.

## Kết quả và khoảng thời gian

Repository tái sử dụng `selected_grades` và quyết định chấp nhận lượt gốc P2 lịch sử. Trước tiên chọn điểm trên toàn lịch sử được chấp nhận của bài giao, rồi yêu cầu lượt gốc được chọn nằm trong khoảng nửa mở `[start, end)`. Khoảng mặc định: 90 ngày; tối đa: 366 ngày. Đổi chính sách chọn điểm Gradebook có thể đổi mẫu phân tích. Hai giao diện chủ động diễn giải bài giao nhất quán.

Một Attempt độc lập là một lượt gốc. Một TestSession Full Mock là một lần nộp bài giao, đóng góp mỗi thành phần đã chốt đúng một lần vào tổng hợp kỹ năng tương ứng. Lượt con của phiên không trở thành bài nộp riêng. Chỉ TestVersion đã xuất bản hoặc được lưu trữ lịch sử mới đóng góp kết quả. Reading/Listening dùng kết quả khách quan đã lưu; Writing/Speaking yêu cầu bản ghi chốt điểm của con người. Thiếu điểm giữ null. Bài tập trung có thể đóng góp bằng chứng câu hỏi/tiêu chí nhưng không cung cấp band toàn mô-đun. Tổng Full Mock yêu cầu đủ bốn band kỹ năng và phép tính IELTS gốc.

Hoàn thành, bài thiếu và yêu cầu đủ điều kiện dùng ngữ nghĩa nhóm học viên/bài nộp P2 hiện tại trên toàn bộ bài giao, độc lập với bộ lọc ngày của kết quả. Giao diện giải thích sự khác biệt này. Tỷ lệ hoàn thành là bài giao được chấp nhận / yêu cầu đủ điều kiện. Tỷ lệ đúng hạn là lượt được chấp nhận đúng hạn / mọi lượt được chấp nhận. Mẫu số rỗng trả phần trăm null.

## Bằng chứng và luyện tập lặp lại

Nhóm Reading/Listening lấy từ registry câu hỏi có cấu trúc. Lượt khách quan đã chốt cần điểm được lưu. Câu trả lời có độ đúng null bị loại; câu trả lời thiếu trong lượt đã chốt được tính là chưa trả lời và sai. DTO không chứa nội dung câu hỏi, câu trả lời hoặc đáp án. Độ chính xác câu nhiều đáp án dùng độ đúng toàn câu gốc, không thay thế cách chấm điểm thô có điểm thành phần.

Mẫu câu hỏi là lần tiếp xúc đã chấm mới nhất cho mỗi `(learner, question UUID)` trong lượt gốc/khoảng đã chọn. Phiên bản lặp không tạo bằng chứng độc lập mới. `questions_attempted` gồm câu chưa trả lời đã chốt sau loại trùng; `questions_correct`, `unanswered` và độ chính xác dùng chung mẫu số đó. Lần xuất hiện bổ sung được báo là `repeated_exposures`. Mẫu cấp lớp đại diện cặp học viên/câu hỏi, không phải số lượng câu biên soạn khác nhau tương ứng.

Gần đây là 30 ngày cuối kết thúc tại cuối khoảng; lịch sử là phần trước đó. Xu hướng câu hỏi yêu cầu năm mẫu ở cả hai giai đoạn và biểu diễn chênh lệch điểm phần trăm, nếu không trả null. Tiêu chí Writing tách Task 1 và Task 2. Tiêu chí Speaking tách bối cảnh toàn mô-đun và bối cảnh tập trung chính xác. Mẫu tiêu chí do người chấm được loại trùng theo ngữ cảnh học viên/task/phiên bản, giữ mẫu mới nhất. Xu hướng tiêu chí yêu cầu ba mẫu ở cả hai giai đoạn. Loại trừ đầu ra tư vấn AI.

Tổng hợp/lịch sử kỹ năng chứa band toàn mô-đun hợp lệ tách biệt cho Reading, Listening, Writing và Speaking. Số phiên bản khác nhau thể hiện việc dùng lại bài đánh giá. Biểu đồ học viên dùng mốc đánh giá và thang cố định 0–9, kèm lịch sử văn bản theo ngày. Lịch sử một điểm chỉ hiển thị dạng văn bản. Tổng hợp lớp không nối điểm các học viên khác nhau thành một đường tiến bộ.

## Ưu tiên luyện tập theo quy tắc xác định

| Quy tắc | Bằng chứng tối thiểu | Điều kiện kích hoạt | Mức độ/độ tin cậy |
| --- | --- | --- | --- |
| Loại câu hỏi | 10 cặp học viên/câu hỏi khác nhau, 5 gần đây | Độ chính xác gần đây dưới 60% | Mức cao khi dưới 40%; độ tin cậy cao cần 30 cặp khác nhau và 10 gần đây, nếu không là trung bình |
| Tiêu chí người chấm | 3 bài đánh giá gần đây khác nhau | Trung bình gần đây thấp hơn mục tiêu kỹ năng ít nhất 0.5, hoặc mốc tham chiếu 6.0 rõ ràng khi không có mục tiêu | Mức cao khi chênh 1 band; độ tin cậy cao cần 8 mẫu gần đây |
| Kỹ năng toàn mô-đun | 3 phiên bản gần đây khác nhau và mục tiêu kỹ năng rõ ràng | Trung bình gần đây thấp hơn mục tiêu ít nhất 0.5 | Mức vừa, độ tin cậy trung bình |

Dữ liệu thưa không tạo kết luận điểm yếu. Ưu tiên sắp theo mức độ, độ tin cậy, số mẫu giảm dần, kỹ năng và nhóm, giới hạn 20. Phản hồi cung cấp giá trị quan sát, mốc so sánh, lý do và số mẫu. Đây là quy tắc luyện tập đã ghi tài liệu, không phải chẩn đoán, chắc chắn thống kê hoặc dự đoán mức tăng IELTS tương lai.

Đề xuất kiểm tra 100 bài giao đang hoạt động mới nhất trong lớp của học viên. Quy tắc P2 hiện có về thành viên, xuất bản/kiểm duyệt, thời gian mở, hạn và giới hạn lượt làm quyết định tính đủ điều kiện. Loại bài giao đã được chấp nhận. Metadata kỹ năng/câu hỏi có cấu trúc phải khớp khoảng thiếu hụt quan sát được. Phiên bản chưa hoàn thành xếp trước phiên bản đã hoàn thành, rồi phá hòa bằng ưu tiên điểm yếu, bài chưa bắt đầu, ngày tạo và UUID. Kết quả loại trùng thành sáu liên kết bài giao thực với lý do xác định. Không có nội dung phù hợp thì hiển thị rỗng trung thực; không tự giao bài. Khám phá thư viện công khai nằm ngoài giai đoạn này.

## Mục tiêu và kế hoạch học tập

Mục tiêu xác thực band theo bước nửa điểm từ 0 đến 9. Tái sử dụng bốn cột kỹ năng hồ sơ hiện có; `users.target_overall_band` lưu mục tiêu tổng thể tùy chọn được khai báo rõ. Không có giá trị rõ này thì hiển thị mục tiêu hồ sơ suy ra hiện có. Lưu mục tiêu duy trì `target_band` suy ra của hồ sơ. Mục tiêu tuyệt đối không đổi điểm hoặc quy tắc chấm.

Kế hoạch chuẩn hóa lưu học viên/lớp học, người tạo/cập nhật, tiêu đề, kỹ năng mục tiêu, trọng tâm, mô tả, trạng thái, revision và thời gian. Mỗi kế hoạch có 1–30 tham chiếu duy nhất tới bài giao/tài nguyên hiện có. Khóa ngoại ghép trong cơ sở dữ liệu cưỡng chế hoạt động cùng lớp. Kế hoạch đang hoạt động chấp nhận tài nguyên đã xuất bản mà học viên thấy được và bài giao đang hoạt động. Tài nguyên ẩn hiển thị nhãn không khả dụng mà không lộ tiêu đề.

Hoàn thành bài giao lấy từ bài nộp được chấp nhận. Học viên đã tham gia có thể đánh dấu tài nguyên hiển thị không phải đánh giá là đã học; dấu tự báo cáo riêng này không hoàn thành bài giao IELTS. `COMPLETED` yêu cầu mọi hoạt động liên kết hoàn thành. Chỉnh sửa dùng revision kỳ vọng (409 khi lỗi thời). Kế hoạch đã lưu trữ và hàng mục không hoạt động giữ lịch sử. Trang kế hoạch mặc định 30, tối đa 50.

## API

Đường dẫn nằm dưới `/api/v1`. Khoảng thời gian yêu cầu thông tin múi giờ; `completion_offset` phân trang tổng hợp bài giao theo 20 mục.

| Đường dẫn | Phương thức / quyền |
| --- | --- |
| `/me/learning-goals` | GET/PUT mục tiêu của chính mình |
| `/classrooms/{id}/my-progress` | GET bảng tiến độ lớp học của chính mình |
| `/classrooms/{id}/my-recommendations` | GET đề xuất của chính mình |
| `/classrooms/{id}/analytics` | GET `analytics.view` |
| `/classrooms/{id}/students/{studentId}/analytics` | GET `analytics.view`, nhóm học viên/lịch sử lớp học |
| `/classrooms/{id}/learning-plans` | GET kế hoạch lớp học/học viên của chính mình hoặc được nhân sự phân quyền, limit/offset |
| `/classrooms/{id}/students/{studentId}/learning-plans` | POST `learning_plans.manage` |
| `/classrooms/{id}/students/{studentId}/learning-plans/{planId}` | PUT `learning_plans.manage`, revision kỳ vọng |
| `/classrooms/{id}/learning-plans/{planId}/items/{itemId}/complete-resource` | POST học viên đã tham gia có kế hoạch đang hoạt động, chỉ tài nguyên hiển thị |

Client frontend có kiểu trong `lib/api/classroom-learning.ts` xác thực phản hồi Zod và chuyển chuỗi mục tiêu Decimal tại ranh giới HTTP. Repository sở hữu SQL tổng hợp; service sở hữu quyền truy cập, phạm vi và quy tắc. Không có vòng truy vấn từng lượt làm bài cho từng học viên.

## Migration và giới hạn chủ động

Alembic `20261027_0038` thêm nhân sự/chính sách Gradebook theo phạm vi. `20261027_0039` thêm mục tiêu tổng cùng kế hoạch/mục. Cả hai đã được migration trên cơ sở dữ liệu cục bộ thật, xác minh tại `20261027_0039 (head)`. Nâng cấp mới trên môi trường cô lập và hạ cấp khi chưa có dữ liệu qua 0037/nâng cấp lại đều đạt. Chốt bảo vệ downgrade giữ dữ liệu nhân sự, chính sách điểm khác mặc định, kế hoạch và mục tiêu rõ ràng. Thêm enum kiểm toán vẫn là bổ sung. Ràng buộc mô hình khớp quy ước đặt tên migration có tiền tố hiện có.

Phản hồi giới hạn 60 điểm xu hướng/kỹ năng, 20 đánh giá gần đây, 200 nhóm tiêu chí (cờ cắt bớt), 20 tổng hợp hoàn thành/trang, 50 học viên cần chú ý và sáu đề xuất. Tập ứng viên đề xuất có giới hạn và chỉ trong lớp. Lọc kế hoạch đã lưu trữ diễn ra trong trang hiển thị. Triển khai lớn về sau có thể cần cache tổng hợp; không thêm hạ tầng phân tích nền. Xem [UX không gian làm việc](classroom-workspace.md) để biết thiết kế và giới hạn xác minh trên trình duyệt.
