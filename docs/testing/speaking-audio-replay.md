# Replay audio Speaking trên CPU

Công cụ `scripts/replay_speaking.py` chạy local, không cần trình duyệt, microphone,
PostgreSQL hay attempt production. Nó dùng analyzer Azure và `SpeakingScorer` production,
không tạo bộ chấm riêng. Không khởi tạo Modal, Whisper T4 hoặc vLLM L4.

Replay đã có ở `main` tại `7a3fe4a`; phần diarization local bổ sung ở mục 9. Kiểm thử
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
Workflow manual này không tự diarize hay xác nhận speaker. Tùy chọn diarization local ở mục 9.
Full cần đủ Parts 1/2/3, Part 2 long turn,
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

## 9. Local speaker diarization và review

Có thể bắt đầu bằng **một MP3 Speaking dài 12–14 phút có cả examiner và candidate**.
CLI đề xuất timestamps tự động; operator xác nhận speaker, hai mốc chuyển Part và
câu hỏi thật. Không cần tự nhập start/end của mọi câu trả lời. Pipeline Speaking
production, Azure/Luna, cost guards và workflow manual ở trên giữ nguyên.

### Setup riêng, không thêm Torch vào backend hoặc Modal Web

[Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) hỗ trợ
inference local/CPU, đồng thời trả regular và exclusive diarization. Tool giữ **cả hai**:
exclusive giúp đề xuất window; regular phát hiện tiếng chồng lấn mà exclusive có thể che đi.
Không sử dụng hosted pyannoteAI. Model gated cần bạn tự đăng nhập Hugging Face, đọc và
chấp nhận điều kiện trên model card, rồi tạo read token. Tool không chấp nhận điều kiện thay bạn.

```powershell
uv sync --project tools/speaking_diarization --python 3.12 --locked
uv run --project backend python scripts/replay_speaking.py --setup-diarization-model
```

Điền `HF_TOKEN` trong `backend/.env` **đã gitignore**, hoặc nhập ở prompt terminal ẩn
của lệnh setup. Không truyền token bằng CLI arguments, không dán vào chat. Worker chỉ
nhận token qua environment của subprocess **setup**; analyzer không nhận Azure/OpenAI/HF
credentials. Bản ghi local không được tải lên Hugging Face khi setup.

Weights mặc định ở `storage/models/pyannote-community-1/`, bị gitignore. Setup tải đúng
revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`, ghi `bandpilot-model.json`
với checksum từng asset. Inference xác minh receipt, chạy với HF offline, telemetry tắt
và chặn network trong child process; không tự download khi thiếu asset.

Environment `tools/speaking_diarization` có lockfile riêng cho Python 3.12,
Windows/Linux x86-64: pyannote.audio 4.0.7, Torch/torchaudio 2.8.0 CPU, TorchCodec
0.7.0, huggingface-hub 0.36.0, NumPy 2.2.6. Không sửa `backend/uv.lock`, không hạ
package đang dùng cho Azure/VAD. [TorchCodec matrix](https://github.com/meta-pytorch/torchcodec/tree/v0.8.0#installing-torchcodec)
liệt kê TorchCodec 0.7 với Torch 2.8 và FFmpeg 4–7; Windows support còn experimental.
[pyannote source](https://github.com/pyannote/pyannote-audio/tree/4.0.7) là API đã đối chiếu.

### Từ full recording đến manifest duyệt được

Đặt file vào thư mục private như bước 1; không đặt cùng lúc full file và các file Part.

```powershell
uv run --project backend python scripts/replay_speaking.py --auto-segment
uv run --project backend python scripts/replay_speaking.py --review-segments
```

Đây đều là lệnh offline: **0 Azure/OpenAI calls**. Auto dùng một local inference trên
mỗi file, tối đa 30 phút/128 MiB nguồn; các file Part là các phiên riêng. Audio được
chuẩn hóa toàn recording cho diarization, không coi cả recording là grading response
và không tăng cap 600 giây của production grading. Audio gốc không đổi, không trim
pauses. Các timestamps luôn tính từ đầu **file nguồn**.

Các artifact private:

- `diarization.json`: regular/exclusive turns, speaker IDs, source SHA, model/revision/runtime/config.
- `.diarization-cache/SENSITIVE-*.json`: cache riêng của local model, không chung Azure/Luna cache.
- `segments.proposed.json`: machine draft có Part chưa biết, câu hỏi chưa biết, overlap/boundary flags.
- `segments.review.json`: các xác nhận và chỉnh sửa operator; xác nhận role khác xác nhận boundaries.
- `question-context.template.json`: template machine tạo lại theo các proposal hiện tại.
- `review.local.html`: report local có audio controls, speaker timeline, Part markers đã xác nhận,
  nút nghe từng window, vùng overlap và câu hỏi đã cung cấp. Mở file trên **máy local**;
  không cần web app/database/server. Không có CDN, upload, telemetry hoặc autoplay.

Regular speaker tracks và window overlap đều được giữ. Không mặc định speaker đầu là
examiner, không ép đúng hai speakers. Heuristic chỉ gợi ý role khi có cả thời lượng tương
đối và nhiều short-to-long turn patterns; trường hợp mơ hồ hoặc hơn hai speakers để `unknown`.
Không có probability/calibrated confidence nếu model không cung cấp.

Nghe các ví dụ speaker trong report, chọn ID **đúng như CLI in ra**, chẳng hạn ID hư cấu
`f12345678-speaker_01`. Đổi các mốc minh họa sau theo recording thực tế:

```powershell
uv run --project backend python scripts/replay_speaking.py --confirm-candidate-speaker f12345678-speaker_01 --set-part-boundaries 240000 480000
```

Hai số là thời điểm bắt đầu Part 2 và Part 3 của file full, không phải timestamps câu trả lời.
Không suy Part 2 chỉ vì có một câu dài. Nếu chưa xác nhận transition, Part vẫn unknown.
Nếu dùng ba file Part: xác nhận candidate ID **riêng cho từng file** rồi chạy
`--confirm-file-parts`. Speaker IDs được namespace theo file; cùng nhãn local SPEAKER_00
không chứng minh cùng người. Final approval còn xác nhận các file là cùng candidate.

Sau khi xác nhận speaker/Parts, copy template câu hỏi ra file operator riêng:

```powershell
Copy-Item benchmarks/speaking/private/replay/question-context.template.json benchmarks/speaking/private/replay/questions.json
# Sửa questions.json: điền câu hỏi/cue thật, kiểm tra association, rồi đặt verified=true.
uv run --project backend python scripts/replay_speaking.py --question-context benchmarks/speaking/private/replay/questions.json
```

Mỗi entry nằm trong `questions` và có proposal ID làm key:

```json
{
  "schema_version": 1,
  "questions": {
    "s-replace-with-real-proposal-id": {
      "prompt_text": "Thay bằng câu hỏi thực sự tương ứng",
      "cue_points": [], "source_kind": "operator", "verified": false
    }
  }
}
```

`context_turn_ids` chỉ trỏ tới turn của speaker khác ngay trước window, không bảo đảm đó
là câu hỏi. Không có trusted transcript thì không tự bịa prompt. Tool chưa chạy thêm local
ASR trên examiner: có thể nhập transcript đã có dưới `source_kind: human_transcript` hoặc
`local_asr`, nhưng cần operator kiểm tra và xác nhận. `human_labels.json` không được dùng
để suy câu hỏi, roles, Parts hoặc timestamps.

### Chỉnh ít window có vấn đề, rồi phê duyệt rõ ràng

```powershell
uv run --project backend python scripts/replay_speaking.py --edit-segment s-REAL_ID 123000 145000
uv run --project backend python scripts/replay_speaking.py --exclude-segment s-OTHER_ID
uv run --project backend python scripts/replay_speaking.py --acknowledge-segment s-LONG_SILENCE_ID
uv run --project backend python scripts/replay_speaking.py --review-segments
uv run --project backend python scripts/replay_speaking.py --approve-segments
uv run --project backend python scripts/replay_speaking.py --mode validate
```

Các ID/mốc ở đây phải thay bằng dữ liệu thật. Window được merge qua pause ngắn nếu không có
speaker khác chen vào; tolerance mặc định 3 giây. Trong Part 2 **đã operator xác nhận**, giữ
long turn và internal silence, đánh dấu long silence để nghe lại. Không merge qua bất kỳ
examiner/other-speaker interruption nào, không concatenate các câu khác nhau.
Padding tối đa mặc định 150 ms và chặn ở turn người khác đã biết giúp tránh cắt phoneme;
model boundary vẫn cần kiểm tra, nhất là leading response silence và preparation.

`--acknowledge-segment` chỉ ghi bạn đã nghe/check long silence. Nó **không cho phép**
grading window chứa other-speaker overlap. Phải sửa bounds để loại overlap hoặc exclude;
window không có candidate speech support, vượt cap, hoặc cắt ngang transition bị từ chối.
Short answers vẫn được giữ, không tự phạt vì ngắn. Quality gate production vẫn có thể từ chối
mẩu quá ngắn/ít speech; không nối qua examiner để lách gate. Final approval là xác nhận bạn đã nghe
các window được chọn, chúng chỉ chứa candidate, đúng boundaries, Parts và câu hỏi; đây là
bước riêng sau identity confirmation. Part 2 window dài nhất được đề xuất LONG_TURN trong
manifest đã duyệt; cần kiểm tra đó đúng là long turn thực tế. Nếu cấu trúc không phù hợp,
dùng manual manifest ở bước 2 thay vì ép cấu hình để pass.

Chỉ `--approve-segments` mới tạo/cập nhật `segments.json` với
`candidate_only_verified=true`. Auto/review/role confirmation không sửa manifest đã duyệt.
Một lần approval mới lưu bản cũ vào `SENSITIVE-approved-<hash>.json`, ghi receipt
`segments.approval.json` bind manifest/source SHA. Sửa recording hoặc approved manifest
sau đó làm validate yêu cầu review lại. Manifest viết tay cũ không có receipt vẫn dùng được.

Sau validate, chạy **đúng lệnh Azure smoke/full ở bước 4–5**. Không có bước diarization nào
bật `--allow-live` thay bạn. Azure/Luna full chỉ nhận approved candidate windows, cùng
CPU VAD, speech evidence cache, scorer và overall rounding hiện có.

### Resources, cache và fallback

Mặc định 2 CPU threads, 4 GiB RSS process family, timeout 30 phút, tối đa 8 speaker clusters
(ceiling cấu hình, không phải xác nhận speaker count thật). Parent dừng/wait process native
trước khi xóa PCM temporary; model không còn nằm trong memory khi CLI thoát. Có thể tạo
private config rồi truyền `--diarization-config <path-trong-input>`:

```json
{"schema_version":1,"threads":2,"memory_mb":4096,"timeout":1800,"max_speakers":8,"pause_tolerance_ms":3000}
```

`--diarization-python <existing-python>` và `--diarization-model-dir <local-model>` chọn
environment/cache đã setup. `--diarization-device cuda` chỉ dùng GPU **đã có sẵn** trong
compatible environment; CPU lock mặc định không có CUDA/NVIDIA packages, không cấp phát
Modal T4/L4. Không tự đổi provider khi thiếu DLL/model, timeout hoặc quá memory.

Cache bind source SHA/name, model/revision, normalization version và local inference config.
Đổi Luna prompt, human labels hoặc Part/question review không chạy lại model. Đổi pause
tolerance chỉ tạo lại proposals từ raw diarization. Review không sửa/xóa Azure checkpoints;
grading reuse cơ chế cache hiện có theo audio windows/config thực sự đã chọn.
Nếu source/model identity đổi, tool lưu state operator cũ vào `SENSITIVE-review-<hash>.json`
và yêu cầu xác nhận lại; không áp xác nhận cũ lên một clustering mới.

Nếu model không chạy được, vẫn dùng `--prepare` và manual `segments.json`. Không cần cài
pyannote để tiếp tục workflow manual. Thiếu model/env trả domain code actionable; xem
`tools/speaking_diarization/README.md`. Không có fallback paid/cloud nào.

### Evaluation và kiểm thử model opt-in

Không có human segmentation truth thì `diarization-evaluation.json` ghi
`HUMAN_SEGMENTATION_UNAVAILABLE`, metrics null. Có thể cung cấp private
`segmentation_labels.json` theo `HumanSegmentation` trong
`backend/app/evaluation/speaking/diarization_evaluation.py`: source SHA, verified human
provenance, `annotation_complete`, role-labelled turns và optional response/Part windows.
Labels chỉ được đọc sau inference để report, không đi vào model/proposal cache.

Metrics hỗ trợ candidate coverage/excluded ms, examiner contamination, matched candidate-turn
boundary MAE, Part assignment trên thời lượng đã assign và response matching IoU ≥0.5.
Binary candidate attribution error là `(missed_candidate_ms + examiner_contamination_ms)`
chia reference candidate+examiner speaker-time. Đây là metric theo vai trò cho mục tiêu
contamination, **không phải full multi-speaker DER**; overlap được tính riêng theo speaker-time.
Thiếu nhãn/denominator trả null, không bịa accuracy. Một recording không chứng minh fairness
theo accent, similar voices, examiner contamination tổng quát hoặc độ đúng band IELTS.

Real-model test cần một private recording tối đa hai phút, ít nhất hai người nói thật, hợp pháp, kèm
`integration-permission.json` (`legally_usable:true`, `human_verified_speakers:2`), model đã setup:

```powershell
$env:SPEAKING_DIARIZATION_INTEGRATION="1"
$env:SPEAKING_DIARIZATION_INTEGRATION_INPUT="C:/Users/Admin/IELTS_Self_Practising_Web/benchmarks/speaking/private/replay"
uv run --project backend pytest backend/tests/test_speaking_diarization_integration.py -q
Remove-Item Env:SPEAKING_DIARIZATION_INTEGRATION
Remove-Item Env:SPEAKING_DIARIZATION_INTEGRATION_INPUT
```

Không tự tải weights hoặc audio trong test; không gọi Azure/OpenAI. Sine/tone fixtures chỉ
kiểm tra decoder, timeline, UI và orchestration, **không chứng minh diarization accuracy**.
Test opt-in chạy native model trực tiếp, không lấy kết quả từ cache diarization; không ghi đè
proposal/approved manifest hoặc Azure checkpoints. Test không tự tính accuracy nếu thiếu nhãn human.

Chạy contracts/replay offline từ root (không cần isolated model environment):

```powershell
$replayTests = @(rg --files backend/tests | Where-Object { $_ -match 'test_speaking_(diarization|segment_review|replay)' })
uv run --project backend pytest @replayTests -q
```

Kết quả thực tế khi triển khai trên `7a3fe4a` + working changes:

| Kiểm tra | Kết quả | Phạm vi |
| --- | --- | --- |
| Lệnh contracts/replay ở trên | 71 passed, 12 skipped | Chạy từ root, giữ nguyên dotenv/operator settings |
| Windows offline regression | 358 passed, 12 skipped | Replay/diarization, legacy ASR/features, Azure mocks, benchmark, hybrid evidence, scorer, config/Modal composition |
| Docker CPU, `--network none` | 81 passed, 1 skipped, 1 deselected | Replay/diarization; MP3/WAV decode và file tổng hợp 14 phút thực sự chạy với FFmpeg |
| Ruff + isolated `uv lock --check` | Pass | 562 Python files formatted; resolve 90 packages, không cài/tải weights |
| Chromium local file | Pass | Seek/start/stop window, no autoplay, zero external requests; desktop/mobile không tràn ngang body |

Windows skips gồm 10 decoder tests khi host thiếu FFmpeg, một symlink test thiếu quyền và
real-model test opt-in. Docker skip real-model test; deselect Git-ignore test vì image test
không có Git (test đó pass trên host). Bộ Windows chạy không đọc dotenv cá nhân; composition
tests chạy cuối vì loader legacy có thay environment. Lượt chạy rộng ban đầu đọc dotenv gây
legacy-profile assertion failures; bốn DB-worker tests không setup được vì PostgreSQL test
không chạy. Không sửa CI/DB hoặc scoring policy để bỏ qua các điều kiện này; DB integration
được kiểm tra sau đó trên hai PostgreSQL test tạm: **248 passed** cho các nhóm Modal,
transcript, scoring, history và storage liên quan đến lỗi CI trước đó. Không có Azure/OpenAI
request hay native diarization inference trong các kết quả trên. HTML/audio tổng hợp chỉ
phục vụ kiểm tra giao diện, không phải mẫu benchmark.

### Troubleshooting

- **Windows thiếu FFmpeg/ffprobe:** cài cả hai, cùng thư mục trên PATH hoặc cấu hình
  `SPEAKING_FFMPEG_PATH`; static FFmpeg executable không bảo đảm có shared DLL cho TorchCodec.
- **TorchCodec/native DLL error:** kiểm tra đúng isolated Python 3.12 và pinned CPU packages,
  FFmpeg shared libraries 4–7/VC runtime; không downgrade backend. Nếu native Windows chưa chạy,
  dùng Linux/WSL environment riêng với cùng lock, hoặc giữ manual segmentation.
- **Model missing/HF 401/403:** chấp nhận đúng model conditions, cấp read token riêng qua
  private file/prompt, chạy lại explicit setup; inference sẽ không tự download.
  Setup trả `REPLAY_DIARIZATION_MODEL_DOWNLOAD_FAILED_CHECK_HF_ACCESS` thay raw Hub error.
  Asset đã thay đổi trả `REPLAY_DIARIZATION_MODEL_ASSET_MISSING_OR_CHANGED`; giữ thư mục cũ
  để kiểm tra và setup vào `--diarization-model-dir` mới, không ghi đè weights đang có.
- **Sai cluster, similar voices, noise/overlap:** nghe ví dụ từng speaker, sửa confirmation,
  chỉnh/exclude window. Nếu model không tách được examiner khỏi candidate, không full-grade
  đề xuất đó; trở lại manual. Không coi duration, speaker number hoặc heuristic là ground truth.
- **Resource limit/timeout:** giảm recording length bằng bộ file Part hợp lệ hoặc cấu hình
  giới hạn phù hợp; không lách grading response cap hay tự bật dịch vụ GPU/cloud.

Lần triển khai này chưa có weights/recording hai speaker thật được phép chạy:
**MODEL_UNVERIFIED, LIVE_UNVERIFIED**. Dependency resolution và contract tests không xác nhận
native model execution, DER, latency CPU thực tế hoặc độ chính xác phân vai. Không có giá
provider mới cho local inference; CPU/RAM/disk và thời gian tải weights vẫn là tài nguyên thật.
