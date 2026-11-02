# Khung điều hướng ngang, giao diện giấy và bản địa hóa giao diện hệ thống

> **Kiểm toán tài liệu: SUPERSEDED.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Khung điều hướng ngang, giao diện giấy và bản địa hóa giao diện hệ thống. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../frontend/src/components/ui/app-shell.tsx).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/shared-platform.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Ngày: 2026-10-10

Trạng thái: Hướng đã phê duyệt, chỉ là đặc tả

Kho mã được kiểm tra: `ChuTungDuongg/IELTS_Self_Practising_Web`

Mốc cơ sở: `0ffe61c333e46a9c61a4a8588b66f455fd452147` — `Refine focused practice browsing`

Tài liệu định nghĩa thay đổi kiến trúc frontend tiếp theo. Không triển khai thay đổi hoặc cho phép công việc ngoài phạm vi frontend đã duyệt. Sản phẩm bàn giao của nhiệm vụ đặc tả chỉ là tài liệu này.

## 1. Bối cảnh và hiện trạng

Khảo sát thực hiện sau fetch mới `origin/main`; mốc từ xa và cục bộ khớp. Các phát hiện sau quyết định thiết kế:

| Khu vực | Triển khai hiện tại | Hệ quả thiết kế |
| --- | --- | --- |
| Cấu trúc gốc | `frontend/src/app/layout.tsx` hiển thị `AuthProvider` → `AppShell`, máy chủ đặt `lang="en"` và `data-theme="light"`. | Thêm ngữ cảnh ngôn ngữ cục bộ trình duyệt quanh cấu trúc hiện có; giữ lấy dữ liệu máy chủ và ranh giới xác thực. |
| Khung làm việc | `components/ui/app-shell.tsx` sở hữu thương hiệu, nhãn ngữ cảnh, thao tác xác thực, giao diện, điều hướng và xác nhận đăng xuất. CSS dùng đầu trang 72px và thanh bên cố định 248px. | Thay thanh bên toàn cục bằng một điều hướng chính ngang và phân chia đầu/chân trang vừa phải. |
| Điều hướng | Người đăng nhập thấy năm liên kết làm việc; ADMIN thêm Admin, Builder, Transfer. Khách thấy Overview. `/admin` khớp chính xác; Builder bao `/admin/tests/*`. | Giữ đích, quyền hiển thị, `prefetch={false}` ngoài trang chủ và phân biệt tuyến hoạt động. |
| Lượt thi chuyên biệt | AppShell chỉ trả `<main className="exam-shell">` cho đường bắt đầu `/attempt/`. Reading, Listening, Writing, lượt tạm dừng và mô-đun Full Mock đều qua tuyến này. | Giữ nhánh bỏ qua trước tạo khung làm việc. |
| Tuyến khác | `/review/[attemptId]` và `/test-session/[sessionId]` dùng khung thường. Xem trước Builder dùng khung thường nhưng `DraftPreview` hiển thị `.exam-runner` và `.exam-footer` cục bộ. | Xem lại/chuyển tiếp nhận chân trang chung; xem trước nháp loại chân trang này mà không đổi đầu trang/bố cục trình làm hiện tại. |
| Kiểu chữ | Nội dung dùng Segoe UI/system sans 15px. H1 chung 32–46px/760; nút 13px/750; nhiều huy hiệu/dòng dẫn dùng độ đậm 800, viết hoa và giãn chữ rộng. | Giữ phông hệ thống; đơn giản hóa độ đậm, hoa thường, phân cấp trên trang làm việc. |
| Giao diện | `globals.css` định nghĩa token chung và `--exam-*` rõ. Sáng có nền xanh/tím, gradient nhiều lớp; tối đã phẳng nhiều bề mặt nhưng dùng graphite lạnh. | Làm ấm hai bảng màu làm việc, bỏ ánh sáng môi trường nhưng giữ giá trị thi đã phân giải. |
| Lưu giao diện | Đã có `ielts-theme`, `data-theme` gốc, bootstrap nội tuyến và khôi phục `ThemeToggle`. Bootstrap hiện theo `prefers-color-scheme` khi chưa lưu. | Giữ khóa/thuộc tính và bootstrap sớm; mặc định sáng rõ ràng, không thêm chế độ hệ thống ngầm. |
| Trang máy chủ | Overview, Library, Practice, History, Analytics, Admin tải qua `serverApiRequest`; giao diện tính năng tương tác hiện có dùng DTO. | Dịch trình bày tại ranh giới client; không chuyển gọi API sang trình duyệt. |
| Duyệt luyện tập | Skill Practice có lọc kỹ năng/đơn vị cục bộ, tìm kiếm, thẻ giữ gắn, thời gian và điều khiển bắt đầu tập trung. | Bảng lọc là điều hướng tính năng, không thanh bên toàn cục; giữ lựa chọn, tìm kiếm, danh tính thẻ và chốt lượt đang chờ. |
| Thành phần cơ sở chung | Đã có `PageHeading`, `EmptyState`, `ModuleBadge`, `StatusBadge`, biểu tượng, SVG `AppLogo`, `ConfirmDialog`. | Mở rộng/tái dùng; giữ tiêu điểm hộp thoại, hành vi chờ và biến thể ngữ nghĩa. |
| Xác minh | Đã có Vitest/RTL, TypeScript, ESLint và kiểm thử token/tương phản CSS. Một số kiểm thử yêu cầu thanh bên, phát sáng, kích thước hoặc kiểu thiên hà cũ. | Chủ động cập nhật khẳng định thị giác lỗi thời; giữ kiểm tra tiếp cận, giao diện và bảo vệ bài thi. |

Khảo sát bao phủ thành phần UI yêu cầu, layout/CSS gốc, provider xác thực, mọi nhóm trang chính yêu cầu, tuyến lồng Admin/Builder, Transfer, tuyến hồ sơ/xác thực/phiên, lượt/xem lại/chuyển tiếp/xem trước và kiểm thử frontend liên quan. Hướng dẫn ranh giới client Next đã cài xác nhận ngữ cảnh trình duyệt thuộc client component, props server-client phải tuần tự hóa được. Hiện chưa cài gói bản địa hóa hoặc giao diện.

## 2. Mục tiêu

1. Cho trang thường một điều hướng ngang, chiều rộng nội dung hữu ích hơn và chân trang chung tiết chế.
2. Thiết lập kiểu chữ dễ đọc viết hoa đầu câu, phân cấp nút xuyên khung làm việc và Admin.
3. Dùng giấy ấm cho sáng và graphite ấm cho tối, viền nhẹ, điểm nhấn ngữ nghĩa nhỏ.
4. Hỗ trợ English và Tiếng Việt qua từ điển nội bộ nhỏ có kiểu và tùy chọn cục bộ trình duyệt.
5. Giữ tuyến, hạn chế vai trò, quy tắc miền, nội dung biên soạn và trải nghiệm thi cô lập hiện có.

IELTS Studio giữ tên, nhận diện hành tinh SVG và màu nhấn Reading/Listening/Writing phân biệt hiện có. Cảm hứng giấy/biên tập không nghĩa sao chép thương hiệu hoặc giao diện sản phẩm khác.

## 3. Ngoài phạm vi

- Không thiết kế lại trình thi, thêm điều hướng trình làm hoặc đổi bố cục, token thi, thời gian, tự lưu, tô sáng, cờ, quy tắc phát, hành vi hiển thị câu, nộp, đáp án xem lại, Full Mock, chấm hoặc máy trạng thái lượt. Chuỗi/nhãn tiếp cận chung/tĩnh của trình làm hiện có được bản địa hóa; điều này không cho phép đổi hành vi.
- Không đổi chức năng Test Library hoặc logic Skill Practice; không hệ thống ảnh thu nhỏ.
- Không đổi backend, migration, tùy chọn cơ sở dữ liệu, cột ngôn ngữ, header ngôn ngữ API, dịch dữ liệu hoặc trạng thái giao diện backend.
- Không tuyến `/en/*` hoặc `/vi/*`, cookie ngôn ngữ, SEO bản địa hóa hoặc dịch nội dung IELTS biên soạn.
- Không xác thực mới, triển khai Speaking, hành vi AI hoặc gọi AI.
- Không chế độ ngoài sáng/tối, chế độ hệ thống/tự động, tệp phông tải về, thư viện hệ thiết kế, gói bản địa hóa hoặc thay framework CSS.
- Không ngăn điều hướng di động, framework chuyển động hoặc dịch toàn trình biên tập Builder chuyên biệt lồng trong lượt đầu.

## 4. Kiến trúc điều hướng

Dùng một `<nav aria-label={t("nav.primary")}>` ở đầu trang toàn cục. Liên kết máy tính ưu tiên chữ; bỏ biểu tượng từng liên kết dư trong điều hướng gọn. Giữ dấu thương hiệu. Giữ thứ tự và đích:

| Nhãn tiếng Anh | Nhãn tiếng Việt | Đích | Hiển thị |
| --- | --- | --- | --- |
| Overview | Tổng quan | `/` | Mọi người |
| Test library | Thư viện đề | `/library` | Đã đăng nhập |
| Skill practice | Luyện từng kỹ năng | `/practice` | Đã đăng nhập |
| Attempt history | Lịch sử luyện tập | `/history` | Đã đăng nhập |
| Analytics | Thống kê | `/analytics` | Đã đăng nhập |
| Admin | Quản trị | `/admin` | ADMIN |
| Builder | Biên soạn đề | `/admin/tests` | ADMIN |
| Transfer | Chuyển đề | `TRANSFER_ROUTE` (`/transfer`) hiện có | ADMIN |

Không biến nhãn dịch thành đường tuyến/định danh. Bản ghi điều hướng dùng href và khóa dịch ổn định. Đang tải xác thực giữ hiển thị thận trọng: không liên kết đặc quyền trước xác định người dùng. Lỗi phiên vẫn hiện, không giả thành đã đăng xuất. Kiểm tra vai trò máy chủ trong layout Admin/Transfer hiện có là nguồn chuẩn; ẩn liên kết không phải phân quyền.

Giữ khớp chính xác `/` và `/admin`, khớp hậu duệ cho đích khác hiện có. Đặc biệt `/admin/tests/...` kích hoạt Builder, không Admin. Không thêm đích hoạt động toàn cục cho `/profile`, `/review/...`, `/test-session/...`; tiêu đề/thao tác quay lại riêng cung cấp ngữ cảnh.

Bỏ khối ngữ cảnh `Workspace / current section` ở đầu, nhãn `Workspace` và ghi chú quảng bá thanh bên. Liên kết hoạt động cùng H1 cung cấp ngữ cảnh không trùng điều hướng. Giữ liên kết quay lại riêng trang, nguồn gốc đề/phiên bản và điều hướng không gian Builder; không thêm breadcrumb toàn cục thứ hai.

Thao tác đầu trang có thứ tự ổn định: ngôn ngữ, giao diện, người dùng/hồ sơ, đăng xuất. Chưa đăng nhập thay người dùng/đăng xuất bằng Login rồi Register. Tên hiển thị giữ dữ liệu người dùng/biên soạn; nhãn vai trò dịch được nhưng API giữ `USER`/`ADMIN`. Tái dùng xác nhận đăng xuất, chốt một yêu cầu, vô hiệu lúc chờ, khôi phục tiêu điểm và xử lý lỗi hiện tại. Đổi ngôn ngữ tuyệt đối không kích hoạt xác thực, đăng xuất, chuyển hướng hoặc `router.refresh()`.

## 5. Cấu trúc thành phần khung và tổ hợp trang

Cấu trúc khuyến nghị:

```text
RootLayout (server: metadata, theme bootstrap, current footer year)
└── LocaleProvider (client)
    └── AuthProvider (existing client lifecycle)
        └── AppShell (route boundary)
            ├── /attempt/*: main.exam-shell → existing page only
            └── normal route: div.app-shell
                ├── GlobalHeader
                │   ├── existing Brand/AppLogo
                │   ├── PrimaryNavigation
                │   └── HeaderActions: LocaleSwitcher, ThemeToggle, account controls
                ├── main.app-content#main-content → existing page
                └── AppFooter (except inspected Builder preview route)
```

Giữ `AppShell` trong tệp hiện tại. Thêm `global-header.tsx`, `app-footer.tsx` dưới `components/ui/`. `PrimaryNavigation`, `HeaderActions`, `LocaleSwitcher` gọn có thể là hàm cục bộ trong tệp đầu trang, không tệp thành phần riêng. GlobalHeader sở hữu UI xác thực/đăng xuất hiện có; AppShell sở hữu chọn tuyến và vị trí trang. Giữ `ThemeToggle`, `ConfirmDialog`, thành phần cơ sở tái dùng được. Không tách thành phần thi mới chỉ để đổi tên nhánh bỏ qua hiện có.

Khung thường dùng một cột và `min-height: 100dvh` (dự phòng `100vh`), với đầu trang, main giãn và chân trang trong luồng thường. Main giãn đẩy chân trang xuống dưới nội dung ngắn; chân trang tuyệt đối không cố định đè nội dung. Overlay hộp thoại giữ hành vi hiện có, ngoài điều hướng chính.

Kích thước nội dung là giới hạn border-box gồm khoảng đệm khung:

| Nhóm trang | Tối đa ngoài | Ràng buộc trong |
| --- | --- | --- |
| Overview, xem lại, chi tiết thường | 1280px | Văn mô tả ≤72ch; giữ nguyên khung xem lại hiện có. |
| Library, Skill Practice, History, Analytics, danh sách Admin, Builder, Transfer | 1440px | Giữ lưới/điều hướng cục bộ; dùng chỗ rộng thêm không đổi logic. |
| Hồ sơ và biểu mẫu thường | 1280px | Nội dung biểu mẫu ≤920px, nhóm trường giữ cột thích ứng. |
| Biểu mẫu đề mới | 1280px | Nội dung biểu mẫu ≤720px. |
| Login/Register | 1280px | Bảng xác thực ≤480px. |
| Chuyển tiếp Full Mock | 1280px | Nội dung chuyển tiếp hiện có ≤720px. |

Dùng phân loại đường dẫn-chiều rộng nhỏ, rõ trong AppShell, không framework bố cục mới. Xem trước Builder giữ kích thước trình làm bên trong và không nhận ghi đè kiểu chữ làm việc trong `.exam-runner`. Lượt thi không nhận chiều rộng/khoảng đệm này.

Đệm ngang khung: 32px ở ≥1440px, 24px ở 768–1439px, 16px dưới 768px. Đệm trên/dưới main: 40/48px màn hình lớn, 32/40px trung bình, 24/32px nhỏ. Chiều rộng trong đầu/chân trang tối đa 1440px với cùng đệm ngang. Nội dung căn giữa.

Dùng cơ sở khoảng cách 4px: 8px giữa chữ/điều khiển liên quan, 12px nhóm gọn, 16px trường biểu mẫu/khe thẻ hẹp, 24px đệm thẻ thường/khe lưới, 32px giữa phần, 48px giữa phần tổng quan lớn. Thẻ luyện gọn giữ đệm 16px và mật độ hiện có. PageHeading có lề dưới 24px, khe dòng dẫn-tiêu đề 8px, tiêu đề-mô tả 12px. Biểu mẫu cách trường 16px, nhóm/thao tác 24px. Thao tác xuống dưới đề mục khi cần; tránh chiều cao tiêu đề cố định hoặc ép dòng dẫn rỗng.

## 6. Hành vi chân trang

AppFooter là `<footer>` ngữ nghĩa có viền trên, nền giấy, đệm dọc 24px, chữ nhỏ nhẹ. Nội dung gồm:

- `IELTS Studio` (tên sản phẩm giữ nguyên).
- `Practice & authoring` / `Luyện tập và biên soạn đề` bản địa hóa.
- `© {year} IELTS Studio`, dùng năm hiện tại RootLayout cung cấp khi máy chủ render.
- Chỉ báo ngôn ngữ `English` hoặc `Tiếng Việt`, không bộ chọn thứ hai hoặc cờ.

Không bịa liên kết pháp lý, mạng xã hội, liên hệ, tài liệu. Trên máy tính, danh tính/mô tả bên trái, bản quyền/ngôn ngữ bên phải; dưới 768px xếp nhóm cách 12px. Chân trang ngoài nội dung tính năng, tuyệt đối không trùng `.exam-footer`.

Quyết định tuyến dựa định tuyến đã khảo sát:

| Tuyến | Đầu trang toàn cục | Chân trang toàn cục | Lý do |
| --- | --- | --- | --- |
| `/attempt/*` | Không | Không | Tuyến thi riêng hiện có cho luyện tập trung/đầy đủ, mô-đun Full Mock, chốt tạm dừng và chuyển hướng cuối. |
| `/admin/tests/[testId]/versions/[versionId]/preview` | Có, khung Admin hiện có | Không | DraftPreview hiện trình thi/chân trang thi riêng. Chỉ ẩn chân trang toàn cục mới; không thiết kế lại xem trước hoặc gỡ đầu trang hiện tại. |
| `/review/[attemptId]` | Có | Có | Xem lại câu trả lời/điểm đã chốt hiện dùng cấu trúc làm việc. |
| `/test-session/[sessionId]` | Có | Có | Thẻ chuyển tiếp/kết quả dùng khung thường; lượt hoạt động chuyển `/attempt/*`. |
| `/session/restore`, `/login`, `/register`, `/profile`, `/transfer`, tuyến làm việc/Admin khác đã khảo sát | Có | Có | Đây là trang/chốt thường, không trình thi chuyên biệt. |

Giữ điều kiện tiền tố `/attempt/` hiện có. Khớp loại xem trước theo toàn cấu trúc đường, ví dụ `^/admin/tests/[^/]+/versions/[^/]+/preview/?$`; tham số như `?module=listening` không ảnh hưởng. Không loại mọi tuyến Admin/xem lại/phiên/luyện bằng kiểm tra chuỗi con rộng. Không tuyến hiện tại khác cần loại.

## 7. Hệ thống kiểu chữ

Giữ dãy phông sans-serif cục bộ ưu tiên Segoe:

```css
"Segoe UI Variable", "Segoe UI", ui-sans-serif, system-ui,
-apple-system, BlinkMacSystemFont, sans-serif
```

Bỏ dự phòng `Inter` ngẫu nhiên thay vì ngụ ý đã có phông tải về. Dùng cùng dãy cho chữ trang thường, đề mục, nhãn, điều khiển. Hiệu ứng giấy từ khoảng cách/màu, không phông serif hoặc thư viện phông mới. Phông hệ thống dự phòng hỗ trợ dấu tiếng Việt; không đặt chiều cao chữ cố định hoặc hộp dòng chật.

| Vai trò | Cỡ | Độ đậm | Chiều cao dòng | Giãn chữ | Hoa thường |
| --- | --- | --- | --- | --- | --- |
| Nội dung | 16px | 400 | 1.6 | 0 | Viết hoa đầu câu tự nhiên |
| Nhỏ/metadata/trợ giúp | 13px | 400; nhấn 500 | 1.5 | 0 | Viết hoa đầu câu |
| Điều hướng | 14px | 500; hoạt động 600 | 1.4 | 0 | Viết hoa đầu câu |
| Nút | 14px | 600 | 1.4 | 0 | Viết hoa đầu câu |
| Dòng dẫn/ngữ cảnh trang | 13px | 500 | 1.5 | 0.01em | Viết hoa đầu câu |
| Tiêu đề trang / H1 | 32px máy tính, 28px nhỏ | 600 | 1.2 | -0.02em | Viết hoa đầu câu |
| Tiêu đề phần / H2 | 22px máy tính, 20px nhỏ | 600 | 1.3 | -0.01em | Viết hoa đầu câu |
| Tiêu đề thẻ / H3 | 18px | 600 | 1.35 | -0.01em | Giữ hoa thường nội dung biên soạn |
| Nhãn biểu mẫu | 14px | 500 | 1.4 | 0 | Viết hoa đầu câu |
| Trạng thái/huy hiệu | 12px | 500 | 1.4 | 0 | Viết hoa đầu câu |
| Huy hiệu mô-đun gọn | 12px | 600 | 1.4 | Tối đa 0.02em | Chỉ nơi này cho viết hoa toàn bộ |

Áp dụng thang cho đề mục chung, chữ hero tổng quan thường, đề mục tính năng và khung Admin, giữ ngữ nghĩa đề mục. Tiêu đề biên soạn hiện nguyên văn; CSS không được ép hoa thường. Giữ nhấn có chủ ý trong nội dung biên soạn và phông/cỡ riêng thi. Số điểm/chỉ số có thể lớn hơn nội dung, dùng số thẳng cột; không đổi ý nghĩa/định dạng.

Bỏ ép viết hoa và giãn chữ 0.07–0.17em khỏi dòng dẫn làm việc, khẩu hiệu thương hiệu, trạng thái, nhãn phiên bản, lời lộ trình, khung xác thực và dòng dẫn thẻ chung. `.page-context-kicker`, `.authoring-eyebrow`, `.history-eyebrow` hội tụ thang dòng dẫn; giữ viền ngữ cảnh nhỏ tùy chọn. Tránh độ đậm UI thường trên 600 trừ nhấn số cục bộ có lý do ở 700. Chuỗi trạng thái dùng khóa dịch; enum API không đổi.

Mọi biến thể nút hiện có chung chữ 14px/600, bán kính 8px, cao tối thiểu 40px trang máy tính thường, 44px đầu trang/thao tác màn hình nhỏ, đệm ngang 14px, khe biểu tượng 8px. Nút biểu tượng ít nhất 40px, 44px màn hình nhỏ, có tên tiếp cận. Chữ được xuống dòng cho thao tác tiếng Việt dài. Giữ biến thể ngữ nghĩa:

| Biến thể | Cách trình bày |
| --- | --- |
| Primary | Màu nhấn sản phẩm phẳng, chữ token tương phản; một thao tác chính mỗi nhóm cục bộ. |
| Secondary | Bề mặt giấy nổi, viền đủ rõ, chữ mực. |
| Ghost | Bề mặt trong suốt, chữ mực/nhẹ dễ đọc; rê chuột trung tính. |
| Danger | Token nguy hiểm phẳng, chữ tương phản khớp. |
| Danger ghost | Chữ nguy hiểm; rê nền nguy hiểm nhẹ; không phát sáng. |
| Thao tác mô-đun | Giữ quan hệ biến thể Reading/sản phẩm, Listening, Writing; màu ngữ nghĩa phẳng và chữ tương phản theo giao diện. |

Giữ ngữ nghĩa vô hiệu/chờ, hành vi liên kết/nút, nhãn tải và chỉ báo tiêu điểm. Thay nổi lên/bóng màu khi rê bằng đổi bề mặt/viền và chuyển màu 120–160ms. Không đổi kích thước nút trình thi chung qua quy tắc làm việc này.

## 8. Giao diện giấy sáng

Giữ tên token hiện có để nơi dùng không cần kiến trúc giao diện mới. Các giá trị này định nghĩa bảng màu đích làm việc:

| Token | Giá trị sáng | Công dụng |
| --- | --- | --- |
| `--app-bg`, `--paper` | `#f5f2eb` | Nền trang ngà ấm |
| `--app-bg-elevated` | `#eee9df` | Nền khung phụ |
| `--surface` | `#fcfaf5` | Thẻ/bảng giấy |
| `--surface-raised` | `#fffdf8` | Ô nhập, hộp thoại, phần tử nổi |
| `--surface-soft` | `#eeeae1` | Vùng nhóm nhẹ |
| `--surface-hover` | `#e8e3d9` | Rê chuột tương tác trung tính |
| `--surface-glass` | `#fcfaf5` | Bề mặt đầu trang/thanh công cụ đục |
| `--ink` | `#292620` | Mực ấm |
| `--ink-soft` | `#4c473e` | Chữ phụ |
| `--muted` | `#686155` | Chữ trợ giúp/metadata |
| `--line` | `#ddd6c9` | Đường trang trí/cạnh thẻ |
| `--line-strong` | `#8f8575` | Viền ô nhập/điều khiển |
| `--accent` | `#5261a8` | Nhận diện chàm hiện có tiết chế |
| `--accent-strong` | `#434f90` | Rê/nhấn chính |
| `--accent-soft`, `--surface-tint` | `#e7e9f3` | Vùng chọn nhỏ |
| `--accent-contrast` | `#ffffff` | Chữ thao tác nền màu nhấn/mô-đun |
| `--reading`, `--accent-cyan` | `#286f82` | Xanh lam ngọc ngữ nghĩa Reading |
| `--listening`, `--accent-violet` | `#725b91` | Tím ngữ nghĩa Listening |
| `--writing` | `#99562e` | Nâu cam ấm ngữ nghĩa Writing |
| `--success` / `--success-soft` | `#277052` / `#e7f0e9` | Trạng thái thành công |
| `--warning` / `--warning-soft` | `#8a581d` / `#f5ebd9` | Trạng thái cảnh báo |
| `--danger` / `--danger-soft` | `#a83c50` / `#f7e8eb` | Trạng thái phá hủy/lỗi |
| `--danger-contrast` | `#ffffff` | Chữ trên nền nguy hiểm |

Huy hiệu mô-đun dùng chữ ngữ nghĩa trên nền pha 8% màu ngữ nghĩa với giấy; bộ lọc chọn có thể dùng cùng sắc nhẹ kèm dấu rõ. Dùng điểm nhấn đặc 2–3px trên thẻ liên quan, không tô thân thẻ. Giữ nghĩa thành công/cảnh báo/lỗi độc lập danh tính mô-đun. Thông báo thông tin giữ trung tính.

Rà soát trang trí và quyết định áp dụng bề mặt làm việc cả hai giao diện:

| Trình bày hiện tại | Quyết định |
| --- | --- |
| Gradient hướng tâm body và trang trí `.app-shell::before` | Bỏ; dùng nền ứng dụng đặc. |
| Mờ kính `.app-header`, Builder/Library | Thay giấy đục/viền dưới; khung thường không cần làm mờ nền. |
| Gradient/ghi chú ngữ cảnh thanh bên | Bỏ cùng thanh bên toàn cục. |
| Lớp hướng tâm `.home-hero` và đường chéo trang trí `::after` | Bỏ; giữ cấu trúc trên bề mặt giấy. |
| Dấu hành tinh/cảnh tương tác trang chủ | Giữ SVG nhận diện/tương tác; bỏ ánh `.home-orbit-glow`, giảm đổ màu lõi thành bề mặt đặc/token nhẹ, bỏ bóng màu. Không thêm chuyển động/minh họa. |
| Gradient nhấn lộ trình/thẻ | Thay điểm nhấn sản phẩm/mô-đun đặc ngắn. |
| Gradient trạng thái rỗng, đầu History, đầu bài đọc, bảng Builder Listening/Writing | Thay surface hoặc surface-soft. Giữ bố cục chức năng/biên tập. |
| Phát sáng nút/giao diện khi rê và bóng màu trình sửa | Bỏ; rê trung tính/bóng tối thiểu. |
| Thanh tiến độ chức năng, ký hiệu biểu đồ, chỉ báo chọn/tiêu điểm | Giữ màu ngữ nghĩa; không bỏ hình mang thông tin. |
| Trình bày thi/tô sáng/hiển thị đáp án | Giữ hành vi và diện mạo thi đã phân giải; ngoài đợt dọn này. |

Thẻ thường không bóng trừ thật sự nổi. Sáng `--shadow-sm`: `0 1px 3px rgb(41 38 32 / 0.07)`; `--shadow-md`: `0 4px 12px rgb(41 38 32 / 0.08)`; hộp thoại `--shadow-lg`: `0 12px 32px rgb(41 38 32 / 0.16)`. Dùng sm cho thẻ nổi, md chỉ overlay thật sự nổi, lg cho modal/hộp thoại. Giữ định nghĩa `--glow-accent`/`--glow-violet` hiện có làm bí danh `--shadow-sm` trung tính trong dọn tương thích, không nơi làm việc dùng phát sáng màu. Bán kính thẻ 12px, trường/nút thường 8px, hộp thoại 14px; huy hiệu ngữ nghĩa có thể giữ dạng viên.

## 9. Giao diện giấy tối

Dùng `:root[data-theme="dark"]` và `color-scheme: dark`, cùng phân cấp/bố cục giao diện sáng:

| Token | Giá trị tối |
| --- | --- |
| `--app-bg`, `--paper` | `#201e1b` |
| `--app-bg-elevated` | `#25221e` |
| `--surface` | `#292622` |
| `--surface-raised` | `#312d28` |
| `--surface-soft` | `#35312c` |
| `--surface-hover` | `#3c3731` |
| `--surface-glass` | `#292622` |
| `--ink` | `#f1ece2` |
| `--ink-soft` | `#d2cbc0` |
| `--muted` | `#b4aa9a` |
| `--line` | `#494239` |
| `--line-strong` | `#8d8070` |
| `--accent` | `#a4afd9` |
| `--accent-strong` | `#b5bfe2` |
| `--accent-soft`, `--surface-tint` | `#333748` |
| `--accent-contrast`, `--danger-contrast` | `#201e1b` |
| `--reading`, `--accent-cyan` | `#94bac4` |
| `--listening`, `--accent-violet` | `#b4a4ce` |
| `--writing` | `#d2ab8b` |
| `--success` / `--success-soft` | `#a3c3ad` / `#26372d` |
| `--warning` / `--warning-soft` | `#d5b887` / `#3b3022` |
| `--danger` / `--danger-soft` | `#dda4aa` / `#3c292d` |

Giữ bề mặt than ấm thay xanh đen, dùng trắng ngà mềm thay trắng tối đa toàn bộ. Sắc huy hiệu dùng công thức 8%, thao tác nền đặc dùng chữ tối tương phản. Màu rê nhạt hơn chút; không thêm phát sáng đổi độ chói. Bóng tối: sm `0 1px 3px rgb(0 0 0 / 0.16)`, md `0 4px 12px rgb(0 0 0 / 0.20)`, lg `0 12px 32px rgb(0 0 0 / 0.30)`. Quyết định trang trí khác theo mục 8.

Giữ bảng màu thi sáng/tối rõ ở mục 13. Token làm việc ấm hơn không được âm thầm đổi màu điều khiển, tô sáng hoặc khung Candidate.

## 10. Kiến trúc ngôn ngữ và i18n

Hỗ trợ chính xác `type Locale = "en" | "vi"`, mặc định `en`, khóa lưu `ielts-locale`. Giao diện/ngôn ngữ là tùy chọn trình duyệt riêng, không gắn người đã xác thực. Không cần thư viện phụ thuộc, yêu cầu dịch mạng, trạng thái cơ sở dữ liệu, header API, tiền tố tuyến, cookie hoặc luồng sinh bản dịch.

Ranh giới tệp nhỏ:

```text
frontend/src/lib/i18n/
├── en.ts                 # English dictionary; canonical flat dotted keys
├── vi.ts                 # Vietnamese dictionary with identical key shape
├── types.ts              # Locale, TranslationKey, TranslationDictionary
├── translations.ts       # dictionaries and pure lookup/interpolation
└── locale-provider.tsx   # LocaleProvider, hooks, and UiText client boundary
```

Dùng khóa phẳng như `nav.skillPractice`, `common.save`, `practice.sectionNumber`, `history.tabs.focused`. Giá trị Anh là chuỗi thường. Khóa Anh định nghĩa union TypeScript; Việt dùng `satisfies TranslationDictionary`, giá trị mở rộng thành string, không literal tiếng Anh:

```ts
// Illustrative contract, not implementation added by this specification.
type Locale = "en" | "vi";
type TranslationKey = keyof typeof en;
type TranslationDictionary = Record<TranslationKey, string>;
// vi satisfies TranslationDictionary; dictionary map satisfies
// Record<Locale, TranslationDictionary>.
```

`types.ts` chỉ import kiểu từ điển Anh; `en.ts` không phụ thuộc provider. Thiếu/thừa khóa Việt và khóa nơi gọi không biết là lỗi biên dịch. Đóng gói Anh/Việt cục bộ; giao diện hai ngôn ngữ không cần tải từ điển theo nhu cầu.

API:

```ts
const { locale, setLocale } = useLocale();
const { t } = useTranslation();
t("nav.skillPractice");
t("practice.sectionNumber", { number: 2 });
```

`t` nhận `TranslationKey` và tham số vô hướng tùy chọn `Record<string, string | number>`. Dùng biến giữ chỗ tên `{number}`, `{count}`, `{title}`, thay như chuỗi thuần; React escape kết quả. Không thông điệp HTML, eval động, bộ phân tích rich-text hoặc chuỗi backend tùy ý làm khóa. Khi Anh cần số ít/nhiều, dùng khóa riêng chọn theo số đếm hiện có; Việt cung cấp cả hai giá trị tương ứng. Giữ định dạng số/ngày/giờ và tính thời gian hiện tại. Tra cứu phòng vệ có thể trả giá trị Anh nếu giá trị từ điển bất ngờ thiếu, nhưng TypeScript là kiểm tra đầy đủ chính.

Provider cung cấp hook ổn định, khởi tạo `en`, khôi phục giá trị lưu đã xác thực sau hydration, đặt `document.documentElement.lang` khi ngôn ngữ đổi. `setLocale` cập nhật ngữ cảnh ngay và lưu theo khả năng. Bộ chọn gọn gồm nút `EN`, `VI` trong nhóm ngôn ngữ bản địa hóa, tên tiếp cận đầy đủ `English` / `Tiếng Việt`, thuộc tính `lang` tương ứng, `aria-pressed` cho ngôn ngữ chọn. Không dùng cờ. Đổi ngôn ngữ chỉ đổi chữ, không điều hướng/đặt lại trạng thái tính năng.

## 11. Phạm vi dịch và ranh giới server/client

Dịch giai đoạn 1 bao phủ văn bản hệ thống sau, gồm điều khiển trình làm chung/tĩnh. Cả hai ngôn ngữ phải đủ khóa trong phạm vi; văn bản trình sửa Builder chuyên biệt là ngoại lệ hoãn rõ bên dưới. Toàn bộ nội dung IELTS biên soạn bị loại.

| Giao diện | UI hệ thống được dịch | Dữ liệu giữ nguyên văn |
| --- | --- | --- |
| Khung toàn cục | Điều hướng, tên tiếp cận thương hiệu, mô tả sản phẩm, nhãn ngôn ngữ/giao diện, Login/Register/Logout, nhãn vai trò, hộp thoại đăng xuất/nhãn chờ, mô tả chân trang | Tên sản phẩm, tên hiển thị |
| Thành phần cơ sở chung | Save, Cancel, Delete, Edit, Search, Retry, Continue, Resume, Review, Start, Submit, Back; tải, trạng thái rỗng chung, nhãn tổng quát/tên thao tác tiếp cận | ID, mã enum, tuyến |
| UI chung trình làm/xem lại/xem trước/chuyển Full Mock | Pause, Resume, Continue, Submit, Review, Exit/Leave, Back hiện có; thời gian còn/đã qua; Questions/Question và nhãn Section/Passage/Task sinh; nhãn thời gian/trạng thái chung, xác nhận, lỗi/dự phòng tĩnh, điều khiển/tên tiếp cận âm thanh chung như phát/dừng, tua, âm lượng, tốc độ | Mọi nội dung IELTS biên soạn, đáp án/câu trả lời, khóa/giải thích từ dữ liệu đề, ID/payload lượt, thời gian/trạng thái phát |
| Overview | Văn hero/hệ thống, nhãn/mô tả lộ trình, nhãn chỉ số/mục tiêu, thao tác chung | Giá trị hồ sơ, nội dung người dùng, chỉ số số học |
| Library và chi tiết xuất bản | Đề mục/mô tả trang, mô tả dự phòng, nhãn phiên bản/mô-đun/số lượng/thời gian, Open test, quay lại, điều khiển bắt đầu, cảnh báo sẵn sàng tạo cục bộ | Tiêu đề/mô tả đề/mô-đun biên soạn, DTO đóng băng |
| Skill Practice | Đề mục, lọc kỹ năng/đơn vị, All passages/sections/tasks, nhãn Section/Task sinh, thời gian, chữ bắt đầu/chờ/lỗi dự phòng, tóm tắt câu/từ, nhãn tìm kiếm, trạng thái rỗng, trợ giúp âm thanh khả dụng | Tiêu đề đề/bài đọc/phần, trích đề, nội dung câu, ID đích |
| History | Bốn nhãn thẻ, trạng thái, nhãn phiên bản/phạm vi/thời gian/số lượng, trạng thái rỗng, Resume/Review/Delete và xác nhận | Tiêu đề đề/đơn vị, tham chiếu đóng băng, điểm, ngữ nghĩa raw/max/không band |
| Analytics | Đề mục trang/bảng, lọc chung, nhãn chỉ số, chữ Compare/thao tác/rỗng, nhãn biểu đồ/điều khiển tiếp cận | Nhãn biên soạn/API chứa nội dung đề, số và dữ liệu biểu đồ |
| Hồ sơ/xác thực/khôi phục phiên | Nhãn trang/biểu mẫu, chữ xác thực dự phòng/chờ chung, khung Login/Register, chữ khôi phục/tải | Trường người dùng nhập, quyết định xác thực máy chủ |
| Admin | Nhãn bảng tổng quan/trang, thẻ/tìm/phân trang người dùng, nhãn trạng thái/vai trò, thao tác/hộp thoại người dùng chung, đề mục/giải thích chốt | Tên, email, bản ghi người dùng, số lượng |
| Builder/Transfer lượt đầu | Nhãn/mô tả trang chính, danh sách/tìm/thẻ đề, New test/nhãn biểu mẫu metadata, vòng đời phiên bản/Preview/Publish/Clone/Archive, trạng thái lưu, thẻ không gian Builder, nhãn tổng quan mô-đun, hộp thoại tạo/xóa mô-đun cấp trên, nhập/xuất/chọn tệp Transfer và nhãn kết quả chung | Tiêu đề/mô tả, đề, bài đọc, câu hỏi, lựa chọn, hướng dẫn, tên/nội dung tài sản biên soạn |

Hoãn văn bản Builder rất chuyên biệt: trình sửa loại câu lồng, giải thích hướng dẫn riêng registry, hướng dẫn đáp án, vùng điền/tooltip, công cụ marker sơ đồ, hướng dẫn biên tập khoảng âm thanh/thu đoạn. Hộp thoại/thao tác chung của chúng có thể dùng dịch nhưng giai đoạn này không duyệt mọi chuỗi chuyên biệt. Giữ chức năng khoảng, bảo toàn clone/ZIP, thay đổi vòng đời và kiến trúc registry. Không dịch mẫu hướng dẫn tạo nội dung câu IELTS chỉ vì nằm trong registry frontend.

Văn bản hệ thống chung/tĩnh của trình làm được dịch ở giai đoạn này qua từ điển chung. Áp cùng khóa tại điều khiển hiện có trong trình Reading/Listening/Writing, chốt tạm dừng, xem lại đáp án, DraftPreview, chuyển Full Mock. Chỉ dịch chuỗi/nhãn tiếp cận hiện có thuộc ứng dụng; không thêm điều khiển, đổi bố cục, thay renderer hoặc bản địa hóa metadata/nội dung thi biên soạn. UI âm thanh chung được dịch, còn cắt đoạn, quyền tua, tốc độ phát và chính sách Full Mock giữ nguyên.

Gắn dịch vào vị trí chữ/nhãn tiếp cận của client component hiện có. Giữ ổn định instance trình làm, khóa lượt/thẻ, kho câu trả lời, mốc thời gian, phần tử/nguồn/vị trí/tốc độ âm thanh, tô sáng, cờ, tự lưu và vòng đời yêu cầu. Locale hoặc `t` không được thành khóa/phụ thuộc khởi tạo lại lượt, đặt lại trạng thái, tạo lại âm thanh hoặc khởi lại yêu cầu. Đổi ngôn ngữ chỉ cập nhật trình bày: không được ghi miền, đổi payload lượt, điều hướng hoặc gắn lại lượt.

Dịch lỗi/dự phòng tĩnh cục bộ trong phạm vi, dùng nhánh trạng thái/mã hiện có khi có. Giữ nguyên thông điệp chẩn đoán máy chủ không biết; không suy bản dịch từ chuỗi tùy ý hoặc đổi hợp đồng backend. Dự phòng khôi phục phiên chỉ tiếng Việt hiện có đưa vào cùng từ điển mặc định Anh.

**Ranh giới máy chủ:** giữ route component bất đồng bộ, `serverApiRequest`, hành vi `notFound`/redirect và chốt vai trò máy chủ. Client provider không dịch literal đã được server component tạo. Dùng `UiText` nhỏ rõ ràng (xuất cùng provider) cho vị trí chữ tĩnh và ranh giới trình bày client tối thiểu nơi cần nhiều thuộc tính/nhãn dịch. `UiText` nhận khóa/giá trị vô hướng, hiển thị chữ đã escape, không phần tử bọc.

Cho vị trí chữ `PageHeading`, `EmptyState` nhận `ReactNode` thay chỉ `string`, để trang máy chủ truyền `<UiText message="pages.practice.title" />` hoặc tiêu đề biên soạn thô vào cùng thành phần hiện có. `aria-label` gốc, placeholder và chữ nút dịch trong client feature liên quan hiện có; khung overview/library thiên máy chủ có thể dùng một thành phần trình bày client thống nhất mỗi tính năng, nhận cùng DTO tuần tự hóa được. Tuyệt đối không truyền hàm dịch qua ranh giới server/client, đánh dấu trang tải bất đồng bộ `use client` hoặc chuyển import xác thực/API máy chủ vào client component.

Với huy hiệu mô-đun/trạng thái chung, giữ ánh xạ enum-kiểu, cho nhãn dịch tại nơi gọi UI làm việc và hệ thống trình làm chung. Tách định danh enum/kỹ năng/đơn vị ổn định khỏi nhãn dịch. Trong Skill Practice, sinh nhãn từ metadata hiện có khi render, giữ giá trị đích chuẩn hóa, đầu vào/thuật toán tìm khớp, khóa thẻ gắn và payload lượt. Locale không là khóa gắn lại React; đổi không được mất thời gian chọn, yêu cầu chờ, tìm kiếm, nháp hoặc trạng thái hộp thoại. Nhãn metadata tìm kiếm hiện có giữ ổn định giai đoạn này để dịch không thành thiết kế lại tìm kiếm.

Tuyệt đối không dịch tiêu đề/mô tả đề biên soạn, tiêu đề/văn bài Reading, nội dung Listening biên soạn, câu hỏi, lựa chọn đáp án, đề/trích đoạn/câu trả lời Writing, hướng dẫn đề do quản trị biên soạn, nội dung phần/task thủ công, đáp án/giải thích từ dữ liệu đề hoặc trường người dùng nhập. Giá trị giữ nguyên từng byte dữ liệu, tương đương hiển thị tại vị trí hiện có. Nhãn hệ thống sinh như `Question {number}`, `Section {number}`, `Passage {number}`, `Task {number}` được dịch; tuyệt đối không coi tiêu đề biên soạn là nhãn này. Không sửa DTO thay nội dung hoặc ghi chuỗi bản địa hóa qua API lưu. Ngôn ngữ đổi giao diện ứng dụng, không nội dung IELTS; không suy/viết lại ngôn ngữ nội dung biên soạn từ locale UI.

## 12. Hành vi thích ứng

Chọn **điều hướng ngang xuống dòng ở mọi kích thước**, không drawer, menu popup hoặc cắt ngang. Một DOM/danh sách điều hướng thích ứng qua CSS; không giữ bản máy tính/di động ẩn.

| Chiều rộng | Bố trí đầu trang | Điều hướng/thao tác |
| --- | --- | --- |
| ≥1440px | Thương hiệu, điều hướng, thao tác cùng hàng khi vừa; cao tối thiểu 72px, cao thực tự động. | Mọi liên kết hiện theo thứ tự cũ. Điều hướng được xuống dòng trong vùng cấp cho nhãn Việt dài; điều khiển không biến mất. |
| 768–1439px | Thương hiệu/thao tác hàng đầu, điều hướng chính toàn chiều rộng hàng hai. | Điều hướng xuống dòng tự nhiên, khe ngang 8px/dọc 4px; thao tác xuống dòng trong nhóm khi cần. Đầu trang sticky vẫn một khối cao tự động. |
| <768px | Thương hiệu hàng đầu, thao tác hàng sau, điều hướng xuống dòng bên dưới. Đầu trang trong luồng thường thay sticky. | Thao tác xuống theo cùng thứ tự DOM; mọi đích thấy là liên kết trong danh sách xuống dòng, vùng chạm tối thiểu 44px. Không trạng thái menu, chuyển động hoặc điều hướng chỉ cuộn. |

Giữ tên thương hiệu nhưng bỏ tagline đầu trang dư ở mọi kích thước; chân trang cung cấp mô tả. Giới hạn tên tài khoản hiển thị 120px máy tính/trung bình và 96px nhỏ với dấu ba chấm, giữ đầy đủ tên tiếp cận. Nhãn điều hướng xuống dòng theo từ, tuyệt đối không dấu ba chấm. Ở 320px, ADMIN và điều hướng Việt có thể nhiều hàng; đây là đánh đổi dễ đọc được chấp nhận, đầu trang nhỏ không sticky giữ truy cập nội dung trên màn hình thấp.

Đề mục/thao tác trang xếp tự nhiên, nhóm chân trang xếp, đệm theo mục 5. Bộ lọc/lưới Practice, thẻ History, điều hướng Builder cục bộ và bố cục xem lại giữ quy tắc thích ứng riêng. Đổi quy tắc `.app-sidebar`/`.sidebar-*` và giả định cột đầu trang cũ; không gỡ `.practice-filter-panel` hoặc `.builder-local-nav`. Dùng media query CSS, không `window.innerWidth`, chọn markup đầu.

## 13. Cô lập tuyến thi

AppShell thực hiện nhánh bỏ qua `/attempt/` hiện có trước GlobalHeader/AppFooter. LocaleProvider vẫn bên ngoài, sẵn cho thành phần trình làm hiện có dùng chữ hệ thống/nhãn tiếp cận chung/tĩnh giai đoạn này. Truy cập ngữ cảnh không cần điều khiển ngôn ngữ trình làm hoặc phần tử khung mới. Không điều hướng toàn cục, chân trang, giới hạn chiều rộng, đệm hoặc phần tử cố định mới được vào lượt thi.

Giữ giá trị token thi hiện có tại mốc đã khảo sát:

| Token thi | Sáng | Tối |
| --- | --- | --- |
| `--exam-bg` | `#eef2f8` | `#101319` |
| `--exam-surface` | `#ffffff` | `#191e27` |
| `--exam-surface-alt` | `#f5f7fb` | `#1e242e` |
| `--exam-text` | `#172039` | `#e8ecf3` |
| `--exam-muted` | `#626e88` | `#a1abba` |
| `--exam-border` | `#d6deeb` | `#364050` |
| `--exam-control-bg` | `#ffffff` | `#2a3342` |
| `--exam-control-text` | `#172039` | `#edf0f7` |
| `--exam-accent` cơ sở | `#256ea5` | Giá trị hiện có đã phân giải `#9aa6e8` |
| Màu nhấn Listening | Hiện có `#7957d5` | Hiện có `#b1a2cf` |
| Màu nhấn Writing | Hiện có `#cb6d30` | Hiện có `#d5a17d` |
| Nền/chữ tô sáng | `#f4dc86` / `#252137` | `#cbb674` / `#191820` |

Biến thi gốc vẫn rõ; `--exam-accent` cơ sở tối không được theo `--accent` làm việc mới. Quan hệ màu nhấn `.listening-exam`/Writing và điều khiển thi hiện có phải phân giải màu mô-đun cơ sở, không màu làm việc nhẹ mới. Đóng băng phụ thuộc token chung kế thừa hiện có dưới `.exam-shell`, `.exam-runner` cả hai giao diện (gồm mô-đun/màu nhấn, mực/bề mặt/viền, trạng thái/tô sáng, tương phản/bóng thực dùng). Lớp tương thích giới hạn này cũng bảo vệ xem trước Builder trong AppShell. Giữ cỡ body thi kế thừa 15px, kích thước nút, kiểu nhóm câu, trạng thái tiêu điểm/điều hướng, quy tắc thích ứng; ghi đè kiểu chữ làm việc phải loại hậu duệ trình thi.

Đây là bảo vệ tương thích CSS, không tái cấu trúc renderer/token. Rà soát tham chiếu thay vì thay mù `--exam-*` bằng bí danh làm việc. Chốt tạm dừng dưới `.exam-shell` giữ diện mạo dễ đọc. Nội dung câu trả lời/hành vi renderer xem lại không đổi; đề mục/bề mặt thường có thể kế thừa khung giấy mà không đổi tô đúng/sai, raw/max, độ chính xác hoặc band.

Chỉ chuỗi UI tĩnh/nhãn tiếp cận được gắn dịch chung trong trình làm; chữ dịch phải vừa điều khiển hiện có không đổi bố cục, kiểu, token thi. ThemeToggle chung cũng nhận chữ tiếp cận chung bản địa hóa, giữ vị trí/kiểu thi. Giữ nguyên chính sách âm thanh Listening đầy đủ độc lập/Full Mock, dự phòng âm thanh tập trung tùy chọn, cắt, tua, tốc độ, thời gian, tự lưu, tô sáng, cờ, chấm, chuyển trạng thái/bảo mật lượt và nội dung biên soạn. Đổi locale không được đặt lại câu trả lời/thời gian/âm thanh, gắn lại lượt, khởi lại yêu cầu hoặc đổi payload.

## 14. Khả năng tiếp cận

- Dùng header, một landmark điều hướng chính, landmark main khung hiện có và footer toàn cục trên trang thường. Thành phần đầu/chân mới không thêm main lồng. Thêm liên kết bỏ qua hiện khi bàn phím tới `#main-content`; không chèn vào trình thi. Markup cấu trúc trình làm/xem trước/xem lại thuộc tính năng hiện có giữ nguyên; chữ hệ thống/nhãn tiếp cận tĩnh bên trong được dịch.
- Điều hướng hoạt động dùng `aria-current="page"`, đậm 600, gạch dưới/dấu dưới nhìn thấy ngoài màu. Giữ vòng tiêu điểm và ngữ nghĩa liên kết đúng.
- Điều khiển ngôn ngữ dùng nhóm có tên và nút thường `aria-pressed`; tên đầy đủ vẫn cho công nghệ hỗ trợ. Sau đổi, `lang` gốc cập nhật `en`/`vi`. Điều khiển/nhãn tiếp cận trình làm chung theo locale đó; không bọc toàn UI trình làm đã dịch bằng ranh giới tiếng Anh. Giữ nội dung biên soạn/metadata ngôn ngữ. Ranh giới Anh cho chữ Builder chuyên biệt hoãn chỉ áp dụng chữ đó.
- Nút giao diện dùng nhãn thao tác bản địa hóa như `Use dark theme` / `Use light theme` (`Dùng giao diện tối` / `Dùng giao diện sáng`), khớp thao tác tiếp theo. Biểu tượng trang trí; nhãn thấy và tên tiếp cận đồng bộ.
- Giữ ngữ nghĩa hộp thoại đăng xuất, tiêu điểm ban đầu ở hủy, giữ Tab, quy tắc Escape/chờ, trả tiêu điểm. Đổi ngôn ngữ khi mở chỉ cập nhật chữ không tạo lại hộp thoại.
- Dịch xác nhận chung, nhãn thời gian/trạng thái, nhãn điều hướng sinh và tên tiếp cận âm thanh chung cùng chữ hệ thống hiển thị. Giữ tiêu điểm/chờ hộp thoại và ngữ nghĩa điều khiển; bản địa hóa không thêm hành vi điều hướng/trình phát.
- Liên kết/thao tác nhỏ cao vùng đích 44px. Điều hướng xuống dòng vẫn tới được theo DOM bằng Tab/Shift+Tab thường; không cần vai trò menu hoặc widget phím mũi tên. Nhãn Việt dài và zoom chữ 200% không được cắt bởi chiều cao cố định.
- Yêu cầu ≥4.5:1 chữ thường, ≥3:1 chữ lớn và viền điều khiển/tiêu điểm có ý nghĩa với nền kề. Đường trang trí nhẹ không làm viền điều khiển: dùng `--line-strong` cho ranh giới tương tác. Tránh opacity làm giảm tương phản chữ nhẹ.
- Cặp chữ/điều khiển và pha huy hiệu 8% đề xuất đã kiểm tra số học khi đặc tả. Primary/trắng sáng 5.78:1; huy hiệu Reading/Listening/Writing sáng 4.91/4.99/4.86:1. Chữ nhẹ/nền nổi tối 5.96:1, chữ nhấn/thao tác tối 7.69:1. Ví dụ viền điều khiển rõ là 3.57:1 sáng, 3.06:1 tối khi rê. Chữ nhẹ sáng đủ tối cho nền rê; chữ ngữ nghĩa thành công/cảnh báo/nguy hiểm trên nền nhẹ vượt 5:1 sáng, 6:1 tối. Xác minh sau cũng kiểm pha màu hiển thị thật, trạng thái rê, vòng tiêu điểm.
- Giữ giảm chuyển động. Trạng thái phản hồi gồm chữ/biểu tượng dễ đọc và ngữ nghĩa, không chỉ màu. Giữ vai trò alert/status hiện có nơi báo lỗi/công việc chờ.

## 15. Lưu trạng thái và hydration

**Ngôn ngữ:** SSR và render client đầu đều dùng `en`, gồm đề mục dịch và trạng thái bộ chọn. Tuyệt đối không đọc localStorage khi nạp mô-đun, render hoặc khởi tạo state. Effect khi provider gắn đọc `ielts-locale`, chỉ nhận `en`/`vi`, cập nhật state/`lang` gốc, hoàn tất khôi phục. Không ghi mặc định trước khôi phục xong. Tùy chọn Việt đã lưu thay chữ Anh sau hydration; chấp nhận khung hình đầu tiếng Anh ngắn. Không bootstrap ngôn ngữ viết lại chữ server, tra cookie/máy chủ hoặc ẩn cảnh báo hydration rộng.

Cùng khôi phục hoặc đổi ngôn ngữ trong phiên có thể cập nhật chữ trình làm chung sau lượt gắn. Cả hai không được tạo/đặt lại trình làm, câu trả lời, mốc thời gian, trạng thái âm thanh hoặc yêu cầu; danh tính provider/lượt giữ ổn định.

**Giao diện:** giữ `ielts-theme`, `data-theme`, hai bảng màu CSS và vị trí khởi tạo nội tuyến đáng tin. RootLayout vẫn render `data-theme="light"`. Bootstrap chọn tùy chọn sáng/tối hợp lệ đã lưu hoặc **sáng** nếu thiếu/sai/không truy cập được. Bỏ nhánh mặc định `matchMedia`; tùy chọn hệ điều hành không được âm thầm chọn chính sách thứ ba. Bootstrap chỉ được đặt thuộc tính giao diện gốc trước vẽ với `suppressHydrationWarning` gốc giới hạn hẹp hiện có. Không đổi chữ/cấu trúc con.

Markup/state React đầu ThemeToggle xác định là sáng. Layout effect sau hydration đối chiếu giá trị bootstrap/gốc, cập nhật nhãn thao tác tiếp theo dễ tiếp cận; nhấp cập nhật thuộc tính gốc/state ngay rồi lưu theo khả năng. Không cần provider/gói giao diện mới. Giữ quy tắc hiện nhãn CSS nếu giữ nhãn, nhưng nhãn thao tác tiếp cận phải đồng bộ. Nút trong trình thi tiếp tục hoạt động không có GlobalHeader.

**Lỗi:** bắt lỗi đọc/ghi riêng từng tùy chọn. Giá trị lưu thiếu/sai dùng en/sáng. Ghi thất bại vẫn cho chuyển trong tài liệu hiện tại. Lỗi tùy chọn không tạo banner, phá xác thực hoặc chặn luyện. Giữ tùy chọn qua chuyển tuyến client/đăng xuất; không dùng locale/giao diện làm khóa provider/trang. Đồng bộ giữa thẻ ngoài giai đoạn này; từng thẻ tự khôi phục khi gắn/tải.

**Dữ liệu SSR khác:** truyền năm chân trang hiện tại từ máy chủ vào AppShell/AppFooter, dùng cùng giá trị markup client đầu thay tự gọi đồng hồ client. Hành vi tải xác thực/dữ liệu trang máy chủ giữ nguyên. Không phân nhánh cấu trúc thích ứng theo đo client hoặc dịch bằng sửa DOM.

## 16. Chiến lược kiểm thử

Triển khai sau dùng Vitest/RTL có trọng tâm và kiểm tra hợp đồng CSS. Chính thay đổi tài liệu này cần tự rà soát thực chất và `git diff --check`, không chạy kiểm thử ứng dụng.

| Khu vực kiểm thử | Phạm vi trọng tâm bắt buộc |
| --- | --- |
| AppShell/đầu trang | Một điều hướng chính ngang, không aside/thanh bên toàn cục, liên kết khách/USER/ADMIN, đích/thứ tự/chính sách prefetch ổn định, Overview/Admin/Builder/Transfer hoạt động, hồ sơ không bịa liên kết hoạt động, tải/lỗi tài khoản, hành vi chốt/hộp thoại đăng xuất hiện có. |
| Chân trang/tuyến | Chân trang trên tuyến thường/xem lại/chuyển tiếp/xác thực; không đầu/chân trên lượt thi; đường xem trước Builder chính xác không chân toàn cục nhưng giữ đầu, kể cả query/dấu gạch cuối; Builder không xem trước vẫn chân; giữ main khung, đầu/chân không thêm main. |
| Ngôn ngữ | Mặc định Anh khi SSR/render đầu, khôi phục Việt hợp lệ, chọn/cập nhật chữ trực tiếp, lưu/gắn lại, giá trị sai, đọc/ghi ném lỗi, lang gốc, khóa từ điển có kiểu tương ứng, nội suy tham số thuần, đủ nhánh ít/nhiều nơi dùng. |
| Nội dung/trạng thái | Tiêu đề, đề/trích/lựa chọn biên soạn, tên người dùng không đổi; đổi ngôn ngữ giữ bộ lọc/tìm/thời gian/chốt chờ Practice, nháp/hộp thoại Builder; payload lượt tập trung không đổi, chọn locale không tạo HTTP mới. |
| Bản địa hóa/trạng thái trình làm | Trong lượt đã gắn, đổi EN → VI → EN qua provider chung; xác minh điều khiển, nhãn thời gian/trạng thái, xác nhận, nhãn đơn vị/câu sinh, nhãn âm thanh chung cập nhật nơi có. Khẳng định trường bài đọc/tiêu đề/hướng dẫn/đề/lựa chọn/câu trả lời biên soạn, cùng đáp án/giải thích khi dữ liệu xem lại đã chốt có, giữ từng byte và nội dung hiển thị tương đương. Khẳng định cùng trình làm/phần tử âm thanh (nếu có) vẫn gắn, câu đã sửa/mốc thời gian nguyên vẹn, giữ vị trí/tốc độ/trạng thái âm thanh, không khởi lại yêu cầu, payload không đổi. Dùng bộ kiểm thử provider chuyển locale, không thêm khung production. |
| Giao diện | `ielts-theme` hiện có, thuộc tính gốc đúng, cả hai hướng nhấp, khôi phục đã lưu, chưa lưu vẫn sáng dù giả lập hệ điều hành tối, lưu trữ sai/không khả dụng, tên thao tác tiếp bản địa hóa, markup server xác định/biến đổi bootstrap giới hạn. |
| Ngữ nghĩa thích ứng | Một nav/danh sách mọi breakpoint, ngữ nghĩa liên kết theo vai trò thấy, không điều hướng máy tính/di động trùng hoặc drawer; khẳng định CSS xuống dòng, đầu nhỏ không sticky, đệm, kích thước đích. RTL không tuyên bố kiểm bố cục pixel thật. |
| Tương thích thị giác | Token đủ hai giao diện, nền làm việc phẳng, giảm phát sáng/bóng, tương phản chữ/điều khiển/ngữ nghĩa dễ đọc bằng hàm độ chói hiện có, giữ tiêu điểm/giảm chuyển động, giá trị thi/phụ thuộc kế thừa/kích thước trình làm đóng băng. |

Mở rộng `auth.test.tsx`, `root-layout.test.tsx`, `theme-toggle.test.tsx`; thêm kiểm thử khung/chân/ngôn ngữ có trọng tâm khi cần. Cập nhật khẳng định `visual-system-css.test.ts`, `dark-theme-css.test.ts` yêu cầu thanh bên, sáng thương hiệu, kiểu chữ cố định hoặc tên thiên hà cũ. Giữ kiểm tra ngữ nghĩa/tương phản hữu ích và chốt `exam-theme-css.test.ts`. Chỉ tái dùng `skill-practice.test.tsx`, kiểm thử practice/library, History, điều hướng Admin/Builder và xem trước liên quan cho ranh giới trình bày đổi. Thêm trường hợp đổi locale vào kiểm thử trình Reading/Listening/Writing, hộp thoại/trình phát chung liên quan, dùng dữ liệu hư cấu/âm thanh giả thay phát thật. Xác minh `/attempt/*` vẫn không đầu/chân toàn cục, hợp đồng CSS/cấu trúc giữ bố cục, kiểu, token thi. Không mở rộng bộ ngoài phạm vi.

Xác minh sau nhắm `npx vitest run <changed-area test files>`, `npm run typecheck`, `npx eslint <changed TS/TSX files>`, `git diff --check`. Dùng hợp đồng CSS/kiểu/lint thay snapshot DOM lớn hoặc kiểm chữ theo pixel. Không yêu cầu trình duyệt, Playwright, E2E, Next dev server, bộ backend, âm thanh thật, gọi AI. Chọn tệp kiểm thử cụ thể thuộc thay đổi triển khai, không kế hoạch chi tiết trong đặc tả này.

## 17. Rủi ro và lưu ý tương thích

| Rủi ro | Biện pháp bắt buộc |
| --- | --- |
| Rộng thêm sau bỏ thanh bên 248px | Giới hạn rõ 1280/1440px và giới hạn biểu mẫu/văn bên trong; giữ lưới tính năng. |
| Liên kết ADMIN/tiếng Việt quá một hàng | Tự xuống dòng, bố trí trung bình/nhỏ rõ, không cắt chữ, đầu nhỏ không sticky. |
| Ngữ cảnh client không dịch được literal máy chủ | Ranh giới UiText/trình bày client rõ; giữ gọi máy chủ, DTO tuần tự hóa được, chốt xác thực. |
| Đổi token/CSS chung lan vào thi | Đóng băng giá trị thi/phụ thuộc kế thừa; loại hậu duệ trình làm khỏi đổi chữ/nút làm việc; hồi quy CSS có mục tiêu. |
| Đổi locale đặt lại lượt/khởi lại việc | Khóa tính năng/thẻ/provider/lượt và instance trình làm/âm thanh ổn định; không phụ thuộc locale/dịch trong khởi tạo, thời gian, tự lưu, phát, vòng đời yêu cầu. Giữ câu trả lời, mốc giờ, bắt đầu chờ, nháp, payload. |
| Nhầm chữ hệ thống với nội dung thi | Chỉ dịch chuỗi tĩnh/nhãn sinh thuộc ứng dụng; giữ nguyên văn tiêu đề, hướng dẫn, đề/lựa chọn, câu trả lời, đáp án/giải thích, metadata ngôn ngữ từ dữ liệu đề. |
| Nhãn dịch vô tình kéo theo thiết kế lại trình làm | Chỉ gắn vị trí chữ/nhãn tiếp cận; giữ điều khiển, bố cục, token thi, tiêu điểm, quy tắc phát/máy trạng thái; kiểm CSS/cấu trúc và giữ trạng thái có mục tiêu. |
| Đổi chuỗi vô tình đổi định danh/tìm kiếm | Giữ enum/đích API, đầu vào/thuật toán tìm hiện có; chỉ bản địa hóa nhãn hệ thống hiển thị. |
| Kiểm CSS hiện có ép thẩm mỹ lỗi thời | Thay kỳ vọng lỗi thời cụ thể bằng kiểm token/cấu trúc đã duyệt; giữ khẳng định tương phản, thi, thích ứng, ngữ nghĩa. |
| Lưu trữ bị chặn/hỏng | Mặc định xác định, khôi phục có xác thực, ghi theo khả năng; không UI lỗi tùy chọn. |
| Mốc giao diện ngầm theo hệ điều hành | Quyết định bootstrap đã-lưu-hoặc-sáng rõ và hồi quy; giữ tùy chọn tối đã lưu hợp lệ. |
| Xem trước nhận chân trang trùng | Loại đường xem trước chính xác, giữ chốt/đầu Admin và chân thi cục bộ. |
| Dịch chuyên biệt một phần thiếu nhất quán | Giới hạn rõ phạm vi Builder chung/chính; chỉ chữ trình sửa chuyên biệt đã nêu được hoãn. Điều khiển trình làm chung/tĩnh được dịch, nội dung IELTS biên soạn luôn loại. |

Không cần thay thư viện/lockfile, tài sản sinh, migration, schema API hoặc nội dung có bản quyền. Phiên bản xuất bản bất biến, tham chiếu lịch sử đóng băng, đánh giá/hạn máy chủ, registry câu cấu trúc, dữ liệu khoảng Builder và phân quyền vai trò không bị ảnh hưởng.

## 18. Trình tự triển khai tổng thể

1. Thiết lập từ điển Anh/Việt có kiểu, LocaleProvider cục bộ trình duyệt và ranh giới chữ client tối thiểu.
2. Tách trách nhiệm AppShell/Header/Footer, giữ hành vi xác thực/tuyến.
3. Thay thanh bên toàn cục bằng điều hướng ngang xuống dòng, thêm chân chung với loại trừ chính xác.
4. Áp token giấy cùng bảo vệ tương thích thi và khởi tạo giao diện đã-lưu-hoặc-sáng.
5. Áp kiểu chữ, nút, dọn bề mặt/gradient, chiều rộng, khoảng cách làm việc.
6. Dịch khung/thành phần chung, điều khiển trình làm chung/tĩnh hiện có, hộp thoại, chữ thời gian/trạng thái, nhãn sinh, nhãn thao tác tiếp cận mà không đổi hành vi.
7. Dịch phạm vi trình bày trang chính và Admin/Builder/Transfer chung đã chọn, giữ dữ liệu biên soạn và gọi máy chủ.
8. Hoàn tất xác minh hồi quy có trọng tâm, bỏ kiểu/khẳng định thanh bên toàn cục cũ.

Đây chỉ là trình tự kiến trúc. Không đưa nhiệm vụ triển khai, bắt đầu thay sản phẩm hoặc yêu cầu backend.

## 19. Tiêu chí nghiệm thu

Cho triển khai frontend sau:

1. Trang thường có một điều hướng chính ngang, không thanh bên Workspace cố định toàn cục; giữ tuyến/thứ tự/hiển thị vai trò/chốt hiện có.
2. Bỏ trùng ngữ cảnh đầu trang, giữ điều hướng tính năng/quay lại cục bộ, thao tác ngôn ngữ/giao diện/tài khoản theo thứ tự đã nêu.
3. Điều hướng xuống dòng theo kích thước định nghĩa, không drawer, DOM trùng, đích bị cắt hoặc phân nhánh hydration thích ứng.
4. Chân trang dùng nội dung thực, tiết chế, bản địa hóa và năm hiện tại máy chủ cấp. Hiện trên trang thường, vắng ở `/attempt/*` và tuyến xem trước Builder chính xác, không thay chân thi cục bộ.
5. Kiểu chữ, viết hoa đầu câu, kích thước/biến thể nút, khoảng cách, giới hạn nhóm trang theo mục 5 và 7, giữ hoa thường tiêu đề biên soạn.
6. Sáng dùng giấy ấm, tối graphite ấm; màu mô-đun/trạng thái phân biệt được, gradient/sáng bỏ hoặc giảm theo đặc tả, giữ tương phản/tiêu điểm dễ đọc.
7. Chỉ giao diện sáng/tối, khóa lưu/thuộc tính gốc hiện có, tùy chọn đã lưu hợp lệ, dự phòng sáng rõ; không chế độ tự động/hệ thống hoặc gói mới.
8. UI hệ thống EN/VI dùng từ điển cục bộ có kiểu, mặc định en, `ielts-locale`, trạng thái chọn tiếp cận, khôi phục/lưu theo khả năng không tuyến/cookie/tùy chọn backend.
9. Hai từ điển phủ bảng dịch giai đoạn 1: đề mục/thao tác/rỗng, khung Builder/Admin chung, điều khiển trình làm chung/tĩnh, nhãn sinh, chữ thời gian/trạng thái, hộp thoại, lỗi/dự phòng, UI/nhãn âm thanh chung hiện có. Chữ trình sửa Builder chuyên biệt tiếp tục hoãn; nội dung IELTS biên soạn không dịch.
10. Giữ gọi API máy chủ, chốt, ranh giới tuần tự hóa, enum API, nội dung IELTS biên soạn, trường người dùng. Đổi ngôn ngữ giữ trạng thái tính năng hoạt động, không ghi miền hoặc gọi xác thực mới.
11. Markup server/client đầu xác định; locale khôi phục sau hydration, bootstrap giao diện chỉ thuộc tính gốc, lỗi lưu không chặn dùng.
12. Lượt thi cô lập khỏi khung toàn cục và chiều rộng/kiểu làm việc. Bản địa hóa trình làm chỉ đổi chuỗi tĩnh/nhãn tiếp cận. Token thi cơ sở, bố cục, diện mạo kế thừa, hành vi câu, âm thanh, thời gian, tự lưu, tô sáng, cờ, Full Mock, chấm, máy trạng thái lượt giữ ổn định.
13. Kiểm thử frontend có trọng tâm, typecheck, ESLint mục tiêu, kiểm diff đạt; không yêu cầu xác minh trình duyệt/E2E/dev server/backend/AI.
14. Không thiết kế lại chức năng Library/Practice, hệ ảnh thu nhỏ, migration, hành vi xác thực/Speaking/AI mới, tệp phông hoặc thư viện mới.
15. Kiểm thử đổi EN/VI chứng minh điều khiển chung cập nhật, dữ liệu IELTS biên soạn giữ từng byte/tương đương hiển thị, không tạo lại instance lượt/trình làm/âm thanh, câu trả lời và trạng thái thời gian/âm thanh nguyên vẹn, không khởi lại yêu cầu/đổi payload. Loại đầu/chân ở lượt và hợp đồng CSS/bố cục thi tiếp tục đạt không cần trình duyệt/E2E.

Với sản phẩm đặc tả này: ghi lại khảo sát kho mã, giải quyết mọi quyết định/ranh giới yêu cầu, chỉ tài liệu này được commit/push. Triển khai sản phẩm nằm ngoài phạm vi nhiệm vụ.
