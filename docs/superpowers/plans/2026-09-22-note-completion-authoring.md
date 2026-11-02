# Kế hoạch triển khai trình soạn Note Completion

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: kế hoạch triển khai trình soạn Note Completion. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../backend/app/services/auth.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/identity.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **Dành cho tác nhân triển khai:** bắt buộc dùng skill superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans để thực hiện từng công việc. Theo dõi tiến độ bằng checkbox (`- [ ]`).

**Mục tiêu:** xây dựng quy trình soạn Note Completion inline có ngữ nghĩa rõ ràng, giữ ổn định các đoạn văn bản/gap xen kẽ và render đúng ở giao diện làm bài.

**Kiến trúc:** thêm kiểu layout Note, helpers kiểm tính toàn vẹn/thứ tự, editor và renderer chuyên biệt; giữ structured editor cũ cho các completion families khác. Chuẩn hóa NOTE nodes cũ trong FastAPI trước khi Pydantic kiểm tra; xác nhận chính xác định danh question/GAP ở cả đường lưu draft và publish.

**Công nghệ:** Next.js/React/TypeScript, Vitest/Testing Library, FastAPI/Pydantic, pytest.

**Đặc tả:** `docs/superpowers/specs/2026-09-22-note-completion-authoring-design.md`

## Ràng buộc chung

- Không triển khai Speaking, xác thực, chấm AI hoặc thiết kế lại question type không liên quan.
- Không thêm dependency rich-text hoặc persist token soạn thảo `{{gap}}`.
- Giữ answer keys ngoài layout JSON và payload làm bài.
- Giữ UUID ổn định và cách đánh số Reading/Listening toàn cục.
- Giữ hành vi Form, Flow-chart, Summary, Sentence, Text, Table và Diagram.

## Trọng tâm review

- Dán `{{gap}}{{gap}}` hoặc token ở đầu/cuối đoạn phải giữ phần văn bản rỗng tại biên và tạo hai câu hỏi liên kết riêng.
- Kéo trong cùng block hoặc qua block khác phải di chuyển đúng một GAP object hiện có, không mất văn bản xung quanh.
- Block soạn thảo rỗng có thể tồn tại cục bộ nhưng không được autosave hoặc vượt qua validation lưu trữ của backend.
- Chuẩn hóa dữ liệu cũ phải cho kết quả xác định qua các lần tải và không gộp các node cũ liền nhau.
- Xóa block chứa nhiều gaps phải xóa đúng các câu hỏi đó và đánh số lại phần còn lại từ số bắt đầu được cung cấp.

---

### Công việc 1: Model Note backend và chuẩn hóa dữ liệu cũ

**Tệp:**
- Sửa: `backend/tests/test_question_registry.py`
- Sửa: `backend/app/domains/questions/registry.py`
- Sửa: `backend/app/domains/questions/normalization.py`
- Sửa: `backend/app/services/reading.py`
- Sửa: `backend/app/services/tests.py`

**Giao diện:**
- Đầu vào: `StructuredCompletionGroupConfig`, `_stable_uuid`, `QuestionGroupWrite` và TEXT evaluator hiện có.
- Đầu ra: validation Pydantic `NoteSegment`/`NoteBlock` và `_normalize_note_layout(config, group_id)` trả về `layout.blocks` chuẩn.

- [ ] **Bước 1: Viết backend tests đang fail** cho tiêu đề tùy chọn, block TEXT+GAP+TEXT, kiểm indent/style/UUID, tham chiếu lặp/không tồn tại/mồ côi và chuẩn hóa node cũ có tính xác định, không gộp node.
- [ ] **Bước 2: Xác nhận RED** bằng `.\.venv\Scripts\python.exe -m pytest tests/test_question_registry.py -q`; lỗi phải cho thấy NOTE blocks chưa được mô hình hóa hoặc chuẩn hóa.
- [ ] **Bước 3: Triển khai model và chuẩn hóa backend tối thiểu** với validation phân biệt TEXT/GAP, block duy nhất, indent `0..3`, title `<=300`, persisted blocks không rỗng, chuyển dữ liệu cũ bằng UUIDv5 ổn định và kiểm tham chiếu riêng cho NOTE trong service draft/publish.
- [ ] **Bước 4: Xác nhận GREEN** bằng `.\.venv\Scripts\python.exe -m pytest tests/test_question_registry.py tests/test_completion_identity.py tests/test_listening.py tests/test_reading_publish_regression.py tests/test_transfer.py -q`.

### Công việc 2: Kiểu Note frontend, registry, tính toàn vẹn và renderer

**Tệp:**
- Tạo: `frontend/src/features/questions/note-completion.ts`
- Tạo: `frontend/src/features/questions/note-completion-renderer.tsx`
- Tạo: `frontend/tests/note-completion.test.tsx`
- Sửa: `frontend/src/features/questions/types.ts`
- Sửa: `frontend/src/features/questions/registry.tsx`
- Sửa: `frontend/src/features/test-builder/question-group-editor.tsx`

**Giao diện:**
- Đầu vào: `layout.blocks` chuẩn từ backend, `questionTarget`, `SelectableText` và số câu bắt đầu của Builder.
- Đầu ra: `NoteCompletionLayout`, `noteCompletionIntegrityErrors(group)`, `normalizeNoteCompletionOrder(group, layout, base)` và `NoteCompletionRenderer`.

- [ ] **Bước 1: Viết frontend tests đang fail** cho mặc định không có câu hỏi, tiêu đề tùy chọn, render Preview/Candidate/Review, heading/bullet/indent, ô trả lời inline, UUID `onAnswer` đúng, thứ tự chuẩn, validation toàn vẹn chính xác và ẩn thao tác Add question chung.
- [ ] **Bước 2: Xác nhận RED** bằng `npm test -- tests/note-completion.test.tsx`; lỗi phải do thiếu triển khai Note chuyên biệt.
- [ ] **Bước 3: Triển khai tối thiểu các kiểu, pure helpers, định nghĩa registry, routing QuestionGroupEditor và renderer riêng**. Giữ các structured completion khác trong registry loop hiện có.
- [ ] **Bước 4: Xác nhận GREEN** bằng `npm test -- tests/note-completion.test.tsx tests/question-registry.test.tsx tests/table-completion.test.tsx`.

### Công việc 3: Canvas soạn Note inline

**Tệp:**
- Tạo: `frontend/src/features/questions/note-completion-editor.tsx`
- Sửa: `frontend/tests/note-completion.test.tsx`
- Sửa: `frontend/src/features/questions/registry.tsx`
- Sửa: `frontend/src/app/globals.css`

**Giao diện:**
- Đầu vào: `NoteCompletionLayout`, `normalizeNoteCompletionOrder`, `noteCompletionIntegrityErrors`, `EditorProps` và `ConfirmDialog`.
- Đầu ra: `NoteCompletionEditor` chuyển TEXT segment cục bộ, chèn tại caret, di chuyển GAP qua block, controls cho block, inspector gap đang chọn và xác nhận thao tác xóa.

- [ ] **Bước 1: Thêm interaction tests đang fail** cho gõ một token, dán hai token, sửa văn bản quanh gap nhưng giữ IDs/keys, chèn rõ tại caret, kéo trong/qua block, đổi style, tạo block bằng Enter, xóa gap và xác nhận xóa block kèm số câu bị ảnh hưởng.
- [ ] **Bước 2: Xác nhận RED** bằng `npm test -- tests/note-completion.test.tsx`; mỗi tương tác phải fail vì thiếu hành vi quan sát được, không phải lỗi setup test.
- [ ] **Bước 3: Triển khai editor tối thiểu** bằng một span `contentEditable` do browser quản lý cho mỗi TEXT segment, tách token trong từng segment, nút GAP ổn định, toolbar có ngữ nghĩa và chỉ cập nhật Builder state có debounce qua `onChange`.
- [ ] **Bước 4: Xác nhận GREEN** bằng `npm test -- tests/note-completion.test.tsx tests/text-completion-canvas.test.tsx tests/table-completion.test.tsx`.

### Công việc 4: Kiểm chứng đầy đủ và sửa regression

**Tệp:**
- Chỉ sửa tệp liên quan đến kiểm tra fail do công việc 1–3 tạo ra.

**Giao diện:**
- Đầu vào: mọi giao diện production và test nêu trên.
- Đầu ra: typecheck/lint/backend suite sạch và ghi rõ các lỗi baseline không thay đổi.

- [ ] **Bước 1: Kiểm frontend** bằng `npm test`, `npm run typecheck` và `npm run lint`; đối chiếu timeout tiêu đề Table với baseline clean-main đã ghi.
- [ ] **Bước 2: Kiểm backend** bằng `.\.venv\Scripts\python.exe -m pytest` và `.\.venv\Scripts\python.exe -m ruff check app tests`.
- [ ] **Bước 3: Với mỗi lỗi mới tạo ra, viết hoặc giữ test tái hiện nhỏ nhất, xác nhận RED, sửa tối thiểu rồi chạy lại suite phụ trách đến GREEN.**
- [ ] **Bước 4: Kiểm `git diff --check`, phạm vi tệp thay đổi, hành vi DTO làm bài và cách ly answer keys trước review cuối.**
