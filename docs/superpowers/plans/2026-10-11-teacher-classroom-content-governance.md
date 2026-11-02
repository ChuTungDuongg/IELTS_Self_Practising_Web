# Kế hoạch triển khai giáo viên, lớp học, quản trị nội dung và thông báo

> **Kiểm toán tài liệu: HISTORICAL.** Tham khảo lịch sử, không phải hợp đồng hiện hành.
> Mục đích: kế hoạch triển khai giáo viên, lớp học, quản trị nội dung và thông báo. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/classrooms.md); [kiểm toán và giới hạn](../../DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong đợt kiểm toán này.

> **Dành cho worker tác nhân:** KỸ NĂNG PHỤ BẮT BUỘC: dùng superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans để triển khai từng tác vụ. Các bước dùng ô đánh dấu (`- [ ]`) để theo dõi.

**Mục tiêu:** thêm tài khoản TEACHER, đề thuộc giáo viên với ADMIN kiểm duyệt, lớp/lời mời/bài giao, thông báo chung trong ứng dụng, quyền giáo viên chỉ đọc bài học viên có nguồn gốc bài giao, không nới bảo mật USER/ADMIN hoặc ngữ nghĩa lịch sử hiện có.

**Kiến trúc:** giữ vòng đời nội dung `Test`/`TestVersion` hiện có (`DRAFT`, `PUBLISHED`, `ARCHIVED`), thêm lớp quyền sở hữu, kiểm duyệt, truy cập lớp và thông báo quanh đó. Phân quyền phía máy chủ theo tài nguyên; nguồn gốc bài giao, không phải chỉ tư cách thành viên cộng định danh đề, là ranh giới cho giáo viên xem bài. Frontend chủ đích tối thiểu: mở luồng đã duyệt, dùng Builder/xem lại hiện có khi được, không tạo dự án thiết kế riêng.

**Công nghệ:** FastAPI, SQLAlchemy async ORM, PostgreSQL/Alembic, Pydantic, Next.js 16, React 19, TypeScript, Zod, Vitest/RTL.

**Đặc tả:** `docs/superpowers/specs/2026-10-11-teacher-classroom-content-governance-design.md`

## Ràng buộc chung

- Đăng ký công khai luôn tạo `USER`; chỉ ADMIN nâng `USER -> TEACHER`.
- `TEACHER` giữ khả năng USER thường, không là bảng tài khoản riêng.
- Nội dung giáo viên tạo vẫn thuộc giáo viên sau phê duyệt; ADMIN không được âm thầm chuyển quyền sở hữu khi kiểm duyệt.
- Mọi phiên bản giáo viên tạo phải được ADMIN duyệt trước khi người khác dùng, kể cả chỉ trong lớp.
- Kiểm duyệt `CLASSROOM`, `PUBLIC` là phạm vi riêng; PUBLIC cho đủ điều kiện lớp, chiều ngược lại không đúng.
- Giữ `VersionStatus = DRAFT | PUBLISHED | ARCHIVED`; trạng thái kiểm duyệt ở bảng riêng.
- Phiên bản giáo viên đã duyệt/xuất bản bất biến; sửa cần nháp/phiên bản mới và kiểm duyệt mới.
- V1 mỗi lớp đúng một giáo viên sở hữu; không đồng giảng/chuyển chủ.
- V1 lời mời chỉ trong ứng dụng; email chưa có tài khoản giữ chờ đến khi tài khoản khớp xác thực, học viên phải Chấp nhận/Từ chối rõ ràng.
- Nguồn gốc bài giao quyết định quyền xem kết quả. Luyện cá nhân cùng đề vẫn riêng tư.
- Giáo viên chỉ đọc kết quả; thao tác chấm Writing vốn chỉ ADMIN vẫn chỉ ADMIN.
- Lưu trữ/thu hồi đổi hoạt động/hiển thị tương lai, không xóa lịch sử học tập.
- Thông báo là biểu diễn UX/sự kiện chung, không là mã cấp quyền.
- Cho làm lại bài giao; không thêm ràng buộc mỗi học viên duy nhất một lượt.
- Giữ hiển thị đề chính thức/quản trị và hành vi lượt/lịch sử ngoài lớp hiện có.
- Đầu migration khi lập kế hoạch là `20261011_0023`; tạo tiếp từ đầu thực sau kéo main, không rẽ lịch sử Alembic nếu thượng nguồn đổi.
- Xác minh tập trung, ít chi phí: chỉ kiểm đơn vị/tích hợp; không trình duyệt, Playwright, E2E, máy chủ dev, mô hình/GPU trực tiếp, Modal, triển khai.

## Trọng tâm rà soát

1. Hai yêu cầu Chấp nhận đồng thời cùng lời mời phải tạo một tư cách thành viên hoạt động, một chuyển sang chấp nhận, không dòng trùng.
2. Giáo viên biết ID đề/phiên bản/lớp/bài giao giáo viên khác vẫn nhận 403/404 theo quy ước; ID không bỏ qua kiểm quyền sở hữu.
3. Thu hồi PUBLIC khi còn CLASSROOM phải bỏ hiển thị toàn cục, giữ điều kiện lớp; thu hồi phê duyệt cuối đang hiệu lực phải chặn khởi tạo bài giao mới mà không xóa lịch sử.
4. Duyệt v2 không sửa lượt gắn v1; nội dung/lịch sử cũ vẫn hợp tham chiếu dù v1 lưu trữ cho lần khởi tạo tương lai.
5. Gắn lời mời chờ qua đăng nhập/đăng ký lặp phải lặp an toàn: không gắn trùng, không thành viên/thông báo trùng.

---

### Tác vụ 1: Enum miền, mô hình lưu trữ và migration Alembic

**Tệp:**
- Sửa: `backend/app/models/enums.py`
- Sửa: `backend/app/models/entities.py`
- Tạo: `backend/app/models/content_governance.py`
- Tạo: `backend/app/models/classroom.py`
- Tạo: `backend/app/models/notifications.py`
- Sửa: `backend/app/models/__init__.py`
- Tạo: `backend/alembic/versions/20261011_0024_teacher_classroom_governance.py` (hoặc revision tiếp từ đầu vừa kéo thực tế)
- Kiểm thử: `backend/tests/test_teacher_domain_models.py`

**Giao diện:**
- Tạo `UserRole.TEACHER` cùng `TestOrigin`, `ModerationScope`, `ModerationStatus`, `ClassroomStatus`, `InvitationStatus`, `AssignmentStatus` và enum loại/thực thể thông báo dùng về sau.
- Tạo `Test.owner_user_id`, `Test.origin`, `TestVersionModeration`, `Classroom`, `ClassroomInvitation`, `ClassroomMembership`, `ClassroomAssignment`, `Notification`, khóa ngoại nguồn gốc bài giao null trên `Attempt`/`TestSession` như chọn dưới.
- Nguồn gốc Full Mock ở `TestSession.classroom_assignment_id`; mô-đun riêng/theo phạm vi ở `Attempt.classroom_assignment_id`. Không nhân khóa bài giao Full Mock lên lượt con trừ khi truy vấn sẵn cần và kiểm thử chứng minh cần.

- [x] **Bước 1: viết kiểm hợp đồng mô hình/migration thất bại**

Thêm kiểm tập trung cho enum mới, cột giáo viên/chủ đề, duy nhất thành viên hoạt động, lời mời chờ, kiểm duyệt chờ mỗi phạm vi, người nhận/chỉ mục thông báo, cột nguồn gốc null. Có kiểm cũ chứng minh `origin=ADMIN, owner_user_id=NULL` biểu diễn được đề chính thức trước migration.

- [x] **Bước 2: chạy kiểm mô hình, xác nhận thất bại**

Chạy: `cd backend && uv run pytest tests/test_teacher_domain_models.py -q`

Kỳ vọng: FAIL vì enum/mô hình/cột chưa có.

- [x] **Bước 3: triển khai hợp đồng ORM/migration**

Dùng tệp mô hình tập trung riêng cho hệ mới, không mở thêm `entities.py`. Migration phải an toàn thêm `TEACHER` vào `user_role` PostgreSQL, gán bù đề cũ `origin=ADMIN` với chủ cũ null, tạo bảng/chỉ mục/ràng buộc mới, giữ mọi dòng/khóa ngoại. Đề ứng dụng tạo mới cần chủ dù cột DB vẫn null cho nội dung chính thức cũ.

- [x] **Bước 4: kiểm mô hình và chạy thử migration**

Chạy: `cd backend && uv run pytest tests/test_teacher_domain_models.py -q`

Chạy lệnh thử nâng/hạ Alembic hiện có nếu có; nếu không chạy kiểm migration nhỏ nhất sẵn có. Kỳ vọng: PASS.

- [x] **Bước 5: commit**

```bash
git add backend/app/models backend/alembic/versions backend/tests/test_teacher_domain_models.py
git commit -m "Add teacher classroom governance domain model"
```

---

### Tác vụ 2: Quản trị vai trò giáo viên, lớp chính sách, quyền sở hữu đề

**Tệp:**
- Tạo: `backend/app/services/access_policy.py`
- Sửa: `backend/app/services/admin.py`
- Sửa: `backend/app/schemas/admin.py`
- Sửa: `backend/app/api/v1/admin.py`
- Sửa: `backend/app/services/tests.py`
- Sửa: `backend/app/api/v1/tests.py`
- Sửa: `backend/app/schemas/tests.py`
- Sửa: `backend/app/api/v1/assets.py`
- Sửa tuyến/dịch vụ thay đổi Builder Reading/Listening/Writing/câu hỏi hiện dựa chỉ ADMIN hoặc `ensure_draft` thiếu ngữ cảnh quyền sở hữu.
- Kiểm thử: `backend/tests/test_teacher_roles_and_test_ownership.py`
- Kiểm hồi quy: `backend/tests/test_admin.py`

**Giao diện:**
- Tạo chính sách tập trung tương đương `require_test_create`, `require_test_edit`, `require_version_mutable`, `require_classroom_manage`, `require_assignment_view`, `require_admin_moderation`, dịch vụ sau gọi trước thay đổi/đọc.
- `TestService.create_test(..., actor)` ghi `origin`, `owner_user_id`; phản hồi danh sách/đọc giáo viên chỉ lộ nháp/riêng thuộc sở hữu và nội dung vốn được đọc; USER thường vẫn chỉ nội dung xuất bản có quyền.

- [x] **Bước 1: viết kiểm phân quyền thất bại**

Bao phủ ADMIN nâng USER→TEACHER; đăng ký công khai vẫn USER; giáo viên tạo đề thuộc mình; cấm USER tạo; cho sửa nháp của mình, cấm sửa đề giáo viên khác/phiên bản đã duyệt/xuất bản; giữ ADMIN ghi đè; hạ vai trò trả `TEACHER_HAS_ACTIVE_RESOURCES` khi còn tài nguyên giáo viên hoạt động/kiểm duyệt chờ.

- [x] **Bước 2: chạy kiểm phân quyền tập trung, xác nhận thất bại**

Chạy: `cd backend && uv run pytest tests/test_teacher_roles_and_test_ownership.py tests/test_admin.py -q`

Kỳ vọng: kiểm mới FAIL vì thiếu vai trò/chính sách/quyền sở hữu; kiểm ADMIN cũ vẫn đạt hoặc lộ đổi hợp đồng có chủ đích.

- [x] **Bước 3: triển khai phân quyền Builder theo chính sách**

Giữ `AdminUser` cho điểm cuối thực sự chỉ ADMIN như chấm Writing chính thức. Điểm cuối đổi nội dung/Builder dùng người xác thực + chính sách tài nguyên tập trung; không thay `AdminUser` bằng `CurrentUser` không hạn chế. Truyền kiểm tác nhân/tài nguyên xuyên thay đổi tài sản/Reading/Listening/Writing/câu để giáo viên không gọi tầng dưới né quyền.

- [x] **Bước 4: chạy kiểm backend tập trung**

Chạy: `cd backend && uv run pytest tests/test_teacher_roles_and_test_ownership.py tests/test_admin.py tests/test_writing_builder.py tests/test_asset_access.py -q`

Kỳ vọng: PASS.

- [x] **Bước 5: commit**

```bash
git add backend/app/services backend/app/api/v1 backend/app/schemas backend/tests
git commit -m "Add teacher role and owned Builder access"
```

---

### Tác vụ 3: Kiểm duyệt phiên bản, hiển thị chính thức/cộng đồng

**Tệp:**
- Tạo: `backend/app/schemas/content_governance.py`
- Tạo: `backend/app/repositories/content_governance.py`
- Tạo: `backend/app/services/content_governance.py`
- Tạo: `backend/app/api/v1/content_governance.py`
- Sửa: `backend/app/api/v1/router.py`
- Sửa: `backend/app/services/tests.py`
- Sửa: `backend/app/api/v1/tests.py`
- Sửa: `backend/app/api/v1/presenters.py` nếu siêu dữ liệu chủ/nguồn/kiểm duyệt thuộc DTO đề/phiên bản hiện có.
- Kiểm thử: `backend/tests/test_test_version_moderation.py`
- Kiểm hồi quy: `backend/tests/test_api_contract.py`

**Giao diện:**
- Tạo `submit_moderation(version_id, scope, note, actor)`, `cancel_request(request_id, actor)` cho giáo viên, `approve/reject/revoke` ADMIN và hàm `version_access(version, user)` cho thư viện/lớp.
- Bất kỳ yêu cầu PENDING đều khóa phiên bản khỏi sửa nội dung. Duyệt giáo viên thành công đầu chuyển sang `PUBLISHED` bất biến; duyệt PUBLIC sau có thể tái dùng. PUBLIC cho hiển thị cộng đồng toàn cục/điều kiện lớp, CLASSROOM chỉ điều kiện lớp.

- [x] **Bước 1: viết kiểm kiểm duyệt/máy trạng thái thất bại**

Bao phủ gửi/hủy, xung đột yêu cầu chờ trùng, khóa nháp lúc chờ, chỉ chủ gửi/ADMIN xét, duyệt/từ chối lặp an toàn và đồng thời, độc lập PUBLIC/CLASSROOM, PUBLIC⇒đủ lớp, chỉ công khai sau PUBLIC, đề chính thức quản trị/cũ đã xuất bản vẫn toàn cục, quy tắc thu hồi, duyệt v2 giữ lịch sử v1 và chặn sửa bản xuất bản.

- [x] **Bước 2: chạy kiểm kiểm duyệt, xác nhận thất bại**

Chạy: `cd backend && uv run pytest tests/test_test_version_moderation.py tests/test_api_contract.py -q`

Kỳ vọng: FAIL vì thiếu API/dịch vụ/chính sách hiển thị kiểm duyệt.

- [x] **Bước 3: triển khai dịch vụ/API kiểm duyệt**

Mỗi lần gửi là dòng kiểm toán mới, không ghi đè quyết định cũ. Dùng khóa dòng trong giao dịch hoặc mẫu đồng thời tương đương cho duyệt/từ chối/hủy/thu hồi. Bản mới thành bản xuất bản hoạt động phải giữ bản trước và mọi lượt/phiên tham chiếu; chỉ lưu trữ cho chọn nội dung tương lai, không sửa khóa lịch sử. Thông báo giáo viên qua giao diện Notification Tác vụ 4; trước đó dùng giao diện nhỏ tiêm được/không thao tác thay vì gắn kiểm duyệt với chèn thông báo thô.

- [x] **Bước 4: chạy hồi quy kiểm duyệt/thư viện**

Chạy: `cd backend && uv run pytest tests/test_test_version_moderation.py tests/test_api_contract.py tests/test_asset_access.py -q`

Kỳ vọng: PASS.

- [x] **Bước 5: commit**

```bash
git add backend/app/schemas/content_governance.py backend/app/repositories/content_governance.py backend/app/services/content_governance.py backend/app/api/v1/content_governance.py backend/app/api/v1/router.py backend/app/services/tests.py backend/app/api/v1/tests.py backend/app/api/v1/presenters.py backend/tests/test_test_version_moderation.py backend/tests/test_api_contract.py
git commit -m "Add teacher test moderation workflow"
```

---

### Tác vụ 4: Lớp, lời mời, thành viên và thông báo

**Tệp:**
- Tạo: `backend/app/schemas/classrooms.py`
- Tạo: `backend/app/repositories/classrooms.py`
- Tạo: `backend/app/services/classrooms.py`
- Tạo: `backend/app/api/v1/classrooms.py`
- Tạo: `backend/app/schemas/notifications.py`
- Tạo: `backend/app/repositories/notifications.py`
- Tạo: `backend/app/services/notifications.py`
- Tạo: `backend/app/api/v1/notifications.py`
- Sửa: `backend/app/api/v1/router.py`
- Sửa: `backend/app/services/auth.py` (hoặc hook sau xác thực đúng hiện có) để gắn lời mời chờ lặp an toàn sau đăng ký/đăng nhập email khớp.
- Kiểm thử: `backend/tests/test_classrooms_and_notifications.py`

**Giao diện:**
- Tạo CRUD/lưu trữ/khôi phục lớp, tạo/hủy/chấp nhận/từ chối lời mời, xóa/rời thành viên, `NotificationService.create_once(...)`, danh sách/số chưa đọc/đọc/đọc hết và `bind_pending_invitations(user)`.
- Thông báo duy nhất/lặp an toàn theo người nhận + loại sự kiện + định danh thực thể; thao tác luôn tải lại và phân quyền lời mời/lớp/kiểm duyệt bên dưới.

- [x] **Bước 1: viết kiểm lớp/lời mời/thông báo thất bại**

Bao phủ TEACHER tạo lớp một chủ; cấm USER tạo/giáo viên khác quản; lưu trữ chỉ đọc; ADMIN lưu trữ/khôi phục; mời email có/chưa có; chống mời trùng; Chấp nhận/Từ chối rõ; từ chối email sai; hai Chấp nhận đồng thời; rời/xóa giữ thành viên lịch sử; email chưa biết gắn khi đăng nhập sau; đăng nhập lặp không trùng thông báo; số chưa đọc; đọc một/hết; ID thông báo không né phân quyền.

- [x] **Bước 2: chạy kiểm lớp, xác nhận thất bại**

Chạy: `cd backend && uv run pytest tests/test_classrooms_and_notifications.py -q`

Kỳ vọng: FAIL vì API lớp/thông báo chưa có.

- [x] **Bước 3: triển khai dịch vụ lớp/thông báo**

Giải quyết thành viên/lời mời trong giao dịch. Không xóa cứng lịch sử lớp/thành viên. Lớp lưu trữ cấm mời mới/đổi thành viên/giao bài/khởi tạo. Gửi email ngoài phạm vi. Nay dịch vụ có, nối thông báo duyệt/từ chối qua `NotificationService.create_once`.

- [x] **Bước 4: chạy hồi quy lớp/xác thực**

Chạy: `cd backend && uv run pytest tests/test_classrooms_and_notifications.py tests/test_admin.py -q`

Thêm tệp kiểm xác thực sẵn nhỏ nhất nếu cần cho hook đăng nhập/đăng ký. Kỳ vọng: PASS.

- [x] **Bước 5: commit**

```bash
git add backend/app/schemas/classrooms.py backend/app/repositories/classrooms.py backend/app/services/classrooms.py backend/app/api/v1/classrooms.py backend/app/schemas/notifications.py backend/app/repositories/notifications.py backend/app/services/notifications.py backend/app/api/v1/notifications.py backend/app/api/v1/router.py backend/app/services/auth.py backend/tests/test_classrooms_and_notifications.py
git commit -m "Add classrooms invitations and notifications"
```

---

### Tác vụ 5: Bài giao lớp và nguồn gốc lượt bền vững

**Tệp:**
- Mở rộng: `backend/app/schemas/classrooms.py`
- Mở rộng: `backend/app/repositories/classrooms.py`
- Mở rộng: `backend/app/services/classrooms.py`
- Mở rộng: `backend/app/api/v1/classrooms.py`
- Sửa: `backend/app/services/attempts.py`
- Sửa: `backend/app/services/test_sessions.py`
- Chỉ sửa `backend/app/schemas/attempts.py` nếu cần DTO tiếp hợp khởi tạo bài giao nội bộ; API khởi tạo công khai thường không được nhận nguồn gốc bài giao tùy ý.
- Kiểm thử: `backend/tests/test_classroom_assignments.py`
- Kiểm hồi quy: `backend/tests/test_focused_attempts.py`
- Kiểm hồi quy: TestSession/Full Mock hiện có.

**Giao diện:**
- Tạo `create_assignment`, `archive_assignment`, danh sách/chi tiết bài giao và `start_assignment(assignment_id, request, actor)`.
- `start_assignment` suy `test_version_id`, lớp, giáo viên, nguồn gốc từ bài giao. Hỗ trợ lượt mô-đun/theo phạm vi và Full Mock/TestSession qua dịch vụ hiện có; trình duyệt không gắn bài giao vào lượt/phiên đã có.

- [x] **Bước 1: viết kiểm bài giao/nguồn gốc thất bại**

Bao phủ chỉ lớp hoạt động thuộc sở hữu được giao; phiên bản giáo viên cần CLASSROOM/PUBLIC; đề chính thức ADMIN đã xuất bản giao được; phiên bản thu hồi/lưu trữ và lớp lưu trữ cấm giao/khởi mới; chỉ thành viên hoạt động khởi được; làm lại tạo lượt/phiên riêng; lưu nguồn gốc; gọi `/attempts`/`/test-sessions` thường không giả được nguồn; bài cũ vẫn đọc sau kết thúc thành viên.

- [x] **Bước 2: chạy kiểm bài giao tập trung, xác nhận thất bại**

Chạy: `cd backend && uv run pytest tests/test_classroom_assignments.py tests/test_focused_attempts.py -q`

Kỳ vọng: FAIL vì thiếu bài giao/khởi tạo/nguồn gốc.

- [x] **Bước 3: điều phối khởi tạo bài giao**

Dùng `AttemptService`, `TestSessionService` cho vòng đời thi thực, không tạo logic lượt song song. Truyền nguồn gốc tin cậy nội bộ từ `start_assignment`; giữ DTO khởi thường tương thích ngược. Full Mock lưu nguồn ở `TestSession`; mô-đun riêng/theo phạm vi ở `Attempt`.

- [x] **Bước 4: chạy hồi quy bài giao/vòng đời**

Chạy kiểm bài giao mới cùng tập hồi quy lượt/TestSession nhỏ nhất bao phủ toàn mô-đun, đơn vị theo phạm vi, Full Mock. Kỳ vọng: PASS.

- [x] **Bước 5: commit**

```bash
git add backend/app/schemas/classrooms.py backend/app/repositories/classrooms.py backend/app/services/classrooms.py backend/app/api/v1/classrooms.py backend/app/services/attempts.py backend/app/services/test_sessions.py backend/app/schemas/attempts.py backend/tests/test_classroom_assignments.py backend/tests/test_focused_attempts.py
git commit -m "Add classroom assignments and attempt provenance"
```

---

### Tác vụ 6: Giáo viên chỉ đọc kết quả bài giao

**Tệp:**
- Tạo: `backend/app/services/classroom_results.py`
- Mở rộng: `backend/app/schemas/classrooms.py`
- Mở rộng: `backend/app/api/v1/classrooms.py`
- Tái dùng, không nới: trình bày/dịch vụ xem lại/lịch sử trong `backend/app/services/attempts.py`, `backend/app/schemas/attempts.py`, mô hình đọc Writing AI và dịch vụ điểm/lịch sử hiện có.
- Kiểm thử: `backend/tests/test_teacher_assignment_results.py`

**Giao diện:**
- Tạo điểm cuối tóm tắt kết quả bài giao, chi tiết lượt/phiên từng học viên, phân quyền nghiêm qua nguồn gốc bài giao + chủ lớp.
- Chi tiết chỉ đọc có thể gồm câu trả lời/đúng sai/band Listening/Reading, bài Writing, điểm thủ công/chính thức, kết quả/nhận xét AI hiện gắn lượt đã được phép.

- [x] **Bước 1: viết kiểm riêng tư kết quả giáo viên thất bại**

Bao phủ giáo viên đọc kết quả bài mình giao sau học viên rời; không đọc bài giáo viên khác; cùng học viên/cùng đề luyện cá nhân vẫn riêng; USER không dùng điểm cuối giáo viên; giáo viên không gọi thay điểm Writing chỉ ADMIN kể cả bài của lớp mình.

- [x] **Bước 2: chạy kiểm kết quả/riêng tư, xác nhận thất bại**

Chạy: `cd backend && uv run pytest tests/test_teacher_assignment_results.py tests/test_writing_attempts.py -q`

Kỳ vọng: FAIL vì thiếu điểm cuối giáo viên, hồi quy chấm ADMIN vẫn bảo vệ.

- [x] **Bước 3: triển khai dịch vụ kết quả chỉ đọc theo nguồn gốc**

Dùng mô hình xem lại/đọc sau khi kiểm `(assignment.classroom.teacher_id == actor.id)` và nguồn gốc lượt/phiên khớp. Không thêm đường `allow_any_user=True` rộng cho giáo viên, không điểm cuối lịch sử toàn học viên cho giáo viên.

- [x] **Bước 4: chạy hồi quy riêng tư/chấm**

Chạy: `cd backend && uv run pytest tests/test_teacher_assignment_results.py tests/test_writing_attempts.py tests/test_attempt_scoring_history.py -q`

Kỳ vọng: PASS.

- [x] **Bước 5: commit**

```bash
git add backend/app/services/classroom_results.py backend/app/schemas/classrooms.py backend/app/api/v1/classrooms.py backend/tests/test_teacher_assignment_results.py
git commit -m "Add read-only teacher assignment results"
```

---

### Tác vụ 7: UX frontend tối thiểu cho vai trò, lớp, kiểm duyệt, Builder, thông báo

**Tệp:**
- Sửa: `frontend/src/lib/api/auth.ts`
- Sửa: `frontend/src/lib/api/admin.ts`
- Sửa: `frontend/src/lib/api/tests.ts`
- Tạo: `frontend/src/lib/api/classrooms.ts`
- Tạo: `frontend/src/lib/api/content-governance.ts`
- Tạo: `frontend/src/lib/api/notifications.ts`
- Sửa: `frontend/src/components/ui/global-header.tsx`
- Sửa: `frontend/src/components/ui/app-shell.tsx`
- Sửa: `frontend/src/lib/i18n/translations.ts`
- Sửa: `frontend/src/features/auth/admin-user-actions.tsx`
- Tái dùng/tái cấu trúc `frontend/src/features/test-builder/*` hiện có để TEACHER vào Builder theo chủ mà không vào bảng ADMIN.
- Tạo trang giáo viên/trung lập tối thiểu dưới `frontend/src/app/teacher/` cho đề/lớp thuộc sở hữu, trang kiểm duyệt ADMIN dưới `frontend/src/app/admin/`, dùng thành phần chung khi hợp lý.
- Tạo: `frontend/src/features/classrooms/*`, thành phần tập trung cho chi tiết lớp, lời mời, bài giao, điều hướng kết quả chỉ đọc.
- Tạo: `frontend/src/features/notifications/notification-center.tsx`
- Kiểm thử: `frontend/tests/teacher-classroom-ui.test.tsx`
- Kiểm thử: `frontend/tests/notification-center.test.tsx`
- Kiểm hồi quy: khung xác thực/quản trị/i18n hiện có.

**Giao diện:**
- Lược đồ Zod xác thực nhận `USER | TEACHER | ADMIN`, dựng nhãn giáo viên bản địa hóa.
- Điều hướng giáo viên mở Builder/Lớp; ADMIN giữ Quản trị/Builder và thêm kiểm duyệt; USER không thấy soạn giáo viên/quản trị.
- Chuông đầu trang hiện số chưa đọc từ backend; mở bảng không đánh đọc hết; thao tác gọi điểm cuối lời mời thật.

- [x] **Bước 1: viết kiểm hợp đồng UI/API thất bại**

Bao phủ phân tích TEACHER; điều hướng theo vai trò; ADMIN nâng vai trò; hiển thị thao tác USER/TEACHER/ADMIN; link Builder chỉ chủ; Chấp nhận/Từ chối lời mời; danh sách/khởi bài giao; nhãn kết quả chỉ đọc giáo viên; duyệt/từ chối chỉ ADMIN; nguồn Chính thức/Cộng đồng trong thư viện; số chưa đọc/đọc một/hết; EN/VI mọi nhãn mới.

- [x] **Bước 2: chỉ chạy Vitest mới/liên quan, xác nhận thất bại**

Chạy: `cd frontend && npm test -- --run tests/teacher-classroom-ui.test.tsx tests/notification-center.test.tsx`

Kỳ vọng: FAIL vì thiếu vai trò/lược đồ/thành phần.

- [x] **Bước 3: triển khai UI tối thiểu đã duyệt**

Giữ bố cục đơn giản, không bắt đầu thiết kế lại ngoài phạm vi. Dùng Builder/xem lại hiện có, nhãn rõ `Official` so `Community · contributed by <teacher>`, trạng thái lớp lưu trữ/lịch sử chỉ đọc, không điều khiển thay đổi ở màn kết quả giáo viên.

- [x] **Bước 4: chạy kiểm frontend tập trung/kiểm kiểu**

Chạy kiểm mới và kiểm khung xác thực/quản trị/i18n sẵn nhỏ nhất, rồi `cd frontend && npm run typecheck`. Kỳ vọng: PASS.

- [x] **Bước 5: commit**

```bash
git add frontend/src frontend/tests
git commit -m "Add teacher classroom and moderation UI"
```

---

### Tác vụ 8: Tài liệu, quét hồi quy bảo mật, xác minh cuối

**Tệp:**
- Chỉ sửa `README.md` hoặc điểm vào tài liệu người dùng/phát triển hiện có ở chỗ thiết lập giáo viên/lớp.
- Tạo/cập nhật: `docs/teacher-classrooms.md` nếu chưa có tài liệu phù hợp.
- Chỉ cập nhật API/tài liệu/kiểm cho đổi hợp đồng có chủ đích phát hiện trong Tác vụ 1–7.

**Giao diện:**
- Ghi ba vai trò, ngữ nghĩa chủ/Chính thức-Cộng đồng, phạm vi kiểm duyệt, vòng đời lời mời, nguồn gốc/riêng tư bài giao, lưu trữ, mục ngoài v1 (không email/đồng giảng/thay điểm giáo viên/yêu cầu thông báo trực tiếp/giới hạn lượt).

- [x] **Bước 1: thêm/làm mới khẳng định hồi quy tập trung cho năm trọng tâm rà soát**

Mỗi trọng tâm phải có kiểm backend/frontend cụ thể từ tác vụ sở hữu; chỉ thêm khẳng định thiếu, không bộ kiểm trùng.

- [x] **Bước 2: chạy tập backend tập trung**

Chạy kiểm giáo viên/lớp/kiểm duyệt/kết quả mới, mục tiêu `test_admin.py`, `test_api_contract.py`, `test_asset_access.py`, `test_writing_builder.py`, kiểm lượt/TestSession tập trung, hồi quy chấm/lịch sử Writing. Kỳ vọng: PASS.

- [x] **Bước 3: chạy kiểm tĩnh**

Chạy Ruff tệp Python sửa, Vitest frontend liên quan, `npm run typecheck`, ESLint phạm vi liên quan nếu hỗ trợ, `git diff --check`. Không Playwright/E2E/trình duyệt/máy chủ dev/build trừ khi lỗi tập trung đòi hỏi.

- [x] **Bước 4: cập nhật tài liệu, xem diff cuối**

Xác nhận không tệp sinh/bộ nhớ đệm, không vô tình nới chấm Writing chỉ ADMIN, không đăng ký tự gán TEACHER, không truy vấn kết quả giáo viên chỉ phân quyền bằng `student_id + test_version_id`.

- [x] **Bước 5: commit và đẩy**

```bash
git add docs README.md backend frontend
git commit -m "Document teacher classroom workflows"
git status
git push origin main
```

Báo cáo cuối phải có SHA commit cuối, revision migration, đúng lệnh/số đạt tập trung, hành vi chủ/kiểm duyệt, lời mời/thông báo, nguồn gốc/riêng tư bài giao, tuyến UI thêm, mục ngoài v1 có chủ đích, xác nhận `origin/main` chứa triển khai và cây làm việc sạch.

## Bản ghi triển khai — 2026-10-11

Nền sau lấy/fast-forward main: `ad2201783bd39cd4127204d9d3d358a2506dc0c0`. Đầu Alembic thực ban đầu `20261011_0023`; đầu mới duy nhất `20261011_0024`.

Tác vụ 1–7 triển khai kiểm thất bại tập trung trước mã sản xuất. Backend nhóm miền (`20d09c9`), vai trò/chủ (`321d4e6`), kiểm duyệt/lớp/thông báo (`d07b6e5`), nguồn gốc bài giao/kết quả chỉ đọc (`6a29080`). Frontend/bản địa hóa ở `cec1213`; tài liệu theo commit cuối.

Lựa chọn triển khai trong kiến trúc duyệt:

- Lược đồ/dịch vụ/tuyến bài giao/kết quả ở tệp `classroom_assignments`, `classroom_results` tập trung, không phình dịch vụ lớp.
- Nguồn Full Mock chỉ ở `TestSession`; riêng/theo phạm vi ở `Attempt`. CHECK cơ sở dữ liệu từ chối lượt con có danh tính bài giao thứ hai.
- Chủ hủy dùng trạng thái bền `CANCELLED`, khác người xét từ chối. Trạng thái vòng đời phiên bản không đổi.
- OCR CLI nay cần `--owner-user-id ADMIN_UUID`; nhập không tạo nội dung dưới tác nhân bịa.
- Rà độc lập cuối nhận diện/kiểm lại hai sửa: Library/Practice cá nhân dùng điều kiện `public_only` máy chủ cả tác giả; danh sách kết quả/kiểm duyệt/thông báo lộ bản cũ qua phân trang. Số Builder tổng quan ADMIN giữ nghĩa cũ.

Năm trọng tâm được ghim bằng kiểm cụ thể:

| Trường hợp | Hồi quy |
| --- | --- |
| Chấp nhận lời mời đồng thời | `test_classrooms_and_notifications.py::test_concurrent_accept_creates_exactly_one_membership` |
| ID tài nguyên khác biết trước không bỏ quyền sở hữu | `test_teacher_roles_and_test_ownership.py`, `test_classrooms_and_notifications.py::test_other_teacher_cannot_manage_members_invites_or_known_classroom_ids`, `test_teacher_assignment_results.py::test_result_paths_scope_assignment_classroom_and_student_without_cross_resource_leaks` |
| Thu hồi PUBLIC giữ phê duyệt CLASSROOM độc lập | `test_classroom_assignments.py::test_revoking_public_keeps_classroom_starts_until_final_approval_is_revoked` |
| Duyệt v2 giữ lịch sử v1 đóng băng | `test_test_version_moderation.py::test_classroom_v2_replaces_public_v1_and_preserves_attempt_history` |
| Xác thực lặp chỉ gắn lời mời một lần, không tự tham gia | `test_classrooms_and_notifications.py::test_future_auth_binds_pending_email_once_without_auto_join` |

Lệnh tập trung cuối tái hiện trong [teacher-classrooms.md](../../teacher-classrooms.md#focused-verification). Kết quả trên cây mã cuối:

- Backend: **355 đạt** trên 27 tệp chịu ảnh hưởng, không lỗi/cảnh báo.
- Frontend: **269 đạt** trên 20 tệp chịu ảnh hưởng.
- `npm run typecheck`: đạt.
- Ruff kiểm mã/định dạng: đạt toàn bộ **57** tệp Python mới/sửa.
- ESLint có mục tiêu: đạt toàn bộ **75** tệp TS/TSX mới/sửa.
- Nâng DB mới từ 0, hạ khi miền rỗng về `20261011_0023`, nâng lại: đạt, một đầu Alembic. Kiểm tập trung cũng xác nhận từ chối hạ giữ nội dung nguồn giáo viên sau khi chủ đổi vai trò.
- Kiểm khoảng trắng diff cây/vùng chờ đạt trước commit. SHA từ xa cuối/trạng thái sạch được kiểm sau đẩy và báo người dùng.

Không chạy trình duyệt, Playwright/E2E, máy chủ dev, build, mô hình/GPU trực tiếp, Modal hoặc triển khai. Nội dung kiểm hư cấu, không thêm phụ thuộc. Rà độc lập cuối không còn phát hiện Critical/Important sau hai sửa.
