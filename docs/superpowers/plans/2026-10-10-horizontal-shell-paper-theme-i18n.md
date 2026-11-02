# Kế hoạch triển khai khung điều hướng ngang, giao diện giấy và EN/VI

> **Kiểm toán tài liệu: SUPERSEDED.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Kế hoạch triển khai khung điều hướng ngang, giao diện giấy và EN/VI. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../frontend/src/components/ui/app-shell.tsx).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/shared-platform.md); [kiểm toán và giới hạn](../../DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.

> **Dành cho agent triển khai:** SKILL PHỤ BẮT BUỘC: dùng superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans để thực hiện lần lượt từng nhiệm vụ. Các bước dùng ô đánh dấu (`- [ ]`) để theo dõi.

**Mục tiêu:** Thay sidebar workspace thường trực bằng điều hướng ngang, thêm footer chung, hệ thị giác giấy ấm/graphite và bản địa hóa UI hệ thống Anh/Việt có kiểu, không đổi nội dung IELTS do tác giả soạn hoặc hành vi thi.

**Kiến trúc:** RootLayout vẫn là server component, bọc cây AuthProvider/AppShell hiện có trong một LocaleProvider phía client. AppShell ghép GlobalHeader ngang và AppFooter trên tuyến workspace, giữ cơ chế bỏ qua tuyến thi; CSS cung cấp bố cục đáp ứng và bảo vệ tường minh giá trị giao diện thi khỏi bảng màu workspace mới. Từ điển đóng gói có kiểu dịch văn bản hệ thống qua view client hiện có và ranh giới trình bày server/client nhỏ, không đổi fetch dữ liệu hoặc định danh tính năng.

**Công nghệ:** Next.js, React, TypeScript, CSS, Vitest, React Testing Library

**Đặc tả:** `docs/superpowers/specs/2026-10-10-horizontal-shell-paper-theme-i18n-design.md`

## Ràng buộc chung

- Chỉ frontend. Không thêm phụ thuộc, đổi backend/API/schema/DB/migration, tải font, thêm tài sản nhị phân hoặc dịch vụ ngoài. Đọc `frontend/AGENTS.md` và hướng dẫn Next.js đi kèm liên quan trước viết mã triển khai.
- Đúng `en | vi`, mặc định `en`, khóa storage `ielts-locale`. Đúng hai giao diện light/dark, khóa `ielts-theme`; ưu tiên giao diện đã lưu hợp lệ, nếu không dùng light. Không có system/auto, tuyến ngôn ngữ, cookie, cờ quốc gia, đồng bộ xuyên tab hoặc bản dịch sinh tự động.
- Dịch UI tĩnh và nhãn hỗ trợ truy cập do ứng dụng sở hữu. Giữ tiêu đề/mô tả bài, tiêu đề/nội dung đoạn đọc, nội dung Listening, prompt/phương án câu hỏi, hướng dẫn quản trị viên, đề/response Writing, nội dung section/task soạn tay, đáp án/giải thích và giá trị người dùng. Ngôn ngữ đổi giao diện, không đổi nội dung IELTS.
- Bao gồm ngay điều khiển tĩnh chung của runner/review/preview/paused-gate/chuyển Full Mock. Không thiết kế lại runner, thêm điều khiển mới, đặt ranh giới ép tiếng Anh toàn runner hoặc đổi bố cục/token thi, timer, autosave, highlight, cờ, chính sách phát, chấm, bảo mật hoặc chuyển trạng thái attempt.
- Giữ Full Listening, Full Mock, âm thanh focused Listening tùy chọn, clip, quyền tua/tốc độ, raw/max + accuracy và không có focused Band. Không đổi nghiệp vụ Skill Practice/Test Library, AI, thiết kế auth hoặc triển khai Speaking. Trường đích Speaking hiện có chỉ được dịch nhãn.
- Giữ phiên bản published/DTO đóng băng, tuyến, mã enum, ID, payload, nhánh xác minh và guard server. Dịch nhánh dự phòng cục bộ; chẩn đoán server chưa biết và nhãn tác giả/API đi qua nguyên trạng.
- Ngôn ngữ/giao diện không trở thành key trang/thẻ/attempt hoặc phụ thuộc làm reset store, tạo lại audio, điều hướng hay gọi lại yêu cầu. SSR/văn bản client đầu là tiếng Anh; khôi phục ngôn ngữ sau hydration. Bootstrap giao diện gốc chỉ đổi `data-theme`, dùng phạm vi bỏ qua cảnh báo hydration hẹp hiện có ở root.
- Giữ editor Builder chuyên biệt và chức năng range. Hoãn trợ giúp lồng, hướng dẫn đáp án, công cụ completion/diagram, hướng dẫn khoảng âm thanh. Mẫu hướng dẫn IELTS là nội dung bị loại khỏi dịch, không phải việc dịch tồn đọng tương lai.
- Xác minh bằng Vitest/RTL tập trung, hợp đồng CSS/tính tương phản, typecheck, ESLint chọn lọc và `git diff --check`. Không trình duyệt/kiểm thủ công, Playwright/E2E, server dev, bộ backend, gọi AI, Modal hoặc âm thanh thật. Kiểm DOM/CSS không chứng minh render từng pixel.
- Lệnh test/ESLint/typecheck dưới chạy tại `frontend/`; lệnh Git tại gốc repository. Dùng gói/script đã cài (`test: vitest run`, `typecheck: tsc --noEmit`). Giả HTTP/media API; chỉ fixture hư cấu. Reset storage tùy chọn/thuộc tính root, khôi phục mock/timer giả từng kiểm thử.
- Mỗi commit triển khai chỉ gồm thay đổi/kiểm thử liệt kê. Cập nhật assertion lỗi thời khi nhiệm vụ sở hữu đổi hành vi, giữ kiểm tra hữu ích; không để nhiệm vụ trước hỏng đến Nhiệm vụ 12. Chạy `npm run typecheck`, `npx eslint <changed .ts/.tsx paths>` chọn lọc và `git diff --check` tại root trước mỗi commit.

## Trọng tâm rà soát

1. **ADMIN + tiếng Việt + tên dài:** cả tám liên kết chính trong một mốc điều hướng, xuống dòng không cắt/ẩn hành động. Nhiệm vụ 3 sở hữu `admin Vietnamese navigation preserves all routes`, Nhiệm vụ 5 sở hữu `header wraps at approved breakpoints`.
2. **Storage tùy chọn bị chặn/hỏng:** lỗi đọc/ghi/getter hoặc giá trị sai dùng mặc định en/light hợp lệ; vẫn chuyển được trong document hiện tại. Nhiệm vụ 1–2 sở hữu `locale storage failures are non-fatal` và `theme bootstrap defaults to light`.
3. **Đổi ngôn ngữ lúc đang làm:** văn bản cập nhật, định danh runner/audio, draft, timestamp timer và số yêu cầu ổn định. Nhiệm vụ 11 sở hữu `locale switch preserves active attempt state` cho Reading, Listening, Writing.
4. **Token workspace tối rò vào thi:** giá trị thi light/dark đóng băng và thuộc tính dùng chung kế thừa phân giải giống nhau ở attempt, paused gate, preview nhúng. Nhiệm vụ 6 sở hữu `paper tokens cannot change resolved exam colors or controls`.
5. **Loại footer đúng tuyến preview:** Builder preview giữ header/footer bài thi cục bộ, chỉ bỏ footer toàn cục; tuyến edit/detail/review/transition giữ footer. Nhiệm vụ 4 sở hữu `only exact Builder preview suppresses the global footer`.

## Bản đồ tệp

Đường dẫn dưới tính từ gốc repository. Tệp trình bày mới nhóm văn bản/thuộc tính của một tính năng thống nhất; tuyến fetch hiện có giữ fetch/guard. `PrimaryNavigation`, `HeaderActions`, `LocaleSwitcher` ở cục bộ `global-header.tsx`. Tái dùng icon, AppLogo, hằng tuyến, API client, registry/renderer câu hỏi, bộ timer/autosave, layout role server, không tái cấu trúc.

| Tạo | Trách nhiệm duy nhất |
| --- | --- |
| `frontend/src/lib/i18n/en.ts`, `vi.ts` | Cặp từ điển văn bản hệ thống phẳng; tiếng Anh định nghĩa key, tiếng Việt cung cấp giá trị chuỗi. |
| `frontend/src/lib/i18n/types.ts` | Kiểu ngôn ngữ/key/từ điển/tham số/hàm. |
| `frontend/src/lib/i18n/translations.ts` | Dịch/nội suy thuần và ánh xạ enum-thông điệp chung. |
| `frontend/src/lib/i18n/locale-provider.tsx` | Context tùy chọn client, hook và UiText không wrapper. |
| `frontend/src/components/ui/global-header.tsx` | Một điều hướng chính ngang, hành động auth/tùy chọn hiện có. |
| `frontend/src/components/ui/app-footer.tsx` | Mô tả sản phẩm, năm từ server, chỉ báo ngôn ngữ. |
| `frontend/src/components/home/overview-content.tsx` | Trình bày tổng quan từ kết quả server serialize được hiện có. |
| `frontend/src/features/practice/library-content.tsx` | Trình bày danh sách/chi tiết Library, gồm thuộc tính native đã dịch. |
| `frontend/src/features/auth/admin-content.tsx` | Trình bày dashboard/chi tiết người dùng Admin từ kết quả server hiện có. |
| `frontend/tests/locale-test-utils.tsx` | Harness provider/chuyển ngôn ngữ chỉ test dùng chung, giữ định danh con. |
| `frontend/tests/translations.test.ts`, `locale-provider.test.tsx` | Hợp đồng từ điển, nội suy, hydration, lưu tùy chọn. |
| `frontend/tests/app-shell.test.tsx`, `app-footer.test.tsx`, `shell-layout-css.test.ts` | Hợp đồng role/tuyến/khung UI/chiều rộng/bố cục shell đáp ứng. |
| `frontend/tests/common-localization.test.tsx`, `workspace-localization.test.tsx`, `runner-localization.test.tsx`, `localization-matrix.test.tsx` | Hồi quy trình bày song ngữ/giữ trạng thái có mục tiêu. |

| Sửa | Trách nhiệm duy nhất trong thay đổi này |
| --- | --- |
| `frontend/src/app/layout.tsx` | Vị trí provider, bootstrap giao diện xác định, năm footer server. |
| `frontend/src/app/globals.css` | Shell ngang, màu giấy, thang kích thước/nhịp, tương thích thi tường minh. |
| `frontend/src/components/ui/app-shell.tsx` | Loại trừ tuyến, chiều rộng nội dung, ghép shell. |
| `frontend/src/components/ui/theme-toggle.tsx` | Đối soát xác định, nội dung hành động kế đã dịch. |
| `frontend/src/components/ui/page-heading.tsx`, `empty-state.tsx` | Ô văn bản ReactNode cho UiText server/nội dung tác giả nguyên gốc. |
| `frontend/src/components/ui/module-badge.tsx`, `status-badge.tsx` | Nhãn dịch tùy chọn, giữ style theo enum. |
| `frontend/src/components/ui/confirm-dialog.tsx` | Nhãn chung mặc định đã dịch, giữ focus/pending hiện có. |
| `frontend/src/components/home/interactive-planet.tsx` | Chỉ nội dung hỗ trợ truy cập chung hiện có; không đổi chuyển động/định danh. |
| `frontend/src/features/auth/auth-provider.tsx` | Chỉ dịch dự phòng lỗi session do Local sở hữu ở lớp trình bày, giữ vòng đời yêu cầu. |
| `frontend/src/app/page.tsx`, `library/page.tsx`, `library/[versionId]/page.tsx` | Giữ tải/guard server, giao trình bày cho view client thống nhất. |
| `frontend/src/app/practice/page.tsx`, `history/page.tsx`, `analytics/page.tsx`, `transfer/page.tsx` | Heading server tĩnh qua UiText. |
| `frontend/src/app/profile/page.tsx` | Văn bản form client hiện có; giữ giá trị input/effect yêu cầu. |
| `frontend/src/app/login/page.tsx`, `register/page.tsx`, `session/restore/page.tsx` | Chỉ văn bản dự phòng Suspense tĩnh. |
| `frontend/src/features/auth/auth-form.tsx`, `session-restore.tsx` | Khung auth/restore, văn bản dự phòng cục bộ. |
| `frontend/src/features/practice/skill-practice.tsx`, `start-focused-practice.tsx` | Văn bản bộ lọc/thẻ/bắt đầu, không đổi lọc/đích/timer. |
| `frontend/src/features/history/attempt-history-list.tsx` | Bốn tab, văn bản trạng thái/hành động/xác nhận. |
| `frontend/src/features/analytics/analytics-dashboard.tsx` | Nhãn metric/bộ lọc/biểu đồ/điều khiển chung; dữ liệu biểu đồ không đổi. |
| `frontend/src/features/exam/start-attempt.tsx`, `start-full-mock.tsx` | Trình bày bắt đầu/timer/readiness; yêu cầu attempt không đổi. |
| `frontend/src/features/exam/focused-attempt.ts` | Helper hiển thị thuần nhận hàm dịch tùy chọn; phép tính điểm không đổi. |
| `frontend/src/features/test-builder/content-summary.tsx` | Heading đơn vị sinh có kiểu, tóm tắt chung, trích đoạn tác giả nguyên gốc. |
| `frontend/src/app/admin/page.tsx`, `admin/users/[userId]/page.tsx` | Giữ tải/guard server, ranh giới trình bày AdminContent. |
| `frontend/src/app/admin/tests/page.tsx`, `admin/tests/new/page.tsx`, `admin/tests/[testId]/page.tsx`, `admin/tests/[testId]/versions/[versionId]/edit/page.tsx` | Chỉ văn bản tuyến Builder chính. |
| `frontend/src/features/auth/admin-guard.tsx`, `admin-user-list.tsx`, `admin-user-actions.tsx` | Văn bản guard/danh sách/hành động người dùng chung hiện có. |
| `frontend/src/features/test-builder/test-library-list.tsx`, `new-test-form.tsx`, `test-details-heading.tsx`, `version-actions.tsx`, `builder-workspace-navigation.tsx`, `builder-lifecycle.tsx`, `autosave-link.tsx` | Dịch bước đầu khung danh sách/metadata/phiên bản/tab/trạng thái lưu, giữ logic vòng đời. |
| `frontend/src/features/test-builder/reading-builder.tsx`, `listening-builder.tsx`, `writing-builder.tsx`, `module-duration-editor.tsx`, `listening-section-editor.tsx` | Chỉ nhãn mô-đun/tạo/xóa/thời lượng cấp cao; hoãn công cụ/hướng dẫn lồng. |
| `frontend/src/features/transfer/transfer-portal.tsx` | Văn bản nhập/xuất/tệp/kết quả chung hiện có. |
| `frontend/src/features/reading/reading-runner.tsx`, `reading-review.tsx` | Chỉ chuỗi tĩnh runner/review, nhãn hỗ trợ truy cập. |
| `frontend/src/features/listening/listening-runner.tsx`, `listening-review.tsx`, `audio-player.tsx` | Văn bản điều khiển/dự phòng tĩnh; ba trạng thái phát hiện có không đổi. |
| `frontend/src/features/writing/writing-runner.tsx`, `writing-review.tsx` | Điều khiển/khung review tĩnh; giữ đề/response/dữ liệu đánh giá. |
| `frontend/src/features/exam/pause-attempt-control.tsx`, `paused-attempt-gate.tsx`, `draft-recovery-notices.tsx`, `test-session-transition.tsx`, `terminal-attempt-redirect.tsx`, `use-exam-submit.ts` | Văn bản trạng thái/lỗi/hành động tĩnh chung hiện có, không effect vòng đời phụ thuộc ngôn ngữ. |
| `frontend/src/features/test-builder/draft-preview.tsx` | Chỉ điều khiển preview/nhãn sinh chung. |
| `frontend/src/features/highlighting/selectable-text.tsx` | Chỉ nhãn hành động/dialog/lỗi highlight hiện có; không đổi văn bản chọn/offset ngữ nghĩa. |
| `frontend/src/features/questions/renderers.tsx`, `note-completion-renderer.tsx`, `table-completion-renderer.tsx`, `diagram-labelling-renderer.tsx` | Chỉ tên hỗ trợ truy cập Question chung/placeholder selector đáp án rỗng; nội dung tác giả, giá trị IELTS, bố cục renderer không đổi. |

Tệp test hiện có cần sửa được nêu trong khối **Tệp** từng nhiệm vụ. Không tuyến attempt/review/test-session/preview nào cần đổi fetch/dispatch vì bản địa hóa; test hiện có vẫn là đích hồi quy. Không dịch tệp editor câu hỏi chuyên biệt. ListeningSectionEditor chỉ gồm khung section cấp cao; trường range, capture/preview, hướng dẫn xác minh/hành vi range vẫn hoãn/giữ nguyên.

## Giao diện dùng chung đã chốt

Nhiệm vụ 1 sở hữu các export sau; nhiệm vụ tiếp phải dùng đúng tên/kiểu:

```ts
// en.ts / vi.ts: named exports en and vi; types.ts imports en as a type.
export type Locale = "en" | "vi";
export type TranslationKey = keyof typeof en;
export type TranslationDictionary = Record<TranslationKey, string>;
export type TranslationParams = Record<string, string | number>;
export type TranslationFunction = (
  key: TranslationKey, params?: TranslationParams,
) => string;

// translations.ts
export function translate(
  locale: Locale, key: TranslationKey, params?: TranslationParams,
): string;
export const moduleTranslationKeys: Record<"READING" | "LISTENING" | "WRITING", TranslationKey>;
export const statusTranslationKeys: Readonly<Record<string, TranslationKey>>;

// locale-provider.tsx ("use client")
export function LocaleProvider(props: { children: ReactNode }): ReactElement;
export function useLocale(): { locale: Locale; setLocale(locale: Locale): void };
export function useTranslation(): { t: TranslationFunction };
export function UiText(props: {
  message: TranslationKey; params?: TranslationParams;
}): ReactElement;
```

Tiếng Anh dùng `as const`; tiếng Việt dùng `satisfies TranslationDictionary`, không dùng kiểu literal giá trị tiếng Anh. UiText trả fragment văn bản đã escape. Context mặc định tiếng Anh, setter không làm gì khi ngoài provider, giữ tương thích test thành phần tiếng Anh cô lập hiện có; production luôn có provider root. Không có API dịch HTML. `translate` thay token tên `{parameter}`, giữ token chưa giải quyết khi thiếu tham số, dự phòng tiếng Anh nếu thiếu mục từ điển runtime. Số ít/nhiều dùng key tường minh theo số đếm hiện có. Không đổi định dạng số/ngày.

Nhiệm vụ 2 tạo `AppShell({ children, currentYear }: { children: ReactNode; currentYear: number }): ReactElement`; RootLayout cấp năm một lần ở server. Nhiệm vụ 3 tạo `GlobalHeader({ pathname }: { pathname: string }): ReactElement`. Nhiệm vụ 4 tạo `AppFooter({ year }: { year: number }): ReactElement`. Tất cả export có tên, không dùng tùy chọn làm key.

Nhiệm vụ 8 mở rộng PageHeading: `eyebrow?: ReactNode`, `title: ReactNode`, `description?: ReactNode`; EmptyState: `title: ReactNode`, `description: ReactNode`; prop khác không đổi. ModuleBadge thêm `label?: ReactNode` bên prop module hiện có; StatusBadge thêm `label?: ReactNode` bên prop status. Vẫn tương thích server, dùng ghi đè khi được cấp, giữ hiển thị dự phòng tiếng Anh cho bên gọi chưa chuyển/được hoãn.

Export trình bày client của Nhiệm vụ 9 được chốt:

```ts
export function OverviewContent(props: {
  publishedCount: number; resumableCount: number; testCount: number;
  isAdmin: boolean; adminStats: AdminStats | null; profile: Profile | null;
}): ReactElement;
export function LibraryContent(props: {
  items: Array<{
    test: TestSummary; version: TestSummary["versions"][number]; detail: VersionDetail;
  }>;
}): ReactElement;
export function LibraryVersionContent(props: {
  test: TestSummary; version: VersionDetail;
}): ReactElement;
```

Dùng import chỉ kiểu của DTO hiện có. Tuyến server vẫn chọn phiên bản published, fetch bản ghi, áp nhánh role, gọi notFound. View giữ quy tắc tính/thứ tự; không đưa hàm API/mô-đun server vào. Prop `AdminDashboardContent` Nhiệm vụ 10 là `{ stats: AdminStats | null; users: AdminUserList | null; search: string; status: "active" | "deactivated"; offset: number }`; prop `AdminUserDetailContent` là `{ detail: AdminUserDetail }`, cùng trả ReactElement từ `admin-content.tsx`. Giữ key danh sách `${status}:${search}:${offset}`.

Nhiệm vụ 9 chỉ mở rộng helper hiển thị thuần:

```ts
export function focusedUnitLabel(
  attempt: Pick<AttemptResponse, "scope" | "focused_unit">,
  t?: TranslationFunction,
): string | null;
export function accuracyLabel(
  raw: number | null, max: number | null, t?: TranslationFunction,
): string | null;
```

Hàm dịch mặc định tiếng Anh. Sinh nhãn đơn vị theo `kind`, `order_index + 1` hiện có; giữ `title` tác giả nguyên văn bên nhãn, giữ hành vi null/rỗng. Không phân tích/dịch nhãn server hoặc title để tìm kind. Accuracy giữ guard null/phép tính `(raw / max * 100).toFixed(1)`. Giao diện request/runner/player khác không đổi.

## Các nhiệm vụ

### Nhiệm vụ 1: Nền tảng i18n có kiểu

**Tệp:**
- Tạo: `frontend/src/lib/i18n/en.ts`, `vi.ts`, `types.ts`, `translations.ts`, `locale-provider.tsx`.
- Test (tạo): `frontend/tests/translations.test.ts`, `locale-provider.test.tsx`, `locale-test-utils.tsx`.

**Giao diện:**
- Đầu vào: Context/effect React và cấu hình Vitest/RTL hiện có.
- Đầu ra: Mọi export của Nhiệm vụ 1 trong Giao diện dùng chung đã chốt; thành phần chỉ dùng cho test `LocaleControls` sử dụng useLocale và `renderWithLocale(ui: ReactElement): RenderResult` trong `locale-test-utils.tsx`, render một provider với các phần tử con ổn định cùng các điều khiển đó.

- [ ] **Bước 1: Viết test thất bại**

Đặt tên test là `dictionaries have identical complete keys`, `interpolates scalar parameters as plain text`, `locale starts in English without render-time storage`, `restores only en or vi after mount` và `locale storage failures are non-fatal`. Kiểm tra `Pause` / `Tạm dừng`, `Question {number}` / `Câu hỏi {number}` với số 2, giữ token khi thiếu tham số, escape tham số `<img>`, không đọc storage trong SSR, khôi phục VI/lang ở root, giá trị không hợp lệ/null => en, không ghi mặc định trước khi khôi phục, và getter/getItem/setItem của storage ném lỗi. Ghi thất bại vẫn cập nhật UI/lang; không hiện banner. Bộ đếm mount của phần tử con vẫn là một sau khi chuyển đổi. Dùng renderToString cùng hydrateRoot để kiểm tra markup đầu tiên xác định, không dùng snapshot.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/translations.test.ts tests/locale-provider.test.tsx`

Kỳ vọng: FAIL vì các export từ điển/provider chưa tồn tại.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Triển khai đúng chữ ký đã chốt và khởi tạo cặp key `common.*`, `shell.*`, `theme.*`, `footer.*` cùng key điều khiển runner cần cho các test đầu tiên. Bổ sung đồng thời cả hai từ điển và nơi sử dụng ở các nhiệm vụ sau. Khởi tạo state bằng en, dùng một effect khôi phục khi mount, chỉ nhận đúng giá trị hợp lệ và bắt riêng lỗi ghi lưu trữ. Cập nhật lang ở root trong effect; không truy cập storage khi import/render/khởi tạo state, không ghi đè VI đã lưu bằng EN mặc định. Giữ setLocale ổn định, suy ra t từ locale hiện tại và render UiText bằng fragment. Định nghĩa các ánh xạ enum một lần, giữ mã và kiểu trình bày. Bộ hỗ trợ test chuyển đổi trên cùng một instance provider thay vì render lại phần tử con có key.

- [ ] **Bước 4: Chạy test tập trung**

Chạy: `npx vitest run tests/translations.test.ts tests/locale-provider.test.tsx`

Kỳ vọng: PASS, gồm khôi phục, escape và định danh khi mount; kiểm tra kiểu xác nhận bộ key tiếng Việt tương ứng.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/lib/i18n frontend/tests/translations.test.ts frontend/tests/locale-provider.test.tsx frontend/tests/locale-test-utils.tsx
git commit -m "Add typed English and Vietnamese UI translations"
```

### Nhiệm vụ 2: Layout root và hydrate tùy chọn

**Tệp:**
- Sửa: `frontend/src/app/layout.tsx`, `frontend/src/components/ui/app-shell.tsx`, `theme-toggle.tsx`, `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test: `frontend/tests/root-layout.test.tsx`, `theme-toggle.test.tsx`, `auth.test.tsx`, `locale-provider.test.tsx`, `builder-route.test.tsx`, `profile.test.tsx`, `skill-practice.test.tsx`, `transfer-portal.test.tsx`.

**Giao diện:**
- Đầu vào: LocaleProvider/useTranslation từ Nhiệm vụ 1; AuthProvider và export `themeInitializationScript` giữ nguyên.
- Đầu ra: Prop currentYear bắt buộc của AppShell; bootstrap hai giao diện xác định và nhãn hành động kế tiếp của ThemeToggle.

- [ ] **Bước 1: Viết test thất bại**

Mở rộng test root-layout: các provider lồng theo LocaleProvider → AuthProvider → AppShell; lang/văn bản/theme ở server vẫn là en/light dù đã lưu VI/dark; server truyền năm cố định trong test (2026). Chạy bootstrap tin cậy với storage giả lập: light/dark đã lưu được ưu tiên; dữ liệu thiếu, hỏng hoặc đọc ném lỗi đều chọn light dù hệ điều hành giả lập ưu tiên dark; script không có matchMedia hay ghi lại văn bản theo locale. ThemeToggle bắt đầu bằng markup light xác định, đồng bộ với root dark sau mount, hiện `Use light theme`, vẫn chuyển khi setItem thất bại và không đọc/ghi storage locale. Cập nhật mọi fixture AppShell hiện có trong các test auth, builder-route, profile, skill-practice và transfer-portal với `currentYear={2026}` để commit trung gian qua kiểm tra kiểu.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/root-layout.test.tsx tests/theme-toggle.test.tsx tests/auth.test.tsx tests/locale-provider.test.tsx tests/builder-route.test.tsx tests/profile.test.tsx tests/skill-practice.test.tsx tests/transfer-portal.test.tsx`

Kỳ vọng: FAIL do thiếu provider/năm và nhánh ngầm chọn dark theo hệ điều hành hiện có.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Bọc cây hiện có mà không chuyển việc tải API ở server sang client. Truyền `new Date().getFullYear()` từ RootLayout vào AppShell; AppShell nhận prop này trước khi tích hợp footer. Giữ bootstrap nội tuyến ở vị trí tin cậy hiện có và suppressHydrationWarning chỉ tại root; chọn theme đã lưu hợp lệ hoặc light ở nhánh catch/mặc định. ThemeToggle khởi tạo state React là light, dùng layout effect sau hydration để đồng bộ data-theme, rồi cập nhật state/root đồng bộ khi nhấn trước khi thử ghi storage. Dịch nhãn hiển thị/hỗ trợ truy cập cho hành động kế tiếp, không thêm theme provider hay đổi vị trí runner. Giữ AuthProvider được mount khi thay đổi tùy chọn.

- [ ] **Bước 4: Chạy test tập trung**

Chạy: `npx vitest run tests/root-layout.test.tsx tests/theme-toggle.test.tsx tests/auth.test.tsx tests/locale-provider.test.tsx tests/builder-route.test.tsx tests/profile.test.tsx tests/skill-practice.test.tsx tests/transfer-portal.test.tsx`

Kỳ vọng: PASS, không che cảnh báo văn bản hydration và không phát sinh request xác thực do đổi tùy chọn.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/app/layout.tsx frontend/src/components/ui/app-shell.tsx frontend/src/components/ui/theme-toggle.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/root-layout.test.tsx frontend/tests/theme-toggle.test.tsx frontend/tests/auth.test.tsx frontend/tests/locale-provider.test.tsx frontend/tests/builder-route.test.tsx frontend/tests/profile.test.tsx frontend/tests/skill-practice.test.tsx frontend/tests/transfer-portal.test.tsx
git commit -m "Make locale and theme hydration deterministic"
```

### Nhiệm vụ 3: Header toàn cục và điều hướng ngang

**Tệp:**
- Tạo: `frontend/src/components/ui/global-header.tsx`.
- Sửa: `frontend/src/components/ui/app-shell.tsx`, `frontend/src/app/globals.css`, `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test (tạo): `frontend/tests/app-shell.test.tsx`; sửa `frontend/tests/auth.test.tsx` và các kỳ vọng shell bị ảnh hưởng trong `dark-theme-css.test.ts`.

**Giao diện:**
- Đầu vào: AppShell currentYear, useAuth/logout hiện có, ThemeToggle, AppLogo/icon, `TRANSFER_ROUTE`, useLocale/useTranslation.
- Đầu ra: GlobalHeader(pathname); các hàm cục bộ PrimaryNavigation/HeaderActions/LocaleSwitcher, một nav và định danh mục ổn định theo tuyến.

- [ ] **Bước 1: Viết test thất bại**

Thêm `guest user and admin navigation preserve routes`, `admin active matching is exact`, `admin Vietnamese navigation preserves all routes` và `attempt routes bypass global chrome`. Khách thấy Overview cùng Login/Register; trạng thái tải/lỗi không hiện liên kết đặc quyền. USER có `/`, `/library`, `/practice`, `/history`, `/analytics`; ADMIN thêm `/admin`, `/admin/tests`, `/transfer` theo thứ tự đó. `/admin` chỉ khớp chính xác; Builder khớp các tuyến con mà không đồng thời kích hoạt Admin. Kiểm tra mọi liên kết ngoài trang chủ giữ prefetch false, một landmark Primary, aria-current và node liên kết ổn định khi đổi EN/VI. Kiểm tra không có aside toàn cục, ngữ cảnh Workspace/phần hiện tại lặp lại hay ghi chú Built for focus. Giữ test logout chỉ gọi một lần/đang chờ/hủy/focus. Tên hiển thị dài vẫn đọc được qua công nghệ hỗ trợ. Điều khiển locale có EN/VI, tên ngôn ngữ đầy đủ, lang và aria-pressed, không có cờ/role menu.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/app-shell.test.tsx tests/auth.test.tsx tests/dark-theme-css.test.ts`

Kỳ vọng: FAIL với sidebar hiện tại, thiếu nút locale và ngữ cảnh header.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Chuyển phần trình bày header/xác thực/logout của shell vào GlobalHeader, giữ ref chặn thao tác đang chờ và vòng đời ConfirmDialog. Dùng href tuyến làm key nav, key từ điển làm nhãn; giữ các hàm cục bộ trong tệp này. Thương hiệu gồm hành tinh hiện có + IELTS Studio, không lặp khẩu hiệu. Render thương hiệu, một nav ưu tiên văn bản và các hành động; thứ tự hành động là locale, theme, người dùng, logout, với lựa chọn xác thực tương ứng cho khách. Giữ lỗi phiên và quy tắc hiển thị theo role. AppShell giữ nhánh trả về sớm main.exam-shell cho `/attempt/`, các tuyến khác ghép header/main. Chỉ bỏ markup/quy tắc sidebar toàn cục; giữ bộ lọc Practice và điều hướng cục bộ Builder. Bổ sung CSS flex một cột/header tối thiểu ở bước này; Nhiệm vụ 5 thêm các hợp đồng responsive chính xác. Thay ngay các assertion sidebar đã bỏ trong test CSS dark bị ảnh hưởng.

- [ ] **Bước 4: Chạy test tập trung**

Chạy: `npx vitest run tests/app-shell.test.tsx tests/auth.test.tsx tests/dark-theme-css.test.ts`

Kỳ vọng: PASS cho tuyến, role, nav EN/VI, logout và nhánh bỏ qua shell của attempt.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/components/ui/global-header.tsx frontend/src/components/ui/app-shell.tsx frontend/src/app/globals.css frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/app-shell.test.tsx frontend/tests/auth.test.tsx frontend/tests/dark-theme-css.test.ts
git commit -m "Replace the workspace sidebar with horizontal navigation"
```

### Nhiệm vụ 4: Footer dùng chung và loại trừ tuyến chính xác

**Tệp:**
- Tạo: `frontend/src/components/ui/app-footer.tsx`.
- Sửa: `frontend/src/components/ui/app-shell.tsx`, `frontend/src/app/globals.css`, `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test (tạo): `frontend/tests/app-footer.test.tsx`; sửa `frontend/tests/app-shell.test.tsx`, `root-layout.test.tsx`.

**Giao diện:**
- Đầu vào: currentYear từ server, useLocale/useTranslation và usePathname.
- Đầu ra: AppFooter(year); `isBuilderPreview(pathname: string): boolean` cục bộ trong AppShell, dùng `^/admin/tests/[^/]+/versions/[^/]+/preview/?$`.

- [ ] **Bước 1: Viết test thất bại**

Thêm `only exact Builder preview suppresses the global footer`: ID attempt (gồm các tuyến con đang tạm dừng/kết thúc) không có header/footer; preview khớp chính xác, có thể có dấu gạch chéo cuối, chỉ có header toàn cục và .exam-footer cục bộ hiện có. Các tuyến Builder edit/detail/list/new, `/review/id`, `/test-session/id`, `/session/restore`, auth/profile/transfer và đường dẫn dễ nhầm chứa `preview` vẫn có footer toàn cục. Lựa chọn query không đổi cách khớp pathname. Kiểm tra tên sản phẩm, prop 2026, `Practice & authoring` / `Luyện tập và biên soạn đề` và chỉ báo English/Tiếng Việt; không tự thêm liên kết pháp lý/mạng xã hội. Footer SSR và lần render client đầu dùng cùng một năm.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/app-footer.test.tsx tests/app-shell.test.tsx tests/root-layout.test.tsx tests/draft-preview.test.tsx`

Kỳ vọng: FAIL vì footer dùng chung và quy tắc loại trừ preview chính xác chưa tồn tại.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Ghép AppFooter sau main có khả năng giãn trên mọi tuyến thông thường, chỉ loại trừ regex chính xác ở trên. Giữ attempt theo nhánh bỏ qua sớm hiện có và không sửa footer cục bộ của DraftPreview. Footer dùng năm từ server, nhận diện/mô tả sản phẩm và chỉ báo locale, không thêm bộ chọn thứ hai. Thêm bề mặt đặc/viền trên, padding dọc 24px, nhóm trái/phải trên desktop và các nhóm xếp chồng ở màn hình nhỏ với gap 12px. Không dùng đồng hồ client, không ẩn footer theo xác thực hay khớp chuỗi con quá rộng.

- [ ] **Bước 4: Chạy test tập trung**

Chạy: `npx vitest run tests/app-footer.test.tsx tests/app-shell.test.tsx tests/root-layout.test.tsx tests/draft-preview.test.tsx`

Kỳ vọng: PASS cho các trường hợp loại trừ chính xác và tuyến thông thường.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/components/ui/app-footer.tsx frontend/src/components/ui/app-shell.tsx frontend/src/app/globals.css frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/app-footer.test.tsx frontend/tests/app-shell.test.tsx frontend/tests/root-layout.test.tsx
git commit -m "Add the shared footer with exam route exclusions"
```

### Nhiệm vụ 5: Chiều rộng shell và bố cục responsive

**Tệp:**
- Sửa: `frontend/src/components/ui/app-shell.tsx`, `global-header.tsx`, `frontend/src/app/globals.css`.
- Test (tạo): `frontend/tests/shell-layout-css.test.ts`; sửa `frontend/tests/app-shell.test.tsx`, các assertion chiều rộng bị ảnh hưởng trong `visual-system-css.test.ts`.

**Giao diện:**
- Đầu vào: Một DOM header/nav/footer và các điều kiện loại trừ chính xác.
- Đầu ra: `contentWidth(pathname: string): "standard" | "wide"` cục bộ, các class `.app-content-standard` / `.app-content-wide`; bố cục theo breakpoint chỉ dùng CSS.

- [ ] **Bước 1: Viết test thất bại**

Thêm `page family selects the approved width` và `header wraps at approved breakpoints`. Chiều rộng ngoài chuẩn là 1280 cho Overview/review/chi tiết/form thông thường; chiều rộng lớn 1440 cho danh sách Library, Practice, History, Analytics, danh sách/dashboard Admin, workspace Builder và Transfer. Các tuyến chi tiết published `/library/[id]`, `/admin/users/[id]`, `/admin/tests/[id]` và `/admin/tests/new` được nêu rõ vẫn dùng chuẩn; version edit/preview vẫn dùng rộng. Chiều rộng trong của Profile là 920, new-test 720, auth 480 và transition 720. Kiểm tra giới hạn border-box gồm padding và văn mô tả <=72ch; attempt không có class chiều rộng/padding. Đọc khai báo CSS để chứng minh quy tắc >=1440, 768–1439 và <768, khả năng xuống dòng/chiều cao tự động, nav không cắt tràn hay nowrap, header màn hình nhỏ không sticky, giới hạn tên người dùng 120/96, một DOM nav và không có JS phụ thuộc chiều rộng. RTL giữ đủ tám liên kết ADMIN tiếng Việt cùng hành động trong DOM với văn bản dài; đây là test cấu trúc, không khẳng định đã đo việc xuống dòng.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/shell-layout-css.test.ts tests/app-shell.test.tsx tests/visual-system-css.test.ts`

Kỳ vọng: FAIL do thiếu class chiều rộng và các quy tắc khoảng cách/responsive shell hiện tại.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Phân loại đường dẫn cục bộ, xét ngoại lệ chi tiết/form mới đã nêu trước nhóm dùng chiều rộng lớn; không tạo lớp trừu tượng registry tuyến. Dùng min-height:100vh dự phòng rồi 100dvh, một cột, main flex-grow, container border-box căn giữa. Header/footer tối đa 1440. Padding ngang/trên/dưới main: desktop 32/40/48, trung bình 24/32/40, nhỏ 16/24/32. Desktop có chiều cao header tối thiểu 72px, chiều cao thực tự động, đủ chỗ cho thương hiệu/nav/hành động một hàng và xuống dòng tự nhiên với VI. Màn hình trung bình giữ header sticky thành một khối tự tăng chiều cao, thương hiệu/hành động trước rồi nav với gap ngang 8px/dọc 4px. Màn hình nhỏ dùng thương hiệu, hành động, nav xuống dòng bên dưới và không sticky; tại 320px cho phép nhiều hàng, vùng bấm vẫn 44px. Dùng một nav cùng CSS flex/grid, không drawer hay window.innerWidth. Giữ toàn bộ tên người dùng cho công nghệ hỗ trợ, chỉ rút gọn thị giác bằng dấu ba chấm; nhãn nav xuống dòng theo từ, không dấu ba chấm. Áp dụng giới hạn trong của form/văn bản <=72ch vào class hiện có và thay assertion chiều rộng sidebar toàn cục cố định, giữ quy tắc bố cục riêng của tính năng.

- [ ] **Bước 4: Chạy test tập trung**

Chạy: `npx vitest run tests/shell-layout-css.test.ts tests/app-shell.test.tsx tests/visual-system-css.test.ts`

Kỳ vọng: PASS cho chiều rộng, hợp đồng breakpoint trong mã nguồn và điều hướng dùng ngôn ngữ dài vẫn truy cập được.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/components/ui/app-shell.tsx frontend/src/components/ui/global-header.tsx frontend/src/app/globals.css frontend/tests/shell-layout-css.test.ts frontend/tests/app-shell.test.tsx frontend/tests/visual-system-css.test.ts
git commit -m "Apply responsive horizontal shell widths and spacing"
```

### Nhiệm vụ 6: Token giao diện giấy và tương thích bài thi tường minh

**Tệp:**
- Sửa: `frontend/src/app/globals.css`.
- Test: `frontend/tests/visual-system-css.test.ts`, `dark-theme-css.test.ts`, `exam-theme-css.test.ts`, `shell-layout-css.test.ts`.

**Giao diện:**
- Đầu vào: Bảng màu/bóng đổ trong đặc tả đã duyệt và nơi sử dụng CSS dùng chung/bài thi hiện tại.
- Đầu ra: Token giấy sáng/tối chính xác, giá trị bài thi cố định theo phạm vi, bề mặt đặc và bóng trung tính; không đổi API thành phần.

- [ ] **Bước 1: Viết test thất bại**

Thay kỳ vọng bảng màu cũ bằng toàn bộ bảng token sáng/tối đã duyệt, gồm nền sáng `#f5f2eb`, muted `#686155`, Writing `#99562e`, line-strong `#8f8575`; nền tối `#201e1b`, muted `#b4aa9a`, Writing `#d2ab8b`, line-strong `#8d8070`. Thêm `paper tokens cannot change resolved exam colors or controls`: ghi lại giá trị root/dùng chung mà .exam-shell/.exam-runner sử dụng trước khi sửa, phân giải khai báo sáng/tối theo phạm vi rồi đối chiếu sau sửa. Bao gồm preview nhúng trong Builder và màn hình chặn khi tạm dừng; exam-accent tối phải phân giải thành `#9aa6e8`, không thành accent workspace mới `#a4afd9`. Cố định mọi giá trị --exam-* và highlight, accent mô-đun, giá trị điều khiển/nút/focus và cỡ chữ thân bài thi 15px. Test độ tương phản workspace kiểm tra văn bản thường/hover >=4.5 và viền/focus có ý nghĩa >=3, gồm phối màu mô-đun 8% và nền trạng thái nhẹ; kiểm tra bài thi giữ mốc hiện có thay vì thiết kế lại điều khiển. Chỉ bỏ kỳ vọng không khí/glow đã bị thay thế.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts`

Kỳ vọng: FAIL do bảng màu thiên hà hiện tại và alias bài thi kế thừa chưa được bảo vệ.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Chép đúng mọi giá trị workspace từ bảng màu đặc tả; giữ tên token đã có và alias tương thích. Chép bóng trung tính đã duyệt: độ lệch sm/md/lg sáng 0 1px 3px / 0 4px 12px / 0 12px 32px với rgb(41 38 32), alpha .07/.08/.16; tối dùng cùng độ lệch, rgb(0 0 0), alpha .16/.20/.30. Glass là bề mặt đặc; alias glow đã ngừng dùng chuyển thành shadow-sm trung tính. Cố định các thuộc tính dùng chung hiện thực sự được exam-shell/runner kế thừa (màu chữ/bề mặt/đường viền/mô-đun/trạng thái/tương phản/bóng) bằng giá trị sáng/tối theo phạm vi tường minh. Giữ --exam-bg/surface/alt/text/muted/border/control-bg/control-text/accent và highlight ở giá trị bài thi cố định của đặc tả; tách exam-accent tối khỏi accent workspace. Áp dụng tương thích cả trong preview lồng và attempt, không tạo ExamShell mới hay viết lại renderer.

Bỏ gradient xuyên tâm trang trí ở body/shell, pseudo-element tạo không khí của shell, blur header/toolbar, trang trí không khí/đường chéo ở hero, bóng màu và gradient trang trí card trong cả hai theme. Giữ hành tinh SVG và class chuyển động; bỏ glow quỹ đạo xung quanh, dùng lõi màu đặc nhẹ và không drop-shadow màu. Làm phẳng trang trí accent card/empty/history/Builder/passage theo bề mặt đã duyệt; giữ tiến độ/biểu đồ/vùng chọn/focus/đúng sai/highlight có chức năng. Giữ quy tắc responsive bài thi và hình thức điều khiển tường minh hiện có; phần khung review thông thường có thể dùng bề mặt giấy.

- [ ] **Bước 4: Chạy test tập trung**

Chạy: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts tests/app-logo.test.tsx tests/interactive-planet.test.tsx`

Kỳ vọng: PASS với phép tính bảng màu/tương phản và mốc bài thi hiện tại được giữ, cùng hành vi SVG/chuyển động nguyên vẹn.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/app/globals.css frontend/tests/visual-system-css.test.ts frontend/tests/dark-theme-css.test.ts frontend/tests/exam-theme-css.test.ts frontend/tests/shell-layout-css.test.ts
git commit -m "Introduce paper and graphite themes with exam isolation"
```

### Nhiệm vụ 7: Chữ, nút và thành phần thị giác dùng chung

**Tệp:**
- Sửa: `frontend/src/app/globals.css`, `frontend/src/features/test-builder/content-summary.tsx`.
- Test: `frontend/tests/visual-system-css.test.ts`, `dark-theme-css.test.ts`, `exam-theme-css.test.ts`, `shell-layout-css.test.ts`.

**Giao diện:**
- Đầu vào: Phân tách token workspace/bài thi và class thành phần cơ bản hiện có.
- Đầu ra: Hợp đồng phông/thang cỡ/nút/bo góc/nhịp khoảng cách workspace đã duyệt; chưa đổi prop thành phần.

- [ ] **Bước 1: Viết test thất bại**

Kiểm tra bộ phông cục bộ ưu tiên Segoe, không tải Inter/phông; thân bài 16/400/1.6, metadata 13/400 hoặc nhấn mạnh 500/1.5, nav 14/500 và active 600/1.4, nút 14/600/1.4, nhãn trên tiêu đề 13/500/1.5/.01em, H1 32 (nhỏ 28)/600/1.2/-.02em, H2 22 (nhỏ 20)/600/1.3/-.01em, H3 18/600/1.35/-.01em, nhãn 14/500/1.4, trạng thái 12/500/1.4 và mô-đun 12/600/1.4/tracking<=.02em. Kiểm tra viết hoa đầu câu trừ nhãn mô-đun ngắn, không có quy tắc viết hoa nội dung tác giả, nút có bán kính 8/tối thiểu 40 và vùng bấm header nhỏ 44, không transform/glow khi hover, card 12/trường 8/dialog 14. Giữ thân bài thi 15 và số đo hiện có. Kiểm tra PageHeading cách dưới 24, nhãn trên tiêu đề gap 8, mô tả 12; trường form 16/nhóm 24; gap theo thang 4px, giữ gap 16 gọn của Practice.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts`

Kỳ vọng: FAIL do độ đậm/tracking/viết hoa và bán kính điều khiển cũ.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Áp dụng đúng thang trên vào selector workspace thông thường, loại trừ phần tử con .exam-shell/.exam-runner và giữ ghi đè tương thích từ Nhiệm vụ 6. Dùng `"Segoe UI Variable", "Segoe UI", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif`. Bỏ utility viết hoa/tracking của ContentSummary khỏi tiêu đề sinh tự động thay vì đổi kiểu chữ chuỗi tác giả. Làm phẳng nút primary/secondary/ghost/danger/danger-ghost/Listening/Writing; padding 14, gap icon 8, chuyển màu/bề mặt 120–160ms, không nhấc nút. Card mặc định không bóng; card nổi dùng sm, overlay md, dialog lg. Áp dụng nhịp trường/form/tiêu đề và gap 8/12/16/24/32/48 ở đúng ngữ cảnh đã duyệt. Chỉ dùng 700 cho chỉ số có ý nghĩa; giữ chữ số dạng bảng và hỗ trợ focus/giảm chuyển động.

- [ ] **Bước 4: Chạy test tập trung**

Chạy: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts tests/builder-workspace-page.test.tsx tests/skill-practice.test.tsx`

Kỳ vọng: PASS; thay có chủ đích các assertion CSS cũ còn hữu ích, không loại bỏ hàng loạt.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/app/globals.css frontend/src/features/test-builder/content-summary.tsx frontend/tests/visual-system-css.test.ts frontend/tests/dark-theme-css.test.ts frontend/tests/exam-theme-css.test.ts frontend/tests/shell-layout-css.test.ts
git commit -m "Apply the workspace typography and primitive scale"
```

### Nhiệm vụ 8: Dịch shell và nội dung dùng chung

**Tệp:**
- Sửa: `frontend/src/components/ui/global-header.tsx`, `app-shell.tsx`, `app-footer.tsx`, `theme-toggle.tsx`, `page-heading.tsx`, `empty-state.tsx`, `module-badge.tsx`, `status-badge.tsx`, `confirm-dialog.tsx`; `frontend/src/components/home/interactive-planet.tsx`; `frontend/src/features/auth/auth-provider.tsx`; `frontend/src/lib/i18n/en.ts`, `vi.ts`, `translations.ts`.
- Test (tạo): `frontend/tests/common-localization.test.tsx`; sửa `frontend/tests/app-shell.test.tsx`, `app-footer.test.tsx`, `theme-toggle.test.tsx`, `status-badge.test.tsx`, `auth.test.tsx`, `interactive-planet.test.tsx`, `translations.test.ts`.

**Giao diện:**
- Đầu vào: Hook/UiText và ánh xạ enum của Nhiệm vụ 1; header/footer đã dùng key từ Nhiệm vụ 3–4.
- Đầu ra: Vị trí ReactNode/nhãn badge tùy chọn đã chốt; nhãn dialog mặc định dùng chung đã dịch và toàn bộ văn bản shell.

- [ ] **Bước 1: Viết test thất bại**

Thêm `common primitives accept translated nodes and raw authored titles`, `open logout dialog changes language without recreation` và `locale switch does not recheck auth`. Giữ nguyên tên hiển thị người dùng; nhãn role, hành động theme kế tiếp, nhóm ngôn ngữ, tên thương hiệu cho công nghệ hỗ trợ, mô tả footer và tiêu đề/mô tả/đang chờ/hủy của logout cùng đổi. Chuyển ngôn ngữ khi dialog đang mở: vẫn cùng node dialog, focus vẫn ở nút hủy, giữ quy tắc Tab/Escape/đang chờ và request logout chỉ gọi một lần. Kiểm tra kiểu enum/giá trị dự phòng không rõ vẫn hoạt động với nhãn badge tùy chọn. PageHeading/EmptyState ở SSR có thể nhận fragment UiText hoặc chuỗi gốc mà không đổi wrapper/bố cục. Thông báo chẩn đoán phiên từ server không xác định giữ nguyên; chỉ dịch thông báo dự phòng do ứng dụng quản lý. Storage theme và locale vẫn độc lập.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/common-localization.test.tsx tests/app-shell.test.tsx tests/app-footer.test.tsx tests/theme-toggle.test.tsx tests/status-badge.test.tsx tests/auth.test.tsx tests/interactive-planet.test.tsx tests/translations.test.ts`

Kỳ vọng: FAIL do prop thành phần cơ bản chỉ nhận chuỗi và phần văn bản dialog/hỗ trợ truy cập dùng chung còn tĩnh.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Chỉ mở rộng các vị trí văn bản đã chốt và thêm nhãn hiển thị badge tùy chọn; giữ markup/class/kiểu trình bày và đầu vào enum. ConfirmDialog dịch mặc định Cancel/Working lúc render, vẫn ưu tiên ghi đè tường minh từ bên gọi và giữ effect phụ thuộc open/pending/callback. Hoàn tất từ điển common/shell cùng vị trí trình bày, gồm nhãn theme/hỗ trợ truy cập/liên kết bỏ qua. Chỉ giữ liên kết bỏ qua ở shell thông thường, trỏ tới main hiện có `id="main-content"`. AuthProvider lưu state phân biệt thông báo dự phòng do ứng dụng quản lý với chẩn đoán gốc và phân giải dự phòng lúc trình bày; không đưa t/locale vào dependency của effect/callback tải xác thực/logout/refresh. Dịch nội dung hỗ trợ truy cập chung hiện có của hành tinh mà không đổi effect con trỏ/giảm chuyển động. Không tự khớp chuỗi bất kỳ sang bản dịch, truyền hàm qua prop server hay chuyển rộng các thành phần cơ bản thành client.

- [ ] **Bước 4: Chạy test tập trung**

Chạy lệnh ở Bước 2 cùng `npx vitest run tests/root-layout.test.tsx tests/locale-provider.test.tsx`.

Kỳ vọng: PASS cho UI dùng chung EN/VI, ranh giới SSR, focus và định danh xác thực ổn định.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/components/ui/global-header.tsx frontend/src/components/ui/app-shell.tsx frontend/src/components/ui/app-footer.tsx frontend/src/components/ui/theme-toggle.tsx frontend/src/components/ui/page-heading.tsx frontend/src/components/ui/empty-state.tsx frontend/src/components/ui/module-badge.tsx frontend/src/components/ui/status-badge.tsx frontend/src/components/ui/confirm-dialog.tsx frontend/src/components/home/interactive-planet.tsx frontend/src/features/auth/auth-provider.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/src/lib/i18n/translations.ts frontend/tests/common-localization.test.tsx frontend/tests/app-shell.test.tsx frontend/tests/app-footer.test.tsx frontend/tests/theme-toggle.test.tsx frontend/tests/status-badge.test.tsx frontend/tests/auth.test.tsx frontend/tests/interactive-planet.test.tsx frontend/tests/translations.test.ts
git commit -m "Localize shared shell and common UI copy"
```

### Nhiệm vụ 9: Dịch các trang workspace chính

**Tệp:**
- Tạo: `frontend/src/components/home/overview-content.tsx`, `frontend/src/features/practice/library-content.tsx`.
- Sửa: `frontend/src/app/page.tsx`, `library/page.tsx`, `library/[versionId]/page.tsx`, `practice/page.tsx`, `history/page.tsx`, `analytics/page.tsx`, `profile/page.tsx`, `login/page.tsx`, `register/page.tsx`, `session/restore/page.tsx`; `frontend/src/features/auth/auth-form.tsx`, `session-restore.tsx`; `frontend/src/features/practice/skill-practice.tsx`, `start-focused-practice.tsx`; `frontend/src/features/history/attempt-history-list.tsx`; `frontend/src/features/analytics/analytics-dashboard.tsx`; `frontend/src/features/exam/start-attempt.tsx`, `start-full-mock.tsx`, `focused-attempt.ts`; `frontend/src/features/test-builder/content-summary.tsx`; `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test (tạo): `frontend/tests/workspace-localization.test.tsx`; sửa `frontend/tests/home-user-metric.test.tsx`, `practice-library.test.tsx`, `skill-practice.test.tsx`, `attempt-history-list.test.tsx`, `analytics-dashboard.test.tsx`, `profile.test.tsx`, `auth.test.tsx`, `auth-session-restore.test.tsx`, `translations.test.ts`.

**Giao diện:**
- Đầu vào: Vị trí UiText/ReactNode ở server, useTranslation, nhãn badge ghi đè và ánh xạ enum dùng chung.
- Đầu ra: OverviewContent/LibraryContent/LibraryVersionContent và helper hiển thị nhận hàm dịch tùy chọn theo giao diện đã chốt. SummaryUnit hiện có của ContentSummary được export với `heading: { message: "common.passageNumber" | "common.sectionNumber" | "common.taskNumber"; params: { number: number } }`; các trường khác giữ nguyên. Cả hai hàm tạo summary thuần trả kiểu đó; ContentSummary là thành phần trình bày client và dùng message+number làm key đơn vị, không dùng văn bản đã dịch.

- [ ] **Bước 1: Viết test thất bại**

Thêm `workspace locale changes copy without changing selected state` và `generated labels translate while authored titles stay exact`. Kiểm tra tiêu đề/mục tiêu Overview, danh sách/chi tiết/rỗng/sẵn sàng của Library, bộ lọc/tìm kiếm/số lượng/bộ đếm thời gian/hỗ trợ âm thanh của Practice, cả bốn tab/hành động/trạng thái History, nhãn chung Analytics, khung Profile/auth/restore. Lưu truy vấn Practice, bộ lọc kỹ năng/đơn vị và thời lượng không mặc định; chuyển ngôn ngữ rồi kiểm tra card/ID/đầu vào request đã chọn giữ nguyên. Giữ tab History và dialog xóa đang mở, lựa chọn Analytics và bản nháp nhập liệu Profile. Tiêu đề giả lập `Section 2` vẫn chính xác là `Section 2` khi do tác giả nhập, còn nhãn Section 2 sinh tự động đổi thành `Phần 2`; bao gồm dấu tiếng Việt/văn bản giống HTML/đoạn trích đề/options. So sánh fixture DTO đã serialize trước/sau. Mô tả dự phòng tạo cục bộ chỉ dịch khi mô tả tác giả là null. Giả lập tuyến server một lần và kiểm tra chuyển ngôn ngữ không gọi lại hàm fetch hay startAttempt. Effect auth/restore không khởi động lại; văn bản restore mặc định chuyển thành tiếng Anh thay cho nội dung hiện chỉ có tiếng Việt.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/workspace-localization.test.tsx tests/home-user-metric.test.tsx tests/practice-library.test.tsx tests/skill-practice.test.tsx tests/attempt-history-list.test.tsx tests/analytics-dashboard.test.tsx tests/profile.test.tsx tests/auth-session-restore.test.tsx tests/translations.test.ts`

Kỳ vọng: FAIL do các chuỗi tiếng Anh còn lại và tiêu đề summary sinh tự động chưa có kiểu.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Chỉ chuyển phần trình bày Overview và Library vào các tệp client gắn kết đã chốt để aria-label và nhãn gốc của chúng dùng được t. Giữ fetch bất đồng bộ, lọc phiên bản published, tải stats/profile theo role, guard/notFound và DTO có thể serialize ở server. Các trang server khác truyền UiText cho tiêu đề và nội dung dự phòng Suspense; tính năng client hiện có dịch tại đúng vị trí hiện tại. Giữ thuật toán sắp xếp/tìm kiếm và dữ liệu tác giả gốc dùng để tìm; không suy ra kết quả lọc từ nhãn mới dịch. Dùng định danh tuyến/enum/UUID thay cho tiêu đề đã dịch làm key danh sách sinh tự động.

Bao phủ mọi dòng thuộc phạm vi trong mục 11 của đặc tả cho các trang này. Thêm cặp key `pages.*`, `practice.*`, `history.*`, `analytics.*`, `profile.*`, `auth.*` và key chung cho đơn vị/số lượng/độ chính xác sinh tự động. Giữ giá trị trường, điểm thô và định dạng ngày. Hàm tạo summary mang mô tả heading thay cho chuỗi tiếng Anh; chỉ nhãn loại/nhóm do ứng dụng quản lý ánh xạ sang key cục bộ trong trình bày summary/card, không sửa mẫu hướng dẫn registry hay helper editor. Mở rộng focusedUnitLabel/accuracyLabel theo giao diện đã chốt, với mặc định tiếng Anh và phép tính hiện tại. View bắt đầu ở client tạo văn bản sẵn sàng đã dịch từ mô-đun/số lượng hiện có nhưng giữ nguyên quy tắc khả dụng/thời gian/request. State dự phòng/lỗi cục bộ lưu key/nhánh rồi render qua t; thông báo server không xác định giữ nguyên và không đưa t vào dependency request.

- [ ] **Bước 4: Chạy test tập trung**

Chạy lệnh ở Bước 2 cùng `npx vitest run tests/auth.test.tsx tests/builder-workspace-page.test.tsx tests/focused-reading-review.test.tsx tests/focused-listening-review.test.tsx` để bao phủ tương thích tiếng Anh của summary/helper dùng chung.

Kỳ vọng: PASS, giữ state/nội dung/payload và không đổi tính khả dụng/cách chấm focused.

- [ ] **Bước 5: Commit**

```bash
git --literal-pathspecs add -- frontend/src/components/home/overview-content.tsx frontend/src/features/practice/library-content.tsx frontend/src/app/page.tsx frontend/src/app/library/page.tsx 'frontend/src/app/library/[versionId]/page.tsx' frontend/src/app/practice/page.tsx frontend/src/app/history/page.tsx frontend/src/app/analytics/page.tsx frontend/src/app/profile/page.tsx frontend/src/app/login/page.tsx frontend/src/app/register/page.tsx frontend/src/app/session/restore/page.tsx frontend/src/features/auth/auth-form.tsx frontend/src/features/auth/session-restore.tsx frontend/src/features/practice/skill-practice.tsx frontend/src/features/practice/start-focused-practice.tsx frontend/src/features/history/attempt-history-list.tsx frontend/src/features/analytics/analytics-dashboard.tsx frontend/src/features/exam/start-attempt.tsx frontend/src/features/exam/start-full-mock.tsx frontend/src/features/exam/focused-attempt.ts frontend/src/features/test-builder/content-summary.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/workspace-localization.test.tsx frontend/tests/home-user-metric.test.tsx frontend/tests/practice-library.test.tsx frontend/tests/skill-practice.test.tsx frontend/tests/attempt-history-list.test.tsx frontend/tests/analytics-dashboard.test.tsx frontend/tests/profile.test.tsx frontend/tests/auth.test.tsx frontend/tests/auth-session-restore.test.tsx frontend/tests/translations.test.ts
git commit -m "Localize main workspace pages and practice controls"
```

### Nhiệm vụ 10: Dịch đợt đầu Admin, Builder và Transfer

**Tệp:**
- Tạo: `frontend/src/features/auth/admin-content.tsx`.
- Sửa: `frontend/src/app/admin/page.tsx`, `admin/users/[userId]/page.tsx`, `admin/tests/page.tsx`, `admin/tests/new/page.tsx`, `admin/tests/[testId]/page.tsx`, `admin/tests/[testId]/versions/[versionId]/edit/page.tsx`, `transfer/page.tsx`; `frontend/src/features/auth/admin-guard.tsx`, `admin-user-list.tsx`, `admin-user-actions.tsx`; `frontend/src/features/test-builder/test-library-list.tsx`, `new-test-form.tsx`, `test-details-heading.tsx`, `version-actions.tsx`, `builder-workspace-navigation.tsx`, `builder-lifecycle.tsx`, `autosave-link.tsx`, `reading-builder.tsx`, `listening-builder.tsx`, `writing-builder.tsx`, `module-duration-editor.tsx`, `listening-section-editor.tsx`; `frontend/src/features/transfer/transfer-portal.tsx`; `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Test: `frontend/tests/admin-dashboard.test.tsx`, `admin-user-list.test.tsx`, `admin-user-detail.test.tsx`, `test-library-list.test.tsx`, `version-actions.test.tsx`, `builder-workspace-navigation.test.tsx`, `builder-workspace-page.test.tsx`, `builder-autosave.test.tsx`, `module-duration-editor.test.tsx`, `transfer-portal.test.tsx`, `workspace-localization.test.tsx`, `translations.test.ts`.

**Giao diện:**
- Đầu vào: Prop DTO AdminContent đã chốt, summary/key dùng chung và API BuilderLifecycle/context không đổi.
- Đầu ra: Đầy đủ key đợt đầu `admin.*`, `builder.*`, `transfer.*`; không đổi API editor/vòng đời/request.

- [ ] **Bước 1: Viết test thất bại**

Thêm assertion song ngữ vào fixture tính năng hiện có cho dashboard/guard/role người dùng và dialog dùng chung; tab/tìm kiếm danh sách test, metadata test mới, Preview/Validate/Publish/Clone/Archive phiên bản, tab workspace/tổng quan mô-đun/tạo/xóa/thời lượng/trạng thái lưu Builder và điều khiển tệp/import/export/kết quả Transfer. Chuyển ngôn ngữ khi đang có bản nháp metadata, workspace Builder đã chọn, request autosave đang chờ và tệp/phiên bản Transfer đã chọn: giá trị, key, lời gọi đang xử lý và định danh tệp giữ nguyên. Tên/email/tiêu đề đề/mô tả/tên asset/chẩn đoán validation từ server giữ nguyên. Nội dung hướng dẫn và mẫu do tác giả soạn trong một editor chuyên biệt đại diện giữ nguyên; Cancel dùng chung có thể dịch. Không khẳng định mọi chuỗi trong editor lồng đều đã dịch.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/admin-dashboard.test.tsx tests/admin-user-list.test.tsx tests/admin-user-detail.test.tsx tests/test-library-list.test.tsx tests/version-actions.test.tsx tests/builder-workspace-navigation.test.tsx tests/builder-workspace-page.test.tsx tests/builder-autosave.test.tsx tests/module-duration-editor.test.tsx tests/transfer-portal.test.tsx tests/workspace-localization.test.tsx tests/translations.test.ts`

Kỳ vọng: FAIL với chuỗi tiếng Anh thuộc phạm vi đợt đầu, trong khi assertion mốc editor chuyên biệt vẫn PASS.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Dùng AdminContent cho thuộc tính gốc dashboard/chi tiết nhất quán và nhãn pha trộn hệ thống/người dùng. Giữ layout server Admin/Transfer, validation search/offset, fetch/redirect/notFound và key danh sách người dùng. Tiêu đề server Builder/Transfer dùng UiText; client hiện có dùng t ở vị trí văn bản. Chỉ sửa trình bày trạng thái lưu trong BuilderLifecycle; giữ queue/ref/dependency callback/chuyển trạng thái. Dịch nhãn tạo/xóa mô-đun và section cấp cao trong các editor được liệt kê, không đi sâu vào hướng dẫn question-group/answer-key/completion/diagram/audio-range. Giữ chuỗi dùng khởi tạo/lưu nội dung đề, gồm tiêu đề dự phòng của ListeningSectionEditor trong fields(); dịch nhãn hiển thị không được đổi tiêu đề được tạo hay đầu vào mutation. Không đổi registry, clone/ZIP, ghi/reset âm thanh, validation hay công cụ chuyên biệt. Giữ nguyên từng byte mẫu hướng dẫn tác giả; nội dung chuyên biệt hoãn dịch có thể giữ ngôn ngữ hiện có, không đặt một ranh giới tiếng Anh chung bao quanh điều khiển đã dịch. Dùng lại cặp hành động common thay vì nhân đôi key.

- [ ] **Bước 4: Chạy test tập trung**

Chạy lệnh ở Bước 2 cùng `npx vitest run tests/builder-route.test.tsx tests/reading-builder-sync.test.tsx tests/listening-audio-ranges.test.tsx tests/writing-builder.test.tsx` làm kiểm tra bất biến có mục tiêu cho các tệp editor cấp cao đã sửa.

Kỳ vọng: PASS, giữ lưu/vòng đời/lựa chọn và chức năng khoảng âm thanh nguyên vẹn.

- [ ] **Bước 5: Commit**

```bash
git --literal-pathspecs add -- frontend/src/features/auth/admin-content.tsx frontend/src/app/admin/page.tsx 'frontend/src/app/admin/users/[userId]/page.tsx' frontend/src/app/admin/tests/page.tsx frontend/src/app/admin/tests/new/page.tsx 'frontend/src/app/admin/tests/[testId]/page.tsx' 'frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx' frontend/src/app/transfer/page.tsx frontend/src/features/auth/admin-guard.tsx frontend/src/features/auth/admin-user-list.tsx frontend/src/features/auth/admin-user-actions.tsx frontend/src/features/test-builder/test-library-list.tsx frontend/src/features/test-builder/new-test-form.tsx frontend/src/features/test-builder/test-details-heading.tsx frontend/src/features/test-builder/version-actions.tsx frontend/src/features/test-builder/builder-workspace-navigation.tsx frontend/src/features/test-builder/builder-lifecycle.tsx frontend/src/features/test-builder/autosave-link.tsx frontend/src/features/test-builder/reading-builder.tsx frontend/src/features/test-builder/listening-builder.tsx frontend/src/features/test-builder/writing-builder.tsx frontend/src/features/test-builder/module-duration-editor.tsx frontend/src/features/test-builder/listening-section-editor.tsx frontend/src/features/transfer/transfer-portal.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/admin-dashboard.test.tsx frontend/tests/admin-user-list.test.tsx frontend/tests/admin-user-detail.test.tsx frontend/tests/test-library-list.test.tsx frontend/tests/version-actions.test.tsx frontend/tests/builder-workspace-navigation.test.tsx frontend/tests/builder-workspace-page.test.tsx frontend/tests/builder-autosave.test.tsx frontend/tests/module-duration-editor.test.tsx frontend/tests/transfer-portal.test.tsx frontend/tests/workspace-localization.test.tsx frontend/tests/translations.test.ts
git commit -m "Localize Admin Builder and Transfer workspace chrome"
```

### Nhiệm vụ 11: Dịch điều khiển tĩnh của bài thi và runner

**Tệp:**
- Sửa: `frontend/src/features/reading/reading-runner.tsx`, `reading-review.tsx`; `frontend/src/features/listening/listening-runner.tsx`, `listening-review.tsx`, `audio-player.tsx`; `frontend/src/features/writing/writing-runner.tsx`, `writing-review.tsx`; `frontend/src/features/exam/pause-attempt-control.tsx`, `paused-attempt-gate.tsx`, `draft-recovery-notices.tsx`, `test-session-transition.tsx`, `terminal-attempt-redirect.tsx`, `use-exam-submit.ts`; `frontend/src/features/test-builder/draft-preview.tsx`; `frontend/src/lib/i18n/en.ts`, `vi.ts`.
- Sửa (chỉ điều khiển tĩnh dùng chung): `frontend/src/features/highlighting/selectable-text.tsx`; `frontend/src/features/questions/renderers.tsx`, `note-completion-renderer.tsx`, `table-completion-renderer.tsx`, `diagram-labelling-renderer.tsx`.
- Test (tạo): `frontend/tests/runner-localization.test.tsx`; sửa `frontend/tests/reading-navigation.test.tsx`, `listening-navigation.test.tsx`, `listening-player.test.tsx`, `writing-runner.test.tsx`, `writing-review.test.tsx`, `focused-reading-review.test.tsx`, `focused-listening-review.test.tsx`, `pause-attempt-control.test.tsx`, `test-session-transition.test.tsx`, `draft-preview.test.tsx`, `translations.test.ts`.
- Test (sửa ca điều khiển dùng chung): `frontend/tests/selectable-text.test.tsx`, `question-registry.test.tsx`, `note-completion.test.tsx`, `table-completion.test.tsx`, `diagram-labelling.test.tsx`.

**Giao diện:**
- Đầu vào: Provider/bộ hỗ trợ test ổn định, t/UiText, key common, helper hiển thị nhận hàm dịch tùy chọn.
- Đầu ra: Đầy đủ key chung `runner.*` / `audio.*`; prop runner hiện có, src/clip/policy/ref/onDuration của ListeningAudioPlayer và cấu trúc trả về công khai của useExamSubmit không đổi.

- [ ] **Bước 1: Viết test thất bại**

Thêm test theo bảng `locale switch preserves active attempt state` cho cả ba runner thực, chép hàm tạo payload giả lập tối thiểu từ test hiện có vào runner-localization.test.tsx rồi giả lập HTTP/media; không import tệp test như mô-đun fixture. Chuyển EN → VI → EN qua bộ hỗ trợ provider bên ngoài shell attempt; không thêm bộ chọn locale trong runner. Kiểm tra các vị trí Pause/Resume/Continue/Submit/Review/Exit-or-Leave/Back, Time remaining/Time elapsed, Question(s), Passage/Section/Task sinh tự động, văn bản lưu/trạng thái/lỗi/dialog và tên player cho công nghệ hỗ trợ được cập nhật ở nơi vốn có. Nhãn VI đại diện: `Tạm dừng`, `Tiếp tục`, `Nộp bài`, `Thời gian còn lại`, `Thời gian đã dùng`, `Câu hỏi 2`, `Phần 2`. Nhãn không tạo thêm điều khiển chưa có.

Trước khi chuyển, nhập đáp án/bài Writing, chọn đơn vị, đặt cờ/highlight và tăng thời gian giả lập. So sánh định danh node runner/input/audio, response/revision bản nháp được giữ, đơn vị đã chọn, bộ đếm dựa trên timestamp và highlight/cờ sau khi chuyển. Theo dõi việc tạo lifecycle/store bằng spy, không chỉ bộ đếm wrapper; tác vụ lưu đã xếp hàng và lời gọi điều hướng/hoạt động ban đầu giữ số lần/payload, chuyển ngôn ngữ không phát request hay hành động router. Giữ currentTime/rate/volume/mute và số lần gọi play/pause/load bằng media giả lập; không phát âm thanh thật. Lặp lại với khôi phục provider sau mount, autosave đang chờ và dialog dùng chung đang mở. Không để bộ đếm giả tạo request định kỳ không liên quan trong khoảng kiểm tra.

Ghi lại tiêu đề/khối passage/nội dung section Listening/đề/options/hướng dẫn admin/đề Writing/bài viết/đáp án/giải thích do tác giả soạn trước/sau, so sánh chính xác chuỗi/fixture đã serialize cùng văn bản hiển thị; `Section 2` do tác giả nhập giữ tiếng Anh, còn nhãn sinh tự động được dịch. Mở rộng fixture Listening của runner/review cho clip+audio, audio không có clip và không có audio: hành vi clip/policy/source không đổi, thông báo dự phòng trung tính được dịch, câu hỏi vẫn hiện. Giữ đầy đủ allowSeeking/allowSpeed của bài độc lập và hạn chế Full Mock. Bao phủ màn hình tạm dừng, điều khiển sinh tự động ở review/preview, điểm thô/tối đa/độ chính xác/không Band của focused và số lần polling/advance ở chuyển tiếp Full Mock. Test AppShell riêng chứng minh không có khung toàn cục trên attempt full/focused/paused.

Trong test điều khiển dùng chung hiện có, chuyển locale khi popover highlight mở: nhãn hành động/dialog/lỗi và tên Question chung cho công nghệ hỗ trợ/placeholder selector trống cập nhật, nhưng văn bản được chọn, offset, ID highlight, node/focus popover và giá trị đáp án giữ nguyên chính xác. Lựa chọn IELTS như TRUE/FALSE/NOT GIVEN, nội dung option, chú thích sơ đồ, mẫu hướng dẫn và nội dung bảng/ghi chú tác giả không đổi. Các assertion này bao phủ cùng ranh giới hệ thống tĩnh bên trong renderer tái sử dụng, không phải dịch editor Builder chuyên biệt.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/runner-localization.test.tsx tests/reading-navigation.test.tsx tests/listening-navigation.test.tsx tests/listening-player.test.tsx tests/writing-runner.test.tsx tests/writing-review.test.tsx tests/focused-reading-review.test.tsx tests/focused-listening-review.test.tsx tests/pause-attempt-control.test.tsx tests/test-session-transition.test.tsx tests/draft-preview.test.tsx tests/translations.test.ts tests/selectable-text.test.tsx tests/question-registry.test.tsx tests/note-completion.test.tsx tests/table-completion.test.tsx tests/diagram-labelling.test.tsx`

Kỳ vọng: FAIL với UI runner/player chưa dịch; các assertion vòng đời/chấm điểm/phát âm thanh hiện tại vẫn hợp lệ.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Chỉ nối t vào các vị trí văn bản tĩnh/nhãn hỗ trợ truy cập hiện có. Giữ phân cấp/class JSX, token/bố cục bài thi, render nội dung tác giả, tên/ID input, key UUID, hook vòng đời, phép tính bộ đếm, store autosave, handler cờ/highlight và prop attempt/player. Truyền t cho helper hiển thị; phân biệt nhãn sinh tự động với tiêu đề tác giả bằng dữ liệu kind/order hiện có. Chỉ dịch nhánh dự phòng tĩnh do ứng dụng quản lý; thông báo/cảnh báo server bất kỳ và hướng dẫn tác giả giữ nguyên. Trong renderer dùng chung được liệt kê, chỉ dịch tên Question chung/placeholder selector trống; không dịch nội dung question-registry, giá trị đáp án/lựa chọn IELTS, chú thích tác giả hay đổi answer primitive. SelectableText chỉ dịch nhãn ứng dụng hiện có và nhánh lỗi cục bộ; giữ nguyên offset ngữ nghĩa và vòng đời portal/event.

Với lỗi tĩnh hiện lưu dưới dạng chuỗi tiếng Anh, lưu key thông báo của nhánh hiện có thay cho kết quả dịch; phân giải lúc render. Trong useExamSubmit, giữ kiểu công khai string|null của submitError nhưng lưu nội bộ hai key dự phòng do ứng dụng quản lý rồi phân giải bằng t hiện tại bên ngoài callback submit. Không thêm t/locale vào dependency mutation/effect, cách suy ra timer/store/source hay effect reset audio. Effect reset của player vẫn chỉ phụ thuộc src và start/end/duration/clip-error/preview-request; dịch nhãn không đổi các giá trị này hay định danh node audio. Giữ ngữ nghĩa dự phòng audio focused và dùng thông báo trung tính. Nhãn điểm/độ chính xác trong review có thể dịch, nhưng phép tính raw/max/band/null và giải thích tác giả không đổi. Không đưa header/footer toàn cục hay widget tùy chọn mới vào `/attempt/*`.

- [ ] **Bước 4: Chạy test tập trung**

Chạy lệnh ở Bước 2 cùng `npx vitest run tests/app-shell.test.tsx tests/attempt-page.test.tsx tests/reading-instructions.test.tsx tests/writing-routing.test.tsx tests/draft-answer-autosave.test.tsx tests/revision-autosave.test.ts tests/exam-draft-recovery.test.ts tests/timer.test.ts tests/exam-theme-css.test.ts`.

Kỳ vọng: PASS cho điều khiển EN/VI, dữ liệu tác giả tương đương từng byte/hiển thị, state/request/audio ổn định và hành vi bài thi hiện tại. Không yêu cầu trình duyệt/E2E.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/src/features/reading/reading-runner.tsx frontend/src/features/reading/reading-review.tsx frontend/src/features/listening/listening-runner.tsx frontend/src/features/listening/listening-review.tsx frontend/src/features/listening/audio-player.tsx frontend/src/features/writing/writing-runner.tsx frontend/src/features/writing/writing-review.tsx frontend/src/features/exam/pause-attempt-control.tsx frontend/src/features/exam/paused-attempt-gate.tsx frontend/src/features/exam/draft-recovery-notices.tsx frontend/src/features/exam/test-session-transition.tsx frontend/src/features/exam/terminal-attempt-redirect.tsx frontend/src/features/exam/use-exam-submit.ts frontend/src/features/test-builder/draft-preview.tsx frontend/src/lib/i18n/en.ts frontend/src/lib/i18n/vi.ts frontend/tests/runner-localization.test.tsx frontend/tests/reading-navigation.test.tsx frontend/tests/listening-navigation.test.tsx frontend/tests/listening-player.test.tsx frontend/tests/writing-runner.test.tsx frontend/tests/writing-review.test.tsx frontend/tests/focused-reading-review.test.tsx frontend/tests/focused-listening-review.test.tsx frontend/tests/pause-attempt-control.test.tsx frontend/tests/test-session-transition.test.tsx frontend/tests/draft-preview.test.tsx frontend/tests/translations.test.ts
git add -- frontend/src/features/highlighting/selectable-text.tsx frontend/src/features/questions/renderers.tsx frontend/src/features/questions/note-completion-renderer.tsx frontend/src/features/questions/table-completion-renderer.tsx frontend/src/features/questions/diagram-labelling-renderer.tsx frontend/tests/selectable-text.test.tsx frontend/tests/question-registry.test.tsx frontend/tests/note-completion.test.tsx frontend/tests/table-completion.test.tsx frontend/tests/diagram-labelling.test.tsx
git commit -m "Localize static runner controls without resetting attempts"
```

### Nhiệm vụ 12: Hợp nhất hợp đồng thị giác và hồi quy

**Tệp:**
- Sửa: `frontend/src/app/globals.css` chỉ khi test hợp đồng tập trung mới chứng minh còn thiếu.
- Test: `frontend/tests/visual-system-css.test.ts`, `dark-theme-css.test.ts`, `exam-theme-css.test.ts`, `shell-layout-css.test.ts`, `app-shell.test.tsx`.

**Giao diện:**
- Đầu vào: Markup shell cuối cùng, token giấy/graphite chính xác và mốc bài thi cố định.
- Đầu ra: Hợp đồng CSS hợp nhất, dễ đọc, không có snapshot khổng lồ hay kiến trúc thị giác mới.

- [ ] **Bước 1: Viết test thất bại**

Thêm `final workspace hover focus and reduced-motion contracts` cho mọi biến thể nút và bề mặt card/trường thực sự thay đổi, gồm tương phản badge/trạng thái phối màu, hành động nhỏ 44px, không glow màu/gradient không khí/blur, dấu nav/focus/thứ tự Tab thông thường và không trùng nav. Thêm hợp đồng mã nguồn tường minh rằng chữ/selector workspace không thể ghi đè số đo cố định của phần tử con bài thi và giá trị preview nhúng. Giữ assertion hiện có về gap completion, khoảng trắng hướng dẫn, cuộn dải câu hỏi, padding history, Writing/review responsive và độ đúng của highlight. Đổi tên mô tả test thiên hà/sidebar cũ và chỉ bỏ kỳ vọng lỗi thời khi hợp đồng thay thế đã chứng minh yêu cầu mới.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts tests/app-shell.test.tsx`

Kỳ vọng: FAIL khi lộ quy tắc cascade/hover/focus còn thiếu. Nếu các nhiệm vụ trước đã hoàn tất và đáp ứng assertion mới, ghi PASS rồi giữ test hồi quy; không cố tạo thất bại hay sửa CSS không cần thiết.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Chỉ sửa thiếu sót cascade/selector có bằng chứng trong globals.css để khớp giá trị đã duyệt. Giữ helper phân tích test/tính tương phản cục bộ trong tệp hiện tại trừ khi lặp mã hiện có trực tiếp ngăn assertion chính xác; không thêm framework CSS/phụ thuộc công cụ hay dọn dẹp diện rộng. Đối chiếu rằng assertion lỗi thời đã được thay trong nhiệm vụ sở hữu và mọi test bài thi/phản hồi/giảm chuyển động còn hữu ích đều được giữ. Hợp nhất test thuần không cần sửa production khi test đã xanh.

- [ ] **Bước 4: Chạy test tập trung**

Chạy lệnh ở Bước 2 cùng `npx vitest run tests/app-logo.test.tsx tests/interactive-planet.test.tsx tests/draft-preview.test.tsx tests/reading-navigation.test.tsx tests/listening-navigation.test.tsx tests/writing-runner.test.tsx`.

Kỳ vọng: PASS; ghi bằng chứng CSS/DOM mà không khẳng định đã kiểm tra pixel trong trình duyệt.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/tests/visual-system-css.test.ts frontend/tests/dark-theme-css.test.ts frontend/tests/exam-theme-css.test.ts frontend/tests/shell-layout-css.test.ts frontend/tests/app-shell.test.tsx
git commit -m "Consolidate shell theme and exam regression contracts"
```

Nếu cần sửa CSS theo bằng chứng, thêm tường minh `frontend/src/app/globals.css` trước commit này.

### Nhiệm vụ 13: Kiểm chứng cuối cùng giữa các tính năng

**Tệp:**
- Test (tạo): `frontend/tests/localization-matrix.test.tsx`.
- Sửa: Mặc định không sửa tệp production; ca kiểm tra ma trận thất bại phải được sửa trong tệp/nhiệm vụ sở hữu đã nêu, không mở rộng phạm vi.

**Giao diện:**
- Đầu vào: AppShell, LocaleProvider, view tính năng và bộ hỗ trợ test thực; chỉ giả lập ranh giới auth/API/media hiện có.
- Đầu ra: Ma trận tập trung giữa các tính năng và bằng chứng kiểm chứng được ghi lại.

- [ ] **Bước 1: Viết test thất bại**

Thêm `role locale theme route matrix preserves chrome and feature identity` với dòng bảng đại diện thay vì mọi tổ hợp tích Descartes trùng lặp. Bao gồm guest/en/light/auth, USER/vi/dark/Practice, USER/en/dark/History và review, ADMIN/vi/light/Builder edit/Transfer, ADMIN/vi/dark/preview chính xác, và en→vi trong fixture Reading/Listening/Writing full/focused cùng chuyển tiếp Full Mock. Kiểm tra liên kết/loại trừ theo role đúng kỳ vọng, định danh phần tử con giữ nguyên, state Practice/History/Builder đã chọn, focus dialog logout/request duy nhất và lưu tùy chọn độc lập qua chuyển tuyến/logout. Refresh/mount với VI/dark đã lưu, storage không hợp lệ/ném lỗi và năm từ server để bao phủ hydration không cần trình duyệt. Dùng lại fixture tính năng trong tệp test hiện có khi import sẽ làm các lần chạy test phụ thuộc nhau; ma trận nên ngắn và bổ sung assertion ghép tính năng thay vì lặp mọi test renderer.

- [ ] **Bước 2: Chạy test để xác nhận thất bại**

Chạy: `npx vitest run tests/localization-matrix.test.tsx`

Kỳ vọng: Chỉ FAIL nếu ma trận tích hợp mới phát hiện thiếu bảo đảm khi ghép thành phần. Các nhiệm vụ trước lẽ ra đã đáp ứng; PASS ngay là kết quả kiểm chứng cuối hợp lệ, không được dẫn tới thay đổi hành vi bịa ra.

- [ ] **Bước 3: Triển khai thay đổi tối thiểu**

Giải quyết lỗi tích hợp có bằng chứng trong tệp sở hữu cùng test hồi quy tương ứng, rồi chạy lại kiểm tra tập trung của nhiệm vụ đó. Nếu không có lỗi thì không sửa sản phẩm. Rà soát diff tệp đã đổi: chỉ frontend, có điều khiển runner tĩnh, hướng dẫn Builder chuyên biệt vẫn hoãn, không gồm dữ liệu tác giả, loại trừ preview/attempt chính xác, ID/key/dependency effect ổn định, tương thích bài thi tường minh, không thêm phụ thuộc/tệp sinh tự động/bí mật hay đổi payload nghiệp vụ. Xác nhận mỗi bề mặt thuộc đặc tả đều có cả key từ điển và nơi gọi; chỉ đối chiếu key không chứng minh bao phủ chuỗi.

- [ ] **Bước 4: Chạy test tập trung**

Chạy các nhóm lệnh tường minh này từ `frontend/`, giữ cấu hình Vitest và mock hiện có:

```bash
npx vitest run tests/translations.test.ts tests/locale-provider.test.tsx tests/root-layout.test.tsx tests/theme-toggle.test.tsx tests/common-localization.test.tsx tests/app-shell.test.tsx tests/app-footer.test.tsx tests/auth.test.tsx tests/auth-session-restore.test.tsx tests/localization-matrix.test.tsx
npx vitest run tests/workspace-localization.test.tsx tests/home-user-metric.test.tsx tests/practice-library.test.tsx tests/skill-practice.test.tsx tests/attempt-history-list.test.tsx tests/analytics-dashboard.test.tsx tests/profile.test.tsx tests/admin-dashboard.test.tsx tests/admin-user-list.test.tsx tests/admin-user-detail.test.tsx tests/test-library-list.test.tsx tests/version-actions.test.tsx tests/builder-workspace-navigation.test.tsx tests/builder-workspace-page.test.tsx tests/builder-autosave.test.tsx tests/module-duration-editor.test.tsx tests/transfer-portal.test.tsx
npx vitest run tests/runner-localization.test.tsx tests/reading-navigation.test.tsx tests/reading-instructions.test.tsx tests/listening-navigation.test.tsx tests/listening-player.test.tsx tests/writing-runner.test.tsx tests/writing-review.test.tsx tests/focused-reading-review.test.tsx tests/focused-listening-review.test.tsx tests/pause-attempt-control.test.tsx tests/test-session-transition.test.tsx tests/draft-preview.test.tsx tests/attempt-page.test.tsx tests/writing-routing.test.tsx tests/draft-answer-autosave.test.tsx tests/revision-autosave.test.ts tests/exam-draft-recovery.test.ts tests/timer.test.ts
npx vitest run tests/visual-system-css.test.ts tests/dark-theme-css.test.ts tests/exam-theme-css.test.ts tests/shell-layout-css.test.ts tests/status-badge.test.tsx tests/app-logo.test.tsx tests/interactive-planet.test.tsx tests/builder-route.test.tsx tests/reading-builder-sync.test.tsx tests/listening-audio-ranges.test.tsx tests/writing-builder.test.tsx tests/selectable-text.test.tsx tests/question-registry.test.tsx tests/note-completion.test.tsx tests/table-completion.test.tsx tests/diagram-labelling.test.tsx
npm run typecheck
```

Để lint có mục tiêu, từ root repository dùng PowerShell thu thập riêng tệp TS/TSX đã đổi trong đợt này, rồi chạy ESLint đã cài trong frontend:

```powershell
$rolloutFiles = @(git diff --name-only 74f89315256610d35b7a061e751dcb687c07c019 -- frontend)
$rolloutLintPaths = @($rolloutFiles | Where-Object { $_ -match '\.tsx?$' } | ForEach-Object { $_ -replace '^frontend/', '' })
$rolloutLintPaths = @(@($rolloutLintPaths) + 'tests/localization-matrix.test.tsx' | Sort-Object -Unique)
Push-Location frontend
try { npx eslint -- $rolloutLintPaths } finally { Pop-Location }
git diff --check 74f89315256610d35b7a061e751dcb687c07c019
git diff --check
```

Đường dẫn lint ma trận tường minh bao phủ tệp này khi chưa được Git theo dõi. Nếu không có thay đổi chưa stage khác, vẫn xem diff của đợt triển khai so với mốc trên. Kỳ vọng: mọi test được liệt kê PASS, typecheck/ESLint thoát 0 và diff không có lỗi khoảng trắng. Không mở rộng sang toàn bộ bộ test, trình duyệt/E2E hay dịch vụ. Ghi số lượng/lệnh thực tế, không giả định kết quả.

- [ ] **Bước 5: Commit**

```bash
git add -- frontend/tests/localization-matrix.test.tsx
git commit -m "Verify locale theme and shell integration"
```

Bao gồm mọi bản sửa tích hợp cần thiết đã được rà soát và test hồi quy với đường dẫn tường minh. Bản kế hoạch này không tự cấp phép triển khai hay xuất bản sản phẩm; làm theo chỉ dẫn Git của phiên triển khai sau khi kiểm chứng.

## Bao phủ đặc tả và điều kiện rà soát

| Phạm vi đặc tả đã duyệt | Nhiệm vụ sở hữu |
| --- | --- |
| Mục tiêu, ngoài phạm vi, ràng buộc hiện có và danh mục tuyến | Ràng buộc chung; Nhiệm vụ 3–5, 9–11 |
| Shell ngang/thành phần/điều hướng/hành vi xác thực | Nhiệm vụ 2–5, 8 |
| Chiều rộng nội dung, khoảng cách và bố cục responsive | Nhiệm vụ 5, 7, 12 |
| Footer dùng chung và loại trừ tuyến | Nhiệm vụ 4; ma trận ở Nhiệm vụ 13 |
| Bảng màu giấy/graphite chính xác, độ nổi và dọn trang trí | Nhiệm vụ 6–7, 12 |
| Chữ, nút, trường, tiêu đề và trạng thái ngữ nghĩa | Nhiệm vụ 6–7, 12 |
| Từ điển có kiểu, điều khiển locale và ranh giới server/client | Nhiệm vụ 1–2, 8–10 |
| Bảng dịch và hoãn Builder chuyên biệt | Nhiệm vụ 8–11; Ràng buộc chung |
| Bổ sung dịch điều khiển chung/tĩnh của runner và loại trừ nội dung tác giả | Nhiệm vụ 11; hồi quy state/nội dung ở Nhiệm vụ 9–10, 13 |
| Cô lập tuyến bài thi và giá trị kế thừa/bài thi cố định | Nhiệm vụ 3–6, 11–13 |
| Hỗ trợ truy cập, focus, tương phản, ngôn ngữ và giảm chuyển động | Nhiệm vụ 1, 3–8, 11–13 |
| Hydration/tùy chọn/năm/giữ state | Nhiệm vụ 1–2, 4, 8–11, 13 |
| Chiến lược test, rủi ro và năm nhóm state rủi ro cao | Trọng tâm rà soát và từng test sở hữu; Nhiệm vụ 12–13 |
| Tiêu chí nghiệm thu và ranh giới chỉ triển khai frontend | Mọi kiểm tra nhiệm vụ cùng rà soát diff Nhiệm vụ 13 |

Rà soát cuối đối chiếu chữ ký với Giao diện dùng chung đã chốt, cả tính tương ứng key từ điển lẫn bao phủ nơi gọi trong phạm vi; không chuyển đổi chuỗi tác giả, không hoãn dịch runner hàng loạt, không thiết kế lại runner, không khởi tạo lại/thêm dependency request do locale, không mở rộng editor chuyên biệt, loại trừ tuyến chính xác và giữ hình thức bài thi. Nhiệm vụ kiểm chứng có thể đã xanh; ghi bằng chứng thay vì thêm thay đổi không cần thiết. Tài liệu này chỉ là kế hoạch triển khai; chuẩn bị tài liệu không bắt đầu bất kỳ nhiệm vụ nào ở trên.
