# Security và reliability boundaries

> Mục đích và phạm vi: Các kiểm soát thực có, failure handling và việc chưa được chứng minh.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## Identity và authorization

[security.py](../../backend/app/core/security.py) dùng scrypt cho password, token HS256 kiểm signature/type/issuer/audience/expiry; [auth routes](../../backend/app/api/v1/auth.py) set HttpOnly cookies với Secure/SameSite theo Settings. [dependencies](../../backend/app/api/dependencies.py) load User hiện hành và kiểm active; không chỉ tin role cũ trong token. Refresh rotation lưu fingerprint và revoke state trong PostgreSQL; frontend single-flight/Web Locks giảm cuộc đua, không thay kiểm backend.

`safeAuthDestination` lọc next destination; proxy chuyển 401 tới session restoration và không tự sở hữu refresh. Transient API lỗi không nên biến thành “đăng xuất”. OAuth chỉ hoạt động nếu cấu hình đúng. Xem [Identity module](../modules/identity.md). Không thấy middleware rate-limit toàn cục trong app hiện tại; không được khẳng định có brute-force protection đầy đủ. SameSite/CORS không phải chứng nhận chống mọi CSRF; deployment threat review vẫn cần.

## Resource access và confidentiality

| Resource | Boundary ở source | Failure cần kiểm |
| --- | --- | --- |
| Builder/publish/moderation | AccessPolicy + actor/test/version locks | Draft của người khác, pending moderation, archived content |
| Active exam | Attempt owner/scope, presenters | Không có answer keys trước finalization; Full Mock review vẫn locked |
| Classroom results | Assignment provenance + capability | Cùng student/test nhưng là personal attempt phải bị chặn |
| Private audio/files | Asset access, Speaking/Classroom services rồi storage delivery | UUID/path không cấp quyền; membership/publication phải kiểm lại |
| Gradebook | Native accepted root + human final | AI chưa được người có quyền Save không trở thành final |
| Notifications | Recipient scope | Notification không cấp quyền target |

[AccessPolicy](../../backend/app/services/access_policy.py), [capabilities](../../backend/app/services/classroom_capabilities.py), [asset access](../../backend/app/services/asset_access.py), [delivery](../../backend/app/storage/delivery.py) là nguồn chính. S3/R2 object key opaque ở DB, không trả bucket credentials. Ranges không được bypass authorize; endpoint media kiểm quyền trước đọc bytes.

## Upload, import và output

Upload giới hạn kích thước, MIME/signature và path; Transfer còn kiểm file counts, expanded size, checksum và graph/schema trước import. React renderer không được bơm raw HTML từ content. Classroom markdown là subset; CSV gradebook xử lý formula/control characters. Đây là kiểm soát từng đường đi, không phải chứng nhận chống mọi malware trong file.

Speaking runtime có error wrapper không echo request input/DB parameters. `AppError` có code/status rõ; frontend chỉ xử lý known denial code, không nuốt mọi exception. Logs diagnostic optional không được ghi cookie/token/body/audio/transcript. [request timing](../../backend/app/core/request_timing.py) và Nginx timing dành điều tra có giới hạn; không phải observability stack đầy đủ.

## Reliability dưới cạnh tranh

Autosave revision, idempotent same-payload replay, parent-before-child locks và unique constraints giảm lost update/deadlock/duplicate advance. Timer deadline được kiểm sau lock; `setInterval` chỉ hiển thị. Process failure vẫn có thể gây ambiguous commit; [asset compensation](../../backend/app/services/asset_cleanup.py) bảo vệ committed reference, không xóa mù.

AI checkpoints/leases giữ progress và ngăn stale writer; không đảm bảo exactly-once external calls. Shutdown stop workers theo lifespan. SSE reconnect replay events; observer disconnect không cancel job. Database outage, missing audio hoặc model output sai phải hiện trạng thái lỗi/unavailable, không fabricated score.

## Operations và recovery

`/api/v1/health` là liveness, `/api/v1/ready` kiểm DB timeout; chúng không kiểm toàn bộ model/bucket. Embedded Modal DB cần một owner/guard và recreate lifecycle. Local Volume commit bất đồng bộ không phải immediate durability acknowledgement. Backup consistent cần dừng writers; restore và migration copy sang destination riêng, checksum và reconciliation trước cutover. [Storage backup](../storage-backup-restore.md), [migration](../storage-migration.md), [concurrency incident](../concurrency-audit.md).

## Cần xác minh riêng

Production IAM/TLS/secret rotation, live authenticated private-media/SSE, peak resource usage, DR drill, RPO/RTO và rate-limit policy chưa được audit này đo/triển khai. Không có cam kết SLA, security certification hoặc penetration-test result. Đề xuất tương lai phải ghi là đề xuất, kèm threat và test; không thêm control “đã có” chỉ vì hợp lý. Liên quan: [data](data-architecture.md), [runtime](runtime-architecture.md), [testing](testing-and-delivery.md).
