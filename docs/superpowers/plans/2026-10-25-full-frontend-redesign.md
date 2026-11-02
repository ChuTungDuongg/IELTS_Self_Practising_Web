# Kế hoạch triển khai thiết kế lại toàn bộ frontend

> **Kiểm toán tài liệu: SUPERSEDED.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Kế hoạch triển khai thiết kế lại toàn bộ frontend. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../frontend/src/components/ui/app-shell.tsx).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/shared-platform.md); [kiểm toán và giới hạn](../../DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.

> **Dành cho agent triển khai:** Dùng superpowers:executing-plans để thực hiện các nhiệm vụ tại chỗ. Bản yêu cầu thực hiện chi tiết của người dùng cho phép tiếp tục triển khai mà không dừng xin duyệt. Không commit hoặc push.

**Mục tiêu:** Tạo cách trình bày nhất quán, dễ đọc và đáp ứng nhiều kích thước màn hình cho mọi màn hình BandPilot hiện có, đồng thời giữ hành vi nghiệp vụ.

**Kiến trúc:** Giữ Next.js, React, TypeScript, Tailwind v4 và cấu trúc CSS/thành phần toàn cục hiện có. Thêm stylesheet trình bày có phạm vi chủ đích sau stylesheet cũ, dùng token ngữ nghĩa dùng chung. Chỉ tinh chỉnh thành phần trình bày khi CSS không thể cải thiện tương tác. Không đổi API, backend, chấm điểm, xác thực, thời gian, lưu trữ hay schema nội dung.

**Công nghệ:** Next.js 16 / React 19, CSS và CSS module, Vitest / Testing Library, TypeScript và ESLint hiện có. Không thêm phụ thuộc.

**Đặc tả:** Bản yêu cầu thiết kế lại toàn ứng dụng của người dùng, cung cấp ngày 2026-10-25 trong `C:/Users/Admin/.codex/attachments/de1042bb-58c3-4860-b138-dd8b06c943b4/Pasted text.txt`.

## Định hướng thiết kế

Áp dụng quy tắc màn hình ứng dụng của Taste. Dùng định hướng workspace biên tập: các mép nội dung thẳng hàng, header tiết chế, tiêu đề trang 24–32px, một họ sans dễ đọc cho điều khiển và phông serif hiện có cho đoạn đọc/bài luận. Giữ biểu trưng BandPilot, quỹ đạo tương tác và bảng màu nhấn cá nhân hóa. Bề mặt trắng phẳng trên nền sáng trung tính; bề mặt graphite trên nền tối trung tính thực sự. Một thang khoảng cách (4/8/12/16/24/32/48), bán kính 6/10/14, viền điều khiển trung tính, focus rõ và phản hồi tiết chế. Thương hiệu hiện có là ngoại lệ tường minh đối với ưu tiên tím/chàm của Taste. Không bịa số liệu, tiến độ hay nội dung đề thi.

## Ràng buộc chung và quyết định

- Không dùng trình duyệt, Playwright, Cypress, E2E, toàn bộ bộ test, bản build production, commit hay push.
- Chỉ kiểm tra kiểu, test thành phần có mục tiêu, ESLint nhẹ và `git diff --check`.
- Làm trong checkout hiện có theo yêu cầu; giữ `.agents/` và `skills-lock.json` chưa được Git theo dõi từ trước.
- Chỉ áp dụng kiểu trình bày cho màn hình Speaking hiện có; không làm giai đoạn Speaking mới hay thay đổi chấm điểm.
- Giữ hợp đồng source/query, hạn chế mô-đun, khả năng tua trong bài thi, offset highlight, autosave, định danh, registry câu hỏi và mọi điều khiển hiện có.
- Không ẩn điều khiển soạn đề trên di động; bố trí lại để vừa màn hình. Không khóa overflow toàn body.
- Người dùng đã miễn tường minh việc kiểm tra trình duyệt và chấm điểm ảnh chụp bằng giới hạn kiểm chứng. Không tuyên bố đã kiểm chứng thị giác.
- Tinh chỉnh thuần CSS dùng kiểm tra CSS tĩnh và test tập trung hiện có. Hành vi tương tác mới phải có test tập trung trước; không viết test chỉ lặp lại khai báo trang trí.

## Trọng tâm rà soát

1. Điều hướng di động: mở, Escape, trả focus và chọn tuyến phải giữ mọi đích đến theo role truy cập được.
2. Bố cục bài thi: các khung độc lập trên desktop, nguồn/câu hỏi truy cập được ở màn hình hẹp, không vô tình đổi hạn chế media đang bị vô hiệu hóa.
3. Theme: biến ngữ nghĩa phải áp dụng tới bài thi, highlight qua portal, dialog và CSS module mà không render phụ thuộc theme.
4. Dữ liệu thực: ngày trên biểu đồ và trạng thái rỗng phải trung thực; lỗi hiện có không được lộ nguyên văn exception.
5. Soạn đề và review: mọi họ câu hỏi, điều khiển, chú thích, chấm điểm và kết quả đánh giá đã lưu vẫn có mặt.

## Danh mục tuyến và danh sách kiểm tra bao phủ

Mọi tuyến `src/app/**/page.tsx` thực tế, nhóm theo nơi sở hữu phần trình bày:

- [x] Trang chủ/dashboard: `/` — tổng quan, mục tiêu, chỉ số, lộ trình học và quỹ đạo tương tác.
- [x] Tài khoản: `/login`, `/register`, `/session/restore`, `/profile`, `/settings/personalization`.
- [x] Học tập: `/library`, `/library/[versionId]`, `/practice`.
- [x] Bài thi: `/attempt/[attemptId]` — Reading, Listening, Writing, Speaking; mọi renderer câu hỏi tập trung và highlight.
- [x] Thi thử và review: `/test-session/[sessionId]`, `/review/[attemptId]`, `/history`.
- [x] Tiến độ: `/analytics`.
- [x] Quản trị: `/admin`, `/admin/users/[userId]`, `/admin/moderation`, `/admin/moderation/[requestId]`, `/admin/writing-benchmark`.
- [x] Quản lý đề: `/admin/tests`, `/admin/tests/new`, `/admin/tests/[testId]`, `/teacher/tests`, `/teacher/tests/new`.
- [x] Builder/preview: `/admin/tests/[testId]/versions/[versionId]/{edit,preview}`, `/teacher/tests/[testId]/versions/[versionId]/{edit,preview}`.
- [x] Lớp học: `/classrooms`, `/classrooms/[classroomId]`, `/teacher/classrooms`, `/teacher/classrooms/[classroomId]`.
- [x] Kết quả lớp học: cả hai biến thể `/classrooms` và `/teacher/classrooms` của `/[classroomId]/assignments/[assignmentId]/results` và `/results/[attemptId]`.
- [x] Chuyển dữ liệu: `/transfer`.
- [x] Dùng chung: header/footer, tiêu đề, nút, trường, badge, dialog, overlay cá nhân hóa, menu thông báo, popover highlight, trạng thái tải/rỗng/lỗi, phân trang, tìm kiếm, bộ lọc và tab.

## Nhiệm vụ 1 — Nền tảng dùng chung và shell

Tệp: `src/app/layout.tsx`, tệp mới `src/app/design-system.css`, `src/components/ui/global-header.tsx`, `src/components/ui/app-shell.tsx`, `src/components/ui/app-footer.tsx`, thông báo bản địa hóa, test shell tập trung.

- [x] Kiểm tra giao diện thành phần hiện có và hướng dẫn CSS Next đã cài.
- [x] Thêm test điều hướng di động tập trung đang thất bại, rồi triển khai mở/đóng, đóng bằng bàn phím và xử lý focus mà không đổi logic truy cập tuyến.
- [x] Thiết lập token bề mặt/văn bản/điều khiển/trạng thái ngữ nghĩa trong cả hai theme; giữ màu nhấn cá nhân hóa và hỗ trợ alias biến cũ.
- [x] Thống nhất nút, trường, panel, bề mặt nổi, focus và giảm chuyển động; giữ mọi giao diện hiện có.
- [x] Bố trí lại điều hướng trên tablet/di động; giữ nhãn và mọi đích đến theo role.
- [x] Kiểm chứng test shell cùng TypeScript.

## Nhiệm vụ 2 — Màn hình trang chủ, học tập và tài khoản

Tệp: thành phần tổng quan, trình duyệt bài luyện và thành phần thư viện, selector CSS xác thực/tài khoản, bản dịch và test thành phần tập trung.

- [x] Giữ quỹ đạo tương tác; cân đối lại hero quanh hành động học và dữ liệu mục tiêu thực tế.
- [x] Thêm liên kết trực tiếp hữu ích tới kỹ năng với lựa chọn ban đầu theo URL; kiểm chứng chọn kỹ năng từ URL và hành vi lọc thông thường.
- [x] Cải thiện khả năng đọc lướt thư viện, metadata mô-đun, điều khiển bắt đầu, dải tiến độ và trạng thái rỗng.
- [x] Tinh chỉnh đăng nhập/đăng ký, khôi phục, hồ sơ và cá nhân hóa bằng hành vi/điều khiển hiện có.
- [x] Thêm phần trình bày tải/lỗi tuyến nhẹ, tái sử dụng được theo quy ước Next đã cài, cùng test thử lại tập trung.
- [x] Kiểm chứng test trang chủ/thư viện/tài khoản có mục tiêu.

## Nhiệm vụ 3 — Bài thi, thi thử đầy đủ và review

Tệp: trình bày runner Reading/Writing, stylesheet trình bày dùng chung, markup câu hỏi/editor hiện có chỉ khi cần, CSS module phản hồi Writing, CSS module bài luận có chú thích.

- [x] Kiểm tra shell Reading, Listening, Writing, Speaking, renderer câu hỏi, mọi điều hướng, bộ đếm thời gian, autosave, âm thanh, highlight và markup review.
- [x] Tinh chỉnh header bài thi, khung nguồn/câu hỏi, điều khiển đáp án, điều hướng, phản hồi lưu/cờ/trạng thái, player và khung media.
- [x] Cung cấp bộ chuyển khung Reading cho màn hình nhỏ, giữ cả hai vùng DOM được mount và vị trí cuộn độc lập; viết test tương tác tập trung trước khi triển khai.
- [x] Cải thiện đề/editor Writing và thứ bậc phản hồi, panel tiêu chí, bằng chứng, tiến độ, đánh giá đã lưu và chú thích. Hiển thị mọi văn bản AI qua cơ chế render an toàn hiện có.
- [x] Tinh chỉnh kiểu trình bày Speaking và chuyển tiếp/kết quả full mock mà không đổi hành vi.
- [x] Kiểm chứng điều hướng Reading/Listening tập trung, runner/phản hồi AI Writing và hợp đồng thành phần full mock.

## Nhiệm vụ 4 — Tiến độ, lịch sử và quản lý

Tệp: thành phần analytics, selector history/test-builder/classroom/admin/transfer, CSS module benchmark, test analytics tập trung.

- [x] Dùng timestamp được cung cấp trong biểu đồ xu hướng band có nhãn, truy cập được; giữ dữ liệu API và phép tính. Test nhãn ngày và dữ liệu truy cập bằng bàn phím trước khi triển khai.
- [x] Tinh chỉnh nhóm lịch sử và tóm tắt kết quả, giữ mọi hành động/dialog.
- [x] Kiểm tra và tinh chỉnh danh sách đề, mọi builder mô-đun, editor họ câu hỏi, validation/autosave, media, preview, import/export, người dùng/kiểm duyệt admin và quy trình lớp học.
- [x] Tinh chỉnh ngân hàng và phân phối benchmark, bảng/phân trang nhất quán và bố trí lại trên tablet/di động.
- [x] Kiểm chứng test thành phần analytics, lịch sử, điều hướng builder và editor đại diện.

## Nhiệm vụ 5 — Nhất quán, kiểm chứng và báo cáo

- [x] Rà soát selector/thành phần đã đổi theo mọi nhóm tuyến trên; đánh dấu bao phủ chính xác.
- [x] Kiểm tra tương ứng giữa hai theme, nhãn trạng thái có ý nghĩa, focus bàn phím, kích thước chạm, xuống dòng, truy cập khung responsive, overlay đặc và giảm chuyển động.
- [x] Chạy TypeScript, ESLint trên tệp TS/TSX đã đổi và `git diff --check`.
- [x] Chỉ chạy nhóm test đơn vị/thành phần tập trung liên quan tới tương tác đã đổi; ghi đúng lệnh/kết quả.
- [x] Yêu cầu một lượt review mã độc lập mới cho toàn bộ diff chưa commit; sửa phát hiện đáng kể rồi chạy lại kiểm tra tập trung tương ứng.
- [x] Báo cáo thay đổi mã nguồn riêng với bố cục chưa kiểm chứng bằng trình duyệt. Giữ bản kế hoạch làm hồ sơ tiến độ và tiếp tục công việc.

## Hồ sơ thực hiện

- Chuẩn bị: đọc Taste Skill và tài liệu màn hình ứng dụng, AGENTS root/frontend, tài liệu Next cục bộ về CSS/tải/lỗi; kiểm tra danh mục tuyến và token/thành phần hiện có. Bắt đầu typecheck mốc ban đầu cùng bốn tệp thành phần đại diện trước khi sửa.
- Quyết định: bản yêu cầu chi tiết chỉ dẫn tường minh triển khai sau khi lập kế hoạch; tiếp tục mà không hỏi duyệt thiết kế/kế hoạch tùy chọn trong skill. Không được phép làm xác thực hay chấm điểm mới.
- Quyết định: làm tại chỗ, không thao tác thay đổi Git. Quy trình cô lập và commit sẽ trái với yêu cầu thay đổi chưa commit có thể review và ý định dùng workspace hiện tại của người dùng.


## Hồ sơ bao phủ và kiểm chứng cuối cùng

Mọi tuyến trang hiện có, tổng cộng 37, đều được bao phủ bởi stylesheet trình bày dùng chung và selector theo khu vực ứng dụng liệt kê trên. Luồng tài khoản và quản lý giữ thành phần/hành vi hiện có. Thay đổi markup/tương tác có mục tiêu chỉ gồm điều hướng, tiếp tục attempt đang hoạt động, chọn kỹ năng trực tiếp, chuyển khung Reading, dữ liệu xu hướng dễ đọc và phản hồi tải/thử lại. CSS module đánh giá Writing và benchmark được tinh chỉnh riêng.

Định hướng Taste: editorial-greeting, seed 25102026, giữ bảng màu/kiểu chữ hiện có. Chất liệu riêng của sản phẩm là attempt thực tế hiện tại và bốn mục tiêu kỹ năng của người học; quỹ đạo hiện có giữ tương tác con trỏ. Giữ điều hướng ngang hiện tại thay vì thêm sidebar. Không tuyên bố có ảnh chụp hay điểm đánh giá thị giác.

Các kiểm tra đã thực hiện (thư mục frontend, gọi trực tiếp điểm vào Node vì npm không nằm trong PATH của máy này):

| Nhóm kiểm tra tập trung | Kết quả |
| --- | --- |
| app-shell, điều hướng Reading, điều hướng Listening, mốc đánh giá AI Writing | 214 PASS trước khi sửa |
| Điều hướng Reading, luyện kỹ năng, analytics, mở/đóng điều hướng | 65 PASS tại thời điểm đó |
| Chỉ số/tiếp tục bài ở trang chủ và luyện kỹ năng | 45 PASS |
| Ngày analytics, bảng văn bản, bản địa hóa và phản hồi lỗi/thử lại | 5 PASS |
| app-shell, thư viện, layout root, cá nhân hóa | 132 PASS với một kỳ vọng menu shell lỗi thời; đã cập nhật kỳ vọng cho điều khiển Menu mới được phép và kiểm tra lại shell bên dưới |
| Phản hồi trang, điều hướng Listening, player Listening, runner Writing | 97 PASS |
| Đánh giá AI Writing, bài luận có chú thích, ngân hàng benchmark, chuyển tiếp mock | 103 PASS |
| Điều hướng Builder, UI giáo viên/lớp học, lịch sử attempt, transfer | 57 PASS |
| Hợp đồng CSS responsive cuối cùng, mở/đóng menu, shell, điều hướng Reading | 107 PASS |
| Điều hướng Listening sau bản sửa responsive, cùng hợp đồng shell/CSS | 133 PASS và 1 assertion phần tử cũ thất bại; đã sửa assertion và kiểm tra riêng lại hợp đồng menu/CSS: 5 PASS |
| TypeScript, lần chạy cuối | PASS, không lỗi |
| ESLint trên mọi nguồn/test TS/TSX đã đổi | PASS, không lỗi hay cảnh báo |
| Biên dịch Lightning CSS stylesheet dùng chung và ba CSS module đã đổi (đúng chế độ CSS module) | PASS, không cảnh báo |
| Độ tương phản token văn bản/bề mặt ngữ nghĩa mới, tính từ mã nguồn | chữ chính sáng 15.55:1; chữ phụ sáng 5.03:1; chữ chính tối 14.61:1; chữ phụ tối 6.38:1 |
| git diff --check | PASS |

Taste lint mã nguồn báo 0 FAIL và 36 WARN. Cảnh báo nhận diện khai báo như box-shadow: none và backdrop-filter: none theo mẫu; bóng thực tế chỉ giới hạn ở panel nổi và phân đoạn được chọn nhẹ. Đây là kiểm tra mã nguồn, không phải trình kiểm tra trình duyệt đang bị cấm.

### Review mới và các bản sửa

Một reviewer độc lập chỉ đọc đã xem diff được Git theo dõi, tệp nguồn mới, ràng buộc và CSS cũ. Cả bốn phát hiện P2 cần xử lý đều được tái hiện và sửa:

1. Hiển thị Menu trên desktop: quy tắc display icon dùng chung ghi đè quy tắc ẩn trước đó. Đã đổi thứ tự quy tắc ẩn; kiểm tra hồi quy xét kiểu đang áp dụng trên desktop và điện thoại.
2. State menu cũ: quay lại đường dẫn từng mở làm điều hướng bung lại. Đã chuyển state mở/đóng vào thanh header có key theo pathname; tương tác đi rồi quay lại nay vẫn đóng.
3. Cờ Listening bị cắt: track chip cố định trên di động vượt cột Listening hẹp. Giữ track số linh hoạt, track cờ 32px và lưới câu hỏi di động hai cột, với chiều cao điều khiển 44px.
4. Bộ lọc tablet: kiểu bộ lọc ba cột cũ bị ép vào sidebar 180px. Thêm mốc sidebar một cột tường minh; di động giữ bố cục gọn riêng.

Cuối cùng: cả bốn hồi quy review đều RED→GREEN. Không có phát hiện review mã bị hoãn.

### Quyết định và giới hạn còn lại

- Quyết định: thực hiện trong checkout hiện tại, không commit, tạo branch hay worktree, vì bản yêu cầu muốn triển khai trực tiếp có thể review. Mọi tệp người dùng chưa được Git theo dõi từ trước đều được giữ.
- Quyết định: dùng màu thương hiệu/cá nhân hóa và kiểu chữ hiện có thay vì thay tùy chọn người dùng; thể hiện Taste qua thứ bậc bề mặt, thang kích thước, khoảng cách, nhấn dữ liệu và điều khiển tiết chế.
- Quyết định: kiểm tra CSS/mã nguồn gốc và test thành phần tập trung thay cho kiểm tra trình duyệt theo giới hạn tường minh của người dùng. Phần còn lại: hình học viewport thực tế, cuộn/chọn, bố cục media và tương phản pixel cần lượt kiểm tra thị giác bằng người/trình duyệt sau này.
- Quyết định: lỗi tải tuyến nay vẫn là lỗi, không biến thành tổng bằng không/tập rỗng bịa ra. Tải Practice một phần giữ nội dung thành công và hiện phản hồi thử lại. Không đổi hợp đồng API.
- Không chạy: trình kiểm tra trình duyệt/ảnh chụp, test trình duyệt/E2E, toàn bộ bộ test hay build production. Không đưa ra tuyên bố về kết quả của các bước đó.
- Tiếp tục: khi được phép kiểm chứng bằng trình duyệt, kiểm tra mọi nhóm tuyến ở 1440, 768 và 390px trong cả hai theme; ưu tiên đoạn Reading dài, bản đồ/dock âm thanh Listening, bằng chứng/chú thích Writing, builder, kết quả lớp học và overlay đang mở. Giữ thay đổi hiện tại và dùng tài liệu này làm bản đồ bao phủ.
