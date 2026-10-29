# Administration, moderation và benchmark bank

> Mục đích và phạm vi: Quản lý tài khoản/nội dung và công cụ đánh giá nội bộ mà không mở rộng quyền lớp học ngầm.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## A–C. Mục đích, workflow và ownership

Quản lý tài khoản/nội dung và công cụ đánh giá nội bộ mà không mở rộng quyền lớp học ngầm.

ADMIN đọc stats/directory, mở account detail, đổi role/active state hoặc xóa account đã vô hiệu theo preconditions. Moderation preview/approve/reject/revoke đi workflow nội dung. Writing benchmark bank nhập human labels, complete sample, export dữ liệu đánh giá.

AdminService owns account operations và dependency guards; AdminDirectoryService query directory/observer metadata. ContentGovernanceService owns moderation. WritingBenchmarkService owns samples/limits/completeness, export service owns portable evaluation output.

## D. Implementation map

| Lớp | Source |
| --- | --- |
| Pages/UI | [frontend/src/app/admin/](../../frontend/src/app/admin/); [frontend/src/features/admin/](../../frontend/src/features/admin/); [frontend/src/features/writing-benchmark/](../../frontend/src/features/writing-benchmark/) |
| Clients | [frontend/src/lib/api/admin.ts](../../frontend/src/lib/api/admin.ts); [frontend/src/lib/api/admin-directory.ts](../../frontend/src/lib/api/admin-directory.ts); [frontend/src/lib/api/content-governance.ts](../../frontend/src/lib/api/content-governance.ts); [frontend/src/lib/api/writing-benchmark.ts](../../frontend/src/lib/api/writing-benchmark.ts) |
| Router/schema | [backend/app/api/v1/admin.py](../../backend/app/api/v1/admin.py); [backend/app/api/v1/content_governance.py](../../backend/app/api/v1/content_governance.py); [backend/app/api/v1/writing_benchmark.py](../../backend/app/api/v1/writing_benchmark.py); [backend/app/schemas/admin.py](../../backend/app/schemas/admin.py); [backend/app/schemas/admin_directory.py](../../backend/app/schemas/admin_directory.py); [backend/app/schemas/writing_benchmark.py](../../backend/app/schemas/writing_benchmark.py) |
| Service/repository/model | [backend/app/services/admin.py](../../backend/app/services/admin.py); [backend/app/services/admin_directory.py](../../backend/app/services/admin_directory.py); [backend/app/repositories/admin_directory.py](../../backend/app/repositories/admin_directory.py); [backend/app/services/content_governance.py](../../backend/app/services/content_governance.py); [backend/app/services/writing_benchmark.py](../../backend/app/services/writing_benchmark.py); [backend/app/models/writing_benchmark.py](../../backend/app/models/writing_benchmark.py) |
| Tests | [backend/tests/test_admin.py](../../backend/tests/test_admin.py); [backend/tests/test_admin_directory.py](../../backend/tests/test_admin_directory.py); [backend/tests/test_moderation_concurrency.py](../../backend/tests/test_moderation_concurrency.py); [backend/tests/test_writing_benchmark_capacity.py](../../backend/tests/test_writing_benchmark_capacity.py); [frontend/tests/admin-directory.test.tsx](../../frontend/tests/admin-directory.test.tsx) |

## E–F. Data flow và API contracts

Admin page → typed client → require_admin → domain-specific guard → transaction/query → minimized DTO. Observer classroom đọc existing services sau authorization; không clone một hệ thống gradebook admin riêng.

Các đường dẫn sau dùng prefix `/api/v1`; DTO, dependency và response model ở router được dẫn trong bảng. [Source map](../handbook/source-map.md) liệt kê toàn bộ route cùng khai báo gốc.

- `GET /admin/stats`
- `GET /admin/users`
- `PATCH /admin/users/{user_id}`
- `DELETE /admin/users/{user_id}`
- `GET /admin/directory/people`
- `GET /admin/directory/classrooms`
- `GET /admin/test-moderation-requests`
- `POST /admin/test-moderation-requests/{request_id}/reject`

## G. Persistence

User role/is_active, RefreshSession, dependent content/classroom references; TestVersionModeration retains decision history; WritingBenchmarkSample stores score labels/task metadata/image key. Directory is query projection, không một account model mới.

## H. Business rules

Demotion/deactivation phải xét active classrooms, staff/moderation/draft obligations. Permanent delete không đồng nghĩa cascade mọi academic record; service kiểm dependencies. Moderation approval validate/publish trong transaction và giữ origin. Benchmark completeness/capacity enforce backend, không chỉ form.

## I. Security

AdminUser dependency và service guards, không dựa admin URL. ADMIN observer classroom quyền đọc được phân biệt với platform governance; không có candidate mutations hay teacher authorship tự động. Private benchmark image dùng authenticated endpoint.

## J. Failure và recovery

Conflict thông báo cần giải quyết dependencies trước thao tác account/content. Concurrent decision serialize bằng locks/unique state. Không sửa DB thủ công để bỏ chặn xóa. Export file thiếu ảnh/checksum không được coi benchmark đầy đủ.

## K. Focused testing

Role transitions, inactive deletion references, directory pagination/permissions, moderation race, benchmark CRUD/capacity/image/export. Frontend tests kiểm không hiện edit controls cho observer, error states và route contracts.

## L. Extension guide

Thêm administrative operation phải chọn scope account/platform/classroom chính xác, server dependency + policy, output minimization và relevant audit history. Nếu metric directory, query bounded qua repository thay dump toàn bộ users.

## M. Giới hạn

Stats không chứng minh traffic thương mại hay user engagement. Benchmark labels không chứng minh licensed data hoặc examiner quality; phải có quyền sử dụng và quy trình gắn nhãn. Không có billing/paid subscriptions trong module đã kiểm tra.

## N. Câu hỏi phỏng vấn

**1. ADMIN có toàn quyền không?** Không; các boundary classroom observer, retained history và pending governance vẫn có preconditions.

**2. Vì sao delete bị chặn?** Academic/content references cần retention; cascade bừa có thể phá lịch sử hoặc quyền sở hữu.

**3. Benchmark bank là AI training?** Hiện là lưu/export ground truth cho evaluation offline; không tự huấn luyện model.

## Tài liệu liên quan

[Classroom](classrooms.md), [Builder](authoring.md), [benchmark bank](../writing-benchmark-bank.md).
