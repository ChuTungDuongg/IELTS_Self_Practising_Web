# Điều tra hiệu năng BandPilot — ngày 27 tháng Mười năm 2026

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Điều tra hiệu năng BandPilot — ngày 27 tháng Mười năm 2026. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../backend/app/repositories/tests.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](handbook/testing-and-delivery.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


Mốc ban đầu: `origin/main` tại `4b24dbbbf999fb5f8482036ce64cfe1aff55cf71`. Log từ xa hiện tại đã được tải qua GitHub Actions API trước khi sửa. [CI 40507333869](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions/runs/40507333869) chỉ thất bại ở kiểm thử duy trì phát Listening (1,620/1,621 kiểm thử đạt). [Golden Path 40507334185](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions/runs/40507334185) đạt. Workflow và cổng chất lượng không đổi.

## Ranh giới đo lường

Không chạy server development, trình duyệt, build production Local, trình chạy E2E Local, toàn bộ bộ kiểm thử Local, reset DB hoặc yêu cầu AI thật. Bằng chứng đến từ kiểm thử thành phần tập trung, số yêu cầu/render, biên dịch SQL PostgreSQL, kiểm tra đồ thị import runtime và xem artifact `.next` hiện có. Bản build này có trước thay đổi, không phải phép đo sau build. Mọi số liệu bên dưới mô tả kịch bản kiểm thử xác định, không phải độ trễ trình duyệt.

## Vấn đề đã xác nhận và thay đổi đã triển khai

| Phạm vi | Vấn đề quan sát được và nguyên nhân | Trước | Sau | Bảo vệ / đánh đổi |
| --- | --- | --- | --- | --- |
| CI Listening | `renderWithLocale` đã cung cấp wrapper bền vững. `rerender` của kiểm thử chèn provider thứ hai, thay cây player. | Tệp kiểm thử player: 24 đạt, 1 lỗi. | Giữ cùng nút `audio` và player, thời gian phát, tốc độ, âm lượng, mute và UI phát khi đổi ngôn ngữ/bố cục/giao diện. | Giữ `toBe`, kiểm tra trạng thái phát và lời gọi media. Vẫn kiểm tra thay nguồn và giới hạn thi độc lập. Không cần sửa vòng đời player. |
| Header toàn cục | `HeaderBar key={pathname}` mount lại thông báo khi điều hướng. | Một lần đổi tuyến: 2 lời gọi danh sách và 2 lời gọi số chưa đọc, gồm mount đầu. | 1 lời gọi danh sách và 1 lời gọi đếm; giữ nút header. | ID tài khoản vẫn reset thông báo. Mở panel vẫn tải mới; không cache thông báo chung. Menu đóng khi điều hướng và vẫn đóng khi quay lại. |
| Đăng ký ngôn ngữ | Mọi thành phần dịch đều đăng ký toàn bộ context tùy chọn. | Chỉ đổi giao diện gây 1 render thêm của thành phần thăm dò bản dịch. | 0 render thêm. | Đăng ký ngôn ngữ riêng được memo hóa dùng cùng trạng thái tùy chọn chuẩn. Hàng đợi ghi, lỗi và đổi tài khoản giữ kiểm thử. |
| Trang chủ | Loader profile/admin độc lập chờ catalog/history kết thúc. | Khi catalog chưa xong, cả hai loader sau chưa chạy. | Cả hai chạy trước khi catalog xong, sau xác thực người dùng. | Cùng yêu cầu API/xử lý lỗi; đọc độc lập đồng thời. Không tuyên bố benchmark thời gian. |
| Catalog / Skill Practice | Loader danh sách gọi chi tiết riêng cho từng phiên bản đã xuất bản được chọn. Mỗi yêu cầu lặp tải đồ thị ORM. | Sáu bài Library hư cấu: 1 danh sách + 6 chi tiết = 7 lời gọi loader. | 1 danh sách, không gọi chi tiết, cùng 6 thẻ. Skill Practice cũng bỏ yêu cầu chi tiết bổ sung. | Bật tường minh `public_only=true&include_details=true`; dùng lại DTO `VersionDetail` không đáp án và chính sách công khai. Bên gọi ngoài catalog vẫn nhẹ. Thiếu tóm tắt nhúng vẫn dùng phương án dự phòng từng phiên bản hiện có. |
| Reading | Khối đoạn đọc render lại theo đồng hồ hiển thị và trạng thái lưu đáp án của runner. | Tăng timer 3 giây trong một đợt gây thêm một render văn bản đoạn đọc. | 0 render thêm trong lần tăng đó hoặc khi đáp án/lưu không liên quan đổi. | Callback/controller highlight ổn định và ranh giới đoạn đọc được memo hóa. Highlight/ngôn ngữ vẫn làm mất hiệu lực. DOM vẫn mount. |
| Ngôn ngữ Classroom | Callback lỗi đã dịch là phụ thuộc fetch. | EN→VI khiến Classwork và Stream mỗi phần gọi yêu cầu thứ hai. | Mỗi phần giữ 1 yêu cầu. | Lưu lỗi bắt được và dịch khi render. Vẫn giữ refresh tường minh, bộ lọc, mutation, hủy và thứ tự yêu cầu. |
| Tiến độ bài tập | Chữ ký ID phụ thuộc thứ tự và giá trị context nội tuyến lặp việc với đầu vào tương đương. | Đổi thứ tự/khử trùng cùng ID: 2 lời gọi tiến độ. | 1 lời gọi, không render thêm bên dùng context. | Tập ID chuẩn, context memo hóa. Giữ lượt đọc bắt buộc, lô 100-ID và refresh tường minh. Không cache dữ liệu riêng tư. |
| Tải mô-đun Classroom | Gradebook, analytics, plans, profiles là phụ thuộc tĩnh của workspace Stream mặc định. | Cả bốn đều có thể tới qua import runtime tĩnh. | Không phần nào thuộc đồ thị import tĩnh ban đầu. | Tải panel hiện có bằng `next/dynamic` khi chọn; trạng thái tải được dịch. Không đổi quyền, API dữ liệu hoặc điều khiển thi. Lần dùng đầu tải chunk panel. Chưa đo byte bundle hoặc thời gian trình duyệt. |
| So sánh Analytics | Chọn hai attempt tải toàn bộ lịch sử full-module và sự kiện điều hướng người dùng. | SQL lọc user/scope nhưng thiếu điều kiện ID đã chọn/trạng thái cuối. | SQL giới hạn hai ID, cùng chủ sở hữu/phạm vi, đã hoàn tất; bỏ tải sự kiện điều hướng không dùng. | Kiểm thử SQL biên dịch/loader. Dashboard vẫn tải sự kiện để tính thời gian. Khóa chính hiện có đủ; không migration/cache. |

Tải SQL catalog chia lô tối đa 100 ID phiên bản được chọn. Chẩn đoán không cần DB kiểm tra 250 ID thành các lô 100/100/50. Hồi quy PostgreSQL so đường cũ danh sách cộng chi tiết với đường catalog mới, xác minh DTO giống nhau và ít SELECT hơn (tối đa 20 cho fixture sáu bài). Cũng kiểm tra quyền thấy dữ liệu của học viên, chủ sở hữu và quản trị viên: phê duyệt chỉ Classroom, bản nháp, bài lưu trữ và bản ghi không được phép vẫn bị loại. Các kiểm tra có DB này được giao cho CI từ xa không đổi, không chạy trên DB development người dùng.

## Phát hiện kiểm toán khác và giới hạn

- `AuthProvider` được mount ở layout gốc; kiểm tra session ban đầu không phụ thuộc pathname. Context đã memo hóa, HTTP client đã gộp yêu cầu refresh. Refresh khi xác thực/đăng xuất phục vụ tính cập nhật và được giữ.
- Điểm vào Three.js hiện có dùng `import("./scene")` sau kiểm tra tùy chọn trình duyệt. Manifest tải được hiện có xác nhận chunk scene riêng. Kiểm thử đồ thị import nay giữ nó ngoài shell toàn cục. Không báo phần trăm giảm bundle bịa đặt.
- Classroom vốn chỉ render tab hoạt động và giữ provider tiến độ ngoài nội dung tab. Gradebook giới hạn trang học viên/bài tập, loader LMS hủy phản hồi lỗi thời. Không thêm cache giữ toàn bộ tab mount hoặc gói virtualization nặng.
- Writing giữ autosave có revision 750 ms, flush tường minh trước nộp và ranh giới hoàn tất telemetry. Đã xem quy trình thu âm/chunk Speaking và AI nhưng không đổi. Không có nút thắt thu âm/AI đã chứng minh để sửa vòng đời.
- Registry câu hỏi vẫn đưa editor Builder vào một số đường import bài thi; tách hợp đồng này cần công việc riêng cho editor/renderer. Catalog production lớn và dashboard analytics đầy đủ cũng cần đo runtime đại diện trước khi thiết kế lại phân trang/tổng hợp.
- Không suy ra độ trễ biên dịch development từ các kiểm thử này. Đo riêng điều hướng production, độ trễ API/kế hoạch SQL, tác vụ dài, bố cục, bộ nhớ và chunk tuyến đã nén trước khi chọn thay đổi tiếp.

## Kiểm tra hồi quy và tương thích

Kiểm thử frontend tập trung bao gồm điều hướng, shell, cá nhân hóa, thông báo, loader trang chủ, catalog/Skill Practice, điều hướng Reading/Listening, duy trì player, runner Writing, nội dung/LMS/analytics Classroom, tiến độ bài tập và ranh giới import. Kiểm thử Listening được chạy lặp. Harness cá nhân hóa nay chờ điều khiển tài khoản được bật trước tương tác, thay vì chạy đua với tải tùy chọn bất đồng bộ.

Kiểm tra backend Local chỉ dùng session giả và hợp đồng SQL/schema đã biên dịch. Đi kèm là TypeScript typecheck, ESLint trên tệp đổi, Ruff lint/format theo phạm vi và `git diff --check`. CI từ xa cung cấp toàn bộ bộ kiểm thử, migration, build production và kiểm thử trình duyệt Golden Path.

Không đổi chấm điểm, quy tắc mutation TestVersion, tham chiếu attempt lịch sử, thực thi deadline, hàng đợi autosave, tiến trình Full Mock, quyền Classroom, điểm cuối do người chấm, nhà cung cấp AI hoặc tuyến thông báo. Bổ sung chi tiết catalog công khai dùng quyền của yêu cầu hiện tại và DTO tóm tắt công khai hiện có; không thêm đáp án hoặc cache chung xuyên người dùng.
