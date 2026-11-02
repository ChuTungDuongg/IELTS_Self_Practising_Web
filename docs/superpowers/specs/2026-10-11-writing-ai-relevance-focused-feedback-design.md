# Cổng kiểm tra liên quan Writing AI và ảnh chụp phản hồi luyện tập tập trung

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Cổng kiểm tra liên quan Writing AI và ảnh chụp phản hồi luyện tập tập trung. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/services/mts_writing.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Ngày: 2026-10-11

Trạng thái: Hướng đã được phê duyệt, chỉ là đặc tả

Kho mã được kiểm tra: `ChuTungDuongg/IELTS_Self_Practising_Web`

Mốc cơ sở: `d152f3675fbf4a96c2e34d0831fcb45049ba0858` — `Improve Task 1 coherence and cohesion calibration`

Tài liệu định nghĩa hai thay đổi Writing AI phối hợp: cổng kiểm tra mức liên quan tương thích IELTS cho Task 1/Task 2 và ảnh chụp phản hồi AI tư vấn thuộc người dùng cho luyện Writing tập trung. Tài liệu không triển khai thay đổi nào. Chấm thủ công/chính thức hiện có tiếp tục là nguồn chuẩn.

## 1. Mục tiêu

1. Phát hiện câu trả lời hoàn toàn không liên quan đề Writing trước khi tiêu tốn toàn bộ luồng đánh giá TA/TR.
2. Giữ độc lập tiêu chí IELTS: câu hoàn toàn không liên quan nhận Task Achievement/Task Response Band 1.0, còn CC, LR, GRA tiếp tục đánh giá từ ngôn ngữ thực sự đã viết.
3. Khi phân loại liên quan không chắc chắn hoặc lỗi, tiếp tục luồng bình thường (fail-open), để cổng không chắc chắn tuyệt đối không rút ngắn sai đánh giá câu hợp lệ.
4. Cho USER thường làm Writing `FOCUSED_UNIT` lưu một ảnh chụp AI tư vấn mới nhất mỗi task gồm bốn điểm tiêu chí AI và phản hồi từng tiêu chí.
5. Giữ ảnh chụp cá nhân hoàn toàn tách biệt `AttemptWritingScore`, band Writing chính thức, History/Analytics chính thức và luồng ADMIN sao chép vào biểu mẫu thủ công hiện có.

## 2. Ngoài phạm vi

- Không có quy tắc `0/0/0/0` cho bài lạc đề.
- Không thêm nguồn điểm IELTS chính thức và không cấp USER quyền ghi điểm Writing thủ công/chính thức.
- Không tự sao chép điểm AI vào `AttemptWritingScore`.
- Không phạt CC, LR hoặc GRA theo mức liên quan.
- Không có bộ phát hiện gian lận, đạo văn, học thuộc hoặc tác giả tổng quát.
- Không thêm quy tắc câu trả lời 20 từ trở xuống trong phần này; quy tắc mô tả đó độc lập cổng liên quan.
- Không bỏ phiếu mô hình, giám khảo chấm thứ hai hoặc thiết kế lại hiệu chỉnh tổng thể.
- Không tự ghi đè ảnh chụp cá nhân đã lưu sau chấm lại; thay thế yêu cầu người dùng chủ động lưu.
- Phiên bản đầu không có bảng lịch sử ảnh chụp hoặc giao diện xóa.

## 3. Kiến trúc hiện có ràng buộc thiết kế

Dịch vụ Task 2 hiện chạy bốn luồng tiêu chí bằng chứng → chấm điểm độc lập qua `MTSWritingScoringService`; lỗi một tiêu chí ngăn tổng hợp nhưng giữ kết quả tiêu chí đã hoàn tất. Task 1 kế thừa dịch vụ: CC/LR/GRA có thể chạy độc lập khi TA chờ đối chiếu hình ảnh, hòa giải chuyên gia biểu đồ tùy chọn, dữ kiện xác định và xác minh phát biểu.

`writing_ai_grading_runs` đã sở hữu kết quả AI hoàn tất bất biến, danh tính nhà cung cấp/mô hình/prompt, dấu vân tay đầu vào, mức sử dụng, chẩn đoán và lịch sử sự kiện. Worker lưu tiến độ tiêu chí từng phần, chỉ hoàn thành lượt khi đủ bốn tiêu chí.

`WritingAIAssessment` đã hỗ trợ `Chép gợi ý AI vào biểu mẫu` chỉ ADMIN; `WritingReviewView.copyAISuggestions` chép điểm/phản hồi AI vào biểu mẫu chấm thủ công cục bộ, còn API lưu thủ công hiện có tiếp tục được `AdminUser` bảo vệ.

Luyện tập tập trung được biểu diễn bởi `Attempt.scope == FOCUSED_UNIT` đã lưu cùng `focused_writing_task_id`; `AttemptScopeGuard` đã kiểm tra task Writing được chọn thuộc lượt tập trung.

Tái sử dụng các ranh giới hiện có này, không bỏ qua chúng.

## 4. Hợp đồng mức liên quan

Thêm schema nghiêm ngặt nhỏ dùng chung điều phối Task 1/Task 2:

```text
RelevanceVerdict = ON_TOPIC | PARTIALLY_RELEVANT | WHOLLY_UNRELATED
RelevanceConfidence = HIGH | MEDIUM | LOW

WritingRelevanceAssessment
- verdict
- confidence
- source_ids: up to 4 stable essay segment IDs
- reason: concise Vietnamese explanation
```

Bộ phân loại dựa trên bằng chứng: mọi `source_id` trả về phải phân giải được tới cùng đoạn `P#S#` ổn định mà chấm điểm đang dùng. Backend phân giải ID; mô hình không cần chép lại trích dẫn.

Chỉ chính xác điều kiện này mới được rút ngắn luồng TA/TR:

```text
verdict == WHOLLY_UNRELATED
AND confidence == HIGH
```

`WHOLLY_UNRELATED + MEDIUM/LOW`, JSON không hợp lệ, ID nguồn không biết, lỗi nhà cung cấp, hết thời gian, lỗi ngữ cảnh hoặc mọi lỗi xác thực đều fail-open, tiếp tục luồng TA/TR bình thường hiện có.

Vì vậy trạng thái liên quan lưu trữ/công khai phân biệt kết quả thô bộ phân loại với việc thực sự áp dụng rút ngắn luồng hay không.

## 5. Ngữ nghĩa liên quan và bảo vệ khỏi kết luận sai

`WHOLLY_UNRELATED` chỉ dành câu trả lời có nội dung truyền đạt hoàn toàn không đề cập yêu cầu đề. Cổng không được dùng nhãn này chỉ vì câu yếu, chưa đầy đủ hoặc không chính xác.

Các trường hợp sau vẫn là `ON_TOPIC` hoặc `PARTIALLY_RELEVANT` và phải tiếp tục chấm bình thường:

- Task 2 trả lời chủ đề nhưng bỏ một yêu cầu, chỉ bàn một phía, quan điểm yếu/không rõ, phát triển ý kém, có chi tiết lan man hoặc hiểu sai một phần câu hỏi.
- Task 1 cố mô tả hình được cung cấp nhưng thiếu tổng quan, chọn đặc điểm chính yếu, báo sai số/xu hướng, bỏ so sánh quan trọng, ngắn, tổ chức kém hoặc yếu ngôn ngữ.
- Câu trả lời có một hay nhiều đoạn lạc đề nhưng vẫn giải quyết đáng kể yêu cầu đề.
- Bộ phân loại không chắc cách diễn đạt lại hoặc bàn gián tiếp có liên quan hay không.

Ví dụ thật sự `WHOLLY_UNRELATED` gồm biểu đồ CO2 Task 1 được trả bằng bài học ngoại ngữ, hoặc đề tái chế Task 2 được trả hoàn toàn bằng câu chuyện du lịch không liên quan.

Prompt phải ưu tiên rõ `PARTIALLY_RELEVANT` hơn `WHOLLY_UNRELATED` khi còn liên hệ có ý nghĩa với đề hoặc bằng chứng mơ hồ. Không được suy luận học thuộc hoặc gian lận.

## 6. Điều phối Task 2

Task 2 có thể chạy liên quan đồng thời CC/LR/GRA để tránh cộng độ trễ cổng vào phản hồi ngôn ngữ:

```text
prompt + essay
├─ relevance classification
├─ CC evidence → score
├─ LR evidence → score
└─ GRA evidence → score
```

Nếu liên quan không đạt điều kiện rút ngắn có độ tin cậy cao, chạy luồng bằng chứng → chấm TR (`ta`) hiện có không đổi.

Nếu liên quan là `WHOLLY_UNRELATED + HIGH`:

- không gửi yêu cầu bằng chứng TR hoặc chấm TR;
- tạo `CriterionResult` xác định cho `ta` với điểm `1.0`;
- phản hồi nêu bằng tiếng Việt rằng câu trả lời hoàn toàn không liên quan đề, do đó phù hợp hồ sơ Task Response Band 1 chính thức được cung cấp;
- điểm mạnh/cải thiện giữ thuần tiêu chí và ngắn gọn;
- bằng chứng phân giải từ ID nguồn đại diện hợp lệ của bộ phân loại nếu có;
- phát sự kiện tiến độ/hoàn thành tiêu chí bình thường để lượt vẫn là kết quả bốn tiêu chí đầy đủ cấu trúc;
- tiếp tục CC/LR/GRA bình thường, tính tổng tư vấn bằng tổng hợp trọng số đều hiện có.

Đây là áp dụng mô tả, không phải phạt số hoặc trần điểm. Prompt band thấp Task 2 hiện có đã nêu nội dung hoàn toàn không liên quan phù hợp Task Response Band 1 và tiêu chí được đánh giá độc lập.

## 7. Điều phối Task 1

Liên quan Task 1 cần ngữ cảnh đề hình ảnh, nhưng phiên bản đầu không được thêm lần gọi ảnh/VLM thứ hai chỉ để kiểm tra liên quan.

Dùng đầu ra đối chiếu hình ảnh chính hiện có làm ngữ cảnh đề có cấu trúc:

```text
image + prompt
  → existing primary visual grounding
  → structured VisualReference
  → text-only relevance classification(prompt + compact visual context + essay)
```

CC/LR/GRA giữ độc lập và có thể tiếp tục đồng thời.

Nếu không áp dụng rút ngắn liên quan, giữ chính xác luồng TA Task 1 hiện tại: hòa giải chuyên gia tùy chọn, dữ kiện xác định, trích xuất/xác minh phát biểu, bằng chứng TA và chấm TA.

Nếu xác nhận `WHOLLY_UNRELATED + HIGH` sau đối chiếu chính dùng được:

- TA thành Band `1.0` xác định theo hồ sơ Task 1 Band 1 hiện có (`no relevant report content`);
- bỏ trích xuất phát biểu TA, xác minh phát biểu, suy dữ kiện xác định, DePlot/chuyên gia biểu đồ tùy chọn, bằng chứng TA và chấm TA;
- CC/LR/GRA tiếp tục bình thường;
- metadata đối chiếu hình ảnh Task 1 vẫn có vì đã cung cấp ngữ cảnh đề liên quan;
- không tạo mâu thuẫn dữ kiện giả vì luồng bỏ qua không so sánh phát biểu bài không liên quan với dữ kiện biểu đồ.

Nếu đối chiếu hình ảnh chính không dùng được, kiểm tra liên quan không thể an toàn kết luận bài hoàn toàn không liên quan hình. Fail-open sang hành vi Task 1 hiện có; không suy Band 1 chỉ từ đề văn bản nếu ý nghĩa đề phụ thuộc đáng kể hình.

Với nhóm Task 1 không phải biểu đồ, áp dụng cùng cách tham chiếu hình ảnh có cấu trúc.

## 8. Hành vi nhà cung cấp liên quan, sửa đầu ra và ngân sách

Tạo một hàm hoàn tất có cấu trúc chỉ văn bản, có giới hạn cho liên quan thay vì nhúng logic vào từng bộ chấm tiêu chí. Tái sử dụng trừu tượng nhà cung cấp, hành vi `temperature=0`/seed xác định và giới hạn đồng thời cấp lượt hiện có.

Tương tác liên quan phải:

- coi đề, bài viết và dữ liệu hình ảnh có cấu trúc là dữ liệu không tin cậy;
- chỉ trả hợp đồng JSON liên quan nghiêm ngặt;
- dùng ngân sách đầu ra riêng nhỏ vì schema rất gọn;
- tối đa một lần sửa có mục tiêu cho đầu ra nhà cung cấp sai định dạng/không hợp lệ;
- tuyệt đối không biến lỗi liên quan thành lỗi cả lượt;
- ghi chẩn đoán/độ trễ/mức sử dụng an toàn, không chứa nội dung mô hình thô.

Bộ phân loại đã sửa hoặc lỗi vẫn theo cùng quy tắc rút ngắn độ tin cậy cao. Không thêm lần gọi thứ ba.

## 9. Lưu trữ liên quan, sự kiện và danh tính cache

Mở rộng kết quả lượt AI công khai/lưu trữ bằng metadata liên quan tùy chọn. Lượt lịch sử thiếu trường vẫn đọc được.

Cấu trúc kết quả khuyến nghị:

```text
relevance:
  verdict
  confidence
  reason
  evidence
  short_circuit_applied: boolean
```

Lưu liên quan trong `result_json`, không trong bảng quan hệ mới. Nó thuộc một lượt AI và bất biến cùng lượt đó.

Chỉ thêm hoạt động/sự kiện riêng liên quan tại nơi giúp tiến độ trực tiếp rõ hơn, ví dụ `relevance.started`, `relevance.completed` và `relevance.failed`; sự kiện lỗi nghĩa là fail-open, không lỗi lượt. Không dùng sai `criterion.failed` cho giai đoạn phụ này.

Vì liên quan có thể đổi luồng thực thi/kết quả tiêu chí, prompt/hợp đồng ngữ nghĩa của nó phải tham gia danh tính cache AI. Tăng phiên bản prompt/fingerprint tổng hợp Task 2/Task 1 khi triển khai; không đổi hợp đồng tri giác Task 1 không thay đổi chỉ vì cổng liên quan văn bản.

Lượt hoàn tất lịch sử giữ phiên bản cũ và vẫn hiển thị được.

## 10. Điểm tổng tư vấn cho câu hoàn toàn không liên quan

Câu hoàn toàn không liên quan với độ tin cậy cao vẫn tạo đủ bốn kết quả tiêu chí:

```text
TA/TR = 1.0
CC    = normal assessment
LR    = normal assessment
GRA   = normal assessment
```

Phép tính trọng số đều hiện có tính điểm tổng task tư vấn. Không thêm ghi đè tổng hợp đặc biệt.

Giá trị này chỉ là đầu ra AI tư vấn. Bản thân nó tuyệt đối không cập nhật `AttemptWritingScore`, `Attempt.band_score`, History hoặc Analytics chính thức.

## 11. Lưu phản hồi cá nhân cho luyện tập tập trung

Thêm bảng/mô hình riêng cho ảnh chụp tư vấn USER đã lưu, ví dụ `writing_ai_practice_feedback`.

Các cột bắt buộc:

```text
id
user_id
attempt_id
writing_task_id
source_ai_run_id

ta_score
ta_feedback
cc_score
cc_feedback
lr_score
lr_feedback
gra_score
gra_feedback

created_at
updated_at
```

Dùng cùng ràng buộc nửa band như điểm tiêu chí AI. Phản hồi dùng cột văn bản có giới hạn hoặc lưu trữ xác thực tương đương, nhất quán giới hạn phản hồi tiêu chí hiện có.

Bất biến cơ sở dữ liệu:

- duy nhất `(user_id, attempt_id, writing_task_id)` để có một ảnh chụp mới nhất;
- xóa `attempt_id` lan truyền tới ảnh chụp;
- xóa `user_id` lan truyền;
- `source_ai_run_id` tham chiếu lượt nguồn, không được âm thầm trỏ sang lượt làm/task khác;
- `writing_task_id` phải là task Writing thực.

Không lưu trùng giá trị tổng; có thể suy từ bốn điểm tiêu chí nếu giao diện muốn hiển thị trung bình task tư vấn.

Lưu chủ động lần hai cùng người/lượt/task cập nhật hàng hiện có và `source_ai_run_id`; không nối lịch sử.

## 12. Phân quyền ảnh chụp cá nhân

USER thường đã xác thực chỉ được lưu/đọc ảnh chụp khi mọi điều kiện sau đúng:

1. lượt làm thuộc người dùng hiện tại đó;
2. mô-đun lượt làm là Writing;
3. `attempt.scope == FOCUSED_UNIT`;
4. `focused_writing_task_id == requested writing_task_id`;
5. lượt AI nguồn thuộc cùng lượt làm và task;
6. lượt AI nguồn được cùng người dùng yêu cầu và là `COMPLETED`;
7. lượt nguồn có kết quả đủ bốn tiêu chí đã xác thực.

Frontend chỉ cung cấp `source_run_id`. Tuyệt đối không cung cấp điểm tiêu chí/phản hồi để lưu. Backend sao chép kết quả lượt hoàn tất đã xác thực vào ảnh chụp, ngăn người dùng giả điểm AI tư vấn bằng sửa nội dung yêu cầu.

Từ chối Writing toàn mô-đun, Full Mock Writing, lượt người khác, task khác, lượt đang hoạt động/thất bại và kết quả lịch sử sai định dạng.

Chấm thủ công ADMIN vẫn riêng. `PUT /attempts/{attempt_id}/writing-scores/{writing_task_id}` hiện có tiếp tục chỉ `AdminUser`, không tái dùng cho ảnh chụp cá nhân.

## 13. API ảnh chụp cá nhân

Giữ tài nguyên dưới nhóm tuyến Writing AI hiện tại:

```text
GET /attempts/{attempt_id}/writing/{writing_task_id}/ai-practice-feedback
PUT /attempts/{attempt_id}/writing/{writing_task_id}/ai-practice-feedback
```

Nội dung `PUT`:

```json
{"source_run_id":"<uuid>"}
```

Phản hồi chứa ID lượt nguồn, bốn cặp điểm/phản hồi đã lưu và thời gian. GET trả cấu trúc cho phép null hoặc phản hồi không tìm thấy nhất quán kho mã; triển khai cần chọn một quy ước và dùng thống nhất ở frontend. Ưu tiên phản hồi null nếu tránh phải xử lý lỗi dự kiến cho trạng thái phổ biến “chưa lưu”.

Phiên bản này không yêu cầu endpoint DELETE.

## 14. Tích hợp DTO xem lại

Không gộp phản hồi tư vấn cá nhân vào `WritingTaskScore`. DTO đó biểu diễn ngữ nghĩa điểm/phản hồi thủ công/chính thức hiện có.

Có thể thêm trường `ai_practice_feedback` tùy chọn vào DTO task xem lại Writing tập trung, hoặc để `WritingAIAssessment` tải tài nguyên riêng. Ưu tiên API Writing AI riêng khi tránh mở rộng hợp đồng xem lại chung cho lượt không tập trung.

Dù chọn cách trình bày nào, thiếu ảnh chụp không được ảnh hưởng tải trang xem lại.

## 15. Hành vi frontend

`WritingAIAssessment` nhận đủ ngữ cảnh phạm vi lượt làm và vai trò để chọn thao tác rõ ràng.

Hành vi ADMIN giữ nguyên:

```text
Chép gợi ý AI vào biểu mẫu
→ copy score + criterion feedback into local manual form
→ admin may edit
→ explicit Save Task N scores
→ official/manual score
```

Hành vi USER tập trung trở thành:

```text
Lưu nhận xét AI vào bài luyện
→ PUT source_run_id
→ save latest personal snapshot
→ advisory only
```

Sau khi có ảnh chụp đã lưu, ghi nhãn thao tác `Cập nhật nhận xét AI đã lưu` khi lượt hoàn tất đang hiển thị khác lượt nguồn đã lưu. Chỉ chấm lại không ghi đè ảnh chụp.

Hiển thị thẻ riêng như `Nhận xét AI đã lưu`, chứa điểm + phản hồi TA/TR, CC, LR, GRA, thời gian lượt nguồn/cập nhật và nhãn rõ `Tham khảo · Không phải điểm chính thức`.

USER thường trong xem lại toàn mô-đun/full-mock không có khả năng chép biểu mẫu ADMIN hoặc lưu cá nhân tập trung. Quyền xem/chấm lại AI hiện có ngoài ra giữ nguyên.

Nếu lượt nguồn chứa kết quả hoàn toàn không liên quan với độ tin cậy cao, thẻ đã lưu có thể hiển thị giải thích từ lượt nguồn; không sao chép metadata liên quan vào bảng ảnh chụp.

## 16. Xử lý lỗi và đồng thời

Upsert ảnh chụp cá nhân phải trong giao dịch. Lưu trùng đồng thời hội tụ về một hàng duy nhất; không tạo bản ghi ảnh chụp trùng.

Nếu lượt nguồn yêu cầu hoàn thành hoặc đổi trạng thái giữa hiển thị frontend và lưu, backend kiểm tra lại hàng lượt bền vững. Chỉ được sao chép kết quả hoàn tất bền vững.

Lưu phản hồi cá nhân tuyệt đối không bắt đầu suy luận, không đổi lượt nguồn và không đổi điểm chính thức.

Lỗi liên quan là lỗi phụ fail-open. Lỗi chấm giữ ngữ nghĩa thất bại tiêu chí/lượt hiện có sau quyết định cổng.

Hành vi hủy giữ nguyên: tháo thẻ task chỉ dừng quan sát; thao tác Stop chủ động hủy lượt backend.

## 17. Ranh giới prompt/phiên bản

Ngữ nghĩa liên quan thay đổi hành vi chấm, nên phiên bản cache production phải đổi khi triển khai.

Task 1:

- tăng phiên bản prompt/fingerprint tổng hợp Task 1 và phiên bản ngữ nghĩa chấm/liên quan phù hợp;
- giữ `TASK1_VISUAL_CONTRACT_VERSION = mts-task1-visual-v3` trừ khi chính schema hình ảnh/hướng dẫn tri giác đổi;
- giữ hướng dẫn hiệu chỉnh TA/CC v7 hiện có.

Task 2:

- tăng hợp đồng prompt Task 2 có hiệu lực để lượt cache cũ thiếu liên quan không thể giả là hành vi mới;
- giữ rubric/phạm vi tiêu chí, trừ tích hợp tối thiểu cần để cung cấp kết quả rút ngắn liên quan.

Không thêm thưởng, phạt, độ lệch, sàn hoặc trần điểm ngoài trường hợp Band 1 xác định theo mô tả cho câu hoàn toàn không liên quan độ tin cậy cao.

## 18. Chiến lược kiểm thử

Triển khai phải dùng TDD có trọng tâm và chỉ kiểm thử chi phí thấp; tính năng không yêu cầu chạy trình duyệt, Playwright, mô hình thật, GPU, Modal hoặc triển khai.

Kiểm thử hợp đồng backend cần bao quát ít nhất:

1. Task 2 `ON_TOPIC` và `PARTIALLY_RELEVANT` giữ luồng bốn tiêu chí hiện có.
2. `WHOLLY_UNRELATED + HIGH` bỏ bằng chứng/chấm TR, tạo TR 1.0 và vẫn chạy CC/LR/GRA.
3. `WHOLLY_UNRELATED + MEDIUM/LOW` fail-open và chạy TR bình thường.
4. Liên quan sai định dạng, hết giờ/lỗi nhà cung cấp, ID bằng chứng không biết và hết lượt sửa đều fail-open, không làm lỗi lượt.
5. Task 1 hoàn toàn không liên quan độ tin cậy cao sau đối chiếu dùng được bỏ phát biểu/dữ kiện/chuyên gia/bằng chứng TA/chấm nhưng vẫn trả TA 1.0 + CC/LR/GRA bình thường.
6. Đối chiếu hình ảnh Task 1 không dùng được không rút ngắn chỉ từ liên quan văn bản.
7. Metadata liên quan được lưu, phát lại, phân tích cho lượt hiện tại, còn lượt lịch sử thiếu nó vẫn hợp lệ.
8. Đổi dấu vân tay cache/phiên bản ngăn dùng lại lượt hoàn tất trước liên quan.
9. USER có lượt tập trung của mình tạo/cập nhật được đúng một ảnh chụp cá nhân.
10. USER toàn mô-đun/full-mock, lượt/task người khác, lượt không khớp, đang hoạt động và thất bại không lưu được ảnh chụp.
11. Backend sao chép điểm/phản hồi từ `result_json`; schema không cho client gửi tiêu chí giả.
12. Lưu/cập nhật ảnh chụp không đổi `AttemptWritingScore`, `Attempt.band_score`, giá trị chính thức History/Analytics.
13. Xóa lượt làm lan truyền xóa ảnh chụp cá nhân.

Kiểm thử frontend cần bao quát ít nhất:

1. ADMIN vẫn thấy `Chép gợi ý AI vào biểu mẫu` và hành vi sao chép hiện tại hoạt động.
2. USER tập trung thấy `Lưu nhận xét AI vào bài luyện` sau lượt hoàn tất.
3. USER toàn mô-đun/full-mock không thấy thao tác lưu cá nhân.
4. Thẻ ảnh chụp đã lưu hiển thị bốn điểm/phản hồi và nhãn tư vấn.
5. Chấm lại mới không ghi đè thẻ đã lưu cho đến cập nhật chủ động.
6. Giải thích rõ trạng thái liên quan cho bài hoàn toàn không liên quan, không ngụ ý CC/LR/GRA bằng không hoặc bài gian lận.
7. Lượt lịch sử thiếu metadata liên quan tiếp tục hiển thị.

Chạy tệp pytest/Vitest liên quan nhỏ nhất, kiểm tra kiểu TypeScript cho hợp đồng frontend thay đổi, Ruff trên Python đổi và `git diff --check`. Không cần bộ rộng hơn trừ khi lỗi có trọng tâm phát hiện phụ thuộc.

## 19. Tài liệu và khả năng quan sát

Cập nhật `docs/ai-writing.md` với:

- ngữ nghĩa cổng liên quan và hành vi fail-open;
- khác biệt thực thi Task 1/Task 2;
- cơ sở rút ngắn Band 1 từ hồ sơ mô tả band thấp hiện có;
- độc lập tiêu chí CC/LR/GRA;
- ảnh chụp luyện tập tập trung cá nhân so với chấm thủ công/chính thức;
- định danh phiên bản mới và ảnh hưởng ngân sách lượt gọi khi vận hành.

Báo cáo độ trễ/mức dùng cần tách giai đoạn liên quan đủ rõ để so lượt bình thường và rút ngắn mà không lưu nội dung prompt/bài viết/đầu ra mô hình.

## 20. Tiêu chí nghiệm thu

Thay đổi hoàn tất khi mọi điều sau thỏa:

- Bài hợp lệ đúng chủ đề hoặc liên quan một phần tuyệt đối không bị rút ngắn bởi điều kiện yếu hơn `WHOLLY_UNRELATED + HIGH`.
- Lỗi bộ phân loại liên quan không được làm lỗi lượt vốn chấm được.
- Câu hoàn toàn không liên quan độ tin cậy cao tạo TA/TR 1.0, CC/LR/GRA bình thường và tổng tư vấn bình thường; tuyệt đối không ép `0/0/0/0`.
- Task 1 tránh phân tích TA sau đối chiếu không cần thiết khi xác nhận hoàn toàn không liên quan.
- Hành vi chấm thủ công/sao chép/lưu ADMIN không đổi.
- USER thường có thể chủ động lưu/cập nhật một ảnh chụp điểm+phản hồi AI mới nhất cho task Writing tập trung của mình.
- Ảnh chụp cá nhân không thể trở thành hoặc đổi điểm chính thức/thủ công qua API này.
- Chấm lại không âm thầm thay ảnh chụp đã lưu.
- Lượt AI lịch sử và lượt Writing hiện có vẫn đọc được.
- Không cần suy luận thật, trình duyệt/E2E, triển khai hoặc thay tính năng không liên quan để xác thực triển khai.
