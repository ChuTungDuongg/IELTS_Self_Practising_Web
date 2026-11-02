# Kế hoạch triển khai Classroom 2.0

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: kế hoạch triển khai Classroom 2.0. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **Dành cho tác nhân triển khai:** chia phần feed, classwork và frontend độc lập để thực hiện song song với phạm vi rõ ràng. Yêu cầu gốc cho phép triển khai trên main mà không dừng duyệt kế hoạch.

**Mục tiêu:** mở rộng lớp học hiện có bằng Stream, thảo luận, Classwork có cấu trúc và tài nguyên học riêng tư, đồng thời giữ bài giao IELTS.
**Kiến trúc:** thêm bảng chuẩn hóa, giữ assignments là dữ liệu chuẩn. Services sở hữu transaction và phân quyền. Classroom row locks tuần tự hóa mọi mutation, gồm sắp xếp và lưu trữ. Lịch sử membership cho phép giữ quyền đọc; chỉ thành viên đang hoạt động được bình luận. ADMIN giữ quyền giám sát đọc và quản lý tại thời điểm kế hoạch này, nhưng ghi nội dung soạn mới yêu cầu TEACHER là chủ lớp.
**Công nghệ:** FastAPI, AsyncSession, PostgreSQL, Alembic, Next.js, React, Zod, pytest, Vitest. Không thêm runtime dependency.
**Đặc tả:** attachment của người dùng `4ff7a759-10be-4718-8b56-1a62c1578ff0/Pasted text.txt`.

## Ràng buộc chung

- Giữ xác thực, TestVersion bất biến, nguồn gốc assignment, chấm điểm và AI flows.
- Không chạy full suites, browsers, E2E, production builds hoặc dev stack.
- Giữ các storage deletions có sẵn và design files chưa theo dõi.
- Markdown subset an toàn render thành React nodes; không bao giờ render raw HTML.
- Vòng đời DRAFT/PUBLISHED/ARCHIVED. Học viên chỉ thấy resource đã publish nằm trong section đã publish.
- Tệp dùng local storage keys được sinh, allowlist hữu hạn/nhận dạng loại từ nội dung, download có xác thực và cleanup bù khi lỗi.
- Sắp xếp lại dùng danh sách IDs có thứ tự đầy đủ dưới classroom lock và expected revision. Xung đột trả 409; không âm thầm ghi đè.
- Hỗ trợ Anh/Việt và theme tokens chung; controls di chuyển bàn phím bổ sung native drag/drop.

## API contract dùng chung

Mọi đường dẫn dưới đây tương đối với `/api/v1/classrooms/{classroomId}`. Ngày là ISO strings, IDs là UUID strings.

Trạng thái chung: DRAFT | PUBLISHED | ARCHIVED. Danh sách phân trang trả `{items, next_cursor}`.

Feed: GET `/feed?cursor=&limit=20&status=`. Entries `{id, kind: ANNOUNCEMENT|DISCUSSION|ASSIGNMENT_ACTIVITY, title: string|null, body: string, status, pinned: boolean, author_id, author_name, author_role, created_at, updated_at, published_at: string|null, comment_count, resource_ids: string[], assignment_id: string|null}`. Với assignments, timestamps lấy từ assignment chuẩn. POST `/posts` với `{kind, title?, body, resource_ids?, status?: DRAFT|PUBLISHED}`. GET/PATCH `/posts/{id}` (patch cùng các trường tùy chọn, thêm `pinned?`, `locked?`, status). Vòng đời: POST `/posts/{id}/{publish|archive|pin}` (`pin` có body `{pinned}`). Bình luận GET/POST `/posts/{id}/comments` (`{body}`); PATCH/DELETE `/comments/{id}`. Comment `{id, post_id, author_id, author_name, body, state: VISIBLE|RETRACTED|MODERATED, created_at, updated_at}`. Body đã soft-delete phải trống trong DTOs.

Classwork: GET `/classwork` trả `{revision: number, sections: Section[], resources: Resource[], items: Item[]}`. Section `{id,classroom_id,title,description,status,position,created_at,updated_at}`. Resource `{id,classroom_id,title,description,kind: TEXT|LINK|FILE,body: string|null,url: string|null,status,original_filename: string|null,media_type: string|null,size_bytes: number|null,created_at,updated_at}`. Item `{id,section_id: string|null,resource_id: string|null,assignment_id: string|null,position}`.

POST `/sections` `{title,description?,status?}`; PATCH `/sections/{id}` với cùng trường tùy chọn. POST `/sections/reorder` `{ids: string[],expected_revision}`. POST `/resources` `{title,description?,kind:TEXT|LINK,body?,url?,status?,section_id?}`. PATCH `/resources/{id}` cho metadata/nội dung/trạng thái. POST `/resources/upload` multipart `file,title,description?,status,section_id?`. GET `/resources/{id}` lấy metadata; GET `/resources/{id}/file?inline=true` lấy tệp có xác thực. POST `/items` `{section_id: string|null,assignment_id}` đặt assignment hiện có vào Classwork (duy nhất trong lớp). POST `/items/reorder` `{section_id: string|null,ids: string[],expected_revision}` chuyển items sang section đích và chuẩn hóa cả nguồn/đích; IDs là toàn bộ thứ tự đích mong muốn. Alias GET `/sections`, GET `/resources` có thể trả `{items}`.

## Trọng tâm review

- Draft UUIDs, sections bị ẩn và phân quyền tệp riêng, gồm thành viên cũ.
- Timestamps bằng nhau qua các trang feed post/assignment.
- Revision conflicts và IDs sắp xếp thuộc lớp khác.
- Lớp đã archive chỉ đọc đối với mọi mutation mới.
- Kiểm tệp và cleanup sau ghi database thất bại.

## Công việc và tiến độ

- [x] Rà quy ước hiện có, storage, tests và migration head.
- [x] Classwork models, quyền nội dung dùng chung, resource storage và migration bổ sung (tác nhân chính).
- [x] Feed/post/comment models, schemas, service/router, notifications và tests tập trung (tác nhân feed).
- [x] Classroom UI có tabs dùng chung, typed clients, nội dung an toàn, composers, comments, reorder và component tests (tác nhân frontend).
- [x] Tích hợp routers/models/migration; kiểm backend/frontend tập trung và review.
- [x] Tài liệu, kiểm diff, commit đúng phạm vi, push an toàn lên origin/main.

## Baseline

Main HEAD: 9c0df34. Giữ nguyên và không stage các storage entries `.gitkeep` đã bị xóa từ trước cùng `.agents/`, `.taste-skill/`, `docs/design-references/`, `skills-lock.json` chưa theo dõi. Dependencies đã cài; không dự kiến cài thêm. Không tạo worktree cách ly vì bàn giao gốc yêu cầu main trong checkout hiện có.

## Kiểm chứng và quyết định

- Người dùng yêu cầu thêm migration database local thực tế. Cần quyền database cao hơn vì sandbox không thấy Docker engine. PostgreSQL hiện có khỏe; không chạy full app stack. Database test cách ly upgrade từ rỗng qua 0036 thành công. Database local được cấu hình sau đó upgrade từ 0035 lên `20261027_0036 (head)` thành công.
- Read locks dùng chung trên lớp (`FOR SHARE`) bảo vệ đọc nội dung nhiều truy vấn khỏi publish/membership changes đồng thời; mọi mutation mới giữ `FOR UPDATE`. Batch feed loading cũng áp dụng lại visibility.
- Tests cách ly cuối: 101 backend cases pass cho Classwork/storage/feed/lớp học hiện có và assignment scope; 57 frontend cases pass. Python lint theo phạm vi và frontend lint/type checks pass. Review độc lập sạch sau các bản sửa có regression tests về image-size policy, điều hướng notification cùng lớp và post controls có attachments bị ẩn.
- Tệp riêng dùng HTTP client có xử lý refresh hiện có trước khi tạo Blob URLs tạm; có cancellation và cleanup.
- Theo yêu cầu gốc, không chạy browser, E2E, production build hoặc toàn bộ test suite repository.
- Đối chiếu remote trước commit: `git fetch origin main`, divergence `0 0`.
