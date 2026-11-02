# Thiết kế luyện kỹ năng Speaking tập trung theo Part

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Thiết kế luyện kỹ năng Speaking tập trung theo Part. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/services/speaking_attempts.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/speaking.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Trạng thái

Thiết kế trao đổi được phê duyệt ngày 2026-10-13; đặc tả văn bản chờ người dùng rà soát cuối trước lập kế hoạch triển khai.

Đây là mở rộng kiến trúc luyện tập tập trung và hệ thống Speaking hiện có. Nó thêm Speaking vào **Skill Practice** thành đơn vị Part 1 / Part 2 / Part 3, tái sử dụng bộ ghi/khôi phục/chép lời/AI hiện có, thêm luồng luyện điều hướng tự do cho Part 1/Part 3 mà không làm yếu hạn chế thi/full-mock.

## Mục tiêu

Thêm Speaking vào `/practice` để học viên chọn một Speaking Part đã biên soạn từ đề xuất bản và luyện toàn Part đó trong một lượt tập trung.

Trải nghiệm phải cung cấp:

- **Part 1**: luyện có hướng dẫn hoặc luyện câu hỏi tự do;
- **Part 2**: chỉ luyện có hướng dẫn;
- **Part 3**: luyện có hướng dẫn hoặc luyện câu hỏi tự do;
- kiểm tra micro trước bắt đầu, bộ ghi, lưu âm thanh phân đoạn, khôi phục, Listen/Retry, bản chép lời và đánh giá AI hiện có;
- phạm vi nội dung và trạng thái ghi do máy chủ quyết định;
- ngữ nghĩa lịch sử/xem lại luyện tập tập trung tuyệt đối không giả thành mô-đun Speaking đầy đủ đã hoàn thành.

## Ngoài phạm vi

Thay đổi này không:

- thêm trình làm Speaking hoặc hệ thống phương tiện thứ hai;
- thêm câu hỏi giám khảo AI thích ứng;
- thêm biên soạn bài giao lớp cho toàn Speaking Part;
- đổi hạn chế điều hướng/làm lại Full Mock hoặc chế độ thi;
- đổi prompt/hiệu chỉnh chấm Speaking IELTS chỉ để ép chấm Part;
- biến điểm AI/luyện cuối cấp Part thành band Speaking toàn mô-đun;
- thêm bản ghi Speaking tập trung vào Analytics toàn mô-đun;
- gọi dịch vụ ASR/LLM/GPU thật khi xác minh triển khai.

## Kiến trúc hiện tại

Hệ thống hiện có bản ghi `SpeakingPart` đã biên soạn cho Part 1/2/3 và `SpeakingPrompt` theo thứ tự. Dữ liệu `VersionDetail` công khai đã cung cấp phần và câu hỏi Speaking, nên khám phá Skill Practice không cần API nội dung thứ hai.

Lượt tập trung hiện hỗ trợ `SPEAKING_PROMPT` qua `Attempt.focused_speaking_prompt_id`. Vì vậy `AttemptScopeGuard`, schema API, nhãn lịch sử và `SpeakingRepository.prompts()` giới hạn lượt Speaking tập trung ở một câu hỏi. Trình làm Speaking hiện tuần tự: hoàn thành câu đang hoạt động cam kết bền vững, khóa và chuyển tiến độ sang câu sau. Chế độ Practice cho Listen/Retry câu hiện tại; thi/full-mock không cho.

Thiết kế mở rộng các ranh giới hiện có, không bỏ qua.

## 1. Mô hình miền Part tập trung

Thêm loại đơn vị tập trung mới:

```text
SPEAKING_PART
```

Thêm trạng thái lượt làm cho phép null:

```text
focused_speaking_part_id -> speaking_parts.id
speaking_practice_flow: GUIDED | FREE
```

Giữ trường và ngữ nghĩa hiện có:

```text
focused_speaking_prompt_id
speaking_mode: PRACTICE | EXAM
```

`SPEAKING_PROMPT` tiếp tục hỗ trợ lượt lịch sử và tích hợp hiện có. Bắt đầu Skill Practice mới chỉ dùng `SPEAKING_PART`.

`speaking_mode` và `speaking_practice_flow` chủ động là khái niệm riêng:

- `speaking_mode=PRACTICE` điều khiển khả năng Practice như nghe/làm lại;
- `speaking_mode=EXAM` giữ hạn chế thi;
- `speaking_practice_flow=GUIDED` điều khiển luyện Part tuần tự;
- `speaking_practice_flow=FREE` bật điều hướng câu hỏi do học viên chọn trong Part đã chọn.

Lượt Speaking tập trung phải nhắm đúng một trong `focused_speaking_prompt_id` hoặc `focused_speaking_part_id`, tuyệt đối không cả hai.

Để tương thích ngược, `speaking_practice_flow` cho phép null trên bản ghi lịch sử/toàn mô-đun/tập trung câu hỏi. Với yêu cầu Practice `SPEAKING_PART` mới, bỏ flow mặc định `GUIDED`; `FREE` phải khai báo rõ. Backend từ chối `speaking_practice_flow` khác null ở nơi không có ý nghĩa, không để lượt Speaking không liên quan vô tình kế thừa ngữ nghĩa Free.

## 2. Migration

Tạo một migration Alembic sau head duy nhất hiện tại. Migration phải:

- thêm `attempts.focused_speaking_part_id` cho phép null với khóa ngoại `RESTRICT` tới `speaking_parts.id`;
- thêm `attempts.speaking_practice_flow` cho phép null/có giới hạn theo quy ước kho mã;
- thay CHECK phạm vi tập trung để lượt Speaking tập trung có đúng một đích câu hỏi hoặc một đích Part, giữ nguyên mọi quy tắc loại trừ Reading/Listening/Writing;
- giữ mọi lượt tập trung câu hỏi lịch sử, không suy đoán ý định Part cha;
- giữ một head Alembic duy nhất.

Migration phải được kiểm thử trên schema PostgreSQL mới migration. Không chỉ dựa bảng kiểm thử tạo bằng metadata ORM.

## 3. Hợp đồng bắt đầu lượt và xác thực

Cấu trúc yêu cầu mới về khái niệm:

```json
{
  "test_version_id": "...",
  "module": "SPEAKING",
  "scope": "FOCUSED_UNIT",
  "focused_unit": { "kind": "SPEAKING_PART", "id": "..." },
  "speaking_mode": "PRACTICE",
  "speaking_practice_flow": "FREE",
  "timer": { "mode": "COUNT_UP" }
}
```

Yêu cầu `SPEAKING_PROMPT` hiện có giữ hợp lệ.

Xác thực backend là nguồn chuẩn. Với bắt đầu tập trung Part mới:

- Part chọn phải thuộc chính xác mô-đun Speaking của phiên bản đề xuất bản yêu cầu;
- Part 1 nhận `GUIDED` hoặc `FREE`;
- Part 2 chỉ nhận `GUIDED`;
- Part 3 nhận `GUIDED` hoặc `FREE`;
- từ chối `SPEAKING_PART + EXAM` cho hợp đồng Skill Practice này;
- luyện Speaking tập trung dùng đếm lên ở cấp lượt; thời gian chuẩn bị/trả lời đã biên soạn của câu hỏi tiếp tục là nguồn chuẩn trong trình làm;
- ID thiếu, thuộc phiên bản/mô-đun khác nhận xử lý đích không hợp lệ an toàn hiện có.

Vô hiệu hóa frontend chỉ là tiện ích; backend cũng phải cưỡng chế các quy tắc này.

## 4. Phạm vi Part do máy chủ quyết định

`SpeakingRepository.prompts(attempt)` trở thành:

```text
if focused_speaking_part_id:
    return every prompt in that Part, ordered by prompt.order_index
elif focused_speaking_prompt_id:
    return that one prompt (legacy/current compatibility)
else:
    return the complete Speaking module
```

Mọi thao tác ghi Speaking tiếp tục chứng minh câu hỏi thuộc tập câu giới hạn của lượt. Lượt Part 1 không được bắt đầu, ghi, tải lên, làm lại, nghe lại, chọn hoặc chốt câu Part 2/3 dù client tự gửi UUID.

Trình duyệt tuyệt đối không được gửi danh sách ID câu hỏi có thẩm quyền.

## 5. Khám phá Skill Practice và thẻ

`/practice` trở thành trình duyệt bốn kỹ năng:

```text
Reading
Listening
Writing
Speaking
  All parts
  Part 1
  Part 2
  Part 3
```

`VersionDetail.speaking_parts` đã xuất bản cung cấp đơn vị. Mỗi thẻ Speaking đại diện toàn bộ một Part, không phải một câu. Thẻ hiện thông tin gọn như:

```text
SPEAKING
Part 1
Introduction and Interview
8 questions
IELTS Cambridge 11 Test 1 · Version 13
```

Part 1/Part 3 có bộ chọn kiểu luyện gọn:

```text
Guided practice
Free question practice
```

Part 2 chỉ cung cấp Guided. Thẻ Speaking dùng màu/kiểu Speaking ngữ nghĩa hiện có, không thêm ngôn ngữ thị giác mới.

Thẻ và hành vi thời gian Reading/Listening/Writing hiện có giữ nguyên. Speaking không hiện bộ chọn phút tập trung chung; bắt đầu `COUNT_UP` và dùng thời gian câu hỏi đã biên soạn trong bộ máy Speaking.

## 6. Luyện Part có hướng dẫn

Luyện có hướng dẫn tái sử dụng trình Speaking và ngữ nghĩa tuần tự bền vững hiện tại.

Part 1/Part 3 chạy câu hỏi theo thứ tự biên soạn:

```text
prompt -> record -> durable finish acknowledgement -> next prompt
```

Part 2 giữ chuỗi có ý nghĩa của nó:

```text
preparation -> long turn -> authored follow-up(s) -> finish
```

Kiểm tra micro, truyền chunk, quyền làm/nghe lại, khoảng khôi phục, hành vi ghi chú nháp, bộ đếm và yêu cầu xác nhận backend hiện có tiếp tục hiệu lực.

Không hiện bộ chọn câu tự do ở Guided. Hành vi Guided hiện có có thể tiếp tục tự vào câu hiện tại sau kiểm tra ban đầu theo hợp đồng trình làm hiện tại.

## 7. Luyện câu hỏi tự do

Free chỉ có cho lượt Practice tập trung Part 1/Part 3.

Trình làm hiện bộ chọn câu hỏi có khả năng tiếp cận, ví dụ:

```text
[1] [2✓] [3] [4✓] [5] ...
```

cùng điều khiển tiện ích Previous/Next. Học viên có thể đi bất kỳ thứ tự, ví dụ Q1 -> Q5 -> Q3 -> Q8. Mỗi câu giữ trạng thái trả lời độc lập do máy chủ lưu như chưa trả lời, được chọn, đang ghi, đã cam kết và làm lại.

Khác Guided, chọn câu Free **không được** tự bắt đầu ghi. Học viên chủ động nhấn `Record`. Cách này giữ luồng tự luyện dự kiến: chọn câu, suy nghĩ/đọc, ghi khi sẵn sàng rồi điều hướng tự do.

Có thể quay lại câu đã cam kết trong Free. Học viên được quay lại, nghe bản thu cam kết và làm lại. Làm lại một câu không được xóa bản ghi câu khác.

Đây là ngoại lệ chủ động với UX khóa câu trước của Guided Practice; chỉ áp dụng khi chính lượt được lưu `FREE`.

### 7.1 Hợp đồng trạng thái Free

Hệ thống tuần tự hiện tại không thể đơn giản tái dùng “hoàn thành câu chuẩn cuối => nộp lượt”. Free cần trạng thái nghỉ/duyệt an toàn rõ ràng hoặc biểu diễn máy chủ tương đương.

Về khái niệm:

```text
BROWSING / IDLE
  -> select prompt
QUESTION_ENTER / READY
  -> explicit Record
PREPARING? -> STARTING? -> RECORDING
  -> durable finish
BROWSING / IDLE
```

Tên pha cụ thể có thể theo quy ước hiện có nhưng ngữ nghĩa sau là bắt buộc:

- lượt Free mới không bị ép tự bắt đầu Q1;
- hoàn thành Q8 đầu tiên **không được** hoàn tất lượt chỉ vì Q8 đứng cuối thứ tự biên soạn;
- cam kết một câu trả về trạng thái an toàn để chọn câu khác được phép;
- hoàn tất lượt là thao tác `Finish practice` chủ động riêng;
- thứ tự câu chuẩn vẫn điều khiển nhãn bộ chọn và Previous/Next, không quyết định hoàn thành.

Trạng thái Speaking công khai của Free Part phải gồm đủ dữ liệu máy chủ có giới hạn để dựng lại bộ chọn sau tải lại, ví dụ câu được chọn và tóm tắt điều hướng chứa ID/thứ tự, trạng thái an toàn (`UNANSWERED`, `COMMITTED`, hiện tại). Frontend không được suy hoàn thành có thẩm quyền từ trạng thái thành phần cục bộ.

### 7.2 Chuyển câu khi đang ghi

Điều hướng Free tuyệt đối không âm thầm bỏ bản ghi đang hoạt động. Nếu học viên chọn câu khác khi đang thu, hiện xác nhận với thao tác tương đương:

```text
Continue recording
Stop & switch
```

`Stop & switch` phải:

1. dừng bộ ghi vật lý;
2. đẩy hết/đóng truyền chunk đang chờ;
3. chốt câu hiện tại qua máy chủ;
4. chờ xác nhận backend đã lưu bền vững;
5. chỉ sau đó kích hoạt câu yêu cầu.

Không chuyển câu lạc quan trước xác nhận.

Nếu lưu thất bại, ở lại câu hiện tại và hiện lỗi lưu/thử lại có hướng xử lý bình thường.

### 7.3 Chọn câu phía máy chủ

Điều hướng Free cần thao tác/chuyển trạng thái rõ do máy chủ quyết định để chọn câu trong Part giới hạn của lượt. Không được triển khai chỉ bằng frontend viết lại giả định về `SpeakingPromptProgress.prompt_id`.

Máy chủ chỉ cho chọn từ trạng thái không ghi an toàn, trừ khi client trước hết thực hiện luồng `Stop & switch` được xác nhận nêu trên. Từ chối đích ngoài Part.

Tên tuyến theo quy ước API Speaking hiện có; không thêm endpoint ghi tiến độ tùy ý chung.

### 7.4 Nghe lại và làm lại câu đã cam kết

Hệ thống tuần tự hiện coi câu đã cam kết trước là khóa. Free chủ động cần ngoại lệ hẹp do máy chủ phân quyền cho câu đã cam kết trong Part chọn.

Chọn câu đã cam kết phải cung cấp được câu trả lời cam kết để nghe mà không mở câu không liên quan hoặc bỏ qua phạm vi Part.

Nếu chọn Retry trên câu Free đã cam kết, bản thu cam kết trước phải giữ làm dự phòng hợp lệ đến khi bản thay thế cam kết bền vững. Lần thử thất bại/bỏ dở không được phá bản ghi tốt cuối. Khi thay thế cam kết thành công, cập nhật nguyên tử bản thu/dấu vân tay cam kết hoạt động và đánh dấu bản bị thay theo quy ước nguồn gốc hiện có.

Hành vi chỉ Free; ngữ nghĩa khóa Guided, Exam, Full Mock không đổi.

## 8. Quy tắc Part 2

Part 2 luôn Guided. Chuẩn bị thẻ đề, lượt nói dài và chuỗi câu hỏi phụ liên quan được coi là một luồng luyện nhất quán.

Backend từ chối `Part 2 + FREE`; frontend không cung cấp lựa chọn đó. Không thêm bộ chọn nhảy trực tiếp vào giữa Part 2.

## 9. Ngữ nghĩa hoàn thành

Luyện Part Guided hoàn tất qua luồng tuần tự hiện có khi chuỗi câu của Part chọn đã hoàn thành.

Luyện Part Free chỉ hoàn tất qua thao tác `Finish practice` chủ động. Có thể kết thúc khi chưa trả lời hết, nhưng phải có ít nhất một câu cam kết bền vững và phải từ chối hoàn tất khi còn chuyển trạng thái ghi/khôi phục đang hoạt động chưa giải quyết.

Hoàn tất không được tạo câu trả lời giả cho câu chưa trả lời. Xem lại hiển thị `Not answered` dựa danh sách câu đã biên soạn của Part.

Lượt làm là một lượt tập trung cho Part, không phải mỗi câu một lượt.

## 10. Tải lại, khôi phục và lưu trữ

`FREE`/`GUIDED` lưu trên Attempt, không chỉ là trạng thái React.

Sau tải lại, backend tiếp tục quyết định:

- Part và luồng được chọn;
- câu được chọn/hiện tại và pha;
- câu trả lời cam kết và số bản thu hoạt động;
- trạng thái gián đoạn/khôi phục;
- điều kiện câu hỏi và trạng thái bộ chọn.

Giao diện dựng lại bộ chọn từ trạng thái backend. Khôi phục âm thanh phân đoạn hiện có không đổi: sự cố/tải lại không bịa âm thanh, đặt lại hạn mức trả lời hoặc chuyển câu khác.

Nếu sự cố khi Free làm lại, bản thu cam kết hiện có vẫn dự phòng trừ khi/cho đến bản thay thế đã cam kết bền vững.

## 11. Xem lại

Xem lại tập trung Part hiện toàn bộ danh sách câu đã biên soạn của Part chọn cùng trạng thái trả lời; điều khiển âm thanh/chép lời chỉ có cho câu đã trả lời.

Ví dụ:

```text
Speaking · Part 1
Free practice

Q1  27s
Q2  Not answered
Q3  31s
```

Xem lại Guided ghi rõ luyện có hướng dẫn. Lượt `SPEAKING_PROMPT` cũ tiếp tục dùng nhãn tập trung câu hỏi hiện có, không âm thầm diễn giải thành lượt Part.

Câu chưa trả lời chỉ mang thông tin; không nhận âm thanh/bản chép lời/phản hồi giả.

## 12. Lịch sử và Analytics

Lượt tập trung Part thuộc lịch sử Focused Practice. Trình bày cần phân biệt Part 1/2/3 và Guided/Free khi hữu ích.

Các lượt này không được:

- chiếm vị trí mô-đun Speaking đầy đủ trong nhóm By-skill/By-test;
- tính là mô-đun Speaking đầy đủ đã hoàn thành;
- đóng góp band luyện Part như band Speaking đầy đủ;
- đóng góp điểm tổng Full Mock;
- vào Analytics Speaking toàn mô-đun như đề đầy đủ.

Loại trừ lượt tập trung hiện có được mở rộng sang `SPEAKING_PART`.

## 13. Bản chép lời và nghe lại âm thanh

Tạo bản chép lời vẫn theo từng câu trả lời cam kết. Học viên không cần trả lời mọi câu trong Free Part trước khi tạo/xem bản chép lời câu đã trả lời.

Âm thanh thô giữ riêng tư theo phân quyền phương tiện hiện có. Không yêu cầu định dạng lưu mới hoặc tài sản âm thanh ghép toàn Part.

## 14. Đánh giá AI

Part tập trung có thể dùng luồng Speaking AI hiện tại khi bằng chứng cam kết đủ chấm. Giao diện phải ghi rõ kết quả luyện Part, ví dụ:

```text
AI Assessment · Part 1 practice
Advisory
```

Bộ chấm vẫn có thể trả đánh giá tiêu chí FC/LR/GRA/PR cho bằng chứng thực có, nhưng kết quả Part không là band bài thi IELTS Speaking đầy đủ.

Nếu lượt Free quá ít bằng chứng dùng được, giữ hành vi không đủ điều kiện chấm hiện tại thay vì bịa điểm. Không đổi prompt/hiệu chỉnh AI chỉ để ép chấm cấp Part.

## 15. Ngữ nghĩa điểm chốt con người/cá nhân

Chấm chủ quan nhận biết nguồn gốc vừa bổ sung tiếp tục là nguồn chuẩn.

Speaking Part tập trung cá nhân có thể giữ điểm luyện do người/tự đánh giá đã lưu nếu luồng điểm cuối hiện tại hỗ trợ. Tuy nhiên điểm gắn lượt tập trung, không được nâng thành:

- `attempt.band_score` toàn mô-đun khi ngữ nghĩa tập trung hiện có giữ null;
- điểm tổng Full Mock;
- Analytics Speaking đầy đủ.

Kết quả AI giữ tư vấn, tuyệt đối không tự nâng thành điểm cuối khi lượt hoàn thành.

Học viên/giáo viên lớp giữ ranh giới chấm chủ quan do `Add provenance-aware subjective skill grading` đưa vào.

## 16. Tương thích lớp học

Tính năng dành cho `/practice`. Không thêm giao diện lớp mới giao toàn Part.

Hợp đồng giao/bắt đầu `SPEAKING_PROMPT` hiện có giữ tương thích ngược. Schema API dùng chung có thể nhận discriminator `SPEAKING_PART` nơi cần cho kiểu chung, nhưng triển khai không được âm thầm mở rộng hành vi giao bài lớp.

Không được suy giảm nguồn gốc bài giao, chấm cuối lớp chỉ giáo viên và ranh giới luyện cá nhân riêng tư.

## 17. Khả năng tiếp cận, UX thích ứng và i18n

Văn bản hiển thị mới được bản địa hóa EN + VI.

Bộ chọn Free phải:

- dùng nút ngữ nghĩa, trạng thái hiện tại/hoàn thành/chưa trả lời rõ không chỉ dựa màu;
- vận hành được bằng bàn phím;
- giữ tiêu điểm nhìn thấy;
- cuộn ngang hoặc xuống dòng an toàn trên màn hình hẹp, không tràn trang;
- giữ trạng thái ghi và bộ đếm dễ tiếp cận;
- tôn trọng giảm chuyển động cho mọi chuyển trạng thái nhẹ.

Xác nhận điều hướng khi ghi phải tiếp cận được bằng bàn phím/chạm và tái dùng quy ước hộp thoại dự án.

## 18. Tương thích ngược

Triển khai phải bảo toàn:

- lượt Speaking toàn mô-đun cũ;
- lượt `SPEAKING_PROMPT` tập trung cũ;
- ngữ nghĩa Practice/Exam hiện có;
- hạn chế Full Mock không nghe lại/làm lại/quay lại;
- hành vi chunk/bản thu/khôi phục âm thanh hiện có;
- cache/phân quyền bản chép lời hiện có;
- ngữ nghĩa AI Speaking tư vấn hiện có;
- chấm cuối Writing/Speaking nhận biết nguồn gốc hiện tại;
- luyện tập tập trung Reading/Listening/Writing.

Không viết lại lượt lịch sử từ phạm vi câu hỏi sang Part.

## 19. Rủi ro và biện pháp

### Điều hướng Free bỏ qua giả định khóa tuần tự hiện tại

Biện pháp: thêm chuyển trạng thái máy chủ rõ cho chọn câu Free, giữ tập câu được phép theo Part làm nguồn chuẩn. Không sửa tiến độ cục bộ trong React.

### Hoàn thành câu cuối theo biên soạn có thể vô tình nộp lượt Free

Biện pháp: phân nhánh ngữ nghĩa hoàn thành theo `speaking_practice_flow` đã lưu. Cam kết câu Free trả về trạng thái duyệt/an toàn; chỉ `Finish practice` chủ động mới nộp lượt.

### Điều hướng khi ghi có thể mất âm thanh

Biện pháp: yêu cầu dừng -> đẩy hết/đóng -> ACK hoàn thành bền vững -> chuyển. Tuyệt đối không ngầm bỏ bản đang ghi.

### Làm lại câu đã cam kết có thể mất bản ghi tốt cuối

Biện pháp: giữ bản cam kết đến khi bản thay thế cam kết bền vững; đổi bản cam kết hoạt động nguyên tử.

### Luyện Part có thể làm sai thống kê kỹ năng đầy đủ

Biện pháp: giữ `scope=FOCUSED_UNIT`, mở rộng nhãn lịch sử/xem lại và thêm hồi quy rõ rằng điểm Part tập trung không nâng thành band toàn mô-đun/Analytics/Full Mock.

### Migration có thể phá ràng buộc phạm vi lịch sử

Biện pháp: thêm đích Part theo hướng bổ sung, giữ `focused_speaking_prompt_id`, kiểm thử ràng buộc nâng cấp thật và xác minh một head Alembic.

## 20. Chốt kiểm tra CI từ xa tại mốc cơ sở

Triển khai BẮT BUỘC bắt đầu bằng kiểm tra kết quả GitHub Actions hiện tại của `origin/main` và nhật ký tác vụ lỗi thật trước viết tính năng.

Tại thời điểm đặc tả, mốc tính năng trước các commit tài liệu là:

```text
0a4a757c0788a2c0ce63ea671295770a12062bad
Add provenance-aware subjective skill grading
```

Lượt CI push `38346177088` **đỏ**. Lỗi nằm ở giai đoạn kiểm thử đơn vị, không phải lint/kiểm tra kiểu/head migration:

- Ruff lint backend: đạt.
- Ruff format backend: đạt.
- Nâng Alembic PostgreSQL mới: đạt.
- Xác minh một head Alembic: đạt.
- Kiểm thử backend: **6 lỗi, 367 đạt**. Lỗi chung quan sát ở kiểm thử chấm chủ quan mới là `sqlite3.OperationalError: no such table: attempt_speaking_scores`, cho thấy luồng schema/dữ liệu mẫu kiểm thử thiếu bảng điểm cuối Speaking mới dù chính nâng PostgreSQL bằng migration của CI đã đạt.
- Kiểm tra kiểu frontend: đạt.
- ESLint frontend: đạt.
- Kiểm thử đơn vị frontend: **3 lỗi, 281 đạt**. Một lỗi xác nhận ở `tests/speaking-history-classroom.test.tsx`, nơi `getByRole("button", { name: "Use AI score as starting point" })` nay khớp nhiều nút sau đổi giao diện chấm chủ quan. Các lỗi frontend còn lại phải đọc từ nhật ký từ xa thật, không đoán.
- Workflow riêng `Golden path E2E` cùng SHA hoàn thành thành công nhưng không ghi đè workflow CI đỏ.

Vì vậy kế hoạch triển khai phải cưỡng chế trình tự:

1. fetch `origin/main` mới nhất và kiểm tra Actions từ xa đúng SHA đó;
2. nếu main còn đỏ, tái hiện/sửa lỗi CI cơ sở trước (hoặc xác minh main mới hơn đã sửa);
3. không chồng tính năng lên CI đỏ chưa giải thích;
4. chạy tập hồi quy có trọng tâm khi triển khai;
5. sau push, kiểm tra GitHub Actions SHA cuối;
6. không tuyên bố hoàn tất khi workflow CI liên quan đỏ;
7. nếu CI từ xa lỗi, kiểm tra log thật, sửa gốc và push commit tiếp theo bình thường; tuyệt đối không force-push chỉ để giấu lỗi.

## 21. Chiến lược kiểm thử

Kiểm thử backend tối thiểu phải gồm:

- hợp đồng yêu cầu/schema `SPEAKING_PART`;
- mặc định `GUIDED` khi bỏ flow Part và từ chối khai báo flow sai chỗ;
- Part thuộc chính xác phiên bản/mô-đun đã xuất bản;
- chấp nhận Guided + Free cho Part 1/3;
- từ chối Part 2 Free;
- từ chối `SPEAKING_PART + EXAM` cho luồng này;
- migration thật + hành vi CHECK phạm vi;
- repository Part trả đủ và chỉ các câu của Part theo thứ tự chuẩn;
- từ chối bắt đầu/phương tiện/làm lại/nghe lại/chọn/chốt câu ngoài Part;
- giữ hành vi `SPEAKING_PROMPT` cũ;
- giữ tiến trình Guided;
- Free bắt đầu không tự ghi, cho Record chủ động;
- Free chọn không theo thứ tự và dựng lại trạng thái bộ chọn;
- cam kết câu biên soạn cuối không tự nộp lượt Free;
- kết thúc Free chủ động yêu cầu >=1 câu cam kết, cho phép câu chưa trả lời và từ chối thu đang hoạt động chưa giải quyết;
- nghe/làm lại câu cam kết chỉ hoạt động trong phạm vi Free Part;
- thử lại câu cam kết thất bại giữ bản ghi cam kết trước;
- chuyển khi ghi không thể bỏ qua chốt bền vững;
- tải lại/khôi phục giữ Part/flow/trạng thái hiện tại;
- xem lại chỉ chứa Part chọn và mục chưa trả lời;
- Part tập trung tiếp tục bị loại khỏi nâng band History/Analytics/Full Mock toàn mô-đun;
- hồi quy chấm chủ quan/nguồn gốc tiếp tục đạt.

Kiểm thử Vitest/RTL frontend tối thiểu phải gồm:

- Speaking xuất hiện trong Skill Practice với bộ lọc All parts / Part 1 / Part 2 / Part 3;
- thẻ dùng payload bắt đầu `SPEAKING_PART`;
- Part 1/3 cung cấp Guided và Free;
- Part 2 chỉ Guided;
- Speaking đếm lên thay cấu hình phút chung;
- trình Guided không có bộ chọn Free;
- bộ chọn Free không tự bắt đầu ghi;
- Record chủ động bắt đầu câu chọn;
- bộ chọn Free điều hướng không theo thứ tự;
- trạng thái hoàn thành/chưa trả lời/hiện tại dễ tiếp cận;
- quay lại giữ nghe/làm lại;
- điều hướng khi ghi yêu cầu xác nhận;
- `Stop & switch` chờ xác nhận lưu trước chuyển;
- lưu thất bại giữ người dùng ở câu hiện tại;
- hành vi Finish Practice chủ động và chốt >=1 câu;
- dựng lại sau tải dùng trạng thái backend;
- hạn chế thi/full-mock Speaking hiện có không đổi.

Không yêu cầu trình duyệt/Playwright để xác minh triển khai trừ khi lỗi về sau thật sự không chẩn đoán được bằng kiểm thử đơn vị/thành phần. Không gọi Modal, ASR thật, LLM thật hoặc GPU cho nhiệm vụ này.

## 22. Tiêu chí nghiệm thu

Tính năng chỉ hoàn tất khi:

1. Skill Practice liệt kê Speaking Part 1/2/3 từ phiên bản xuất bản.
2. Bắt đầu thẻ tạo một lượt Practice tập trung Part.
3. Part 1/3 hỗ trợ Guided và Free; Part 2 chỉ Guided.
4. Guided giữ tương đương luyện Speaking tuần tự hiện có trong Part chọn.
5. Free cho chọn không theo thứ tự an toàn và không tự ghi.
6. Free cho quay lại, Listen và Retry an toàn, giữ bản ghi từng câu cùng bản cam kết tốt cuối khi thay thất bại.
7. Điều hướng khi đang thu không được làm mất/bỏ qua lưu bản ghi chưa xác nhận.
8. Hoàn thành câu Free tuyệt đối không tự nộp chỉ vì là câu biên soạn cuối; Finish Practice chủ động kiểm soát hoàn tất.
9. Backend từ chối mọi câu ngoài Part chọn.
10. Tải lại/khôi phục dựng lại luồng, câu chọn, trạng thái trả lời/bộ chọn đã lưu.
11. Xem lại/lịch sử xác định đúng Part và flow; câu Free chưa trả lời biểu diễn không bịa.
12. Điểm AI/con người cấp Part giữ tư vấn/tập trung, tuyệt đối không thành band Speaking toàn mô-đun hoặc Full Mock.
13. Lượt Speaking tập trung câu hỏi cũ và toàn mô-đun vẫn hoạt động.
14. Chấm cuối nhận biết lớp/nguồn gốc hiện tại giữ nguyên.
15. Alembic giữ một head, migration mới đạt trên cơ sở dữ liệu PostgreSQL mới.
16. Mốc CI đỏ có trước được giải quyết trước hoàn tất tính năng.
17. GitHub Actions SHA cuối đã push được kiểm tra, workflow CI liên quan xanh.

## 23. Ràng buộc thực thi cho kế hoạch triển khai sau này

- Tuyệt đối không dùng Astra.
- Tối đa hai tác nhân con không lồng, chỉ khi bảo đảm mô hình không phải Astra; nếu không thực hiện trực tiếp.
- Ưu tiên kiểm thử đơn vị/thành phần backend/frontend có trọng tâm khi phát triển.
- Không dùng trình duyệt thủ công/Playwright, triển khai Modal, ASR thật, LLM thật hoặc GPU cho công việc này.
- Giữ thương hiệu BandPilot và phần chấm chủ quan/AI Writing/Speaking vừa hoàn thành.
- Dùng commit bình thường và tích hợp fast-forward an toàn; tuyệt đối không force-push.
