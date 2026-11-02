# Danh sách kiểm tra triển khai frontend Gravity IELTS

> **Kiểm toán tài liệu: SUPERSEDED.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Danh sách kiểm tra triển khai frontend Gravity IELTS. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../frontend/src/components/ui/app-shell.tsx).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/shared-platform.md); [kiểm toán và giới hạn](../../DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.

Đặc tả: `docs/design-references/ielts_gravity_codex_master_prompt.md` (đủ 940 dòng, gồm phụ lục gốc).

## Định hướng và ranh giới

BandPilot giữ thương hiệu la bàn, dữ liệu học tập thực, Next.js/React/TypeScript và API client hiện tại. Trang chủ chuyển trình tự chuyển động khối cầu cobalt → lime → rose của Gravity thành bốn thông điệp: luyện tập có mục tiêu, bốn kỹ năng, học từ review và chuẩn bị thi thử đầy đủ. Quả cầu CSS hiện có chỉ mang tính trang trí; hợp nhất vào một cảnh Three.js tải khi cần. Màn hình nội bộ dùng cùng bề mặt slate, điều khiển bo góc và kiểu chữ chính xác, không dùng WebGL hay hiệu ứng cuộn. Màu nhấn tài khoản, locale và tùy chọn sáng/tối hiện có vẫn quyết định cách hiển thị.

Bản yêu cầu chính ghi đè tường minh các hạn chế thường lệ của Taste về gradient, nhãn mono và glass cho trang chủ theo mẫu tham chiếu. Không lấy định hướng ngẫu nhiên thay mẫu người dùng đã chọn. Sau đó người dùng cho phép kiểm thử trình duyệt, đồng bộ dữ liệu từ Modal sang Docker và commit/push thay đổi hoàn tất trực tiếp vào `main`. Tự động hóa E2E, build production và bộ kiểm thử dài vẫn ngoài phạm vi kiểm tra yêu cầu. Giữ bản sửa 401 trang chủ cùng test hồi quy có sẵn chưa commit. Không sửa `.agents/`, `.taste-skill/`, `skills-lock.json` không liên quan và tài liệu tham chiếu thiết kế được cung cấp.

## Danh sách kiểm tra

- [x] A: Đọc prompt chính, phụ lục gốc, Taste Skill và quy tắc repository.
- [x] A: Lập danh mục đủ 37 tuyến trang, shell dùng chung, theme, quả cầu, bề mặt runner/review/editor và test tập trung.
- [x] B: Nền tảng slate/cobalt dùng chung, theme tối dễ đọc, điều khiển, shell, focus và trạng thái.
- [x] C: Phụ thuộc Three.js được quản lý và lõi vật lý xác định có kiểu.
- [x] C: Renderer chỉ chạy client, vật liệu glass/matte, ánh sáng, cụm cầu → rơi/nảy → trái tim → đi qua ống kính, động lượng con trỏ.
- [x] C: Bốn phần IELTS responsive, tuyến thực, chỉ số/mục tiêu/tiếp tục bài được cá nhân hóa hiện có và footer.
- [x] C: Phương án tĩnh/không JS/dự phòng WebGL, giảm chuyển động, tạm dừng, ngừng chạy khi ẩn/ngoài màn hình, dọn tài nguyên và chất lượng cho thiết bị công suất thấp.
- [x] D: Xác thực, hồ sơ và cá nhân hóa.
- [x] D: Thư viện/luyện tập, analytics và dashboard.
- [x] D: Reading, Listening, Writing, Speaking, thi thử và review.
- [x] D: Lịch sử, admin/test builder, benchmark, lớp học/quản trị và chuyển dữ liệu.
- [x] E: Kiểm tra đơn vị/thành phần tập trung, TypeScript, lint nhẹ, kiểm tra CSS và xác nhận khoảng trắng diff.
- [x] E: Bao phủ tuyến và báo cáo trung thực giới hạn cuối cùng.
- [x] Theo dõi tiếp: đồng bộ cơ sở dữ liệu phát triển Modal đã dừng và asset vào Docker cục bộ, sao lưu cục bộ trước khi thay thế.
- [x] Theo dõi tiếp: đối chiếu số lượng bản ghi của đủ 47 bảng và kích thước đủ 154 tệp asset với bản export; xác nhận Alembic head `20261013_0035`.
- [x] Theo dõi tiếp: quan sát HTTP 200 ở trang chủ/lịch sử đã xác thực sau khi người dùng đăng nhập bình thường.
- [x] Theo dõi tiếp: kiểm tra ảnh chụp trình duyệt thực ở 1440×900, 768×1024 và 390×844; sửa footer xếp chồng, ticker xuống dòng, chữ hero bị che và canvas tràn vào workspace học tập. Kiểm chứng điều khiển tạm dừng/tiếp tục ticker.
- [ ] Kiểm chứng thiết bị còn lại: WebGL chuyển động bình thường trên GPU thật, hiệu năng chạm/FPS/bộ nhớ, hình thức tương ứng giữa theme/ngôn ngữ và màn hình bài thi/editor đã xác thực. Trình duyệt dùng kiểm tra yêu cầu giảm chuyển động và đúng là giữ phương án tĩnh dự phòng.

Bàn giao qua Git là thao tác cuối, được cho phép tường minh trên `main`; phản hồi chat cuối ghi kết quả thực tế.

## Đơn vị triển khai

1. `components/home/gravity/physics.ts`: sinh vật thể xác định, ngưỡng chế độ theo mẫu, lấy mẫu hình trái tim, bộ giải va chạm và biên; test số học tập trung.
2. `components/home/gravity/scene.ts`: renderer và vòng đời tài nguyên; bước thời gian cố định, chất lượng có giới hạn và quyền quản lý sự kiện DOM. `gravity-field.tsx` chỉ tải khi cần sau khi kiểm tra tùy chọn; hình tĩnh vẫn nằm phía sau.
3. `gravity-landing.tsx` + `gravity-home.css`: bốn phần IELTS thực, cuộn gốc, hiệu ứng hiện bằng IO, điều khiển chuyển động cục bộ; `overview-content.tsx` giữ nội dung workspace thực. Văn bản Anh/Việt đi qua từ điển hiện có.
4. Hợp đồng bố cục `design-system.css` hiện có được mở rộng bởi `gravity-product.css`: trình bày dùng chung và theo khu vực; giữ API bố cục/lưu trữ/media runner và hành vi editor. CSS module Writing/benchmark dùng cùng token.
5. Test tập trung bao phủ pha vật lý/va chạm/trái tim/con trỏ, hồi quy trang chủ không có phiên, phương án dự phòng/tùy chọn/vòng đời, điều hướng và quy trình runner hiện có. Không tuyên bố về hiệu năng GPU/trình duyệt hay ảnh chụp.

## Bao phủ tuyến

Cả 37 tuyến đều được review mã nguồn/thành phần và áp dụng lượt tinh chỉnh trình bày dùng chung. Kiểm tra trình duyệt tiếp theo bao phủ trang chủ và đăng nhập; trang chủ đã xác thực của người dùng cũng tải thành công. Phần lớn tệp tuyến nội bộ được chủ đích giữ nguyên: thành phần hiện có kế thừa token tinh chỉnh và quy tắc riêng theo khu vực. Danh mục tuyến không có nghĩa cả 37 tuyến đã được kiểm chứng bằng trình duyệt.

| Khu vực thực tế | Số tuyến trang | Trình bày đã triển khai |
| --- | ---: | --- |
| `/` | 1 | Bốn phần Gravity; khối cầu sinh bằng thuật toán; liên kết kỹ năng thực; tiếp tục attempt đã lưu; mục tiêu/chỉ số cá nhân hóa; lời mời khách thay cho chỉ số bằng không không khả dụng; ticker và chữ thương hiệu ở footer. |
| `/login`, `/register`, `/session/restore`, `/profile`, `/settings/personalization` | 5 | Bố cục xác thực chia vùng; khoảng cách form và validation dễ đọc; yêu cầu tối thiểu mật khẩu hiện có được mô tả cho công nghệ hỗ trợ; card tài khoản, modal, lựa chọn màu nhấn và trạng thái phiên. |
| `/library`, `/library/[versionId]`, `/practice` | 3 | Card đề, metadata, bộ lọc kỹ năng, tiêu đề chi tiết và lối vào thi thử đầy đủ; liên kết query của cả bốn kỹ năng dùng bộ lọc luyện tập hiện có. |
| `/history`, `/analytics` | 2 | Tab, hàng/card attempt, xác nhận, thống kê thực, khung biểu đồ, so sánh và trạng thái lỗi/rỗng. |
| `/attempt/[attemptId]`, `/review/[attemptId]`, `/test-session/[sessionId]` | 3 | Chữ và điều khiển Reading/Listening/Writing/Speaking, trạng thái thời gian/lưu tiết chế, bề mặt đoạn đọc/câu hỏi, thứ bậc điểm, chuyển tiếp thi thử và review. Khung Writing cuộn vẫn giữ hành động Save truy cập được trong cửa sổ thấp. |
| `/admin`, `/admin/users/[userId]`, `/admin/tests`, `/admin/tests/new`, `/admin/tests/[testId]`, sửa/preview phiên bản, `/admin/writing-benchmark`, danh sách/chi tiết kiểm duyệt, `/transfer` | 11 | Thống kê, bảng, điều hướng editor cục bộ, nhóm nội dung, điều khiển đáp án, validation, danh sách/editor benchmark, phân phối, card quản trị và panel chuyển dữ liệu. |
| `/teacher/tests`, `/teacher/tests/new`, sửa/preview phiên bản | 4 | Cùng hệ thống builder/điều khiển dùng chung, gồm đủ bốn editor mô-đun và preview. |
| `/classrooms`, `/teacher/classrooms`, cả hai tuyến chi tiết, cả hai nhóm danh sách/chi tiết kết quả bài giao | 8 | Tiêu đề, card, bảng, thông báo, dialog và phân trang dùng chung; giữ ranh giới role và kết quả hiện có. |

## Tệp quan trọng

- `frontend/src/components/home/gravity/{physics.ts,scene.ts,load-scene.ts,gravity-field.tsx,gravity-landing.tsx}` lần lượt sở hữu vật lý, vòng đời GPU, tải khi cần, phần tăng cường và nội dung IELTS.
- `frontend/src/app/gravity-home.css` sở hữu trang chủ theo mẫu tham chiếu; `gravity-product.css` mở rộng hệ thống thiết kế dùng chung hiện có cho màn hình nội bộ.
- `components/home/overview-content.tsx` giữ chỉ số/mục tiêu thực và tách dữ liệu đã đăng nhập khỏi lời mời khách. `app/page.tsx` giữ bản sửa khởi động không có phiên trước đó.
- `components/ui/{app-shell,app-footer}.tsx`, `features/auth/auth-form.tsx` cùng CSS module đánh giá/chú thích Writing và benchmark hiện có điều chỉnh bề mặt thực tế của chúng.
- `lib/i18n/{en,vi}.ts` cung cấp văn bản mới qua hệ thống locale hiện tại. `app/layout.tsx` import stylesheet và phông tiêu đề tự lưu trữ.
- `frontend/package.json` và `package-lock.json`: một bản runtime `three@0.186.1`, `@types/three` và `@fontsource-variable/raleway@5.3.0`. Không có framework UI/vật lý/hoạt ảnh cạnh tranh.

## Điều chỉnh mẫu tham chiếu và phương án dự phòng

- Vật lý giữ FOV camera 38 / z 11, phơi sáng ACES 1.15, phân phối bán kính/khối lượng theo mẫu, xác suất glass 22%, 4 lượt xử lý tiếp xúc, lực hút/giảm chấn/động lượng con trỏ và ngưỡng cuộn theo mẫu. Seed 25102026 giúp tái tạo trường vật thể sinh bằng thuật toán.
- Cuộn gốc của tài liệu điều khiển tiến độ tương đối theo section để section cao hơn trên điện thoại vẫn đồng bộ. Không chặn sự kiện bánh xe và không có hiệu ứng cuộn trên tuyến bài thi/workspace.
- Canvas sticky trong câu chuyện trang chủ thay vì cố định toàn cục. Nó không thể tiếp tục nằm sau workspace học tập, tuyến khác hay bài thi. Tệp `BrandOrbit` cũ được giữ nhưng không còn mount; tương tác con trỏ trang trí được hợp nhất vào trường cầu.
- Số lượng desktop/di động/công suất thấp: 96/54/32. Phân đoạn hình học: 48/28/20. Giới hạn DPR: 1.75/1.25/1. Shadow map desktop dùng 1024². Chế độ công suất thấp bỏ sinh môi trường studio và bóng. Vật liệu glass/matte cùng ánh sáng/phản chiếu studio sinh bằng thuật toán vẫn được giữ.
- Vật lý chạy cố định 60 Hz, tối đa ba nhịp bắt kịp. Render tạm dừng khi ẩn/ngoài màn hình hoặc được dừng thủ công, rồi ngủ sau khi mọi khối cầu đã đi qua ống kính. Cuộn ngược khôi phục trường cầu; vật thể đã thả được đưa về vị trí chờ để tọa độ không tăng vô hạn.
- Cầu CSS tĩnh, mọi tiêu đề và liên kết được render ở server. Chế độ giảm chuyển động và Save-Data bỏ tải Three.js. Lỗi GPU/import và timeout khởi tạo 8 giây giữ trường tĩnh sử dụng được. Không có màn hình tải chặn hay bộ đếm tiến độ bịa ra.
- Nút Pause/Resume và Scatter cho phép tương tác bằng bàn phím/chạm. Ticker footer có điều khiển tạm dừng riêng. Thay đổi tùy chọn media và remount Strict Mode giải phóng tài nguyên đúng cách; tạm dừng thủ công vẫn giữ qua thay đổi tùy chọn.
- Renderer, vật liệu, hình học cầu/sàn dùng chung, environment target, shadow map, rAF, listener và observer được giải phóng, kể cả khi khởi tạo thất bại. Test đơn vị dùng GPU giả lập, không tuyên bố đã kiểm chứng driver/thiết bị.
- Raleway được tự lưu trữ (Latin 48,264 byte; tiếng Việt 11,384 byte), cùng phông thân bài hệ thống và dự phòng mono hiện có. Không có request Google Fonts/CDN lúc chạy hay ảnh/mô hình/texture bên ngoài. Hình sinh bằng thuật toán theo mẫu người dùng chọn; không lấy hạn ngạch ảnh stock hay định hướng Taste ngẫu nhiên thay thế.
- Chủ đích bỏ drawer bảng màu tùy chọn: điều khiển màu nhấn/theme tài khoản hiện có vẫn là hệ thống tùy chọn toàn cục duy nhất. Màu tham chiếu áp dụng cho cảnh trang chủ; màu nhấn người dùng vẫn chi phối điều khiển sản phẩm.

## Hồ sơ kiểm chứng

Mọi kiểm tra được phép bên dưới đều PASS. Các nhóm chồng lặp; không cộng số lượng thành tổng test riêng biệt.

| Kiểm tra | Kết quả |
| --- | --- |
| Trang chủ, xác thực, shell, vật lý ban đầu (4 tệp tập trung) | 137 PASS |
| Điều hướng Reading/Listening, player, runner Writing, chuyển tiếp mock, hợp đồng responsive (6 tệp) | 126 PASS |
| Đánh giá AI Writing, lịch sử, autosave builder, trang benchmark (4 tệp) | 115 PASS |
| Runner Speaking, UI giáo viên/lớp học, transfer, analytics, cá nhân hóa (5 tệp) | 76 PASS |
| Vật lý cuối cùng, vòng đời cảnh, quyền sở hữu tài nguyên với GPU giả lập, render server, trang chủ và hợp đồng responsive (6 tệp) | 36 PASS |
| Export của gói stylesheet và hồi quy tệp phông được tham chiếu (1 tệp) | 2 PASS; lỗi import subset ban đầu đã được tái hiện thành test thất bại trước khi sửa |
| TypeScript `tsc --noEmit` | PASS sau thay đổi mã cuối cùng |
| ESLint trên TS/TSX đã đổi và test tập trung | PASS sau thay đổi mã cuối cùng |
| Lightning CSS: 2 stylesheet mới + 3 CSS module đã đổi | Phân tích thành công, không cảnh báo |
| Kiểm tra lockfile | Đúng một bản runtime Three.js |
| Tương phản màu trong mã nguồn | Chữ thân bài sáng 14.95:1, chữ phụ 5.31:1; chữ thân bài tối 14.50:1, chữ phụ 7.84:1; chữ chính hero 11.41:1 và nội dung 6.82:1 trên nền xanh; chữ phụ footer 9.24:1 |
| `git diff --check` | PASS; Git chỉ báo chuyển LF→CRLF thông thường |

Test hồi quy đã tái hiện và sửa xử lý API khách/chỉ số bằng không, tiếp tục khi vào lại màn hình, thay đổi tùy chọn khi dừng thủ công và độ ổn định khi giữ trạng thái thả lâu. Test tập trung không thay thế kiểm chứng bố cục/render trình duyệt hay dữ liệu thật.

Trong lần xem trước cục bộ của người dùng, Next.js báo thiếu `@fontsource-variable/raleway/latin.css` và `vietnamese.css`. Gói phông biến thiên đã cài cung cấp `index.css`, không cung cấp các điểm vào subset đó. `layout.tsx` nay import điểm vào root được gói hỗ trợ; dải Unicode bao phủ Latin và tiếng Việt, trình duyệt tải subset phông cần thiết. Kiểm tra TypeScript/lint/phân tích CSS trước đó không phát hiện lỗi phân giải mô-đun này. Test hồi quy tập trung mới phân giải mọi import stylesheet trong layout và kiểm tra mọi tệp phông nhị phân được tham chiếu. `/login` và `/` trên server cục bộ hiện có đều trả HTTP 200 sau khi sửa, không còn phản hồi module-not-found; phản hồi trang chủ chứa markup câu chuyện Gravity. Đây là kiểm chứng HTTP/SSR, không phải kiểm chứng trình duyệt.

## Theo dõi bản xem trước cục bộ, 2026-10-25

Cơ sở dữ liệu cục bộ ban đầu ở `20261012_0032`, chậm hơn model backend cùng bảng điểm Speaking/cột luyện tập. Trang chủ đã xác thực thất bại qua `getHistory`. Người dùng yêu cầu đồng bộ dữ liệu Modal vào Docker. Ứng dụng `modal serve` đã dừng gần nhất dùng workspace `tungduong156glis` và volume `ielts-web-postgres-dev`. Một tác vụ export tạm chỉ dùng CPU mount cơ sở dữ liệu đó cùng `ielts-web-assets` ở chế độ chỉ đọc, chép dữ liệu PostgreSQL đã dừng sang vùng lưu trữ tạm, tạo bản dump PostgreSQL logic và tệp nén asset. Volume nguồn không bị sửa.

Cả hai server cục bộ đều dừng khi sao lưu/khôi phục. Cơ sở dữ liệu và asset trước đồng bộ được giữ tại đường dẫn bị Git bỏ qua `backups/modal-to-local/20261025-sync/local-before/2026-10-25T125544Z-ee53dd5d`. Bản export tải về nằm trong thư mục cùng cấp `source/` cũng bị Git bỏ qua. Checksum hợp lệ trước khi khôi phục. Cơ sở dữ liệu đã khôi phục có schema `20261013_0035`, 3 người dùng, 4 đề và 10 attempt. Số lượng của đủ 47 bảng public khớp trước hoạt động đăng nhập/phiên tiếp theo, và đủ 154 tệp asset export (234,120,157 byte) có mặt với kích thước đúng. `alembic upgrade head` xác nhận không cần migration thêm. Cặp server hiện có được khởi động lại bằng `npm run dev`.

Sau lần đăng nhập bình thường của người dùng, log server cục bộ cho thấy HTTP 200 với `/api/v1/history`, `/api/v1/tests`, `/api/v1/auth/profile`, `/api/v1/admin/stats` và `/`. Không thêm catch-all để che lỗi backend. Không có thông tin đăng nhập, bản dump cơ sở dữ liệu, nội dung đề thi hay asset nhị phân trong commit frontend.

Ảnh chụp thực tế cho thấy lỗi CSS mà kiểm tra đơn vị bỏ sót: hàng flex footer cũ đặt mọi section mới cạnh nhau, chiều rộng văn bản kế thừa bó hẹp ticker, và margin âm của hình sticky khiến nó vẽ ra ngoài câu chuyện. Footer nay xếp các section theo cột, ticker giữ một dòng với dấu phân cách không co, và `overflow: clip` giới hạn hình mà không tạo container cuộn cạnh tranh. Mặt nạ hero ban đầu chừa vùng dưới để văn bản dễ đọc trong cả chế độ canvas và dự phòng. Test hồi quy cascade stylesheet dùng chung bao gồm quy tắc cũ và kiểm tra các xung đột này.

Sau đó người dùng yêu cầu footer nhỏ hơn và vòng lặp thực sự chuyển động. Ticker nay giới hạn 26px, chữ thương hiệu 112px, khoảng cách gọn hơn và nút Play/Pause liền kề. Quy tắc giảm chuyển động toàn cục hiện có ép mọi hoạt ảnh CSS xuống 0.01ms và một lượt; điều đó khiến nút Resume trước đây không hiệu quả. Ghi đè có phạm vi hẹp giữ toàn bộ vòng lặp vô hạn 26 giây của ticker và thời lượng khi tạm dừng, giữ nguyên reset hỗ trợ truy cập toàn cục ở nơi khác. Tiếp đó người dùng yêu cầu tường minh tự phát mặc định: footer nay render ở server trong trạng thái đang chạy và bắt đầu ngay, kể cả khi giảm chuyển động. Vẫn có Pause/Resume thủ công; trường cầu vẫn tuân thủ giảm chuyển động riêng.

Kiểm tra tiếp theo mới nhất: 45 test tập trung trong tám tệp PASS, gồm tự phát ngay từ render server, Pause/Resume thủ công và xung đột thời lượng/số lượt của stylesheet dùng chung. TypeScript và lint trên TS/TSX/test đã đổi đều PASS. Kiểm tra trình duyệt trước đó ở chiều rộng desktop, tablet và điện thoại cho thấy văn bản hero dễ đọc, tài liệu không tràn ngang. Thay đổi tự phát cuối được test trong tab desktop mới ở 1440×900 và sau tải lại di động ở 390×844, không nhấn Play: cả hai bắt đầu chạy với 26 giây/vô hạn, transform thay đổi giữa các lần quan sát. Pause giữ cùng ma trận giữa các lần quan sát; Resume khởi động lại chuyển động. Không ghi nhận cảnh báo/lỗi console trong tab test. Ảnh chụp desktop/điện thoại cuối được lưu ngoài repository tại thư mục visualization của nhiệm vụ. Chế độ giảm chuyển động của trình duyệt giữ Three.js chưa tải, đúng chủ đích; điều này không kiểm chứng render GPU trực tiếp.

Kiểm chứng còn lại: thời điểm cầu/trái tim/cuộn với chuyển động bình thường trên phần cứng thật; thao tác chạm thật và GPU/FPS/bộ nhớ thiết bị; ảnh chụp trình duyệt của cả hai ngôn ngữ/theme và màn hình runner/editor đã xác thực; đóng gói production và hành vi Modal được host. Không thực hiện tự động hóa E2E, build production hay sửa mã backend. Tài liệu tham chiếu được cung cấp và tệp công việc không liên quan vẫn nguyên vẹn.
