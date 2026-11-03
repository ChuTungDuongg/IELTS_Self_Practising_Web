# Chép lời Speaking và bằng chứng hybrid

<a id="speaking-hybrid-v1"></a>

## Azure unscripted + CPU VAD (opt-in)

Bổ sung working tree trên `3cf5c9a`: chọn `SPEAKING_PROFILE=speaking_hybrid_v1`
rõ ràng. Default vẫn `legacy`; phần faster-whisper và acoustic proxies bên dưới
chỉ mô tả legacy. Không có production switch hoặc benchmark live trong lần này.

```dotenv
SPEAKING_PROFILE=speaking_hybrid_v1
SPEAKING_ASR_ENABLED=true
SPEAKING_AZURE_KEY=<backend-secret-only>
SPEAKING_AZURE_REGION=<your-approved-region>
SPEAKING_AZURE_LOCALE=en-US
SPEAKING_AZURE_PROSODY=true
SPEAKING_AZURE_TIMEOUT_SECONDS=180
SPEAKING_AZURE_MAX_CONCURRENCY=2
SPEAKING_AZURE_MAX_QUEUE=8
SPEAKING_VAD_MODEL_PATH=<absolute-local-path-to-silero-v6.0.onnx>
SPEAKING_VAD_MODEL_SHA256=597d30b3ec076608d059477bb14cfeffdf951bf5cae370d38f65d33bbfe82004
```

Azure Speech SDK tùy chọn ghim `azure-cognitiveservices-speech==1.53.0`; CPU VAD
dùng `onnxruntime==1.23.2`, `numpy==2.2.6`. Không dùng `speech` extra faster-whisper
cho profile hybrid. Trên Debian Bookworm cần `libasound2`, `libssl3`,
`ca-certificates` và `ffmpeg`. [CPU Modal preset](modal-web.md#speaking-hybrid-cpu)
cài riêng các dependency này. Local dùng
`uv sync --extra azure-speech --extra speech-vad` từ `backend/`.

Setup model là hành động operator rõ ràng từ repository root:

```powershell
backend/.venv/Scripts/python.exe scripts/setup_speaking_vad.py storage/models/silero-v6.0.onnx
```

Script chỉ tải Silero v6.0 ONNX tại commit
`fba061dc5559f696e62171e9a0741782b0fdc23c`, kiểm SHA-256 trên rồi lưu binary
trong `storage/` đã bỏ qua. Không có request-time/model startup download;
không nạp torch/CUDA. Asset thiếu, checksum sai hoặc ONNX unavailable tạo
bằng chứng VAD unavailable và hạn chế FC, không giả silence hoặc điểm band.

`analyze_response` giữ một phiên continuous recognition cho mỗi segment/take.
Chỉ final events góp vào lexical transcript; interim không thành dữ liệu đã
chốt. SDK không nhận reference transcript và không bật miscue/read-aloud
completeness. `SpeechAnalysisResult` giữ lexical/display text riêng, word/
utterance/observation IDs, timing millisecond, capability và coverage, native
call outcome/usage, version/config fingerprint và limitations. Không suy SDK
service model version, missing phonemes, confidence hoặc prosody từ trường khác.
Native work có deadline, concurrency và admission queue hữu hạn; cancellation/
timeout/partial stream không được quảng cáo là hoàn tất và không blind retry.

Chuẩn hóa giữ timeline từng recorder segment, take và normalized interval;
không trim leading/trailing audio và không chèn recovery grace thành silence.
Offsets Azure trong một stream được ánh xạ vào normalized/response timeline;
recovery gap không biết thời lượng vẫn unknown. VAD đo trong response window
sau preparation. WPM, articulation rate và internal pauses dùng mẫu số riêng;
silence đầu/cuối hoặc qua recovery boundary không thành internal pause.
Filler/repetition/repair/false-start markers từ lexical text vẫn là heuristic;
ASR có thể không giữ các disfluencies này. VERBATIM giữ lexical output nhận
được, CLEAN chỉ gộp whitespace, không sửa grammar hoặc bảo đảm nhận đúng mọi từ.

Speech checkpoint nằm trong metadata JSONB riêng của normalized response và
không phụ thuộc prompt Luna. Checkpoint complete có thể tái dùng; partial/failed
và attempted có billing chưa rõ được lưu trạng thái riêng để tránh tự phát lại
call tính phí. Các feature/scorer fingerprints vẫn riêng; legacy records không
bị viết lại. Key/raw response/audio không đưa vào log hoặc browser DTO. Quyền
đọc/replay vẫn qua FastAPI theo ownership/classroom và Full Mock review lock.
Xem [privacy, cost assumptions và evaluation](ai-speaking.md) trước xử lý dữ
liệu thật. **LIVE_UNVERIFIED**: chưa xác nhận Azure account, unscripted fidelity,
false positives, band agreement, latency hoặc chi phí thực.

## Hồ sơ triển khai legacy

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: mô tả xử lý bản chép lời Speaking mở rộng miền ghi âm riêng tư P3 và không cấp điểm IELTS. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../backend/app/services/speaking_transcript_worker.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/speaking.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải kết quả chạy lại trong đợt kiểm toán này.

Xử lý bản chép lời Speaking mở rộng miền ghi âm riêng tư P3, không cấp điểm IELTS.

Bộ chuẩn hóa giải mã từng bộ chứa MediaRecorder độc lập, chỉ nối các đoạn dữ liệu trong cùng bộ chứa. FFmpeg lấy mẫu lại từng đầu vào trước khi nối PCM mono 16 kHz có dấu 16 bit. Tệp gốc không bị ghi lại. Bộ tách luồng đầu vào và giao thức được giới hạn; lệnh dùng mảng đối số, thời gian chờ và giới hạn đầu ra/thời lượng. Đầu ra tiến trình con bị bỏ, không ghi nhật ký. Tệp phái sinh nằm trong `storage/speaking-derived` và được quản lý bởi hàng đợi dọn dẹp khi xóa có tính giao dịch.

Danh tính bộ nhớ đệm chuẩn hóa gồm dấu vân tay âm thanh đã chốt, định dạng, phiên bản bộ chuẩn hóa và giới hạn thời lượng. Danh tính chép lời bổ sung nhà cung cấp/mô hình/phiên bản/cấu hình ASR và phiên bản định dạng tất định. Khóa duy nhất lượt làm bài/bộ nhớ đệm cùng khóa lượt làm bài cha ngăn công việc trùng; khóa lượt xử lý và quyền xử lý tạm thời có rào chắn bảo vệ điểm kiểm tra của worker. Bản chép lời thành công của từng câu trả lời vẫn giữ khi câu khác thất bại hoặc thử lại. Công việc chờ được khôi phục khi ứng dụng khởi động lại; quyền xử lý cũ có thể được nhận lại. SSE theo dõi sự kiện đã lưu, không sở hữu hoặc hủy worker.

VERBATIM giữ nguyên văn bản nhà cung cấp. CLEAN chỉ gộp khoảng trắng, không đổi ngữ pháp, từ vựng, thì, mạo từ, từ đệm, lặp lại hoặc câu khởi đầu bị bỏ dở. Chỉ âm thanh đã chốt được gửi vào nhà cung cấp; ghi chú riêng lúc làm bài không đi vào đầu vào xử lý. Mốc thời gian từng từ và kích thước văn bản được kiểm tra. Lỗi nhà cung cấp chuyển thành mã trong danh sách cho phép; tải sự kiện chứa trạng thái/định danh câu trả lời, không chứa bản chép lời. Mỗi lần đọc đều kiểm tra chủ sở hữu hoặc nguồn gốc bài giao hiện có. Giáo viên giao bài chỉ được đọc và không thể yêu cầu tạo bản chép lời.

Chép lời mặc định bị tắt. Phụ thuộc và thao tác nhập mô-đun cơ bản không cài hoặc nạp mô hình tiếng nói. Gói tùy chọn `speech` khai báo faster-whisper; gói này chưa được cài trong lần xác minh phát triển. Để bật xử lý trong môi trường cục bộ đã chuẩn bị riêng, cấu hình:

```dotenv
SPEAKING_ASR_ENABLED=false
SPEAKING_ASR_MODEL_DIRECTORY=
SPEAKING_ASR_MODEL=local-model
SPEAKING_ASR_VERSION=faster-whisper-v1
SPEAKING_ASR_LANGUAGE=en
SPEAKING_NORMALIZER_VERSION=pcm-v1
SPEAKING_FFMPEG_PATH=ffmpeg
SPEAKING_PROCESSING_TIMEOUT_SECONDS=120
SPEAKING_MAX_DECODED_SECONDS=600
SPEAKING_TRANSCRIPT_STALE_SECONDS=300
```

Dùng thư mục mô hình đã chuyển đổi đầy đủ sẵn có, gồm model.bin, config.json, tokenizer.json và preprocessor_config.json. Bộ tiếp hợp từ chối thư mục thiếu trước khi nhập gói tùy chọn, đồng thời yêu cầu CPU/int8 với `local_files_only=True`. Kiểm tra tokenizer rõ ràng cũng chặn cơ chế dự phòng tokenizer của hàm khởi tạo thư viện. Xem [hàm khởi tạo faster-whisper chính thức](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py). Tăng phiên bản mô hình/bộ tiếp hợp khi thay nội dung mô hình cục bộ. Không bật ASR đám mây.

Kiểm thử thường dùng byte/WAV tổng hợp và bộ tiếp hợp ASR/tiến trình con giả. Chúng không chạy FFmpeg, tải mô hình hoặc suy luận tiếng nói trực tiếp. Kiểm thử migration và PostgreSQL phải đạt trước khi coi giai đoạn chép lời hoàn tất.

Cổng kiểm tra chất lượng chạy trước ASR và lưu bằng chứng có phiên bản trong siêu dữ liệu tệp chuẩn hóa. Nó phân biệt AUDIO_OK, NO_SPEECH, TOO_SHORT, AUDIO_CORRUPT, VERY_LOW_SIGNAL, SEVERE_CLIPPING, BACKGROUND_DOMINANT và ASR_UNUSABLE. `SPEAKING_QUALITY` chấp nhận cấu hình JSON ghi đè trong giới hạn. Mặc định dùng năng lượng khung 20 ms để đo hoạt động và hoạt động đổi dấu ở mức cao kéo dài làm chỉ báo tiếng ồn nền. Đây là chỉ báo kỹ thuật tất định, không phải VAD đã huấn luyện hoặc nhận biết lời nói có ngôn ngữ; cần hiệu chuẩn bằng bản ghi đại diện. Ngưỡng chỉ phân loại khả năng sử dụng về mặt kỹ thuật, không sinh điểm IELTS. Cấu hình chất lượng tham gia danh tính bộ nhớ đệm chép lời.

Thời lượng đã giải mã chỉ chứa âm thanh được chấp nhận. Chuẩn hóa nhiều bộ chứa ghi số phân đoạn; không có ranh giới khoảng trống khôi phục vật lý. Khoảng bù kết nối lại bảy giây không bao giờ được chèn vào âm thanh chuẩn hóa hoặc hạn mức nói. Nguồn gốc thô và ghi chú riêng nằm ngoài hợp đồng đầu vào chất lượng.

Bằng chứng độ lưu loát dùng VERBATIM và mốc thời gian căn chỉnh đúng token. WPM đếm từ nguyên văn trên thời lượng âm thanh được chấp nhận; tốc độ phát âm đếm cùng số từ trên tổng thời lượng các từ đã căn chỉnh. Mốc thiếu/không khớp khiến bằng chứng nói/im lặng/tốc độ phát âm/khoảng ngừng không khả dụng. Khoảng ngừng là khoảng cách giữa từ từ 0.25 s; khoảng ngừng dài từ 2 s, và tỷ lệ ngừng dài là phần số khoảng ngừng được phát hiện có độ dài này. Lượt nói gồm các từ giữa hai khoảng ngừng dài, kể cả khoảng ngắn hơn. Thời lượng nói liên tục Part 2 là lượt dài nhất như vậy, chỉ áp dụng cho LONG_TURN do người soạn quy định. Bộ chứa khôi phục thiếu độ lệch ranh giới đáng tin cậy không có bằng chứng khoảng ngừng/lượt nói; thời lượng giải mã vẫn loại khoảng bù kết nối. Từ um/uh, lặp token/cụm từ, dấu gạch biểu thị khởi đầu bỏ dở và “I mean” được ghi rõ là chỉ báo từ văn bản.

Nhà cung cấp phát âm có thể thay thế yêu cầu WAV chuẩn hóa đọc được thực sự. Bản cơ sở nhẹ đo cao độ/tự tương quan trên khung 40 ms có giới hạn, biến thiên RMS/năng lượng từ và tóm tắt thời lượng/khoảng cách/độ tin cậy căn chỉnh. Mặc định cao độ được lấy mẫu tất định từ tối đa 128 khung hoạt động. Độ tin cậy ASR được ghi rõ là chỉ báo mức dễ hiểu, kèm độ bao phủ; không phải độ chính xác ngữ âm hoặc điểm IELTS. Căn chỉnh thiếu/độ tin cậy thấp trả LOW_EVIDENCE. Nhà cung cấp bị tắt hoặc âm thanh không dùng được trả UNAVAILABLE. Thay thế âm vị, trọng âm ngôn ngữ và nỗ lực nghe được đặt null rõ ràng vì bản cơ sở không đủ khả năng chứng minh. Các chỉ báo này cần hiệu chuẩn dữ liệu thật trước khi đưa ra nhận định mạnh hơn.

`SPEAKING_PRONUNCIATION` chấp nhận JSON ghi đè trong giới hạn; `SPEAKING_PRONUNCIATION_ENABLED=false` vẫn cho phép chép lời và ghi rõ phần phát âm không khả dụng. Phiên bản/cấu hình nhà cung cấp và đặc trưng tham gia danh tính lượt xử lý. Các gói chất lượng/độ lưu loát/phát âm được lưu nguyên tử cùng mỗi cặp VERBATIM/CLEAN trong siêu dữ liệu nhà cung cấp riêng tư, có dấu vân tay bao phủ âm thanh, bản chép lời/căn chỉnh, chất lượng, cấu hình đặc trưng/nhà cung cấp và ngữ cảnh bài nói dài. Bản thân chép lời không chấm điểm; [quy trình chấm tư vấn](speaking-grading.md) riêng sử dụng bằng chứng này.

Mốc thời gian từ phải hữu hạn, không âm, đúng thứ tự và không chồng lấn; điểm cuối không vượt thời lượng giải mã. Siêu dữ liệu nhà cung cấp không hợp lệ/chồng lấn khiến câu trả lời thất bại an toàn thay vì trở thành bằng chứng thời gian. Tiêu đề/nội dung/thời lượng WAV trong bộ nhớ đệm được xác minh trước khi tái sử dụng; tệp phái sinh thiếu/hỏng được dựng lại, đường dẫn cũ vào hàng đợi dọn dẹp. Đầu vào gốc thiếu/hỏng/vượt đường dẫn cho phép bị từ chối an toàn. Bản chép lời lịch sử bị ẩn khi dấu vân tay âm thanh không còn khớp câu trả lời đã chốt.
