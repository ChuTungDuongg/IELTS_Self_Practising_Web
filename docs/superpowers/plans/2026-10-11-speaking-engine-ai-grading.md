# Kế hoạch triển khai bộ máy Speaking, ghi âm, chép lời và chấm AI

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: kế hoạch triển khai bộ máy Speaking, ghi âm, chép lời và chấm AI. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../../../backend/app/services/speaking_attempts.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/speaking.md); [kiểm toán và giới hạn](../../DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong đợt kiểm toán này.
> Chỉ dẫn Speaking vẫn có tính ràng buộc theo AGENTS; không lưu trữ hoặc vô hiệu hóa các bổ sung tự rà soát.

> **Dành cho worker tác nhân:** KỸ NĂNG PHỤ BẮT BUỘC: dùng superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans để triển khai từng tác vụ. Các bước dùng ô đánh dấu (`- [ ]`) để theo dõi.

**Mục tiêu:** thêm Speaking thành kỹ năng IELTS thứ tư đầy đủ, gồm Builder Part 1/2/3, ghi âm từng câu chịu được sự cố, bản chép lời chỉ đọc theo câu, chấm AI kết hợp âm thanh/văn bản, trải nghiệm xem lại động, tích hợp Full Mock/lịch sử/lớp học và công cụ benchmark.

**Kiến trúc:** giữ Speaking trong `TestVersion -> TestModule -> Attempt` hiện có. Lưu Part/câu hỏi do người soạn dưới dạng nội dung cấu trúc có phiên bản; bản ghi người làm bài là tệp riêng tư của lượt làm bài ngoài PostgreSQL, có bản kê cơ sở dữ liệu và phân quyền. Xử lý tiếng nói qua giao diện nhà cung cấp ASR/căn chỉnh/âm học thay thế được; chấm tổng thể theo tiêu chí, dùng mẫu điểm trước đã chứng minh từ Writing (`evidence -> score-only -> persist -> feedback`).

**Công nghệ:** FastAPI, SQLAlchemy async ORM, PostgreSQL/Alembic, Pydantic, kho tài sản cục bộ, API MediaRecorder/Web Audio của trình duyệt, tiền xử lý FFmpeg, phụ thuộc faster-whisper/căn chỉnh/phân tích âm thanh tùy chọn, nhà cung cấp LLM cấu trúc hiện có, Next.js 16, React 19, TypeScript, Zod, Vitest/RTL.

**Đặc tả:** `docs/superpowers/specs/2026-10-11-speaking-engine-ai-grading-design.md`

**Nền lập kế hoạch:** `origin/main` là `d606bfaedf871bbc45326223cf4f1d74f54399e9` khi viết. Mỗi giai đoạn thực thi bắt đầu bằng `git fetch origin && git pull --ff-only origin main`; chỉnh ID migration theo đầu Alembic hiện hành thực tế thay vì giả định SHA này vẫn mới nhất.

## Ràng buộc chung

- Speaking là mô-đun đầy đủ cạnh Reading, Listening, Writing; không làm bản trình diễn tách rời.
- Dòng cũ `Do not implement Speaking.` trong `AGENTS.md` gốc đã bị đặc tả phê duyệt thay thế, phải đổi lúc bắt đầu triển khai thành bất biến Speaking có phạm vi; tài liệu kế hoạch lịch sử không liên quan vẫn giữ tính lịch sử.
- Part 1 và Part 3 dùng câu hỏi có thứ tự. Part 2 dùng thẻ gợi ý bài nói dài, có câu hỏi tiếp tùy chọn do người soạn. Lưu bằng ID ổn định + `order_index`, không dùng con trỏ danh sách liên kết.
- Mặc định ứng dụng Part 1/3 trả lời 60 giây; Part 2 chuẩn bị 60 giây, trả lời 120 giây. Đây là mặc định sản phẩm cấu hình được, không tuyên bố giới hạn từng câu IELTS chính thức cố định.
- Luyện tập chỉ cho Nghe/Thử lại câu hiện tại chưa chốt. Thi/Full Mock không cho phát lại, thử lại, về câu trước hoặc mở lại câu đã chốt.
- Thời gian/trạng thái máy chủ có thẩm quyền. Bộ đếm và hoạt ảnh trình duyệt chỉ để trình bày.
- Khôi phục sau tải lại/sự cố trả cùng câu hỏi và ảnh chụp thời gian còn lại được máy chủ xác nhận gần nhất, cấp đúng một khoảng bù kết nối/chuẩn bị 7 giây cho gián đoạn đó, rồi tiếp tục thời gian gốc. Tải lại lặp không cộng dồn bù hoặc tua ngược thời gian.
- Âm thanh gốc là dữ liệu riêng tư của lượt làm bài. Tái sử dụng lớp lưu trữ vật lý, nhưng **không** ép bản ghi vào mô hình phân quyền nội dung xuất bản `Asset` gắn với `test_version_id`.
- Ưu tiên `audio/webm;codecs=opus` nếu hỗ trợ, dự phòng theo khả năng. Frontend không được mã hóa WAV. Tiền xử lý tiếng nói có thể tạo PCM/WAV mono 16 kHz.
- Tải các đoạn MediaRecorder nhỏ (mục tiêu 2–5 giây). Sự cố cứng tạo bộ chứa/phiên MediaRecorder mới, nên một lần ghi logic gồm một hoặc nhiều phân đoạn có thứ tự, mỗi phân đoạn chứa đoạn dữ liệu có thứ tự và lặp an toàn.
- `Generate Transcript` và `Grade with AI` là thao tác riêng. Chấm có thể tái sử dụng hoặc tự tạo bản chép lời hợp lệ, nhưng không được tạo công việc ASR trùng cho cùng dấu vân tay.
- Bản chép lời chỉ đọc, chỉ theo câu. Bản sạch có thể chuẩn hóa dấu câu/chữ hoa/cách hiện từ đệm nhưng không được sửa ngữ pháp hoặc âm thầm làm tốt hơn điều người làm bài nói.
- Lỗi kỹ thuật/âm thanh là trạng thái không chấm được, không phải band IELTS thấp.
- Chỉ số lưu loát chỉ là bằng chứng. Không tạo quy tắc band cứng như `pause_count > N => Band X`.
- Phát âm cần bằng chứng từ âm thanh. LLM chỉ nhận bản chép lời không được bịa điểm Pronunciation.
- Không lấy trung bình điểm từng câu/Part. Điểm tiêu chí đánh giá tổng thể toàn lượt Speaking; phân tích từng câu chỉ để bằng chứng/nhận xét.
- Giữ triển khai Writing AI điểm trước ở `d606bfae...`; không gây hồi quy hoặc viết lại Writing để xây Speaking.
- Điểm AI tiêu chí Speaking vẫn là giá trị nửa band tư vấn (`0..9`, bước `0.5`) đã phê duyệt. Lưu `raw_mean`; dùng chính sách hiển thị `round_to_half` của dự án cho tổng tư vấn, trừ khi phiên bản/hiệu chuẩn sau đổi rõ ràng. Không tuyên bố làm tròn/độ chính xác được giám khảo chứng nhận.
- Full Mock cuối cùng thành Listening -> Reading -> Writing -> Speaking. Tổng dự án bốn kỹ năng chỉ có khi đủ band bốn mô-đun.
- Quyền sở hữu giáo viên/lớp, kiểm duyệt, nguồn gốc bài giao, phiên bản xuất bản bất biến và quyền giáo viên chỉ đọc kết quả giữ ngữ nghĩa quản trị hiện có.
- UI theo trạng thái và được trau chuốt: mức micro trực tiếp, tiến độ thời gian, chuyển nhẹ 150–250 ms, tiến độ lưu/khôi phục/chép lời/AI, hỗ trợ giao diện/màu nhấn và `prefers-reduced-motion`. Không parallax, hạt trang trí hoặc chuyển động làm chậm đổi trạng thái/mạng.
- Phụ thuộc tiếng nói nặng không được khiến kiểm thử đơn vị backend thường nạp mô hình. Đặt sau factory nhà cung cấp/nhóm phụ thuộc tùy chọn, kiểm bằng giả lập/stub/dữ liệu nhỏ.
- Xác minh tập trung, ít chi phí theo ý người dùng: không tự động hóa trình duyệt, Playwright/E2E, máy chủ dev, micro thật, tải mô hình ASR/âm học thật, LLM/GPU/Modal trực tiếp hoặc triển khai. Dùng pytest/Vitest tập trung, Ruff/ESLint có mục tiêu, kiểm kiểu TypeScript và `git diff --check`.
- Thay đổi hành vi theo TDD: viết kiểm thử tập trung thất bại, chạy xác nhận RED, triển khai tối thiểu, chạy GREEN, rồi commit. Không gộp mọi giai đoạn vào một commit.

## Cấu trúc tệp

Trách nhiệm backend mới nên tập trung, không mở rộng mãi `entities.py` và mô-đun riêng Writing:

- `backend/app/models/speaking.py` — nội dung Speaking do người soạn và siêu dữ liệu câu trả lời/lần ghi/tiến độ/tệp âm thanh.
- `backend/app/models/speaking_transcript.py` — lượt chép lời/sự kiện/bản chép lời.
- `backend/app/models/speaking_ai.py` — siêu dữ liệu lượt chấm AI/sự kiện/kết quả.
- `backend/app/schemas/speaking.py` — DTO Builder, làm bài, câu trả lời, khôi phục, xem lại.
- `backend/app/schemas/speaking_ai.py` — lược đồ bản chép lời/đặc trưng/chấm.
- `backend/app/repositories/speaking.py`, `speaking_transcript.py`, `speaking_ai.py` — chỉ lưu trữ.
- `backend/app/services/speaking_builder.py` — ngữ nghĩa soạn/kiểm/thứ tự.
- `backend/app/services/speaking_attempts.py` — máy trạng thái câu hỏi, quy tắc luyện tập/thi, hoàn tất.
- `backend/app/services/speaking_media.py` — lưu đoạn/phân đoạn riêng tư và phân quyền phát lại.
- `backend/app/services/speaking_transcript.py` — điều phối/bộ nhớ đệm chép lời.
- `backend/app/services/speaking_audio.py` — chuẩn hóa FFmpeg và hàm chất lượng/tiền xử lý.
- `backend/app/services/speaking_features.py` — bằng chứng độ lưu loát/ngữ điệu tất định.
- `backend/app/services/speaking_ai.py`, `speaking_ai_worker.py` — điều phối chấm điểm trước và vòng đời worker bền vững.
- `backend/app/providers/speaking_asr/` — giao thức nhà cung cấp ASR/căn chỉnh và bản triển khai tùy chọn.
- `backend/app/providers/speaking_pronunciation/` — giao thức bằng chứng phát âm từ âm thanh và bản cơ sở căn chỉnh/ngữ điệu.
- `backend/app/domains/scoring/speaking_prompts.py` — hợp đồng lời nhắc mô tả/bằng chứng/điểm/nhận xét.
- `frontend/src/features/speaking/` — kiểm trước khi làm bài, hook/bộ điều khiển ghi âm, làm bài, xem lại, bảng chép lời/AI.
- `frontend/src/lib/api/speaking.ts`, `speaking-ai.ts` — hợp đồng mạng có kiểu/Zod.

Không tạo mọi tệp trước. Chỉ tạo khi tác vụ sở hữu tệp đạt GREEN.

## Trọng tâm rà soát

1. Thử lại đoạn dữ liệu trùng/sai thứ tự khi mạng chập chờn phải tạo đúng một bản ghi logic có thứ tự; phiên MediaRecorder tiếp tục phải mở phân đoạn mới thay vì làm hỏng bộ chứa WebM trước.
2. Lặp tải lại/kết nối trong câu đang trả lời không được tăng thời gian nói: backend khôi phục một ảnh chụp còn lại hữu hạn, một bù 7 giây cho mỗi gián đoạn hợp lệ; câu hoàn tất vẫn đóng.
3. Người dùng/giáo viên không liên quan không được truy cập âm thanh/bản chép lời riêng bằng ID; giáo viên giao bài chỉ đọc bài có nguồn gốc bài giao theo điều kiện hiện có.
4. Lỗi ASR/âm thanh không được âm thầm thành điểm LR/GRA/Pronunciation hợp lệ. Bản chép lời/bằng chứng âm học thiếu/cũ phải rõ ràng; hành vi lỗi tiêu chí/lượt phải tất định.
5. Điều hướng/tải lại khi chép lời/chấm AI chỉ ngắt theo dõi; backend tiếp tục, đối chiếu SSE/JSON nối lại không xử lý trùng hoặc mất điểm đã lưu.

---

# P1 — Miền nghiệp vụ + cơ sở dữ liệu + Builder

### Tác vụ 1: bật phạm vi Speaking và lưu nội dung soạn

**Tệp:**
- Sửa: `AGENTS.md`
- Sửa: `backend/app/models/enums.py`
- Tạo: `backend/app/models/speaking.py`
- Sửa: `backend/app/models/__init__.py`
- Tạo: `backend/alembic/versions/<next_revision>_speaking_content.py`
- Sửa: `backend/app/schemas/content.py`
- Tạo: `backend/app/schemas/speaking.py`
- Kiểm thử: `backend/tests/test_speaking_builder.py`

**Giao diện:**
- Tạo `ModuleType.SPEAKING`, `SpeakingPromptType = SHORT_ANSWER | LONG_TURN | FOLLOW_UP`, `SpeakingPart`, `SpeakingPrompt` và DTO Builder lồng trong phản hồi `TestModule`/Builder hiện có.
- `SpeakingPart` thuộc một `TestModule` SPEAKING; `(module_id, part_number)` duy nhất cho Part 1/2/3. `SpeakingPrompt` có UUID ổn định, `order_index`, `prompt_text`, `preparation_seconds`, `response_seconds`, `config_json` hữu hạn cho gợi ý/dữ liệu trình bày.

- [x] **Bước 1: viết kiểm thử hợp đồng mô hình/Builder thất bại**

Thêm kiểm thử chứng minh `ModuleType.SPEAKING` được chấp nhận; biểu diễn đủ ba Part; từ chối số Part trùng; ID câu hỏi ổn định qua đổi thứ tự; bản nháp có thể thiếu; tuần tự hóa Builder lộ `speaking_parts` mà không đổi DTO Reading/Listening/Writing.

- [x] **Bước 2: chạy và xác nhận RED**

Chạy: `cd backend && uv run pytest tests/test_speaking_builder.py -q`

Kỳ vọng: FAIL vì enum/mô hình/lược đồ Speaking chưa có.

- [x] **Bước 3: triển khai enum, tệp mô hình tập trung, lược đồ, migration và hướng dẫn repository**

Trước tạo migration chạy `uv run alembic heads`; sinh từ đúng đầu duy nhất hiện tại. Chỉ thay cấm Speaking cũ trong `AGENTS.md` gốc bằng bất biến công việc Speaking theo đặc tả/kế hoạch đã duyệt. Không viết lại tài liệu lịch sử nói Speaking ngoài phạm vi tác vụ cũ.

- [x] **Bước 4: chạy GREEN và kiểm mã mô hình**

Chạy: `cd backend && uv run pytest tests/test_speaking_builder.py -q && uv run ruff check app/models/enums.py app/models/speaking.py app/schemas/speaking.py tests/test_speaking_builder.py`

- [x] **Bước 5: commit**

```bash
git add AGENTS.md backend/app/models backend/app/schemas backend/alembic/versions backend/tests/test_speaking_builder.py
git commit -m "Add Speaking content domain model"
```

### Tác vụ 2: CRUD Builder Speaking, kiểm tra, nhân bản phiên bản và chuyển dữ liệu

**Tệp:**
- Tạo: `backend/app/repositories/speaking.py`
- Tạo: `backend/app/services/speaking_builder.py`
- Tạo: `backend/app/api/v1/speaking.py`
- Sửa: `backend/app/api/v1/router.py`
- Sửa: `backend/app/api/v1/reading.py` chỉ ở chỗ dựng phản hồi Builder dùng chung
- Sửa: `backend/app/api/v1/tests.py`
- Sửa: dịch vụ nhân bản phiên bản đang nhân nội dung mô-đun Reading/Listening/Writing
- Sửa: `backend/app/api/v1/transfer.py` cùng tệp dịch vụ/lược đồ khi cần
- Kiểm thử: `backend/tests/test_speaking_builder.py`
- Kiểm thử: bộ kiểm nhân bản/chuyển dữ liệu hiện có

**Giao diện:**
- Tạo thao tác Builder thêm/cập nhật/xóa/đổi thứ tự Part/câu và `validate_speaking_module(module_id)`.
- Kiểm khi xuất bản/kiểm duyệt cần Part 1/2/3, đúng một `LONG_TURN` Part 2, đề không trống, thời gian dương, thứ tự chuẩn hóa duy nhất và loại câu hợp Part. Tự lưu nháp vẫn cho trạng thái trung gian chưa đủ.

- [x] **Bước 1: thêm kiểm thử API/dịch vụ thất bại** cho thêm cuối, chuẩn hóa thứ tự, gợi ý Part 2/thời gian 60/120 mặc định, mặc định 60 giây Part 1/3 cấu hình được, từ chối xuất bản sai, chính sách chủ sở hữu/bất biến đã xuất bản, nhân bản tạo ID mới theo ngữ nghĩa nhân bản hiện có và ZIP xuất/nhập khứ hồi.
- [x] **Bước 2: chạy RED:** `cd backend && uv run pytest tests/test_speaking_builder.py tests/test_asset_cloning.py -q` cùng tệp kiểm chuyển dữ liệu hiện có.
- [x] **Bước 3: triển khai repository/dịch vụ/tuyến tối thiểu, nối kiểm xuất bản.** Tái sử dụng `require_content_author`/chính sách truy cập hiện tại; không thêm lối bỏ qua cho giáo viên riêng Speaking.
- [x] **Bước 4: chạy GREEN + Ruff** cho tệp đã sửa.
- [x] **Bước 5: commit:** `git commit -am "Add Speaking Builder API and validation"` (đưa tệp mới vào vùng chờ rõ ràng trước).

### Tác vụ 3: giao diện Speaking Builder động

**Tệp:**
- Sửa: `frontend/src/lib/api/builder.ts`
- Tạo: `frontend/src/features/test-builder/speaking-builder.tsx`
- Tạo: `frontend/src/features/test-builder/speaking-prompt-editor.tsx`
- Sửa: `frontend/src/features/test-builder/builder-editor-page.tsx`
- Sửa: `frontend/src/features/test-builder/builder-workspace-navigation.tsx`
- Sửa: `frontend/src/features/test-builder/content-summary.tsx`
- Sửa: `frontend/src/app/globals.css`
- Sửa: `frontend/src/lib/i18n/en.ts`
- Sửa: `frontend/src/lib/i18n/vi.ts`
- Tạo: `frontend/tests/speaking-builder.test.tsx`

**Giao diện:**
- Hợp kiểu workspace Builder thành `overview | reading | listening | writing | speaking`; hợp kiểu mô-đun có `SPEAKING`.
- `SpeakingBuilder` hiển thị Part 1/2/3, thêm câu cuối, đổi thứ tự/xóa, gợi ý + thời gian + câu tiếp tùy chọn Part 2, dùng vòng đời tự lưu hiện có.

- [x] **Bước 1: viết kiểm thử RTL thất bại** cho điều hướng workspace, tạo, thêm/đổi thứ tự, mặc định Part 2, dữ liệu tự lưu, hành vi đóng băng đã xuất bản/đang kiểm duyệt, chuyển tiêu điểm tới thẻ mới, lớp/trạng thái tương thích giảm chuyển động.
- [x] **Bước 2: chạy RED:** `cd frontend && npx vitest run tests/speaking-builder.test.tsx`.
- [x] **Bước 3: triển khai UI/lược đồ API.** Dùng token giao diện ngữ nghĩa hiện có; thêm chuyển xuất hiện/đổi thứ tự nhẹ 150–250 ms và `prefers-reduced-motion`, không thư viện hoạt ảnh mới.
- [x] **Bước 4: chạy GREEN, kiểm kiểu/ESLint có mục tiêu:** `npx vitest run tests/speaking-builder.test.tsx && npm run typecheck` rồi ESLint tệp đã sửa.
- [x] **Bước 5: commit:** `git commit -m "Add Speaking Builder workspace"`.

**Chốt P1:** dừng và rà soát. Chưa bắt đầu làm giao diện thi khi kiểm P1 chưa đạt và hợp đồng Builder/xuất bản/nhân bản/chuyển dữ liệu chưa nhất quán.

---

# P2 — Giao diện làm bài + trạng thái ghi âm + bộ đếm

### Tác vụ 4: máy trạng thái Speaking và API câu hiện tại

**Tệp:**
- Mở rộng: `backend/app/models/speaking.py`
- Tạo: `backend/alembic/versions/<next_revision>_speaking_attempt_state.py`
- Tạo: `backend/app/services/speaking_attempts.py`
- Mở rộng: `backend/app/repositories/speaking.py`
- Mở rộng: `backend/app/schemas/speaking.py`
- Mở rộng: `backend/app/api/v1/speaking.py`
- Sửa: `backend/app/services/attempts.py`
- Sửa: `backend/app/services/attempt_scope.py`
- Kiểm thử: `backend/tests/test_speaking_attempts.py`

**Giao diện:**
- Tạo `SpeakingResponse`, `SpeakingResponseTake`, `SpeakingPromptProgress`.
- Các điểm vào dịch vụ về khái niệm: `get_state(attempt_id)`, `begin_prompt(...)`, `heartbeat(...)`, `finish_current_response(..., completion_reason)`, `retry_current_response(...)`.
- Tiến độ lưu câu/pha đang hoạt động, mốc/hạn pha có thẩm quyền, `last_confirmed_remaining_ms`, thế hệ/số lần gián đoạn, trạng thái đã dùng bù và thời gian tiếp tục gần nhất.

- [x] **Bước 1: viết kiểm trạng thái thất bại** cho thứ tự Part 1→chuẩn bị Part 2→bài nói dài/câu tiếp→Part 3; chỉ câu hiện tại; Xong/Tiếp; hết giờ; khóa câu đã chốt; chỉ thử lại câu hiện tại ở luyện tập; cấm thử lại/phát lại khi thi/Full Mock; đích câu Speaking theo phạm vi; thời gian còn lại máy khách không tăng trạng thái máy chủ.
- [x] **Bước 2: chạy RED:** `cd backend && uv run pytest tests/test_speaking_attempts.py tests/test_focused_attempts.py -q`.
- [x] **Bước 3: triển khai máy trạng thái bằng `TimerService.now()` và trạng thái cơ sở dữ liệu.** Không thêm ngữ nghĩa `setInterval` ở máy chủ. Giữ vòng đời `Attempt` tổng quát, tiến độ câu Speaking là trạng thái con.
- [x] **Bước 4: chạy GREEN + Ruff.**
- [x] **Bước 5: commit:** `git commit -m "Add Speaking attempt state machine"`.

### Tác vụ 5: kiểm trình duyệt trước khi làm bài, lớp ghi âm và trạng thái giao diện

**Tệp:**
- Tạo: `frontend/src/lib/api/speaking.ts`
- Tạo: `frontend/src/features/speaking/speaking-recorder.ts`
- Tạo: `frontend/src/features/speaking/use-speaking-recorder.ts`
- Tạo: `frontend/src/features/speaking/speaking-preflight.tsx`
- Tạo: `frontend/src/features/speaking/speaking-runner.tsx`
- Sửa: `frontend/src/app/attempt/[attemptId]/page.tsx`
- Sửa: hàm đích lượt làm bài/định tuyến dùng chung khi cần
- Sửa: `frontend/src/app/globals.css`, tệp i18n
- Tạo: `frontend/tests/speaking-preflight.test.tsx`
- Tạo: `frontend/tests/speaking-runner.test.tsx`
- Sửa: `frontend/tests/attempt-page.test.tsx`

**Giao diện:**
- `SpeakingRecorder` bọc `MediaRecorder`, `navigator.mediaDevices` gốc và lấy mẫu mức Web Audio; mã sản xuất nhận callback trạng thái/đoạn dữ liệu thay vì trực tiếp thao tác UI.
- Trạng thái giao diện phản chiếu pha backend: vào câu, chuẩn bị, ghi, hoàn tất/tải, hoàn tất, khôi phục.

- [x] **Bước 1: thêm kiểm thử thất bại** bằng `MediaRecorder`, `mediaDevices`, `AudioContext`, bộ đếm giả: từ chối quyền; chọn MIME ưu tiên WebM/Opus; thước mức âm; thi chỉ hiện câu hiện tại; chuẩn bị Part 2 + đếm trước bắt đầu; Xong/Tiếp và hết hạn; thi không thử/phát lại; xác nhận Thử lại luyện tập; không chuyển trước khi callback lưu xong; giảm chuyển động.
- [x] **Bước 2: chạy RED:** `cd frontend && npx vitest run tests/speaking-preflight.test.tsx tests/speaking-runner.test.tsx tests/attempt-page.test.tsx`.
- [x] **Bước 3: triển khai lớp ghi âm trình duyệt gốc và UI theo trạng thái.** Không thêm phụ thuộc sóng âm/ghi của bên thứ ba; dùng thanh mức nhẹ từ dữ liệu bộ phân tích.
- [x] **Bước 4: chạy GREEN + `npm run typecheck` + ESLint có mục tiêu.**
- [x] **Bước 5: commit:** `git commit -m "Add Speaking preflight and runner state UI"`.

**Chốt P2:** kiểm giao diện/trạng thái phải đạt với bộ ghi/mạng giả. Chưa bền vững qua sự cố tới P3; không quảng bá/bật luồng Speaking sản xuất trước khi xong P3.

---

# P3 — Tải đoạn âm thanh riêng tư + khôi phục + xem lại

### Tác vụ 6: lưu âm thanh riêng tư theo phân đoạn và phân quyền

**Tệp:**
- Mở rộng: `backend/app/models/speaking.py`
- Tạo: `backend/alembic/versions/<next_revision>_speaking_audio_chunks.py`
- Tạo: `backend/app/services/speaking_media.py`
- Mở rộng: `backend/app/repositories/speaking.py`
- Mở rộng: `backend/app/api/v1/speaking.py`
- Sửa: `backend/app/storage/local.py`
- Sửa: `backend/app/core/config.py`, `.env.example`, `backend/.env.example` chỉ cho cấu hình Speaking mới có giới hạn
- Kiểm thử: `backend/tests/test_speaking_media.py`

**Giao diện:**
- Thêm `SpeakingAudioSegment(response_take_id, segment_index, mime_type, ...)`, `SpeakingAudioChunk(segment_id, sequence, storage_key, sha256, byte_size, ...)` với ràng buộc duy nhất bảo đảm lặp an toàn.
- Một lần ghi luyện tập có thể nhiều phân đoạn sau sự cố/khôi phục. Phiên/tiến trình MediaRecorder mới luôn tạo phân đoạn mới; thứ tự đoạn dữ liệu chỉ trong phân đoạn. Dấu vân tay âm thanh logic cuối băm thứ tự băm phân đoạn/đoạn + danh tính lần ghi đã chốt.
- Điểm cuối đọc/phát riêng phân quyền chủ lượt hoặc màn kết quả giáo viên được bài giao cho phép hiện có; ID không liên quan không cấp truy cập.

- [x] **Bước 1: viết kiểm thử thất bại** cho MIME WebM, giới hạn kích thước, thử lại trùng `(segment,sequence)` lặp an toàn, từ chối băm trùng mâu thuẫn, tới sai thứ tự vẫn ra bản kê đúng, phân đoạn mới sau khôi phục, loại lần ghi luyện tập bị thay, dấu vân tay tất định và phân quyền phát chủ/giáo viên/người ngoài.
- [x] **Bước 2: chạy RED:** `cd backend && uv run pytest tests/test_speaking_media.py tests/test_asset_access.py tests/test_classroom_assignments.py -q`.
- [x] **Bước 3: triển khai bản kê lưu trữ riêng.** Dùng lại an toàn hệ thống tệp `LocalAssetStorage`, lưu trong không gian Speaking riêng; không tạo dòng nội dung công khai `Asset` cho âm thanh người làm bài. Mở xử lý MIME WebM/Opus trình duyệt.
- [x] **Bước 4: chạy GREEN + Ruff.**
- [x] **Bước 5: commit:** `git commit -m "Add private Speaking chunk storage"`.

### Tác vụ 7: giao thức gián đoạn/khôi phục với một lần bù 7 giây

**Tệp:**
- Mở rộng: `backend/app/services/speaking_attempts.py`
- Mở rộng: `backend/app/api/v1/speaking.py`
- Mở rộng: `backend/app/schemas/speaking.py`
- Mở rộng: `backend/app/core/config.py`
- Kiểm thử: `backend/tests/test_speaking_recovery.py`

**Giao diện:**
- Tạo ngữ nghĩa `interrupt`/`resume` rõ hoặc chuyển trạng thái lặp an toàn tương đương, định khóa bằng câu/lần ghi hiện tại + thế hệ gián đoạn.
- Phản hồi tiếp tục trả `remaining_ms` do máy chủ cho phép, `recovery_grace_seconds=7`, danh tính câu/lần ghi/phân đoạn kế và khả năng khôi phục.
- Thêm cấu hình cửa sổ đủ điều kiện kết nối lại hữu hạn (chọn mặc định thận trọng khi triển khai, ghi tài liệu/kiểm); hạn chế lạm dụng/khôi phục sự cố nhưng không đổi hợp đồng bù 7 giây hiển thị.

- [x] **Bước 1: viết kiểm thất bại** cho ảnh chụp 31 giây → bù 7 giây → tiếp 31 giây; tải lặp cùng thế hệ không cộng bù; từ chối mã/thế hệ cũ; không mở câu hoàn tất; gián đoạn muộn/không khôi phục bị từ chối an toàn; heartbeat/xác nhận đoạn chỉ giảm không tăng còn lại; tiếp tục đồng thời lặp an toàn.
- [x] **Bước 2: chạy RED:** `cd backend && uv run pytest tests/test_speaking_recovery.py -q`.
- [x] **Bước 3: triển khai khôi phục an toàn giao dịch.** Chỉ lưu trạng thái an toàn kiểm toán, không ghi nội dung chép lời/âm thanh vào nhật ký.
- [x] **Bước 4: chạy GREEN + Ruff.**
- [x] **Bước 5: commit:** `git commit -m "Add Speaking crash recovery protocol"`.

### Tác vụ 8: nối truyền đoạn/khôi phục với giao diện làm bài và tạo phát lại xem lại

**Tệp:**
- Mở rộng: `frontend/src/lib/api/speaking.ts`
- Mở rộng: `frontend/src/features/speaking/speaking-recorder.ts`
- Mở rộng: `frontend/src/features/speaking/speaking-runner.tsx`
- Tạo: `frontend/src/features/speaking/speaking-review.tsx`
- Sửa: tệp đích định tuyến làm bài/xem lại
- Sửa: `frontend/src/app/globals.css`, tệp i18n
- Mở rộng: `frontend/tests/speaking-runner.test.tsx`
- Tạo: `frontend/tests/speaking-review.test.tsx`

**Giao diện:**
- Bộ ghi phát đoạn dữ liệu mỗi khoảng ~2–5 giây cấu hình được, thử tải lặp an toàn, đẩy hết trước hoàn tất, mở phân đoạn mới sau khôi phục.
- Xem lại dựng thẻ trả lời Part 1/2/3 có câu/thẻ gợi ý, thời lượng, trình phát được phân quyền và chỗ dành chép lời/AI về sau.

- [x] **Bước 1: viết kiểm frontend thất bại** cho thử lại đoạn, ACK tải trước câu kế, ảnh chụp/bù đếm ngược khi tải lại cứng, phân đoạn mới sau tiếp ghi, tải cuối lỗi giữ câu, Nghe/Thử lại luyện tập so điều khiển thi ẩn, phát lại từng câu.
- [x] **Bước 2: chạy RED** chỉ với Vitest/giả lập.
- [x] **Bước 3: triển khai UI truyền/khôi phục/xem lại.** Trang khôi phục hiện trạng thái phục hồi + đếm 7→1 và tạm dừng thời gian gốc trong khoảng bù.
- [x] **Bước 4: chạy GREEN + kiểm kiểu/ESLint có mục tiêu.**
- [x] **Bước 5: commit:** `git commit -m "Connect Speaking recording recovery and review"`.

**Chốt P3:** ghi Speaking thi/luyện phải dùng bền vững được không cần chép lời/AI. Kiểm không lộ tệp riêng hoặc lách tăng thời gian trước P4.

---

# P4 — Chuỗi xử lý chép lời

### Tác vụ 9: hợp đồng ASR, lưu bản chép lời và lượt xử lý bền vững

**Tệp:**
- Tạo: `backend/app/providers/speaking_asr/base.py`
- Tạo: `backend/app/providers/speaking_asr/faster_whisper.py`
- Tạo: `backend/app/providers/speaking_asr/__init__.py`
- Tạo: `backend/app/models/speaking_transcript.py`
- Tạo: `backend/alembic/versions/<next_revision>_speaking_transcripts.py`
- Tạo: `backend/app/repositories/speaking_transcript.py`
- Tạo: `backend/app/services/speaking_transcript.py`
- Mở rộng: `backend/app/schemas/speaking_ai.py`
- Mở rộng: `backend/app/api/v1/speaking.py`
- Sửa: `backend/app/main.py` để dừng worker nếu dùng sổ tác vụ nền
- Sửa: `backend/pyproject.toml` thêm gói bổ sung `speech` tùy chọn, không nạp phụ thuộc nặng trong kiểm cơ bản
- Kiểm thử: `backend/tests/test_speaking_transcript.py`

**Giao diện:**
- `SpeechASRProvider.transcribe(audio: NormalizedAudio) -> ASRResult` trả văn bản nguyên văn, thời gian/độ tin cậy từ, nhà cung cấp/mô hình/phiên bản.
- Lưu `SpeakingTranscriptRun` + sự kiện tăng dần, hai bản chép lời mỗi câu thành công (`VERBATIM`, `CLEAN`), định khóa theo dấu vân tay âm thanh + phiên bản/cấu hình ASR/căn chỉnh.
- Tái sử dụng lượt hoạt động/hoàn tất khớp; dấu vân tay/phiên bản khác vô hiệu bộ nhớ đệm.

- [x] **Bước 1: viết kiểm thất bại** với nhà cung cấp giả: cô lập từng câu, một câu lỗi không xóa bản thành công, tái sử dụng lượt hoạt động khớp, trúng bộ nhớ đệm, đổi âm thanh khi thử lại làm mất hiệu lực, kiểm mốc từ, chuẩn hóa sạch giữ lỗi ngữ pháp (ví dụ `He go to school` không thành `He goes...`).
- [x] **Bước 2: chạy RED:** `cd backend && uv run pytest tests/test_speaking_transcript.py -q`.
- [x] **Bước 3: triển khai lớp nhà cung cấp và công việc bền vững với factory dễ giả lập.** Bộ tiếp hợp faster-whisper nhập lười; nhập ứng dụng/kiểm thường vẫn được khi chưa cài gói speech. V1 không phân tách người nói.
- [x] **Bước 4: chạy GREEN + Ruff.** Không tải/chạy mô hình Whisper thật.
- [x] **Bước 5: commit:** `git commit -m "Add durable Speaking transcription pipeline"`.

### Tác vụ 10: thao tác chép lời, SSE/đối chiếu và giao diện chỉ đọc từng câu

**Tệp:**
- Mở rộng: `frontend/src/lib/api/speaking.ts`
- Tạo/mở rộng: `frontend/src/lib/api/speaking-ai.ts`
- Tạo: `frontend/src/features/speaking/speaking-transcript-panel.tsx`
- Mở rộng: `frontend/src/features/speaking/speaking-review.tsx`
- Tạo: `frontend/tests/speaking-transcript.test.tsx`
- Tạo: `frontend/tests/speaking-api.test.ts`

**Giao diện:**
- Xem lại mở `Generate Transcript` riêng với `Grade with AI`.
- Bộ theo dõi sự kiện theo Writing: số thứ tự tăng, khử trùng, đối chiếu ảnh chụp JSON; dọn màn chỉ ngắt theo dõi.

- [x] **Bước 1: viết kiểm thất bại** cho trạng thái nút, Sẵn sàng/Đang xử lý/Thất bại từng câu, chép lời chỉ đọc, không có Bản chép lời toàn bộ gộp, xử lý SSE trùng/kết nối lại, dọn điều hướng không gọi hủy.
- [x] **Bước 2: chạy RED.**
- [x] **Bước 3: triển khai API có kiểu/Zod và bảng trực tiếp.**
- [x] **Bước 4: chạy GREEN + kiểm kiểu/ESLint.**
- [x] **Bước 5: commit:** `git commit -m "Add Speaking transcript review UI"`.

**Chốt P4:** dùng chép lời độc lập với chấm; không sửa bản chép lời, lỗi vẫn theo câu.

---

# P5 — Chất lượng âm thanh + độ lưu loát + bằng chứng phát âm

### Tác vụ 11: chuẩn hóa âm thanh và cổng chất lượng

**Tệp:**
- Tạo: `backend/app/services/speaking_audio.py`
- Tạo: `backend/app/services/speaking_quality.py`
- Sửa: `backend/app/core/config.py`, ví dụ môi trường cho đường dẫn FFmpeg/thời gian chờ/ngưỡng chất lượng khi cần
- Kiểm thử: `backend/tests/test_speaking_audio.py`

**Giao diện:**
- `normalize_committed_take(...) -> NormalizedAudio` ghép phân đoạn/đoạn đúng thứ tự qua FFmpeg thành PCM/WAV mono 16 kHz phái sinh, không sửa nguồn gốc.
- `assess_audio_quality(...) -> AudioQualityResult` phát ít nhất `AUDIO_OK`, `NO_SPEECH`, `TOO_SHORT`, `AUDIO_CORRUPT`, `VERY_LOW_SIGNAL`, `SEVERE_CLIPPING`, `BACKGROUND_DOMINANT`, `ASR_UNUSABLE`.

- [x] **Bước 1: viết kiểm thất bại** cho dựng lệnh tiến trình con/an toàn đường dẫn, siêu dữ liệu tổng hợp/mẫu nhỏ; trạng thái không chấm được phải rõ, không trả band.
- [x] **Bước 2: chạy RED.**
- [x] **Bước 3: triển khai lớp bọc FFmpeg/hợp đồng chất lượng hữu hạn.** Giữ tài sản gốc bất biến; có thể đệm phái sinh theo dấu vân tay/phiên bản.
- [x] **Bước 4: chạy GREEN + Ruff.** Không cần chạy tích hợp FFmpeg/mô hình bên ngoài; giả lập tiến trình con khi phù hợp.
- [x] **Bước 5: commit:** `git commit -m "Add Speaking audio quality preprocessing"`.

### Tác vụ 12: độ lưu loát tất định và bằng chứng phát âm từ âm thanh

**Tệp:**
- Tạo: `backend/app/services/speaking_features.py`
- Tạo: `backend/app/providers/speaking_pronunciation/base.py`
- Tạo: `backend/app/providers/speaking_pronunciation/alignment_prosody.py`
- Tạo: `backend/app/providers/speaking_pronunciation/__init__.py`
- Mở rộng: `backend/app/schemas/speaking_ai.py`
- Kiểm thử: `backend/tests/test_speaking_features.py`

**Giao diện:**
- `extract_fluency_features(audio, verbatim_transcript, words) -> FluencyEvidence` tính thời lượng, tỷ lệ nói/im, WPM, tốc độ phát âm, khoảng ngừng/ngừng dài, tín hiệu từ đệm/lặp/khởi đầu bỏ dở/tự sửa, độ dài lượt trung bình, thời lượng liên tục Part 2.
- `PronunciationEvidenceProvider.analyse(audio, transcript, alignment) -> PronunciationEvidence` cung cấp chỉ báo từ âm thanh về căn chỉnh/độ rõ đoạn, đoạn độ tin cậy thấp/chưa căn, tóm tắt trọng âm/nhịp/ngữ điệu/cao độ-năng lượng/vận luật, chỉ báo dễ hiểu/nỗ lực người nghe. Đây là bằng chứng, không ánh xạ trực tiếp band IELTS.

- [x] **Bước 1: viết kiểm đặc trưng tất định thất bại** với mốc thời gian biết trước, chia 0/lời nói rỗng, phân phối ngừng dài, giữ ngập ngừng, thời lượng Part 2, trạng thái nhà cung cấp không khả dụng/bằng chứng thấp.
- [x] **Bước 2: chạy RED.**
- [x] **Bước 3: triển khai mã đặc trưng thuần và nhà cung cấp phát âm thay thế được.** Bản cơ sở có thể dùng độ tin cậy ASR/căn chỉnh cưỡng bức cùng đặc trưng âm học/vận luật; không gọi điểm SpeechOcean/GOPT là “band IELTS”, không chỉ dùng bản chép lời cho PR.
- [x] **Bước 4: chạy GREEN + Ruff.** Không gọi mô hình âm học/GPU thật.
- [x] **Bước 5: commit:** `git commit -m "Add Speaking fluency and pronunciation evidence"`.

**Chốt P5:** tiền xử lý chỉ tạo bằng chứng giải thích được. Rà riêng để không ngưỡng nào vô tình thành quy tắc band.

---

# P6 — Bộ chấm AI IELTS Speaking kết hợp

### Tác vụ 13: lược đồ chấm, mô tả và dịch vụ tiêu chí điểm trước

**Tệp:**
- Tạo: `backend/app/domains/scoring/speaking_prompts.py`
- Tạo: `backend/app/services/speaking_ai.py`
- Tạo: `backend/app/providers/speaking_llm/base.py`
- Tạo: `backend/app/providers/speaking_llm/configured.py`
- Tạo/mở rộng: `backend/app/schemas/speaking_ai.py`
- Sửa: `backend/app/domains/scoring/__init__.py`
- Kiểm thử: `backend/tests/test_speaking_ai.py`

**Giao diện:**
- Tiêu chí: `fc`, `lr`, `gra`, `pr`.
- Chuỗi mỗi tiêu chí: gói bằng chứng -> `CriterionBandScore {score}` (JSON nhỏ; bước 0.5) -> điểm hợp lệ bền vững -> `CriterionFeedback {feedback,strengths,improvements}`.
- FC dùng bằng chứng thời gian/nguyên văn/ngữ nghĩa; LR/GRA dùng chép lời; PR từ chối khi thiếu bằng chứng phát âm từ âm thanh chấp nhận được.
- `speaking_overall(criteria) -> (raw_mean, overall_band)` dùng trọng số đều và chính sách hiển thị nửa band dự án; kết quả vẫn ghi rõ tư vấn.

- [x] **Bước 1: viết kiểm thất bại** cho tách bằng chứng mô tả, đầu vào toàn lượt, không trung bình từng câu, kiểm 0.5, trần token điểm nhỏ, một sửa hữu hạn, nhận xét không ghi đè điểm, lỗi nhận xét giữ điểm/dự phòng an toàn, lỗi điểm không bịa mặc định, thiếu âm học PR => không khả dụng/lỗi rõ, phép tổng trọng số đều.
- [x] **Bước 2: chạy RED:** `cd backend && uv run pytest tests/test_speaking_ai.py -q`.
- [x] **Bước 3: triển khai bộ chấm qua bộ tiếp hợp LLM Speaking ủy quyền hợp đồng LLM cấu trúc đã cấu hình, không đổi tên/tái cấu trúc nội bộ nhà cung cấp Writing.** Không gian lời nhắc/phiên bản Speaking độc lập để tăng phiên bản/bộ nhớ đệm không đổi lịch sử Writing v9.
- [x] **Bước 4: chạy GREEN + Ruff.** Chỉ hoàn thành giả.
- [x] **Bước 5: commit:** `git commit -m "Add score-first Speaking criterion scorer"`.

### Tác vụ 14: lượt chấm AI bền vững, bộ nhớ đệm, hủy và SSE

**Tệp:**
- Tạo: `backend/app/models/speaking_ai.py`
- Tạo: `backend/alembic/versions/<next_revision>_speaking_ai_runs.py`
- Tạo: `backend/app/repositories/speaking_ai.py`
- Tạo: `backend/app/services/speaking_ai_worker.py`
- Tạo: `backend/app/api/v1/speaking_ai.py`
- Sửa: `backend/app/api/v1/router.py`
- Sửa: `backend/app/main.py`
- Mở rộng: `backend/app/core/config.py`, ví dụ môi trường
- Mở rộng: `backend/tests/test_speaking_ai.py`

**Giao diện:**
- Trạng thái/sự kiện lượt lộ `QUEUED/PENDING`, `QUALITY_CHECK`, `TRANSCRIBING`, `ANALYSING_AUDIO`, `BUILDING_EVIDENCE`, `SCORING`, `GENERATING_FEEDBACK` và ngữ nghĩa kết thúc COMPLETED/FAILED/CANCELLED.
- Dấu vân tay bộ nhớ đệm gồm âm thanh/lần ghi đã chốt + phiên bản ASR/căn chỉnh + phiên bản trích đặc trưng/nhà cung cấp phát âm + thang chấm/lời nhắc/mô hình.
- `Grade with AI` tái sử dụng lượt/kết quả chép khớp hoặc chờ ASR hoạt động khớp, không khởi chép trùng.
- SSE dùng sự kiện `(run_id, sequence)` tăng dần, đối chiếu `Last-Event-ID`/`after`, không đệm proxy; ngắt trình duyệt không hủy worker. Chỉ Dừng rõ ràng là thao tác hủy của người dùng.

- [x] **Bước 1: thêm kiểm lưu/API thất bại** cho trúng bộ nhớ đệm, sai do âm thanh cũ, lượt hoạt động trùng, tái sử dụng chép, worker sống qua ngắt yêu cầu/SSE, hủy rõ, khởi động lại/lượt cũ, checkpoint điểm bền trước nhận xét, số thứ tự sự kiện duy nhất.
- [x] **Bước 2: chạy RED.**
- [x] **Bước 3: triển khai repository/worker/router lượt theo ngữ nghĩa bền vững Writing nhưng ở bảng/mô-đun Speaking riêng.** Tránh tái cấu trúc Writing diện rộng.
- [x] **Bước 4: chạy GREEN + Ruff.** Không nhà cung cấp/mô hình trực tiếp.
- [x] **Bước 5: commit:** `git commit -m "Add durable Speaking AI grading runs"`.

### Tác vụ 15: giao diện đánh giá AI động

**Tệp:**
- Mở rộng: `frontend/src/lib/api/speaking-ai.ts`
- Tạo: `frontend/src/features/speaking/speaking-ai-progress.tsx`
- Tạo: `frontend/src/features/speaking/speaking-ai-assessment.tsx`
- Mở rộng: `frontend/src/features/speaking/speaking-review.tsx`
- Sửa: `frontend/src/app/globals.css`, tệp i18n
- Tạo: `frontend/tests/speaking-ai-api.test.ts`
- Tạo: `frontend/tests/speaking-ai-assessment.test.tsx`

**Giao diện:**
- Xem lại giữ hai thao tác: Tạo bản chép lời và Chấm bằng AI. Nút Chấm dùng được trước khi bấm tạo bản chép lời.
- Đánh giá hiện tổng tư vấn + FC/LR/GRA/PR, bằng chứng/nhận xét, phân tích độ lưu loát/Part 2/phát âm, tiến độ bước trực tiếp. Điểm tiêu chí hợp lệ đã lưu vẫn hiện dù nhận xét sau lỗi.

- [x] **Bước 1: viết kiểm thất bại** cho tiến độ bước, SSE kết nối lại/khử trùng, Dừng gọi hủy, tháo thành phần không hủy, hiển thị nhận xét dự phòng, thông báo chất lượng không chấm được, nhãn tư vấn, giao diện/giảm chuyển động.
- [x] **Bước 2: chạy RED.**
- [x] **Bước 3: triển khai UI theo ngữ nghĩa theo dõi Writing, không gắn hợp đồng Speaking với tên tiêu chí Writing.**
- [x] **Bước 4: chạy GREEN + `npm run typecheck` + ESLint có mục tiêu.**
- [x] **Bước 5: commit:** `git commit -m "Add Speaking AI assessment UI"`.

**Chốt P6:** không tuyên bố độ chính xác giám khảo. Xác nhận PR không thể thành công từ bằng chứng chỉ văn bản, checkpoint điểm sống qua lỗi nhận xét.

---

# P7 — Full Mock + lịch sử + lớp học

### Tác vụ 16: Full Mock bốn kỹ năng và điểm tổng

**Tệp:**
- Sửa: `backend/app/services/test_sessions.py`
- Sửa: `backend/app/domains/module_durations.py`
- Sửa: `backend/app/domains/scoring/ielts_band.py`
- Sửa: `backend/app/domains/scoring/__init__.py`
- Sửa: `backend/app/schemas/test_sessions.py`
- Kiểm thử: TestSession/Full Mock hiện có + `backend/tests/test_full_mock_history_delete.py`
- Sửa: `frontend/src/lib/api/exam.ts`
- Sửa: thành phần/kiểm chuyển Full Mock

**Giao diện:**
- `MODULE_ORDER = (LISTENING, READING, WRITING, SPEAKING)`.
- `project_overall_band(reading, listening, writing, speaking)` trả `None` tới khi đủ bốn, dùng chính sách nửa band tổng IELTS hiện có.
- Full Mock hoàn tất sau lượt Speaking cuối, không phải Writing.

- [x] **Bước 1: viết kiểm backend/frontend thất bại** cho bốn mô-đun/thời lượng bắt buộc, chuyển Writing→Speaking, hoàn tất phiên sau Speaking, từ chối thiếu Speaking, tổng bốn band, xóa lịch sử vẫn xóa an toàn cả phiên.
- [x] **Bước 2: chạy RED.**
- [x] **Bước 3: triển khai đổi thứ tự/thời lượng/tổng.** Chọn mặc định thời lượng khuyến nghị Speaking hợp lý, khớp thời gian câu đã soạn; không dùng thời lượng chính thức 11–14 phút cũ làm bất biến cơ sở dữ liệu cứng cho lượt.
- [x] **Bước 4: chạy GREEN + kiểm kiểu/Ruff khi phù hợp.**
- [x] **Bước 5: commit:** `git commit -m "Integrate Speaking into Full Mock"`.

### Tác vụ 17: lịch sử, luyện theo phạm vi, phân tích, kết quả bài giao và riêng tư

**Tệp:**
- Sửa: `backend/app/services/history.py`, `backend/app/api/v1/history.py` nếu cần mở trình bày riêng mô-đun
- Sửa: `backend/app/services/classroom_assignments.py`, `backend/app/api/v1/classroom_assignments.py`
- Sửa: lược đồ/dịch vụ phân tích chỉ nơi liệt kê kỹ năng rõ ràng
- Sửa: API/thành phần lịch sử và kết quả lớp frontend
- Mở rộng: `frontend/src/features/speaking/speaking-review.tsx` cho giáo viên chỉ đọc
- Kiểm thử: `backend/tests/test_classroom_assignments.py`, `backend/tests/test_focused_attempts.py`, kiểm lịch sử/phân tích; kiểm lịch sử/lớp frontend

**Giao diện:**
- Lịch sử cá nhân lộ lượt Speaking với tóm tắt âm thanh/chép lời/AI theo phân quyền chủ sở hữu thường.
- Giáo viên chỉ đọc được câu trả lời/âm thanh/bản chép lời/kết quả tư vấn của bài giao qua đúng điều kiện nguồn gốc hiện có; luyện cá nhân trên cùng phiên bản vẫn riêng tư.
- Luyện Speaking theo phạm vi có thể chọn câu/Part theo phạm vi lượt đã duyệt, không nới hành vi thi.

- [x] **Bước 1: thêm kiểm riêng tư/tích hợp thất bại** cho giáo viên truy cập bài giao so luyện cá nhân khác, bỏ thành viên vẫn giữ quyền đọc bài giao lịch sử, ngữ nghĩa thử lại theo phạm vi, dựng/xóa lịch sử, liệt kê Speaking phân tích nơi có.
- [x] **Bước 2: chạy RED.**
- [x] **Bước 3: tích hợp bằng nguồn gốc/chính sách truy cập hiện có; không thêm lối tra mọi học viên cho giáo viên.**
- [x] **Bước 4: chạy GREEN + kiểm kiểu frontend/kiểm mã có mục tiêu.**
- [x] **Bước 5: commit:** `git commit -m "Integrate Speaking history and classroom results"`.

**Chốt P7:** kiểm bốn kỹ năng cùng tồn tại; phiên lịch sử ba kỹ năng vẫn đọc được, không hồi tố thành không hợp lệ. Full Mock mới cần Speaking.

---

# P8 — Công cụ benchmark + hiệu chuẩn

### Tác vụ 18: bộ chạy đánh giá Speaking có nhãn người chấm và tài liệu

**Tệp:**
- Tạo: `backend/app/benchmarks/speaking.py` (hoặc theo quy ước gói benchmark hiện có)
- Tạo: `backend/scripts/evaluate_speaking.py`
- Tạo: `backend/tests/test_speaking_benchmark.py`
- Tạo: `docs/ai-speaking.md`
- Sửa: README/lộ trình chỉ nơi còn liệt kê Speaking là tương lai

**Giao diện:**
- Bản kê đánh giá tham chiếu âm thanh cục bộ/riêng bằng đường dẫn hoặc ID mẫu kiểm soát, cùng nhãn người chấm FC/LR/GRA/PR/tổng; không commit bản ghi riêng/có bản quyền.
- Báo MAE, RMSE từng tiêu chí/tổng, Pearson/Spearman khi đủ mẫu, Quadratic Weighted Kappa, trong ±0.5/±1.0, tỷ lệ lỗi/không chấm được; chỉ phân nhóm tùy chọn khi cỡ mẫu có trách nhiệm.
- Lưu siêu dữ liệu phiên bản bộ chấm/nhà cung cấp/lời nhắc/ASR/âm học mỗi kết quả để tái hiện đổi hiệu chuẩn.

- [x] **Bước 1: viết kiểm chỉ số/bản kê thất bại** với nhãn/dự đoán tổng hợp, gồm dòng thiếu/không chấm được, đầu ra tất định.
- [x] **Bước 2: chạy RED:** `cd backend && uv run pytest tests/test_speaking_benchmark.py -q`.
- [x] **Bước 3: triển khai CLI ngoại tuyến/tài liệu.** Giải thích Speak & Improve/SpeechOcean/L2-ARCTIC hỗ trợ nghiên cứu, không trực tiếp là dữ liệu chuẩn nhãn IELTS; không thêm tự tải/phân phối tập dữ liệu.
- [x] **Bước 4: chạy GREEN + Ruff.**
- [x] **Bước 5: commit:** `git commit -m "Add Speaking grading benchmark tooling"`.

Xác minh P8: 142 kiểm thử tập trung đạt (`test_speaking_ai.py`,
`test_speaking_benchmark.py`, `test_speaking_benchmark_metrics.py`); Ruff có mục tiêu
và `git diff --check` đạt. Bộ chạy/CLI theo quy ước `app/evaluation` và
`scripts` gốc hiện có. P8 không thêm nhà cung cấp trực tiếp, đổi điểm sản xuất hoặc
migration cơ sở dữ liệu mới.

---

## Lệnh xác minh từng giai đoạn

Cuối mỗi giai đoạn chỉ chạy kiểm thử tập trung chịu tác động cùng kiểm tĩnh ít chi phí; không mở trình duyệt hoặc chạy hạ tầng tiếng nói/LLM trực tiếp. Lệnh điển hình:

```bash
cd backend
uv run pytest tests/test_speaking_builder.py -q                 # P1
uv run pytest tests/test_speaking_attempts.py -q                # P2
uv run pytest tests/test_speaking_media.py tests/test_speaking_recovery.py -q  # P3
uv run pytest tests/test_speaking_transcript.py -q              # P4
uv run pytest tests/test_speaking_audio.py tests/test_speaking_features.py -q   # P5
uv run pytest tests/test_speaking_ai.py -q                       # P6
# P7: focused full-mock/history/classroom targets named above
uv run pytest tests/test_speaking_benchmark.py -q                # P8
uv run ruff check <touched backend files>

cd ../frontend
npx vitest run <phase-specific speaking test files>
npm run typecheck
npx eslint <touched frontend files>

cd ..
git diff --check
```

Nếu lệnh tập trung phát hiện lỗi cũ không liên quan, báo tên lỗi thay vì mở bộ kiểm dài ngoài phạm vi. Không nói đã xác minh giai đoạn nếu kiểm được nêu chưa thực sự đạt.

## Chốt commit/rà soát khuyến nghị

Triển khai P1–P8 tuần tự. Mỗi tác vụ đánh số có commit riêng; mỗi giai đoạn kết thúc bằng rà soát trước giai đoạn sau. Kiến trúc phụ thuộc giao diện chặt (ID nội dung -> trạng thái lượt -> bản kê tệp -> chép lời -> đặc trưng -> chấm -> tích hợp sản phẩm), không giao giai đoạn sau khi giao diện trước chưa ổn.

Trước mỗi giai đoạn:

```bash
git fetch origin
git pull --ff-only origin main
git status --short
```

Yêu cầu cây làm việc sạch trước bắt đầu, giữ công việc thượng nguồn như Writing AI v9, không force-push `main`.

## Phạm vi tự rà soát

- Đặc tả §§1–2: Tác vụ 1–3 (miền nội dung, Builder, kiểm tra, soạn động).
- Đặc tả §§3–5: Tác vụ 4–8 (kiểm trước, làm bài, quy tắc luyện/thi, chia đoạn, khôi phục, xem lại).
- Đặc tả §§6–8: Tác vụ 9–12 (chép lời, chất lượng, ASR/căn chỉnh, bằng chứng độ lưu loát/âm học).
- Đặc tả §§9–12: Tác vụ 13–15 (chấm tổng thể bốn tiêu chí điểm trước, lượt/bộ nhớ đệm/SSE bền vững, UI AI).
- Đặc tả §§13–18: xuyên Tác vụ 6–17 (riêng tư, nguồn gốc giữ lại, UX động, lỗi/cấu hình, Full Mock/lớp/lịch sử).
- Triển khai Đặc tả §19: giữ đúng chốt rà soát P1–P8.
- Benchmark/hiệu chuẩn Đặc tả §20: Tác vụ 18.

Năm rủi ro Trọng tâm rà soát được kiểm rõ ở Tác vụ 6/7 (đoạn/khôi phục), 6/17 (phân quyền riêng tư), 9/11/13 (lỗi ASR/âm thanh), 9/14/15 (nền bền vững/kết nối lại).
