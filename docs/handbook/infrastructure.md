# Hạ tầng và vận hành

> Mục đích và phạm vi: Các chế độ triển khai, nơi quản lý cấu hình và thao tác vận hành thực tế.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái triển khai đang chạy.

## Cục bộ: chạy gì và ở đâu?

[package.json](../../package.json) điều phối Next.js và FastAPI; [manifest frontend](../../frontend/package.json) định nghĩa script, lockfile khóa phụ thuộc. Backend dùng Python >=3.12, uv và [uv.lock](../../backend/uv.lock). PostgreSQL 17 trong Docker dùng cổng host 5433, frontend 3000, API 8000. Tệp nhị phân cục bộ nằm ở thư mục gốc storage đã cấu hình, không commit vào Git.

Các lệnh dưới đây là hướng dẫn cho người vận hành, **không được chạy trong lần kiểm toán tài liệu này**:

```powershell
# Từ root; chỉ sau khi đã cấu hình môi trường local riêng
npm install
docker compose up -d postgres
uv --directory backend sync --locked
uv --directory backend run alembic upgrade head
npm run dev
```

Xác nhận DATABASE_URL trước migration. `.env` backend và biến môi trường frontend có phạm vi khác nhau: `NEXT_PUBLIC_API_BASE_URL` công khai, `API_INTERNAL_BASE_URL` dùng phía server, `DATABASE_URL` và khóa provider chỉ dùng ở backend. Không chép toàn bộ môi trường backend vào tiến trình Next.

## Modal demo

Nguồn: [app.py](../../deploy/modal/app.py), [web_runtime.py](../../deploy/modal/web_runtime.py), [nginx.conf](../../deploy/modal/nginx.conf). Hướng dẫn vận hành chuẩn: [triển khai Modal](../modal-web.md). Trong cây làm việc tại lần kiểm toán, hướng dẫn này có thay đổi chương trình khởi chạy chưa commit; lần kiểm toán giữ nguyên và không dùng chương trình mới làm bằng chứng cho revision mã nguồn.

Web có 2 CPU/4096 MiB, 1 container, tối đa 8 lượt đầu vào. Runtime lấy khóa bảo vệ trước khi mở PostgreSQL 17 nhúng; Volume cơ sở dữ liệu và Volume asset có vai trò khác nhau. Chỉ tự migration/seed theo chế độ/cấu hình đã được kiểm tra hợp lệ. Khởi động đợi API readiness và Next; khi tắt, dừng ứng dụng/DB trước khi commit Volume. Nếu tiến trình/commit lỗi, cần xử lý vận hành, không bỏ khóa bảo vệ để ép triển khai.

```powershell
# Operator: dùng đúng Secret/Volumes và environment đã xác minh
modal deploy deploy/modal/app.py --strategy recreate
```

Recreate phù hợp demo chỉ có một bên sở hữu dữ liệu, tránh PostgreSQL cũ/mới cùng sở hữu thư mục. Không dùng nhiều replica để chữa độ trễ. Nginx hiện tắt buffering cho frontend/API; không thêm cache dùng chung cho xác thực, media, analytics hay SSE.

## Chế độ cloud của Modal và GPU

Chế độ cloud dùng PostgreSQL bên ngoài và S3/R2; marker triển khai phải khớp Settings trong Secret, không mount asset/cơ sở dữ liệu cục bộ bền vững như demo. Migration chạy riêng qua hàm dành cho người vận hành:

```powershell
modal run deploy/modal/app.py::migrate_database
```

Phải kiểm tra đích trước khi chạy lệnh. Web không tự seed cơ sở dữ liệu ngoài. Cấu hình provider dùng `STORAGE_BACKEND`, `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_KEY_PREFIX`; tên biến thông tin xác thực nằm tại [Settings](../../backend/app/core/config.py). AWS có chuỗi cấp thông tin xác thực/IAM; R2 cần endpoint và thông tin xác thực tài khoản đúng. Không chuyển dự phòng sang cục bộ khi cloud lỗi.

Writing LLM, Speaking ASR, DePlot có tệp triển khai và GPU/cache riêng; bật AI ở Web không chứng minh model đã sẵn sàng. [Kiến trúc AI](ai-architecture.md) giải thích trạng thái lạnh/ấm và chi phí theo cấu hình.

## Cách ly staging và chi phí

Mỗi staging cần tên ứng dụng, Volume DB, Volume asset, Secret và khóa bảo vệ tách production; cơ sở dữ liệu rỗng/giả lập. Đọc [bằng chứng P2](../modal-web-performance.md) trước khi đo lại: từng có sự cố dùng chung khóa bảo vệ và dọn dẹp chậm 5h34m. Lập danh sách tài nguyên do test sở hữu trước khi tạo; ghi ID ứng dụng, người chịu trách nhiệm dừng và thời điểm kết thúc. Dừng đúng ứng dụng test sau kiểm chứng, giữ tài nguyên bền vững nếu còn cần bằng chứng. Không dừng ứng dụng khác, không reset Volume.

`min_containers=1` giữ Web ấm và phát sinh chi phí khi nhàn rỗi; GPU giảm số container tùy cấu hình. Không suy hóa đơn từ mẫu CPU vài giây. Benchmark production cần quyền riêng, không ngầm dùng production vì thiếu URL staging.

## AWS EC2 / Docker

[Compose](../../deploy/aws/compose.yml) có backend/frontend/proxy và lệnh migrate trong profile tools. Template có Nginx HTTPS, CA TLS cho DB ngoài, S3/R2 riêng tư, cấu hình không chạy root/chỉ đọc và giới hạn tài nguyên. Compose này không có dịch vụ cơ sở dữ liệu production ẩn.

```powershell
# Operator runbook; yêu cầu cert, backend.env và database đích đã kiểm tra
 docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml config --no-env-resolution --quiet
 docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml --profile tools run --rm --no-deps migrate
```

Lệnh build/khởi động, ví dụ IAM và ma trận cấu hình nằm tại [hướng dẫn AWS](../aws-deployment.md); không sao chép ở đây. Migration trước triển khai phải xét tương thích ngược; quay lui image không tự quay lui schema hay byte object. Giữ bản sao lưu độc lập và đích khôi phục cách ly. Xem [sao lưu](../storage-backup-restore.md), [di chuyển storage](../storage-migration.md).

## Những gì lần kiểm toán này chưa xác minh

Bổ sung 2026-11-02: [báo cáo khả năng phục vụ](../performance/5000-user-capacity.md) ghi các test cục bộ có giới hạn trong môi trường cách ly, cấu hình ngân sách kết nối DB và cách triển khai/quay lui bộ xử lý Writing. `python -m app.workers.writing` có thể tách thực thi inference khỏi HTTP; cấu hình production Compose/Modal hiện có không thay đổi. Các test đó không chứng nhận năng lực replica cloud.

Không truy vấn tài nguyên cloud, không triển khai, không kiểm tra hạn TLS/chứng chỉ, IAM thực tế, head production hay diễn tập khôi phục thảm họa. Test cấu hình chứng minh điều kiện từ chối/chấp nhận trong mã, không chứng minh độ sẵn sàng cloud. Cục bộ, Modal demo, Modal dùng DB ngoài và EC2 cần danh sách nghiệm thu riêng; không xem chúng như một cách triển khai đồng nhất.
