# Kiểm toán bộ máy câu hỏi và giao diện lượt làm bài

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Kiểm toán bộ máy câu hỏi và giao diện lượt làm bài. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../backend/app/domains/questions/registry.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/reading-listening.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


Mốc ban đầu: `4724167200f66e9fcd5a9c5605cd14dfd4e1cfc5` (`main`, 2026-10-26), gồm các sửa lỗi đồng thời ngay trước đó. Tham chiếu cũ được cung cấp là `43fdc9d`. Ranh giới Next.js → FastAPI → PostgreSQL vẫn là chuẩn có thẩm quyền.

## Bằng chứng sử dụng qua kiểm tra chỉ đọc

Đã truy cập được PostgreSQL Local theo cấu hình. Mọi kiểm tra dùng `SET TRANSACTION READ ONLY`, timeout câu lệnh và truy vấn tổng hợp; không đưa nội dung, dữ liệu tài khoản, văn bản đáp án hoặc thông tin xác thực vào đây. Đếm nhóm qua phép nối `question_groups → test_modules → test_versions → tests`. Cột published/draft loại bài cha đã lưu trữ; archived gồm phiên bản lưu trữ hoặc bài cha lưu trữ. Tham chiếu lịch sử đếm attempt riêng tham chiếu phiên bản/mô-đun có loại đó, rồi số đáp án lưu nối qua `questions`. Đây là quan sát Local, không bao phủ toàn bộ triển khai/sao lưu/xuất dữ liệu.

Hai registry chuẩn đều có **21 loại**. Mười lăm loại xuất hiện Local, sáu loại không. Mỗi loại vẫn thuộc hợp đồng transfer schema-version-1. Không xuất hiện Local không chứng minh loại đó lỗi thời. Mọi dòng đều có trạng thái `unknown` đối với sử dụng ở triển khai khác và ZIP đã lưu.

| Loại câu hỏi | Đã xuất bản | Nháp | Lưu trữ | Tham chiếu lịch sử (attempt / đáp án) | Tương thích nhập | Hành động đề xuất |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| multiple_choice | 6 | 2 | 23 | 2 / 0 | Giữ v1 | Giữ |
| multiple_choice_multiple | 6 | 0 | 36 | 0 / 0 | Giữ v1; ô trả lời tổ hợp | Giữ |
| true_false_not_given | 5 | 2 | 30 | 2 / 0 | Giữ v1 | Giữ |
| yes_no_not_given | 1 | 0 | 6 | 0 / 0 | Giữ v1 | Giữ |
| text_completion | 5 | 3 | 18 | 2 / 0 | Giữ v1; gap ID ổn định | Giữ |
| matching_headings | 1 | 0 | 6 | 0 / 0 | Giữ v1; bí danh heading cũ | Giữ; dùng chung điều khiển chọn phương án |
| matching | 4 | 2 | 17 | 0 / 0 | Giữ v1; chuẩn hóa nhãn cũ | Giữ; dùng chung điều khiển chọn phương án |
| matching_information | 2 | 1 | 11 | 2 / 0 | Giữ v1; ID đoạn | Giữ ngữ nghĩa đoạn riêng |
| matching_features | 0 | 0 | 0 | 0 / 0 | Giữ v1; fixture hồi quy | Giữ; dùng chung renderer matching |
| matching_sentence_endings | 1 | 1 | 0 | 2 / 0 | Giữ v1 | Giữ; dùng chung renderer matching |
| summary_completion_word_list | 1 | 0 | 6 | 0 / 0 | Giữ v1; ID phương án, không dùng văn bản | Giữ; dùng chung điều khiển chọn phương án |
| plan_labelling | 1 | 0 | 6 | 0 / 0 | Giữ v1; tham chiếu ảnh/marker | Giữ |
| map_labelling | 1 | 0 | 6 | 2 / 0 | Giữ v1; marker Reading / phương án Listening | Giữ |
| diagram_labelling | 2 | 0 | 17 | 0 / 0 | Giữ v1; hình học và đáp án văn bản | Giữ ngữ nghĩa sơ đồ riêng |
| form_completion | 0 | 0 | 0 | 0 / 0 | Giữ v1; fixture ZIP hiện có | Giữ bố cục có cấu trúc |
| note_completion | 7 | 2 | 29 | 4 / 0 | Giữ v1; block hiện đại/node cũ | Giữ |
| table_completion | 2 | 1 | 11 | 0 / 0 | Giữ v1; segment hiện đại/ô cũ | Giữ |
| flow_chart_completion | 0 | 0 | 0 | 0 / 0 | Giữ v1; hợp đồng node có cấu trúc | Giữ |
| summary_completion | 0 | 0 | 0 | 0 / 0 | Giữ v1; hợp đồng node có cấu trúc | Giữ |
| sentence_completion | 0 | 0 | 0 | 0 / 0 | Giữ v1; hợp đồng node có cấu trúc | Giữ |
| short_answer | 0 | 0 | 0 | 0 / 0 | Giữ v1; hợp đồng trả lời văn bản | Giữ |

Reading Local dùng gán nhãn sơ đồ, nối heading/thông tin/kết câu, dạng đồng ý, điền văn bản/ghi chú/bảng, danh sách từ và hai dạng MCQ. Listening dùng map/plan, matching, điền văn bản/ghi chú/bảng và hai dạng MCQ. Snapshot Local không có bản ghi `attempt_answers` đã lưu; phụ thuộc attempt ở cấp phiên bản vẫn có như bảng. Không suy ra số không ở triển khai không truy cập được.

## Phân loại tương thích và hợp nhất an toàn

- **Đang dùng:** 15 loại có số lượng khác không giữ ID chuẩn, cấu hình, đáp án, response, đánh số, renderer và chấm điểm.
- **Triển khai dùng chung:** dạng đồng ý đã chung renderer; matching/features/endings chung renderer/editor; plan/map chung renderer; điền có cấu trúc và đánh giá văn bản đã dùng chung. Hợp nhất nhóm rộng hơn thêm rủi ro khi chưa chứng minh lợi ích.
- **Trùng lặp nhỏ đã chứng minh:** matching, heading matching và điền danh sách từ lặp cùng select phương án giá trị UUID. Chỉ dùng chung điều khiển đó, giữ nguyên nhãn, placeholder, class, trạng thái disabled và payload callback. Nối đoạn giữ lựa chọn block-ID riêng.
- **Chưa dùng Local:** matching_features, form_completion, flow_chart_completion, summary_completion, sentence_completion và short_answer vẫn được hỗ trợ/cung cấp. Chúng là dạng soạn thảo IELTS hợp lệ và/hoặc fixture transfer hiện có; vắng Local không đủ kết luận không cần. **Không ẩn, ngừng hỗ trợ hoặc xóa loại nào.**
- **Đã chứng minh lỗi thời:** không có. Không có cơ sở migration schema, chuyển đổi câu hỏi đã lưu, đánh số lại hoặc cập nhật dữ liệu.

Bảo vệ mốc ban đầu thêm một hợp đồng JSON hư cấu dùng chung cho mọi loại, được kiểm thử frontend render/tương tác/serialize/đánh số và backend xác minh/chuẩn hóa/chấm điểm cùng dùng. Kiểm tra UUID, loại đáp án, giá trị response, nhiều ô và đầu vào fixture bất biến. Giữ bộ kiểm thử chuẩn hóa cũ, Builder, note/table/diagram phong phú và transfer. Định danh giao thức ZIP v1 và quy tắc ánh xạ ID không đổi.

Mốc trước sửa bộ máy: **76 kiểm thử backend đạt** (hợp đồng registry, registry/evaluation, transfer); **69 kiểm thử frontend đạt** (hợp đồng lưu dùng chung, registry và đánh số).

## Thiết kế giao diện và xác minh

Practice là tùy chọn UI riêng với scope, timer, ngữ cảnh attempt và chế độ Speaking. `attempt-presentation.ts` chỉ lưu `PRACTICE`/`EXAM` theo khóa trình duyệt UUID attempt/session Full Mock. Giữ `/attempt/:id`, pause/resume và đích history. `useSyncExternalStore` cung cấp phương án Legacy an toàn SSR trước khi đọc storage. Reading/Listening ưu tiên tùy chọn attempt hợp lệ, rồi session, rồi Legacy; Writing/Speaking giữ giao diện hiện có. Đồng bộ tùy chọn không tạo attempt hoặc queue autosave mới. Tùy chọn trình duyệt không đồng bộ sang thiết bị khác; xóa storage khôi phục Legacy tương thích.

Khởi chạy Reading/Listening full-module, focused-unit, classroom-module và Full Mock chỉ mở hộp chọn giao diện kính sau khi bấm Start. Thẻ bài không có bộ chọn giao diện. Practice là mặc định; giao diện Exam cũ mang nhãn **Legacy**, giữ giá trị nội bộ `EXAM` để tương thích. Hai thumbnail desktop không tương tác render đoạn/câu hỏi seed hư cấu qua registry chuẩn, thành phần pane/navigation chung, header thật và CSS runner. Chúng hiển thị radio đã chọn, gap note có cấu trúc, văn bản, player và điều hướng thay vì đường skeleton. Iframe thu phóng không script giữ media query desktop đúng; style và thuộc tính gốc Personalization đồng bộ vào đó, có dọn observer. Không mount controller, tạo attempt, audio element hoặc fetch thông báo. Nhãn mẫu được dịch nêu rõ nội dung hư cấu.

Chỉ tạo attempt/session khi xác nhận nên đóng hộp thoại không chạy timer. Chặn yêu cầu trùng khi chờ xác nhận; focus ở trong modal, Escape/backdrop hủy trước gửi và trả focus về nút bắt đầu. Full Mock lưu chọn theo session để Reading/Listening sau và reload kế thừa. Điều này theo yêu cầu sau của người dùng cho hai bố cục trong Full Mock; bỏ quy tắc ép Exam trước đó. Tùy chọn không đổi timer/scope/context hoặc chính sách backend. Listening vẫn truyền `audio_policy.allow_seeking/allow_speed` từ payload sang player hiện có. Writing/Speaking khởi chạy như cũ.

Hai giao diện giữ hook/controller runner, registry chuẩn, giá trị response, cờ, highlight ngữ nghĩa, revision autosave, đối soát nộp và đồng hồ từ server hiện có. Legacy giữ shell câu hỏi/CSS. Theo góp ý tiếp, Reading/Listening đang chạy còn giữ toàn header BandPilot (logo, điều hướng, cá nhân hóa, thông báo, tài khoản/đăng xuất) ở cả hai giao diện. Workspace flex dành chiều cao header thực và phần viewport còn lại cho runner, không overlay hoặc giả định chiều cao cố định. Writing/Speaking giữ shell tập trung gốc. Đồng hồ thực riêng suy từ timestamp hiển thị `Asia/Ho_Chi_Minh` / GMT+7 trên header với placeholder SSR xác định; không tham gia timer thi. Practice chỉ áp CSS Module gốc khi chế độ đã xác định là Practice. Refactor renderer chung chỉ giới hạn điều khiển phương án trên; không thêm kéo thả. Các thay đổi trang chủ/Speaking được yêu cầu thêm ghi bên dưới.

Reading Practice thêm bề mặt giấy, chữ sans-serif dễ đọc, dấu học tập xanh lá, hành động theo accent tài khoản, khoảng số nhóm đơn giản từ helper đánh số, navigator thường trực và vùng cuộn riêng. `ReadingSplitPane` bắt đầu 50/50, dùng pointer capture (kể cả touch), chặn chọn văn bản khi kéo, hỗ trợ phím mũi tên (2%; Shift 10%), Home/End chặn biên và Enter reset, công bố giá trị/điều khiển separator. ResizeObserver điều chỉnh giới hạn 30–70% để giữ khoảng 340px mỗi pane khi có thể. Ngắt observer lúc unmount; handler pointer chỉ ở element. Đổi đoạn giữ cùng divider; đáp án/đồng hồ ở controller cha. Dưới 900px ẩn divider, bộ chuyển Passage/Questions hiện có vẫn giữ hai pane có điều khiển mount. Chiều rộng chủ ý là trạng thái UI session, không phải trường DB.

Listening Practice dùng toolbar gọn một hàng, tài liệu chứa mọi nhóm của phần chọn, dock âm thanh và dải điều hướng câu hỏi dưới. Dải câu hỏi, trước/sau và Submit thành một nhóm giữa có giới hạn chiều rộng. Một điều khiển cờ câu đang chọn thay nút cờ lặp trong Practice; giữ cờ lưu/chỉ báo chip. Icon đóng vector được căn giữa hình học. Chip active dùng helper hiện theo chiều ngang hiện có. Nhóm map/plan/diagram giữ cột ảnh/đáp án desktop, chỉ xếp dọc dưới 600px. Toolbar/footer/audio chiếm chỗ bố cục, không phủ nội dung. Player Practice dùng nút Play/Pause vector tròn tô màu, icon tua năm giây không khung, loa nhỏ và thanh trượt mảnh; accent theo token CSS Personalization toàn cục ngay khi đổi. Không thêm bỏ qua mở đầu; trạng thái player/chính sách seek/speed/clip vẫn dùng chung. Chỉ thêm hướng dẫn highlight hiện có và hộp Personalization thật; không có Notes/Translation giả. Dark mode dùng token bề mặt sản phẩm. Mọi nội dung mới có bản dịch EN/VI.

## Lỗi highlight bổ sung do người dùng báo

`SelectableText` gốc đọc range đồng bộ trong `mouseup/touchend` của chính nó. Range hoàn tất sau đó hoặc thả pointer ngoài span không được kiểm lại tới lần chọn sau. Ba hồi quy xác định (câu hỏi, đoạn đọc, thả bên ngoài) thất bại trước sửa. Nay thành phần gộp `selectionchange`/`pointerup` trên document liên quan vào một frame, dùng callback mới nhất. Span khác không xử lý range; listener/frame được gỡ khi unmount hoặc chuyển chỉ đọc. Escape, click ngoài, đóng bởi peer và cuộn hiện có cũng chặn lựa chọn trì hoãn đã cũ. Vẫn cần xác nhận; giữ UUID đích, offset ngữ nghĩa, kiểm tra chồng lấn và hợp đồng văn bản đã lưu. Cổng 36 ca highlight/ranh giới từ/bản địa hóa runner đạt.

## Hồ sơ xác minh

- Giai đoạn 1: 76 backend và 69 frontend đạt ở mốc ban đầu; ca tích hợp ZIP v1 mọi loại mới cũng đạt.
- Giai đoạn 2: 77 backend engine/transfer và 106 frontend câu hỏi đạt sau hợp nhất điều khiển.
- Giai đoạn 3: 62 kiểm thử định tuyến giao diện, khởi chạy Practice và bản địa hóa runner đạt; TypeScript đạt.
- Giai đoạn 4: 51 kiểm thử controller/divider Practice mới đạt. Mọi loại chuẩn được trả lời qua runner Reading thật ở hai giao diện và gửi cùng attempt ID, question ID, giá trị và revision kỳ vọng. Ca khác kiểm giữ input/cuộn/đồng hồ/chiều rộng, hủy pointer, dọn resize, giới hạn hình ảnh Listening từ server và tùy chọn Full Mock.
- Cổng backend Local cuối: **133 đạt** trên PostgreSQL test riêng cổng loopback 5544 (registry, chấm, ZIP v1, revision đồng thời, Full Mock, focused attempt, Reading/Listening). Không kiểm thử phá dữ liệu nào dùng DB development đã kiểm toán.
- Ruff lint/format và TypeScript frontend đạt. `next build --webpack` production đạt sau Windows Turbopack không tạo được worker Node CSS (`Access is denied`, kể cả ngoài sandbox); build Linux Turbopack mặc định vẫn là cổng Golden Path GitHub. Kết quả lint, Vitest và CI từ xa cuối ghi lúc bàn giao.
- Lần Vitest đầy đủ đầu có 1,492 đạt và một lỗi thời điểm Speaking-review có sẵn (kiểm subscription trước effect). Tệp 14 ca của nó đạt riêng không sửa; chạy lại toàn bộ không nới kiểm tra hoặc sửa Speaking không liên quan.
- Theo chính sách kiểm thử nhiệm vụ, không chạy trình duyệt thủ công hoặc Playwright/skill inspector Local. Vì vậy không tuyên bố đánh giá ảnh chụp giao diện. Bố cục tham chiếu được cung cấp và góp ý preview Local người dùng định hướng style có phạm vi; xác minh trình duyệt dùng CI. Golden Path giữ ba spec hiện có, thêm Reading Practice cho highlight lần chọn đầu native, hình học divider, tràn độc lập, refresh, đáp án lưu và hành vi panel 390px. Kiểm Reading/Listening còn kiểm header, GMT+7, vừa viewport, điều hướng giữa. Listening kiểm icon đóng vector và đổi accent toàn cục trực tiếp; Full Mock giữ audio/vòng đời.

Không đổi schema DB, nội dung published, loại chuẩn, hình dạng question/response/key đã lưu, quy tắc chấm hoặc phiên bản ZIP. Chưa biết mức dùng triển khai/ZIP ngoài, lưu tùy chọn UI xuyên thiết bị và đánh giá hình ảnh ngoài kiểm CI. Commit mạch lạc tách bảo vệ hợp đồng, hợp nhất điều khiển phương án, ranh giới chế độ, sửa highlight và style/tương tác Practice.

Yêu cầu sau của người dùng còn hiển thị GMT+7 ở mọi trang dùng header toàn cục (trang chủ, Test library, Skill practice, History, Analytics) và đếm ngược ngày/giờ/phút/giây đã dịch trong IELTS Goals. Vì profile hiện chỉ lưu ngày, đếm ngược nêu rõ đích 00:00 GMT+7 ngày đó, chặn ở không và không ghi profile. Đồng hồ chung suy từ timestamp (kể cả tab tạm dừng), placeholder SSR ổn định, dọn listener/interval. Ngày lịch không hợp lệ không hiện đếm ngược gây hiểu nhầm. Bố cục/nội dung trang chủ khác không đổi.

Speaking Part 2 nay có **Skip preparation** trong chuẩn bị long-turn. Endpoint có kiểu, cấp quyền chủ sở hữu dùng khóa attempt/progress và kiểm prompt/take hiện tại để chuyển `PREPARING → STARTING` với ba giây dẫn vào hiện có. Không tạo take mới hoặc giảm/tăng thời lượng nói. Lặp yêu cầu trong STARTING/RECORDING trả trạng thái chuẩn, không reset deadline; yêu cầu hết hạn, hoàn tất, sai chủ, sai take hoặc không long-turn bị từ chối. Runner flush ghi chú nháp, chặn click trùng, chờ server RECORDING trước thu mic. Timeout chuẩn bị tự động gốc vẫn còn. Kiểm thử tái hiện thiếu hành động trước, rồi đạt: 23 kiểm thử runtime backend, gồm hai kết nối PostgreSQL thật độc lập chờ khóa attempt và hạn chế replay/retry Exam, cùng frontend chờ ack, ghi chú lưu, click trùng và thử lại lỗi mạng. Không đổi schema, gọi provider hoặc phản hồi AI.

Rà soát trước bàn giao phát hiện hai hồi quy giao diện: callback cài đặt Practice thay đổi reset focus dialog mỗi tick đồng hồ, và quy tắc flex footer có sẵn làm rộng wrapper điều hướng Reading mới. Hồi quy giữ focus thất bại tái hiện lỗi đầu trước khi callback ổn định sửa; ghi đè flex theo phạm vi sửa lỗi sau, với kiểm hình học CI trên điều khiển thấy được và wrapper. Chỉ dẫn cuối người dùng là **push và kết thúc không theo dõi CI**; kết quả CI/E2E từ xa chưa xác minh lúc bàn giao.

Xác minh Local cuối sau mọi yêu cầu tiếp: **131 tệp Vitest / 1,523 kiểm thử đạt**; backend Speaking/Full Mock **32 đạt**, ngoài cổng backend engine/vòng đời 133 ca trước. TypeScript, ESLint, Ruff lint/format, `next build --webpack` và `git diff --check` staged đạt. Rà soát cuối riêng không tìm thêm vấn đề cần sửa. Assertion E2E đã cập nhật nhưng không chạy Local theo chính sách; không tuyên bố kết quả CI từ xa.
