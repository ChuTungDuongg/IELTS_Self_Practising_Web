# Thiết kế chấm điểm IELTS, Writing và lịch sử

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Thiết kế chấm điểm IELTS, Writing và lịch sử. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/services/mts_writing.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

**Ngày:** 2026-09-20

**Trạng thái:** Đã phê duyệt

## Mục đích

Mở rộng ứng dụng luyện IELTS hiện có mà không thay kiến trúc Next.js → FastAPI → PostgreSQL. Thay đổi bổ sung chấm band IELTS do backend sở hữu, Builder và luồng làm Writing đầy đủ, lưu chấm Writing thủ công và hai chế độ lịch sử phối hợp, đồng thời bảo toàn mọi hành vi Reading/Listening hiện có.

## Quy tắc sản phẩm

- PostgreSQL tiếp tục là nguồn chuẩn. React tuyệt đối không sở hữu chấm điểm hoặc xác thực miền.
- Bản ghi `TestVersion` đã xuất bản tiếp tục bất biến; lượt làm lịch sử gắn với phiên bản đóng băng của chúng.
- Điểm thô Reading/Listening tiếp tục hiển thị cùng band chính thức.
- Reading/Listening chỉ nhận band chính thức khi `max_score == 40`.
- Reading/Listening dùng chính xác cùng bảng quy tắc sản phẩm của ứng dụng:

  | Điểm thô | Band |
  |---|---:|
  | 39–40 | 9.0 |
  | 37–38 | 8.5 |
  | 35–36 | 8.0 |
  | 33–34 | 7.5 |
  | 30–32 | 7.0 |
  | 27–29 | 6.5 |
  | 23–26 | 6.0 |
  | 20–22 | 5.5 |
  | 16–19 | 5.0 |
  | 13–15 | 4.5 |
  | 10–12 | 4.0 |
  | 7–9 | 3.5 |
  | 5–6 | 3.0 |
  | 3–4 | 2.5 |
  | 0–2 | không có band chính thức (`null`) |

- Writing tuyệt đối không có điểm thô hoặc điểm tối đa khách quan. Band cho phép null cho đến khi chấm thủ công.
- Band Writing thủ công từ 0.0 đến 9.0 theo bước 0.5.
- Điểm tổng của dự án là trung bình chính xác ba band Reading, Listening và Writing. Chỉ có khi đủ ba band và được làm tròn tới 0.5 gần nhất bằng quy tắc thập phân half-up. Điểm nằm đúng giữa tại một phần tư band được làm tròn lên với các điểm không âm này.
- Speaking và chấm Writing tự động vẫn ngoài phạm vi. Giao thức `WritingScoringProvider` hiện có giữ nguyên cho công việc tương lai.

## Kết quả khảo sát kiến trúc hiện có

Builder Reading/Listening dùng chung DTO `BuilderVersion` và endpoint tạo mô-đun tổng quát. Hành vi câu hỏi tập trung trong registry frontend/backend tương ứng. Mọi mẫu Listening được yêu cầu đã đăng ký và có trình biên tập, hiển thị thi, hiển thị xem lại, xác thực, đánh giá và kiểm thử, nên không tạo lại loại Listening nào.

`WritingTask`, `AttemptWritingResponse`, `WRITING_TASK_IMAGE`, bộ đếm từ backend/frontend và giao thức nhà cung cấp chấm Writing đã tồn tại. Dịch vụ phiên bản đã nhân bản task Writing nhưng payload Builder và thí sinh chưa cung cấp chúng. `WritingTask` cũng thiếu quan hệ tài sản rõ ràng.

Dịch vụ lượt làm hiện chỉ chấm yêu cầu nộp rõ ràng. Hết giờ và gián đoạn AFK chốt bài mà không chấm. Điều hướng xem lại xử lý Listening riêng, còn lại mặc định Reading. Lịch sử là danh sách phẳng thiếu định danh đề/phiên bản ổn định và band.

## Lưu trữ và migration

Thêm migration Alembic sau revision `20260919_0006`. Migration thêm `attempts.band_score NUMERIC(2,1)` cho phép null và bảo toàn toàn bộ cột/dữ liệu điểm hiện có. Downgrade chỉ xóa cột mới này.

Mô hình SQLAlchemy `Attempt` lưu giá trị dạng `Decimal | None`; DTO Pydantic công khai cung cấp `float | None`. Không thêm cột nguồn điểm vì luồng thủ công hiện tại không cần.

Thêm quan hệ `WritingTask.image_asset` dùng khóa ngoại `image_asset_id` hiện có. Không thêm bảng Writing song song.

## Miền chấm điểm

Tạo mô-đun chấm điểm backend có trọng tâm gồm:

- `listening_raw_to_band(raw_score: int, max_score: int) -> float | None`
- `reading_raw_to_band(raw_score: int, max_score: int) -> float | None`
- `round_to_half(value: Decimal) -> Decimal`
- `project_overall_band(reading, listening, writing) -> float | None`

Hai hàm đổi điểm thô sang band ủy quyền cho cùng bảng quy tắc sản phẩm bất biến nhưng vẫn là hàm công khai riêng, để chính sách Reading/Listening có thể khác về sau mà không đổi nơi gọi. Đầu vào ngoài `0 <= raw_score <= max_score` ném `ValueError`; điểm tối đa khác 40 trả `None`; điểm thô 0–2 trả `None`.

Dịch vụ lượt làm gán band khách quan sau tính điểm thô và tối đa. Nó xóa rõ cả ba trường điểm cho Writing. Chốt do backend kích hoạt được chuyển bất đồng bộ để chấm khách quan diễn ra trước khi lượt hết giờ hoặc gián đoạn AFK trở thành cuối cùng.

## Miền Builder Writing

`BuilderVersion` có thêm danh sách `writing_tasks` ở mỗi mô-đun. Task Builder gồm ID ổn định, số task cố định, chỉ số thứ tự cố định, đề bài, ID/metadata ảnh tùy chọn, số từ tối thiểu khuyến nghị và thời lượng khuyến nghị.

Tạo mô-đun `WRITING` qua endpoint mô-đun tổng quát hiện có tạo nguyên tử:

- Task 1: số 1, thứ tự 0, 150 từ, 1,200 giây, ảnh tùy chọn.
- Task 2: số 2, thứ tự 1, 250 từ, 2,400 giây, không ảnh.

API cập nhật task Writing chỉ cung cấp trường được sửa. Không thể đổi số task/thứ tự qua API. Task 1 có thể tham chiếu một `WRITING_TASK_IMAGE` thuộc bản nháp hiện tại. Task 2 từ chối mọi ID ảnh khác null. Thay thế/gỡ tái sử dụng hành vi dọn tài sản không còn tham chiếu hiện có.

Bản nháp được phép chưa hoàn chỉnh. Xác thực xuất bản coi thiếu task, đề trống và giá trị sẵn sàng không chuẩn là cảnh báo tại nơi nhất quán với chính sách Reading/Listening chưa đầy đủ hiện có. Danh tính task không hợp lệ, trùng số/thứ tự, ảnh Task 2, sai loại tài sản, tài sản mới gắn chéo phiên bản và task Writing thuộc mô-đun không phải Writing là lỗi cấu trúc chặn. Bộ xác thực phiên bản hiện có vẫn yêu cầu ít nhất một mô-đun có ý nghĩa.

Nhân bản tiếp tục sao chép task Writing và giữ tham chiếu ảnh theo ngữ nghĩa tài sản dùng chung hiện có. Đính kèm mới vào bản nháp nhân bản vẫn phải là tài sản tải cho bản nháp đó.

## API và vòng đời lượt làm Writing

DTO bài thi đang diễn ra tổng quát thêm `writing_tasks`. Hàng task thí sinh gồm đề, metadata ảnh Task 1 tùy chọn, số từ tối thiểu, thời lượng khuyến nghị, nội dung đã lưu và số từ đã lưu chuẩn từ máy chủ. Không chứa đáp án.

`PUT /attempts/{attempt_id}/writing/{writing_task_id}` nhận nội dung văn bản thuần. Backend:

1. khóa và đồng bộ lượt làm;
2. yêu cầu lượt Writing đang làm;
3. xác minh task thuộc chính xác phiên bản và mô-đun Writing của lượt làm;
4. tính số từ bằng hàm backend hiện có;
5. upsert `AttemptWritingResponse`;
6. cập nhật `last_active_at`; và
7. ghi `WRITING_UPDATED` với ID task trong metadata sự kiện.

Trình làm Writing dùng bộ đếm suy ra từ mốc thời gian hiện có. Đếm từ cục bộ chỉ là phản hồi hiển thị. Khi tải, nó khôi phục câu trả lời máy chủ, trì hoãn tự lưu để gộp thay đổi, cung cấp thao tác Save rõ ràng tức thì và lưu thành công task đang mở trước khi gọi endpoint nộp chuẩn. Lưu cuối thất bại chặn nộp và hiển thị lỗi có thể thử lại.

Nộp Writing chốt qua máy trạng thái lượt làm bình thường với `raw_score`, `max_score` và `band_score` giữ null.

## Xem lại Writing và chấm thủ công

Thêm payload và tuyến xem lại riêng Writing. Nó chứa mọi task theo thứ tự, đề, metadata ảnh Task 1, câu trả lời đã lưu hoặc rỗng và số từ máy chủ. Không chứa cấu trúc đáp án khách quan.

`PUT /attempts/{attempt_id}/writing-score` nhận band có ràng buộc. Backend yêu cầu:

- lượt làm Writing;
- trạng thái khác `IN_PROGRESS`;
- giá trị từ 0.0 đến 9.0; và
- bội số của 0.5.

Điểm lưu vào `Attempt.band_score`. Giao diện xem lại có bộ chọn ràng buộc, điều khiển Save rõ ràng, trạng thái thành công/lỗi và hiển thị ngay band đã lưu. Giao thức cho chấm tự động tương lai giữ nguyên.

## Hợp đồng lịch sử

Giữ một endpoint `/history` và mở rộng phản hồi thay vì thêm endpoint trùng. Nó trả:

- `items`: mọi lượt làm theo thứ tự thời gian đảo ngược hiện tại;
- `groups`: tổng hợp do backend tạo với khóa chính xác `test_version_id`; và
- `total`.

Mỗi mục gồm `test_id`, `test_version_id`, tiêu đề, số phiên bản, mô-đun, trạng thái, thời gian, điểm thô, điểm tối đa và band.

Với mỗi nhóm đề/phiên bản, backend chọn lượt mới nhất có trạng thái khác `IN_PROGRESS` cho từng mô-đun, sắp theo `finished_at` rồi `started_at`. Lượt cũ giữ trong `items`. Nhóm cung cấp các mục Reading, Listening, Writing được chọn cùng điểm tổng ba kỹ năng do backend tính.

Frontend hiển thị hai thẻ từ cùng payload này:

- **Theo kỹ năng:** mọi lượt riêng lẻ, Continue cho lượt đang làm, Review cho lượt đã chốt, xóa, thông báo không có band chính thức cho lượt khách quan không đủ 40 điểm tối đa và Not graded cho Writing chưa có band.
- **Theo đề:** một thẻ cho mỗi phiên bản đề chính xác, điểm mô-đun được chọn, điểm tổng chỉ khi đủ ba band và liên kết tới lượt riêng được chọn.

Sau xóa, trang làm mới từ backend để lựa chọn nhóm và điểm tổng tuyệt đối không được React tính lại độc lập.

## Tích hợp frontend

Bật `writing` trong `BuilderWorkspace`, định tuyến, chỉ số tổng quan và định tuyến xem trước. Thêm thành phần Builder, trình làm và xem lại Writing chuyên biệt thay vì mở rộng thành phần Reading/Listening bằng điều kiện mô-đun rải rác.

Thư viện luyện tập gồm mô-đun Writing đã xuất bản và bắt đầu qua API khởi tạo lượt hiện có. Writing dùng cùng hạ tầng thời gian mặc định 60 phút và các cấu hình thời gian sẵn có.

Xem trước bản nháp hiển thị cả hai đề, ảnh Task 1 nếu có và khuyến nghị từ/thời lượng từng task. Không có trình sửa câu trả lời thí sinh hoặc vùng giữ chỗ ảnh Task 2.

Kiểu mới mở rộng token thị giác, điều khiển, thẻ, sắc mô-đun, Dark Mode và breakpoint thích ứng hiện có. Textarea dài có chiều cao tối thiểu dễ dùng và đổi cỡ theo chiều dọc mà không tràn ngang toàn trang ở 390, 768, 1024 và 1440 pixel.

## Tương thích và xử lý lỗi

- Trường payload Reading/Listening hiện có giữ nguyên; trường mới chỉ bổ sung và mặc định rỗng/null trong schema frontend.
- Không được thay đổi nội dung đã xuất bản qua endpoint Writing.
- Payload thí sinh đang thi tuyệt đối không lộ đáp án.
- Lỗi lưu, tải lên, chấm và xóa có thể thử lại và dùng kiểu thông báo/hộp thoại hiện có.
- Thay đổi cục bộ `frontend/next-env.d.ts` hiện có được giữ và loại khỏi chỉnh sửa nhiệm vụ.
- Không thêm nội dung thi có bản quyền hoặc thư viện phụ thuộc thời gian chạy mới.

## Chiến lược kiểm thử

Kiểm thử được thêm trước hoặc cùng mỗi phần triển khai:

1. Biên bảng chấm thuần, đầu vào không hợp lệ, hành vi khác 40, làm tròn thập phân half-up và yêu cầu điểm tổng ba kỹ năng.
2. Tuần tự hóa migration/mô hình/schema và chốt khách quan, kể cả chốt do backend kích hoạt.
3. Khởi tạo mô-đun Writing, xác thực task, kiểm tra quyền sở hữu/loại tài sản, nhân bản và xác thực phiên bản.
4. Upsert câu trả lời Writing, số từ chuẩn do máy chủ tính, payload tiếp tục, ngữ nghĩa nộp và xác thực điểm thủ công.
5. Định danh lịch sử, chọn lượt đã chốt mới nhất, tuần tự hóa band và tính điểm tổng backend.
6. Builder Writing, tự lưu/lưu chủ động của trình làm, chấm ở xem lại, xem trước nháp, định tuyến và hai thẻ lịch sử.
7. Toàn bộ kiểm thử và lint backend, toàn bộ kiểm thử frontend, kiểm tra kiểu TypeScript, ESLint và bản dựng production.

