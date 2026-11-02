# Trải nghiệm không gian làm việc lớp học

> **Kiểm toán tài liệu: CURRENT.** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Trải nghiệm không gian làm việc lớp học. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../frontend/src/features/classrooms).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/classrooms.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/đo hiệu năng bên dưới thuộc lần thực hiện gốc, không phải lần chạy lại trong đợt kiểm toán này.

Thiết kế lại giữ điều hướng toàn cục, phông chữ, màu nhấn và token sáng/tối có ngữ nghĩa của BandPilot. Stream, Classwork, Assignments và Calendar tách các luồng học tập; People/Gradebook/Analytics tuân theo khả năng lớp học, còn My Progress hiển thị tiến độ cá nhân trong lớp. Giữ nguyên liên kết bài đăng từ thông báo và liên kết sâu tới bài giao.

## Rà soát thiết kế bằng hai kỹ năng

Đã đọc và áp dụng cả hai kỹ năng được cài: `.agents/skills/ui-ux-pro-max/SKILL.md` và `.agents/skills/design-taste-frontend/SKILL.md`, kể cả tài liệu tham khảo màn hình ứng dụng của Taste. Đã chạy các tìm kiếm UI/UX Pro Max cục bộ sau:

- `education LMS SaaS classroom productivity dashboard --design-system --variance 2 --motion 2 --density 7 -p "BandPilot Classroom"`
- `dashboard navigation information hierarchy --domain ux`
- `progressive disclosure form complexity --domain ux`
- `keyboard focus modal dialog --domain ux`
- `responsive dashboard layout --stack nextjs`
- `accessible data tables --domain ux`

Tìm kiếm đề xuất phong cách Minimalism/Swiss và cảnh báo bài giao bị ẩn, điều hướng lộn xộn và hành vi di động kém. Bố cục trang giới thiệu chung và phông giáo dục vui nhộn không phù hợp ứng dụng IELTS dành cho người lớn hiện có, nên thương hiệu BandPilot và kiến trúc màn hình làm việc được ưu tiên. Không thêm thư viện phụ thuộc, framework chuyển động, MASTER.md toàn cục hoặc giao diện thứ hai.

Hướng ứng dụng của Taste là `achromatic-ledger`, seed 2734, giữ bảng màu/kiểu chữ. Hướng kết hợp là SaaS giáo dục biên tập tối giản: đầu trang gọn, một mặt phẳng nội dung, bề mặt phẳng, bảng số liệu căn chỉnh và điều khiển theo ngữ cảnh. Chủ đề thực, bài giao IELTS, hạn nộp và bản ghi kỹ năng riêng tạo bản sắc sản phẩm. Chỉ số hiển thị bằng văn bản thay vì ô trang trí; trạng thái rỗng không tạo dữ liệu giả.

## Luồng làm việc

Đầu trang hiển thị lớp học, số giáo viên/thành viên thực và trạng thái. Menu Create được phân quyền mở trực tiếp tạo thông báo, chủ đề, tài nguyên hoặc bài giao. Cài đặt/quản lý và lưu trữ nằm trong menu phụ. Lớp đã lưu trữ vẫn đọc được và ẩn điều khiển ghi.

Classwork mặc định hiển thị nội dung. Add content chỉ mở một luồng chủ đề/tài nguyên/đặt bài giao có trọng tâm sau khi chọn. Nếu không có bài giao đủ điều kiện, hiển thị trạng thái rỗng rõ ràng và thao tác tạo được phân quyền, thay cho hộp chọn chỉ chứa dấu gạch ngang. Hoạt động chưa đặt dùng nhóm phụ; không có chủ đề giả hoặc nhóm rỗng. Nhãn dùng Topic / Chủ đề học còn tên Section backend giữ nguyên.

Chủ đề có thể thu gọn và có một menu quản lý theo ngữ cảnh. Điều khiển chỉnh sửa/xuất bản/lưu trữ/di chuyển tài nguyên được mở khi cần. Kéo thả gốc và phương án bàn phím giữ API P1 có kiểm tra revision. Xung đột tải lại thứ tự hiện tại và giải thích cách thử lại.

### Cải tiến Classwork gọn

Classwork nay hiển thị một nút chủ đề với tổng số mục chính xác và một vùng nội dung được điều khiển. Chỉ chủ đề đã xuất bản đầu tiên có nội dung hoạt động được mở ban đầu; nhóm rỗng, chưa đặt và lịch sử bắt đầu đóng. ID chủ đề ổn định giữ lựa chọn mở qua làm mới nội dung/tiến độ. Điều hướng hash phần, bài giao, tài nguyên và mục mở nhóm đích, đưa tiêu điểm tới đề mục hoặc hàng. Liên kết truy vấn bài giao hiện có vẫn mở thẻ chi tiết bài giao.

Tài nguyên đã phân giải và bài giao chuẩn được chuẩn hóa một lần, loại tham chiếu trùng và chưa phân giải khỏi số lượng. Bài giao đã lưu trữ xuất hiện một lần trong nhóm lịch sử thu gọn riêng, kể cả bài giao không có trong ảnh chụp vị trí Classwork. Tài nguyên lưu trữ được phân quyền có nhóm thu gọn riêng. Bài giao chuẩn đang hoạt động chưa đặt vẫn di chuyển được qua API vị trí hiện có. Không lưu phần tổng hợp giả.

Trước: đề mục chủ đề → vùng tài liệu luôn mở → ProgressSummary đầy đủ cho từng bài giao. Sau: nút/số lượng chủ đề → hàng tài nguyên hoặc bài giao gọn → luồng đọc/chi tiết/kết quả hiện có theo nhu cầu. ClassworkAssignmentMeta dùng dữ liệu nhà cung cấp P2 và tối đa ba phần: loại/kỹ năng, trạng thái hiện tại và hạn nộp hiệu lực có ý nghĩa hoặc số lần bắt đầu đã dùng hữu hạn. Nó không bịa điểm, lặp hạn đóng tuyệt đối hoặc hiển thị bộ đếm sử dụng bằng không khi không giới hạn. ProgressSummary giữ nguyên ở màn hình khác. Nhân sự giữ chỉnh sửa, xuất bản, lưu trữ, sắp thứ tự có revision và Move theo ngữ cảnh, kể cả đích thả ở chủ đề đã thu gọn.

Cải tiến này giữ bố cục achromatic-ledger hiện có của Taste, không vẽ lại hoặc thêm giao diện. Hướng dẫn màn hình ứng dụng cho phép một viền chủ đề nhẹ và đường phân hàng. Kết quả UI/UX Pro Max cục bộ hướng dẫn khóa ổn định, tiêu điểm bàn phím và phương án thay kéo. Tìm kiếm vùng mở rộng và lần thử lại không tạo mục dữ liệu khớp đã xác minh; vì vậy dùng rõ thiết kế được cung cấp và ngữ nghĩa nút/vùng. Xác minh frontend có trọng tâm đạt 69 kiểm thử, gồm 29 trường hợp Classwork gọn mới; TypeScript và ESLint theo phạm vi đạt. Bộ dữ liệu đồng thời P2 cũng được cô lập: chuỗi 21 kiểm thử vòng đời/miền/danh sách đạt. Kiểm tra trình duyệt, kích thước màn hình và tương phản hiển thị vẫn bị loại theo giới hạn thực thi của người dùng.

Stream nhóm bộ lọc và New post, nhấn mạnh tiêu đề/loại/tác giả/ngày bản địa hóa, phân giải tiêu đề hoạt động từ metadata bài giao thật và nhóm hạn thời gian. Bình luận và thao tác phụ mở khi cần. Kiểm duyệt thảo luận dùng khả năng riêng, độc lập với quyền tác giả nội dung.

Assignments dùng một danh sách gọn, tạo mặc định đóng, cài đặt lịch hiển thị dần và các luồng tiến độ/tiếp tục/kết quả/theo dõi/gia hạn hiện có. Thao tác lưu trữ dùng hộp thoại xác nhận hiện có. Calendar giữ lịch hạn thực P2. People ẩn biểu mẫu cài đặt/mời đến khi được yêu cầu, đồng thời giữ bề mặt nhân sự/học viên/lời mời riêng.

Gradebook có cột danh tính cố định, cuộn nội bộ, xuất CSV và phương án danh sách học viên. Hồ sơ giữ liên kết kết quả/chấm điểm chuẩn và thêm phân tích/kế hoạch được phân quyền. My Progress và Analytics dùng cùng dải chỉ số phẳng, lịch sử kỹ năng riêng, bảng bằng chứng, liên kết luyện tập thực và trạng thái thiếu dữ liệu trung thực.

## Khả năng tiếp cận và thích ứng màn hình

Thẻ có tabpanel liên kết, trạng thái được chọn, tiêu điểm di chuyển và hỗ trợ Arrow/Home/End. Vùng mở rộng gốc vận hành được bằng bàn phím. Menu thao tác đóng khi Escape, trả tiêu điểm về nhãn tóm tắt và vẫn mở khi có xác nhận phá hủy bên trong. Hộp thoại xác nhận hiện có giữ rồi trả tiêu điểm; trình tạo đưa tiêu điểm tới trường đầu. Trạng thái tải/lỗi/thử lại và hủy yêu cầu lỗi thời ngăn hiển thị sai. Thao tác đang chờ vô hiệu hóa lặp lại và giữ thông báo xung đột.

Không có thanh bên cố định. Thẻ và bảng cuộn trong giới hạn riêng. Cột co nhỏ được, tiêu đề xuống dòng và quy tắc 1024/768/480 bao quát máy tính/máy tính bảng/điện thoại hẹp. Văn bản biểu mẫu di động giữ 16px và điều khiển chạm cao ít nhất 44px. Giữ tiêu điểm, trạng thái văn bản, nhãn, giảm chuyển động và token giao diện. Biểu đồ có phương án lịch sử văn bản theo ngày.

## Kiểm tra đã thực hiện và giới hạn

### Gỡ an toàn, hoạt động tài nguyên và bài giao do giáo viên chỉ định

Classwork giữ cấu trúc chủ đề/hàng gọn nêu trên. Menu ngữ cảnh nay phân biệt Delete resource, Delete topic và Remove from Classwork, với xác nhận theo hậu quả và chặn gửi lặp. Menu bài đăng dùng cùng điều khiển biểu tượng mở rộng có khả năng tiếp cận. Quản lý nội dung và quản lý bài giao được kiểm tra riêng; học viên và Teaching Assistant mặc định không được xóa nội dung học tập được quản lý, còn quyền giám sát Admin không ngụ ý quyền tác giả. Lớp đã lưu trữ tiếp tục chỉ đọc.

Xóa chủ đề chuyển nội dung sang nhóm chưa đặt và tăng revision lớp trong giao dịch. Tài nguyên đã xuất bản dưới chủ đề ẩn vẫn ẩn sau khi chủ đề bị gỡ. Xóa tài nguyên từ chối **mọi** tham chiếu bài đăng/kế hoạch học tập được giữ lại, kể cả lịch sử, với `RESOURCE_REFERENCED`; nhân sự phải dọn tham chiếu được phân quyền hoặc lưu trữ tài nguyên. Gỡ tệp an toàn cam kết thay đổi cơ sở dữ liệu trước, kiểm tra lại tham chiếu bền vững rồi mới xóa tệp nhị phân không còn tham chiếu. Lỗi dọn hệ thống tệp được ghi nhật ký và có thể để lại tệp mồ côi không truy cập được cho bảo trì; không đảo ngược xóa đã cam kết. Bài đăng đã xóa giữ bình luận và nguồn gốc thông báo qua `deleted_at`, rời bảng tin và liên kết cũ hiện thông báo nội dung không khả dụng.

Gỡ vị trí bài giao giữ bài giao chuẩn, lịch, lượt làm bài, phiên và điểm. `classwork_hidden` cùng `removed_assignment_ids` của ảnh chụp ngăn cơ chế dự phòng chưa đặt chuẩn lập tức đưa lại; gắn lại được phân quyền xóa trạng thái này. DELETE chuẩn chủ động bảo thủ: lượt làm bài, phiên, nhật ký chính sách, gia hạn, thông báo hoặc kế hoạch học tập chặn xóa bằng `ASSIGNMENT_HISTORY_PROTECTED`. Bài giao hiện tại thường có nhật ký chính sách và nên dùng Archive hoặc Remove from Classwork; giao diện không giả gọi hai thao tác đó là Delete.

Stream suy ra `RESOURCE_ACTIVITY` từ cùng bản ghi tài nguyên và vị trí. Mốc xuất bản được điền cho tài nguyên đã xuất bản hiện có; bản nháp, chủ đề cha ẩn và nội dung lưu trữ/đã xóa tuân quy tắc hiển thị hiện có. Một UNION bài đăng/bài giao/tài nguyên có giới hạn, con trỏ biết loại và danh tính React giữ thứ tự/phân trang. Truy vấn tải chi tiết kiểm tra lại quyền hiển thị lớp/trạng thái/chủ đề hiện tại, nên khóa đã chọn lỗi thời không thể lộ nội dung tài nguyên vừa ẩn. Tài nguyên gắn vào bài đăng đã xuất bản chưa xóa không xuất hiện như mục độc lập trong bảng tin hỗn hợp; bộ lọc tài nguyên vẫn hiện hoạt động chuẩn của nó. Trình đọc dùng tuyến tệp có xác thực hiện có. Sắp lại và sửa metadata không tạo thông báo tài nguyên hoặc bài đăng sao chép.

Bài giao HTTP mới yêu cầu `target` bất biến rõ ràng: MODULE cùng mô-đun đầy đủ/đơn vị tập trung, hoặc FULL_MOCK. Giáo viên chọn Test logic, kỹ năng hợp lệ, phạm vi và đơn vị thực từ metadata đã xuất bản được lớp phân quyền. Đơn vị tập trung hỗ trợ tái sử dụng bộ máy Reading Passage, Listening Part, Writing Task và Speaking Prompt; không cung cấp Speaking Part. Full Mock yêu cầu bốn mô-đun hiện có và thời lượng dương. Máy chủ từ chối đơn vị thiếu, thuộc nơi khác hoặc không tương thích. `require_assignment_start()` so sánh mục tiêu trong giao dịch bắt đầu hiện có trước kiểm tra chính sách P2; đổi mô-đun, phạm vi, đơn vị hoặc chế độ lượt gốc nhận `ASSIGNMENT_TARGET_MISMATCH`. Full Mock giữ một phiên/lần bắt đầu gốc, cách chấm, bộ đếm thời gian và nguồn điểm chốt của con người giữ nguyên.

Học viên thấy một mục tiêu được giao và thao tác Start, giữ lựa chọn trình bày hợp lệ, Resume và Results. Ngữ cảnh mục tiêu đi cùng Classwork, Stream, theo dõi, cả hai chế độ Gradebook và phân tích học tập. Đề xuất khớp kỹ năng được giao và ngữ cảnh câu hỏi/task tập trung. Bài giao cũ có target null giữ bắt đầu linh hoạt và tham chiếu lịch sử đóng băng. Mục tiêu khác yêu cầu bài giao thay thế; trigger cơ sở dữ liệu từ chối sửa ngay cả trước khi có bài làm học viên.

API mới dưới `/classrooms/{id}`: DELETE `posts/{id}`, `resources/{id}`, `sections/{id}`, `items/{id}` (gỡ vị trí) và `assignments/{id}` (xóa chuẩn có bảo vệ); GET `assignment-versions/{id}` cung cấp lựa chọn mục tiêu an toàn, đúng phạm vi. Client DELETE Classwork gửi `expected_revision` và xử lý xung đột qua luồng làm mới hiện có. Migration `20261027_0040` và `0041` thêm metadata gỡ/xuất bản cùng lưu trữ target đối tượng-hoặc-null đã xác thực và trigger mục tiêu bất biến. Cả hai đã áp dụng trên cơ sở dữ liệu cục bộ thật, hiện ở `0041`; cơ sở dữ liệu rỗng cô lập đạt nâng cấp → hạ về `0039` → nâng cấp mà không hạ cơ sở dữ liệu ứng dụng. Downgrade từ chối trạng thái gỡ/target đang giữ thay vì âm thầm bỏ dữ liệu.

### Hiển thị bản sửa đổi kỹ thuật

Library thông thường, chi tiết đề, Skill Practice, tạo/hiển thị bài giao Classroom, History, tóm tắt lượt làm bài học viên/admin và Analytics không còn hiện số TestVersion kỹ thuật. Khám phá nhóm theo Test logic và chọn số đã xuất bản đủ điều kiện cao nhất, phá hòa bằng ID ổn định, **chỉ trong các phiên bản mà luồng được phân quyền đã trả về**. Bản nháp, lưu trữ hoặc chưa phê duyệt không thể thắng lựa chọn đó. Tuyến chi tiết lịch sử, bắt đầu, xem lại và xóa rõ ràng giữ ID đóng băng gốc. Builder và kiểm duyệt giữ thao tác revision; số kỹ thuật nằm trong lịch sử revision nâng cao thu gọn thay cho nhãn nổi bật. Hợp đồng Transfer, bộ đếm, quan hệ cơ sở dữ liệu và tính so sánh điểm giữ nguyên.

Giữ hệ phân cấp danh sách màn hình ứng dụng và bề mặt nhẹ của Taste. Hướng dẫn UI/UX Pro Max được dùng cho tiêu điểm hiển thị, menu biểu tượng có nhãn, mở rộng bằng bàn phím/phương án Move, biểu mẫu hiển thị dần, trạng thái thử lại và điều khiển 44px. Không đổi giao diện toàn cục hoặc thư viện phụ thuộc. Xác minh cuối vẫn là kiểm thử đơn vị/tích hợp có trọng tâm, TypeScript, ESLint/Ruff theo phạm vi và rà soát khả năng tiếp cận/thích ứng ở mã nguồn; không chạy trình duyệt, E2E, bản dựng, toàn bộ kiểm thử, toàn bộ hệ thống hoặc AI thật. Kiểm tra mã nguồn Taste báo không có lỗi; cảnh báo là bóng overlay hiện có, dương tính giả `box-shadow: none`, khóa bình luận `unlock`, thêm số không ngày và dấu gạch biểu thị thiếu giá trị. Tắt theo dõi CI theo yêu cầu người dùng.

Tập frontend cuối gồm 16 tệp đạt **211 kiểm thử**, thêm **5 kiểm thử tuyến Builder** đạt (**216 trường hợp khác nhau**); bốn tệp Classroom thay đổi cũng đạt lần kiểm tra tiếp theo **47 kiểm thử** sau chỉnh vùng chạm/nhãn mục tiêu cuối. Bộ chọn mã nguồn Reading E2E được cập nhật theo liên kết Draft hướng người dùng mà không chạy E2E. Tập backend mười tệp đạt 158 trường hợp; kiểm thử xóa cũ mới ban đầu kỳ vọng 200 từ endpoint tạo hiện có trả 201, sau đó đạt khi sửa kỳ vọng (**159 trường hợp khác nhau đã xác minh**). TypeScript, ESLint theo phạm vi, Ruff kiểm tra/định dạng cả 27 tệp Python thay đổi, vòng nâng/hạ migration và `git diff --check` đều đạt. Tranh chấp kết nối thật P2 nay dùng cơ sở dữ liệu dùng một lần, đã migration và cô lập để không để lại bộ dữ liệu đã cam kết trong cơ sở dữ liệu kiểm thử chung.

Xác minh dùng kiểm thử thành phần/API/CSS Vitest có trọng tâm, TypeScript, ESLint theo phạm vi, kiểm thử phân quyền/kết quả PostgreSQL và `git diff --check`. Kiểm tra mã nguồn ứng dụng Taste báo **0 FAIL**. Cảnh báo đã rà soát: bóng menu nổi thật là chủ ý, `box-shadow: none` là dương tính giả của bộ quét, `unlock` là khóa mở bình luận hiện có, thêm số không dùng định dạng ngày và dấu gạch biểu thị giá trị thiếu.

Ngày 2026-10-27, bảy tệp frontend có trọng tâm đạt **78 kiểm thử**, cùng TypeScript và ESLint theo phạm vi. Lượt hồi quy backend tám tệp đạt 99 kiểm thử; kiểm thử đếm truy vấn còn lại đạt sau khi sửa thứ tự chèn dữ liệu mẫu. Lượt chỉ P4 cuối đạt cả **14 kiểm thử**, và tranh chấp nhân sự hai kết nối thật đạt lại sau khi làm chốt an toàn cơ sở dữ liệu tương thích CI. Cả 39 tệp Python liên quan nhiệm vụ đạt Ruff kiểm tra/định dạng theo phạm vi. Vòng migration 0038/0039 mới và kiểm tra head 0039/API 200 trên máy cục bộ thật đều đạt.

Người dùng cấm rõ việc mở trình duyệt, kiểm tra ảnh chụp/kích thước màn hình, E2E, bản dựng production, toàn bộ bộ kiểm thử và gọi AI thật. Không hoạt động nào trong số đó chạy. Rà soát thích ứng và giao diện chỉ ở mã nguồn; tương phản hiển thị, bố cục điểm ảnh và tương tác trình duyệt thực vẫn cần rà soát thủ công. Không tuyên bố khớp từng điểm ảnh hoặc đã xác minh bằng trình duyệt.
