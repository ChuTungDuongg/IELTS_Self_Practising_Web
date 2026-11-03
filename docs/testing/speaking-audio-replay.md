# Replay audio Speaking trên CPU

Công cụ `scripts/replay_speaking.py` chạy local, không cần trình duyệt, microphone,
PostgreSQL hay attempt production. Nó dùng analyzer Azure và `SpeakingScorer` production,
không tạo bộ chấm riêng. Không khởi tạo Modal, Whisper T4 hoặc vLLM L4.

Đã đối chiếu `main` tại `6631ea4` (cây mã giống `de3271b`). Việc triển khai và kiểm thử
ngoại tuyến không xác nhận credential, quota, latency hoặc độ chính xác live: **LIVE_UNVERIFIED**.
Kiến trúc, eligibility FC/PR và giới hạn ASR nằm trong [AI Speaking](../ai-speaking.md).

## 1. Chuẩn bị môi trường và audio

Chạy các lệnh PowerShell dưới đây **từ root repository**. `--project backend` cần thiết
vì root không có Python project. FFmpeg **và ffprobe cùng thư mục** phải có trên PATH;
hoặc đặt `SPEAKING_FFMPEG_PATH` thành đường dẫn tuyệt đối tới FFmpeg. Native runtime
của Azure phải được cài theo [hướng dẫn setup hiện có](../speaking-transcription.md).

```powershell
uv sync --project backend --locked --extra azure-speech --extra speech-vad --group dev
New-Item -ItemType Directory -Force benchmarks/speaking/private/replay | Out-Null
```

Tải bằng trình duyệt từ nguồn bạn có quyền sử dụng, hoặc dùng bản ghi của chính mình,
rồi lưu MP3/WAV vào thư mục đó. CLI chỉ đọc file local; không tải URL, không upload
Azure Portal và không tự tìm recording IELTS. Không đưa bản ghi riêng tư vào Git.

Chọn **một** kiểu input:

```text
benchmarks/speaking/private/replay/
  full_speaking.mp3          # hoặc .wav
  segments.json             # được --prepare tạo
  human_labels.json         # tùy chọn
```

Hoặc thay file full bằng `part1.mp3`, `part2.mp3`, `part3.mp3` (WAV cũng được).
Không đặt đồng thời file full và các file Part, hoặc hai định dạng của cùng file.
Mỗi nguồn tối đa 128 MiB / 30 phút; sample rate 8–192 kHz, 1–8 channels.
Header, demuxer thật và khả năng decode được kiểm tra, không chỉ extension.
File chuẩn hóa là temporary PCM mono 16 kHz signed 16-bit; bản gốc giữ nguyên.
Không trim pause nội bộ, time-stretch, denoise hoặc thêm im lặng.

## 2. Prepare và validate: không gọi API

```powershell
uv run --project backend python scripts/replay_speaking.py --prepare --input benchmarks/speaking/private/replay
uv run --project backend python scripts/replay_speaking.py --mode validate --input benchmarks/speaking/private/replay
```

`--prepare` kiểm tra file và tạo `segments.json` **chưa xác minh**, với timestamps `null`,
prompt trống, `speaker_role: "unknown"`. Chạy lại không ghi đè cấu hình đã sửa.
Nếu chưa có audio, thư mục vẫn được tạo và CLI hướng dẫn bổ sung file.
Validate tạo report metadata/eligibility, không tạo Azure client hoặc Luna provider.
Draft hợp lệ có thể validate thành công nhưng vẫn **chưa đủ điều kiện full grading**;
xem `input.full_grading_eligible` và limitations trong report.

Nghe file bằng audio player local, điền start/end **integer milliseconds** theo đúng nguồn,
thêm mỗi câu trả lời thành một segment. Không cần cắt MP3 bằng phần mềm ngoài.
Một file Part vẫn có thể chứa examiner; tên file không chứng minh ai đang nói.
Loại câu hỏi, hướng dẫn và preparation time khỏi candidate windows, nhưng giữ
leading/trailing silence thuộc thời gian trả lời thực sự. Chỉ đặt
`candidate_only_verified: true` sau khi đã nghe và xác nhận các đoạn candidate.

Ví dụ dưới đây là **timestamps và câu hỏi hư cấu để minh họa schema**, không phải
mốc thật của bất kỳ recording nào; phải sửa theo audio của bạn:

```json
{
  "schema_version": 1,
  "source": "full_speaking.mp3",
  "candidate_id": "candidate-1",
  "candidate_only_verified": false,
  "segments": [
    {
      "id": "p1-q1", "part_number": 1,
      "start_ms": 10000, "end_ms": 35000,
      "prompt_type": "SHORT_ANSWER", "prompt_text": "Describe a fictional hobby.",
      "speaker_role": "candidate"
    },
    {
      "id": "p2-long-turn", "part_number": 2,
      "start_ms": 300000, "end_ms": 410000,
      "prompt_type": "LONG_TURN", "prompt_text": "Describe a fictional journey.",
      "cue_points": [], "speaker_role": "candidate"
    },
    {
      "id": "p3-q1", "part_number": 3,
      "start_ms": 510000, "end_ms": 550000,
      "prompt_type": "FOLLOW_UP", "prompt_text": "Why might fictional towns change?",
      "speaker_role": "candidate"
    }
  ]
}
```

Với file Part riêng, đặt `source` trên **từng segment**, ví dụ `"source": "part2.mp3"`;
mốc thời gian tính từ đầu file Part đó. Có thể thêm segments `examiner` hoặc `preparation`
để ghi metadata; chúng không đi vào grading. Không cho phép overlap trong cùng nguồn,
vượt duration hoặc ghép hai `speaker_id` khác nhau trong một attempt.
CLI không diarize hay tự xác nhận speaker. Full cần đủ Parts 1/2/3, Part 2 long turn,
timestamps, câu hỏi/cue context thật và một candidate đã được operator xác minh.

File 14 phút không được gửi như một response. Công cụ cắt theo từng window đã xác nhận,
kiểm tra cap production hiện hành (mặc định 600 giây/response), giữ mapping
normalized time → source start/end. Đừng tăng cap để né segmentation; native timeout
Azure vẫn áp dụng. Mọi response là một recording liên tục; không nối qua khoảng mất dữ liệu.

## 3. Cấu hình private

Đọc mặc định `backend/.env`, hoặc `--config <private-dotenv>`; environment variables
của process vẫn có precedence theo `Settings`. Công cụ không sửa dotenv và không in key.
Tên canonical của implementation là **`SPEAKING_AZURE_KEY/REGION/LOCALE`**:

```dotenv
SPEAKING_PROFILE=speaking_hybrid_v1
SPEAKING_ASR_ENABLED=true
SPEAKING_ASR_PROVIDER=azure
SPEAKING_AZURE_KEY=<điền trong file local, không gửi vào chat>
SPEAKING_AZURE_REGION=japaneast
SPEAKING_AZURE_LOCALE=en-US
SPEAKING_AZURE_PROSODY=true
SPEAKING_AZURE_ALLOW_PAID=false
# Chỉ khai báo sau khi operator xác nhận resource là Free; runtime không tra ARM.
SPEAKING_AZURE_BILLING_MODE=free_only

AI_WRITING_OPENAI_API_KEY=<key local>
SPEAKING_AI_ENABLED=true
SPEAKING_AI_PROVIDER=openai
SPEAKING_AI_MODEL=gpt-6-luna
```

Giữ nguyên reasoning/token settings hiện có. Azure-only không cần OpenAI key hoặc VAD
asset. Full kiểm tra cả OpenAI config và pinned VAD trước khi gửi audio:

```powershell
uv run --project backend python scripts/setup_speaking_vad.py storage/models/silero_vad.onnx
```

Đặt `SPEAKING_VAD_MODEL_PATH` trong dotenv thành **đường dẫn tuyệt đối** tới file trên
(ví dụ `C:/Users/Admin/IELTS_Self_Practising_Web/storage/models/silero_vad.onnx`).
Setup tải asset pinned có checksum một lần; request không tải model, không dùng CUDA.
`free_only` là attestation của operator, không phải runtime chứng nhận tier F0.
Billing mode `unknown` fail closed; `paid` cần opt-in riêng. Không fallback resource,
OpenAI transcription, Modal T4 hoặc provider khác khi thiếu credential/quota.

## 4. Azure-only technical smoke

**Chỉ operator chủ động chạy các lệnh live dưới đây.** `--allow-live` cùng estimate/budget
là xác nhận gửi dữ liệu và chấp nhận estimate của lần chạy. Ví dụ 0.50/1 USD chỉ minh họa
guard, không phải giá đã được kiểm chứng hoặc hard cap hóa đơn; thay bằng estimate của bạn.

```powershell
uv run --project backend python scripts/replay_speaking.py --mode azure --allow-live --input benchmarks/speaking/private/replay --max-audio-seconds 60 --estimated-cost-usd 0.50 --max-estimated-cost-usd 1
```

Chọn candidate window đầu tiên có timestamps nếu có; nếu chưa segment, dùng preview từ đầu
nguồn đầu tiên. Luôn giới hạn preview tối đa **60 giây** hoặc giới hạn nhỏ hơn được chỉ định.
Không gọi Luna, không xuất IELTS bands. Audio chưa xác minh giữ
`UNSEGMENTED_AUDIO`/`SPEAKER_NOT_VERIFIED`; examiner trong preview chỉ phục vụ kiểm tra kỹ thuật.
Report có lexical/timing/pronunciation coverage, capabilities và safe provider reasons;
transcript thật chỉ nằm trong checkpoint `SENSITIVE-*`. Không sửa “Yesterday I go” trước chấm.
Fillers/disfluencies có thể bị ASR chuẩn hóa; transcript không được bảo đảm verbatim.

## 5. Full Azure + CPU VAD + Luna

```powershell
uv run --project backend python scripts/replay_speaking.py --mode full --allow-live --input benchmarks/speaking/private/replay --max-audio-seconds 900 --estimated-cost-usd 1.50 --max-estimated-cost-usd 3 --resume
```

Estimate trên cũng chỉ là ví dụ operator tự thay. `--max-audio-seconds` là tổng **mọi**
candidate window đã chọn; full từ chối nếu vượt giới hạn, không âm thầm cắt mất Parts.
Sau quality gate, mỗi segment dùng một Azure continuous unscripted analysis, tái sử dụng
transcript/timestamps/pronunciation cho `analysis_to_asr` và `build_feature_bundle`.
CPU VAD đo pauses, production `build_attempt_evidence`/`SpeakingScorer` chấm toàn lượt.
Không bình quân band từng câu hay Part. Score-first giữ điểm khi feedback lỗi;
`speaking_overall` chỉ tính khi đủ FC/LR/GRA/PR hợp lệ. Thiếu PR/temporal FC giữ unavailable.

## 6. Human labels tùy chọn

Không có `human_labels.json` vẫn chạy smoke/full. Report không có MAE/RMSE/agreement khi
không có human truth. Benchmark có nhãn hiện có và `scripts/evaluate_speaking.py` giữ
validation `HumanLabels` nghiêm ngặt; replay dùng hợp đồng riêng.

Ví dụ **nhãn hư cấu**, chỉ Overall; không suy diễn bốn tiêu chí:

```json
{
  "schema_version": 1,
  "bands": {"overall": 6.5},
  "provenance": {
    "kind": "published_human_assessment",
    "reference": "Thay bằng nguồn nhãn thật và người chấm có thể đối chiếu",
    "verified": false
  }
}
```

Các key tùy chọn khác là `fc/lr/gra/pr`. Chỉ đặt `verified: true` cho nhãn người chấm đã
đối chiếu; `ai_prediction`/`unverified` không được nhận là verified human ground truth.
Labels/provenance không được gửi Azure hoặc LLM. Metrics chỉ tính tiêu chí thực sự được
công bố và có prediction; thiếu mẫu số trả null. Một lượt replay không chứng minh độ
chính xác, fairness theo accent hay repeat stability. Dùng benchmark nhiều người nói với
DEV/HOLDOUT độc lập trong [workflow evaluation hiện có](../ai-speaking.md#đánh-giá-hybrid-ngoại-tuyến).

## 7. Report, resume và chi phí

CLI in đường dẫn `benchmarks/speaking/reports/replay/replay-<hash>/summary.md`:

- `summary.md`, `summary.json`: input counts, eligibility, coverage, scores/reasons,
  provenance, usage/latency, human comparisons nếu có và caveats.
- `samples.jsonl`, `speech-coverage.json`: metadata/coverage từng segment, safe telemetry.
- `predictions.json`: output Luna chỉ gồm scores/reasons/usage/provenance.
- `SENSITIVE-source-mapping.json`, `SENSITIVE-luna-*.json`: câu hỏi, mapping và evidence/feedback riêng tư.
- `.speech-cache/SENSITIVE-*.json` ở thư mục report gốc: lexical transcript, timings,
  pronunciation evidence và ledger trước/sau request; không xóa khi chỉ Luna thất bại.

Summary không chứa raw transcript/audio, tên nguồn, private path hoặc label reference.
Toàn bộ private/reports bị gitignore; không force-add các file này. Temporary derivatives
được xóa khi hoàn tất/hủy sau khi tác vụ native đọc file đã kết thúc. Muốn xóa dữ liệu replay,
xóa input và report/checkpoint riêng của nó sau khi đã đối chiếu billing; xóa cache cũng mất
bảo vệ tránh gửi lại audio. Không có recording học viên trong DB bị thay đổi.

Speech cache bind theo private input namespace, hash nguồn và PCM thực tế, window/Part,
normalization/timeline và Azure SDK/provider/locale/prosody/billing identity. Scoring cache
thêm evidence, VAD/features, model/prompt/rubric/config/code provenance. Đổi prompt Luna
không gọi lại Azure. Evidence complete phù hợp luôn được tái sử dụng; `--resume` cho phép
tiếp tục tiêu chí Luna đã báo failed, giữ điểm đã checkpoint trước feedback.

`ATTEMPTED`, timeout, cancelled, partial hoặc failed Azure không tự gửi lại, kể cả `--resume`.
CLI giữ `REPLAY_AZURE_BILLING_UNKNOWN_INSPECT_CHECKPOINT` hoặc domain error cụ thể.
Operator phải kiểm tra ledger/service usage và **chủ động archive/xóa đúng checkpoint** nếu
chấp nhận một lần submit mới có thể tính phí. Không có flag âm thầm bỏ qua fence này.
Lock ngăn hai process replay live cùng lúc; chỉ gỡ stale `SENSITIVE-live.lock` sau khi chắc
process cũ đã dừng và đã kiểm tra checkpoint. Unknown Luna pending cũng cần đối chiếu thủ công.

Quota/throttle báo `SPEAKING_AZURE_QUOTA_EXCEEDED`, không retry storm hoặc đổi resource/tier.
429 có thể do rate/concurrency, không luôn là hết monthly quota; telemetry giữ reason code
an toàn khi SDK cung cấp. Attempts/submitted duration/usage quan sát được **không phải hóa đơn**.
Azure Speech/prosody và Luna là hai khoản riêng; timeout/partial và submit lại có thể vẫn
tiêu thụ F0 allowance/credits. Xem [công thức và nguồn pricing đã ghi nhận](../ai-speaking.md)
để tự lập estimate theo region/resource, prosody và token caps; tool không bịa đơn giá.
`--estimated-cost-usd 0` chỉ được dùng với Azure-only khi operator xác nhận free allowance;
full cần estimate dương. Không có automatic live API call trong CI/unit tests.

## 8. Kiểm thử và giới hạn xác minh

```powershell
uv run --project backend pytest backend/tests/test_speaking_replay_contract.py backend/tests/test_speaking_replay_audio.py backend/tests/test_speaking_replay_runner.py backend/tests/test_speaking_replay_cli.py -q
```

Test dùng PCM tổng hợp và fake Azure/Luna response qua các contract production. Integration
MP3/WAV cần FFmpeg/ffprobe; thiếu chúng thì audio tests skip rõ ràng. CI cài FFmpeg CPU.
Container local chạy `--network none` để xác minh decode thật mà không gửi provider requests.
Các lần mock giữ **LIVE_UNVERIFIED**, không được trình bày là benchmark IELTS giám khảo.

Kết quả thực tế trên working tree của lần triển khai này:

| Kiểm tra | Kết quả |
| --- | --- |
| Replay + production evidence/scorer + benchmark + Azure contract regression, chạy từ root | 328 passed, 9 skipped trên Windows |
| Local/Modal ASR, composition/launcher và Writing scorer/text/budget regression | 209 passed |
| Các test replay trong Debian CPU container có FFmpeg, `--network none` | 42 passed; 1 Git check deselected và đã pass trên host |
| CLI prepare → validate với WAV tổng hợp 3 giây, container không có credential | Thành công, 0 Azure/Luna calls, không bands, đủ 5 report files |
| Ruff lint/format toàn backend và scripts; `git diff --check` | Pass |

Windows hiện thiếu FFmpeg/ffprobe trên PATH nên 8 audio integrations skip tại host; test
symlink còn lại skip do quyền tạo symlink. Cả decode MP3/WAV, symlink escape và source
14 phút chia windows đã chạy thật trong container Linux. Không chạy integration với DB,
không mở browser và không gọi Azure/OpenAI live trong lần triển khai này.

Chưa xác minh live credential/quota, account/locale prosody, độ trung thực transcript,
phoneme observations, accent false positives, chi phí và band agreement thực tế. en-US
là locale kỹ thuật, không yêu cầu giọng Mỹ. Azure scores là evidence phụ, không map tuyến
tính sang IELTS. Technical smoke pass chỉ chứng minh luồng kỹ thuật hoạt động; đánh giá
đúng giám khảo cần candidate-only data và nhãn người chấm độc lập phù hợp.
