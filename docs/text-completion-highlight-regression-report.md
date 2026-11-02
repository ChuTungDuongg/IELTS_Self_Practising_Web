# Báo cáo hồi quy Text Completion và highlight

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Báo cáo hồi quy Text Completion và highlight. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../frontend/src/features/questions/text-completion-canvas.tsx).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/reading-listening.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


Triển khai trên working tree hiện có tại HEAD `2d4d7c0`. Giữ thay đổi block câu, preview và điều hướng Reading trước đó. Không reset, migration hoặc commit.

## Phát hiện và cách sửa

1. **Nguyên nhân phải click nhiều lần trong editor.** Vùng editor trắng lớn là container không sửa được và không có hành vi focus khi bấm khoảng trắng. Chỉ từng span TEXT nhận nhập liệu, kể cả span rỗng rất nhỏ.
2. **Vòng đời con trỏ.** Key ổn định không ngăn React đối soát text child thay đổi trong `contentEditable`. Mỗi input còn chuẩn hóa segment, xóa segment rỗng và có thể gộp mất định danh segment active. Span thường không rỗng không nhất thiết mount lại, nhưng đối soát văn bản/chuẩn hóa cấu trúc có thể làm gián đoạn selection.
3. **Kiến trúc soạn thảo.** Span `EditableText` ổn định để trình duyệt quản lý text node/selection. Layout effect chỉ đồng bộ khi văn bản DOM khác model. Input cập nhật `segment.text` không chuẩn hóa cấu trúc. Click khoảng trắng focus cuối segment TEXT cuối; chỉ tạo segment cuối sửa được khi cấu trúc cần. Câu chỉ có một text rỗng có vùng bấm toàn chiều rộng. Click trực tiếp văn bản giữ vị trí con trỏ native. Thao tác cấu trúc xóa tham chiếu con trỏ cũ; thêm/tách focus một lần sau render, không timer.
4. **Nguyên nhân Q?.** GAP tham chiếu UUID Question không tồn tại. Đánh số hiển thị không sửa được. Mã cập nhật Reading cũ tạo câu ORM không truyền `id` gửi lên; commit hiện có mới nhất đã sửa. Giữ và xác minh sửa đó.
5. **Điểm lệch vòng đời chính xác.** Đường Reading cũ và Listening vẫn lỗi: thêm câu khi cập nhật nhóm vượt xác minh bằng UUID gửi lên, nhưng ORM tạo UUID khác trong khi tham chiếu GAP JSONB giữ UUID gửi lên. Clone phiên bản còn cấp ID câu mới nhưng không ánh xạ lại GAP đã sao chép. Chuẩn hóa frontend làm draft lỗi nặng hơn khi bỏ câu không khớp.
6. **Định danh câu hỏi.** Reading create/update giữ hành vi ID gửi lên hiện có. Listening update nay truyền ID gửi lên tường minh cho câu mới. Chuẩn hóa hiện đại giữ ID được cấp; số hiển thị/thứ tự không tạo định danh.
7. **Định danh GAP.** Save/refetch giữ GAP ID/tham chiếu câu. Phiên bản mới phải có khóa chính câu khác; clone nay áp ánh xạ UUID cũ-sang-mới tường minh cho `question_id` có cấu trúc, không sửa phiên bản nguồn đóng băng. Chỉ clone phiên bản dùng ánh xạ này.
8. **Xác minh lưu.** Builder phát hiện liên kết GAP thiếu/chưa giải quyết, câu mồ côi, tham chiếu trùng, định danh câu trùng/thiếu, định danh block/segment trùng/thiếu. Hiện lỗi dễ đọc và chặn Save. Chuẩn hóa thứ tự giữ nội dung sai thay vì bỏ.
9. **Draft lỗi đã có.** Không tự đoán nối lại. Tác giả có thể nối GAP chọn với câu còn sống chưa liên kết, thêm GAP thiếu cho câu còn sống hoặc tạo đáp án thay cho GAP đã mất câu. Thay thế cần cấu hình tác giả; không thể dựng lại đáp án đã xóa. Bố cục hiện đại cố ý rỗng không còn bị coi là nội dung cũ dựa prompt.
10. **Nguyên nhân HTML sai.** `SelectableText` render dialog dạng block trong span inline của nó, vốn có thể nằm trong đoạn văn `QuestionHeader`.
11. **Sửa portal.** Dialog tạo/xóa đều dùng `createPortal(..., document.body)`. Cây chọn văn bản chỉ chứa nội dung an toàn inline. Header dạng đoạn giữ ngữ nghĩa. Wrapper label/paragraph liên quan trong matching/render văn bản cũ được sửa cục bộ.
12. **An toàn SSR và tương tác.** Trạng thái dialog ban đầu null cả server/client đầu; có bảo vệ `document`, chỉ tạo portal sau tương tác. Giữ vị trí cố định theo viewport. Ref portal giữ xử lý click trong/ngoài, Escape, đóng peer, nút pending và lỗi API. Cuộn/resize đóng vị trí cũ. Chỉ chọn văn bản không lưu highlight.

## Tệp đổi trong nhiệm vụ này

Mã ứng dụng:

- `frontend/src/features/questions/text-completion-canvas.tsx`
- `frontend/src/features/questions/text-completion-integrity.ts` (mới)
- `frontend/src/features/test-builder/question-group-editor.tsx`
- `frontend/src/features/highlighting/selectable-text.tsx`
- `frontend/src/features/questions/renderers.tsx`
- `frontend/src/app/globals.css`
- `backend/app/domains/questions/normalization.py`
- `backend/app/services/listening.py`
- `backend/app/services/tests.py`

Kiểm thử hồi quy:

- `frontend/tests/text-completion-canvas.test.tsx`
- `frontend/tests/selectable-text.test.tsx`
- `backend/tests/test_completion_identity.py` (mới)

Thay đổi chưa commit hiện có ở Reading runner/navigation, draft preview và kiểm thử tương ứng vẫn giữ. Đã kiểm toán `editors.tsx`, question types/registry, DTO, lưu trữ/chuẩn hóa Reading, Reading review, render passage và hướng dẫn nhóm. Không chuyển quy tắc nghiệp vụ sang React.

## Kiểm thử và kết quả

Kiểm thử mới kiểm text-node/định danh con trỏ ổn định khi sửa giữa, focus khoảng trắng/rỗng, tạo text cuối, giữ dữ liệu lỗi/chặn lưu, nối lại tường minh, đáp án thay thế, mở lại đích đáp án UUID, cả hai portal body dưới đoạn TFNG thật, markup SSR, cảnh báo lồng console, tạo/xóa, lỗi API, click trong/ngoài, Escape, đóng peer và đóng khi cuộn. PostgreSQL kiểm Reading/Listening create/update/refetch/reorder giữ ID, đáp án thay thế được chấp nhận, phân biệt hoa/thường và giới hạn số. Clone kiểm ánh xạ liên kết/cấu hình nguồn không đổi.

| Kiểm tra | Kết quả cuối |
| --- | --- |
| Frontend `npm test` | 116 đạt trên 19 tệp |
| `npm run lint` | Đạt |
| `npm run typecheck` | Đạt |
| `npm run build` | Đạt, tạo mọi tuyến |
| Backend toàn bộ `pytest -q` | 103 đạt, gồm tích hợp PostgreSQL |
| Ruff `check app tests` | Đạt |
| `git diff --check` | Đạt |

Ca khôi phục câu bị mất bổ sung được quan sát thất bại trước vì thiếu hành động, rồi đạt sau triển khai. Kiểm thử dùng timer thật; không có tiến trình treo cần kết thúc cưỡng bức.

## Xác minh bằng trình duyệt đang chạy

Dùng frontend/backend người dùng đang chạy và tạo bài Local hư cấu **Completion regression QA**.

- Click một lần trong câu, gõ ngay; `m|jor` + `a` tạo `major`.
- Click một lần bề mặt câu rỗng nhận gõ ngay.
- Insert GAP hiện Q2 ngay và mở đúng điều khiển đáp án.
- Save, reload toàn trang, mở lại giữ UUID hai câu và liên kết GAP; không có Q?.
- Đáp án đúng `major`, thay thế `important`, chấm phân biệt hoa/thường, tối đa 3 từ và 2 số còn nguyên sau reload. Edit answer vẫn phân giải theo UUID.
- Clone phiên bản QA đã publish thành draft v2. GAP trỏ UUID câu của phiên bản mới. Đổi thứ tự câu, lưu, reload toàn bộ, xác nhận thứ tự mới và liên kết UUID/đáp án draft gốc.
- Bắt đầu Reading attempt, chọn văn bản header TFNG, mở dialog tạo. Kiểm DOM đang chạy xác nhận `parentElement.tagName === BODY`, không có tổ tiên paragraph.
- Chọn văn bản giữ số highlight bằng không; click Highlight đổi thành một. Reload giữ highlight đã lưu.
- Mở tùy chọn xóa; kiểm DOM lại thấy portal body. Escape/click ngoài đóng. Remove highlight trả số lượng về không.
- Luồng highlight được thử không có cảnh báo lồng sai/hydration. Tab attempt mở lại mới ghi không lỗi console. Lỗi build mã hóa nguồn tạm trước đó trong phát triển đã sửa trước kiểm cuối.

## Hành vi giữ nguyên và giới hạn

Giữ mỗi câu một block, xác nhận thêm/đổi thứ tự/xóa câu, bố cục PASSAGE, điều hướng dưới/cờ Reading và không có gợi ý kỹ thuật từng gap ở Candidate/Preview/Review. PostgreSQL vẫn có thẩm quyền; giữ tách đáp án bài đang làm, phiên bản publish bất biến, đánh giá server và offset highlight ngữ nghĩa.

Không thể tự suy ra/khôi phục nội dung đáp án đã mất. Định danh block/segment trùng làm hỏng cấu trúc được phát hiện/chặn thay vì âm thầm viết lại. Xác minh trình duyệt dùng Chromium; chưa thử riêng trình duyệt khác/IME. Người rà soát độc lập phát hiện lỗi khôi phục câu bị mất trên; đã sửa/kiểm thử, nhưng không hoàn tất kết luận toàn bộ vì chạm giới hạn sử dụng.

Fixture QA hư cấu vẫn còn Local: published v1, draft v2 và Reading attempt. Không sửa nội dung test hiện có người dùng. Thay đổi chưa commit để rà soát.
