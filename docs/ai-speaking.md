# Kiến trúc và đánh giá Speaking của BandPilot

## Profile `speaking_hybrid_v1` (opt-in)

Mặc định vẫn là provider local/profile legacy. `SPEAKING_ASR_PROVIDER=azure` chọn
profile `speaking_hybrid_v1`; tên canonical của credential là `SPEAKING_AZURE_KEY`. Mặc định
`SPEAKING_LEXICAL_ASR_PROVIDER=azure_pa` dùng **một phiên Azure unscripted cho mỗi đoạn ghi liên tục**,
dùng chung transcript/timing/observations. Operator có thể chọn ASR lexical độc lập
theo [cấu hình transcription](speaking-transcription.md#independent-lexical-asr).
CPU Silero ONNX đo hoạt động nói trên timeline trong cả hai chế độ.
`SpeechAnalysisResult` có phiên bản, capability/coverage, nguồn gốc, usage và
limitations rõ ràng. Không gửi reference text hoặc human band vào Azure/Luna;
không dùng completeness/read-aloud penalty. en-US là locale kỹ thuật mặc định,
không phải yêu cầu thí sinh nói giọng Mỹ. Recognition confidence không phải
pronunciation accuracy; điểm Azure 0–100 không đổi số học sang band IELTS.

Luna tiếp tục chấm holistic ở cấp lượt theo FC/LR/GRA/PR, lưu điểm trước nhận
xét. VAD và provider observations là bằng chứng, không phải quy tắc trừ band.
Thiếu VAD, timeline hoặc độ bao phủ âm học làm FC/PR không đủ điều kiện; không
bịa điểm mặc định hoặc trừ vì accent khác. Chỉ đủ bốn tiêu chí mới có overall.
Nhận xét gắn evidence IDs được backend xác thực; replay chỉ dùng tuyến âm thanh
riêng tư đã phân quyền. Điểm người có quyền nhập vẫn có thẩm quyền.

Speech cache gắn nguồn âm thanh, segment/take mapping và identity/config Azure;
không phụ thuộc prompt Luna. Feature/AI cache vẫn có phiên bản riêng. Checkpoint
speech dùng JSONB riêng tư hiện có; byte âm thanh vẫn ở asset storage. Prompt đổi
có thể chấm lại từ speech evidence đã lưu. Thay provider/locale/config/model cần
cache identity mới. Bản ghi lịch sử/legacy vẫn đọc được. Interrupted billable
requests có trạng thái chưa rõ cần đối soát, không tự gọi lại âm thầm.
CLI hybrid `--resume` cũng giữ checkpoint đã bắt đầu speech analysis, kể cả
band chưa đủ hoặc LLM thất bại; không tự gửi lại audio. Sau đối soát, operator
chọn run/output mới một cách rõ ràng nếu chấp nhận chi phí mới. Flag bắt đầu
orchestration không phải số call đã xác nhận hoặc hóa đơn Azure.

ASR có thể bỏ fillers, repetition hoặc false starts; tên VERBATIM nghĩa là giữ
lexical text nhận được, **không bảo đảm nguyên văn lời nói thật**. Marker lexical
là heuristic; stress/phoneme/prosody và provider error flags có thể thiếu hoặc
sai, đặc biệt giữa các accent. Unknown không được biến thành lỗi của thí sinh.
Trước production cần cohort human-labelled đại diện, DEV/HOLDOUT tách speaker,
kiểm false positives và eligibility. Profile không tự bật ở production; xem
[cấu hình/rollback](modal-web.md#speaking-hybrid-cpu) và [transcription](speaking-transcription.md#speaking-hybrid-v1).
Các mô tả faster-whisper/acoustic baseline bên dưới áp dụng profile legacy.

### Nguồn lexical độc lập và nguyên nhân đã xác nhận (2026-11-06)

Đã xác nhận bằng trace và test hư cấu: parser cũ xây toàn bộ utterance và acoustic
observations trong một đường parse; phoneme/observation tùy chọn sai có thể khiến
utterance lexical hợp lệ bị bỏ. GRA còn lấy `SpeechAnalysisResult.utterances` của PA
ghi đè utterances canonical. Cache trước đây chỉ có một nguồn speech, nên không thể
thay model lexical mà vẫn tái dùng PA một cách tường minh. Đây là lỗi/coupling trong
code; chưa chứng minh chúng giải thích mọi lỗi nhận dạng của audio người dùng.

Microsoft xác nhận PA dùng model STT khác regular Azure STT trong
[tài liệu pronunciation assessment](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-pronunciation-assessment).
Điều này là lý do cần so sánh trên cùng audio, không phải bằng chứng Azure STT hay
Whisper chính xác hơn đối với giọng Việt. Không đổi PA thành scripted assessment,
không gửi transcript ASR độc lập làm reference cho PA.

```text
Normalized candidate PCM (cùng bytes / từng recorder segment)
  -> lexical ASR được chọn -> canonical text + timings + uncertainty -> LR / GRA / FC lexical
  -> Azure unscripted PA  -> PA words + phoneme / accuracy / prosody -> PR
  -> CPU Silero VAD       -> speech activity / real pauses           -> FC temporal
```

Ở `azure_pa`, lexical và acoustic là cùng request; ở `azure_stt` là hai request speech
riêng. `faster_whisper_local` tái dùng adapter CPU local, và `faster_whisper_modal` gọi
endpoint T4 đã được operator triển khai riêng. Chọn tên provider không deploy/start
GPU, tải model hoặc thêm Whisper vào image CPU. Không tự chuyển provider khi lỗi.

`features.lexical_analysis` giữ evidence lexical riêng; `speech_analysis` vẫn giữ PA.
GRA utterances, LR words, FC lexical/WPM lấy nguồn canonical; FC eligibility dùng VAD
và trạng thái lexical, không phụ thuộc PA thành công. PR vẫn cần PA hoàn chỉnh theo
coverage gates hiện có. Nếu hai engine nghe khác từ, payload PR giữ PA transcript và
observation IDs của PA, canonical transcript vẫn riêng với
`cross_provider_alignment=not_performed`. Không ghép confidence, phoneme hoặc accuracy
của PA vào từ Whisper/STT. Không có cross-provider forced alignment.

Adapter giữ lexical khi optional acoustic/display/timing hỏng, ghi limitations và
missing capability riêng; acoustic damage hoặc word timing không đầy đủ làm result
partial. NoMatch/mất coverage vẫn partial; không tạo confidence khi provider thiếu.
Không có LLM rewrite, grammar restoration, bỏ fillers hoặc chỉnh band qua transcript.

Default identity/cache của PA giữ nguyên khi không cấu hình segmentation. Independent
projection có `independent-lexical-v1` và feature payload `evidence-v3`. Hai namespace
JSONB `speech_analysis` / `lexical_asr` có model/config identity riêng và cùng cơ chế
ATTEMPTED-before-call, terminal checkpoint, retry consent, attempt token fence. Đổi
lexical model không chạy lại PA; đổi Luna prompt không chạy lại cả hai. Lịch sử
completed không bị viết lại; đọc `get(run_id)` cũ vẫn dùng snapshot frozen. Endpoint
`latest` tiếp tục chỉ trả identity hiện tại như trước. Lifecycle xóa normalized
artifacts cũng xóa cả hai namespace; không thêm SQL migration/raw provider payload.

Chỉ bật request cloud thứ hai khi có permission và estimate/budget tường minh. Modal
còn cần opt-in GPU + proxy credentials. Ước tính là admission guard, không phải báo
giá hoặc hard billing cap; timeout có thể đã tính phí và không được auto retry.
Xem [benchmark và lệnh A/B có kiểm soát](testing/speaking-audio-replay.md#compare-asr).
Hiện chỉ có kết quả fixture/offline; chưa có WER/CER live của cohort human-verified.
Không đề xuất engine thắng. Rollback: chọn lại `azure_pa`, bỏ segmentation override,
restart worker theo quy trình deploy hiện có; không xóa lịch sử/checkpoints.

### Eligibility và giới hạn dữ liệu ở profile đầu tiên

Các ngưỡng dưới đây là điều kiện đủ dữ liệu kỹ thuật, chưa được hiệu chuẩn bằng
giám khảo và không phải ngưỡng band. FC cần VAD hợp lệ trên mỗi response, stream
complete và ít nhất 5 giây detected speech toàn lượt. PR cần stream complete trên
mọi response, observations trên từng response, ít nhất 20 từ có bằng chứng,
20 giây recognized utterance windows toàn lượt và coverage word accuracy ≥0.6
(trọng số theo số từ). Câu Part 1 ngắn không phải tự đạt 20 giây. Recognized
utterance windows có thể chứa pause: `assessed_speech_ms` hiện là tên tương thích
của độ dài cửa sổ được nhận dạng, không phải phép đo chính xác thời gian phát âm.
VAD và pronunciation evidence lưu riêng để không đánh đồng hai phép đo.

Scorer dùng tối đa khoảng 300 observations phát âm toàn lượt, phân tầng theo
response, loại/metric và vị trí timeline, không chọn chỉ các điểm thấp. Payload
giữ tổng số observations, số được chọn, coverage đầy đủ và limitation
`OBSERVATIONS_STRATIFIED_SAMPLE`; toàn bộ evidence vẫn ở checkpoint riêng tư.
Evidence ID của mẫu vẫn resolve về audio gốc. Đây không phải tỷ lệ lỗi của toàn
bài và không phải detector đầy đủ. Thiếu band vẫn giữ observations nghe lại được.
No-match sau final hợp lệ làm stream partial và lưu vùng ASR chưa nhận dạng;
không tự sửa ngữ pháp hoặc giả phần chưa nghe được. Nhận xét tổng quan không có timestamp.

Speech request đang `ATTEMPTED` khi worker chết/hủy được khóa để tránh gọi lại
mù. Người làm bài có thể [xác nhận gửi lại đúng các câu bị gián đoạn](speaking-transcription.md#khôi-phục-yêu-cầu-azure-bị-gián-đoạn),
chấp nhận khả năng request trước đã được xử lý/tính hạn mức; retry thông thường,
startup và chấm AI không tự cấp quyền này. Checkpoint cũ giữ trong
`previous_attempts`, và attempt token ngăn worker cũ ghi đè kết quả lần mới.
Sửa derivative WAV bị mất giữ nguyên ledger này; đổi prompt/feature không gọi lại
Azure. Cache speech bao gồm hash bytes chuẩn hóa thực tế, source/take fingerprint,
timeline/normalizer version và provider configuration/SDK identity. Xóa recording
qua lifecycle hiện có xóa/cascade cả checkpoint và derivative cache. Không thêm
SQL column hoặc migration; dữ liệu mới ở JSONB versioned đã có, legacy đọc được.

`GET /api/v1/speaking-attempts/analysis-profile` yêu cầu đăng nhập và chỉ trả trạng
thái cấu hình/SDK/VAD, không trả credential/path. `configured=true` không xác nhận
account/region/prosody live; `LIVE_UNVERIFIED` vẫn được giữ tới khi operator test.
Native SDK cleanup có thể bị treo trong thư viện: caller timeout/cancel có giới
hạn, bộ nhớ PCM thuộc native worker và slot được giữ tới khi cleanup kết thúc.
Khi đó capacity bị từ chối, không tạo thêm native thread hoặc xóa file đang đọc;
operator có thể cần restart replica sau đối soát billing. Không retry tự động.

### Quyền riêng tư và chi phí

Khi bật rõ ràng profile này, backend gửi WAV đã chốt tới Azure tại region operator
chọn; transcript và bằng chứng cần chấm đi vào LLM provider đang cấu hình. Key
chỉ ở backend Secret; không đưa raw provider payload, token, transcript hoặc byte
âm thanh vào log công khai. Voice/transcript có thể chứa dữ liệu cá nhân: phải
kiểm quyền sử dụng và chính sách của cả hai provider. Microsoft hiện mô tả
không lưu input của real-time recognition/pronunciation assessment; điều đó
không xóa bản ghi/checkpoint riêng của ứng dụng hoặc thay chính sách LLM.
Nguồn [Microsoft Speech privacy](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/speech-service/speech-to-text/data-privacy-security), đối chiếu 2026-11-03.

Đối chiếu tài liệu chính thức 2026-11-03: [Azure Speech pricing](https://azure.microsoft.com/en-us/pricing/details/speech/)
tính thời lượng âm thanh theo giây; [pronunciation assessment pricing](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/pronunciation-assessment-tool#pricing)
nêu baseline bằng speech-to-text Standard/commitment, prosody có phụ phí. Một
phiên dùng chung không cộng thêm một lượt ASR riêng. Với `D` là tổng giây billable
của **mọi** request đã gửi, ước tính speech là
`D / 3600 × (R_baseline + I_prosody × R_prosody)`.
Chưa biết rate thực theo region, currency, agreement/commitment và account;
không có con số USD được xác nhận cho project này. Submitted duration/call count
không phải hóa đơn. Timeout, retry do người dùng và partial stream vẫn có thể
tốn tiền. Chi phí Luna dùng usage và rate theo cấu hình OpenAI hiện có trong
[AI Writing/OpenAI](ai-writing.md#openai-gpt6-luna); reasoning nằm trong completion
tokens, không cộng hai lần. Cộng thêm CPU Modal, storage và network. Không có
benchmark chi phí/độ trễ trực tiếp cho hybrid: **LIVE_UNVERIFIED**.

### Đánh giá hybrid ngoại tuyến

Để replay MP3/WAV có sẵn mà không tạo attempt hoặc bắt buộc human bands, dùng
[CLI audio replay](testing/speaking-audio-replay.md): prepare/validate offline,
Azure-only smoke hoặc full Azure + CPU VAD + Luna với live opt-in và checkpoint riêng.

Thêm `speaker_id` giả danh và `split: "DEV" | "HOLDOUT"` cùng nhau vào mỗi dòng
manifest. Một speaker xuất hiện ở cả hai split bị từ chối trước chọn N mẫu;
`--require-speaker-splits` từ chối manifest cũ thiếu nhãn split. Các mẫu không có
speaker ID vẫn dùng được trong báo cáo legacy nhưng mang `speaker_split_status=unverified`.
Label band/split/speaker không đi vào `InferenceSample` hoặc lời nhắc suy luận.
Báo cáo tách metrics theo DEV/HOLDOUT; `fc_pr_half_band_gate` là kiểm mô tả
MAE ≤0.5 và |signed bias| ≤0.5 trên cặp hợp lệ FC/PR, không phải chấp thuận
production. Luôn xem coverage, số mẫu, failure rate và tính đại diện cùng gate.

`--analysis-evaluation private/analysis.json` thêm sidecar riêng tư có
`schema_version: 1`, `samples` gồm `id`, `truth_source: "human" | "unlabelled"`,
`truth` và `observed`. `truth` tùy chọn có `lexical_transcript`,
`word_boundaries_ms` (ID token đã căn chỉnh thủ công → `[start,end]`), `pauses_ms`
và `feedback_labels` (ID đơn vị đã được người chấm kiểm → boolean có lỗi thật).
`observed` có transcript/timing/pause cùng dạng, `feedback_flags`, `latency_ms`,
`provider_calls`, `usage` và `repeat_scores`. Không nhúng sidecar vào manifest
hoặc suy luận. Report chỉ xuất số liệu, không xuất lexical text hoặc path.

WER giữ fillers/repetitions và chỉ chuẩn hóa case/punctuation; timing báo MAE
hai biên trên token đã khớp và số token thiếu; pause dùng matching một-một với
IoU ≥0.5. Feedback FPR là `FP/(FP+TN)`, false discovery là `FP/(FP+TP)`; flag
chưa được human review có mẫu số riêng, không coi là lỗi. Thiếu truth trả null.
TTS source text không là human transcript, pronunciation hoặc IELTS truth.
`repeat_scores` phải đến từ các lần inference mới độc lập trên cùng đầu vào;
báo mean/max range từng tiêu chí. Cache replay không đo repeat stability.

`llm_telemetry` tổng hợp latency p50/p95, logical calls, transport attempts,
provider error rate và token usage quan sát được; không suy số token thiếu.
`speech_telemetry` giữ attempted/failed calls và submitted duration từ các kết
quả Azure đã trả; billed duration/amount vẫn chưa rõ. Exception trước khi nhận
kết quả không được diễn giải thành miễn phí hoặc zero provider calls.
Các trường nhập ngoại tuyến và telemetry của checkpoint được tiếp tục là
recorded evidence, không chứng minh đã phát sinh call mới trong lần tạo báo cáo.

Live luôn cần `--allow-live`, `--max-samples` trong 1–100, speaker split, và cả
`--max-estimated-cost-usd`/`--estimated-cost-per-sample-usd` dương. Bộ chạy tuần
tự, concurrency 1. Estimate phải bao gồm audio, prosody, token budgets và retries;
guard từ chối nếu tổng estimate vượt budget. Đây là admission theo **ước tính**,
không phải hard billing cap của Azure/OpenAI; cần account controls riêng. Chỉ
chạy khi operator đã cho phép live và đã xác nhận rate. Không có live run trong
lần triển khai working tree này.

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: mô tả kiến trúc và đánh giá Speaking của BandPilot. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../backend/app/services/speaking_ai_worker.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/speaking.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải kết quả chạy lại trong đợt kiểm toán này.

Speaking P1–P8 đã được triển khai. Mọi band và nhận xét AI đều mang tính tư vấn: dự án chưa có bằng chứng benchmark xác lập độ chính xác tương đương giám khảo. P8 thêm bộ chạy đánh giá, không thay điểm hoặc lược đồ sản xuất.

## Vận hành và chấm điểm

Next.js cung cấp câu hỏi đã soạn, kiểm tra micro trước khi làm bài, ghi âm và xem lại. FastAPI sở hữu chuyển trạng thái câu hỏi, dấu thời gian/hạn chót, hạn chế thử lại và phân quyền tệp âm thanh riêng tư. PostgreSQL lưu phiên bản đề đóng băng và nguồn gốc lượt làm bài; bộ chứa âm thanh nằm trong kho riêng tư. Tải đoạn dữ liệu có thể lặp an toàn. Khôi phục sau tải lại giữ thời gian còn lại của máy chủ và cấp một khoảng chuẩn bị bù bảy giây mà không tăng hạn mức nói. Bộ ghi khôi phục tạo phân đoạn chứa riêng. Xác nhận tải lên cuối cùng phải có trước khi chuyển tiếp. Ghi chú riêng không tham gia đầu vào chấm lời nói.

Chuỗi xử lý là âm thanh gốc đã chốt → PCM mono 16 kHz chuẩn hóa → cổng chất lượng → ASR nguyên văn có mốc thời gian từ → định dạng sạch và đặc trưng độ lưu loát/âm học có phiên bản → đánh giá tổng thể FC/LR/GRA/PR. Các bộ chứa khôi phục giải mã riêng trước khi nối PCM. Văn bản sạch giữ nguyên từ và ngữ pháp của người làm bài. Trên Modal, Web chạy FFmpeg, chất lượng, độ lưu loát và bằng chứng phát âm trên CPU; chỉ WAV chuẩn hóa đi từ FastAPI đến dịch vụ faster-whisper T4 riêng được bảo vệ qua proxy. Bộ nhớ đệm mô hình large-v3 đã ghim nằm trên `ielts-speaking-asr-model-cache`; âm thanh yêu cầu dùng tệp tạm riêng tư có thể hủy ngoài Volume đó. Dịch vụ Ministral L4 hiện có phục vụ cả chấm tiêu chí Writing và Speaking. Hai dịch vụ GPU đều có số container tối thiểu bằng 0, nên riêng khởi động Web không nạp mô hình nào. Lần chép lời đầu có thể gồm tải/nạp mô hình và chờ hàng đợi; không suy độ trễ ổn định từ nó. Đặc trưng thời gian mô tả lời nói, không tự gán band theo công thức. Phát âm cần bằng chứng âm thanh đã đo, không thể thành công chỉ từ văn bản chép lời hoặc độ tin cậy ASR. Âm thanh không đánh giá được hoặc thiếu bằng chứng phát âm khiến tiêu chí không khả dụng, không bịa điểm 0 hay trung bình.

`SpeakingScorer` xác thực điểm nửa band trước, lưu qua điểm kiểm tra, rồi yêu cầu nhận xét hữu hạn. Lỗi nhận xét giữ điểm hợp lệ. Điểm tổng sản xuất dùng trọng số đều FC/LR/GRA/PR và cách làm tròn nửa band của dự án; thiếu một tiêu chí khiến tổng không khả dụng. Worker và sự kiện bền vững hỗ trợ hủy, kết nối lại và khởi động lại. Speaking tích hợp Full Mock, lịch sử và kết quả lớp học. Giáo viên đọc bản ghi/bản chép lời và AI tư vấn qua nguồn gốc bài giao, có thể lưu điểm cuối do người chấm rõ ràng cho bài giao lớp mình. Lượt cá nhân không liên quan vẫn riêng tư.

## Đầu vào benchmark riêng tư

Bộ chạy tuân theo quy ước `app/evaluation` và thư mục `scripts` gốc hiện có. Dùng bản kê UTF-8 JSONL, mỗi dòng một phần thể hiện trọn vẹn đã được gán nhãn:

```json
{"schema_version":1,"id":"synthetic-001","responses":[{"audio_path":"audio/fictional.wav","part_number":1,"prompt_type":"SHORT_ANSWER","prompt_text":"Describe a fictional garden."}],"human":{"fc":6,"lr":6.5,"gra":7,"pr":6.5,"overall":6.5},"subgroups":{"recording_environment":"quiet"},"assessor_version":"fictional-rater-v1"}
```

Ví dụ này là hư cấu, không phải bằng chứng đánh giá của người chấm. Mỗi câu trả lời cần đúng một `audio_path` hoặc `fixture_id` có kiểm soát; đường dẫn phân giải cạnh bản kê và có thể trỏ tới tệp riêng ngoài git. ID dữ liệu mẫu dành cho bộ nạp kiểm thử ngoại tuyến được tiêm; bộ nạp âm thanh thật từ chối chúng an toàn. Cần câu hỏi để tái tạo đánh giá theo ngữ cảnh. `test_reference` tùy chọn là định danh không diễn giải nội dung. Siêu dữ liệu người chấm chỉ là mã phiên bản không nhận diện cá nhân. Cả năm nhãn người chấm đều phải là số hữu hạn 0–9 theo bước nửa band; tổng của người chấm là nhãn độc lập, không tính lại từ tiêu chí. Trường lạ, ID/khóa JSON trùng và khóa phân nhóm nhạy cảm bị từ chối. Đầu vào giới hạn 16 MiB và 10,000 mẫu; xác thực xem mọi dòng kể cả khi `--max-samples` chỉ đánh giá N mẫu đầu.

Giữ âm thanh người làm bài, bản kê, cấu hình dotenv riêng và kết quả ngoài git hoặc trong `benchmarks/speaking/private/` và `benchmarks/speaking/reports/` đã bỏ qua. Cần sự cho phép và kiểm giấy phép trước khi xử lý lời nói qua nhà cung cấp bên ngoài. Không commit đề có bản quyền, bản ghi riêng hoặc bản chép lời nhận diện cá nhân. Quy tắc Git bỏ qua là lớp bảo vệ bổ sung, không phải quyền phân phối dữ liệu nơi khác.

## Quy trình ngoại tuyến

Từ `backend/`, xác thực bản kê không khởi tạo nhà cung cấp:

```powershell
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --validate-manifest
```

Để tạo báo cáo ngoại tuyến, nhập kết quả chỉ có điểm từ một lần chạy bộ chấm hiện có:

```powershell
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --predictions ../benchmarks/speaking/private/predictions.json --output ../benchmarks/speaking/reports/offline
```

JSON dự đoán có `schema_version: 1`, đối tượng `provenance` bắt buộc (hợp đồng `ScorerProvenance`) và `predictions`; mỗi mục gồm `id`, `scores` FC/LR/GRA/PR theo nửa band hoặc null và `reasons` tùy chọn thuộc danh sách cho phép. Không cung cấp tổng: bộ chạy gọi `speaking_overall` sản xuất. Mẫu/tiêu chí thiếu vẫn là lỗi trong mẫu số. ID mẫu lạ, văn bản lỗi tùy ý, bản chép lời và trường dư bị từ chối. Siêu dữ liệu nhà cung cấp nhập vào là khai báo của tác giả kết quả, không chứng minh nhà cung cấp đã được gọi.

Để chạy thử ngoại tuyến chỉ với dữ liệu tổng hợp, tạo tệp bằng đoạn Python sau từ `backend/`, rồi chạy hai lệnh trên:

```python
import json
from pathlib import Path
from app.core.config import Settings
from app.evaluation.speaking.models import provenance

root = Path("../benchmarks/speaking/private")
root.mkdir(parents=True, exist_ok=True)
sample = {"schema_version": 1, "id": "synthetic-001", "responses": [
    {"fixture_id": "fictional-tone", "part_number": 1,
     "prompt_type": "SHORT_ANSWER", "prompt_text": "Describe a fictional garden."}],
    "human": {"fc": 6, "lr": 6.5, "gra": 7, "pr": 6.5, "overall": 6.5}}
identity = provenance(Settings()).model_copy(update={
    "provider": "fixture", "model": "synthetic-v1",
    "asr_provider": "fixture", "asr_model": "synthetic-v1"})
(root / "manifest.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
(root / "predictions.json").write_text(json.dumps({"schema_version": 1,
    "provenance": identity.model_dump(mode="json"), "predictions": [
        {"id": sample["id"], "scores": {"fc": 6, "lr": 6, "gra": 6, "pr": 6}}]}),
    encoding="utf-8")
```

Dự đoán tổng hợp kiểm phép tính và hợp đồng tệp, không đo được độ chính xác thật của bộ chấm. Kiểm thử tự động dùng bằng chứng tổng hợp và nhà cung cấp giả:

```powershell
uv run pytest tests/test_speaking_benchmark.py tests/test_speaking_benchmark_metrics.py tests/test_speaking_hybrid_evaluation.py tests/test_modal_speaking_hybrid.py -q
```

## Chấm thủ công với cấu hình nhà cung cấp

Chấm trực tiếp yêu cầu `--allow-live` rõ ràng. CLI đọc cùng `Settings` backend với sản xuất; `--config` chọn tệp dotenv riêng mà không đặt bí mật trong đối số lệnh. Với ASR cục bộ, đặt `SPEAKING_ASR_PROVIDER=local`, cài gói bổ sung `backend[speech]` và trỏ `SPEAKING_ASR_MODEL_DIRECTORY` tới mô hình cục bộ đầy đủ. Với ASR Modal, đặt `SPEAKING_ASR_PROVIDER=modal`, `SPEAKING_ASR_ENABLED=true`, `SPEAKING_ASR_BASE_URL` được bảo vệ, `SPEAKING_ASR_MODEL` đã ghim, `SPEAKING_ASR_MODEL_REVISION`, `SPEAKING_ASR_VERSION`, cùng `AI_WRITING_MODAL_KEY`/`AI_WRITING_MODAL_SECRET` chỉ ở backend. Web sản xuất tự nạp các cấu hình này; đánh giá thủ công cục bộ cần cấu hình riêng. Bật truyền tải LLM Speaking hiện có và nhà cung cấp phát âm riêng biệt. Quy trình benchmark không thêm bộ tải tập dữ liệu/mô hình.

```powershell
# Chỉ sau khi có authorization live, rate và budget estimate riêng:
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --allow-live --max-samples 5 --max-estimated-cost-usd $BudgetUsd --estimated-cost-per-sample-usd $UpperEstimatePerSampleUsd --config ../benchmarks/speaking/private/providers.env --output ../benchmarks/speaking/reports/candidate --resume
```

Bộ tiếp hợp gọi hợp đồng bộ chuẩn hóa, chất lượng, ASR, đặc trưng và `SpeakingScorer` hiện có, không tạo bộ chấm thứ hai. WAV đầu vào phải sẵn mono 16 kHz PCM có dấu 16 bit; WebM/Ogg/MP4/M4A dùng bộ giải mã FFmpeg sản xuất có giới hạn. Một tệp biểu diễn một bộ chứa câu trả lời đầy đủ. Cung cấp đầu vào bất biến; chuyển đổi dùng tệp tạm riêng tư. Tệp gốc không hỗ trợ, thiếu hoặc quá lớn (giới hạn 128 MiB), lỗi chất lượng và lỗi nhà cung cấp tạo mã lỗi an toàn. Không đổi dòng lượt làm bài hoặc điểm sản xuất.

`predictions.json` được ghi điểm kiểm tra nguyên tử trước mỗi yêu cầu nhận xét. Tiếp tục chỉ tái sử dụng mẫu đã đủ điểm khớp chính xác mẫu, băm nội dung âm thanh, cấu hình và nguồn gốc; mẫu thất bại/một phần được thử lại. Đây là quy trình cục bộ tuần tự: không để nhiều tiến trình cùng ghi một thư mục đầu ra. Lỗi nhận xét không bị tính là không chấm được nếu điểm tiêu chí đã lưu. Lỗi nhà cung cấp vẫn hiện trong tỷ lệ thất bại cuối; CLI thoát 0 nghĩa là đã tạo báo cáo, không phải mọi mẫu đều chấm được. Lỗi đầu vào/I/O trả mã thoát 2 cùng mã lỗi hữu hạn. Kiểm thử thường không gọi ASR/LLM trực tiếp, Modal hoặc dịch vụ GPU.

## Báo cáo và chỉ số

Đầu ra tất định gồm `summary.json`, `summary.md`, `samples.csv`, `samples.jsonl` và điểm kiểm tra điểm số khi chấm có cấu hình. Báo cáo chứa ID mẫu, band, sai số có dấu và mã nguyên nhân an toàn, không chứa nội dung âm thanh, bản chép lời, câu hỏi, đường dẫn hệ thống tệp, suy luận ẩn hoặc thông điệp nhà cung cấp. Tóm tắt gồm bất đồng lớn nhất, phân phối sai số có dấu và các nhóm hiệu chuẩn mô tả theo band người chấm. Những nhóm này không hiệu chỉnh điểm.

Cả năm tiêu chí đều có số lượng tổng/hợp lệ, độ bao phủ và tỷ lệ không chấm được/thất bại. MAE là trung bình trị tuyệt đối của sai số dự đoán trừ người chấm; RMSE là căn trung bình bình phương. Pearson đo liên hệ tuyến tính; Spearman dùng hạng trung bình cho trường hợp bằng nhau. Quadratic Weighted Kappa so sánh bất đồng bình phương theo nhóm quan sát với kỳ vọng từ phân phối biên trên 19 ô nửa band từ 0 đến 9 của dự án. Đồng thuận trong ±0.5/±1.0 và chính xác là tỷ phần trên cặp hợp lệ. Tương quan không đồng nghĩa đồng thuận: bộ chấm bị lệch có thể tương quan tốt nhưng MAE lớn.

Thống kê cặp loại dự đoán thiếu, nhưng lỗi luôn giữ trong mẫu số độ bao phủ. Tương quan cần ít nhất ba cặp hợp lệ; QWK cần năm. Quá ít cặp, vector hằng hoặc bất đồng kappa kỳ vọng bằng 0 trả null kèm trạng thái giải thích, không trả NaN. Nhóm toàn lỗi vẫn tạo báo cáo. Phân nhóm tùy chọn gồm môi trường ghi âm, nhóm trình độ, nhóm câu hỏi hoặc loại micro. Mặc định mỗi nhóm cần 20 mẫu có nhãn; `--minimum-subgroup-samples` cấu hình được với sàn năm. Nhóm nhỏ bị ẩn; thống kê cặp còn lại vẫn áp giới hạn mẫu riêng. Không phân tích nhân khẩu nhạy cảm hoặc tuyên bố công bằng từ mẫu nhỏ.

Mọi kết quả ghi bộ chấm/nhà cung cấp/mô hình, thang chấm/lời nhắc, hợp đồng điểm/nhận xét, nhà cung cấp/mô hình/phiên bản/căn chỉnh ASR, phiên bản chuẩn hóa, chất lượng, độ lưu loát và phát âm, băm cấu hình/triển khai và git SHA nếu có. Bí mật và đường dẫn thư mục mô hình được băm, không xuất ra. Trọng số mô hình và hành vi triển khai phải được ghim, phiên bản khai báo phải tăng khi đổi; riêng tên mô hình không định danh được trọng số có thể thay đổi. So sánh các lần chạy phải dùng cùng băm nhóm dữ liệu, nhãn và giao thức chỉ số, đồng thời xem thay đổi tỷ lệ lỗi cùng mức đồng thuận. Không tự động đưa phiên bản mới vào sản xuất.

## Dữ liệu nghiên cứu và chính sách hiệu chuẩn

[Speak & Improve Corpus 2025](https://researchdatasets.cambridge.org/datasets/speak-and-improve-corpus-2025) chứa nhãn CEFR tổng thể mang tính chỉ dẫn. Đơn vị xuất bản hạn chế phân phối và sử dụng, gồm giấy phép nghiên cứu/giáo dục phi thương mại và yêu cầu phê duyệt khi công bố tài liệu dẫn xuất; cần kiểm điều khoản và chính sách lưu giữ của nhà cung cấp trước. [SpeechOcean762](https://github.com/jimbozhang/speechocean762) hướng tới đánh giá phát âm. [L2-ARCTIC](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/) hỗ trợ nghiên cứu lời nói/phát âm của người không bản ngữ. Các tập này và tập phát âm khác có thể hỗ trợ xác minh phụ trợ; không tập nào tự cung cấp dữ liệu chuẩn chính thức IELTS FC/LR/GRA/PR. Kiểm riêng giấy phép, sự đồng ý và cách dùng được phép hiện hành của mỗi tập. Không đóng gói bản tải xuống hoặc bản ghi ở đây.

Không ánh xạ trực tiếp điểm SpeechOcean hoặc độ tin cậy ASR sang IELTS Pronunciation hay điểm tổng. Cần benchmark phần thể hiện đại diện, gán nhãn độc lập, có mức đồng thuận giữa người chấm và đánh giá trên dữ liệu giữ riêng trước khi tuyên bố độ chính xác. Dùng kết quả để nhận diện thiên lệch, so phiên bản, phát hiện hồi quy và quyết định cần hiệu chuẩn hay không. Một lần chạy nhỏ không đủ căn cứ đặt độ lệch sản xuất. Biến đổi tương lai phải rõ ràng, có phiên bản, được xem xét riêng và xác minh trên dữ liệu giữ riêng. P8 không có hiệu chuẩn ẩn hoặc thao túng điểm.

## Luyện kỹ năng theo từng Part

`/practice` cung cấp toàn bộ Part Speaking đã xuất bản. Part 1 và Part 3 hỗ trợ luyện câu hỏi Có hướng dẫn hoặc Tự do; Part 2 luôn Có hướng dẫn. Khởi tạo dùng `SPEAKING_PART`, `PRACTICE` và đồng hồ lượt làm bài đếm tăng. Hạn chót câu hỏi đã soạn vẫn kiểm soát chuẩn bị/ghi âm. Lượt `SPEAKING_PROMPT` cũ giữ nguyên phạm vi.

Chọn tự do được lưu qua `POST /speaking-attempts/{id}/select-prompt`, không tự ghi âm. Chuyển khi đang ghi cần dừng, đóng tải lên, nhận xác nhận bền vững cho câu trả lời, rồi chọn câu khác. Lần ghi đã chốt vẫn là dự phòng tới khi bản thay thế chốt xong. `POST /speaking-attempts/{id}/finish-practice` rõ ràng cần ít nhất một câu đã lưu và cho phép còn câu chưa trả lời. Trang xem lại hiển thị câu đó không có âm thanh/bản chép lời. Điểm Part vẫn là bản ghi luyện tập có phạm vi, không góp vào band Speaking đầy đủ, điểm tổng Full Mock hoặc Analytics toàn mô-đun. Khởi tạo toàn Part từ lớp học bị từ chối. Migration `20261013_0034` thêm phạm vi và luồng này.

## Điểm cuối Speaking do người chấm

Chủ sở hữu bài luyện cá nhân có thể nhập tay FC/LR/GRA/PR hoặc chép kết quả AI hiện hành đã hoàn tất vào biểu mẫu, chỉnh sửa rồi Lưu rõ ràng. AI không tự ghi điểm cuối. Học viên lớp chỉ xem điểm cuối hoặc “Đang chờ giáo viên chấm”. Nhân sự có quyền chấm của lớp được lưu/sửa tiêu chí qua đúng nguồn gốc bài giao. ADMIN chỉ quan sát lớp và không được ghi điểm cuối cho bài của lớp, kể cả qua route cá nhân; quyền chấm bài luyện cá nhân của nền tảng được xét riêng. Chấm của giáo viên không cấp quyền tạo lại transcript hoặc sửa tệp gốc. Xem [GradingPolicy hiện hành](../backend/app/services/grading_policy.py).

Tiêu chí người chấm và nhận xét tùy chọn lưu độc lập trong `attempt_speaking_scores`, do Alembic không phá hủy `20261013_0033` thêm. Điểm tổng dùng hàm Speaking tổng thể trọng số đều hiện có. Điểm luyện tập có phạm vi không tạo band phân tích toàn mô-đun. Khóa xem lại Full Mock vẫn có thẩm quyền. `SpeakingReviewData.final_score` mang đánh giá này, `grading` mang khả năng backend cho phép. Xem [teacher-classrooms.md](teacher-classrooms.md#human-final-subjective-grading) về chính sách thẩm quyền và các tuyến dùng chung.


### Azure billing safety (configuration follow-up)

`SPEAKING_AZURE_ALLOW_PAID=false` is the default. The additional local declaration
`SPEAKING_AZURE_BILLING_MODE=unknown|free_only|paid` fails closed when unknown;
paid also requires explicit allow-paid. Tier/feature eligibility is verified outside
the worker: no ARM permission, upgrade, key/resource rotation or provider fallback.
The current user's F0 resource is explicitly declared `free_only` in ignored dev
configuration. This is not a live pricing verification or a hard cloud spending cap.

The configured key/region is snapshotted per analyzer and contributes only a hash
to cache identity. Policy changes invalidate analysis identity. SDK TooManyRequests
or HTTP 429 maps to `SPEAKING_AZURE_QUOTA_EXCEEDED`, not a claim of monthly allowance
exhaustion. Safe reason codes distinguish explicit rate/concurrency/quota subcodes
when available; no raw details enter events/UI. The current stream is stopped, the
remaining responses in that run are marked unavailable with the same code, and no
second provider/session is tried. Durable failed/partial checkpoints are terminal;
UI reconnect or ordinary retry does not blindly resend potentially billed audio.
Only interrupted `ATTEMPTED` calls can be resubmitted through the candidate's
explicit acknowledgement described in the [recovery flow](speaking-transcription.md#khôi-phục-yêu-cầu-azure-bị-gián-đoạn);
prior attempt history remains durable and terminal failed/partial checkpoints are unchanged.
A persisted quota checkpoint may need operator reconciliation after service recovery.

See [Microsoft SDK cancellation codes](https://learn.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.cancellationerrorcode)
and [Speech quotas/concurrency](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits),
checked 2026-11-03. [Modal setup](modal-web.md#azure-configuration-secrets-and-canonical-command)
contains the canonical launcher and Secret replacement commands. Live resource
credentials, F0 prosody availability and billing remain **LIVE_UNVERIFIED**.


## Admin research experiments

[Phase 3 research](testing/admin-speaking-benchmark-research.md) adds ASR-only comparison without Luna and paired downstream experiments through the production scorer. Reference transcripts and human bands are evaluation-only; lower WER is not a guarantee of lower band error. No learner transcript, rubric default or scoring authority is changed. Optional GPU inference remains separately authorized.

Paired transcript comparisons retain the evidence actually consumed by their P2
run through immutable cache receipts. Current research fixes preserve that
provenance across recovery and fence cancellation atomically; no alternative
Speaking scoring implementation or automatic calibration is introduced.


## Quality, consensus and regression gates

[Phase 4 Quality and Gates](testing/admin-speaking-benchmark-quality-and-gates.md) establishes examiner-question extraction, multi-rater IELTS Speaking ground truth with strict blind reviewer isolation, dataset QA (`speaking-dataset-quality-v1`), frozen evaluation suites, and continuous evaluation regression gates (`speaking-regression-gate-v1`). Gate evaluations and offline CI CLI (`scripts/speaking_benchmark_gate_cli.py`) project solely over persisted P1-P3 evidence without invoking paid models or modifying production rubric thresholds.
