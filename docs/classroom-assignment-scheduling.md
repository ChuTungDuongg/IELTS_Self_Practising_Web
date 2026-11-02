# Lập lịch bài giao lớp học (P2)

> **Kiểm toán tài liệu: CURRENT.** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Lập lịch bài giao lớp học (P2). Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../backend/app/services/assignment_scheduling.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/classrooms.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/đo hiệu năng bên dưới thuộc lần thực hiện gốc, không phải lần chạy lại trong đợt kiểm toán này.

P3 mở rộng quản lý lịch/gia hạn cho đồng giảng viên được phân quyền qua chính sách khả năng lớp học tập trung. Cài đặt/quản lý nhân sự của chủ sở hữu vẫn riêng; TA không được quyền thay đổi bài giao hoặc gia hạn. Cùng truy vấn quyết định lịch sử nay cung cấp dữ liệu cho Gradebook và phân tích lớp học. Xem [hợp đồng P3](classroom-gradebook.md).

P2 mở rộng bộ máy bài giao, TestVersion bất biến và IELTS gốc hiện có. Mã mới không đặt bộ đếm thời gian thi thứ hai hoặc đổi cách chấm. Không gian Classroom bổ sung Calendar dạng lịch công việc, tiến độ học viên dùng chung, chỉnh lịch, theo dõi và ngoại lệ cá nhân.

## Chính sách và quyết định lịch sử

`ClassroomAssignment` thêm `available_from`, `due_at`, `cutoff_at` có múi giờ, `max_attempts` cho phép null, `allow_late_submission` và `policy_revision`. Thời điểm được chuẩn hóa về UTC. Đầu vào phải có múi giờ; từ chối epoch dạng số và ngày không có múi giờ. Xác thực yêu cầu thời điểm mở phải trước hạn nộp/hạn đóng, hạn nộp không sau hạn đóng và giới hạn là số nguyên dương. Giới hạn biên soạn hiện tại là 10,000 lần bắt đầu cơ sở và 10,000 lần bổ sung.

Hàng cũ nhận khoảng thời gian/giới hạn null và `allow_late_submission=true`, giữ lịch không hạn chế ban đầu. Thời điểm mở tính bao gồm. Hạn nộp và hạn đóng tính bao gồm: hoàn thành đúng hạn nộp là đúng giờ; đúng hạn đóng có thể được chấp nhận muộn. Chặn bắt đầu mới sau hạn đóng. Khi không cho nộp muộn, bắt đầu và nộp sau hạn nộp bị chặn/không chấp nhận. Nếu không có hạn đóng, bài muộn có thể mở vô thời hạn.

Mỗi Attempt độc lập/tập trung được giao trực tiếp tiêu thụ một lần bắt đầu; mỗi TestSession được giao trực tiếp tiêu thụ một lần. Lượt con Full Mock không tiêu thụ thêm. Lượt bỏ dở/chưa hoàn thành vẫn tính; luyện tập cá nhân và bài giao khác không tính. Liên kết tiếp tục gốc không tạo lượt gốc mới. Kiểm tra chạy trong giao dịch tạo hiện có của AttemptService/TestSessionService dưới khóa người thực hiện, phiên bản nội dung, lớp, bài giao và thành viên. Đếm cùng tạo được tuần tự hóa, kể cả yêu cầu mô-đun/Full Mock cạnh tranh. Kiểm tra kiểm duyệt/quyền sở hữu hiện có tiếp tục là nguồn chuẩn.

Bài nộp khóa học thành công là Attempt gốc SUBMITTED/AUTO_SUBMITTED có mốc hoàn thành. INTERRUPTED/ABANDONED tuyệt đối không là bài nộp thành công. Full Mock yêu cầu cha COMPLETED, mốc hoàn thành, đủ mọi lượt con dự kiến và tất cả con SUBMITTED/AUTO_SUBMITTED; hoàn thành một mô-đun không thỏa bài giao. Chốt Speaking gốc và tự nộp theo thời gian dùng cùng quy tắc đọc. Lượt làm/kết quả IELTS vẫn có ngay khi việc chấp nhận cho khóa học thất bại.

Quyết định lịch sử được suy ra từ **dòng thời gian chính sách chuẩn hóa chỉ cho nối thêm**, thay vì đổi mã hoàn thành bộ máy hoặc thêm máy trạng thái thi song song. `classroom_assignment_policy_events` ghi người thực hiện, lý do, revision, `clock_timestamp()` máy chủ, lịch cơ sở và thay đổi ghi đè cá nhân. Trigger PostgreSQL từ chối UPDATE/DELETE các sự kiện này. Với mỗi lượt gốc thành công, SQL xác định sự kiện cơ sở và học viên cuối có hiệu lực không sau `finished_at` chuẩn của nó. Thay đổi sau không thể gán lại nhãn hoàn thành quá khứ, kể cả đổi chấp nhận muộn hoặc cấp/thu hồi gia hạn. Hoàn thành trước P2 không có sự kiện trước đó dùng chính sách cũ không hạn chế. Bài đang làm dùng thay đổi chính sách có hiệu lực trước khi hoàn thành. Chấp nhận lịch sử độc lập thời điểm đọc tiến độ lần đầu.

Mô hình đọc tiến độ ưu tiên bài nộp được chấp nhận mới nhất, rồi bài đang làm, rồi bài nộp thành công nhưng bị từ chối mới nhất. Kết quả thành công được chấp nhận vẫn thỏa yêu cầu khi lần thử khác chưa hoàn tất hoặc bị từ chối. `accepted`/`late` mô tả lần hoàn thành được chọn; hạn hiệu lực hiện tại hiển thị riêng. Trạng thái mở (SCHEDULED/OPEN/OVERDUE/CLOSED/ARCHIVED) độc lập trạng thái nộp. MISSED yêu cầu đã đóng và học viên thuộc nhóm đủ điều kiện. Thành viên hoạt động mới tham gia sau khi đóng không bị đánh dấu thiếu bài trước đó. Theo dõi gồm thành viên đang hoạt động cùng học viên cũ thực sự có lượt gốc của bài giao; loại thành viên cũ chưa có bài. Kết quả lịch sử giữ phân quyền theo bài giao hiện có.

## Gia hạn và phân quyền

`classroom_assignment_extensions` có một ngoại lệ hiện tại có thể sửa cho mỗi bài giao/học viên và giữ thông tin người tạo/cập nhật; mỗi thay đổi cũng nối thêm sự kiện bất biến. Boolean `override_due` / `override_cutoff` rõ ràng phân biệt kế thừa với gỡ hạn: false kế thừa, true với null gỡ hạn đó. Ghi đè khác null được kéo dài hạn cơ sở hữu hạn, tuyệt đối không rút ngắn hoặc thêm hạn mới khi cơ sở không hạn chế. Chính sách kết quả phải đúng thứ tự ngày. Số lần bắt đầu bổ sung cộng vào giới hạn hữu hạn và giữ chính sách vô hạn là vô hạn. Thu hồi đưa quyết định tương lai về cơ sở hiện tại; quyết định đã hoàn thành giữ lịch sử.

Chỉ TEACHER chủ sở hữu được sửa chính sách lịch mới hoặc quản lý ngoại lệ; ADMIN giữ quản lý bài giao/lớp học và giám sát đọc hiện có, gồm theo dõi/lịch sử. Học viên chỉ đọc tiến độ hiệu lực của mình. Chỉ cấp/cập nhật gia hạn cho học viên đang tham gia và hoạt động. Vẫn có thể thu hồi ngoại lệ đã tồn tại của thành viên cũ khi lớp/bài giao đang hoạt động. Lưu trữ lớp/bài giao chặn đổi chính sách mới và bắt đầu mới, đồng thời giữ bài gốc đang làm và lịch sử.

Cập nhật lịch yêu cầu `expected_revision`. Thay đổi gia hạn cũng tăng revision bài giao, nên biểu mẫu lịch lỗi thời nhận 409 thay vì ghi đè thay đổi. Lưu không đổi không tạo sự kiện kiểm toán hoặc thông báo. Nếu sửa cơ sở dự kiến làm ngoại lệ hiện có không hợp lệ, từ chối 422 cho đến khi chủ động điều chỉnh/thu hồi ngoại lệ đó. Không được patch `test_version_id`. Giao diện xác nhận đổi lịch và giải thích ảnh hưởng tới bài đang làm.

## Hợp đồng API

Mọi đường dẫn bên dưới nằm dưới `/api/v1/classrooms/{classroomId}` và dùng DTO rõ ràng.

| Đường dẫn | Hành vi |
| --- | --- |
| `POST /assignments` | Mở rộng tạo hiện có bằng trường lập lịch tùy chọn |
| `PATCH /assignments/{id}` | Chủ sở hữu cập nhật lịch/metadata, bắt buộc expected_revision, lý do tùy chọn; TestVersion bất biến |
| `GET /assignment-progress` | Tiến độ riêng của người dùng đã xác thực; limit 1–100, offset, danh sách assignment_ids tùy chọn tối đa 100 |
| `GET /assignments/{id}/progress` | Tiến độ một bài giao của người thực hiện |
| `GET /assignments/{id}/monitoring` | Nhóm học viên và tổng hợp cho chủ sở hữu/ADMIN, lọc trạng thái/tìm kiếm, limit 1–100 và offset |
| `GET /assignments/{id}/extensions` | Ngoại lệ hiện tại dành cho nhân sự |
| `PUT/DELETE /assignments/{id}/extensions/{studentId}` | Chủ sở hữu cấp/cập nhật hoặc thu hồi |
| `GET /assignments/{id}/schedule-history` | Trang kiểm toán nhân sự, limit 1–100 và offset |
| `GET /assignment-calendar` | start/end có múi giờ, khoảng nửa mở tối đa 93 ngày, limit 1–100 và offset |

Tiến độ gồm trạng thái mở/nộp, hạn/giới hạn hiệu lực, mức dùng lượt gốc, số lần bắt đầu còn lại, can_start và mã từ chối có cấu trúc, liên kết tiếp tục lượt gốc đang làm, liên kết hoàn thành/kết quả được chọn và chấp nhận. Không sao chép nội dung thi, điểm hoặc đáp án vào phản hồi tiến độ. Theo dõi tổng hợp bằng SQL và tải gia hạn theo lô cho trang được chọn; số truy vấn không tăng theo từng học viên. Sự kiện lịch là phép chiếu SQL bài giao lọc theo khoảng (mở/hạn nộp/hạn đóng), dùng ghi đè cá nhân trong chế độ học viên. Không có hàng sự kiện lịch sao chép.

## Thông báo và vận hành

Tạo bài giao, thay đổi lịch đáng kể và ngoại lệ cá nhân tạo sự kiện trong ứng dụng ở backend trong cùng giao dịch. Sự kiện gia hạn chỉ tới tài khoản học viên đang tham gia và hoạt động bị ảnh hưởng. Khóa sự kiện dựa UUID tái dùng ràng buộc duy nhất người nhận-sự kiện hiện có; cập nhật không đổi lặp lại không thông báo. Liên kết thông báo mở bài giao được phân quyền trong không gian hiện có.

Kho mã có worker AI bền vững nhưng không có bộ lập lịch định kỳ chung. Vì vậy nhắc hạn dùng **CLI chạy một lần** có giới hạn và tính lũy đẳng:

```powershell
# From backend/, using that deployment's normal DATABASE_URL/.env
.venv/Scripts/python.exe -m app.assignment_reminders --limit 100
```

Tác vụ xét lớp/bài giao đang hoạt động và tài khoản học viên đang tham gia, gửi nhắc sắp hạn trong 24 giờ trước hạn nộp hiệu lực và một nhắc quá hạn sau đó, bỏ qua yêu cầu đã thỏa. Tôn trọng hạn riêng, thu hồi gia hạn và học viên mới. Chống trùng gồm người nhận, bài giao, loại nhắc và thời điểm hạn hiệu lực; thử lại và chạy lặp không tạo sự kiện trùng. Dùng thời gian máy chủ và dịch vụ PostgreSQL/cục bộ hiện có. Báo cáo JSON gồm processed/emitted và batch_full; lô đầy nghĩa là có thể cần chạy tiếp để xử lý hết tồn đọng. Worker ở các môi trường triển khai khác nhau có thể chạy an toàn vì chèn sự kiện có tính lũy đẳng.

**Thay đổi này không tự triển khai nhắc định kỳ.** Cấu hình bộ lập lịch máy chủ sau triển khai. Trên Linux tại `/opt/bandpilot`, dùng `.env` backend hiện có, cài dòng crontab sau cho tài khoản ứng dụng (điều chỉnh đường dẫn cài đặt/nhật ký theo máy thực):

```cron
*/15 * * * * cd /opt/bandpilot/backend && .venv/bin/python -m app.assignment_reminders --limit 1000 >> /opt/bandpilot/assignment-reminders.log 2>&1
```

Trên Windows, cấu hình Task Scheduler lặp mỗi 15 phút, chương trình `C:\Users\Admin\IELTS_Self_Practising_Web\backend\.venv\Scripts\python.exe`, đối số `-m app.assignment_reminders --limit 1000` và **Start in** `C:\Users\Admin\IELTS_Self_Practising_Web\backend`. Dùng tài khoản/môi trường sở hữu cấu hình backend. Bật theo dõi thất bại tác vụ/thu thập nhật ký. Không thêm luồng nền FastAPI, Redis, Celery, email hoặc kết nối lịch ngoài. Thông báo bài giao tức thì và kiểm tra hạn/bắt đầu hoạt động không cần cấu hình bộ lập lịch.

## Migration và giới hạn

Alembic revision `20261027_0037` theo sau P1 `20261027_0036`. Nó thêm trường bài giao, bảng gia hạn/sự kiện, nhãn enum thông báo và chỉ mục ghép tiến độ lượt gốc. Không ghi lại dữ liệu đề/phiên bản/lượt làm bài hiện có. Hỗ trợ downgrade khi tính năng chưa có dữ liệu; downgrade từ chối lịch sử lập lịch hoặc chính sách đã cấu hình. Nhãn thông báo PostgreSQL được bổ sung vẫn còn sau downgrade theo quy ước hiện có.

Lịch công việc là danh sách có giới hạn thay vì lưới tháng. Đọc trạng thái không đồng bộ bộ đếm thi; tiếp tục bài gốc thực hiện đồng bộ bình thường của bộ máy. Phiên có mô-đun bỏ dở/gián đoạn được giữ và không thỏa yêu cầu nộp của khóa học. Mỗi trang cung cấp lần hoàn thành được chọn và liên kết giao diện kết quả/lịch sử hiện có cho lượt khác. Chạy nhắc định kỳ yêu cầu cấu hình máy chủ nêu trên. [Gradebook P3 và nhân sự theo phạm vi](classroom-gradebook.md) cùng [phân tích, đề xuất xác định và kế hoạch P4](classroom-learning-analytics.md) nay dựa trên cùng quyết định này. Điểm danh và đề xuất bằng AI vẫn ngoài phạm vi.

Xác minh dùng dữ liệu hư cấu, PostgreSQL cô lập, pytest/Vitest có trọng tâm và kiểm tra tĩnh. Không dùng trình duyệt, E2E, toàn bộ bộ kiểm thử, bản dựng production hoặc toàn bộ hệ thống phát triển; hành vi trực quan chưa được xác minh trên trình duyệt.

### Phạm vi đã xác minh (2026-10-27)

- Nâng cấp PostgreSQL mới qua 0037, hạ P2 rỗng về 0036 và nâng lại đều thành công. Cơ sở dữ liệu cục bộ đã cấu hình được nâng từ 0036 và xác minh tại `20261027_0037 (head)`.
- Backend có trọng tâm: **145 đạt**, bao gồm kiểm thử chính sách/lập lịch/vòng đời mới cùng bài giao lớp, thành viên/thông báo, Stream/Classwork/tài nguyên riêng tư P1 và phiên Full Mock gốc hiện có. Tranh chấp hai kết nối thật xác nhận giới hạn bắt đầu; đã thực thi tự nộp Reading tập trung gốc và hoàn thành Speaking. Trang theo dõi dùng số truy vấn cố định; lịch sử từ chối cập nhật trực tiếp cơ sở dữ liệu.
- Frontend có trọng tâm: **65 đạt** trên lập lịch bài giao, nội dung/API P1, điều khiển/API/phân trang giáo viên và trung tâm thông báo. TypeScript, ESLint/Ruff theo phạm vi và `git diff --check` giới hạn nhiệm vụ đều đạt.
- Kiểm tra nhanh CLI chạy một lần trên cơ sở dữ liệu kiểm thử cô lập trả báo cáo lô JSON thành công. Không cài bộ lập lịch máy chủ và không tuyên bố có gửi định kỳ tự động.
