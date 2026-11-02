# Phân tích luyện tập cá nhân

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: mô tả phân tích luyện tập cá nhân. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../backend/app/services/analytics.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/analytics.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải kết quả chạy lại trong đợt kiểm toán này.

Không gian `/analytics` dùng phông Raleway/Segoe UI, token giao diện, khung ứng dụng và dịch vụ FastAPI Analytics giới hạn theo người dùng hiện có. Tệp kiểu dáng riêng nằm tại `frontend/src/features/analytics/analytics.css`.

## Phạm vi ngày và kỹ năng

- Lần lấy dữ liệu ban đầu ở máy chủ và điều khiển máy khách đều dùng **toàn bộ lịch sử**. Trong bước gắn tương tác phía máy khách, không lấy lại hoặc diễn giải lại tổng số từ trước tới nay.
- Các lựa chọn 7, 30 và 90 ngày bao gồm hôm nay theo lịch BandPilot, `Asia/Ho_Chi_Minh` (UTC+7), lấy mốc lúc tải trang. Chú thích ngày hiển thị chính xác các ngày lịch có tính cả hai đầu. API nhận mốc UTC rõ ràng và áp dụng khoảng nửa mở `[start, end)`.
- `GET /api/v1/analytics` nhận `start` và `end` tùy chọn có thông tin múi giờ. Mốc thiếu múi giờ, thứ tự ngược, bằng nhau hoặc khoảng đủ hai đầu dài hơn 3660 ngày trả 422. Bỏ hai đầu giữ hành vi toàn bộ lịch sử hiện có.
- Lượt đã hoàn tất thuộc ngày `finished_at`, dự phòng `started_at` cho bản ghi lịch sử thiếu mốc kết thúc. Lượt đang hoạt động/tạm dừng thuộc ngày bắt đầu. Đây là **nhóm lượt làm bài**, không phải đo số giây nằm trong cửa sổ lịch: toàn bộ thời gian hoạt động đã ghi của mỗi lượt được chọn đều được tính.
- Bộ lọc kỹ năng áp dụng cho số lượt hoàn tất, thời gian luyện tập, xu hướng, độ chính xác, phần cần chú ý, hoạt động gần đây, phân đoạn thời gian và tùy chọn so sánh. Như API hiện có, trung bình bốn kỹ năng, số bài thi thử hoàn tất, kết quả thi thử và điểm tổng suy từ luyện tập bao phủ mọi kỹ năng trong phạm vi ngày đã chọn. Chú thích nêu rõ điều này.
- Full Mock hoàn tất được đếm một lần mỗi phiên hoàn tất theo ngày kết thúc (dự phòng lịch sử: ngày bắt đầu). Kết quả có thể gồm lượt thành phần hoàn tất trước ngày phiên kết thúc.

## Ý nghĩa chỉ số

- Bốn thẻ chính hiển thị lượt toàn mô-đun đã hoàn tất, thời gian hoạt động đã ghi, phiên Full Mock hoàn tất và nguồn điểm tổng có nhãn. Các trạng thái hoàn tất và phạm vi toàn mô-đun hiện có không đổi; lượt gián đoạn/bỏ dở đã kết thúc vẫn được tính như trước.
- Tổng thời gian và trung bình thời gian ghi nhận giữ tập lượt đang hoạt động/tạm dừng hiện có. Bộ đếm thời gian loại thời gian thực tạm dừng. Thẻ thời gian không khẳng định trung bình chỉ giới hạn ở lượt hoàn tất.
- Thẻ điểm tổng ưu tiên điểm tổng Full Mock hoàn tất gần nhất nếu có, nếu không dùng điểm tổng suy từ luyện tập của API. Nguồn ghi cạnh giá trị; cả hai không được trình bày là kết quả thi IELTS chính thức.
- Phân đoạn điều hướng được ghi vẫn là số phân đoạn, không được gọi là thời gian mỗi câu, trung bình tác vụ Writing hoặc phân rã thời gian đầy đủ.
- Độ chính xác chỉ dùng câu trả lời Reading/Listening đã chấm (`is_correct` khác null). Phần cần chú ý yêu cầu ít nhất năm câu đã chấm cho mỗi loại câu hỏi thực sự đăng ký. Độ chính xác so sánh giữ hành vi điểm cuối hiện có.
- Hoạt động gần đây hiển thị năm lượt hoàn tất mới nhất, liên kết đến `/review/{attempt_id}` hiện có. Danh sách đầy đủ liên kết đến `/history`.

## Biểu đồ và tương tác

Mỗi kỹ năng quan sát được có đường gấp khúc SVG thẳng, màu và hình điểm riêng. Vị trí x theo thời gian dùng dấu thời gian; mốc bằng nhau giữ cùng vị trí. Giá trị null, không hữu hạn, ngoài band hoặc ngày không hợp lệ không được vẽ thành 0. Không thêm chuỗi điểm tổng, nội suy, tăng trưởng hư cấu hoặc đa giác radar. Mỗi điểm có điều khiển bàn phím gốc, chú giải có dấu thời gian và dòng tương ứng trong bảng điểm hỗ trợ tiếp cận. Chỉ giữ một điểm dừng Tab và điều hướng Left/Right/Home/End để tránh hàng trăm điểm Tab với lịch sử dài.

Bộ lọc chỉ chốt giá trị cùng phản hồi dữ liệu thành công. Yêu cầu lỗi giữ lựa chọn/kết quả trước đó và cho thử lại phạm vi lỗi. Đổi phạm vi thành công dựng lại bảng so sánh để yêu cầu cũ không ghi kết quả vào phạm vi mới. Tiêu đề do người soạn nhập vẫn là văn bản; tùy chọn so sánh mới kèm ngày kết thúc thật để phân biệt nhiều lượt cùng đề. Nhãn API cũ vẫn được hỗ trợ.

Các thẻ phụ giữ mọi trường so sánh hiện có, gồm tiêu chí Writing, điểm thô, độ chính xác, thời lượng và band. Khoảng ngày tùy chọn, tăng trưởng so với kỳ trước, biểu đồ radar và thời gian từng câu được chủ đích để ngoài phạm vi.

## Xác minh tập trung

Frontend:

```powershell
cd frontend
npm exec -- vitest run tests/analytics-page.test.tsx tests/analytics-dashboard.test.tsx tests/analytics-scope.test.ts tests/band-trend.test.tsx tests/speaking-api.test.ts --maxWorkers=2
npm run typecheck
npm exec -- eslint src/app/analytics/page.tsx src/features/analytics src/lib/api/analytics.ts src/lib/i18n/en.ts src/lib/i18n/vi.ts tests/analytics-page.test.tsx tests/analytics-dashboard.test.tsx tests/analytics-scope.test.ts tests/band-trend.test.tsx
```

Kiểm thử cơ sở dữ liệu backend chỉ dùng `isolated_db_session`. Tạo PostgreSQL kiểm thử mới, cung cấp `P2_TEST_DATABASE_URL` hoặc `TEST_DATABASE_URL` khác `DATABASE_URL` thường dùng, theo `backend/testsupport/test_database.py`. CI hiện có đã tạo dịch vụ riêng này. Không trỏ các lệnh vào cơ sở dữ liệu ứng dụng.

```powershell
cd backend
uv run --offline pytest tests/test_analytics.py tests/test_analytics_date_scope.py tests/test_analytics_date_validation.py tests/test_analytics_query_scope.py tests/test_test_database_safety.py -q
uv run --offline ruff check app/api/v1/analytics.py app/services/analytics.py app/schemas/analytics.py tests/test_analytics.py tests/test_analytics_date_scope.py tests/test_analytics_date_validation.py
```

Lần kiểm thử tích hợp tập trung dùng dữ liệu tổng hợp và phiên chỉ hoàn tác. Không cần migration lược đồ hoặc đổi dữ liệu sản xuất. Phạm vi tác vụ không gồm xác minh bằng trình duyệt/ảnh chụp, máy chủ phát triển, bản dựng và triển khai; hành vi thích ứng/giao diện được xem xét tĩnh và kiểm qua hợp đồng DOM/CSS, không tuyên bố đã xác minh thị giác.
