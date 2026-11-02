# Kế hoạch triển khai Speaking — Các sửa đổi sau tự rà soát

> **Kiểm toán tài liệu: CURRENT.** Đây là nguồn chuẩn cho phạm vi này; đã đối chiếu ranh giới/API với mã nguồn, chưa xác thực trên môi trường đang chạy.
> Mục đích: Kế hoạch triển khai Speaking — Các sửa đổi sau tự rà soát. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/services/speaking_attempts.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/speaking.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.
> Các chỉ dẫn Speaking vẫn có tính ràng buộc theo AGENTS; không lưu trữ hoặc vô hiệu hóa các sửa đổi sau tự rà soát.

> **Tài liệu đi kèm có tính ràng buộc của:** `docs/superpowers/plans/2026-10-11-speaking-engine-ai-grading.md`
>
> Các tác nhân triển khai phải đọc tệp này cùng đặc tả thiết kế đã được phê duyệt và kế hoạch triển khai chính. Các sửa đổi này giải quyết vấn đề phát hiện trong bước tự rà soát kế hoạch bắt buộc; khi cách diễn đạt xung đột, tệp này được ưu tiên.

## 1. Sửa phụ thuộc P4/P5: chuẩn hóa âm thanh phải diễn ra trước ASR

Kế hoạch chính hiện khai báo kiểu cho hợp đồng ASR ở P4 là `SpeechASRProvider.transcribe(audio: NormalizedAudio)` nhưng đến P5 mới tạo `normalize_committed_take(...) -> NormalizedAudio`. Thứ tự đó không hợp lệ.

Sửa các nhiệm vụ theo giai đoạn như sau:

- **Nhiệm vụ 9 (P4)** đồng thời tạo ranh giới chuẩn hóa tối thiểu `backend/app/services/speaking_audio.py` mà việc tạo bản chép lời cần đến.
- Nhiệm vụ 9 phải ghép bản kê segment/chunk đã cam kết theo thứ tự và tạo **16 kHz mono PCM/WAV `NormalizedAudio`** có giới hạn thông qua FFmpeg (hoặc thành phần giả lập tương đương trong kiểm thử đơn vị) trước khi gọi ASR.
- Âm thanh/chunk thô đã tải lên vẫn là hiện vật nguồn chuẩn bất biến; chuẩn hóa tạo hiện vật/bộ đệm dẫn xuất với khóa gồm dấu vân tay âm thanh đã cam kết + phiên bản bộ chuẩn hóa.
- Kiểm thử Nhiệm vụ 9 phải bao quát thứ tự bản kê, việc gọi bộ chuẩn hóa/an toàn đường dẫn, danh tính bộ đệm và việc ASR nhận âm thanh đã chuẩn hóa. Không chạy tích hợp FFmpeg/Whisper thật trong xác minh thường lệ.
- **Nhiệm vụ 11 (P5)** không còn tạo `speaking_audio.py` từ đầu. Nhiệm vụ này **mở rộng** dịch vụ chuẩn hóa P4 bằng đầy đủ chỉ số kiểm soát chất lượng/khả năng đọc và tạo `speaking_quality.py` theo kế hoạch.

Điều này giữ đúng trình tự triển khai dự kiến (`transcript` trước phân tích âm học/độ trôi chảy sâu hơn) mà không khiến P4 phụ thuộc vào một kiểu dữ liệu chỉ xuất hiện ở P5.

## 2. Ghi chú nháp Part 2 chỉ thuộc thời gian làm bài và bị loại khỏi chấm điểm

Bổ sung các bất biến bắt buộc sau vào Nhiệm vụ 4/5 và kiểm thử tương ứng:

- Phần chuẩn bị Part 2 có thể cung cấp vùng ghi chú nháp cho thí sinh.
- Ghi chú chỉ là dữ liệu tiện ích trong thời gian thực hiện lượt làm bài; chúng không phải nội dung đề được biên soạn.
- Tuyệt đối không thêm ghi chú vào bản chép lời ASR, bằng chứng của tiêu chí, lời nhắc chấm điểm LLM, bằng chứng phát âm hoặc kết quả AI cuối cùng.
- Nếu lưu ghi chú để khôi phục sau sự cố, phải giới hạn chúng theo lượt làm bài/câu hỏi Part 2 hiện tại, phân quyền như dữ liệu riêng tư của lượt làm bài và không đưa vào đầu vào nhà cung cấp chấm điểm.
- Khôi phục Exam/Full Mock có thể khôi phục ghi chú nháp nhưng không thay đổi ngữ nghĩa khôi phục 7 giây hoặc thời gian nói.

Bổ sung kiểm thử backend/frontend có trọng tâm chứng minh một chuỗi ghi chú nháp đặc trưng không thể xuất hiện trong đầu vào chép lời/chấm điểm tạo từ cùng lượt làm bài.

## 3. Làm rõ các tranh chấp đồng thời khi chốt câu trả lời

Kiểm thử Nhiệm vụ 4/7 phải bao gồm các tình huống tranh chấp mà đặc tả yêu cầu, không chỉ luồng thành công:

- `Done / Next` chạy đua với thời điểm hết hạn do máy chủ quyết định chỉ cam kết **một** trạng thái trả lời cuối cùng.
- Yêu cầu chốt trùng lặp phải có tính lũy đẳng, không tạo bản thu/chunk trùng và không chuyển qua hai câu hỏi.
- Retry trong luyện tập chạy đua với việc chốt không được thay thế câu trả lời sau khi câu đó đã được cam kết/khóa.
- Khôi phục không được mở lại câu trả lời vừa được chốt đồng thời bởi yêu cầu khác.

Sử dụng các mẫu giao dịch/khóa/tính lũy đẳng của cơ sở dữ liệu đã có trong kho mã; tuyệt đối không chỉ giải quyết các tranh chấp này bằng trạng thái frontend.

## 4. Xóa/lưu giữ lượt làm bài phải bao gồm hiện vật lời nói riêng tư

Bổ sung yêu cầu cho Nhiệm vụ 6 và 17:

- Xóa lượt làm bài cá nhân phải dọn dẹp hoặc đưa vào hàng đợi dọn dẹp các chunk/segment Speaking thô thuộc sở hữu, âm thanh dẫn xuất đã ghép/chuẩn hóa, bản chép lời, hiện vật đặc trưng và hiện vật lượt chạy Speaking AI theo ngữ nghĩa xóa hiện có của kho mã.
- Không để lại tệp phương tiện mồ côi có thể đoán được sau khi hàng phân quyền trong cơ sở dữ liệu bị xóa.
- Nếu chính sách lịch sử học tập của bài giao/lớp học cấm xóa lượt làm bài bắt nguồn từ bài giao, phải giữ nhất quán cả lượt làm bài và các hiện vật lời nói cần thiết, không xóa phương tiện trong khi vẫn giữ lịch sử.
- Dọn dẹp phải giới hạn theo quyền sở hữu/tham chiếu; tuyệt đối không xóa đối tượng lưu trữ vẫn được lượt làm bài/hiện vật đang lưu giữ tham chiếu.

Bổ sung kiểm thử có trọng tâm vào các đích kiểm thử xóa/lịch sử lượt làm bài hiện có cho: dọn dẹp khi xóa Speaking cá nhân, bảo toàn lịch sử bài giao và ngăn dọn dẹp chéo lượt làm bài trái phép.

## 5. Hợp đồng bảo mật/lỗi phải rõ ràng xuyên suốt các nhà cung cấp mới

Trong Nhiệm vụ 6, 9, 11 và 14:

- tuyệt đối không ghi nhật ký byte âm thanh thô, nội dung bản chép lời, ghi chú nháp thí sinh, nội dung yêu cầu nhà cung cấp hoặc văn bản ngoại lệ tùy ý từ nhà cung cấp;
- khóa/URL lưu trữ riêng tư không phải token phân quyền;
- nhà cung cấp ASR/phát âm đám mây tiếp tục bị vô hiệu hóa cho đến khi cấu hình xử lý dữ liệu của chúng được ghi thành tài liệu;
- ánh xạ lỗi sang ngữ nghĩa miền đã được phê duyệt (`SPEAKING_CHUNK_SEQUENCE_CONFLICT`, `SPEAKING_RECOVERY_NOT_AVAILABLE`, `SPEAKING_AUDIO_UNASSESSABLE`, các mã thất bại/hủy tạo bản chép lời và chấm AI), không làm lộ lỗi backend/nhà cung cấp.

## Kết quả tự rà soát

Với các sửa đổi trên, thứ tự phụ thuộc của kế hoạch trở nên nhất quán:

```text
P1 authored content
 -> P2 attempt/recorder state
 -> P3 durable private media + recovery
 -> P4 normalized audio + transcript
 -> P5 quality/fluency/pronunciation evidence
 -> P6 score-first AI grading
 -> P7 product integration
 -> P8 benchmark/calibration
```

Năm lĩnh vực rủi ro cao nhất của thiết kế đã được phê duyệt hiện có trách nhiệm kiểm thử rõ ràng: tính lũy đẳng của phương tiện chia đoạn, ngăn lợi dụng thời gian khôi phục/tranh chấp chốt câu trả lời, phân quyền/dọn dẹp vòng đời phương tiện riêng tư, lỗi ASR/âm thanh không đủ điều kiện chấm và worker chép lời/AI bền vững tiếp tục hoạt động sau khi trình quan sát frontend kết thúc.
