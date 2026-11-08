# Danh mục mô-đun và bản đồ trách nhiệm

> Mục đích và phạm vi: Điểm bắt đầu để xác định miền nghiệp vụ chịu trách nhiệm và tài liệu tương ứng.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái triển khai đang chạy.

Chọn mô-đun theo **trạng thái và chính sách nó quản lý**, không theo URL gần giống. Bảng ánh xạ cả frontend/backend; bản đồ mã nguồn liệt kê mọi tuyến/model/trang ở revision được kiểm tra. Các service nhỏ được nhóm dưới miền nghiệp vụ liên quan để tránh hàng chục trang trùng lặp.

| Mô-đun | Hướng dẫn chuẩn | Phạm vi quản lý / tích hợp |
| --- | --- | --- |
| Danh tính, tài khoản, hồ sơ và tùy chọn | [danh tính](../modules/identity.md) | Xác thực cục bộ/OAuth, refresh/khôi phục/logout, hồ sơ/mục tiêu/tùy chọn |
| Test Builder, registry câu hỏi và quản trị nội dung | [soạn đề](../modules/authoring.md) | Bản nháp/xuất bản/kiểm duyệt, đồ thị nội dung, registry câu hỏi/đáp án, ảnh bìa |
| Reading và Listening: bộ máy câu hỏi khách quan | [Reading/Listening](../modules/reading-listening.md) | Đoạn đọc/highlight Reading, player/khoảng phát Listening, đánh giá đáp án khách quan |
| Attempt, Full Mock, bộ đếm thời gian và lịch sử | [attempt](../modules/attempts.md) | Autosave, thời hạn/tạm dừng, phạm vi focused, Full Mock, review/lịch sử |
| Writing: bài tác giả soạn, chấm thủ công và AI tham khảo | [Writing](../modules/writing.md) | Task1/Task2, điểm cuối người chấm, snapshot tham khảo, chú thích, ngân hàng benchmark |
| Speaking: ghi âm, xử lý, chấm điểm và khôi phục | [Speaking](../modules/speaking.md) | Đề/ghi âm/khôi phục, media, ASR/bằng chứng, điểm tham khảo/người chấm |
| Lớp học, nhân sự, bài giao, nội dung và sổ điểm | [lớp học](../modules/classrooms.md) | Thành viên/nhân sự, luồng tin/classwork, lịch/đối tượng/gia hạn, sổ điểm, lưu trữ/xóa |
| Phân tích, mục tiêu học tập và kế hoạch cải thiện | [phân tích](../modules/analytics.md) | Chỉ số cá nhân, bằng chứng/gợi ý/mục tiêu/kế hoạch của lớp học |
| Quản trị, kiểm duyệt và ngân hàng benchmark | [quản trị](../modules/administration.md) | Người dùng/danh bạ, kiểm duyệt, thao tác benchmark admin, ranh giới quan sát |
| Lưu trữ asset, chuyển dữ liệu, di chuyển và khôi phục | [asset/chuyển dữ liệu](../modules/assets-transfer.md) | Cục bộ/S3/R2, khoảng byte riêng tư, chuyển dữ liệu/import bản nháp, di chuyển/sao lưu/khôi phục |
| Nền tảng dùng chung: shell, bản địa hóa, thông báo và kiểm tra trạng thái | [nền tảng dùng chung](../modules/shared-platform.md) | Shell/i18n/theme, chuyển động trang chủ, thông báo, lỗi, sức khỏe hệ thống/thời gian xử lý |

## Quy tắc phân chia trách nhiệm dùng chung

Hiệu năng/mở rộng là chủ đề xuyên suốt: [khảo sát khả năng phục vụ](../performance/5000-user-capacity.md), [công cụ thử tải](../../benchmarks/load/README.md). Điều phối Writing thuộc Writing, ngân sách kết nối thuộc hạ tầng; thẩm quyền bài thi không chuyển sang lớp benchmark.

- Mọi thay đổi dữ liệu API/nghiệp vụ đi qua FastAPI. Bổ sung UI không tạo nguồn thẩm quyền mới.
- Bài giao lớp học gọi bộ máy attempt/session hiện có. Sổ điểm/phân tích học tập dùng lại bản ghi gốc đã chọn/điểm cuối người chấm, không tách nhánh chấm điểm.
- Factory provider lưu trữ dùng chung cho nội dung, ảnh bìa, giọng nói, tài nguyên lớp học và ảnh benchmark; miền nghiệp vụ vẫn quản lý metadata.
- Provider/worker AI không quản lý xác thực, điểm cuối câu hỏi khách quan hay bản ghi điểm cuối người chấm.
- Service thông báo ghi sự kiện theo người nhận do nghiệp vụ phát sinh; không cấp quyền cho liên kết đích.

## Tình trạng triển khai

Mọi mô-đun trong bảng đều có mã, tuyến và tệp test hiện hữu. AI/OAuth/cloud/nhắc hạn tùy cấu hình; không phải tất cả đang bật trong một lần triển khai. RAG/pgvector, thanh toán, gửi email/hiện diện thời gian thực chưa được xác nhận là khả năng hiện hành. Bộ chấm AI cũ dưới evaluation là ứng viên benchmark thử nghiệm/lịch sử, không phải runtime mặc định.

[Ma trận bao phủ](../DOCUMENTATION_COVERAGE.md) ghi Partial/Not verified, không báo 100%. [Hướng dẫn phát triển](feature-development-playbook.md) chỉ cách thay đổi, [bản đồ mã nguồn](source-map.md) giúp tra endpoint chính xác.


### Admin Speaking Benchmark Lab — Phase 1 addition

Owner: `api/v1/speaking_benchmark.py` → `services/speaking_benchmark*.py` → `models/speaking_benchmark.py`, typed client and `features/speaking-benchmark/`. Separate entrypoint: `scripts/speaking_benchmark_worker.py`; native boundary: existing local Community-1 tool. [Schema, architecture and operational contract](../testing/admin-speaking-benchmark.md). This dataset preparation module is separate from learner Speaking and Writing Benchmark.


### Admin Speaking Research — Phase 3

Owner: `api/v1/speaking_benchmark_research.py`, `services/speaking_benchmark_research*.py`, reference service/model, typed client and `features/speaking-benchmark/research/`. Separate CPU entrypoint `scripts/speaking_benchmark_research_worker.py`. [Operations and measurement protocol](../testing/admin-speaking-benchmark-research.md).
