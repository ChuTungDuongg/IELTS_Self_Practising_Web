# Benchmark Writing Task 2 ngoại tuyến

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: mô tả benchmark Writing Task 2 ngoại tuyến. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../../scripts/benchmark_task2.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../docs/modules/writing.md); [kiểm toán và giới hạn](../../docs/DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải kết quả chạy lại trong đợt kiểm toán này.

`task2.jsonl` của ngân hàng quản trị dùng trực tiếp với CLI. JSONL là định dạng chuẩn; CSV chỉ để xem. `schema_version: 1` định danh định dạng tệp, không phải phiên bản ngân hàng/tập dữ liệu. Lược đồ sinh từ `app.evaluation.task2.models.BenchmarkSample`.

Nhãn người chấm gồm `tr`, `cc`, `lr`, `gra`, mỗi điểm từ 0–9 theo bước nửa band. Khi xuất dùng một người chấm, giá trị nguồn gốc dự phòng trung lập và mặc định không cho phân phối lại. Nhãn không đi vào suy luận. Task 2 không có hình ảnh, nhận thức thị giác hoặc DePlot.

Từ thư mục gốc kho mã, xác thực mà không dùng nhà cung cấp:

```sh
uv run --project backend python scripts/benchmark_task2.py --manifest benchmarks/writing_task2/private/task2.jsonl --split dev --dry-run --output benchmarks/writing_task2/reports/dev-plan
```

Tùy chọn chạy thử **thủ công** một mẫu qua nhà cung cấp (không phải kiểm thử triển khai/CI):

```sh
uv run --project backend python scripts/benchmark_task2.py --manifest benchmarks/writing_task2/private/task2.jsonl --split dev --limit 1 --max-concurrent-llm-requests 2 --resume --output benchmarks/writing_task2/reports/dev-smoke
```

Các mẫu chạy tuần tự. Trong mỗi mẫu, dịch vụ sản xuất giới hạn yêu cầu tiêu chí ở 1–4. Lời nhắc có hiệu lực hiện là `mts-task2-v12`; bộ đánh giá không đổi lời nhắc/hiệu chuẩn sản xuất. Dùng DEV để lặp cải tiến và thư mục đầu ra `--split holdout` riêng để đánh giá cuối cùng.

Đầu ra: `report.json`, `report.md`, `disagreements.csv`, `cache/`, `attempts/`. Task 2 dùng chung mã tính đồng thuận chính xác/±0.5/±1.0, độ lệch, MAE, RMSE và QWK của Task 1. QWK yêu cầu 10 cặp nửa band so sánh được và phương sai kỳ vọng khác 0. Lỗi vẫn hiển thị; tiêu chí hợp lệ trong kết quả một phần có thể góp vào chỉ số, còn điểm tổng yêu cầu đủ bốn dự đoán. Các lần thất bại/chi phí trước vẫn được giữ khi thử lại thành công. Kết quả trúng bộ nhớ đệm không thêm yêu cầu mới. Chi phí yêu cầu đang chạy bị gián đoạn là chưa biết, không tự tạo số liệu.

Danh tính tiếp tục bao gồm nội dung, nhãn, phần chia dữ liệu, nhà cung cấp/mô hình, điểm cuối đã băm, lời nhắc có hiệu lực, cấu hình chạy, nguồn gốc ô văn bản, hợp đồng và phần triển khai. Đường dẫn/nhãn hiển thị không ảnh hưởng danh tính. Bản ghi thất bại/hỏng/không nhất quán không được coi là kết quả trúng bộ nhớ đệm thành công.

Giữ đầu vào riêng tư và báo cáo ở nơi Git bỏ qua hoặc ngoài Git. Báo cáo chứa ID an toàn, giá trị băm, điểm và bộ đếm, không chứa văn bản nguồn hoặc lỗi thô của nhà cung cấp. Suy luận gửi đề bài/bài viết đến nhà cung cấp đã cấu hình. Không cần cơ sở dữ liệu sản xuất, phiên quản trị hoặc kết nối API. Xem [hướng dẫn Colab](../../docs/writing-benchmark-bank.md).
