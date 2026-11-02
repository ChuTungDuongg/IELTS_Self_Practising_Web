# Chuyển đổi hệ thống lưu trữ: đã hoàn tất triển khai ngoại tuyến

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Chuyển đổi hệ thống lưu trữ: đã hoàn tất triển khai ngoại tuyến. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../backend/app/storage/operations.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](storage-architecture.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


Lưu trữ tài sản Local vẫn mặc định. Có thể chọn S3/R2 sau các cổng ngoại tuyến P3 bên dưới. Đổi backend không di chuyển tệp hiện có.

## Theo dõi staging Modal — 2026-10-28

Đã xác minh triển khai development thật tắt AI với PostgreSQL 17 nhúng và LocalAssetStorage trên các Volume DB/tài sản/snapshot mới được chọn tường minh. Giữ tài nguyên production hiện có. Chỉ tải snapshot tổng hợp; DB Local thường chỉ được xem chỉ đọc, không xuất. Xác nhận revision Alembic `20261028_0043` trong container staging đang chạy.

Kiểm HTTPS đang chạy bao gồm health/readiness, catalog công khai có xác thực, trả ảnh/âm thanh/ảnh bìa, range, lỗi quyền sở hữu, phiên bản published bất biến, clone, Transfer ZIP v1/v2, tài nguyên Classroom, Speaking riêng tư chia đoạn. FFmpeg thật tạo WAV chuẩn hóa một giây, dọn vùng tạm. Kiểm kê/chạy thử/đối soát P5 xác minh 19 đối tượng có tham chiếu; xác minh sao lưu DB/media trong bảo trì trên Modal và sau tải xuống. Bản ghi DB, âm thanh riêng thô/chuẩn hóa và sao lưu tồn tại sau thay container Web. Điều này không chứng minh độ bền tức thời của upload chưa commit: Volume demo Modal vẫn lưu bất đồng bộ.

App thử nghiệm đã dừng, xác nhận không tác vụ/container còn chạy. Giữ Volume staging bền vững và Secret riêng để khôi phục. Chưa xác minh kết nối S3/R2 thật, suy luận AI hoặc chuyển production. Báo cáo vận hành chi tiết/bằng chứng tổng hợp nằm ngoài Git tại `.test-tmp/modal-live/`; không commit thông tin tài khoản, dump hoặc ghi âm.

Công việc CI tiếp giữ service PostgreSQL cô lập, cấp DB recovery P5 dùng tạm riêng. Lỗi CI thật phát hiện mock Builder cũ, lệch định dạng, ánh xạ lỗi Python tar và truy vấn ảnh bìa catalog thừa. Hồi quy tập trung nay bao phủ sửa đó. Healthcheck PostgreSQL dùng TCP; khóa Volume cũ thống nhất giữa chế độ triển khai. Trạng thái GitHub Actions cuối được ghi trong báo cáo vận hành Local sau push sửa.

## P5 HOÀN TẤT — Xác minh di chuyển và khôi phục ngoại tuyến

Commit khởi đầu: `eeecfc6e39d604de2db234653be5c54da3c19623` (P4). Cổng trước: P2 `71272ea721a9324446c48e0d31d98ae571d71afa`, P3 `a7ec5d0cf3f7a9599a40e9427ae793201e3be752`. Mở rộng nguyên mẫu kiểm kê/sao chép chưa tracked hiện có, không thay bằng bộ máy lưu trữ thứ hai.

Di chuyển hỗ trợ Local/S3/R2 hai chiều, kể cả S3↔R2 và đổi vị trí Local có kiểm soát. Cấu hình độc lập tường minh, nhãn môi trường, định danh namespace chuẩn, từ chối chồng lấn, xác nhận đích và xác nhận bảo trì bảo vệ thao tác ghi. Mặc định chạy thử. Sao chép dùng luồng giới hạn và 1–8 worker, kiểm siêu dữ liệu nguồn/kích thước/SHA-256 đích, không ghi đè xung đột, tiếp tục bằng xác minh lại dữ liệu đã có. Checkpoint JSON riêng tư nguyên tử là bằng chứng, không phải lý do bỏ xác minh.

Danh mục bao phủ cả sáu nguồn tham chiếu bền vững, mọi phiên bản/take lịch sử; khóa cleanup-outbox vẫn là chẩn đoán riêng. Đối soát phát hiện đối tượng sai/thiếu/hỏng, so mã băm trước nếu được cấp, tùy chọn liệt kê mồ côi phân trang giới hạn không xóa. Tệp FFmpeg/ZIP tạm, cache mô hình, thư mục DB không thuộc sao chép tài sản thường. Truy cập Local trực tiếp còn lại chỉ phục vụ an toàn adapter/liệt kê/đầu ra Local, sao lưu Local cũ, vùng tạm và PostgreSQL/Volume triển khai; không thấy hồi quy lưu trữ nghiệp vụ.

Sao lưu `--portable` ghi gói v2 có phiên bản gồm dump custom PostgreSQL thật, dữ liệu đối tượng có tham chiếu và manifest SHA-256/kích thước/MIME đã xác minh. Kiểm kê/pg_dump dùng chung snapshot DB chỉ đọc đã xuất; vẫn phải dừng mọi tác vụ ghi độc lập vì PostgreSQL/kho đối tượng không cùng giao dịch. Lỗi để lại gói riêng tư được đánh dấu chưa hoàn tất. Giữ tương thích sao lưu/khôi phục Local v1 cũ.

Khôi phục mặc định xác minh/tiền kiểm. Phục hồi đối tượng không phá dữ liệu, xung đột chặn ghi, đối tượng khớp hỗ trợ tiếp tục. Khôi phục DB là lệnh riêng tường minh vào DB recovery khác, rỗng, không hoạt động, với ID đích/DB đã rà soát và hash manifest cố định. Không dùng --clean/reset. Tham chiếu khôi phục thật/dữ liệu đích phải đối soát trước khi báo hoàn tất ứng dụng. Xác minh archive theo luồng, từ chối thành viên không an toàn và giới hạn metadata PAX/GNU cùng lượt đọc đối tượng thường.

Xác minh tập trung cuối: **75 kiểm thử P5/sao lưu cũ**, gồm hai ca snapshot/dump/restore PostgreSQL thật trên container PostgreSQL 17 dùng tạm với tmpfs; **31 hồi quy storage/nghiệp vụ chọn lọc** và **4 hồi quy tích hợp Classroom/clone** đạt. Tổng: **110 đạt, không lỗi, không bỏ qua**. Có hai cảnh báo phụ thuộc ngừng hỗ trợ sẵn có ở kiểm media được bảo vệ. Ruff theo phạm vi, lockfile ngoại tuyến, xác minh Compose và kiểm diff đạt. Chỉ migration/restore service test loopback riêng; không sửa DB development thường/production. Xóa service dùng tạm sau xác minh. Không liên hệ, triển khai hoặc cấp dịch vụ cloud.

Hướng dẫn vận hành: [kiến trúc](storage-architecture.md), [di chuyển/chuyển đổi](storage-migration.md), [sao lưu/khôi phục](storage-backup-restore.md), [Modal](modal-web.md), [AWS](aws-deployment.md). Giữ topology, Secrets, mặc định replica P4. Môi trường vận hành cần công cụ client PostgreSQL tương thích; image Web AWS tối giản không có. Sao lưu demo Modal phải giữ cơ chế một chủ sở hữu DB, ngừng ghi và giới hạn độ bền Volume. Báo cáo/manifest không có thông tin xác thực; bản sao lưu có dữ liệu học tập riêng tư phải bảo mật/sao chép độc lập.

Mọi cổng triển khai đều ngoại tuyến. Hành vi IAM/R2/TLS/Modal thật, thông lượng, độ bền, lấy sao lưu độc lập, phục hồi thảm họa/chuyển production vẫn thuộc staging/người vận hành riêng. Cờ bảo trì xác nhận người vận hành thật sự ngừng ghi, không phải khóa phân tán. Chỉ hoàn tác cấu hình sau ghi mới không an toàn nếu thiếu đối soát DB tương ứng/đối tượng mới được tham chiếu. Không di chuyển tài sản thật hoặc restore production.

## P3 HOÀN TẤT — Xác minh cấu hình Local/S3/R2 ngoại tuyến

Commit Local khởi đầu: `71272ea721a9324446c48e0d31d98ae571d71afa`. Xác minh tập trung cuối: 98 kiểm thử cấu hình/SDK/hợp đồng/sao lưu ngoại tuyến đạt, thêm 99 kiểm thử nghiệp vụ/tích hợp chọn lọc đạt trên PostgreSQL dùng tạm. Bỏ qua một kiểm symlink hiện có vì host Windows không tạo được symlink; CI Linux bao phủ bảo vệ đó. Ruff theo phạm vi, `uv lock --check --offline` và `git diff --check` đạt. Nay chọn được S3/R2; Local vẫn mặc định. Không đổi môi trường ứng dụng, gọi cloud thật hoặc chuyển tài sản.

### Chọn kho lưu trữ

Đặt biến môi trường chỉ backend trong `backend/.env` hoặc secret runtime:

| Cấu hình | Local | AWS S3 | Cloudflare R2 |
| --- | --- | --- | --- |
| `STORAGE_BACKEND` | `local` (mặc định) | `s3` | `r2` |
| `STORAGE_ROOT` | thư mục Local bền vững | không dùng cho media bền vững | không dùng cho media bền vững |
| `S3_BUCKET` | không dùng | tên bucket riêng tư bắt buộc | tên bucket riêng tư bắt buộc |
| `S3_REGION` | không dùng | region AWS thực tế | `auto` |
| `S3_ENDPOINT_URL` | không dùng | thường bỏ qua | `https://<account-id>.r2.cloudflarestorage.com` |
| `S3_KEY_PREFIX` | không dùng | namespace tương đối an toàn tùy chọn | namespace tương đối an toàn tùy chọn |
| thông tin xác thực | không có | role IAM hoặc chuỗi AWS SDK chuẩn; biến AWS tường minh tùy chọn | cặp access/secret token giới hạn phạm vi bắt buộc trong `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |

Hỗ trợ `AWS_SESSION_TOKEN` cho thông tin xác thực tạm. Thông tin chỉ ở server, được che trong Settings/lỗi, không nhúng cấu hình frontend hoặc bản ghi asset. Dùng bucket/tiền tố riêng cho môi trường; đổi tiền tố cũng đổi namespace vật lý. Không dự phòng sang Local khi cấu hình, quyền hoặc nhà cung cấp lỗi.

Khởi động xác minh cấu hình, khởi tạo client được chọn trong worker thread. Không thăm dò/tạo bucket; thông tin/quyền sai được báo khi SDK phân giải xác thực hoặc thao tác đối tượng có quyền đầu chạy. Local tạo `audio`/`images`; cloud không chạm `STORAGE_ROOT`. Client SDK tái sử dụng theo cấu hình. I/O đối tượng đồng bộ chạy worker thread; ghi bị hủy được chờ trước bù trừ rollback, mở luồng bị hủy đóng body khi hoàn tất. Adapter dùng Put/Get/Head/Delete riêng tư, tạo có điều kiện, Content-Type/Content-Length, SigV4, timeout kết nối 5s/đọc 60s, tối đa bốn lượt SDK tổng. Upload spool chunk giới hạn ra đĩa tạm thay vì giữ cả ghi âm trong RAM. Không yêu cầu giả định ACL, KMS hoặc ETag-as-checksum. Header checksum SDK tùy chọn bị giới hạn cho thao tác bắt buộc để tương thích S3. ZIP tiếp tục xác minh SHA-256 cấp ứng dụng.

Tại cổng P3, CLI sao lưu/khôi phục cũ chỉ hỗ trợ Local. Chọn cloud làm chúng thất bại trước dump, restore hoặc thay tệp. Không lách bằng giả rằng backend đang dùng là Local. Nay P5 cung cấp sao lưu PostgreSQL trong bảo trì, danh mục tham chiếu, dữ liệu sao chép, kiểm SHA-256/kích thước, phát hiện thiếu đối tượng, restore/hoàn tác theo nhà cung cấp.

Cổng ngoại tuyến bao phủ hợp đồng Local/S3, lời gọi boto3 Stubber, cấu hình R2, chọn factory/khởi động, range có bảo vệ, chuẩn hóa/ASR Speaking, quyền/tải Classroom, clone/cleanup, khứ hồi ZIP v1/v2 xuyên nhà cung cấp và bù trừ lỗi trên PostgreSQL dùng tạm. Staging thật vẫn phải xác minh quyền IAM/R2, endpoint/TLS, thử lại provider, upload lớn/tua, độ trễ và sao lưu có thể restore độc lập trước chuyển production. Kiểm thử ngoại tuyến không chứng minh bucket đang chạy cụ thể đã sẵn sàng.

Tham khảo: [tương thích S3 của R2](https://developers.cloudflare.com/r2/api/s3/api/), [cấu hình boto3](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html).

## P2 HOÀN TẤT — Xác minh tích hợp nghiệp vụ lưu trữ ngoại tuyến

Lưu chunk/WAV Speaking chuẩn hóa, phát có bảo vệ, tài nguyên Classroom, ảnh bìa, asset bài thi, clone, cleanup và đọc/ghi Transfer ZIP dùng thao tác storage. Chuẩn hóa lưu khóa opaque `speaking-derived/`; FFmpeg/phân tích nhận tệp tạm giới hạn. Xác minh cache phân biệt đối tượng thiếu/hỏng với provider lỗi. Worker thread dùng tệp kết thúc trước xóa tệp tạm, kể cả khi hủy; ASR Local vì vậy có thể vượt timeout yêu cầu trong lúc chờ thread đang chạy kết thúc. Phát truyền chunk có quyền với single-range.

Lần chạy PostgreSQL ngoại tuyến dùng TransferService thật với Local và adapter tương thích S3/client giả, đủ bốn tổ hợp nguồn/đích cho ZIP v1/v2. Kiểm byte media/ảnh bìa, SHA-256/kích thước metadata, ánh xạ UUID, phiên bản publish, loại media riêng không liên quan, import lặp, lỗi storage, lỗi flush DB, dọn bù trừ. Kiểm tập trung hiện có còn bao phủ archive sai, bìa thiếu/hỏng, rollback clone, cấp quyền, recovery và đồng thời Speaking. Hai kiểm âm thanh chuẩn hóa session độc lập kiểm chèn cache đồng thời/mất xác nhận commit. Không liên hệ S3/R2 thật.

Cổng tích hợp P2 tập trung đạt ngoại tuyến, gồm từ chối đối tượng từ xa thiếu/hỏng, dùng Classroom/worker phiên âm xuyên suốt với client S3 giả và dọn clone dựa S3. Factory storage ứng dụng xác minh cấu hình cloud trước chọn. Các kiểm này không xác lập cloud production sẵn sàng hoặc xác minh AWS/R2 thật.

### Chạy kiểm thử PostgreSQL an toàn

Cấp PostgreSQL **riêng, dùng tạm**, chỉ loopback, tên chứa token `_test`. Đặt `TEST_DATABASE_URL` là URL asyncpg; phải khác host/port/database với `DATABASE_URL` ứng dụng. Fixture mới xác minh trước kết nối, không reset/migration DB. Với CI, `P2_TEST_DATABASE_URL` chọn service riêng không đổi `TEST_DATABASE_URL` của kiểm đồng thời hiện có.

Chỉ migration DB test được cấp tường minh, bằng lệnh riêng tạm đặt `DATABASE_URL` thành URL test đó; trả giá trị thường trước chạy kiểm mới. Ví dụ PowerShell sau khởi động PostgreSQL dùng tạm trên cổng loopback đã xác minh:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://p2tester:fictional@127.0.0.1:PORT/ielts_p2_test'
# In a separate process, set DATABASE_URL to that same disposable test URL and run:
uv run alembic upgrade head
# With DATABASE_URL restored to the ordinary app configuration:
uv run pytest tests/test_transfer_cross_storage.py tests/test_speaking_normalized_storage.py -q
```

Không dùng thiết lập này trên DB ứng dụng hiện có. CI cấp service PostgreSQL thứ hai, migration riêng. Kiểm Local đã hoàn tất dùng container ngắn hạn/Volume không tên, xóa container sau đó. Thông tin DB test bên trên là hư cấu.

### Kiểm toán filesystem

Chủ ý giữ đường dẫn chỉ Local: đầu vào/đầu ra FFmpeg và vùng tạm WAV chuẩn hóa, xác minh/nhập/xuất ZIP tạm, cache mô hình, adapter Local và fixture benchmark Local chọn tường minh. Tạo thư mục lúc khởi động nay chỉ Local. Công cụ sao lưu/khôi phục Local từ chối cloud tường minh cho tới P5 có thao tác hiểu cloud. Service nghiệp vụ được kiểm tra không phân giải asset bền vững thành đường dẫn Local. Độ bền Modal Volume vẫn chưa giải quyết.

## P4 HOÀN TẤT — Xác minh cấu hình triển khai di động ngoại tuyến

Commit Local khởi đầu: `a7ec5d0cf3f7a9599a40e9427ae793201e3be752`. Lần tập trung cuối: 122 đạt, bỏ qua một symlink cũ trên host Windows, hai cảnh báo phụ thuộc ngừng hỗ trợ. Xác minh cấu hình Compose, Ruff theo phạm vi, lockfile ngoại tuyến, diff đạt. Kiểm giả Modal/tiến trình/thăm dò mạng, tái dùng hợp đồng storage P3 ngoại tuyến. Không build image, migration DB thật hoặc gọi cloud. Tệp P5 vẫn chưa commit, ngoài giai đoạn này.

Modal demo giữ tên Volume gốc mặc định, PostgreSQL nhúng, một Web container. Topology managed dùng DB TLS bên ngoài/adapter S3/R2 chọn, không phụ thuộc Volume Local bền vững. Dấu topology được cố định; Secret backend xác minh runtime. Có Volume/Secret dev riêng và tùy chọn cô lập nghiêm mà không đổi tên/sao chép dữ liệu. Secret cloud cần nhãn dev/production khớp. Cảnh báo rõ khi demo cũ dùng chung Volume.

Độ bền tài sản Local vẫn là giới hạn demo: commit Volume nền và HTTP/DB thành công không xác nhận bền vững cho từng upload. Chỉ reload khi khởi động, commit tường minh sau dừng tiến trình, báo lỗi commit. Không thêm commit từng chunk hoặc hệ đồng bộ phân tán. Runtime có thể ghi chứng chỉ CA DB công khai tạm từ Secret, xóa khi dừng. Web external không khởi động/khởi tạo/seed PostgreSQL nhúng; migration là hàm vận hành tường minh.

Mẫu EC2/Docker thêm Nginx HTTPS, backend/frontend riêng, readiness/healthcheck, tiến trình ứng dụng không root, secret-file, mount CA RDS, role S3/token R2, profile migration riêng. Chỉ công khai cổng 80/443. Bốn profile/lệnh nằm trong [hướng dẫn triển khai](aws-deployment.md). Giữ auth, API proxy, SSE, media bảo vệ và transport AI. Không triển khai thật, migration DB, chuyển asset hoặc gọi cloud. Chưa xác minh build/TLS/mạng cloud đang chạy. Kiểm kê/di chuyển và sao lưu/khôi phục P5 tách riêng.

## Nguyên mẫu kiểm kê/sao chép trước đây (được P5 thay thế)

Nguyên mẫu `scripts/migrate_asset_storage.py` chưa commit kiểm kê tham chiếu trong `assets`, `test_covers`, `classroom_resources`, `speaking_audio_chunks`, `speaking_normalized_audio`, `writing_benchmark_samples`. Không chép tệp không tham chiếu hoặc tác vụ cleanup chờ. Đọc DB bằng giao dịch repeatable-read chỉ đọc; không phải snapshot nguyên tử kho đối tượng. Ngừng upload/xóa/xử lý media nền khi kiểm kê/sao chép, thực hiện lượt cuối đã xác minh trước chuyển đổi.

Người vận hành phải cấp `DATABASE_URL`, cấu hình nguồn/đích trong môi trường tường minh. Mỗi phía dùng `SOURCE_` hoặc `DESTINATION_`: Local dùng `STORAGE_ROOT` tuyệt đối; S3/R2 dùng `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL` tùy chọn, `S3_KEY_PREFIX`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_SESSION_TOKEN`. R2 bắt buộc endpoint HTTPS; S3 có thể dùng chuỗi provider xác thực AWS SDK. Giữ giá trị trong runtime an toàn, không commit thông tin xác thực. Công cụ không đổi Settings ứng dụng, xóa nguồn hoặc ghi đè xung đột. Kiểm kích thước/SHA-256 thay ETag. Mặc định chạy thử; ghi cần `--copy`, `--workers` giới hạn 1–8. Thoát khác không hoặc bất kỳ đối tượng thiếu/xung đột/lỗi/chưa xác minh đều chặn chuyển đổi.

Tiện ích không phải sao lưu đầy đủ: tạo sao lưu logic PostgreSQL riêng và xác minh mọi đối tượng có tham chiếu có bản sao restore độc lập được. Giữ storage/snapshot DB gốc tới khi thử restore/hoàn tác. Tiếp tục an toàn cho đối tượng sao chép xong khớp, nhưng đích xung đột/chưa chép xong cần điều tra, không tự ghi đè. Không chạy production trước khi rà soát toàn tích hợp/quy trình vận hành.
