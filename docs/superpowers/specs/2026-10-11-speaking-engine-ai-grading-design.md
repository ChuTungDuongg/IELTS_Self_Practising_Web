# Thiết kế bộ máy Speaking, ghi âm, bản chép lời và chấm AI

> **Kiểm toán tài liệu: CURRENT.** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Thiết kế bộ máy Speaking, ghi âm, bản chép lời và chấm AI. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/services/speaking_attempts.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/speaking.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.
> Chỉ dẫn Speaking vẫn có tính ràng buộc theo AGENTS; không lưu trữ hoặc vô hiệu hóa các sửa đổi sau tự rà soát.

## Trạng thái

Thiết kế đã được thống nhất trong trao đổi, ghi lại để lập kế hoạch triển khai. Đặc tả đưa Speaking thành kỹ năng IELTS chính thức thứ tư, định nghĩa Builder, trình làm, hợp đồng ghi/khôi phục, luồng chép lời, kiến trúc chấm AI kết hợp, UX xem lại và ranh giới tích hợp.

Đây là bổ sung kiến trúc. Triển khai phải chia giai đoạn; không làm toàn phân hệ như một thay đổi không phân biệt.

## Mục tiêu

Thêm trải nghiệm luyện/thi IELTS Speaking đủ chất lượng production với các yêu cầu:

- tích hợp Speaking vào bộ máy đề/phiên bản/lượt làm hiện có, không làm bản trình diễn tách rời;
- hỗ trợ biên soạn và thực hiện Part 1, Part 2, Part 3;
- ghi và lưu bền vững lời nói thí sinh theo câu hỏi;
- chịu tải lại/sự cố trình duyệt với khôi phục có giới hạn;
- cung cấp luồng chép lời riêng chỉ đọc theo từng câu;
- cung cấp luồng `Grade with AI` chủ động dùng bằng chứng âm thanh + bản chép lời;
- chấm bốn tiêu chí Speaking độc lập và tổng thể trên toàn lượt làm;
- giữ chấm AI tư vấn và có thể quan sát;
- có giao diện động, thích ứng theo trạng thái, không chuyển động gây xao nhãng khi thi;
- chừa khả năng hiệu chỉnh/tinh chỉnh về sau bằng dữ liệu người gán nhãn.

## Cơ sở nghiên cứu

Thiết kế theo các mẫu hệ thống/đánh giá công khai sau, không coi Speaking là chấm LLM chỉ dựa bản chép lời:

- Cấu trúc và mô tả band Speaking IELTS chính thức: ba phần, khoảng 11–14 phút, bốn tiêu chí trọng số đều là Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy, Pronunciation.
- Đánh giá nói tự động theo cấu trúc năng lực kiểu ETS SpeechRater: ASR cộng đặc trưng phát âm, ngữ điệu, trôi chảy, ngữ pháp, từ vựng/nội dung/diễn ngôn, cùng lọc rõ câu không đủ điều kiện chấm.
- Hệ thống Cambridge Speak & Improve / SLATE 2025: nhánh âm học và văn bản riêng, thường hợp nhất với đặc trưng trôi chảy/phát âm thiết kế thủ công.
- Kiến trúc nghiên cứu công khai kiểu CASA: nhánh lời nói âm học + nhánh chép lời/nội dung + tầng hợp nhất/chấm.
- Nghiên cứu phát âm kiểu GOPT / SpeechOcean: GOP và biểu diễn lời nói học được có thể cung cấp bằng chứng phát âm, nhưng không được ánh xạ trực tiếp điểm bộ dữ liệu đó sang band IELTS.
- Whisper / faster-whisper cùng căn chỉnh từ kiểu WhisperX làm mẫu ASR/gắn thời gian thực dụng.

Dự án **không** tuyên bố tái tạo chính xác một bài nghiên cứu. V1 là bộ chấm IELTS tư vấn kết hợp, theo mô tả năng lực, lấy cảm hứng từ hệ thống công khai này.

## Ghi chú phạm vi kho mã

Kho mã hiện vẫn có chỉ dẫn `AGENTS.md` cũ nói không triển khai Speaking. Yêu cầu người dùng này ghi đè rõ chốt phạm vi lỗi thời đó. Kế hoạch cần cập nhật hướng dẫn kho mã để công việc sau không coi Speaking bị cấm khi bắt đầu triển khai.

## Quyết định sản phẩm

- Speaking trở thành kỹ năng chính thức cùng Listening, Reading, Writing.
- Đề Speaking có đúng ba phần logic: Part 1, Part 2, Part 3.
- Part 1/Part 3 biên soạn thành chuỗi câu theo thứ tự. Builder thiên về nối thêm như danh sách liên kết, nhưng lưu bằng ID ổn định + `order_index`, không con trỏ `next_question_id`.
- Part 2 là loại câu lượt dài/thẻ đề riêng với thời gian chuẩn bị, ý gợi, thời gian trả lời và câu phụ tùy chọn.
- Thời gian câu hỏi cấu hình được. Part 1/3 mặc định 60 giây mỗi câu cho luồng ứng dụng này, nhưng không mã hóa 60 giây thành khẳng định bất biến về thời gian từng câu IELTS chính thức.
- Part 2 mặc định 60 giây chuẩn bị và tối đa 120 giây nói.
- Thí sinh được nhấn `Done / Next` trước hết giờ; hết giờ tự dừng, lưu và chuyển tiếp.
- Exam/Full Mock: không nghe lại, làm lại hoặc quay câu trước đã cam kết.
- Tập trung/tự luyện: thí sinh được nghe/làm lại câu hiện tại trước `Done / Next`; câu trước đã cam kết vẫn khóa.
- Khôi phục tải lại/sự cố tiếp tục câu gián đoạn, không bắt đầu lại.
- Khôi phục giữ ảnh chụp thời gian trả lời/chuẩn bị còn lại lúc gián đoạn do máy chủ quyết định, rồi cấp khoảng ân hạn kết nối/chuẩn bị 7 giây trước tiếp tục thời gian còn lại. Ân hạn không cộng hạn mức nói, không thể lợi dụng bằng tải lại lặp.
- Xem lại Speaking cung cấp hai thao tác riêng: `Generate Transcript` và `Grade with AI`.
- Bản chép lời chỉ đọc, chỉ hiển thị từng câu; v1 không có giao diện bản chép lời gộp toàn bộ.
- `Grade with AI` tái dùng bản chép lời hợp lệ nếu có; nếu chưa thì tạo nội bộ.
- Người dùng không được sửa bản chép ASR trước chấm.
- Bản chép sạch có thể chuẩn hóa dấu câu/cách trình bày từ đệm để phân tích nhưng tuyệt đối không sửa ngữ pháp hoặc âm thầm cải thiện lời thí sinh.
- Chấm AI tổng thể toàn lượt Speaking. Phân tích cấp câu chỉ làm bằng chứng/phản hồi; không lấy trung bình điểm câu.
- AI chấm trước: bằng chứng -> đầu ra chỉ điểm rất nhỏ -> lưu điểm -> phản hồi. Phản hồi thất bại không được xóa điểm hợp lệ.
- Pronunciation phải dùng bằng chứng từ âm thanh; LLM chỉ văn bản không được suy phát âm từ bản chép lời đơn thuần.
- Mặc định giao diện/chuyển động chọn để rõ ràng, hoàn thiện; UX thi giữ tiết chế và dễ tiếp cận.

## 1. Mô hình miền

Tên bảng cụ thể có thể theo quy ước kho mã hiện tại nhưng thiết kế yêu cầu các khái niệm sau.

### 1.1 Mô-đun và các phần Speaking

Mở rộng kiểu mô-đun để hỗ trợ Speaking như mô-đun chính thức.

```text
SpeakingModule
- id
- test_version_id
- recommended_duration_seconds nullable
- config_json

SpeakingPart
- id
- speaking_module_id
- part_number: 1 | 2 | 3
- title nullable
- instructions nullable
- order_index
```

Hệ thống cần cưỡng chế một Part 1, một Part 2, một Part 3 logic mỗi mô-đun Speaking đầy đủ, vẫn cho nháp tạm chưa đủ trong Builder.

### 1.2 Câu hỏi Speaking

```text
SpeakingPrompt
- id
- speaking_part_id
- order_index
- prompt_type: SHORT_ANSWER | LONG_TURN | FOLLOW_UP
- prompt_text
- preparation_seconds
- response_seconds
- config_json
```

`config_json` có thể chứa ý gợi và dữ liệu trình bày riêng phần, nhưng trường thời gian/thứ tự cốt lõi cần giữ cột có kiểu truy vấn được khi khả thi.

Part 1/Part 3 thường dùng câu `SHORT_ANSWER`.

Part 2 dùng một câu `LONG_TURN` với cấu hình thẻ đề và câu phụ biên soạn tùy chọn. Câu phụ vẫn được biên soạn rõ ở v1; không yêu cầu giám khảo AI thích ứng.

### 1.3 Thứ tự ổn định

Thêm câu mặc định nối cuối. Sắp lại dùng chuẩn hóa `order_index` như mẫu Builder hiện có. Không triển khai danh sách liên kết cơ sở dữ liệu.

ID câu ổn định giữ qua sắp lại để tham chiếu trả lời/lịch sử bền vững.

## 2. Builder

Speaking Builder tích hợp Builder đề/phiên bản hiện có, tuân quyền sở hữu, kiểm duyệt, tự lưu, phiên bản bất biến và chính sách giáo viên/admin hiện có.

### 2.1 Biên soạn Part 1 / Part 3

Mỗi phần hiển thị luồng dọc theo thứ tự:

```text
Question card
   ↓
Question card
   ↓
+ Add question
```

Mỗi thẻ hỗ trợ:

- văn bản câu hỏi;
- thời gian trả lời mặc định hợp lý 60 giây;
- sắp lại;
- xóa khi bản nháp còn được sửa;
- xác thực tại chỗ.

Thêm/sắp lại cần chuyển tiếp nhẹ để trình tự rõ bằng thị giác.

### 2.2 Biên soạn Part 2

Trình biên soạn lượt dài hỗ trợ:

- đề chính thẻ gợi;
- danh sách ý gợi (`You should say...`);
- thời gian chuẩn bị, mặc định 60s;
- thời gian trả lời lượt dài, mặc định 120s;
- chuỗi câu hỏi phụ tùy chọn;
- xem trước trình bày thí sinh.

Ghi chú nháp thí sinh chỉ là dữ liệu trong lúc làm, không phải nội dung biên soạn/chấm.

### 2.3 Xác thực

Xác thực xuất bản/kiểm duyệt cần từ chối mô-đun Speaking đầy đủ sai cấu trúc, gồm thiếu phần bắt buộc, trùng số phần, thiếu câu lượt dài, thời gian không dương, chỉ số thứ tự trùng/lỗi thời sau chuẩn hóa và văn bản câu bắt buộc rỗng.

Tự lưu nháp được lưu trạng thái trung gian chưa đủ theo quy ước Builder hiện có.

## 3. Thiết lập và trình làm Speaking thí sinh

### 3.1 Kiểm tra micro trước bắt đầu

Trước bắt đầu lượt Speaking, hiện vùng thiết lập micro:

- xin quyền micro một lần;
- chọn thiết bị vào khi API trình duyệt cho phép;
- xác minh khả năng `MediaRecorder`;
- hiện thước mức âm thời gian thực nhẹ;
- phát hiện tín hiệu rõ im lặng/gần im lặng;
- hiện MIME ghi được hỗ trợ đã chọn;
- chỉ bắt đầu khi kiểm tra sẵn sàng tối thiểu thành công.

Không chạy AI trong kiểm tra ban đầu.

### 3.2 Thực hiện câu hỏi

Với Part 1/3:

```text
QUESTION_ENTER
-> RECORDING
-> USER_DONE or TIMEOUT
-> FINALIZING / UPLOADING
-> COMPLETED
-> NEXT_QUESTION
```

Chỉ hiển thị câu và đếm ngược của câu hiện tại. Không cho thí sinh xem câu tương lai trong thi/full-mock.

Với Part 2:

```text
QUESTION_ENTER
-> PREPARING
-> short start countdown
-> RECORDING
-> USER_DONE or TIMEOUT
-> FINALIZING / UPLOADING
-> optional authored FOLLOW_UP prompt(s)
-> COMPLETED
```

### 3.3 Hành vi Done / Next

`Done / Next`:

1. dừng bộ ghi;
2. đẩy hết chunk chờ;
3. chốt metadata câu trả lời;
4. chờ xác nhận backend;
5. chỉ chuyển tiếp sau khi câu trả lời được nhận bền vững.

Không chuyển lạc quan khi lưu cuối thất bại.

### 3.4 Luyện tập so với thi/full mock

Tập trung/tự luyện:

- câu hiện tại có thể cung cấp `Listen`, `Retry recording`, `Done / Next`;
- làm lại yêu cầu xác nhận nhẹ;
- làm lại thay thế bản thu hiện tại/trước chưa cam kết;
- khi thí sinh chuyển tiếp, câu trước khóa.

Exam/Full Mock:

- không nghe lại;
- không làm lại;
- không điều hướng câu trước;
- không mở lại câu đã hoàn tất.

## 4. Ghi âm, tài sản, chia chunk và lưu câu trả lời

### 4.1 Hợp đồng lưu trữ

Âm thanh thô lưu ngoài PostgreSQL qua lớp tài sản/lưu trữ hiện có. PostgreSQL lưu metadata, quyền sở hữu/nguồn gốc, trạng thái trả lời, thứ tự chunk và tham chiếu tài sản.

Ưu tiên `audio/webm;codecs=opus` khi trình duyệt hỗ trợ, có dự phòng theo khả năng. Không yêu cầu frontend mã hóa WAV.

Tiền xử lý ASR/âm học dẫn xuất có thể chuẩn hóa nội bộ về PCM/WAV mono 16 kHz.

### 4.2 Câu trả lời Speaking

```text
SpeakingResponse
- id
- attempt_id
- prompt_id
- active_take_number
- started_at
- completed_at nullable
- duration_ms
- status
- completion_reason: USER_DONE | TIMEOUT | INTERRUPTED
- locked
- committed_audio_fingerprint nullable
```

Làm lại luyện tập giữ nguồn gốc. Bản thu bị thay không dùng chấm.

### 4.3 Ghi chia chunk

Để khôi phục sự cố, MediaRecorder phải định kỳ phát chunk nhỏ (mục tiêu khoảng 2–5 giây; giá trị cụ thể chọn khi triển khai theo hành vi trình duyệt và chi phí tải).

```text
SpeakingAudioChunk
- id
- response_id
- take_number
- sequence
- asset reference / storage key
- duration_ms nullable
- created_at
```

Tải chunk có tính lũy đẳng theo câu trả lời/bản thu/thứ tự. Thử lại trùng không được nhân đôi âm thanh logic.

Câu trả lời logic cuối có thể biểu diễn bằng bản kê chunk có thứ tự hoặc tài sản dẫn xuất đã ghép; chunk thô giữ làm nguồn gốc trừ khi chính sách lưu giữ chủ động gộp về sau.

## 5. Khôi phục sự cố/tải lại

### 5.1 Thời gian do máy chủ quyết định

Bộ đếm frontend hỗ trợ hiển thị. Backend sở hữu pha hoạt động chuẩn và ảnh chụp thời gian còn lại có thể khôi phục.

Về khái niệm:

```text
SpeakingPromptProgress
- attempt_id
- prompt_id
- state
- phase_started_at
- phase_deadline_at
- last_confirmed_remaining_ms
- interruption_count
- recovery_grace_used_for_current_interruption
- last_resumed_at nullable
```

Có thể gộp lưu trữ cụ thể vào bảng lượt/câu trả lời nếu rõ hơn, nhưng ngữ nghĩa phải tường minh.

Backend cập nhật/suy `last_confirmed_remaining_ms` từ thời gian chuẩn và heartbeat/chunk được chấp nhận. Client tuyệt đối không tự tạo giá trị còn lại lớn hơn.

### 5.2 Hành vi khôi phục

Nếu trình duyệt tải lại/sự cố trong pha hoạt động hợp lệ:

- giữ chunk đã tải;
- khôi phục đúng câu đang hoạt động;
- không đặt lại toàn thời gian gốc;
- khôi phục ảnh chụp thời gian còn lại có giới hạn từ trạng thái gián đoạn/được máy chủ xác nhận cuối;
- tạm dừng tiêu thụ thời gian ảnh chụp khi trình duyệt kết nối lại theo luồng khôi phục;
- cấp đếm ngược ân hạn khôi phục 7 giây sau ứng dụng/micro khôi phục đủ trạng thái để tiếp tục;
- trong ân hạn, hiện câu khôi phục và kết nối/khởi tạo lại micro;
- sau ân hạn, tiếp tục thời gian chuẩn bị/trả lời còn lại đã khôi phục;
- tiếp tục thứ tự chunk/bản thu nhất quán.

Ví dụ: ảnh chụp gián đoạn hợp lệ cuối còn 31 giây. Sau khôi phục thành công, giao diện đếm ngược kết nối/chuẩn bị 7 giây rồi tiếp tục 31 giây còn lại của hạn mức trả lời gốc.

Nếu backend không xác lập trạng thái gián đoạn khôi phục hợp lệ (ví dụ lượt đã chốt hoặc trạng thái lưu không nhất quán), phải từ chối an toàn thay vì tạo thêm thời gian.

### 5.3 Chống lạm dụng

- ân hạn và khôi phục thời gian còn lại do máy chủ cho phép, không do frontend tính;
- tải lại lặp khi khôi phục không được cộng nhiều lần 7 giây hoặc liên tục tua lại thời gian còn;
- câu hoàn thành tuyệt đối không mở lại;
- mỗi chuyển gián đoạn/khôi phục lũy đẳng, gắn kiểm toán được với cùng câu/bản thu;
- ghi sự kiện gián đoạn/khôi phục để gỡ lỗi/kiểm toán mà không lộ log nhạy cảm cho người dùng.

### 5.4 Chunk cuối không khôi phục được

Chunk cuối nhỏ trong bộ nhớ có thể mất khi tiến trình/trình duyệt sập cứng. Chấp nhận được nếu chunk trước đã tải bền vững. Khôi phục không được giả âm thanh thiếu tồn tại. Phân tích chất lượng có thể nêu khoảng thiếu đáng kể về sau nếu cần.

## 6. Phân hệ bản chép lời

Speaking Review cung cấp thao tác `Generate Transcript` riêng.

### 6.1 Tác vụ chép lời

Tạo bản chép lời chạy như tác vụ nền bền vững hoặc tài nguyên xử lý tái dùng, không là yêu cầu đồng bộ dài.

Luồng xử lý:

```text
committed audio
-> quality/readability check
-> ASR
-> word-level timestamps/alignment
-> verbatim transcript
-> clean transcript
-> persist per response
```

Không chấm điểm trong luồng này.

### 6.2 Bản ghi chép lời

Về khái niệm:

```text
SpeakingTranscript
- id
- response_id
- audio_fingerprint
- kind: VERBATIM | CLEAN
- text
- word_timing_json
- asr_provider
- asr_model
- asr_version
- confidence_metadata_json nullable
- status
- generated_at
```

Có thể dùng bảng từ chuẩn hóa hơn nếu trường hợp truy vấn/sử dụng chứng minh cần; JSON đủ cho v1 nếu xác thực và có giới hạn.

### 6.3 Ngữ nghĩa chỉ đọc

Người dùng được xem bản chép nhưng không sửa trước chấm AI.

Bản chép nguyên văn cần giữ điểm không trôi chảy liên quan đánh giá mà ASR phát hiện được, gồm lặp, từ đệm, khởi đầu dang dở và tín hiệu nói chưa hoàn chỉnh.

Bản chép sạch được chuẩn hóa dấu câu/hoa thường/trình bày từ đệm để phân tích ngữ nghĩa nhưng không được sửa ngữ pháp, từ vựng, thì, chọn từ hoặc lỗi ngôn ngữ khác của thí sinh.

### 6.4 Chỉ giao diện từng câu

Xem lại hiện bản chép dưới từng thẻ câu hỏi/trả lời. V1 không yêu cầu xem bản gộp đầy đủ.

Lỗi chép lời được cô lập theo câu khi có thể; một câu lỗi không được bỏ bản chép đã tạo của câu khác.

### 6.5 Tái dùng/vô hiệu hóa

Danh tính cache bản chép gồm dấu vân tay âm thanh cam kết + mô hình/phiên bản/cấu hình ASR/căn chỉnh.

Nếu âm thanh cam kết đổi qua làm lại luyện tập, bản chép cũ không hợp lệ cho chấm mới.

`Grade with AI`:

- tái dùng xử lý bản chép hợp lệ đã hoàn tất;
- chờ/tái dùng tác vụ chép đang hoạt động khớp thay khởi ASR trùng;
- tạo nội bộ bản chép thiếu/lỗi thời khi cần.

## 7. Cổng chất lượng âm thanh

Trước chấm, đánh giá âm thanh có đủ điều kiện chấm không.

Tối thiểu phân biệt các trạng thái tương đương:

```text
AUDIO_OK
NO_SPEECH
TOO_SHORT
AUDIO_CORRUPT
VERY_LOW_SIGNAL
SEVERE_CLIPPING
BACKGROUND_DOMINANT
ASR_UNUSABLE
```

Không biến lỗi kỹ thuật âm thanh thành band tiêu chí IELTS thấp. Nếu không chấm được phát âm vì thu micro không dùng được, trả trạng thái không thể đánh giá/thất bại thay bịa `Pronunciation = 1`.

Kiểm tra chất lượng cần giải thích được và theo ngưỡng, nhưng bản thân ngưỡng không được trở thành quy tắc band IELTS.

## 8. Tiền xử lý lời nói và trích xuất đặc trưng

V1 cần dùng ranh giới nhà cung cấp thay được, không gắn cứng một mô hình nghiên cứu vào logic miền.

### 8.1 Nhà cung cấp ASR/căn chỉnh

Triển khai mặc định thực dụng có thể dùng faster-whisper/Whisper cộng căn chỉnh từ/thời gian kiểu WhisperX. Giao diện nhà cung cấp cần cho thay thế về sau.

Không yêu cầu phân vai người nói cho bản ghi chỉ thí sinh trừ khi về sau ghi âm giám khảo cùng luồng.

### 8.2 Đặc trưng trôi chảy/thời gian

Tính bằng chứng xác định như:

- tổng thời lượng trả lời/lời nói;
- tỷ lệ nói/im lặng;
- từ mỗi phút;
- tốc độ cấu âm;
- số lần ngừng và phân bố độ dài ngừng;
- số/tỷ lệ ngừng dài;
- số khoảng ngừng có từ đệm nếu phát hiện được;
- lặp;
- khởi đầu dang dở;
- tự sửa;
- độ dài lượt trung bình;
- thời lượng nói liên tục Part 2.

Đây là bằng chứng, không công thức chấm cứng.

Không triển khai quy tắc như `pause_count > N => Band X`.

### 8.3 Nhà cung cấp bằng chứng phát âm/âm học

Định nghĩa ranh giới thay được như:

```text
PronunciationEvidenceProvider
```

V1 có thể kết hợp:

- biểu diễn bộ mã hóa lời nói;
- độ tin cậy ASR/căn chỉnh và thời gian âm/từ nơi đáng tin;
- bằng chứng phát âm kiểu GOP nơi áp dụng;
- đặc trưng cao độ/F0, nhịp, trọng âm, thời gian;
- chỉ dấu thay thế lời nói liên kết;
- chỉ dấu khả năng hiểu/nỗ lực người nghe.

Nhà cung cấp trả bằng chứng/đặc trưng có giới hạn, không điểm dữ liệu chưa rà soát ánh xạ trực tiếp sang IELTS.

Nghiên cứu mở như GOPT/SpeechOcean có thể hướng dẫn triển khai/kiểm thử, nhưng tuyệt đối không đổi nhãn tuyến tính điểm phát âm SpeechOcean thành band IELTS.

## 9. Kiến trúc chấm Speaking AI

Speaking Review cung cấp `Grade with AI` riêng. Bản thân nộp bài không tự gọi chấm AI.

### 9.1 Lượt chấm bền vững

Tái dùng triết lý kiến trúc chấm Writing AI:

- bản ghi lượt lưu bền vững;
- worker nền;
- tiến độ/sự kiện bền vững;
- trạng thái SSE/JSON kết nối lại được;
- đóng/tải lại frontend không hủy worker;
- chỉ Stop/hủy chủ động kết thúc tác vụ nơi được hỗ trợ.

Các pha khái niệm:

```text
QUEUED
QUALITY_CHECK
TRANSCRIBING
ANALYSING_AUDIO
BUILDING_EVIDENCE
SCORING
GENERATING_FEEDBACK
COMPLETED
```

với kết quả `FAILED` / `CANCELLED` rõ ràng.

### 9.2 Chấm toàn bộ phần thể hiện

Bốn tiêu chí IELTS đánh giá độc lập trên toàn phần thể hiện Speaking:

- Fluency and Coherence (`fc`);
- Lexical Resource (`lr`);
- Grammatical Range and Accuracy (`gra`);
- Pronunciation (`pr`).

Chỉ số/bằng chứng từng câu/phần có thể hỗ trợ phản hồi, nhưng điểm tiêu chí cuối không được là trung bình số học điểm từng câu hoặc phần.

### 9.3 Nhánh Fluency and Coherence

Đầu vào:

- ngữ cảnh mọi câu hỏi và bản chép trả lời;
- bằng chứng thiếu trôi chảy nguyên văn;
- chỉ số thời gian/trôi chảy;
- ranh giới phần và hành vi lượt dài Part 2;
- ngữ nghĩa mô tả Fluency and Coherence IELTS chính thức.

Đánh giá tổng thể tính liên tục, ngập ngừng, tiến triển, tổ chức diễn ngôn, đặc trưng liên kết/diễn ngôn và khả năng duy trì/phát triển lời nói.

### 9.4 Nhánh Lexical Resource

Đầu vào:

- bản chép toàn lượt;
- ngữ cảnh câu hỏi;
- ngữ nghĩa mô tả LR chính thức.

Đánh giá độ đa dạng, chính xác, phù hợp, khả năng diễn đạt lại, kết hợp từ, kiểm soát ngôn ngữ thành ngữ/ít thông dụng và hạn chế từ vựng toàn lượt.

### 9.5 Nhánh Grammatical Range and Accuracy

Đầu vào:

- bản chép toàn lượt;
- phân đoạn phát ngôn/câu;
- bằng chứng mẫu ngữ pháp xác định tùy chọn;
- ngữ nghĩa mô tả GRA chính thức.

Đánh giá độ đa dạng/linh hoạt cấu trúc, chính xác, mẫu lỗi và hiệu quả giao tiếp. Bộ phát hiện ngữ pháp xác định được cung cấp bằng chứng nhưng không tạo trần điểm cứng.

### 9.6 Nhánh Pronunciation

Pronunciation phải dùng bằng chứng âm thanh. Không để mô hình ngôn ngữ chỉ văn bản gán điểm phát âm chỉ từ kiểu bản chép.

Đầu vào cần bao quát khi có:

- độ rõ/kiểm soát âm đoạn;
- khả năng thay/lược âm hoặc cấu âm không ổn định;
- trọng âm từ/câu;
- nhịp;
- ngữ điệu/chuyển cao độ;
- lời nói liên kết;
- bằng chứng khả năng hiểu tổng thể và nỗ lực người nghe;
- nhất quán trên toàn lượt.

Ngữ nghĩa mô tả Pronunciation IELTS chính thức tiếp tục quyết định chấm; đặc trưng âm học là bằng chứng.

### 9.7 Hợp đồng chấm trước

Áp dụng bài học độ tin cậy từ chấm Writing AI.

Với mỗi tiêu chí:

```text
criterion evidence
-> SCORE ONLY
-> durable valid score
-> feedback generation
```

Đầu ra điểm cần rất nhỏ, về khái niệm:

```json
{"score": 6.5}
```

Dùng xác thực nửa band nghiêm ngặt nhất quán hợp đồng chấm tư vấn dự án. Không dịch điểm, thiên lệch cho rộng, band mặc định dự phòng hoặc tự tạo điểm bằng heuristic.

Nếu giai đoạn điểm vẫn không hợp lệ sau sửa có giới hạn, tiêu chí thất bại rõ ràng.

Nếu phản hồi thất bại sau có điểm hợp lệ:

- giữ điểm;
- giữ bằng chứng xác thực;
- dùng trạng thái/thông điệp phản hồi dự phòng an toàn ngắn;
- không bịa điểm mạnh/cải thiện chi tiết;
- ghi chẩn đoán nội bộ an toàn.

### 9.8 Đầu ra phản hồi

Phản hồi tạo sau và theo điểm đã chốt. Có thể gồm:

- giải thích tiêu chí ngắn;
- số ít điểm mạnh có giới hạn;
- số ít cải thiện có giới hạn;
- tham chiếu bằng chứng câu/phần khi hữu ích.

Đầu ra phản hồi không được chứa trường điểm có thẩm quyền có thể ghi đè điểm số đã chốt.

### 9.9 Band tổng

Bốn điểm tiêu chí trọng số đều theo cấu trúc đánh giá Speaking IELTS. Chỉ tái dùng quy tắc làm tròn nửa band dự án sau xác minh khớp ngữ nghĩa hiển thị tổng Speaking dự kiến.

Mọi đầu ra tự động ghi nhãn rõ tư vấn/không chính thức.

## 10. Cache/dấu vân tay chấm

Danh tính kết quả AI phải đủ nguồn gốc để ngăn tái dùng lỗi thời, gồm:

```text
committed attempt audio fingerprint(s)
response/take revisions
quality-gate version
ASR provider/model/version/config
alignment version
fluency-feature extractor version
pronunciation-evidence provider/version
IELTS speaking rubric/prompt version
score/feedback contract version
```

Đổi bản thu luyện tập cam kết vô hiệu hóa bản chép/đặc trưng/điểm AI phụ thuộc của lượt đó.

Tải lại xem lại với đầu vào không đổi tái dùng hiện vật/kết quả hiện có.

## 11. UX xem lại

Xem lại tổ chức theo Part và câu hỏi.

Mỗi thẻ trả lời có thể hiện:

- câu hỏi/thẻ đề;
- phát âm thanh;
- thời lượng;
- trạng thái ghi/lý do hoàn thành;
- trạng thái tạo bản chép;
- bản chép chỉ đọc khi sẵn sàng;
- lỗi xử lý/chất lượng bản địa hóa.

Thao tác cấp trên:

```text
[ Generate Transcript ]    [ Grade with AI ]
```

Trạng thái bản chép theo câu, ví dụ Ready / Processing / Failed.

Giao diện kết quả AI hiện:

- band tổng tư vấn;
- bốn thẻ điểm tiêu chí;
- phản hồi tiêu chí ngắn;
- điểm mạnh/cải thiện;
- bằng chứng/chỉ số chọn nơi dễ hiểu;
- chỉ số tổng hợp trôi chảy;
- bằng chứng tổng hợp phát âm;
- khả năng phát câu trả lời liên quan khi xem bằng chứng.

Không công khai chuỗi suy nghĩ nội bộ hoặc lý luận mô hình không rõ.

## 12. UX động và chuyển động

Hành vi động là yêu cầu sản phẩm, không là hoàn thiện tùy chọn cuối.

Dùng chuyển động theo trạng thái giúp hiểu ghi/thời gian/tải/khôi phục:

- chuyển vào/ra câu mượt;
- đếm ngược/tiến độ có chuyển động nhẹ;
- chỉ báo ghi trực tiếp và hình mức micro;
- cảnh báo rõ gần hết giờ không nhấp nháy;
- thẻ chuyển Part;
- chuyển Part 2 chuẩn bị -> 3/2/1 -> ghi;
- trạng thái `Saving...` / `Saved` trước chuyển;
- màn hình khôi phục với đếm ngược 7 giây rõ;
- thẻ xem lại mở rộng;
- tiến độ chép lời/chấm AI trực tiếp qua trạng thái/sự kiện bền vững;
- thẻ tiêu chí có thể xuất hiện dần khi hoàn tất kết quả.

Nguyên tắc chuyển động:

- chuyển giao diện khoảng 150–250ms nơi phù hợp;
- không parallax/hạt hoặc chuyển động trang trí gây xao nhãng khi thi;
- chuyển động tuyệt đối không làm chậm chuyển trạng thái/mạng thật;
- tôn trọng `prefers-reduced-motion`;
- giữ khả năng tiếp cận bàn phím/tiêu điểm;
- giữ bố cục ổn định khi thời gian/ghi đổi;
- tuân cá nhân hóa tối/sáng/màu nhấn hiện có;
- không thay màu ngữ nghĩa lỗi/cảnh báo/thành công bằng màu nhấn tùy ý.

## 13. Cấu trúc API/luồng

Tên tuyến cụ thể theo quy ước kho mã. Khả năng bắt buộc gồm:

### 13.1 Builder/admin/giáo viên

- tạo/cập nhật/sắp/xóa phần/câu Speaking trong phiên bản được sửa;
- xác thực mô-đun Speaking trước xuất bản/kiểm duyệt;
- xem trước nội dung Speaking không ghi dữ liệu thi thật.

### 13.2 Lượt làm/thời gian thực hiện

- bắt đầu lượt Speaking từ ngữ cảnh được phép;
- lấy câu/pha/hạn hoạt động hiện tại do máy chủ quyết định;
- khởi tạo/chốt câu trả lời;
- tải chunk âm thanh lũy đẳng;
- khôi phục câu hoạt động gián đoạn;
- đánh dấu hoàn thành `Done / Next` hoặc hết giờ;
- nộp/chốt lượt.

### 13.3 Bản chép lời

Về khái niệm:

```text
POST /speaking-attempts/{attempt_id}/transcript-runs
GET  /speaking-attempts/{attempt_id}/transcript-runs/{run_id}
GET  /speaking-attempts/{attempt_id}/transcript-runs/{run_id}/events
```

hoặc tái dùng tương đương một lớp lượt xử lý tổng quát.

### 13.4 Chấm AI

Về khái niệm:

```text
POST /speaking-attempts/{attempt_id}/ai-grading-runs
GET  /speaking-ai-grading-runs/{run_id}
GET  /speaking-ai-grading-runs/{run_id}/events
POST /speaking-ai-grading-runs/{run_id}/stop
```

Phân quyền, thử lại/cache, thứ tự sự kiện và kết nối lại cần theo mẫu Writing đã được kiểm chứng khi phù hợp.

## 14. Tích hợp Full Mock, lịch sử, phân tích và lớp học

Speaking phải tích hợp như kỹ năng thực, không để thành tuyến phụ.

### 14.1 Full Mock

Về khái niệm, tiến trình Full Mock trở thành:

```text
Listening -> Reading -> Writing -> Speaking
```

Thứ tự/cấu hình cụ thể cần theo kiến trúc phiên thi hiện có. Nguồn gốc lượt/phiên Speaking con phải giữ liên kết Full Mock cha.

### 14.2 Lịch sử

Lịch sử lượt hỗ trợ:

- lượt kỹ năng Speaking;
- nhóm theo đề;
- nhóm Full Mock;
- trạng thái và thời lượng;
- liên kết bản chép/kết quả AI khi có;
- quy tắc xóa/lưu giữ nhất quán quyền sở hữu lượt và chính sách dọn phương tiện hiện có.

### 14.3 Lớp học

Nội dung Speaking giáo viên tạo/giao theo quy tắc sở hữu/kiểm duyệt/phiên bản hiện có khi Speaking được hỗ trợ.

Lượt Speaking bắt nguồn bài giao tiếp tục cho giáo viên xem chỉ đọc qua ranh giới nguồn gốc/bảo mật bài giao hiện có. Không cấp giáo viên truy cập luyện Speaking cá nhân không liên quan.

Truy cập âm thanh thô là nội dung nhạy cảm, phải theo cùng phân quyền nguồn gốc bài giao, không chỉ `student_id + test_id`.

### 14.4 Phân tích

Phân tích ban đầu chỉ có thể cung cấp lịch sử lượt/band Speaking và xu hướng tiêu chí sau khi hợp đồng chấm ổn định. Giai đoạn bộ máy đầu không yêu cầu phân tích lời nói phong phú.

## 15. Bảo mật, riêng tư và lưu giữ

Âm thanh là nội dung giọng nói người dùng tạo, cần xử lý nghiêm hơn câu trả lời văn bản thường.

Yêu cầu:

- truy cập âm thanh/bản chép riêng tư phải xác thực và phân quyền;
- đường lưu/URL tài sản không được là đường bỏ qua phân quyền có thể đoán;
- tránh ghi âm thanh/bản chép thô trong log ứng dụng;
- tuyệt đối không gửi âm thanh/bản chép ra nhà cung cấp ngoài nhiều hơn luồng chấm/chép đã cấu hình cần;
- ghi tài liệu nhà cung cấp/xử lý dữ liệu trước bật ASR đám mây bên thứ ba;
- xóa lượt cần dọn âm thanh/hiện vật dẫn xuất thuộc sở hữu theo ngữ nghĩa xóa hiện có, trừ chính sách yêu cầu giữ (ví dụ lịch sử học tập lớp);
- giáo viên xem lại phải dựa nguồn gốc và chỉ đọc;
- âm thanh thô giữ nguồn chuẩn; bản chép/đặc trưng dẫn xuất tuyệt đối không ghi đè.

## 16. Đồng thời và tính lũy đẳng

Các thao tác sau phải an toàn khi thử lại/nhấp đúp/kết nối lại:

- tải chunk theo `(response, take, sequence)`;
- chốt câu trả lời;
- tranh chấp hết giờ với người dùng `Done`;
- làm lại/thay bản thu luyện;
- tạo quyền khôi phục;
- tạo/tái dùng tác vụ chép;
- tạo/tái dùng tác vụ chấm;
- phát lại/kết nối SSE;
- hủy chấm;
- vô hiệu cache bản chép/điểm sau sửa âm thanh.

Không bản kê chunk trùng, bản thu cam kết trùng, tác vụ chép hoạt động khớp trùng hoặc lượt chấm trùng cùng dấu vân tay chính xác, trừ người dùng chủ động ép lượt mới được hỗ trợ.

## 17. Ngữ nghĩa lỗi

Dùng lỗi miền rõ theo quy ước tên kho mã cho các mã tương đương:

```text
SPEAKING_MODULE_INCOMPLETE
SPEAKING_PART_INVALID
SPEAKING_PROMPT_INVALID
MICROPHONE_REQUIRED
SPEAKING_RESPONSE_NOT_ACTIVE
SPEAKING_RESPONSE_ALREADY_COMPLETED
SPEAKING_RETRY_NOT_ALLOWED
SPEAKING_PREVIOUS_PROMPT_LOCKED
SPEAKING_CHUNK_SEQUENCE_CONFLICT
SPEAKING_RECOVERY_NOT_AVAILABLE
SPEAKING_AUDIO_UNASSESSABLE
TRANSCRIPT_ALREADY_CURRENT
TRANSCRIPT_GENERATION_FAILED
SPEAKING_AI_NOT_CONFIGURED
SPEAKING_AI_GRADING_FAILED
SPEAKING_AI_GRADING_CANCELLED
```

Không lộ văn bản ngoại lệ thô nhà cung cấp cho người dùng cuối.

## 18. Chiến lược kiểm thử

Triển khai dùng TDD theo giai đoạn nhỏ.

### 18.1 Kiểm thử miền/Builder

- tuần tự hóa mô-đun/phần/câu Speaking;
- chuẩn hóa thứ tự;
- xác thực thẻ đề Part 2;
- tích hợp quyền sở hữu/kiểm duyệt giáo viên/admin;
- phiên bản xuất bản bất biến.

### 18.2 Kiểm thử trình làm/trạng thái

- Part 1/3 `Done / Next`;
- hết giờ tự chuyển;
- Part 2 chuẩn bị -> ghi;
- nghe/làm lại luyện so hạn chế thi;
- câu trước cam kết không mở lại;
- phép tính thời gian do máy chủ quyết định.

### 18.3 Kiểm thử chunk/khôi phục

- tải chunk lũy đẳng;
- dựng lại theo thứ tự;
- sự cố với chunk từng phần;
- khôi phục chính xác ảnh chụp thời gian còn lại máy chủ xác nhận;
- ân hạn 7 giây đúng một lần mỗi sự kiện gián đoạn hợp lệ;
- tải lại lặp không thể tích lũy ân hạn hoặc tua thời gian còn;
- tranh chấp chốt.

### 18.4 Kiểm thử bản chép lời

- lưu bản chép từng câu;
- hợp đồng API/UI chỉ đọc;
- bản chép sạch không sửa ngữ pháp thí sinh;
- tái dùng khi dấu vân tay âm thanh khớp;
- làm lại vô hiệu bản chép cũ;
- `Grade with AI` tái dùng tác vụ chép đang hoạt động.

### 18.5 Kiểm thử đặc trưng

- chỉ số trôi chảy xác định từ dữ liệu tổng hợp/nhỏ;
- không ánh xạ cứng một chỉ số sang band IELTS;
- ranh giới nhà cung cấp phát âm nhận bằng chứng âm thanh, không chấp nhận chỉ chấm bản chép là đủ.

### 18.6 Kiểm thử chấm AI

- bốn lần gọi/hợp đồng chỉ điểm tiêu chí độc lập;
- đầu ra điểm nhỏ và xác thực nửa band;
- phản hồi thất bại giữ điểm hợp lệ;
- lỗi điểm tuyệt đối không bịa/mặc định band;
- nhánh Pronunciation yêu cầu bằng chứng âm thanh;
- đầu vào chấm toàn lượt gồm mọi phần, không trung bình điểm câu;
- dấu vân tay cache đổi khi âm thanh cam kết/phiên bản mô hình/rubric đổi;
- đóng/kết nối SSE không hủy worker;
- Stop chủ động hủy theo hợp đồng.

### 18.7 Kiểm thử giao diện

Chỉ kiểm thử thành phần/trạng thái có trọng tâm nơi thực tế:

- trạng thái thiết lập micro;
- trạng thái ghi/thời gian;
- điều khiển làm lại chỉ luyện;
- trạng thái đếm khôi phục;
- hiển thị bản chép từng câu;
- tiến độ xử lý;
- hành vi `prefers-reduced-motion`;
- bản địa hóa và tương thích tối/sáng/màu nhấn.

Tránh trình duyệt/Playwright/E2E trừ giai đoạn sau cho phép rõ. Dự án tiếp tục ưu tiên xác minh có trọng tâm/chi phí thấp.

## 19. Giai đoạn triển khai

Không triển khai toàn Speaking trong một nhiệm vụ Codex. Lập mốc riêng có thể rà soát:

### P1 — Miền + cơ sở dữ liệu + Builder

- schema mô-đun/phần/câu;
- migration;
- CRUD/sắp/tự lưu/xác thực Builder;
- tích hợp quản trị giáo viên/admin/phiên bản;
- cập nhật tài liệu phạm vi/AGENTS kho mã lỗi thời.

### P2 — Trình làm + micro + thời gian

- kiểm tra micro trước bắt đầu;
- trình Part 1/2/3;
- Done/Next và hết giờ;
- điều khiển luyện so với thi;
- giao diện động theo trạng thái.

### P3 — Lưu chunk + khôi phục + xem lại

- tải chunk;
- câu trả lời/bản thu bền vững;
- ân hạn khôi phục 7 giây;
- nghe lại âm thanh khi xem lại;
- lịch sử cơ bản.

### P4 — Luồng chép lời

- chuẩn hóa âm thanh;
- nhà cung cấp ASR/căn chỉnh;
- tác vụ/sự kiện chép lời;
- bản chép nguyên văn/sạch từng câu;
- cache/vô hiệu hóa.

### P5 — Luồng đặc trưng trôi chảy/âm học

- chỉ số trôi chảy xác định;
- trừu tượng nhà cung cấp phát âm/âm học;
- cổng chất lượng;
- lưu đặc trưng/bằng chứng.

### P6 — Bộ chấm Speaking AI IELTS kết hợp

- bốn bộ dựng bằng chứng tiêu chí;
- hợp đồng chấm trước;
- tạo phản hồi;
- lượt chấm/SSE bền vững;
- giao diện xem lại tư vấn.

### P7 — Tích hợp Full Mock / lịch sử / lớp

- tích hợp lượt con Full Mock;
- tích hợp lịch sử By Skill / By Test / By Mock;
- nguồn gốc bài giao/kết quả lớp;
- quyền xem lại âm thanh/bản chép.

### P8 — Công cụ đánh giá chuẩn và hiệu chỉnh

- định dạng nhập bộ đánh giá người gán nhãn;
- đánh giá ngoại tuyến;
- so hiệu chỉnh/phiên bản;
- thử nghiệm thay mô hình.

## 20. Đánh giá và hiệu chỉnh

V1 có thể chấm tư vấn theo mô tả, nhưng suy luận thành công đơn thuần chưa chứng minh độ tin cậy so giám khảo IELTS con người.

Trước tuyên bố chính xác ngang người, xây tập đánh giá có nhãn và báo chỉ số từng tiêu chí/tổng như:

- MAE/RMSE;
- tương quan Pearson/Spearman;
- Quadratic Weighted Kappa;
- phần trăm trong ±0.5 band;
- phần trăm trong ±1.0 band;
- tỷ lệ lỗi/không đủ điều kiện chấm;
- kiểm tra nhóm theo giọng/L1/chất lượng âm thanh tại nơi có ý nghĩa đạo đức và thống kê.

Kho công khai như Speak & Improve giúp xác thực kiến trúc/nghiên cứu tiền huấn luyện nhưng không tự cung cấp nhãn chuẩn IELTS. SpeechOcean/L2-ARCTIC hữu ích nghiên cứu phát âm/giọng, không để hiệu chỉnh band IELTS trực tiếp.

Dữ liệu mẫu đánh giá phải giữ ngoại tuyến; kiểm thử triển khai không được gọi ASR/LLM/GPU đám mây thật trừ khi yêu cầu rõ.

## 21. Nội dung rõ ràng ngoài v1

- không giám khảo AI thích ứng tự chọn câu mới;
- không giám khảo avatar/video hội thoại trực tiếp;
- không tuyên bố 60 giây mỗi câu Part 1/3 là quy tắc IELTS chính thức cố định;
- không cho người dùng sửa bản chép trước chấm;
- không giao diện bản chép gộp toàn bộ;
- không tự chấm ngay khi nộp;
- không ánh xạ trực tiếp điểm SpeechOcean/GOPT sang band IELTS Pronunciation;
- không huấn luyện/tinh chỉnh bộ chấm production trước công việc dữ liệu có nhãn/đánh giá;
- không trung bình band từng câu;
- không suy điểm phát âm chỉ từ văn bản;
- không phân tích Speaking phong phú toàn tổ chức trong mốc bộ máy đầu.

## 22. Tiêu chí nghiệm thu kiến trúc

Kế hoạch triển khai phải giữ các bất biến:

1. Speaking là kỹ năng thi chính thức gồm ba phần theo thứ tự.
2. Builder nối/sắp câu bằng ID ổn định + `order_index`.
3. Câu thi/hiện tại ghi với thời gian do máy chủ quyết định.
4. `Done / Next` cam kết trước chuyển; hết giờ tự cam kết/chuyển.
5. Practice được làm lại câu hiện tại; Exam/Full Mock không nghe/làm lại.
6. Khôi phục giữ chunk trước, khôi phục ảnh chụp thời gian còn lại máy chủ xác nhận và cấp một ân hạn kết nối lại 7 giây có giới hạn trước tiếp tục thời gian đó.
7. Âm thanh thô ở lưu trữ tài sản, giữ nguồn chuẩn.
8. Bản chép theo câu, chỉ đọc, không được cải thiện ngữ pháp thí sinh.
9. `Generate Transcript` và `Grade with AI` là thao tác riêng; chấm có thể tự tái dùng/tạo bản chép.
10. Chấm AI toàn lượt, bốn tiêu chí, chấm trước và chỉ tư vấn.
11. Pronunciation yêu cầu bằng chứng từ âm thanh.
12. Điểm tiêu chí hợp lệ giữ qua lỗi phản hồi; tuyệt đối không bịa điểm không hợp lệ.
13. Tác vụ/sự kiện bền vững tồn tại qua tải frontend; Stop chủ động là ranh giới hủy.
14. Giao diện động làm rõ tiến độ ghi/thời gian/tải/khôi phục/AI, tôn trọng giảm chuyển động/khả năng tiếp cận.
15. Tích hợp Full Mock/lịch sử/lớp dùng nguyên tắc nguồn gốc/phân quyền hiện có, không tạo mô hình bảo mật song song.
16. Tuyên bố độ chính xác ngang giám khảo người cần bộ đánh giá có nhãn thực, không ví dụ đơn lẻ.
