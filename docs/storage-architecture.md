# Lưu trữ tài sản riêng tư có thể chuyển đổi nhà cung cấp

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho nội dung này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác minh môi trường đang chạy.
> Mục đích: Lưu trữ tài sản riêng tư có thể chuyển đổi nhà cung cấp. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../backend/app/storage/factory.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/assets-transfer.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


PostgreSQL quản lý định danh, quyền sở hữu, vòng đời và các quan hệ. Bản ghi tài sản lưu khóa tương đối có thể di chuyển, không lưu URL của nhà cung cấp. Ứng dụng chọn Local (mặc định), S3 hoặc R2 qua `app/storage/factory.py` và `Settings` hiện có. FastAPI cấp quyền truy cập nội dung riêng tư trước khi truyền dữ liệu; không lệnh khôi phục nào công khai nội dung Speaking hoặc bucket. Định danh/lịch sử TestVersion được giữ nguyên.

Danh mục tham chiếu bền vững không lọc theo trạng thái hoạt động/đã xuất bản:

| Nguồn trong cơ sở dữ liệu | Tài sản / vòng đời |
| --- | --- |
| `assets.relative_path` | Sơ đồ Reading, ảnh Writing, âm thanh Listening; mọi phiên bản nháp, lưu trữ và lịch sử, kể cả tệp tải lên chưa dùng nhưng vẫn thuộc một phiên bản |
| `test_covers.relative_path` | Ảnh bìa hiện thuộc bài thi |
| `classroom_resources.storage_key` | Tài nguyên FILE, kể cả tài nguyên đã lưu trữ |
| `speaking_audio_chunks.storage_key` | Lượt thu/khối âm thanh riêng tư, kể cả lượt không hoạt động còn được giữ; kích thước/SHA-256 kỳ vọng từ PostgreSQL và MIME từ đoạn thu |
| `speaking_normalized_audio.storage_key` | Đối tượng WAV/bộ nhớ đệm đã chuẩn hóa còn được giữ |
| `writing_benchmark_samples.task1_image_key` | Ảnh benchmark, kể cả mẫu nháp |

`speaking_media_cleanup` là outbox chờ xóa, không phải tham chiếu đang dùng. Các khóa này được báo cáo riêng. Bảng không có cờ thất bại; tác vụ đang chờ không tự động được mô tả là đã thất bại. Đối soát có thể tìm tác vụ mà đối tượng vẫn tồn tại nhưng không chạy dọn dẹp. Nếu tham chiếu trùng với mục dọn dẹp, đối tượng vẫn bắt buộc phải giữ và không được xóa.

Vùng tạm FFmpeg/ZIP, bộ nhớ đệm mô hình, tệp PostgreSQL và bản sao lưu không phải tham chiếu tài sản thông thường. Di chuyển/sao lưu mặc định chỉ sao chép đối tượng có tham chiếu. Việc liệt kê namespace theo yêu cầu báo cáo đối tượng có thể mồ côi mà không xóa; danh sách cũng có thể chứa tệp tạm hợp lệ, `.gitkeep` hoặc phần còn lại của quá trình xử lý. Không suy ra rằng đối tượng không có tham chiếu có thể được xóa an toàn khi hệ thống đang ghi.

Công cụ vận hành tái sử dụng cổng trừu tượng lưu trữ. `migration.py` thực hiện sao chép có giới hạn, kiểm tra checksum và đối soát chỉ đọc; `operations.py` xử lý cấu hình nguồn/đích tường minh và snapshot cơ sở dữ liệu; `recovery.py` xử lý gói sao lưu v2 có thể chuyển đổi nhà cung cấp. Script di chuyển và điểm vào sao lưu/khôi phục hiện có dùng các mô-đun này. Không có kiến trúc lưu trữ nghiệp vụ thứ hai hoặc chế độ ghi kép.

Thao tác đối tượng dùng bộ đệm đọc 1 MiB, 1–8 worker sao chép, lượng việc chờ có giới hạn và cơ chế timeout/thử lại/tạo có điều kiện hiện có của adapter. Mỗi đối tượng tuân theo hợp đồng 5 GiB; siêu dữ liệu sao lưu giới hạn manifest 64 MiB / 250,000 đối tượng. Danh mục siêu dữ liệu vẫn có độ phức tạp O(số bản ghi). S3 ghi từng đối tượng qua đĩa tạm, vì vậy cần đủ dung lượng tạm cho đối tượng lớn nhất trên mỗi worker. Sao lưu còn cần chỗ cho dump cơ sở dữ liệu và tệp nén. Không dùng ETag làm mã băm.

Việc đưa dữ liệu đám mây xuống tệp tạm luôn tường minh và có giới hạn. Tác vụ SDK/PG/tệp gây chặn chạy ngoài luồng điều phối cơ sở dữ liệu bất đồng bộ; khi hủy, công cụ chờ tác vụ dump/ghi archive đang chạy kết thúc trước khi giải phóng snapshot đã xuất. Không thêm thao tác liệt kê bucket vào khởi động ứng dụng, tuyến HTTP hoặc worker.

Xem [di chuyển](storage-migration.md), [sao lưu/khôi phục](storage-backup-restore.md), [Modal](modal-web.md), [AWS](aws-deployment.md) và [trạng thái xác minh](storage-portability-work-in-progress.md). Xác minh ngoại tuyến tách biệt với IAM/R2/Modal thực tế, TLS/mạng và diễn tập khôi phục production. Thay đổi Settings không tự động di chuyển dữ liệu.


## Private Speaking Benchmark recordings

The [admin lab](testing/admin-speaking-benchmark.md) stores original MP3/WAV under opaque `benchmark/speaking/<sample UUID>/<random UUID>.<extension>` keys through AssetStorage. Keys never appear in DTOs or public Asset routes. Owner-scoped authenticated Range delivery serves the original bytes. Samples and SHA/size/duration metadata live in PostgreSQL; derived decode files are temporary. Inventory/backup/compensation recognize these keys. Upload reservations and sample deletion use the durable media-cleanup outbox with a one-hour grace and reference checks. Failed cleanup remains retryable.
