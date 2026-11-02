# Thiết kế giáo viên, lớp học, quản trị nội dung và thông báo

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Thiết kế giáo viên, lớp học, quản trị nội dung và thông báo. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Trạng thái

Thiết kế đã được thống nhất trong trao đổi, ghi lại để lập kế hoạch triển khai. Chủ động hoãn bố cục frontend chi tiết; đặc tả này chốt ngữ nghĩa sản phẩm, ranh giới phân quyền, quy tắc lưu trữ, luồng và hành vi giao diện tối thiểu nhất quán cho v1.

## Mục tiêu

Mở rộng nền tảng IELTS từ USER/ADMIN thành hệ thống ba vai trò với tài khoản TEACHER, đề thuộc sở hữu giáo viên, thành viên và bài giao lớp, xuất bản lớp/công khai có kiểm duyệt, thông báo từng người và quyền giáo viên chỉ đọc bài nộp học viên bắt nguồn từ bài giao.

Tính năng phải giữ ngữ nghĩa chấm chính thức/thủ công, lượt làm/lịch sử, hành vi USER hiện tại ngoài lớp và tham chiếu phiên bản đề hiện có.

## Quyết định sản phẩm

- Vai trò: `USER`, `TEACHER`, `ADMIN`.
- Đăng ký công khai luôn tạo `USER`; chỉ ADMIN được nâng `USER -> TEACHER`.
- `TEACHER` giữ khả năng USER thường và thêm khả năng giáo viên; không phải mô hình tài khoản riêng.
- ADMIN chỉ được hạ `TEACHER -> USER` sau giải quyết tài nguyên giáo viên hoạt động và kiểm duyệt chờ. ADMIN có thể lưu trữ/vô hiệu hóa tài nguyên trước.
- Đề giáo viên tạo vẫn thuộc giáo viên sau phê duyệt/đóng góp công khai.
- Đề ADMIN tạo đã xuất bản là chính thức/toàn cục. Đề giáo viên được duyệt PUBLIC là nội dung cộng đồng/đóng góp có ghi công giáo viên.
- Mọi phiên bản giáo viên tạo phải được ADMIN duyệt trước người khác sử dụng, kể cả chỉ trong lớp.
- Kiểm duyệt theo phiên bản nội dung, không theo lớp.
- `CLASSROOM` và `PUBLIC` là phạm vi kiểm duyệt riêng. Duyệt PUBLIC bao hàm đủ điều kiện lớp; duyệt CLASSROOM không bao hàm công khai.
- Phiên bản giáo viên đã xuất bản/duyệt bất biến. Sửa cần nháp/phiên bản mới và kiểm duyệt mới.
- Mỗi lớp v1 có đúng một giáo viên chủ sở hữu; không đồng giảng viên hoặc chuyển quyền sở hữu.
- Giáo viên mời qua email; lời mời có thể tồn tại trước khi email có tài khoản.
- V1 chỉ thông báo trong ứng dụng; không gửi email.
- Học viên chủ động Accept hoặc Decline lời mời; không tự tham gia.
- `ClassroomAssignment` là đối tượng chia sẻ lớp và nguồn gốc lượt làm.
- Học viên được làm lại bài giao; v1 không giới hạn một lượt ở cơ sở dữ liệu.
- Giáo viên được xem đầy đủ bài nộp bắt nguồn bài giao ở chế độ chỉ đọc, tuyệt đối không luyện cá nhân không liên quan.
- Lớp/tài nguyên đã lưu trữ giữ lịch sử học tập chỉ đọc và tắt hoạt động tương lai thay vì xóa dữ liệu.
- Thông báo là tài nguyên nền tảng chung, tuyệt đối không là token phân quyền.

## Ràng buộc kiến trúc hiện tại

Kho mã hiện có vai trò USER/ADMIN; tạo/sửa/xuất bản đề phần lớn chỉ ADMIN. `Test` chưa có người tạo/chủ sở hữu. `TestVersion` dùng `DRAFT`, `PUBLISHED`, `ARCHIVED`, có ràng buộc cơ sở dữ liệu một nháp và một phiên bản xuất bản mỗi đề.

Thiết kế giữ vòng đời nội dung đó và thêm quyền sở hữu, kiểm duyệt, truy cập lớp và nguồn gốc xung quanh. Không được mã hóa trạng thái kiểm duyệt vào `VersionStatus`.

## 1. Vai trò, quyền sở hữu và chính sách

### 1.1 Khả năng

`USER` được dùng đề chính thức/toàn cục, chấp nhận lời mời lớp, làm bài giao, quản lý lượt/lịch sử riêng và nhận thông báo.

`TEACHER` còn được tạo đề/nháp, chỉ sửa nội dung thuộc sở hữu còn cho sửa, gửi phiên bản của mình kiểm duyệt, tạo/quản lý lớp thuộc sở hữu, mời/gỡ học viên, tạo bài giao và xem kết quả bài giao chỉ đọc.

`ADMIN` giữ hành vi quản trị hiện có, thêm quản lý vai trò giáo viên, kiểm duyệt, lưu trữ/khôi phục lớp/tài nguyên toàn cục và ghi đè quản trị mà không âm thầm chuyển quyền sở hữu.

### 1.2 Quyền sở hữu đề

Mở rộng `Test` về mặt khái niệm:

```text
owner_user_id: UUID | null
origin: ADMIN | TEACHER
```

Quy tắc:
- đề ADMIN mới: `origin=ADMIN`, `owner_user_id=admin.id`;
- đề TEACHER mới: `origin=TEACHER`, `owner_user_id=teacher.id`;
- đề chính thức cũ trước migration có thể dùng `origin=ADMIN`, `owner_user_id=NULL`; tuyệt đối không bịa người tạo lịch sử;
- mọi đề mới sau migration phải có chủ sở hữu;
- phê duyệt/xuất bản tuyệt đối không đổi chủ sở hữu/nguồn gốc.

### 1.3 Lớp chính sách

Không thay `AdminUser` bằng `CurrentUser` không hạn chế rồi rải kiểm tra vai trò. Thêm kiểm tra chính sách/dịch vụ backend tập trung tương đương:

```text
can_create_test(user)
can_edit_test(user, test, version)
can_manage_classroom(user, classroom)
can_assign_version(user, classroom, version)
can_read_version(user, version, context)
can_view_assignment_attempt(user, assignment, attempt)
can_submit_moderation(user, version, scope)
can_moderate(user)
```

Hiển thị frontend chỉ phục vụ UX; phân quyền backend là nguồn chuẩn.

### 1.4 Hạ vai trò

`TEACHER -> USER` phải xung đột khi còn tài nguyên hoạt động chỉ dành giáo viên, gồm lớp hoạt động, kiểm duyệt chờ hoặc tài nguyên mà chính sách yêu cầu ADMIN lưu trữ/vô hiệu hóa trước.

Nội dung lịch sử công khai đã duyệt có thể tiếp tục công khai có ghi công sau hạ vai trò khi tài nguyên giáo viên khác được giải quyết hợp lệ. Đổi vai trò tuyệt đối không xóa lan truyền lịch sử học tập.

## 2. Vòng đời nội dung và kiểm duyệt

### 2.1 VersionStatus tiếp tục là vòng đời nội dung

Giữ:

```text
DRAFT
PUBLISHED
ARCHIVED
```

`PUBLISHED` nghĩa là nội dung hoạt động bất biến dùng theo quy tắc quyền sở hữu/kiểm duyệt/truy cập; không mặc nhiên nghĩa là công khai toàn cục.

Phiên bản chính thức ADMIN tạo đã xuất bản tiếp tục hiển thị toàn cục theo hành vi chính thức hiện có.

### 2.2 Một phiên bản xuất bản hoạt động mỗi đề

Giữ bất biến hiện có tối đa một phiên bản `PUBLISHED` mỗi `Test`.

Khi nháp giáo viên mới hơn được duyệt CLASSROOM hoặc PUBLIC:
- phiên bản mới hơn trở thành phiên bản `PUBLISHED` hoạt động;
- phiên bản `PUBLISHED` hoạt động trước thành `ARCHIVED` trong cùng giao dịch;
- lượt/lịch sử cũ tiếp tục tham chiếu phiên bản lưu trữ không đổi.

Do kiểm duyệt theo phiên bản, quyền hiển thị/truy cập theo phê duyệt của phiên bản mới hoạt động. Ví dụ: v1 được duyệt PUBLIC và v2 chỉ duyệt CLASSROOM thì v1 bị lưu trữ, đề ngừng công khai toàn cục đến khi chính v2 được duyệt PUBLIC. Hành vi thay thế rõ ràng này là chủ ý để tránh nhiều phiên bản xuất bản cùng hoạt động.

### 2.3 Bản ghi kiểm duyệt

Thêm thực thể kiểm toán riêng:

```text
TestVersionModeration
- id
- test_version_id
- scope: CLASSROOM | PUBLIC
- status: PENDING | APPROVED | REJECTED | REVOKED
- submitted_by_user_id
- reviewed_by_user_id nullable
- submit_note nullable
- review_note nullable
- submitted_at
- reviewed_at nullable
- revoked_at nullable
- revoked_by_user_id nullable
- revoke_reason nullable
```

Mỗi lần gửi tạo hàng mới; không ghi đè yêu cầu lịch sử.

Quy tắc:
- tối đa một yêu cầu `PENDING` mỗi `(test_version_id, scope)`;
- bất kỳ kiểm duyệt đang chờ nào cũng khóa nội dung phiên bản;
- giáo viên chủ sở hữu được hủy yêu cầu PENDING của mình; nếu không còn yêu cầu chờ khác, nháp được sửa lại;
- duyệt/từ chối/thu hồi phải an toàn đồng thời và chỉ hợp lệ từ trạng thái trước được phép.

### 2.4 Ngữ nghĩa phạm vi

`CLASSROOM APPROVED`:
- phiên bản là/tiếp tục `PUBLISHED` hoạt động và bất biến;
- đủ điều kiện bài giao lớp;
- không hiện trong Community Library toàn cục.

`PUBLIC APPROVED`:
- phiên bản là/tiếp tục `PUBLISHED` hoạt động và bất biến;
- hiện toàn hệ thống là nội dung cộng đồng/đóng góp;
- đồng thời đủ điều kiện bài giao lớp.

Giáo viên có thể gửi thẳng PUBLIC không cần duyệt lớp trước, hoặc gửi cùng phiên bản đã duyệt CLASSROOM để duyệt PUBLIC sau.

### 2.5 Thu hồi

Thu hồi PUBLIC gỡ hiển thị toàn cục/cộng đồng tương lai nhưng giữ lượt/lịch sử. Có thể còn đủ điều kiện lớp nếu duyệt CLASSROOM còn hoạt động.

Thu hồi CLASSROOM ngăn giao/bắt đầu trong lớp tương lai chỉ phụ thuộc duyệt CLASSROOM; nếu duyệt PUBLIC còn hoạt động thì vẫn đủ điều kiện lớp qua PUBLIC.

Kiểm duyệt đổi truy cập tương lai, tuyệt đối không đổi lịch sử học tập.

## 3. Miền lớp học

### 3.1 Lớp học

```text
Classroom
- id
- teacher_id
- name
- description nullable
- status: ACTIVE | ARCHIVED
- archived_at nullable
- created_at
- updated_at
```

Quy tắc:
- đúng một chủ sở hữu TEACHER hoạt động;
- không xóa cứng ở v1;
- giáo viên chủ sở hữu được lưu trữ lớp của mình;
- ADMIN được lưu trữ/khôi phục mọi lớp;
- lớp lưu trữ là lịch sử/chỉ đọc: không lời mời, thành viên, bài giao hoặc bắt đầu bài giao mới; lịch sử hiện có vẫn đọc theo quyền bình thường.

### 3.2 Lời mời

```text
ClassroomInvitation
- id
- classroom_id
- invited_email
- invited_email_normalized
- invited_user_id nullable
- invited_by_user_id
- status: PENDING | ACCEPTED | DECLINED | CANCELLED
- created_at
- responded_at nullable
- cancelled_at nullable
```

Quy tắc:
- chuẩn hóa email đúng như tra cứu xác thực/người dùng;
- không có lời mời chờ trùng cho cùng lớp/email;
- không mời thành viên đã hoạt động;
- ngăn mời chủ sở hữu vào chính lớp của họ;
- nếu tài khoản tồn tại, gắn `invited_user_id` và tạo thông báo trong ứng dụng;
- nếu tài khoản chưa tồn tại, chỉ lưu theo email chuẩn hóa;
- khi đăng ký/đăng nhập khớp, gắn lời mời chờ và tạo thông báo thiếu theo cách lũy đẳng;
- tuyệt đối không tự chấp nhận hoặc tự tham gia.

Chấp nhận nằm trong giao dịch: khóa lời mời, xác thực PENDING, người nhận/email, lớp ACTIVE và chưa có thành viên hoạt động; tạo thành viên; đánh dấu ACCEPTED; thông báo giáo viên; cam kết một lần.

### 3.3 Tư cách thành viên

```text
ClassroomMembership
- id
- classroom_id
- user_id
- joined_at
- left_at nullable
- removed_by_user_id nullable
```

`left_at IS NULL` nghĩa là đang hoạt động. Tuyệt đối không xóa lịch sử thành viên. Tối đa một tư cách thành viên hoạt động mỗi lớp/người dùng. Tham gia lại về sau tạo giai đoạn thành viên mới. Học viên được tự rời; giáo viên được gỡ; cả hai không xóa bài nộp cũ.

TEACHER vẫn là người dùng bình thường và có thể làm học viên/thành viên trong lớp giáo viên khác.

## 4. Bài giao và nguồn gốc lượt làm

### 4.1 ClassroomAssignment

```text
ClassroomAssignment
- id
- classroom_id
- test_version_id
- created_by_user_id
- title nullable
- note nullable
- status: ACTIVE | ARCHIVED
- created_at
- archived_at nullable
```

Giáo viên được giao khi:
- lớp ACTIVE thuộc giáo viên hiện tại;
- phiên bản `PUBLISHED` đang hoạt động/bất biến;
- phiên bản thuộc giáo viên với duyệt CLASSROOM hoặc PUBLIC còn hiệu lực, hoặc là phiên bản chính thức ADMIN/hệ thống đã xuất bản;
- do đó đề chính thức ADMIN/hệ thống được giao không cần kiểm duyệt giáo viên vì đã là nội dung chính thức.

Không cần kiểm duyệt bổ sung cho từng lớp.

### 4.2 Nguồn gốc

Hoạt động bắt đầu từ bài giao phải mang nguồn gốc bài giao bền vững chỉ do logic bắt đầu bài giao backend tạo.

Lượt độc lập/mô-đun cần tham chiếu bài giao nguồn khi áp dụng. Với Full Mock, nguồn gốc có thể nằm trên `TestSession` và được lượt con kế thừa, hoặc chỉ sao chép nếu mẫu truy vấn hiện có yêu cầu. Lập kế hoạch phải chọn mô hình ít trùng nhất vẫn giữ điều kiện bảo mật không mơ hồ.

Trình duyệt không được gắn lượt hiện có tùy ý vào lớp sau khi tạo.

### 4.3 Làm lại

Cho phép nhiều lượt/phiên mỗi học viên mỗi bài giao. Giữ đầy đủ lịch sử; tổng hợp có thể nhấn lượt mới nhất/hiện tại.

### 4.4 Ranh giới quyền xem của giáo viên

Giáo viên chỉ được đọc lượt khi bắt nguồn từ bài giao thuộc lớp của họ:

```text
attempt originates from assignment
AND assignment.classroom.teacher_id == current_teacher.id
```

Tuyệt đối không phân quyền chỉ từ `student_id + test_version_id`. Luyện cá nhân cùng đề vẫn riêng tư. Bài nộp lịch sử bắt nguồn bài giao vẫn cho giáo viên đọc sau hết thành viên.

## 5. Giao diện kết quả giáo viên

Truy cập chỉ đọc có thể gồm:
- trạng thái/thời gian;
- câu trả lời Listening/Reading đã nộp, độ đúng, điểm/band;
- văn bản Writing đã nộp;
- kết quả/phản hồi Writing AI hiện có gắn với lượt đó tại nơi hợp đồng dữ liệu thường cho phép;
- điểm Writing chính thức/thủ công nếu đã có.

Giáo viên không được sửa câu trả lời, xóa lượt, đổi điểm chính thức/thủ công, gọi thao tác chấm chỉ ADMIN hoặc xem luyện cá nhân không liên quan. Frontend ghi nhãn rõ xem lại lượt của giáo viên là chỉ đọc.

## 6. Phân hệ thông báo

Dùng mô hình thông báo chung từng người với dữ liệu sự kiện bản địa hóa được:

```text
Notification
- id
- user_id
- type
- payload_json
- entity_type
- entity_id
- read_at nullable
- created_at
```

`type + payload_json` là hợp đồng sự kiện bền vững; bản địa hóa EN/VI frontend hiển thị tiêu đề/thông điệp. Payload chỉ nên chứa metadata hiển thị an toàn cần cho trình bày (ví dụ tên hiển thị lớp/đề), không chứa trạng thái phân quyền hoặc bí mật.

Các loại ban đầu có thể gồm:
- `CLASSROOM_INVITED`;
- `CLASSROOM_INVITATION_ACCEPTED`;
- `CLASSROOM_INVITATION_DECLINED`;
- `TEST_CLASSROOM_APPROVED`;
- `TEST_CLASSROOM_REJECTED`;
- `TEST_PUBLIC_APPROVED`;
- `TEST_PUBLIC_REJECTED`;
- `CLASSROOM_ARCHIVED`.

Quy tắc:
- `read_at IS NULL` nghĩa là chưa đọc;
- đầu trang hiển thị số chưa đọc;
- mở bảng không đánh dấu tất cả đã đọc;
- hỗ trợ đánh dấu một và tất cả đã đọc;
- thao tác luôn tải và phân quyền thực thể đích thật;
- ID thông báo/thực thể tuyệt đối không cấp quyền;
- tạo thông báo lời mời khi đăng ký/đăng nhập có tính lũy đẳng;
- v1 không yêu cầu WebSocket/SSE chung; tải/tải lại đủ;
- v1 không gửi email.

## 7. Cấu trúc API/luồng

Tên tuyến cụ thể theo quy ước hiện tại, nhưng thao tác tài nguyên bắt buộc gồm:

### 7.1 Đề

Tái sử dụng tuyến Builder/đề hiện có.

`POST /tests`:
- ADMIN => đề chính thức thuộc sở hữu;
- TEACHER => đề thuộc giáo viên;
- USER => bị cấm.

Luồng sửa/tạo phiên bản/xóa/xác thực hiện có chuyển sang dựa chính sách tại nơi phù hợp. Thao tác giáo viên giới hạn theo chủ sở hữu và phiên bản được sửa; ADMIN giữ kiểm soát quản trị toàn cục.

### 7.2 Kiểm duyệt

Giáo viên:

```text
POST /test-versions/{version_id}/moderation-requests
POST /test-moderation-requests/{request_id}/cancel
```

ADMIN:

```text
GET  /admin/test-moderation-requests
GET  /admin/test-moderation-requests/{id}
POST /admin/test-moderation-requests/{id}/approve
POST /admin/test-moderation-requests/{id}/reject
POST /admin/test-moderation-requests/{id}/revoke  (or equivalent scoped revocation action)
```

Giao dịch phê duyệt xác thực trạng thái PENDING và phiên bản đích đã khóa, thay phiên bản hoạt động khi xuất bản lần đầu phiên bản mới hơn, ghi kết quả kiểm duyệt, tạo thông báo và cam kết nguyên tử.

### 7.3 Lớp học/thành viên

```text
GET  /classrooms
POST /classrooms
GET  /classrooms/{id}
PATCH /classrooms/{id}
POST /classrooms/{id}/archive
GET  /classrooms/{id}/members
POST /classrooms/{id}/members/{user_id}/remove
POST /classrooms/{id}/leave
```

ADMIN có khả năng lưu trữ/khôi phục toàn cục.

### 7.4 Lời mời

```text
POST /classrooms/{id}/invitations
POST /classroom-invitations/{id}/cancel
GET  /me/classroom-invitations
POST /classroom-invitations/{id}/accept
POST /classroom-invitations/{id}/decline
```

### 7.5 Bài giao/kết quả

```text
GET  /classrooms/{id}/assignments
POST /classrooms/{id}/assignments
GET  /classrooms/{id}/assignments/{assignment_id}
POST /classrooms/{id}/assignments/{assignment_id}/archive
GET  /me/classrooms/{id}/assignments
POST /classroom-assignments/{assignment_id}/start
GET  /classrooms/{classroom_id}/assignments/{assignment_id}/results
GET  /classrooms/{classroom_id}/assignments/{assignment_id}/students/{student_id}/attempts
```

Bắt đầu bài giao suy ra lớp, phiên bản đề, người dùng hiện tại, tư cách thành viên và nguồn gốc từ trạng thái bài giao phía máy chủ. Không tin ID quyền sở hữu/truy cập trình duyệt gửi khi có thể suy ra.

### 7.6 Thông báo

```text
GET  /notifications
GET  /notifications/unread-count
POST /notifications/{id}/read
POST /notifications/read-all
```

## 8. Đồng thời và giao dịch

Các thao tác này phải an toàn giao dịch và chống trùng/xung đột:
- chấp nhận lời mời và tạo thành viên hoạt động;
- gửi/duyệt/từ chối/thu hồi kiểm duyệt;
- thay phiên bản đã xuất bản hoạt động;
- tạo bài giao;
- bắt đầu bài giao/tạo nguồn gốc;
- xác thực nâng/hạ vai trò giáo viên;
- lưu trữ/khôi phục lớp;
- tạo thông báo lũy đẳng cho lời mời chờ.

Nhấp đúp/yêu cầu đồng thời không được tạo thành viên trùng, kiểm duyệt chờ trùng, chuyển trạng thái xuất bản trùng hoặc thông báo trùng.

## 9. Lỗi miền

Dùng ngữ nghĩa miền rõ ràng, tên theo quy ước hiện có, gồm các mã tương đương:

```text
TEACHER_REQUIRED
TEST_OWNERSHIP_REQUIRED
VERSION_IMMUTABLE
MODERATION_ALREADY_PENDING
VERSION_NOT_CLASSROOM_APPROVED
VERSION_NOT_PUBLIC_APPROVED
CLASSROOM_NOT_FOUND
CLASSROOM_ARCHIVED
CLASSROOM_OWNERSHIP_REQUIRED
INVITATION_NOT_FOUND
INVITATION_ALREADY_RESOLVED
INVITATION_EMAIL_MISMATCH
ASSIGNMENT_NOT_ACCESSIBLE
ACTIVE_MEMBERSHIP_REQUIRED
TEACHER_HAS_ACTIVE_RESOURCES
```

## 10. Hành vi frontend tối thiểu; hoãn bố cục chi tiết

Triển khai phải cung cấp giao diện nhất quán cho:
- ADMIN nâng/hạ giáo viên với phản hồi xung đột;
- TEACHER dùng Builder hiện có cho đề thuộc sở hữu và thấy trạng thái sở hữu/kiểm duyệt;
- TEACHER quản lý lớp/thành viên/lời mời/bài giao và kết quả chỉ đọc;
- hàng đợi/chi tiết/thao tác kiểm duyệt ADMIN;
- USER Accept/Decline lời mời, xem lớp/bài giao và bắt đầu bài giao;
- Test Library phân biệt nội dung ADMIN/hệ thống chính thức với nội dung giáo viên cộng đồng công khai;
- chuông thông báo toàn cục với số chưa đọc/danh sách/thao tác đọc;
- tài nguyên lưu trữ hiển thị lịch sử chỉ đọc thay vì xóa;
- mọi thành phần giao diện mới hiển thị đều dùng bản địa hóa EN/VI hiện tại.

Bố cục bảng tổng quan chi tiết, phân cấp thị giác, thông báo thời gian thực, hạn, giới hạn lượt, đồng giảng viên, gửi email, chấm giáo viên và phân tách tổ chức ngoài v1.

## 11. Tương thích và migration

- Giữ luồng USER hiện tại và đề ADMIN/hệ thống chính thức.
- Giữ mọi tham chiếu/ID lượt làm/phiên/lịch sử hiện có.
- Đề cũ thiếu người tạo migration an toàn thành `origin=ADMIN`, thuộc hệ thống (`owner_user_id=NULL`); không bịa quyền sở hữu.
- Tham chiếu phiên bản đã xuất bản hiện có vẫn hợp lệ khi về sau phiên bản thành ARCHIVED sau phê duyệt mới hơn.
- Không ghi lại lượt lịch sử hoặc điểm Writing chính thức/thủ công.
- Giữ Builder/nhập/xuất/tài sản/phiên bản trừ nơi cần metadata sở hữu/truy cập.
- Rà soát nhập nháp/ZIP để đề nhập mới nhận chủ sở hữu/nguồn gốc từ người nhập đã xác thực, không âm thầm thành vô chủ.
- Migration enum PostgreSQL cho `UserRole.TEACHER` phải an toàn với dữ liệu hiện có.

## 12. Bất biến bảo mật

1. USER không được tự nâng lên TEACHER.
2. TEACHER không được sửa nội dung giáo viên khác.
3. TEACHER không được sửa phiên bản đã duyệt/xuất bản.
4. Người dùng khác không dùng được nội dung giáo viên trước khi có phê duyệt ADMIN phù hợp.
5. Duyệt CLASSROOM tuyệt đối không cấp hiển thị toàn cục.
6. Duyệt PUBLIC cấp hiển thị cộng đồng và đủ điều kiện lớp.
7. Giáo viên không được đọc luyện cá nhân học viên ngoài nguồn gốc bài giao.
8. Có thông báo tuyệt đối không cấp phân quyền.
9. Tài nguyên lưu trữ/thu hồi ngừng thao tác tương lai nhưng giữ lịch sử học tập.
10. Chính sách backend là nguồn chuẩn, không phải hiển thị frontend.

## 13. Nội dung rõ ràng ngoài phạm vi

- Gửi lời mời qua email.
- Đồng giảng viên/nhiều chủ sở hữu lớp.
- Chuyển quyền sở hữu lớp.
- Hạn bài giao.
- Giới hạn số lượt làm.
- Giáo viên chấm thủ công/sửa điểm Writing chính thức.
- Thông báo WebSocket/SSE thời gian thực chung.
- Phân vùng tổ chức/trường.
- Khóa học/gói thuê bao trả phí.
- Phân tích lớp đầy đủ ngoài xem trạng thái/kết quả bài giao.

## 14. Luồng nghiệm thu

```text
ADMIN promotes USER -> TEACHER
TEACHER creates test + draft
TEACHER submits CLASSROOM moderation
ADMIN approves
new version becomes active PUBLISHED/immutable and classroom-eligible
TEACHER creates classroom
TEACHER invites email
USER logs in and receives in-app invitation
USER accepts -> membership
TEACHER creates assignment from approved teacher version or official ADMIN version
USER starts through assignment
attempt/session stores assignment provenance
TEACHER sees full assignment result read-only
same teacher version may later be submitted for PUBLIC moderation
ADMIN approves PUBLIC
version appears globally as community content with teacher attribution
```

Mọi dữ liệu học tập lịch sử giữ ổn định nếu trạng thái thành viên, lớp, phê duyệt, xuất bản hoặc vai trò giáo viên đổi về sau.