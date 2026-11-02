# Kế hoạch triển khai hệ thống giao diện Fantasy Galaxy

> **Phân loại tài liệu: SUPERSEDED.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: kế hoạch triển khai hệ thống giao diện Fantasy Galaxy. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../frontend/src/components/ui/app-shell.tsx).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/shared-platform.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **Dành cho tác nhân triển khai:** bắt buộc dùng skill superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans để thực hiện từng công việc. Theo dõi bằng checkbox (`- [ ]`).

**Mục tiêu:** áp dụng hệ thống giao diện Fantasy Galaxy thống nhất cho toàn bộ frontend IELTS Studio, giữ mọi hành vi và ranh giới dữ liệu hiện có.

**Kiến trúc:** giữ cấu trúc components/routes Next.js hiện tại, đưa hệ thống giao diện vào qua semantic CSS tokens và presentation classes dùng chung, sau đó chỉ sửa markup nhỏ để tạo các điểm gắn cấu trúc rõ ràng. Giữ cơ chế `data-theme` hiện có; suy ra lớp làm bài `--exam-*` dịu hơn từ cùng theme tokens.

**Công nghệ:** Next.js 16.3.5, React 19.3, TypeScript 5.9, Tailwind CSS 4, CSS custom properties thuần, Vitest, Testing Library, Playwright.

**Đặc tả:** `docs/superpowers/specs/2026-09-20-fantasy-galaxy-visual-system-design.md`

## Ràng buộc chung

- Giữ tên sản phẩm hiển thị `IELTS Studio`; Fantasy Galaxy là hướng giao diện, không phải đổi tên.
- Chỉ sửa frontend; không đổi backend API, database model, migration, evaluator, lifecycle hoặc persistence.
- Tiếp tục dùng triển khai `data-theme="light"` và `data-theme="dark"` hiện có.
- Chỉ dùng CSS gradients, surfaces nhiều lớp và glow tiết chế; không thêm ảnh galaxy raster, particle system, WebGL, thư viện animation hoặc hiệu ứng chạy liên tục.
- Giữ toàn bộ hành vi Text Completion, highlight, autosave, timer, điều hướng, flags, Listening audio, History, publish-validation, archive và version bất biến.
- Giữ Reading/Listening làm bài dịu hơn đáng kể so với dashboard, admin và builder.
- Giữ semantic HTML, điều hướng bàn phím, ARIA labels, focus-visible, contrast có xét WCAG, reduced-motion và responsive.
- Theo yêu cầu gốc, chỉ tạo một commit tập trung ở cuối; không tạo commit trung gian.

## Trọng tâm review

- Preference `light` hoặc `dark` đã lưu vẫn phải khởi tạo không hydration mismatch; giữ theme script hiện có và kiểm bằng root-layout test.
- Điều hướng câu hỏi khi làm bài vẫn cuộn ngang, phân biệt câu hiện tại/đã trả lời/chưa trả lời/đã đánh dấu; kiểm selectors cần thiết trong exam CSS test và giữ behavior test hiện có.
- Câu completion và ô gap phải inline, không hiện giới hạn từng gap; giữ completion tests và xác nhận các compact classes vẫn có style.
- Viewport hẹp không được ẩn thao tác chính hoặc gây tràn ngang toàn trang; kiểm responsive selectors chính trong visual-system CSS test và xem screenshot kích thước mobile.
- Thao tác phá hủy phải ít nổi bật hơn nhưng vẫn thấy được khi dùng bàn phím; kiểm danger-ghost và focus-visible toàn cục trong visual-system CSS test.

---

## Bản đồ tệp

- `frontend/src/app/globals.css`: quản lý semantic tokens, shell, shared primitives, hệ thống trang, phân cấp builder, độ dịu giao diện làm bài, review, responsive và reduced-motion.
- `frontend/src/components/ui/app-shell.tsx`: cung cấp điểm gắn trang trí shell, giữ điều hướng và tên sản phẩm.
- `frontend/src/components/ui/icons.tsx`: bổ sung SVG icons inline nhẹ cho hero/lộ trình khi icons hiện có chưa đủ.
- `frontend/src/app/page.tsx`: tổ hợp dashboard hero mới, số liệu tóm tắt và lộ trình học.
- `frontend/src/app/library/page.tsx`: thêm structural classes có ngữ nghĩa và phân cấp metadata cho thẻ Reading/Listening đã publish.
- `frontend/src/app/history/page.tsx` và `frontend/src/features/history/attempt-history-list.tsx`: trình bày attempt records cùng empty state tái sử dụng, với ưu tiên thao tác rõ ràng.
- `frontend/src/app/admin/tests/page.tsx`, `frontend/src/app/admin/tests/[testId]/page.tsx` và builder components hiện có: chỉ thêm presentation hooks cần cho hệ thống admin/builder dùng chung.
- `frontend/src/features/reading/reading-runner.tsx`, `frontend/src/features/listening/listening-runner.tsx`, `frontend/src/features/test-builder/draft-preview.tsx`: thêm class hooks cho bố cục đọc và giao diện làm bài, không đổi state/event flow.
- `frontend/src/features/reading/reading-review.tsx` và `frontend/src/features/listening/listening-review.tsx`: thêm phân cấp review, giữ dữ liệu renderer.
- `frontend/tests/visual-system-css.test.ts`: bảo vệ yêu cầu semantic tokens, accessibility, responsive, giao diện làm bài và hiệu ứng tiết chế.
- Tests tập trung hiện có: bảo vệ mọi hành vi được nêu trong đặc tả.

### Công việc 1: Semantic tokens, shell và shared primitives

**Tệp:**
- Tạo: `frontend/tests/visual-system-css.test.ts`
- Sửa: `frontend/src/app/globals.css`
- Sửa: `frontend/src/components/ui/app-shell.tsx`
- Sửa: `frontend/src/app/layout.tsx`
- Kiểm thử: `frontend/tests/visual-system-css.test.ts`
- Kiểm thử: `frontend/tests/root-layout.test.tsx`
- Kiểm thử: `frontend/tests/theme-toggle.test.tsx`

**Giao diện:**
- Đầu vào: contract `document.documentElement.dataset.theme` và các tên class dùng chung hiện có.
- Đầu ra: semantic CSS variables trong đặc tả, cùng các class ổn định `.app-shell`, `.app-header`, `.app-sidebar`, `.surface-card`, `.btn-*`, `.field`, `.select-field`, `.status-*`, `.empty-state`, `.dialog-*` và focus styles cho các công việc sau.

- [ ] **Bước 1: Viết visual-system contract test đang fail**

Tạo Vitest test đọc `src/app/globals.css` và kiểm cả hai theme blocks chứa `--app-bg`, `--app-bg-elevated`, `--surface-hover`, `--surface-glass`, `--accent-violet`, `--accent-cyan`, `--glow-accent` và `--glow-violet`. Kiểm stylesheet có `:focus-visible`, `@media (prefers-reduced-motion: reduce)`, năm biến thể nút, responsive shell rules và không có background asset `url(`.

- [ ] **Bước 2: Chạy contract test, xác nhận fail do thiếu semantic variables**

Chạy: `npm test -- visual-system-css.test.ts`

Mong đợi: lỗi nêu token thiếu đầu tiên, trong khi test harness hiện có vẫn tải thành công.

- [ ] **Bước 3: Thay giá trị theme gốc bằng hệ semantic tokens gọn**

Định nghĩa giá trị sáng/tối theo đặc tả; giữ compatibility aliases như `--paper`, `--reading`, `--listening` và suy ra `--exam-*` trong cùng hai theme blocks. Theme tối dùng navy đậm thay đen; theme sáng dùng gần trắng lạnh thay xám trung tính.

- [ ] **Bước 4: Triển khai shell và shared primitives được chuẩn hóa**

Dùng hai hoặc ba radial gradients tĩnh trên shell/body cùng chi tiết pseudo-element nhỏ. Đổi style header, sidebar, navigation active, cards, buttons, fields, badges, dialogs, empty states, notices và focus rings chỉ bằng semantic tokens. Phần lớn surfaces phải đặc; chỉ shell chrome và overlays dùng trong mờ.

- [ ] **Bước 5: Thêm hook trang trí không ngữ nghĩa, giữ hành vi điều hướng**

Chỉ thêm trang trí shell/brand `aria-hidden` ở nơi pseudo-elements hiện có không diễn đạt được. Giữ `IELTS Studio`, navigation URLs, labels, active-route logic và theme toggle. Chỉ cập nhật metadata description nếu cần mô tả nền tảng học, không đổi tên.

- [ ] **Bước 6: Chạy shell và theme tests**

Chạy: `npm test -- visual-system-css.test.ts root-layout.test.tsx theme-toggle.test.tsx`

Mong đợi: mọi test đã chọn đều pass.

### Công việc 2: Home, Library và History

**Tệp:**
- Sửa: `frontend/src/app/page.tsx`
- Sửa: `frontend/src/app/library/page.tsx`
- Sửa: `frontend/src/app/history/page.tsx`
- Sửa: `frontend/src/features/history/attempt-history-list.tsx`
- Sửa: `frontend/src/components/ui/icons.tsx`
- Sửa: `frontend/src/app/globals.css`
- Kiểm thử: `frontend/tests/attempt-history-list.test.tsx`

**Giao diện:**
- Đầu vào: tokens/shared primitives công việc 1; `getTests`, `getHistory`, `getVersion`, `StartAttempt` và APIs xóa attempt hiện có.
- Đầu ra: structural hooks `.home-hero`, `.home-metrics`, `.learning-path-grid`, `.learning-path-card`, `.practice-grid`, `.practice-card`, `.history-list` và `.history-row`.

- [ ] **Bước 1: Thêm assertions trình bày vào History component test**

Mở rộng test để xác nhận hàng attempt dùng Continue hoặc Review làm thao tác chính và Delete vẫn là `btn-danger-ghost`. Danh sách rỗng phải render tiêu đề empty state dùng chung thay cho đoạn văn đơn lẻ.

- [ ] **Bước 2: Chạy History test tập trung và xác nhận assertion empty state mới fail**

Chạy: `npm test -- attempt-history-list.test.tsx`

Mong đợi: assertion empty state mới fail trước khi cập nhật markup.

- [ ] **Bước 3: Tổ hợp Home thành cổng học tập**

Giữ các lời gọi dữ liệu server. Render hero với danh tính sản phẩm hiện tại, giá trị cốt lõi ngắn gọn, CTA chính `/library` và CTA phụ `/admin/tests`. Trình bày counts thành metrics gọn rồi thêm bốn thẻ lộ trình Tests, Reading, Listening, History bằng routes hiện có và SVG icons inline.

- [ ] **Bước 4: Cải thiện phân cấp thẻ Library**

Giữ một thẻ cho mỗi module đã publish và giữ `StartAttempt`. Thêm semantic classes theo module, metadata version/module, liên kết chi tiết version nhẹ và vùng thao tác rõ. Không bịa dữ liệu tiến độ mà API không cung cấp.

- [ ] **Bước 5: Cải thiện hàng History và empty state**

Dùng `EmptyState` khi không có attempts. Nhóm metadata test/module/version/ngày, trạng thái, thời gian đã dùng và thao tác chính Continue/Review thành các phần responsive. Giữ chính xác hành vi dialog xóa và API calls.

- [ ] **Bước 6: Tạo style ba trang học từ tokens dùng chung**

Triển khai hero, metrics gọn, thẻ lộ trình, thẻ luyện theo module và hàng history responsive. Chỉ dùng gradients cục bộ; giữ thao tác phá hủy ít nổi bật.

- [ ] **Bước 7: Chạy tests tập trung cho các trang học**

Chạy: `npm test -- attempt-history-list.test.tsx root-layout.test.tsx`

Mong đợi: mọi test đã chọn đều pass.

### Công việc 3: Thư viện Admin, chi tiết đề và Builder workspace

**Tệp:**
- Sửa: `frontend/src/app/admin/tests/page.tsx`
- Sửa: `frontend/src/app/admin/tests/[testId]/page.tsx`
- Sửa: `frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx`
- Sửa: `frontend/src/features/test-builder/test-library-list.tsx`
- Sửa: `frontend/src/features/test-builder/builder-workspace-navigation.tsx`
- Sửa: `frontend/src/features/test-builder/version-actions.tsx`
- Sửa: `frontend/src/features/test-builder/reading-builder.tsx`
- Sửa: `frontend/src/features/test-builder/listening-builder.tsx`
- Sửa: `frontend/src/features/test-builder/question-group-editor.tsx`
- Sửa: `frontend/src/app/globals.css`
- Kiểm thử: `frontend/tests/test-library-list.test.tsx`
- Kiểm thử: `frontend/tests/builder-workspace-navigation.test.tsx`
- Kiểm thử: `frontend/tests/builder-workspace-page.test.tsx`
- Kiểm thử: `frontend/tests/version-actions.test.tsx`

**Giao diện:**
- Đầu vào: mọi builder API calls, lifecycle provider, registry editors, preview paths và dữ liệu publish validation hiện có.
- Đầu ra: thẻ/hàng admin rõ ràng, toolbar builder có thứ bậc, điều hướng cục bộ nhận biết module và phân cấp surfaces cha/con; không đổi callbacks/payloads.

- [ ] **Bước 1: Mở rộng component tests với presentation contracts**

Kiểm thư viện admin vẫn có tabs Active/Archived, tìm kiếm, create/continue/edit chính và thao tác phá hủy nhẹ. Builder navigation vẫn có Created/Not created và hàng active `aria-current`. VersionActions giữ Validate, Publish/Edit và Delete draft.

- [ ] **Bước 2: Chạy admin/builder tests tập trung trước sửa markup**

Chạy: `npm test -- test-library-list.test.tsx builder-workspace-navigation.test.tsx builder-workspace-page.test.tsx version-actions.test.tsx`

Mong đợi: assertions hành vi hiện có pass; assertions cấu trúc mới chỉ fail do thiếu class hoặc nhóm.

- [ ] **Bước 3: Áp dụng phân cấp admin dùng chung**

Cải thiện headings, mật độ toolbar, bộ lọc trạng thái, test cards, version rows và nhóm metadata bằng semantic classes. Giữ mọi hành vi archive, restore, clone, permanent-delete và routing.

- [ ] **Bước 4: Cải thiện builder shell và toolbar**

Phân cấp rõ Draft, validation, preview links có sẵn trong module builders, Publish/Edit và xóa. Toolbar sticky trên desktop, xếp chồng trên màn hình hẹp.

- [ ] **Bước 5: Cải thiện điều hướng module và overview**

Dùng accent cyan cho Reading, violet cho Listening ở trạng thái selected/created. Giữ Writing bị vô hiệu hóa, không triển khai. Giảm cảm giác thẻ lồng bằng spacing và mức surface thay vì viết lại markup.

- [ ] **Bước 6: Cải thiện trình bày passage, section, group và editor**

Giữ thẻ passage/listening section làm vùng cha, group summaries thành hàng gọn và editor thành vùng làm việc tập trung. Đổi style Instruction, nội dung, cấu hình đáp án, advanced fields, alternatives và sentence/gap tokens mà không đổi data flow hoặc focus handlers.

- [ ] **Bước 7: Chạy mọi builder behavior tests**

Chạy: `npm test -- builder-route.test.tsx builder-workspace-navigation.test.tsx builder-workspace-page.test.tsx draft-preview.test.tsx question-registry.test.tsx test-library-list.test.tsx text-completion-canvas.test.tsx version-actions.test.tsx`

Mong đợi: mọi tests đã chọn pass, gồm Text Completion identity, cấu trúc câu, alternatives và các ca điều hướng có sẵn.

### Công việc 4: Reading/Listening làm bài, điều hướng và Preview

**Tệp:**
- Sửa: `frontend/src/features/reading/reading-runner.tsx`
- Sửa: `frontend/src/features/listening/listening-runner.tsx`
- Sửa: `frontend/src/features/listening/audio-player.tsx`
- Sửa: `frontend/src/features/test-builder/draft-preview.tsx`
- Sửa: `frontend/src/features/questions/question-group-instruction.tsx`
- Sửa: `frontend/src/features/questions/renderers.tsx`
- Sửa: `frontend/src/app/globals.css`
- Kiểm thử: `frontend/tests/exam-theme-css.test.ts`
- Kiểm thử: `frontend/tests/reading-instructions.test.tsx`
- Kiểm thử: `frontend/tests/reading-navigation.test.tsx`
- Kiểm thử: `frontend/tests/listening-player.test.tsx`
- Kiểm thử: `frontend/tests/draft-preview.test.tsx`
- Kiểm thử: `frontend/tests/selectable-text.test.tsx`

**Giao diện:**
- Đầu vào: payload làm bài, registry renderer contracts, timer helpers, autosave callbacks, flag/highlight APIs, hành vi audio element và navigation refs hiện có.
- Đầu ra: `.exam-passage`, `.exam-passage-body`, `.exam-question-panel-heading` và style làm bài dịu suy ra từ tokens `--exam-*`.

- [ ] **Bước 1: Tăng bảo vệ Candidate CSS contracts**

Mở rộng `exam-theme-css.test.ts` để kiểm shell dùng tokens `--exam-*`; passage/question panes có surfaces đặc riêng; footer strip một hàng cuộn ngang; bốn chip states có style; instructions giữ whitespace; gaps vẫn là controls inline gọn.

- [ ] **Bước 2: Chạy Candidate tests, xác nhận assertions class mới fail**

Chạy: `npm test -- exam-theme-css.test.ts reading-instructions.test.tsx reading-navigation.test.tsx listening-player.test.tsx draft-preview.test.tsx selectable-text.test.tsx`

Mong đợi: chỉ assertions cấu trúc/CSS mới fail.

- [ ] **Bước 3: Thêm hooks cho bố cục Reading**

Thay nhóm utility chỉ phục vụ trình bày trong passage markup bằng semantic classes; giữ nguyên `SelectableText`, target IDs, split panes, cuộn độc lập, theo dõi câu active, chọn passage, điều hướng câu, flags, highlights, autosave, timer và mã submit.

- [ ] **Bước 4: Áp dụng style làm bài dịu**

Dùng Reading surfaces đặc, header/footer tiết chế, instructions nhẹ, controls dễ tiếp cận và chỉ glow khi focus. Không đặt trang trí galaxy sau passage hoặc thẻ câu hỏi.

- [ ] **Bước 5: Cải thiện Listening player và section**

Dùng player surface nổi violet/xanh, nhóm controls thực dụng. Giữ một audio element dùng chung, mọi nhãn player, seek, âm lượng, tốc độ, skip và hành vi phát.

- [ ] **Bước 6: Đồng bộ Draft Preview với render làm bài**

Dùng lại cách trình bày passage, câu hỏi, instructions, player và điều hướng; thêm chỉ báo preview nhỏ. Giữ preview không lưu như hiện có.

- [ ] **Bước 7: Chạy Candidate và regression tests**

Chạy: `npm test -- exam-theme-css.test.ts reading-instructions.test.tsx reading-navigation.test.tsx listening-player.test.tsx draft-preview.test.tsx selectable-text.test.tsx text-completion-canvas.test.tsx timer.test.ts word-boundaries.test.ts`

Mong đợi: mọi test đã chọn đều pass.

### Công việc 5: Review, dialogs, highlights, responsive và kiểm chứng đầy đủ

**Tệp:**
- Sửa: `frontend/src/features/reading/reading-review.tsx`
- Sửa: `frontend/src/features/listening/listening-review.tsx`
- Sửa: `frontend/src/components/ui/confirm-dialog.tsx` chỉ nếu cần semantic hook
- Sửa: `frontend/src/features/highlighting/selectable-text.tsx` chỉ nếu cần semantic hook
- Sửa: `frontend/src/app/globals.css`
- Sửa: `frontend/tests/visual-system-css.test.ts`
- Kiểm thử: toàn bộ `frontend/tests/**/*.test.*`

**Giao diện:**
- Đầu vào: review DTOs đã finalize, question renderers dùng chung, dialog callbacks hiện có và highlight popovers qua portal.
- Đầu ra: hàng review phục vụ học tập, overlay surfaces thống nhất và bảo đảm responsive/accessibility cuối cùng.

- [ ] **Bước 1: Thêm kỳ vọng review và responsive vào CSS contract**

Kiểm trạng thái đúng/sai dùng semantic colors/borders nhẹ; dialog/popover dùng tokens chung; mobile breakpoints bao phủ hàng học tập và Candidate chrome; giữ reduced-motion.

- [ ] **Bước 2: Chạy contract test, xác nhận assertions mới fail trước style cuối**

Chạy: `npm test -- visual-system-css.test.ts`

Mong đợi: assertions review/responsive mới fail.

- [ ] **Bước 3: Cải thiện phân cấp review Reading/Listening**

Giữ answer-key data và renderers hiện có. Trình bày rõ điểm/điều hướng section; tách Your answer, Correct answer và Explanation bằng typography, semantic borders nhẹ thay cho mảng màu bão hòa lớn.

- [ ] **Bước 4: Thống nhất dialogs, validation panels và highlight popovers**

Dùng chung raised surface, đường viền, shadow, radius và căn thao tác. Giữ portals, hydration safety, delete-all, mọi labels và callbacks hiện có.

- [ ] **Bước 5: Hoàn tất responsive và accessibility styling**

Kiểm độ rộng 1440 px, 1024 px, 768 px và 390 px. Bảo đảm shell navigation, hero, cards, history rows, builder toolbar/local navigation, passage/section cards, Candidate header/footer và dialogs dùng được mà không tràn ngang toàn trang. Kiểm contrast sáng/tối và focus thấy được qua bàn phím.

- [ ] **Bước 6: Chạy toàn bộ frontend verification suite**

Chạy từ `frontend/`:

```text
npm test
npm run lint
npm run typecheck
npm run build
```

Mong đợi: mọi lệnh trả exit code 0. Sửa regression triển khai, không xóa hoặc làm yếu tests.

- [ ] **Bước 7: Kiểm giao diện bằng browser**

Xem Home, Library, History, Admin và các màn hình Builder/Candidate/Review có thể truy cập trong cả hai theme, desktop/mobile. Dashboard cần thể hiện cá tính, giao diện làm bài vẫn dịu. Ghi màn hình bị giới hạn bởi môi trường vào phần visual debt cuối.

- [ ] **Bước 8: Kiểm repository diff và khoảng trắng**

Chạy từ thư mục gốc repository:

```text
git status --short
git diff --check
git diff --stat
git diff
```

Xác nhận chỉ đổi design spec, plan, frontend source và tests thuộc nhiệm vụ. Không đưa `.env`, `.env.local`, secret, storage binaries, backend files, migration hoặc tệp không liên quan vào.

- [ ] **Bước 9: Stage đúng tệp nhiệm vụ và kiểm staged diff**

Stage các đường dẫn thuộc nhiệm vụ một cách tường minh, rồi chạy:

```text
git diff --cached --check
git diff --cached --stat
git diff --cached
```

Mong đợi: kiểm khoảng trắng sạch và một diff tập trung vào redesign.

- [ ] **Bước 10: Commit và push**

Chạy:

```text
git commit -m "feat: introduce fantasy galaxy visual system"
git push
```

Mong đợi: một commit trên `main`, push tới `origin/main` không force. Nếu xác thực chặn push, dừng và báo chính xác nguyên nhân.
