# Sao lưu có thể chuyển đổi nhà cung cấp và khôi phục cô lập

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho nội dung này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác minh môi trường đang chạy.
> Mục đích: Sao lưu có thể chuyển đổi nhà cung cấp và khôi phục cô lập. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../backend/app/storage/recovery.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](handbook/infrastructure.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


Định dạng Local v1 gốc của `scripts/backup.py` / `scripts/restore.py` được giữ lại. Lệnh cloud kiểu cũ vẫn thất bại trước khi thay đổi dữ liệu. Thêm `--portable` để dùng quy trình v2 mới, độc lập nhà cung cấp và có thể thực thi. Quy trình này khác với schema v1/v2 của Test Transfer ZIP; schema ZIP không đổi.

Dùng checkout đã rà soát, phụ thuộc Python backend và công cụ client PostgreSQL tương thích máy chủ nguồn (thường cùng phiên bản chính). Thao tác portable dùng `pg_dump`/`pg_restore` trên máy vận hành; thông tin xác thực nằm trong môi trường tiến trình, không nằm trong đối số lệnh hoặc báo cáo. Công cụ không tự động exec vào container cơ sở dữ liệu development thông thường. Quy trình Local cũ giữ phương án dự phòng Compose đã được xác minh. Image Web AWS chủ ý không có công cụ client PG; chạy từ môi trường vận hành được chuẩn bị riêng, bảo mật và có công cụ phù hợp, không giả định `docker compose exec backend pg_dump` tồn tại.

## Tính nhất quán và nội dung

Dừng/chờ **mọi** tác vụ ghi như mô tả trong [di chuyển](storage-migration.md). `--maintenance-window` bắt buộc khi sao lưu portable. Cờ này xác nhận người vận hành đã ngừng ghi, không phải khóa phân tán. Danh mục PostgreSQL và pg_dump dùng chung snapshot repeatable-read chỉ đọc đã xuất; tham chiếu được kiểm tra lại sau sao chép. Đối tượng dùng khóa bất biến, nhưng kho đối tượng và PostgreSQL không cùng giao dịch. Một tác vụ ghi bên ngoài có thể làm mất hiệu lực xác nhận bảo trì; đây không phải sao lưu nguyên tử trực tuyến xuyên hệ thống. Cũng phải đóng băng dọn dẹp/xóa.

Thư mục riêng tư đã hoàn tất chứa:

- `database.dump`: bản sao lưu logic PostgreSQL định dạng custom, đã xác minh SHA-256.
- `storage.tar.gz`: archive truyền theo luồng chỉ chứa đối tượng có tham chiếu, không phải toàn bucket, với khóa di động và dữ liệu gốc.
- `manifest.json`: `format_version: 2` tường minh, backend/môi trường nguồn và định danh đã băm, kích thước/SHA-256/MIME/nhóm từng đối tượng, mã băm tệp, xác nhận nhất quán và chỉ đặt `complete: true` sau xác minh.

Khóa chờ dọn dẹp là thông tin chẩn đoán, không phải đối tượng cần khôi phục. Đối tượng mồ côi, tệp FFmpeg/ZIP tạm, bộ nhớ đệm mô hình và thư mục cơ sở dữ liệu bị loại trừ. Mọi tham chiếu lịch sử còn hiệu lực đều được đưa vào; phạm vi rộng hơn danh mục công khai hoặc Test Transfer ZIP. Bản sao lưu có dữ liệu riêng tư và đáp án: bảo vệ như dữ liệu nhạy cảm, giới hạn quyền người vận hành, mã hóa khi lưu bằng nền tảng sao lưu và giữ một bản độc lập đã xác minh ngoài máy Web. Manifest không chứa khóa mã hóa hoặc thông tin xác thực.

Thất bại/hủy để lại thư mục riêng tư `.backup-incomplete-*` và manifest `complete:false` với loại lỗi đã lọc dữ liệu nhạy cảm. Thư mục không bao giờ được nâng thành sao lưu hoàn tất. Giữ để điều tra; chạy lại sao lưu vào gói mới. Không xóa đối tượng nguồn. Dump thất bại không thể trở thành thành công chỉ có cơ sở dữ liệu. Luồng dump/ghi archive đang chạy được chờ hoàn tất trước khi giải phóng snapshot. Dự trù dung lượng dump/archive và vùng spool tạm từng đối tượng của adapter.

## Tạo và xác minh

Đặt `DATABASE_URL` và `SOURCE_*` tường minh theo bảng môi trường trong [di chuyển](storage-migration.md). Từ `backend/`:

```sh
uv run python ../scripts/backup.py --portable --source s3 --backup-root /secure/backups --maintenance-window --report /secure/backup-report.json
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --verify-only --report /secure/verify-report.json
```

Dùng `--source local` hoặc `r2` với cấu hình độc lập phù hợp. Gói backend đã cài còn hỗ trợ lệnh tương đương không cần script trong repository: `python -m app.storage.recovery_cli backup ...` và `python -m app.storage.recovery_cli restore ...` (bỏ `--portable` tại đó).

Xác minh đọc theo luồng cả hai tệp và mọi thành viên archive. Nó từ chối mục thiếu, thừa, trùng, xung đột hoa/thường, vượt thư mục, liên kết, sparse, sai kích thước hoặc hỏng mà không giải nén theo đường dẫn trong archive. Manifest giới hạn 64 MiB / 250,000 đối tượng; mỗi đối tượng tuân theo hợp đồng lưu trữ 5 GiB. Báo cáo ghi SHA-256 của manifest: giữ giá trị đó độc lập trong danh mục sao lưu đáng tin cậy. Checksum phát hiện hỏng dữ liệu, **không** chống bên độc hại có thể sửa cả gói và manifest. Chỉ khôi phục bản sao lưu tin cậy; dump PostgreSQL có thể thực thi SQL. Kiểm tra dump lạ trong môi trường cách ly. PostgreSQL mô tả [snapshot đã xuất](https://www.postgresql.org/docs/current/app-pgdump.html) và [độ tin cậy/hành vi khôi phục](https://www.postgresql.org/docs/current/app-pgrestore.html).

## Khôi phục cô lập, với thao tác cơ sở dữ liệu được kiểm soát riêng

Tạo bucket/tiền tố recovery riêng tư hoặc thư mục Local mới. Đặt `DESTINATION_ENVIRONMENT=recovery` và giá trị `DESTINATION_*` tường minh. Đích phải khác nguồn sao lưu. Dữ liệu đã tồn tại và khớp có thể dùng lại; bất kỳ khóa khác biệt nào cũng chặn **mọi thao tác ghi trong lần chạy đó**. Không vô tình dùng bucket ứng dụng đang hoạt động làm đích khôi phục. Công cụ không xóa đối tượng hoặc thay thế xung đột; có thể tiếp tục lần chạy thất bại sau điều tra.

Tự cấp một cơ sở dữ liệu PostgreSQL recovery rỗng. Đặt `RESTORE_DATABASE_URL` tường minh (không dùng URL ứng dụng thường) và `RESTORE_ENVIRONMENT=recovery`. Tên phải chứa token `recovery`, `restore` hoặc `test`. Cơ sở dữ liệu phải khác nguồn và ứng dụng, không có quan hệ do người dùng tạo và không có session khác. Giới hạn truy cập để ứng dụng không thể chạy đua với bước tiền kiểm. Công cụ không tạo/đặt lại cơ sở dữ liệu hoặc khởi động máy chủ.

```sh
# Full read-only preflight; emits destination target_id, database_id and manifest hash.
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --destination r2 --database-preflight --report /secure/preflight.json
# Recover object bytes first; complete remains false until database reconciliation.
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --destination r2 --restore-objects --confirm-target REVIEWED_TARGET_ID --confirm-backup REVIEWED_MANIFEST_SHA256 --maintenance-window --allow-cross-environment --report /secure/restore-objects.json
# Separate, explicit database restore after every destination object is verified.
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --destination r2 --restore-database --confirm-target REVIEWED_TARGET_ID --confirm-database REVIEWED_DATABASE_ID --confirm-backup REVIEWED_MANIFEST_SHA256 --maintenance-window --allow-cross-environment --report /secure/restore-database.json
# Resume verification if restore committed but its acknowledgement/report was lost:
uv run python ../scripts/restore.py --portable /secure/backups/BUNDLE --destination r2 --reconcile-database --report /secure/restored-references.json
```

Khôi phục cơ sở dữ liệu dùng một giao dịch pg_restore, `--no-owner --no-acl`, không `--clean`, không `--create` và không hạ cấp schema. Tạo lại role/quyền riêng dưới kiểm soát người vận hành. Trước khi khôi phục, mọi đối tượng phải khớp gói. Sau đó, tập tham chiếu và siêu dữ liệu thực sự được khôi phục phải khớp manifest và các đối tượng đích đọc được. Chỉ khi đó khôi phục ứng dụng mới báo `complete:true`. Chỉ tải đối tượng thành công là chưa đủ. Nếu commit cơ sở dữ liệu thành công nhưng xác minh tiếp theo thất bại, tiếp tục dừng tác vụ ghi; giữ đối tượng/cơ sở dữ liệu để kiểm tra và có thể thử lại `--reconcile-database` an toàn. Không chạy lại pg_restore vào cơ sở dữ liệu đã có dữ liệu: điều kiện đích rỗng sẽ từ chối.

## Cấu hình triển khai và hoàn tác

Development Local dùng thư mục bền vững và công cụ client tương thích. Người vận hành Modal demo phải dùng môi trường bảo trì được kiểm soát, truy cập **cùng** cơ sở dữ liệu nhúng và Volume tài sản đã commit, giữ cơ chế một chủ sở hữu cơ sở dữ liệu. Không mount/khởi động chủ sở hữu PostgreSQL nhúng thứ hai. Chỉ xuất dump cơ sở dữ liệu kiểu cũ từ `/snapshots` không phải sao lưu ứng dụng đầy đủ. Ghi/commit gói v2 đã xác minh độc lập và giữ Volume gốc; không chỉ dựa vào lúc Web dừng để bảo đảm độ bền bản sao lưu. Symlink mount gốc được phân giải thành namespace chuẩn để xác định đích tường minh; liệt kê tài sản từ chối symlink/junction bên trong namespace đó.

Modal managed và AWS production dùng máy/tác vụ vận hành có truy cập an toàn tới cơ sở dữ liệu TLS bên ngoài và S3/R2 riêng tư đã cấu hình. Không công cụ nào phụ thuộc máy chủ phải là Modal/AWS. Topology/Secrets/mặc định replica P4 hiện có không đổi. Giai đoạn này không thêm endpoint sao lưu Modal tự động, tác vụ định kỳ hoặc triển khai cloud. Ở production, diễn tập lấy bản sao lưu độc lập và cấu hình cơ sở dữ liệu/CA client, không chỉ tạo bản sao trên cùng máy.

Giữ tài sản nguồn và bản sao lưu cơ sở dữ liệu tương ứng trước chuyển đổi. Trước ghi mới có thể dùng lại để hoàn tác; sau ghi mới cần cửa sổ bảo trì mới và đối soát hoặc quyết định điểm khôi phục/mất dữ liệu được phê duyệt tường minh. Xem [chuyển đổi/hoàn tác](storage-migration.md). Kiểm thử ngoại tuyến xác minh snapshot/dump/khôi phục PostgreSQL cô lập thật và khôi phục đối tượng qua S3 giả; quyền nhà cung cấp thật, độ bền lưu trữ, thông lượng và diễn tập phục hồi thảm họa vẫn là cổng staging riêng do người vận hành kiểm soát.
