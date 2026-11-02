# Luyện tập theo phạm vi — Giai đoạn 1–3

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: mô tả luyện tập theo phạm vi ở Giai đoạn 1–3. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../backend/app/services/attempt_scope.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/attempts.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải kết quả chạy lại trong đợt kiểm toán này.

Luyện tập theo phạm vi tái sử dụng `Attempt`, chủ sở hữu, `TestVersion` đã xuất bản và đóng băng, bộ đếm thời gian, tự lưu, tạm dừng/tiếp tục, nộp và vòng đời xem lại. Giai đoạn 1 tạo nền tảng phạm vi; Giai đoạn 2 mở bài đọc Reading và tác vụ Writing; Giai đoạn 3 hoàn thiện luồng người dùng với phần Listening và khoảng âm thanh trong bản ghi dùng chung.

## Giai đoạn 2 — Reading và Writing

`/practice` (thanh bên: **Luyện kỹ năng**) dùng không gian đã xác thực và API phiên bản đã xuất bản hiện có. Trang liệt kê đơn vị học từ đề đóng băng còn khả dụng, chưa lưu trữ, trong lưới gọn; mỗi thẻ ghi chính xác nguồn gốc đề/phiên bản. Bảng lọc nội bộ chọn Reading, Listening hoặc Writing và suy bộ lọc Bài đọc/Phần/Tác vụ từ đơn vị đã xuất bản. Tìm kiếm phía máy khách khớp tên đề, tên đơn vị và trích đoạn đề Writing trong bộ lọc đó. Trên máy tính bảng lọc cạnh kết quả, màn hình nhỏ đặt phía trên; thẻ thích ứng chiều rộng. Ảnh thu nhỏ được hoãn. Thư viện đề vẫn là nơi luyện toàn kỹ năng và Full Mock.

Tóm tắt VersionDetail công khai nay gồm ID bài đọc Reading và tác vụ Writing, số từ khuyến nghị tối thiểu, thời lượng khuyến nghị. Tóm tắt nhóm câu hỏi có số vị trí câu thật để đánh số khác thường không bị diễn giải thành dải liên tục giả. Tóm tắt không chứa đáp án hoặc giải thích.

Reading khởi tạo một bài đọc với 20 / 25 / 30 phút hoặc đếm tăng (mặc định 20). Writing khởi tạo một Task 1 hoặc Task 2 với 20 / 25 / 30 / 35 / 40 phút hoặc đếm tăng (mặc định Task 1 = 20, Task 2 = 40). Cả hai dùng `POST /attempts`, phạm vi FOCUSED_UNIT và UUID đơn vị đã xuất bản thật, rồi mở `/attempt/{id}`. Trạng thái đang khởi tạo chặn nhấp trùng; lỗi giữ bộ đếm đã chọn.

Giao diện làm bài và chốt tạm dừng hiện có nhận diện đơn vị đã chọn. Một tác vụ Writing không có nút chuyển tác vụ dư thừa. Tự lưu, tô sáng, cờ, hình, đếm từ, bộ đếm và chuyển vòng đời giữ hành vi hiện có.

Xem lại và lịch sử **Luyện tập theo phạm vi** hiển thị Reading điểm đúng thô/tối đa và tỷ lệ chính xác một chữ số thập phân khi tối đa dương; kết quả một phần không hàm ý band IELTS. Writing theo phạm vi hiển thị **Điểm tác vụ** nếu có điểm tiêu chí, nếu không là **Chưa chấm**. `task_score` có thể null trong lịch sử dùng `calculate_task_overall` hiện có cho đúng tác vụ Writing được chọn, còn `band_score` giữ null. Phạm vi/mô-đun khác trả task_score null. Xem lại giữ trung bình chính xác hai chữ số thập phân; lịch sử định dạng một chữ số. Không có tổng Writing trọng số cho một tác vụ. Tiêu chí thủ công và đánh giá AI riêng tác vụ vẫn dùng được mà không đổi chấm điểm/vòng đời nhà cung cấp.

Các thẻ lịch sử là **Theo kỹ năng**, **Luyện tập theo phạm vi**, **Theo đề**, **Theo bài thi thử**. Bản ghi theo phạm vi xuất hiện ở Luyện tập theo phạm vi thay vì Theo kỹ năng. Tiếp tục, Tiếp tục sau tạm dừng, Xem lại và Xóa lượt riêng dùng thao tác hiện có. Nhóm theo đề/Full Mock, xóa nhóm và phân tích toàn kỹ năng không đổi.

## Giai đoạn 3 — Phần Listening và khoảng âm thanh

Listening giữ một bản ghi tùy chọn trên mô-đun. Hai số nguyên có thể null `ListeningPart.audio_start_seconds` / `audio_end_seconds` xác định vị trí phần trong bản ghi; không tách hoặc nhân bản tệp để tạo đoạn phát. Migration `20261010_0022_listening_audio_ranges` kế tiếp `20261010_0021`. CHECK PostgreSQL cho phép cả hai null hoặc cả hai hiện diện với start >= 0 và end > start, gồm kiểm tra khác null rõ ràng. Nội dung cũ vẫn hợp lệ khi thiếu khoảng.

Trình soạn phần Builder lưu tên và cả hai biên cùng nhau qua cập nhật phần có kiểm tra revision hiện có. Nhập MM:SS, lấy vị trí phát tuyệt đối hiện tại hoặc xem trước đoạn đã chọn trong trình phát chung. Khoảng thiếu/sai định dạng, end <= start hoặc end vượt thời lượng trình duyệt biết chặn tự lưu/xem trước và giải thích. Thời lượng đến từ siêu dữ liệu âm thanh trình duyệt; backend kiểm cấu trúc khoảng mà không dò/chuyển mã âm thanh.

Thay/gỡ bản ghi chung bằng ID tài sản khác đặt lại mọi khoảng phần trong cùng giao dịch và tăng revision các phần bị ảnh hưởng. Gắn lại cùng ID giữ khoảng. Trình soạn cũ không thể khôi phục khoảng cũ sau thay thế. Nhân bản phiên bản và ZIP xuất/nhập giữ khoảng đồng thời ánh xạ lại ID phần; gói schema-v1 cũ không có trường tùy chọn này vẫn nhập được. Xuất bản toàn Listening không đòi khoảng phần.

Tóm tắt phiên bản công khai lộ UUID phần, thời gian đầu/cuối, số câu thật và boolean mô-đun `has_audio`, không lộ đường dẫn kho hoặc đáp án. Luyện kỹ năng cho khởi tạo phần riêng dù có bản ghi/khoảng hay không. Backend chứng minh đơn vị thuộc đúng mô-đun/phiên bản đã xuất bản và kiểm quy tắc phạm vi/bộ đếm thông thường; âm thanh là bổ sung tùy chọn, không phải điều kiện khởi tạo.

Listening theo phạm vi khởi tạo một LISTENING_PART qua API lượt làm bài hiện có với 10 / 15 / 20 phút hoặc đếm tăng (mặc định 10), rồi mở `/attempt/{id}`. Giao diện làm bài/xem lại chỉ nhận phần đã chọn. Khi có khoảng, phát dùng vị trí tuyệt đối trong nguồn nhưng hiển thị trục tương đối 00:00–độ dài đoạn; tua và nhảy nằm trong khoảng, tự dừng ở cuối, nút Phát chạy lại từ đầu. Đổi nguồn/đoạn dừng phát trước mà không tự phát. Khoảng sai hoặc ngoài thời lượng cho lỗi có cách xử lý, không tự rút ngắn rồi báo thành công. Hạn chế tua/tốc độ hiện có vẫn áp dụng.

Thiếu khoảng phần, trang làm bài/xem lại cho nghe toàn bản ghi và thông báo: “Chưa cấu hình khoảng âm thanh cho phần này. Bạn có thể nghe toàn bộ bản ghi.” Thiếu bản ghi, không hiển thị trình phát và thông báo: “Chưa đính kèm bản ghi. Bạn vẫn có thể làm câu hỏi và dùng bản ghi bên ngoài nếu cần.” Cả hai trường hợp vẫn có câu hỏi và vòng đời lượt làm bài thông thường.

Listening riêng toàn mô-đun, xem lại toàn Listening và Full Mock bỏ qua khoảng phần, tiếp tục dùng toàn bản ghi; Full Mock vẫn khóa tua. Xem lại/lịch sử theo phạm vi hiển thị điểm thô/tối đa, tỷ lệ chính xác một chữ số thập phân, không có band IELTS. Tạm dừng/tiếp tục, tự lưu, cờ, tô sáng và nộp dùng vòng đời hiện có. Ánh xạ band Listening toàn mô-đun không đổi. Phân tích lượt theo phạm vi vẫn ngoài phạm vi; giai đoạn này không đổi AI, lời nhắc chấm, phiên bản chấm hoặc nhà cung cấp.

## Nền tảng Giai đoạn 1 (giữ nguyên)

`AttemptContext` vẫn là STANDALONE / FULL_MOCK. `AttemptScope` độc lập là FULL_MODULE / FOCUSED_UNIT. Full Mock luôn tạo lượt FULL_MODULE, giữ thời lượng mô-đun đóng băng và thứ tự Listening → Reading → Writing.

Migration `20261010_0021_focused_attempt_scope` gán FULL_MODULE cho lượt lịch sử, thêm phạm vi không null và khóa ngoại RESTRICT có thể null tới `reading_passages`, `listening_parts`, `writing_tasks`. Ràng buộc yêu cầu đúng một đích khớp cho lượt theo phạm vi, không đích cho toàn mô-đun và FULL_MODULE khi có `test_session_id`. Hạ migration từ chối bỏ phạm vi khi còn bản ghi theo phạm vi, ngăn diễn giải lại lịch sử một phần.

Yêu cầu `POST /api/v1/attempts` hiện có có thể bỏ scope và vẫn tạo FULL_MODULE. Yêu cầu theo phạm vi thêm `scope: "FOCUSED_UNIT"` và đối tượng phân biệt loại `focused_unit` gồm `kind` (READING_PASSAGE / LISTENING_PART / WRITING_TASK), `id`. Máy chủ chứng minh đích thuộc đúng phiên bản đã xuất bản khả dụng và mô-đun. ID đích thiếu và thuộc đối tượng khác dùng cùng phản hồi lỗi an toàn.

DTO lượt làm bài/lịch sử trả `scope`, `focused_unit` (null cho toàn mô-đun). Siêu dữ liệu theo phạm vi gồm loại, ID, thứ tự gốc từ 0, nhãn `Passage N` / `Section N` / `Task N` và tên tùy chọn. Làm bài, tạm dừng và xem lại tái sử dụng siêu dữ liệu; máy khách không cần biết ba khóa ngoại lưu trữ.

`TimerRequest` chỉ kiểm cấu trúc: đếm ngược cần thời lượng dương, đếm tăng không có thời lượng. Chính sách khởi tạo lượt riêng tiếp đó kiểm bộ giá trị mô-đun/phạm vi:

| Phạm vi | Số phút đếm ngược |
| --- | --- |
| Toàn mô-đun | 40 / 50 / 60 / 70 |
| Một bài đọc Reading | 20 / 25 / 30 |
| Một phần Listening | 10 / 15 / 20 |
| Một tác vụ Writing | 20 / 25 / 30 / 35 / 40 |

Mọi phạm vi lượt riêng cũng hỗ trợ đếm tăng. Full Mock bỏ qua các bộ giá trị lượt riêng và tiếp tục dùng hợp đồng thời lượng mô-đun hiện có.

`AttemptScopeGuard` tập trung kiểm đơn vị/nhóm thuộc phạm vi, điều kiện chấm theo phạm vi và trình bày. Kiểm chủ sở hữu/phiên bản hiện có chạy trước kiểm phạm vi cho câu trả lời, cờ, lượt xem câu, điều hướng, tô sáng, phản hồi Writing, chấm tác vụ thủ công và điều kiện AI. Làm bài/xem lại chỉ trả đơn vị đã chọn; không gửi nội dung/đáp án khác rồi để máy khách ẩn. Âm thanh mô-đun Listening vẫn dùng chung; chỉ phát FOCUSED_UNIT mới áp biên phần.

Reading/Listening theo phạm vi lưu điểm thô/tối đa của câu đã chọn, band null kể cả đơn vị có đúng 40 câu. Hết hạn dùng cùng đường chấm. Tác vụ Writing theo phạm vi có thể giữ câu trả lời và điểm tiêu chí/tác vụ, nhưng band Writing cấp lượt vẫn null. Lời nhắc AI, hiệu chuẩn và phiên bản chấm không đổi.

Mục lịch sử thường chứa bản ghi theo phạm vi và scope. Ô toàn mô-đun theo đề cùng phân tích hiện có loại lượt theo phạm vi. Giai đoạn 2 thêm màn lịch sử riêng đã mô tả mà không thêm phân tích lượt theo phạm vi.

## Xác minh

Giai đoạn 2 thêm kiểm thử hợp đồng trình bày/lịch sử và Vitest cho thẻ luyện tập, bộ đếm/khởi tạo, điều hướng được bảo vệ, giao diện làm bài/xem lại theo phạm vi, chốt tạm dừng và thao tác lịch sử. Hồi quy toàn kỹ năng, Full Mock, xóa và đánh giá AI dùng kiểm thử hiện có. Xác minh dùng PostgreSQL cô lập, API frontend giả lập, kiểm tra kiểu và Ruff/ESLint có mục tiêu, không suy luận trực tiếp.

Giai đoạn 3 thêm kiểm migration/ràng buộc thật, lưu khoảng/revision/đặt lại, nhân bản và ZIP khứ hồi cũ/hiện hành, tóm tắt công khai an toàn, điều kiện khởi tạo và làm bài/xem lại theo phạm vi. Vitest bao phủ hàm MM:SS, phát trong giới hạn, Builder lấy vị trí/xem trước/tự lưu/xung đột/đặt lại, thẻ Listening/bộ đếm/khởi tạo, giao diện theo phạm vi/toàn mô-đun/Full Mock, xem lại và tạm dừng. Kiểm thử dùng siêu dữ liệu âm thanh tổng hợp, API giả lập; không dùng trình duyệt, E2E hoặc dịch vụ âm thanh/mô hình trực tiếp.

Lệnh xác minh tập trung Giai đoạn 3 (backend với PostgreSQL cô lập đã migration):

```powershell
# backend/
uv run pytest tests/test_listening_audio_ranges.py tests/test_focused_attempts.py tests/test_focused_scope_migration.py tests/test_focused_attempt_contract.py tests/test_api_contract.py tests/test_listening.py tests/test_asset_cloning.py tests/test_transfer.py tests/test_full_mock_sessions.py -q --tb=line
# frontend/
npx vitest run tests/listening-audio-ranges.test.tsx tests/listening-player.test.tsx tests/listening-navigation.test.tsx tests/focused-listening-review.test.tsx tests/skill-practice.test.tsx tests/practice-library.test.tsx tests/focused-reading-review.test.tsx tests/reading-navigation.test.tsx tests/writing-review.test.tsx tests/attempt-page.test.tsx tests/attempt-history-list.test.tsx tests/focused-attempt-contract.test.ts tests/history-api.test.ts
npm run typecheck
```

Ruff kiểm mã/định dạng và ESLint bao phủ tệp Python/TypeScript mới hoặc sửa. `git diff --check` bao phủ toàn thay đổi.

Lệnh xác minh Giai đoạn 1:

Đã chạy trên PostgreSQL cô lập được migration bằng `uv run alembic
upgrade head`. Kiểm migration thực thi DDL nâng/hạ thật trong ranh giới hoàn tác; không thay migration bằng lược đồ tạo từ siêu dữ liệu.

Từ `backend/`:

```powershell
uv run pytest tests/test_focused_attempts.py tests/test_focused_scope_migration.py tests/test_focused_attempt_contract.py tests/test_timer.py tests/test_attempt_state_machine.py tests/test_attempt_scoring_history.py tests/test_attempt_pause.py tests/test_writing_attempts.py tests/test_full_mock_sessions.py tests/test_analytics.py -q
uv run pytest tests/test_focused_attempts.py tests/test_lifecycle_refactor.py::test_generic_highlights_and_bulk_delete tests/test_lifecycle_refactor.py::test_text_completion_layout_and_answers_round_trip tests/test_lifecycle_refactor.py::test_archived_test_blocks_new_attempt_and_restore_allows_it tests/test_listening.py::test_listening_review_returns_saved_question_highlights tests/test_full_mock_history_delete.py tests/test_attempt_deletion.py tests/test_writing_ai.py -q
```

Từ `frontend/`:

```powershell
npx vitest run tests/focused-attempt-contract.test.ts tests/history-api.test.ts tests/attempt-lifecycle.test.ts tests/attempt-page.test.tsx tests/writing-review.test.tsx
npm run typecheck
npx eslint src/lib/api/attempts.ts src/lib/api/history.ts tests/focused-attempt-contract.test.ts
```

Ruff kiểm mã/định dạng bao phủ tệp Python đã sửa; `git diff --check` bao phủ toàn thay đổi. Không dùng xác minh trình duyệt, E2E, mô hình trực tiếp hoặc triển khai.
