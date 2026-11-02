# Giáo viên, lớp học và quản trị nội dung

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Giáo viên, lớp học và quản trị nội dung. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../backend/app/services/classroom_capabilities.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/classrooms.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Nhân sự và bảng điểm Gradebook (P3)

Đính chính theo chính sách hiện hành ngày 2026-11-02: ADMIN là observer chỉ đọc của lớp học, không quản lý thành viên/nội dung, archive/restore hoặc chấm điểm cuối của bài giao. Chủ lớp giữ quyền khôi phục; nhân sự khác theo capabilities được cấp. Các mô tả quyền ADMIN trong P1/v1 phía dưới là lịch sử, không dùng để cấp quyền mới. Xem [module hiện hành](modules/classrooms.md), [capability policy](../backend/app/services/classroom_capabilities.py) và [grading policy](../backend/app/services/grading_policy.py).

Lớp học nay xác định khả năng chủ sở hữu, đồng giảng viên và TA theo ngữ cảnh, tách biệt vai trò toàn cục. Lời mời nhân sự phải được chấp nhận; Gradebook dùng kết quả được chấp nhận chuẩn và điểm chủ quan chốt bởi con người, cùng hồ sơ học tập chỉ trong lớp và xuất CSV an toàn có giới hạn. Xem [hợp đồng nhân sự, Gradebook và UX/UI lớp học](classroom-gradebook.md). Mô tả chỉ chủ sở hữu của P1/P2 bên dưới ghi lại các giai đoạn gốc đó; ma trận khả năng trong hướng dẫn P3 chi phối thao tác chia sẻ hiện tại.

## Lập lịch bài giao và quản lý bài nộp (P2)

Bài giao nay hỗ trợ thời gian mở, ranh giới hạn nộp/hạn đóng tính bao gồm, chấp nhận muộn, giới hạn bắt đầu lượt gốc dùng chung, ngoại lệ cá nhân, tiến độ riêng tư học viên, theo dõi giáo viên có phân trang, lịch công việc lớp và thông báo bài giao trong ứng dụng. Bộ máy thi, chấm điểm và nguồn gốc phiên bản bất biến hiện có tiếp tục là nguồn chuẩn. Xem [hướng dẫn chính sách, API, migration và triển khai nhắc hạn P2](classroom-assignment-scheduling.md) để biết đầy đủ ngữ nghĩa. Thực thi chính sách tức thì và thông báo hoạt động khi backend chạy; nhắc định kỳ yêu cầu cấu hình bộ lập lịch máy chủ đã ghi tài liệu.

## Không gian Classroom 2.0 (P1)

Trang chi tiết dùng chung cho `/classrooms/{id}` và `/teacher/classrooms/{id}` nay tách **Stream**, **Classwork**, **Assignments** và **People**. Tạo, bắt đầu, nguồn gốc, kết quả bài giao và chấm con người/AI tư vấn hiện có vẫn thuộc thành phần/dịch vụ hiện có. Đầu trang lớp gồm tên hiển thị giáo viên và số thành viên hoạt động được phân quyền. Lớp đã lưu trữ giữ nội dung xuất bản đọc được và chỉ đọc.

### Nội dung và phân quyền

- Giáo viên chủ sở hữu biên soạn thông báo/thảo luận, phần và tài nguyên TEXT/LINK/FILE. Nội dung dùng `DRAFT`, `PUBLISHED` và `ARCHIVED`; nhân sự được xem bản nháp/lưu trữ. Học viên chỉ đọc nội dung đã xuất bản. Tài nguyên đã xuất bản trong phần chưa xuất bản vẫn bị ẩn, kể cả truy cập UUID trực tiếp và tệp.
- ADMIN giữ lưu trữ/khôi phục, quản lý và giám sát đọc lớp học hiện có, kể cả bản nháp. P1 chủ động **không** cấp ADMIN quyền tác giả hoặc kiểm duyệt nội dung học tập mới của giáo viên khác. Giáo viên khác không có quyền sở hữu. Tư cách thành viên lịch sử hiện có cho phép đọc nội dung xuất bản được giữ; bình luận yêu cầu thành viên hoạt động (hoặc giáo viên chủ sở hữu).
- Chuỗi bình luận phẳng phân trang bằng con trỏ, cũ trước. Tác giả được sửa/rút bình luận của mình; chủ sở hữu được kiểm duyệt người khác. Rút/kiểm duyệt giữ nội dung đã lưu và thời gian kiểm toán nhưng trả nội dung rỗng cho client. Bài đăng được lưu trữ thay vì xóa. Thảo luận khóa từ chối bình luận mới.
- Stream kết hợp bài đăng và hàng `ClassroomAssignment` chuẩn bằng SQL UNION có giới hạn, nên bài giao hiện có không cần điền dữ liệu hoặc vòng đời độc lập. Mục ghim đứng trước bảng tin thường mới nhất trước. Khóa con trỏ gồm trạng thái ghim, thời gian tạo, loại nội dung và UUID; thời gian hòa được phá xác định. Con trỏ gắn với lớp/bộ lọc. Như bảng tin phân trang theo khóa thông thường, ghim mục qua ranh giới con trỏ khi phân trang có thể đổi vị trí; làm mới bắt đầu lại chế độ xem.
- Markdown lưu dạng văn bản có giới hạn. Client hiển thị tập con nhỏ (đậm, nghiêng, danh sách và liên kết HTTP/HTTPS) thành node React; tuyệt đối không chèn HTML thô. URL tài nguyên yêu cầu địa chỉ HTTP/HTTPS tuyệt đối không nhúng thông tin xác thực.
- Lần xuất bản thông báo đầu tiên tạo thông báo theo người nhận cho tài khoản học viên đang tham gia/hoạt động trong cùng giao dịch. Chống trùng thông báo hiện có và mốc xuất bản đầu được giữ ngăn thông báo lặp sau sửa hoặc xuất bản lại. Thông báo không cấp quyền truy cập nội dung.

### Classwork có cấu trúc và thứ tự

Phần có UUID ổn định, vị trí rõ và trạng thái xuất bản độc lập. Mỗi mục tham chiếu đúng một tài nguyên hoặc bài giao hiện có. Khóa ngoại ghép ngăn đặt phần/tài nguyên/bài giao chéo lớp. Vị trí tài nguyên/bài giao là duy nhất; tham chiếu TestVersion của bài giao giữ nguyên. Bài giao hiện có chưa đặt vẫn nằm trong Assignments và nhóm Uncategorized của Classwork.

Khóa hàng lớp tuần tự hóa mọi ghi mới với lưu trữ và thay đổi thành viên. Mỗi sửa Classwork tăng `classrooms.content_revision`. Yêu cầu sắp lại cung cấp revision và toàn bộ thứ tự đích mong muốn; revision lỗi thời trả `409 CLASSWORK_CHANGED`. Máy chủ xác thực mọi định danh, chuẩn hóa vị trí và di chuyển tham chiếu nguyên tử. Điều khiển di chuyển bàn phím bổ sung kéo thả. Client làm mới sau ghi thành công và hiển thị lỗi, không giả vờ thành công.

### Tệp riêng tư

Tệp dùng lớp lưu trữ cục bộ hiện có dưới `storage/classroom-resources/`, với tên UUID được sinh. PostgreSQL lưu metadata và khóa lưu trữ riêng tư, tuyệt đối không lưu nhị phân. DTO công khai loại khóa lưu trữ và đường dẫn hệ thống tệp. Endpoint tệp kiểm tra lại thành viên/lịch sử lớp, xuất bản và quyền thấy phần chứa trên mỗi yêu cầu.

Tải lên giới hạn **20 MiB**, cho phép PDF, PNG, JPEG, WebP, văn bản thuần UTF-8 và DOCX. Từ chối tên tệp vượt thư mục/ký tự điều khiển, cặp MIME/phần mở rộng không hỗ trợ và chữ ký không khớp. Gói DOCX có giới hạn số mục/kích thước giải nén, từ chối macro và đường dẫn mục không an toàn. Không dùng dịch vụ lưu trữ ngoài mới. Giai đoạn tải tạm theo mẫu worker được shield hiện có; giao dịch gắn thất bại kiểm tra tham chiếu bền vững rồi xóa tệp không tham chiếu. Nếu mất cơ sở dữ liệu làm kết quả không thể xác định, giữ tệp và ghi lỗi bù trừ, tránh xóa tài nguyên có thể đã cam kết. Tệp tài nguyên lưu trữ được giữ cùng lịch sử.

Tải xuống gửi header private/no-store và nosniff. PDF/ảnh có thể xem nội tuyến qua endpoint xác thực; tài liệu hỗ trợ khác tải dưới dạng đính kèm. Liên kết ngoài mở với thuộc tính an toàn.

Trình xem tài nguyên lấy tệp riêng qua HTTP client biết làm mới hiện có trước khi tạo Blob URL tạm trong trình duyệt. Việc này giữ tải xuống hoạt động khi cookie truy cập ngắn hạn hết nhưng phiên đăng nhập còn hợp lệ. Hủy yêu cầu chờ và thu hồi Blob URL khi đóng trình xem.

### Cơ sở dữ liệu và endpoint

Revision **`20261027_0036`**, theo sau `20261013_0035`, thêm `classroom_sections`, `classroom_resources`, `classroom_content_items`, `classroom_posts`, `classroom_post_resources` và `classroom_comments`, cùng `classrooms.content_revision`, giá trị enum thông báo và khóa/chỉ mục hỗ trợ. Migration chỉ bổ sung, không ghi lại dữ liệu bài giao, lượt làm hoặc TestVersion hiện có. Downgrade từ chối khi giữ lịch sử không gian/thông báo; nhãn enum PostgreSQL bổ sung còn sau downgrade miền rỗng.

Nhóm endpoint mới dưới `/api/v1/classrooms/{id}`:

| Đường dẫn | Thao tác |
| --- | --- |
| `/feed` | GET trang con trỏ, `limit` có giới hạn, bộ lọc trạng thái tùy chọn chỉ cho nhân sự |
| `/posts`, `/posts/{postId}` | POST tạo; GET chi tiết; PATCH sửa/vòng đời/khóa |
| `/posts/{postId}/{publish,archive,pin}` | POST thay đổi xuất bản, lưu trữ và ghim |
| `/posts/{postId}/comments` | GET trang con trỏ; POST bình luận |
| `/comments/{commentId}` | PATCH bình luận của mình; DELETE rút/kiểm duyệt |
| `/classwork` | GET phần/tài nguyên/mục được phân quyền và revision |
| `/sections`, `/sections/{sectionId}`, `/sections/reorder` | GET/POST, PATCH, POST toàn bộ thứ tự phần |
| `/resources`, `/resources/{resourceId}` | GET/POST, GET/PATCH metadata nội dung |
| `/resources/upload`, `/resources/{resourceId}/file` | POST tải multipart; GET tệp có xác thực (`inline=true` cho PDF/ảnh) |
| `/items`, `/items/reorder` | POST vị trí bài giao chuẩn; POST di chuyển/sắp lại mục đích |

P1 không thêm hạn thời gian, khoảng mở, chính sách đóng, giới hạn lượt, quy tắc nộp muộn, gia hạn, bảng điểm, điểm danh, phân tích, đề xuất, đồng giảng viên, trợ giảng, email hoặc truyền thời gian thực. Trình sửa Markdown chủ động nhẹ và bình luận phẳng. Không cung cấp thay tệp hoặc xóa nội dung vĩnh viễn. Bộ đếm thi và chính sách chấm hiện có vẫn là nguồn chuẩn.

### Xác minh P1 có trọng tâm

Với `DATABASE_URL` và `TEST_DATABASE_URL` trỏ tới cơ sở dữ liệu kiểm thử PostgreSQL cô lập đã migration đến head, chạy từ `backend/`:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_classroom_resource_storage.py tests/test_classroom_classwork_unit.py tests/test_classroom_classwork.py tests/test_classroom_posts.py tests/test_classroom_assignments.py tests/test_classrooms_and_notifications.py -p no:cacheprovider -q
```

Đã xác minh **101 trường hợp backend đạt**, gồm từ chối quyền, truy cập UUID phần/tệp ẩn, từ chối ghi vào dữ liệu lưu trữ chỉ đọc, xung đột revision, giữ danh tính bài giao, chống trùng thông báo, phân trang bảng tin cùng thời gian, bù trừ tải lên và hợp đồng migration đóng băng. Migration bổ sung cũng nâng cơ sở dữ liệu cô lập mới qua `20261027_0036` thành công.

Từ `frontend/`, phạm vi Vitest có trọng tâm gồm `tests/classroom-content.test.tsx`, `tests/classroom-content-api.test.ts`, `tests/teacher-classroom-ui.test.tsx`, `tests/teacher-api-contract.test.ts`, `tests/teacher-pagination.test.tsx`, and `tests/notification-center.test.tsx`: **57 trường hợp đạt**. Ruff/ESLint theo phạm vi, TypeScript và `git diff --check` giới hạn nhiệm vụ cũng đạt. Các phát hiện rà soát mã nguồn độc lập đã được giải quyết cùng kiểm thử hồi quy.

Theo giới hạn thực thi nhiệm vụ, không mở trình duyệt, chụp ảnh, chạy E2E, bản dựng production hoặc toàn bộ kiểm thử kho mã. Bố cục trực quan được rà soát tĩnh, chưa xác minh trên trình duyệt thật.

Triển khai v1 này theo [thiết kế](superpowers/specs/2026-10-11-teacher-classroom-content-governance-design.md) và [kế hoạch triển khai](superpowers/plans/2026-10-11-teacher-classroom-content-governance.md) đã phê duyệt. PostgreSQL tiếp tục là nguồn chuẩn; mọi thay đổi miền đi qua FastAPI.

## Thiết lập và vai trò

Áp dụng lệnh migration backend bình thường `uv run alembic upgrade head`. Revision `20261011_0024` theo sau `20261011_0023`; thêm `TEACHER`, quyền sở hữu nội dung, kiểm duyệt, tài nguyên lớp, thông báo và nguồn gốc bài giao. Đề cũ giữ `origin=ADMIN` và có thể không có chủ sở hữu. Đề mới tạo phải có chủ sở hữu đã xác thực.

| Vai trò | Khả năng |
| --- | --- |
| USER | Luyện tập/lịch sử cá nhân, lời mời lớp, tư cách thành viên và bài luyện được giao hiện có. Không được biên soạn đề hoặc tự chọn vai trò đặc quyền khi đăng ký. |
| TEACHER | Mọi khả năng USER thông thường, thêm nội dung Builder và lớp thuộc sở hữu. Không được vào không gian ADMIN chung hoặc sửa nội dung giáo viên khác. |
| ADMIN | Quyền quản trị và chấm Writing chính thức/thủ công hiện có, đổi vai trò, quản trị Builder toàn cục, kiểm duyệt và lưu trữ/khôi phục lớp. |

Nâng tài khoản hiện có lên TEACHER qua điều khiển tài khoản ADMIN. Hạ vai trò, nâng sang vai trò khác TEACHER hoặc vô hiệu hóa gây xung đột khi tài khoản còn lớp hoạt động, kiểm duyệt đang chờ hoặc bản nháp trong đề giáo viên chưa lưu trữ. Trước hết phải lưu trữ lớp, giải quyết yêu cầu và lưu trữ/xóa bản nháp hoặc đề. Đổi vai trò giữ lịch sử học tập và ghi công giáo viên. Xóa vĩnh viễn chỉ ADMIN cũng từ chối tài khoản còn được miền quản trị tham chiếu, kể cả thông báo, thay vì xóa bản ghi đó.

CLI nháp OCR nay yêu cầu chủ sở hữu ADMIN đang hoạt động được chỉ định rõ:

```powershell
uv run python -m app.import_draft path/to/manifest.json --owner-user-id ADMIN_UUID
```

Nhập Transfer cũng gắn quyền sở hữu/nguồn gốc của tác giả đã xác thực. Cả hai cách nhập không được tạo người thực hiện quản trị giả.

Downgrade dành cho miền tính năng rỗng: từ chối khi có lịch sử lớp/thông báo/kiểm duyệt, tài khoản TEACHER hoặc nội dung nguồn giáo viên. Nhãn enum `TEACHER` bổ sung của PostgreSQL còn sau downgrade an toàn; không ghi lại enum người dùng hiện có để xóa nhãn.

## Nội dung thuộc sở hữu và kiểm duyệt

Nội dung giáo viên tạo luôn giữ `origin=TEACHER` và chủ sở hữu. ADMIN phê duyệt không biến nó thành nội dung chính thức. Nội dung chính thức có nguồn ADMIN; nội dung giáo viên được duyệt PUBLIC xuất hiện là nội dung cộng đồng cùng tên hiển thị người đóng góp.

`TestVersion.status` giữ `DRAFT`, `PUBLISHED` hoặc `ARCHIVED`. Bản ghi kiểm duyệt độc lập có phạm vi `CLASSROOM` hoặc `PUBLIC`, giữ người gửi, người duyệt, ghi chú và thời gian chuyển trạng thái. Chủ sở hữu hủy có trạng thái kiểm toán `CANCELLED` riêng, không ghi thành ADMIN từ chối. Mỗi phiên bản có tối đa một yêu cầu đang chờ cho mỗi phạm vi.

- Yêu cầu đang chờ khóa nội dung biên soạn, tài sản và metadata đề dùng chung của phiên bản. Hủy hoặc từ chối yêu cầu đang chờ cuối cùng mở khóa bản nháp.
- Giáo viên có thể gửi thẳng PUBLIC hoặc xin duyệt PUBLIC sau cho cùng phiên bản bất biến đã duyệt CLASSROOM.
- Duyệt CLASSROOM cho phép dùng bài giao trong lớp của chủ sở hữu; không công khai đề toàn cục. Duyệt PUBLIC cho phép luyện cá nhân toàn cục và đồng thời đủ điều kiện lớp học.
- Phê duyệt chạy bộ xác thực nội dung đầy đủ hiện có. Duyệt bản nháp mới xuất bản nó và lưu trữ phiên bản đã xuất bản hoạt động trước trong một giao dịch. Lượt làm vẫn tham chiếu phiên bản gốc đóng băng.
- Thay nội dung đã xuất bản cần bản nháp mới và kiểm duyệt mới. Vẫn có thể nhân bản phiên bản đã xuất bản thành nháp mới khi yêu cầu PUBLIC của nó đang chờ.
- Xuất bản trực tiếp không được bỏ qua kiểm duyệt nội dung nguồn giáo viên, kể cả ADMIN gọi. Nội dung ADMIN chính thức giữ luồng xuất bản hiện có.
- Thu hồi đổi quyền hiển thị và bắt đầu tương lai. Nếu duyệt CLASSROOM còn sau thu hồi PUBLIC, bắt đầu trong lớp vẫn hoạt động. Thu hồi phê duyệt cuối chặn bắt đầu mới mà không xóa lượt làm, bài giao hoặc kết quả hiện có.

Library và Skill Practice cá nhân yêu cầu `public_only=true` khi đọc đề/phiên bản, kể cả liên kết Library trực tiếp. Dùng cùng chính sách đủ điều kiện backend cho mọi vai trò, nên nội dung chỉ CLASSROOM của giáo viên nằm trong Builder và luồng lớp học của họ. Tổng quan ADMIN giữ số đếm riêng toàn bộ đề Builder.

Hàng đợi và trang chi tiết ADMIN cung cấp xem trước chỉ đọc cùng duyệt/từ chối/thu hồi. Yêu cầu và hủy của chủ sở hữu nằm trên thanh công cụ Builder giáo viên. Chính sách backend cũng bao phủ endpoint Reading, Listening, Writing, mô-đun, tài sản và Transfer cấp thấp.

## Lớp học, lời mời và thông báo

Lớp có đúng một chủ sở hữu TEACHER hoạt động. Chủ sở hữu tạo/cập nhật/lưu trữ; ADMIN được lưu trữ và khôi phục. Khôi phục yêu cầu chủ sở hữu vẫn là TEACHER hoạt động. Nội dung và kết quả lớp lưu trữ vẫn đọc được, còn lời mời mới, thay đổi thành viên và bắt đầu bài giao bị chặn.

Lời mời dùng email chuẩn hóa. Tài khoản hiện có nhận lời mời trong ứng dụng. Email chưa biết giữ chờ, không gửi email hoặc tự thêm thành viên. Đăng ký, đăng nhập mật khẩu và Google gắn lời mời chờ khớp và tạo thông báo lũy đẳng. Tài khoản được mời phải chủ động chấp nhận hoặc từ chối. Chỉ tài khoản đó được phản hồi; chấp nhận đồng thời tạo một thành viên và một chuyển trạng thái chấp nhận.

Học viên có thể rời và chủ sở hữu có thể gỡ họ. Giai đoạn thành viên giữ `joined_at`/`left_at`; tham gia lại tạo giai đoạn mới. Hủy lời mời và lưu trữ lớp không xóa hồ sơ học tập.

Thông báo là sự kiện theo người nhận có loại, payload có cấu trúc, tham chiếu thực thể và thời gian đọc. Chuông đầu trang lấy số chưa đọc và danh sách, có Load more cho mục cũ. Mở chuông không đánh dấu đã đọc; đánh dấu một/tất cả là thao tác rõ ràng. Văn bản EN/VI hiển thị từ payload. Tạo sự kiện trong giao dịch miền và có chống trùng; thông báo không cấp thẩm quyền. Giao diện đặt lại trạng thái khi người nhận đăng nhập thay đổi.

## Bài giao và kết quả

Bài giao tham chiếu một phiên bản bất biến. Chủ sở hữu được dùng nội dung giáo viên của mình đang duyệt CLASSROOM/PUBLIC hoặc nội dung ADMIN chính thức đã xuất bản. Không thể giao nội dung cộng đồng của giáo viên khác trong lớp chủ sở hữu. Một phê duyệt có thể dùng trong nhiều lớp của tác giả. Cho phép làm lại.

Bắt đầu bài giao hỗ trợ mô-đun Reading/Listening/Writing/Speaking có sẵn, đơn vị tập trung và Full Mock. Dịch vụ vòng đời hiện có tạo lượt làm. Trong giao dịch đó, backend khóa và kiểm tra tài khoản hoạt động, phiên bản đủ điều kiện, lớp, bài giao và thành viên. DTO lượt/phiên thường từ chối nguồn gốc do trình duyệt cung cấp.

- Lượt độc lập/tập trung lưu `Attempt.classroom_assignment_id`.
- Full Mock lưu `TestSession.classroom_assignment_id`; lượt con suy ra nguồn gốc từ phiên cha và giữ trường bài giao riêng null. Kiểm tra cơ sở dữ liệu cấm nguồn gốc kép.
- Luyện tập cá nhân giữ cả hai trường null.

Truy vấn kết quả giáo viên phải khớp nguồn gốc bài giao thực và giáo viên chủ sở hữu hiện tại của lớp. `student_id + test_version_id`, tư cách thành viên hoặc biết UUID là chưa đủ. Luyện cá nhân cùng phiên bản vẫn riêng tư. Lịch sử bắt nguồn bài giao vẫn đọc được sau hết thành viên, lưu trữ lớp hoặc thu hồi phê duyệt.

Giao diện kết quả chỉ tái sử dụng dịch vụ đọc thuộc học viên hiện có sau phân quyền này. Nó hiện câu trả lời đã lưu/nộp, độ đúng/xem lại khách quan khi mở khóa, văn bản Writing và kết quả thủ công/AI tư vấn hiện có. Đọc kết quả không đổi thời gian, đồng bộ bộ đếm, sửa câu trả lời hoặc gọi đánh giá. Giáo viên được phân quyền chủ động lưu tiêu chí chốt Writing/Speaking của con người qua thao tác ghi riêng theo bài giao; kết quả khách quan giữ chỉ đọc. Xem đáp án Full Mock vẫn khóa đến khi phiên hoàn thành. Danh sách kết quả/hàng đợi kiểm duyệt có trang Previous/Next, giữ bộ lọc và thứ tự ổn định.

## Giao diện và nhóm API

| Giao diện | Mục đích |
| --- | --- |
| `/teacher/tests`, `/teacher/tests/new`, `/teacher/tests/{testId}/versions/{versionId}/edit` | Builder thuộc sở hữu và gửi/hủy kiểm duyệt. |
| `/teacher/classrooms` và chi tiết lớp | Quản lý của chủ sở hữu, lời mời, thành viên, bài giao và điều hướng kết quả. |
| `/classrooms` và chi tiết lớp | Hộp lời mời, lịch sử thành viên và bắt đầu bài giao cho mọi vai trò đã đăng nhập. |
| Tuyến kết quả bài giao lớp dưới `/teacher/classrooms/...` và `/classrooms/...` | Giao diện kết quả dùng chung với chấm chủ quan của giáo viên và kết quả khách quan chỉ đọc; tuyến trung lập cũng hỗ trợ ADMIN kiểm tra được phân quyền. |
| `/admin/moderation`, `/admin/moderation/{requestId}` | Hàng đợi, xem trước và quyết định ADMIN. |
| Đầu trang, Library và người dùng ADMIN hiện có | Chuông thông báo, ghi công chính thức/cộng đồng, điều khiển vai trò TEACHER và thông báo xung đột bản địa hóa. |

Nhóm API dưới `/api/v1`:

- `/classrooms` (danh sách theo vai trò), `/classrooms/{id}/members`, `/classrooms/{id}/invitations`, `/classroom-invitations/{id}/{accept|decline|cancel}` and `/me/classroom-invitations`.
- `/classrooms/{id}/assignments`, chi tiết/lưu trữ bài giao và `/classroom-assignments/{id}/start`.
- `/classrooms/{id}/assignments/{assignmentId}/results`, `/students/{studentId}/attempts` and `/attempts/{attemptId}`.
- `/test-versions/{id}/moderation-requests`, `/test-moderation-requests/{id}/cancel`, `/admin/test-moderation-requests` và tuyến chi tiết/quyết định của nó.
- `/notifications`, `/notifications/unread-count`, `/notifications/{id}/read` and `/notifications/read-all`.

## Giới hạn chủ động của v1

Không thêm gửi email, truyền thông báo thời gian thực, đồng giảng viên, chuyển quyền sở hữu, hạn, giới hạn làm lại, phân tách tổ chức hoặc phân tích lớp đầy đủ. Hỗ trợ chấm cuối Writing/Speaking của con người như bên dưới. Chấm, bộ đếm, tự lưu, bộ hiển thị, chính sách âm thanh và luyện cá nhân giữ trong bộ máy hiện có.

<a id="focused-verification"></a>

## Xác minh có trọng tâm

Xác minh dùng dữ liệu hư cấu và cơ sở dữ liệu PostgreSQL cục bộ mới. Không dùng trình duyệt, Playwright/E2E, máy chủ phát triển, bản dựng, mô hình/GPU thật, Modal hoặc triển khai. Nâng mới qua `20261011_0024`, hạ miền rỗng về `20261011_0023` và nâng lại thành công. Lịch sử migration có một head.

Từ `backend/`, với `DATABASE_URL` và `TEST_DATABASE_URL` trỏ tới cơ sở dữ liệu kiểm thử cô lập:

```powershell
uv run pytest tests/test_teacher_domain_models.py tests/test_teacher_roles_and_test_ownership.py tests/test_test_version_moderation.py tests/test_moderation_concurrency.py tests/test_classrooms_and_notifications.py tests/test_classroom_assignments.py tests/test_teacher_assignment_results.py tests/test_admin.py tests/test_auth.py tests/test_api_contract.py tests/test_asset_access.py tests/test_writing_builder.py tests/test_focused_attempts.py tests/test_full_mock_sessions.py tests/test_writing_attempts.py tests/test_attempt_scoring_history.py tests/test_test_version_concurrency.py tests/test_listening.py tests/test_asset_cloning.py tests/test_transfer.py tests/test_draft_import.py tests/test_writing_relevance.py tests/test_writing_ai_practice_feedback.py tests/test_writing_ai_observer_lifecycle.py tests/test_reading_publish_regression.py tests/test_test_lifecycle.py tests/test_lifecycle_refactor.py -q --tb=short
```

Từ `frontend/`:

```powershell
npx vitest run tests/teacher-classroom-ui.test.tsx tests/notification-center.test.tsx tests/teacher-api-contract.test.ts tests/teacher-builder-governance.test.tsx tests/teacher-pagination.test.tsx tests/auth.test.tsx tests/admin-api.test.ts tests/admin-user-detail.test.tsx tests/admin-user-list.test.tsx tests/app-shell.test.tsx tests/builder-workspace-page.test.tsx tests/builder-workspace-navigation.test.tsx tests/builder-route.test.tsx tests/writing-review.test.tsx tests/writing-ai-practice-feedback.test.tsx tests/practice-library.test.tsx tests/runner-localization.test.tsx tests/skill-practice.test.tsx tests/home-user-metric.test.tsx tests/interactive-planet.test.tsx
npm run typecheck
```

Kết quả: **355 kiểm thử backend** và **269 kiểm thử frontend** đạt. Kiểm tra kiểu đạt. Ruff và ESLint giới hạn ở tệp nguồn thay đổi/mới bằng các lệnh PowerShell sau (từ thư mục backend/frontend tương ứng):

```powershell
$repoRoot = git rev-parse --show-toplevel
$changedPython = @(git -C $repoRoot diff --name-only ad220178 -- '*.py'; git -C $repoRoot ls-files --others --exclude-standard -- '*.py') | Sort-Object -Unique | Where-Object { $_ -like 'backend/*' } | ForEach-Object { $_.Substring(8) }
uv run ruff check @changedPython
uv run ruff format --check @changedPython
```

```powershell
$repoRoot = git rev-parse --show-toplevel
$changedTs = @(git -C $repoRoot diff --name-only ad220178 -- '*.ts' '*.tsx'; git -C $repoRoot ls-files --others --exclude-standard -- '*.ts' '*.tsx') | Sort-Object -Unique | Where-Object { $_ -like 'frontend/*' } | ForEach-Object { $_.Substring(9) }
npx eslint @changedTs
```

Ruff kiểm tra/định dạng đạt cho 57 tệp Python; ESLint đạt cho 75 tệp TS/TSX. Chạy `git diff --check` trước commit. Kế hoạch triển khai ghi phạm vi hồi quy và kết quả rà soát.


<a id="human-final-subjective-grading"></a>

## Chấm điểm chủ quan cuối cùng bởi con người

Đánh giá AI Writing/Speaking tiếp tục chỉ tư vấn. Trong luyện cá nhân, chủ lượt làm có thể nhập tiêu chí hoặc sao chép đánh giá AI hoàn tất vào biểu mẫu, chỉnh sửa và chủ động Save điểm luyện cuối. Sao chép tuyệt đối không lưu điểm. Chú thích Writing vẫn là phản hồi sư phạm, không tham gia phép tính điểm.

Trong lượt làm lớp, học viên không được nhập, sửa hoặc sao chép AI vào điểm cuối. Họ thấy “Đang chờ giáo viên chấm” (EN: “Waiting for teacher grading”) đến khi có điểm cuối của con người. Nhân sự lớp có `grades.edit` chấm qua tuyến theo bài giao; quản trị viên giữ thẩm quyền chấm cuối. Nhân sự không được chấm bài cá nhân dù học viên/phiên bản đề khớp bài giao. Kết quả bài giao lịch sử vẫn chấm được sau hết thành viên.

Nguồn gốc lớp nghĩa là lượt làm có ID bài giao lớp hoặc TestSession Full Mock cha có. Cả hai kỹ năng dùng cùng chính sách phân quyền. Lượt đang làm và con của Full Mock IN_PROGRESS vẫn khóa. Kết quả khách quan lớp giữ chỉ đọc.

Tiêu chí chốt Speaking FC/LR/GRA/PR và phản hồi tùy chọn lưu độc lập trong `attempt_speaking_scores` (Alembic `20261013_0033`). Save chủ động của con người dùng phép tính tổng Speaking trọng số đều hiện có. Worker AI tuyệt đối không ghi điểm cuối của con người. Speaking tập trung giữ đánh giá tiêu chí cuối mà không tạo band phân tích toàn mô-đun; Writing tập trung cũng giữ chấm chỉ task.

Backend cung cấp `grading.context`, `can_edit_final`, `can_copy_ai_to_final` và `waiting_for_teacher` trong xem lại chủ quan và chi tiết kết quả lớp. Client hiển thị khả năng này; tuyến ghi kiểm tra lại phân quyền. Tuyến chủ sở hữu/admin chung là `PUT /attempts/{id}/writing-scores/{task_id}` và `PUT /speaking-attempts/{id}/final-score`. Tuyến giáo viên là `PUT /classrooms/{classroom_id}/assignments/{assignment_id}/attempts/{id}/writing-scores/{task_id}` và cùng tiền tố bài giao kết thúc bằng `/speaking-score`.

## Học tập P4 và không gian làm việc thiết kế lại

My Progress thêm mục tiêu cá nhân, lịch sử đánh giá lớp được chấp nhận, band kỹ năng riêng, độ chính xác loại câu có cấu trúc, tiêu chí chốt con người, ưu tiên luyện dựa bằng chứng, đề xuất bài giao đủ điều kiện và kế hoạch cải thiện được giao. Analytics thêm tổng hợp hoàn thành/thiếu/chờ chấm của lớp và chi tiết học viên được phân quyền. Người quản lý kế hoạch chọn bài giao đang hoạt động hoặc tài nguyên đã xuất bản hiện có; chỉ nhiệm vụ tài nguyên có dấu hoàn thành thủ công riêng. Xem [phân tích, riêng tư, ngưỡng, API và migration 0039](classroom-learning-analytics.md).

[Thiết kế lại không gian Classroom](classroom-workspace.md) áp dụng cả Taste và UI/UX Pro Max. Đầu trang/menu Create gọn, Classwork ưu tiên chủ đề, trình sửa/thao tác theo ngữ cảnh, điều hướng học viên/giáo viên, phân tích phẳng, phương án ma trận/danh sách Gradebook và token thích ứng chung bảo toàn hành vi P1/P2. Chủ động không xác minh trình duyệt theo hạn chế người dùng.
