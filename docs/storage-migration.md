# Di chuyển và đối soát dữ liệu lưu trữ

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho nội dung này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác minh môi trường đang chạy.
> Mục đích: Di chuyển và đối soát dữ liệu lưu trữ. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../backend/app/storage/migration.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/assets-transfer.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


Đây là lệnh dành cho người vận hành, không phải tác vụ khởi động. Chạy từ checkout đã rà soát với Python 3.12+ và các phụ thuộc backend (`cd backend`, sau đó `uv run python ../scripts/migrate_asset_storage.py ...`). Không lệnh nào tạo bucket, đổi cấu hình ứng dụng, xóa nguồn hoặc ghi đè dữ liệu khác biệt. Kiểm thử đám mây dùng adapter S3 thật với client giả ngoại tuyến, không dùng bucket thật.

## Cấu hình độc lập

Công cụ không đọc `backend/.env`. Xuất `DATABASE_URL` tường minh cho danh mục tham chiếu nguồn. Chỉ nhận URL PostgreSQL; URL từ xa phải dùng `?ssl=require`, `verify-ca` hoặc ưu tiên `verify-full`. Cung cấp đường dẫn chứng chỉ qua `PGSSLROOTCERT` (và biến chứng chỉ client khi cần). Các tùy chọn truy vấn URL khác bị từ chối để tránh ghi đè đích.

Mỗi phía lưu trữ dùng tiền tố riêng; thay `SIDE` bằng `SOURCE` hoặc `DESTINATION`:

| Biến môi trường | Local | S3 | R2 |
| --- | --- | --- | --- |
| `SIDE_ENVIRONMENT` | Bắt buộc: `development`, `staging`, `production` hoặc `recovery` | Tương tự | Tương tự |
| `SIDE_STORAGE_ROOT` | Thư mục tuyệt đối, bền vững, bắt buộc | Không dùng | Không dùng |
| `SIDE_S3_BUCKET` | Không dùng | Bucket riêng tư đã tồn tại | Bucket riêng tư đã tồn tại |
| `SIDE_S3_REGION` | Không dùng | Region thực tế | `auto` |
| `SIDE_S3_ENDPOINT_URL` | Không dùng | Thường bỏ qua | Endpoint HTTPS tài khoản `.r2.cloudflarestorage.com` |
| `SIDE_S3_KEY_PREFIX` | Không dùng | Tiền tố tương đối an toàn hoặc gốc bucket được chọn tường minh | Tương tự |
| `SIDE_AWS_ACCESS_KEY_ID`, `SIDE_AWS_SECRET_ACCESS_KEY` | Không dùng | Cặp thông tin xác thực tường minh, tùy chọn | Cặp token có phạm vi giới hạn, bắt buộc |
| `SIDE_AWS_SESSION_TOKEN` | Không dùng | Thông tin xác thực tạm thời, tùy chọn | Nếu áp dụng |
| `SIDE_USE_AWS_CHAIN=true` | Không dùng | Phải chủ động bật khi dùng IAM/chuỗi SDK thông thường thay cho thông tin xác thực tường minh | Không dùng |

Các bí danh thử nghiệm `SIDE_S3_ACCESS_KEY_ID`, `SIDE_S3_SECRET_ACCESS_KEY` và `SIDE_S3_SESSION_TOKEN` vẫn được chấp nhận. Ưu tiên biến có tên AWS. Không xuất thông tin xác thực production cho thao tác development. Dùng role/token riêng và xác minh tổ hợp cơ sở dữ liệu/bucket/tiền tố. Bật chuỗi IAM có thể tìm thấy thông tin AWS sẵn trong môi trường, kể cả role EC2; xác minh danh tính đó bằng kênh riêng. Không đưa token, DSN hoặc báo cáo riêng tư vào Git hay lịch sử shell.

Báo cáo chạy thử cung cấp `target_id` đích ổn định, suy ra từ namespace chứ không từ thông tin xác thực. Đối chiếu thư mục gốc/bucket/tài khoản/tiền tố thật với cấu hình vận hành, rồi xác nhận ID đó tường minh trước khi ghi. Nhãn không chứng minh quyền sở hữu tài khoản. Lệnh đám mây dùng HeadBucket để từ chối bucket không tồn tại hoặc không truy cập được; namespace cố ý để trống vẫn cần xác nhận tường minh. Thư mục Local chồng lấn và tiền tố chồng lấn trong cùng bucket đám mây bị từ chối, kể cả bí danh endpoint AWS khu vực/toàn cầu.

## Các lệnh

Ví dụ cấu hình shell (mọi giá trị đều hư cấu; dùng secret cho giá trị thật):

```sh
export DATABASE_URL='postgresql+asyncpg://operator@127.0.0.1:5433/ielts'
export SOURCE_ENVIRONMENT=development SOURCE_STORAGE_ROOT=/srv/bandpilot/storage
export DESTINATION_ENVIRONMENT=staging DESTINATION_S3_BUCKET=fictional-staging-assets
export DESTINATION_S3_REGION=us-east-1 DESTINATION_S3_KEY_PREFIX=staging/media
export DESTINATION_USE_AWS_CHAIN=true
```

Từ `backend/`:

```sh
# Inventory: metadata only; no bucket listing by default.
uv run python ../scripts/migrate_asset_storage.py --source local --inventory-only --report /secure/inventory.json
# Default dry-run reads/hashes sources and checks existing destination bytes.
uv run python ../scripts/migrate_asset_storage.py --source local --destination s3 --workers 2 --report /secure/migration.json
# Only after reviewing the destination target_id and stopping ALL writers:
uv run python ../scripts/migrate_asset_storage.py --source local --destination s3 --workers 2 --copy --confirm-target REVIEWED_TARGET_ID --maintenance-window --allow-cross-environment --report /secure/migration.json
# Reconfigure SOURCE_* to the destination, keeping the source PostgreSQL inventory:
uv run python ../scripts/migrate_asset_storage.py --source s3 --reconcile --expected-report /secure/migration.json --report /secure/reconcile.json
# Optional, potentially expensive listing (paginated for S3/R2), never deletion:
uv run python ../scripts/migrate_asset_storage.py --source s3 --reconcile --list-orphans --listing-limit 100000 --report /secure/orphans.json
```

Local→S3/R2, S3/R2→Local, S3→R2, R2→S3, các namespace S3 riêng biệt và Local→Local đều dùng cùng một bộ máy. Báo cáo phải là tệp `.json` riêng tư nằm ngoài cả hai thư mục tài sản Local. Giữ báo cáo/checkpoint ngoài bản sao lưu và tài sản nguồn.

Mỗi kết quả ghi khóa, kích thước, SHA-256, backend nguồn/đích và trạng thái. `copied` và `identical` nghĩa là dữ liệu đã được xác minh, không chỉ được PutObject chấp nhận. `would_copy` là xem trước thành công, **không phải** di chuyển hoàn tất. Đối tượng thiếu, hỏng, không hợp lệ, không truy cập được hoặc xung đột khiến tiến trình thoát mã 1. Lỗi đối số CLI dùng mã thoát argparse 2. Không đối tượng bắt buộc chưa xác minh nào được phép dẫn đến `complete=true`. Lần chạy bị gián đoạn giữ checkpoint nguyên tử; chạy lại cùng lệnh để tiếp tục. Công cụ luôn băm lại đối tượng đã có thay vì tin checkpoint. Ghi thất bại/xác nhận không rõ có thể để lại đối tượng ứng viên ở đích; dữ liệu giống nhau được dùng lại an toàn, dữ liệu khác biệt chặn tiến trình và cần điều tra.

Đối soát kiểm tra kích thước kỳ vọng trong cơ sở dữ liệu và SHA-256 Speaking nếu đã lưu. `--expected-report` bổ sung mã băm từ lần di chuyển trước cho mọi tham chiếu hiện tại. Khi không có mã băm đã biết, công cụ chỉ đo mốc đối chiếu, không chứng minh nội dung gốc. Nó báo khóa không hợp lệ, đối tượng thiếu và lỗi toàn vẹn. Khóa dọn dẹp và đối tượng có thể mồ côi chỉ là chẩn đoán; không sửa bản ghi lịch sử. Danh sách bị giới hạn bởi `--listing-limit`; `listing_truncated=true` nghĩa là danh mục mồ côi chưa đầy đủ dù mọi đối tượng có tham chiếu đã vượt xác minh.

## Chuyển đổi và hoàn tác

Triển khai này yêu cầu cửa sổ bảo trì cho **lần sao chép cuối đã xác minh**. `--maintenance-window` là xác nhận tường minh của người vận hành, không phải khóa toàn ứng dụng. Dừng tác vụ ghi Web và mọi tác vụ ghi độc lập/nền: thu âm Speaking, worker chuẩn hóa/phiên âm/AI, tải lên Classroom, thay ảnh bìa, nhập/xuất, benchmark và dọn dẹp. Chờ yêu cầu/tác vụ đang chạy hoàn tất trước khi tiếp tục. Ngăn lịch chạy và instance khác tự khởi động lại. Không công cụ nào chứng minh được rằng một tác vụ ghi không hợp tác ở nơi khác đã dừng.

1. Tạo và xác minh bản sao lưu PostgreSQL + tài sản; lưu độc lập.
2. Xem trước di chuyển; điều tra mọi bản ghi thiếu/xung đột/không hợp lệ.
3. Đóng băng và chờ mọi tác vụ ghi kết thúc, rồi sao chép và đối soát cuối.
4. Yêu cầu xác minh đầy đủ danh mục tham chiếu hiện tại và không còn lỗi chưa giải quyết. Giữ manifest/báo cáo cuối và kho nguồn.
5. Đổi cấu hình lưu trữ chỉ ở backend một cách tường minh; không đổi khóa.
6. Khởi động lại với cấu hình mới và xác minh sức khỏe cùng quyền truy cập ảnh bìa, sơ đồ, tua Listening, phát Speaking, Classroom và xem lại lịch sử.
7. Chỉ cho phép ghi lại sau khi người vận hành nghiệm thu. Giữ nguồn và bản sao lưu cơ sở dữ liệu trong thời hạn lưu giữ đã thống nhất.

Trước khi phát sinh ghi mới, có thể hoàn tác bằng cấu hình/snapshot cơ sở dữ liệu tương ứng và nguồn đã giữ. Sau ghi mới, chỉ hoàn tác cấu hình là **không an toàn**: đóng băng lại rồi đối soát/sao chép mọi đối tượng mới có tham chiếu cùng trạng thái cơ sở dữ liệu tương ứng, hoặc khôi phục theo phê duyệt tường minh chấp nhận mất dữ liệu. Không tự động xóa đối tượng mới, hạ cấp schema hoặc ghi đè dữ liệu xung đột khi hoàn tác. Quyền nhà cung cấp thật, hành vi tệp lớn và hoàn tác vẫn phải được diễn tập trong staging riêng.
