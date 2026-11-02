# Báo cáo backend: Admin ở vai trò quan sát — 2026-10-27

> **Kiểm toán tài liệu: HISTORICAL.** Tham khảo lịch sử, không phải hợp đồng hiện hành.
> Mục đích: báo cáo backend về vai trò quan sát của Admin — 2026-10-27. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/classrooms.md); [kiểm toán và giới hạn](../../DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong đợt kiểm toán này.

## Nguyên nhân gốc

- `resolve_capabilities()` chỉ trừ một số ít quyền thay đổi khỏi `ALL`, khiến quản trị viên vẫn có quyền quản lý lớp, thành viên và sửa điểm cuối.
- `ClassroomAssignmentService.create()` bỏ qua rõ ràng việc phân quyền giao bài cho quản trị viên.
- `AccessPolicy.require_classroom_manage()` trả về sớm đối với quản trị viên.
- `ClassroomService.restore()` yêu cầu quyền kiểm duyệt Admin toàn cục thay vì quyền sở hữu lớp.
- `GradingPolicy` cấp cờ chấm điểm cuối của lớp cho quản trị viên, chấp nhận chấm cuối lớp qua điểm cuối Writing/Speaking cá nhân.
- Thao tác người tham gia có thể tin tư cách thành viên lịch sử hoặc quyền sở hữu lượt làm bài. Vì vậy Admin từng ghi danh vẫn có thể bình luận, rời lớp/trả lời lời mời, hoàn tất mục tài nguyên trong kế hoạch, bắt đầu bài giao hoặc sửa lượt lớp cũ, độc lập với quyền soạn nội dung.

## Triển khai

- Thêm `roster.view`, với danh sách quyền quan sát Admin rõ ràng: `roster.view`, `grades.view`, `analytics.view`. Vai trò Admin toàn cục ưu tiên hơn dòng chủ sở hữu/nhân sự lịch sử.
- Liệt kê danh sách lớp cần `roster.view`; mời và quản lý thành viên vẫn cần `members.manage`. Chủ lớp và đồng giảng được xem danh sách. Giữ quyền cơ bản/tùy chọn TA hiện có; không cấp thêm quyền quản lý thành viên cho TA.
- Khóa tác nhân thay đổi lớp nạp lại tài khoản rồi từ chối Admin bằng `CLASSROOM_OBSERVER_READ_ONLY` (HTTP 403). Ranh giới bao phủ cấu hình, vòng đời lớp, thành viên/phản hồi lời mời, nhân sự, nội dung/tài nguyên, chủ đề/thứ tự, bài đăng/bình luận, lịch/gia hạn, chính sách chọn điểm và kế hoạch học tập.
- Tạo lớp giữ kiểm tra chỉ giáo viên hiện có. Gắn lời mời tự động trong xác thực được giữ nguyên đường xử lý trước; không chấp nhận lời mời hoặc tạo thành viên.
- Bỏ lối Admin vượt phân quyền tạo bài giao/quản lý lớp. Giữ kiểm quyền lưu trữ/khôi phục/xóa bài giao và bảo vệ lịch sử hiện có.
- Khôi phục lớp nay cần `classroom.manage`, nghĩa là giáo viên chủ đang hoạt động; đồng giảng và Admin không khôi phục được. Giữ kiểm chủ hoạt động và khóa vòng đời.
- Chấm cuối lớp từ chối Admin trước khi ghi, gồm tuyến cá nhân và nguồn gốc bài giao ở phiên Full Mock cha. Cờ chấm lớp của Admin luôn false, kể cả khi truyền `assignment_authorized=True`. Giữ quyền chấm cấp nền tảng riêng cho lượt cá nhân.
- Thêm chốt thay đổi lượt lớp cho Admin từng ghi danh. Chốt nhận nguồn gốc bài giao trực tiếp hoặc qua phiên cha và nạp lại tài khoản tác nhân. Áp dụng khi khóa thao tác vòng đời Attempt/Full Mock, vận hành/tệp âm thanh/khôi phục Speaking, xóa lịch sử lượt riêng, tạo/hủy/tiếp nhận kết quả Writing AI và phân quyền thay đổi bản chép lời/AI Speaking. Luyện cá nhân và luồng học viên/giáo viên thường tiếp tục qua chính sách hiện có.
- Rà soát bổ sung: liệt kê/lấy/ảnh chụp Writing AI có thể khôi phục lượt quá hạn trong khi đọc. Nay khôi phục kiểm nguồn gốc lớp trước khi lưu trạng thái lỗi/sự kiện; Admin quan sát lớp nhận lượt đã lưu mà không thay đổi. Giữ khôi phục cho học viên lớp và lượt cá nhân thường.
- Số thành viên lớp hoạt động nay nối vai trò tài khoản, loại dòng thành viên Admin cũ. Giáo viên thường ghi danh làm học viên vẫn được tính.
- Đọc nguồn đã cũ của AI/bản chép lời Speaking vốn dựng DTO lỗi mà không đổi trạng thái lưu; kiểm tập trung nay xác minh cả hai đường.

## Kiểm toán thao tác thay đổi

| Miền | Cách thực thi |
| --- | --- |
| Tạo lớp | Chốt vai trò chỉ giáo viên |
| Cấu hình/lưu trữ/khôi phục | Nạp lại tác nhân thay đổi lớp; kiểm chủ / `classroom.manage` |
| Mời/hủy/xóa/rời/chấp nhận/từ chối thành viên | Chốt thay đổi chung; kiểm quyền/người nhận hiện có |
| Mời/đổi/thu hồi/trả lời nhân sự | Chốt tác nhân thay đổi lớp chung; quy tắc quyền/điều kiện nhân sự hiện có |
| Chủ đề/tài nguyên/tệp/vị trí/thứ tự/gỡ | Chốt thay đổi chung `ContentAccess`; quyền nội dung/bài giao hiện có |
| Thông báo/thảo luận/xuất bản/lưu trữ/ghim/xóa | Chốt thay đổi nội dung chung |
| Tạo/sửa/xóa/kiểm duyệt bình luận | Chốt chung và kiểm người tham gia rõ ràng |
| Tạo/lưu trữ/khôi phục/xóa bài giao | Kiểm quyền bài giao rõ; bảo vệ lịch sử hiện có |
| Lịch bài giao/gia hạn cá nhân | Chốt chung và quyền bài giao/gia hạn |
| Chính sách chọn điểm sổ điểm | Chốt chung và quyền bài giao |
| Điểm cuối Writing/Speaking, tuyến cá nhân và theo phạm vi | `GradingPolicy` theo nguồn gốc; từ chối Admin |
| Tạo/cập nhật kế hoạch học/hoàn tất tài nguyên | Chốt chung, quy tắc kế hoạch/học viên hiện có |
| Khởi tạo bài giao, mô-đun và Full Mock | Chốt người tham gia với tài khoản mới nạp trong giao dịch vòng đời |
| Lượt Admin cũ hiện có | Chốt nguồn gốc khi nạp để thay đổi có khóa; tuyến xem lại chỉ đọc thường vẫn dùng |
| Tạo/hủy chấm AI/chép lời và tiếp nhận kết quả luyện tập | Chốt nguồn gốc khi phân quyền thay đổi lượt |
| Quản trị tài khoản/kiểm duyệt đề toàn cục | Không đổi; không kế thừa quyền lớp từ các chính sách này |

## Tệp được worker phân quyền backend thay đổi

Dịch vụ sản xuất:

- `backend/app/services/classroom_capabilities.py`
- `backend/app/services/access_policy.py`
- `backend/app/services/classrooms.py`
- `backend/app/services/classroom_content_access.py`
- `backend/app/services/classroom_assignments.py`
- `backend/app/services/grading_policy.py`
- `backend/app/services/attempts.py`
- `backend/app/services/test_sessions.py`
- `backend/app/services/speaking_attempts.py`
- `backend/app/services/speaking_transcript.py`
- `backend/app/services/writing_ai.py`
- `backend/app/services/writing_ai_practice_feedback.py`

Kiểm thử:

- Thêm `backend/tests/test_classroom_admin_observer_unit.py`
- Thêm `backend/tests/test_classroom_admin_observer_rest.py`
- Thêm `backend/tests/test_classroom_observer_ai_reads.py`
- Cập nhật kỳ vọng mã lỗi Admin cũ trong `backend/tests/test_classroom_classwork_unit.py`
- Cập nhật kỳ vọng khôi phục của chủ / từ chối Admin trong `backend/tests/test_classrooms_and_notifications.py`
- Cập nhật kỳ vọng cũ cho Admin chấm cuối lớp qua tuyến cá nhân trong `backend/tests/test_subjective_grading.py`
- Mở rộng đối tượng thay thế cơ sở dữ liệu trong `backend/tests/test_writing_ai_observer_lifecycle.py` để nạp lượt cá nhân theo chủ, khớp phụ thuộc phân quyền nguồn gốc mới; hành vi worker/SSE/hủy thực vẫn được kiểm.

Công việc API/lược đồ/repository danh bạ Admin thuộc tác nhân điều phối chính, ngoài quyền sở hữu thay đổi này.

## Bằng chứng xác minh

Đã đọc `backend/tests/conftest.py` bắt buộc trước. Tệp đọc `DATABASE_URL` cấu hình, xử lý lược đồ trong giao dịch chỉ hoàn tác. Phiên này không có `TEST_DATABASE_URL`, nên không chạy fixture tích hợp PostgreSQL, không đặt lại, migration hoặc chạm cơ sở dữ liệu.

Bằng chứng giai đoạn RED:

- Tệp đơn vị phân quyền mới ban đầu: 12 thất bại, 2 đạt, bộc lộ quyền thay đổi của Admin, bỏ chính sách chủ, bình luận bằng thành viên cũ, điểm vào thay đổi người tham gia, nguồn gốc chấm cá nhân, khởi tạo bài giao, khôi phục của chủ.
- Kiểm bổ sung lối vượt tạo bài giao: thất bại vì không phát lỗi phân quyền.
- Kiểm bộ máy lượt cũ: 3 thất bại vì bộ nạp Attempt, Full Mock, Speaking cho Admin ghi lớp.
- Kiểm tạo/tiếp nhận AI cũ: 3 thất bại vì đi tới kiểm vòng đời/phạm vi thay vì từ chối quyền.
- Hồi quy khôi phục khi đọc: 6 ca Admin lớp liệt kê/lấy/ảnh chụp thất bại vì đọc viết lại lượt quá hạn; 9 ca học viên/cá nhân thường đã đạt. Hồi quy SQL thành viên hoạt động thất bại vì truy vấn đếm thành viên không loại Admin.

Lệnh tập trung cuối từ `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_classroom_observer_ai_reads.py tests/test_classroom_admin_observer_unit.py tests/test_classroom_admin_observer_rest.py tests/test_classroom_classwork_unit.py tests/test_classroom_archive_unit.py tests/test_writing_ai_observer_lifecycle.py -q
```

Kết quả sau rà soát bổ sung: **167 đạt trong 12.87 giây**.

Ma trận REST mới thực thi 51 yêu cầu soạn tay qua router/dịch vụ FastAPI thật với đối tượng thay thế tại ranh giới cơ sở dữ liệu. Bao phủ cấu hình/vòng đời, thành viên/nhân sự, bài giao, thao tác lưu trữ được bảo vệ, chủ đề/tài nguyên/thứ tự, thông báo/bình luận, lịch/gia hạn, chính sách điểm, kế hoạch học và điểm cuối Writing/Speaking cá nhân/theo phạm vi. Mọi yêu cầu trả 403, ảnh chụp dòng ORM hiện có không đổi, không có add/flush/delete/execute.

Ca đơn vị bao phủ ưu tiên vai trò Admin, cờ quan sát được phép, tách quyền xem danh sách, chủ giáo viên khôi phục, khả năng đồng giảng, quyền TA tùy chọn, cô lập học viên/giáo viên ngoài, nguồn gốc chấm trực tiếp/qua cha, sửa lượt cũ, giữ quyền chấm nền tảng cá nhân riêng.

17 ca AI phía đọc bao phủ Admin nguồn bài giao trực tiếp/qua cha, khôi phục học viên lớp, khôi phục cá nhân Admin/học viên qua liệt kê/lấy/ảnh chụp, cô lập DTO nguồn cũ của AI/bản chép lời Speaking. Kiểm vòng đời worker/SSE/khôi phục/hủy Writing AI hiện có cũng đạt.

Ruff đúng phạm vi chạy trên đủ 19 tệp Python thuộc sở hữu: **mọi kiểm tra đạt**. `git diff --check` đúng phạm vi đạt, chỉ có thông báo kết thúc dòng của Git. Không chạy trình duyệt, máy chủ, bản dựng sản xuất, tiến trình thường trực, toàn bộ bộ kiểm hoặc tích hợp PostgreSQL.

## Giới hạn xác minh còn lại

- Khẳng định REST không ghi dùng đối tượng thay thế có kiểm soát ở ranh giới DB; chưa chạy hoàn tác/đếm dòng/cạnh tranh PostgreSQL thật vì chưa có DB kiểm cô lập được xác nhận.
- Chưa chạy hai tệp tích hợp PostgreSQL hiện có đã cập nhật.
- Chốt lượt chung thêm đọc tài khoản mới cho thay đổi lượt lớp, tra nguồn cha cho lượt Full Mock. Khôi phục Writing AI quá hạn còn nạp lại lượt làm bài trước mọi ghi trạng thái. Chưa chạy kiểm tích hợp số truy vấn/cạnh tranh.
- Kiểm toán cuối phát hiện hủy Writing AI vẫn có thể tin quyền chủ cũ. Hồi quy riêng thất bại trước khi thêm cùng chốt nguồn gốc; nay hủy cũng từ chối Admin lớp.
- Worker này không commit hoặc đẩy mã.
