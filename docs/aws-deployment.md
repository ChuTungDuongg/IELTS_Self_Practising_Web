# Các cấu hình triển khai có thể chuyển môi trường

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho nội dung này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác minh môi trường đang chạy.
> Mục đích: Các cấu hình triển khai có thể chuyển môi trường. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../deploy/aws/compose.yml).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](handbook/infrastructure.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


P4 cung cấp cấu hình và kiểm tra ngoại tuyến. Không tạo hạ tầng AWS/Modal, không build image, không triển khai hoặc di chuyển dữ liệu trên môi trường đang chạy. P2/P3 tiếp tục là nền tảng ứng dụng/lưu trữ.

| Cấu hình | PostgreSQL | Tài sản bền vững | Điểm vào / proxy | Chính sách migration |
| --- | --- | --- | --- | --- |
| Development Local | PostgreSQL Compose hiện có trên cổng host 5433 | `STORAGE_BACKEND=local`, `storage/` trên host | Các lệnh development Next/FastAPI hiện có trong README | Người vận hành chạy `uv run alembic upgrade head` trên đúng cơ sở dữ liệu Local |
| Modal demo | PostgreSQL 17 nhúng; Volume cơ sở dữ liệu dev/production gốc | Local `/storage`, mặc định `ielts-web-assets` gốc trừ khi ghi đè tường minh | `deploy/modal/app.py`, Next + FastAPI + Nginx trên URL HTTPS Modal hiện có | Giữ migration khi khởi động ở chế độ nhúng; một container Web và cơ chế bảo vệ cơ sở dữ liệu |
| Modal managed | PostgreSQL bên ngoài qua Secret riêng tư, bắt buộc TLS | S3 hoặc R2; không có Volume tài sản Local | Cùng điểm vào Modal, Secret chỉ backend và dấu topology được cố định | Tắt migration Web; người vận hành chạy `migrate_database` một lần trước khi cho phép ghi |
| AWS EC2/Docker | RDS hoặc PostgreSQL managed bên ngoài, TLS | Role instance S3 hoặc token R2 riêng tư | `deploy/aws/compose.yml`, Nginx TLS → Next/FastAPI | Container migration trong profile `tools` tường minh; Web không migration lúc khởi động |

Cấu hình Local giữ `docker-compose.yml`, `backend/.env` bị Git bỏ qua và frontend `.env.local`; không cần tài khoản cloud. Cấu hình auth/CORS và `STORAGE_ROOT` hiện có vẫn hợp lệ. Xem [README](../README.md) cho lệnh Local. Xem [hướng dẫn Modal](modal-web.md) cho lệnh demo/managed, tên Volume và cô lập môi trường. Với cloud, chỉ dữ liệu xử lý tạm nằm trong filesystem container. Đổi bucket/tiền tố không sao chép dữ liệu đang được tham chiếu.

## Cấu hình EC2/Docker

Mẫu chạy ba container ứng dụng có chính sách khởi động lại và kiểm tra sức khỏe. Chỉ Nginx mở cổng host 80/443. Cổng backend/frontend chỉ truy cập trên mạng Compose riêng. Không chạy cơ sở dữ liệu production trong các container này. Không mount Volume nội dung người dùng: Settings P3 yêu cầu `s3` hoặc `r2`. Backend chạy bằng người dùng không phải root, filesystem gốc chỉ đọc và vùng tạm `/tmp` có giới hạn; bộ nhớ đệm frontend vẫn tạm thời. Cấp tài nguyên host phù hợp giới hạn bộ nhớ/CPU đã khai báo và tải thực tế. Không tăng worker/replica trong bước thiết lập.

Trước vận hành, chuẩn bị riêng host EC2 Linux có Docker Compose, PostgreSQL managed, kho riêng tư, DNS và chứng chỉ TLS hợp lệ. Đây là điều kiện do người vận hành chuẩn bị, không phải tài nguyên repository tạo. Chỉ cho phép HTTPS/chuyển hướng HTTP và quản trị cần thiết vào host; chỉ cho security group của host ứng dụng truy cập cơ sở dữ liệu. Không công khai cổng 5432.

Từ thư mục gốc repository, tạo bản riêng tư từ các mẫu:

```sh
cp deploy/aws/compose.env.example deploy/aws/compose.env
cp deploy/aws/backend.env.example deploy/aws/backend.env
```

Build từ checkout của commit đã rà soát để thay đổi chưa commit không liên quan không đi vào image. Điền tệp bị Git bỏ qua từ cấu hình runtime/hệ thống quản lý secret an toàn. `compose.env` chứa định tuyến và đường dẫn tệp không bí mật. `backend.env` chỉ được đưa vào container backend và migration; frontend không nhận thông tin DB/cloud/AI. Giới hạn quyền tệp cho người vận hành. Quản trị viên Docker có thể xem môi trường container; vì vậy cũng phải giới hạn truy cập host/Docker.

Đặt `SITE_DOMAIN`, `DB_CA_FILE`, `TLS_DIRECTORY` và `BANDPILOT_IMAGE_TAG` riêng theo revision. Mount chuỗi chứng chỉ và khóa riêng lấy độc lập dưới tên `fullchain.pem`/`privkey.pem`; cho UID/GID 101 của Nginx đọc khóa mà không công khai (ví dụ nhóm do người vận hành quản lý và mode 0640). Cung cấp bộ CA cơ sở dữ liệu mà UID backend 10001 đọc được. Bind mount từ chối đường dẫn thiếu thay vì tạo thư mục rỗng. Việc lấy/gia hạn chứng chỉ nằm ngoài mẫu này. Reload/tạo lại proxy sau khi gia hạn an toàn; thử quy trình tại staging.

Mã hóa URL mật khẩu cơ sở dữ liệu và dùng URL như `postgresql+asyncpg://user:ENCODED_PASSWORD@host/database?ssl=verify-full`. Container đặt `PGSSLROOTCERT=/run/secrets/database-ca.pem` từ `DB_CA_FILE`. Dùng CA nhà cung cấp cơ sở dữ liệu managed và hostname đúng. RDS mô tả [TLS PostgreSQL và xác minh chứng chỉ](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html). Runtime nhận các chế độ bắt buộc TLS; ưu tiên xác minh hostname tại production. Cấu hình Alembic giữ nguyên thông tin xác thực đã mã hóa phần trăm.

Compose đặt HTTPS `FRONTEND_ORIGIN`, cookie secure và `IELTS_AUTO_MIGRATE=false`. Tạo `JWT_SECRET` riêng ít nhất 32 ký tự; giữ cấu hình JWT hiện có nếu cần duy trì session. Giữ tên cookie mặc định. Đặt thông tin Google OAuth hiện có và callback `https://YOUR_DOMAIN/api/v1/auth/oauth/google/callback` nếu bật OAuth. Thông tin xác thực endpoint AI được bảo vệ vẫn nằm trong `backend.env`; AI trong ví dụ bị tắt cho tới khi cấu hình tường minh. Nhiệm vụ này không sửa dịch vụ AI.

Yêu cầu trình duyệt dùng `/api/v1`; yêu cầu server Next dùng `http://backend:8000/api/v1`. Nginx giữ đường dẫn, auth/cookie, byte range và SSE không đệm, chuyển tiếp HTTPS và cho phép body 310 MiB để chứa ZIP giới hạn 300 MiB cùng phần overhead multipart. Điều chỉnh giới hạn proxy tương ứng nếu giới hạn tải lên ứng dụng đổi. API vẫn quyết định kích thước tải lên và quyền truy cập.

## Thông tin xác thực lưu trữ

Với S3, dùng `S3_BUCKET`, `S3_REGION` thực tế và `S3_KEY_PREFIX` tùy chọn. Ưu tiên role instance EC2 với [chính sách bucket/tiền tố mẫu](../deploy/aws/s3-iam-policy.example.json); thay bucket/tiền tố hư cấu. Chính sách chỉ cấp đọc/ghi/xóa đối tượng trong tiền tố đó. ListBucket cấp bucket cho phép kiểm tra HEAD âm phân biệt thiếu đối tượng và bị từ chối quyền; dùng bucket riêng tư chuyên dụng. Xem [quyền S3 HeadObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html). Không thêm phụ thuộc ACL, bucket công khai, Object Lock hoặc KMS.

SDK dùng chuỗi thông tin xác thực thông thường. Khi dùng role host, bảo đảm container backend truy cập được IMDSv2; mạng container có thể cần giới hạn hop phản hồi metadata 2. Áp dụng chính sách instance có chủ đích và thử ở staging; xem [cấu hình metadata EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-new-instances.html). Frontend/proxy không nhận thông tin lưu trữ tĩnh; role instance là hạ tầng toàn host nên cần giới hạn truy cập workload/metadata phù hợp.

Với R2, đặt `STORAGE_BACKEND=r2`, `S3_REGION=auto`, endpoint HTTPS tài khoản và `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` có phạm vi giới hạn trong secret runtime backend. Giữ bucket riêng tư. Dùng cơ sở dữ liệu và bucket/tiền tố riêng đã xác minh cho dev/staging/production. Không thao tác chuyển cấu hình nào tự di chuyển tài sản Local/Modal.

## Triển khai và migration có kiểm soát

Sau đây là lệnh dành cho người vận hành, được mô tả nhưng **không chạy trong P4**:

```sh
# Does not expand backend secret-file values into console output:
docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml config --no-env-resolution --quiet
docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml build backend frontend
# During a write-free maintenance window, after verified independent backups:
docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml --profile tools run --rm --no-deps migrate
docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml up -d backend frontend proxy
```

Chỉ một người vận hành migration tại một thời điểm, sau khi dừng mọi tác vụ ghi Web trước đó. Khi cần, dùng tệp secret riêng cho chủ sở hữu schema qua `BANDPILOT_BACKEND_ENV`; chuyển lại tệp role ứng dụng cho Web. Profile tools không tự khởi động và Web không gọi Alembic. Khởi động không reset/restore dữ liệu. Giữ image trước đó và kế hoạch hoàn tác đã thử; image cũ chỉ an toàn khi schema tương thích. Khôi phục cơ sở dữ liệu cloud và hoàn tác tài sản tuân theo [khôi phục P5](storage-backup-restore.md), không tự động hạ cấp.

`/api/v1/health` vẫn kiểm tra tiến trình còn sống; `/api/v1/ready` thăm dò cơ sở dữ liệu chỉ đọc có giới hạn và trả 503 tổng quát khi thất bại. Compose chờ sức khỏe trước khi khởi động frontend/proxy. Chính sách Docker restart xử lý tiến trình thoát; container vẫn chạy nhưng không khỏe không tự restart chỉ vì trạng thái health. Giám sát và điều tra lỗi phụ thuộc. Healthcheck không chứng minh quyền bucket hoặc xác minh mọi đối tượng. Kiểm tra đăng nhập/đăng xuất, OAuth, SSE, tải lên, tua phát và transport AI ở staging thật.

## Công việc vận hành còn lại

Image và Nginx ở đây chỉ được kiểm tra cấu hình tĩnh; chưa build Docker hoặc thử TLS đang chạy, AWS IAM/RDS, R2, độ bền Modal hay mạng cloud. P5 cung cấp [kiểm kê/sao chép/tiếp tục/đối soát](storage-migration.md) và [sao lưu portable/khôi phục cô lập](storage-backup-restore.md). Chạy từ môi trường vận hành bảo mật có phụ thuộc backend và công cụ client PostgreSQL tương ứng; image Web tối giản không cài pg_dump/pg_restore. Cung cấp cấu hình SOURCE_/DESTINATION_ và quyền role/token độc lập, không dùng thông tin frontend. Sao lưu cũ vẫn từ chối cloud; dùng quy trình portable tường minh. Diễn tập tính nhất quán khi ngừng ghi, lấy sao lưu độc lập và hoàn tác tại staging. Tách chuyển đổi thật khỏi triển khai ngoại tuyến.
