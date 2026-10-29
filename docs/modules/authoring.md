# Test Builder, question registry và content governance

> Mục đích và phạm vi: Biên soạn đề có cấu trúc, xuất bản nội dung frozen và quản lý eligibility.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## A–C. Mục đích, workflow và ownership

Biên soạn đề có cấu trúc, xuất bản nội dung frozen và quản lý eligibility.

ADMIN/TEACHER tạo Test/draft, thêm module/passage/task/prompt, chỉnh câu/key, autosave revision, preview, validate và publish hoặc gửi moderation. Library đọc phiên bản được phép; draft khác phiên bản người học đang làm.

TestService phối hợp clone/validation/lifecycle; Reading/Listening/Writing/Speaking builder services sở hữu hình dạng nội dung. Hai question registries là nguồn contract trung tâm, không phải switch riêng mỗi page.

## D. Implementation map

| Lớp | Source |
| --- | --- |
| Pages/features | [frontend/src/app/admin/tests/](../../frontend/src/app/admin/tests/); [frontend/src/app/teacher/tests/](../../frontend/src/app/teacher/tests/); [frontend/src/features/test-builder/](../../frontend/src/features/test-builder/); [frontend/src/features/questions/registry.tsx](../../frontend/src/features/questions/registry.tsx) |
| Clients | [frontend/src/lib/api/builder.ts](../../frontend/src/lib/api/builder.ts); [frontend/src/lib/api/tests.ts](../../frontend/src/lib/api/tests.ts); [frontend/src/lib/api/content-governance.ts](../../frontend/src/lib/api/content-governance.ts) |
| Routers/schemas | [backend/app/api/v1/tests.py](../../backend/app/api/v1/tests.py); [backend/app/api/v1/reading.py](../../backend/app/api/v1/reading.py); [backend/app/api/v1/content_governance.py](../../backend/app/api/v1/content_governance.py); [backend/app/schemas/tests.py](../../backend/app/schemas/tests.py); [backend/app/schemas/content.py](../../backend/app/schemas/content.py) |
| Services/repository | [backend/app/services/tests.py](../../backend/app/services/tests.py); [backend/app/services/access_policy.py](../../backend/app/services/access_policy.py); [backend/app/services/draft_revisions.py](../../backend/app/services/draft_revisions.py); [backend/app/services/content_governance.py](../../backend/app/services/content_governance.py); [backend/app/repositories/tests.py](../../backend/app/repositories/tests.py) |
| Domain/models | [backend/app/domains/questions/registry.py](../../backend/app/domains/questions/registry.py); [backend/app/domains/questions/normalization.py](../../backend/app/domains/questions/normalization.py); [backend/app/models/entities.py](../../backend/app/models/entities.py); [backend/app/models/content_governance.py](../../backend/app/models/content_governance.py) |
| Tests | [backend/tests/test_test_version_concurrency.py](../../backend/tests/test_test_version_concurrency.py); [backend/tests/test_version_validation.py](../../backend/tests/test_version_validation.py); [frontend/tests/question-registry.test.tsx](../../frontend/tests/question-registry.test.tsx); [frontend/tests/builder-autosave.test.tsx](../../frontend/tests/builder-autosave.test.tsx) |

## E–F. Data flow và API contracts

Luồng dữ liệu: structured editor → typed Builder API → mutable-version policy/revision → schema validation → PostgreSQL → Builder DTO; publish validation dùng graph thật, không tin cờ “valid” từ frontend.

Các đường dẫn sau dùng prefix `/api/v1`; DTO, dependency và response model ở router được dẫn trong bảng. [Source map](../handbook/source-map.md) liệt kê toàn bộ route cùng khai báo gốc.

- `POST /tests`
- `POST /tests/{test_id}/versions`
- `GET /test-versions/{version_id}/builder`
- `POST /test-versions/{version_id}/validate`
- `POST /test-versions/{version_id}/publish`
- `POST /test-versions/{version_id}/moderation-requests`
- `POST /admin/test-moderation-requests/{request_id}/approve`

## G. Persistence

Test → TestVersion → TestModule → structured content. QuestionGroup/Question có stable UUID/config/key JSON; TestVersionModeration lưu scope/status/reviewer riêng lifecycle nội dung. TestCover thuộc Test, không phải version; cover bytes qua storage.

## H. Business rules

Published authored content bất biến; edit bằng clone draft. Pending moderation khóa nội dung; CLASSROOM approval không thành PUBLIC. Question numbering không đổi identity; completion dùng gap question IDs, image marker chuẩn hóa 0–1. Mỗi objective type cần editor, key editor, schema, evaluator, exam/review renderer.

## I. Security

AccessPolicy lock actor → test → version trước mutation. Owner/ADMIN Builder permissions không đồng nghĩa learner public visibility. Active exam DTO tuyệt đối không lấy Builder schema có answer keys.

## J. Failure và recovery

Revision conflict 409 yêu cầu reconcile; autosave flush trước preview/publish. Upload/clone failure bù trừ bytes với durable-reference check. Concurrent publish/edit được serialize, không last-write-wins âm thầm.

## K. Focused testing

Backend validation/key/normalization/concurrency tests; frontend question-registry, draft-answer-autosave, builder-route, draft-preview và persisted-question-contracts. Kiểm từ authoring tới active DTO và review, không chỉ snapshot editor.

## L. Extension guide

Thêm objective type theo ví dụ A trong playbook: cả registry Python/TS, union, structured config, evaluator, renderers, clone/transfer remap, fixtures. Đừng hardcode test content hoặc thay historical IDs.

## M. Giới hạn

Import draft nhận JSON chuẩn bị bên ngoài, không OCR tích hợp. Moderation là quyền xuất bản, không xác nhận bản quyền; chỉ commit nội dung có quyền sử dụng.

## N. Câu hỏi phỏng vấn

**1. Tại sao version bất biến?** Giữ đề/key của historical attempt ổn định khi tác giả sửa đề mới.

**2. Registry giải quyết gì?** Một điểm đăng ký contract và renderer/evaluator giúp không có type chỉ hoạt động ở Builder.

**3. CLASSROOM khác PUBLIC?** CLASSROOM cho eligibility theo lớp, không tự xuất hiện trong Library công khai.

## Tài liệu liên quan

[Objective skills](reading-listening.md), [transfer](assets-transfer.md), [feature playbook](../handbook/feature-development-playbook.md).
