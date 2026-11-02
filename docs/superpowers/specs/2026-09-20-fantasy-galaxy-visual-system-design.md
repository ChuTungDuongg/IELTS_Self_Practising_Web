# Thiết kế hệ thống thị giác thiên hà kỳ ảo

> **Kiểm toán tài liệu: SUPERSEDED.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Thiết kế hệ thống thị giác thiên hà kỳ ảo. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../frontend/src/components/ui/app-shell.tsx).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/shared-platform.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

**Ngày:** 2026-09-20
**Trạng thái:** Đã phê duyệt để triển khai

## Mục đích

Thiết kế lại frontend IELTS Studio hiện có thành nền tảng học tập thống nhất, cao cấp, lấy cảm hứng từ đài quan sát kỳ ảo yên tĩnh. Nhận diện dùng xanh hải quân vũ trụ đậm, chàm, sapphire, tím và ánh sao cyan, đồng thời giữ tên sản phẩm, kiến trúc ứng dụng và mọi hành vi hiện tại.

Thiết kế phải tạo cảm giác hoàn thiện nhờ phân cấp, kiểu chữ, khoảng cách, chiều sâu bề mặt và mẫu tương tác nhất quán. Không được dựa vào thương hiệu/bố cục sao chép, ảnh thiên hà raster, hạt, WebGL hoặc hiệu ứng phát sáng/kính quá mức.

## Phạm vi và ràng buộc

Công việc chỉ ở frontend. Phạm vi gồm khung ứng dụng, điều hướng, bảng tổng quan, thư viện học viên, lịch sử lượt làm, thư viện đề quản trị, chi tiết đề, không gian Builder, Builder Reading/Listening, xem trước bản nháp, Candidate Reading/Listening, màn hình xem lại, hộp thoại chung, popover, trạng thái rỗng, huy hiệu, biểu mẫu, nút và bộ hiển thị câu hỏi.

Thiết kế lại không thay API backend, mô hình cơ sở dữ liệu, migration, lưu trữ, đánh giá, xuất bản, vòng đời lượt làm hoặc cấu trúc dữ liệu câu hỏi. Cụ thể phải bảo toàn:

- biên soạn Text Completion mỗi khối một câu;
- hành vi con trỏ và tiêu điểm trong vùng biên soạn điền chỗ trống;
- danh tính UUID GAP và Question ổn định, đánh số đúng sau tải lại;
- đáp án văn bản thay thế và thiết lập đáp án nâng cao;
- hướng dẫn điền chỗ trống nhiều dòng;
- luồng xác thực và xuất bản;
- tự lưu và bộ đếm suy ra từ mốc thời gian;
- điều hướng câu hỏi phía dưới và cờ;
- tô sáng theo offset ngữ nghĩa, popover an toàn khi hydration và Delete all highlights;
- âm thanh Listening dùng chung và hành vi trình phát;
- thao tác Continue, Review và Delete trong History;
- hành vi lưu trữ, phiên bản bất biến và vòng đời lượt làm đóng băng.

## Hướng thị giác

IELTS Studio trở thành đài quan sát vũ trụ yên tĩnh phục vụ học tập thay vì giao diện trò chơi hoặc cyberpunk.

- Dark mode là trải nghiệm chủ đạo: nền hải quân nửa đêm, bề mặt xanh theo lớp, viền trong nhẹ và ánh cyan/tím cục bộ.
- Light mode dùng nền gần trắng lạnh, bề mặt nổi sắc nét, bóng chàm mềm và cùng hệ màu nhấn.
- Chiều sâu không khí đến từ số ít gradient hướng tâm CSS và phần tử giả nhẹ. Chi tiết sao trang trí chỉ xuất hiện ở khung và bề mặt tính năng, tuyệt đối không bao quanh nội dung Reading dài.
- Phần lớn thẻ đục hoặc gần đục. Hiệu ứng kính chỉ dành cho điều hướng, thanh công cụ cố định, hộp thoại và một số bề mặt hero.
- Chuyển động giới hạn ở chuyển tiếp rê chuột, tiêu điểm, điều hướng hoạt động và hộp thoại 120–220 ms, hỗ trợ `prefers-reduced-motion`.

## Kiến trúc token ngữ nghĩa

Kiến trúc `data-theme="light"` và `data-theme="dark"` hiện có tiếp tục là nguồn chuẩn. `globals.css` định nghĩa tập token ngữ nghĩa gọn:

- Nền: `--app-bg`, `--app-bg-elevated`
- Bề mặt: `--surface`, `--surface-raised`, `--surface-soft`, `--surface-hover`, `--surface-glass`
- Văn bản: `--ink`, `--ink-soft`, `--muted`
- Đường viền: `--line`, `--line-strong`
- Thương hiệu: `--accent`, `--accent-strong`, `--accent-soft`, `--accent-violet`, `--accent-cyan`
- Ngữ nghĩa: `--success`, `--warning`, `--danger` và các biến thể nền nhẹ tiết chế
- Hiệu ứng: `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--glow-accent`, `--glow-violet`

Có thể giữ bí danh tương thích cho biến chuyên biệt hiện có như token Reading, Listening, tô sáng và bài thi. Giá trị riêng trang suy ra từ token ngữ nghĩa thay vì thêm màu không liên quan.

Bề mặt thi Candidate giữ lớp token `--exam-*` chuyên biệt suy ra từ giao diện đang dùng. Đây là tập con ngữ nghĩa nhằm hạn chế trang trí và tối đa khả năng đọc, không phải triển khai giao diện thứ hai.

## Hệ thống trình bày dùng chung

Các thành phần cơ sở hiện có tiếp tục là ranh giới chính. `PageHeading`, `StatusBadge`, `ModuleBadge`, `EmptyState`, `ConfirmDialog`, `ThemeToggle` và AppShell nhận cách trình bày nhất quán qua lớp và token dùng chung.

Nút có năm biến thể: primary, secondary, ghost, danger và icon. Thao tác phá hủy giữ gọn và ít nổi bật hơn thao tác chính. Biểu mẫu dùng chung chiều cao, khoảng đệm, viền, placeholder, tiêu điểm, vô hiệu hóa và trạng thái xác thực nhất quán. Thẻ dùng bán kính vừa, viền nhẹ, bóng tiết chế và chỉ nhấn màu cục bộ.

Kiểu chữ xác lập các cấp tái sử dụng: dòng dẫn, tiêu đề trang, phụ đề, tiêu đề phần, tiêu đề thẻ, nội dung, metadata, nhãn và trạng thái. Văn bản Reading dài ưu tiên độ dài dòng biên tập, khoảng cách đoạn và chiều cao dòng hơn trình diễn thương hiệu.

## Khung ứng dụng và điều hướng

Khung máy tính giữ cấu trúc đầu trang-thanh bên đồng thời thêm không khí thiên hà kỳ ảo. Nền khung cung cấp lớp sáng hải quân, cyan và tím tĩnh. Đầu trang/thanh bên nổi dùng độ trong có kiểm soát, còn điều hướng hoạt động nhận một điểm nhấn sáng duy nhất. Tên IELTS Studio và cấu trúc tuyến hiện tại giữ nguyên.

Hành vi thích ứng giữ mẫu điều hướng ngang gọn dưới breakpoint hiện có. Nhãn điều hướng vẫn có ở chiều rộng máy tính bảng; chỉ dùng biểu tượng ở màn hình nhỏ nhưng vẫn giữ nhãn cho công nghệ hỗ trợ.

## Trang dành cho học viên

### Trang chủ

Bảng tổng quan trở thành cổng học tập tập trung vào sản phẩm. Hero rộng truyền đạt giá trị, cung cấp CTA luyện tập chính và tuyến biên soạn/lịch sử phụ. Chỉ số tổng hợp vẫn có nhưng không chi phối. Dưới hero, bốn thẻ lộ trình tổ chức Test Library, Reading, Listening và History/Progress với màu nhấn mô-đun có kiểm soát.

### Thư viện

Mô-đun đã xuất bản xuất hiện thành thẻ đề dễ quét với danh tính mô-đun, tiêu đề, mô tả, metadata phiên bản và thao tác Start nổi bật. Reading dùng cyan/xanh; Listening dùng tím. Trang trí thẻ tiết chế, nhận diện mô-đun qua điểm nhấn nhỏ phía trên và phát sáng cục bộ.

### Lịch sử

Lượt làm thành hàng hồ sơ luyện tập gọn. Tiêu đề đề, mô-đun, phiên bản/ngày, trạng thái, thời gian đã qua và thao tác Continue/Review chính tạo đường đọc. Delete giữ dạng danger-ghost và tuyệt đối không cạnh tranh với tiếp tục hoặc xem lại.

## Quản trị và Builder

Trang quản trị dùng cùng hệ thống thiết kế với mật độ thông tin cao hơn một chút. Bộ lọc trạng thái, tìm kiếm, Create Test, phân biệt nháp/đã xuất bản/đã lưu trữ và hàng phiên bản có phân cấp rõ hơn.

Builder bảo toàn mọi thành phần và luồng dữ liệu đang hoạt động. Thanh công cụ cố định làm rõ ưu tiên Draft, Validate, Preview, Publish và xóa. Điều hướng cấu trúc cục bộ hiển thị không gian được chọn và trạng thái Created/Not created với màu nhấn mô-đun. Bề mặt biên soạn chính giảm nặng nề của thẻ lồng bằng khoảng cách, nền nhóm mềm và chiều sâu cha/con rõ hơn.

Bài đọc Reading và phần Listening giữ vai trò khung chính. Nhóm câu hỏi thành hàng tóm tắt gọn. Trình biên tập dùng vùng thị giác cho Instruction, Content, Answer configuration và Advanced settings tại nơi markup hiện có cho phép mà không tái cấu trúc hành vi. Khối câu Text Completion giữ vùng sửa sạch với token chỗ trống gọn và trạng thái chọn nhẹ.

## Bài thi Candidate và xem trước

Chế độ Candidate chủ động giảm trang trí của bảng tổng quan. Nó dùng nền hải quân dịu hoặc trắng lạnh, bề mặt biên tập đục, viền tiết chế và phát sáng tối thiểu chỉ ở điều khiển/tiêu điểm.

Reading giữ cấu trúc hai khung. Kiểu chữ bài đọc có độ dài dòng, chiều cao dòng, khoảng đoạn và cỡ đề mục dễ đọc. Câu hỏi phân nhóm nhẹ và hướng dẫn rõ. Đầu trang, bộ đếm, trạng thái lưu, điều khiển tô sáng, chuyển giao diện, điều hướng chân trang, chip câu hỏi, cờ và Submit giữ hành vi hiện tại.

Listening có thể mang sắc tím/xanh rõ hơn một chút trong trình phát âm thanh nổi. Điều khiển phát, tua, âm lượng, tốc độ và thời gian vẫn thực dụng, không mô phỏng sản phẩm phát trực tuyến giải trí.

Draft Preview dùng chung bộ hiển thị Candidate nhưng nhận diện bằng trạng thái xem trước tiết chế, đồng thời vẫn tách biệt chức năng khỏi câu trả lời đã lưu.

## Xem lại, hộp thoại và tô sáng

Bề mặt xem lại giữ mục đích học tập. Câu đúng/sai dùng viền màu nhẹ thay bảng nền xanh/đỏ đầy. Your answer, Correct answer và Explanation trở thành hàng kiểu chữ riêng nhưng giữ bố cục câu hỏi gốc.

Hộp thoại, popover tô sáng, bề mặt thả xuống và bảng xác thực dùng chung bề mặt, viền, bán kính, bóng, khoảng cách và căn thao tác. Màu tô sáng dễ đọc, không quá bão hòa ở cả hai giao diện.

## Khả năng tiếp cận, thích ứng và hiệu năng

- Giữ HTML ngữ nghĩa, điều hướng bàn phím, nhãn ARIA và hành vi tiêu điểm hiện có.
- Giữ vòng `focus-visible` rõ với tương phản chú trọng WCAG.
- Giữ kích thước chạm điều khiển thực dụng và ngăn tràn ngang toàn trang.
- Giữ hiệu suất biên soạn trên máy tính, đồng thời xếp chồng hoặc cuộn điều hướng cục bộ hợp lý ở màn hình nhỏ.
- Chỉ dùng gradient CSS và phần tử giả; không thêm thư viện ảnh hoặc chuyển động.
- Tránh chuyển động liên tục và tắt chuyển tiếp không cần thiết cho người dùng giảm chuyển động.

## Xác minh

Triển khai chỉ hoàn tất sau khi:

- kiểm tra trực quan Home, Library, History, Admin, Builder, Candidate, Preview và Review tại nơi có dữ liệu;
- kiểm tra giao diện sáng và tối;
- kiểm tra kích thước máy tính và thích ứng;
- `npm test`;
- `npm run lint`;
- `npm run typecheck`;
- `npm run build`;
- `git diff --check` and `git diff --cached --check`;
- kiểm tra diff cuối xác nhận không có thay đổi backend, môi trường, bí mật hoặc ngoài phạm vi.
