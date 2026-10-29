# Speaking: recording, processing, scoring và recovery

> Mục đích và phạm vi: Ghi âm riêng tư có khả năng khôi phục, xử lý transcript/evidence và tách AI khỏi human final.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## A–C. Mục đích, workflow và ownership

Ghi âm riêng tư có khả năng khôi phục, xử lý transcript/evidence và tách AI khỏi human final.

Builder tạo Part 1/2/3 và prompts. Runner preflight microphone, bắt đầu prompt/take, gửi segmented chunks, finish bằng manifest. Người học review audio/transcript, yêu cầu AI khi configured; teacher có quyền xem/grading theo assignment provenance.

SpeakingAttemptService owns prompt timing; SpeakingMediaService owns raw media; TranscriptWorker owns normalization/ASR/evidence; SpeakingAIWorker owns advisory run. Frontend recorder quản lý MediaRecorder và transport, không tự xác nhận prompt đã hoàn tất.

## D. Implementation map

| Lớp | Source |
| --- | --- |
| UI/client | [frontend/src/features/speaking/](../../frontend/src/features/speaking/); [frontend/src/lib/api/speaking.ts](../../frontend/src/lib/api/speaking.ts); [frontend/src/lib/api/speaking-transcript.ts](../../frontend/src/lib/api/speaking-transcript.ts); [frontend/src/lib/api/speaking-ai.ts](../../frontend/src/lib/api/speaking-ai.ts) |
| Routes/schemas | [backend/app/api/v1/speaking.py](../../backend/app/api/v1/speaking.py); [backend/app/api/v1/speaking_ai.py](../../backend/app/api/v1/speaking_ai.py); [backend/app/schemas/speaking.py](../../backend/app/schemas/speaking.py); [backend/app/schemas/speaking_ai_runs.py](../../backend/app/schemas/speaking_ai_runs.py) |
| Services/workers | [backend/app/services/speaking_attempts.py](../../backend/app/services/speaking_attempts.py); [backend/app/services/speaking_media.py](../../backend/app/services/speaking_media.py); [backend/app/services/speaking_transcript_worker.py](../../backend/app/services/speaking_transcript_worker.py); [backend/app/services/speaking_ai_worker.py](../../backend/app/services/speaking_ai_worker.py); [backend/app/services/speaking_final.py](../../backend/app/services/speaking_final.py) |
| Repositories/models | [backend/app/repositories/speaking.py](../../backend/app/repositories/speaking.py); [backend/app/repositories/speaking_transcript.py](../../backend/app/repositories/speaking_transcript.py); [backend/app/repositories/speaking_ai.py](../../backend/app/repositories/speaking_ai.py); [backend/app/models/speaking.py](../../backend/app/models/speaking.py); [backend/app/models/speaking_transcript.py](../../backend/app/models/speaking_transcript.py); [backend/app/models/speaking_ai.py](../../backend/app/models/speaking_ai.py) |
| Tests | [backend/tests/test_speaking_media.py](../../backend/tests/test_speaking_media.py); [backend/tests/test_full_mock_speaking.py](../../backend/tests/test_full_mock_speaking.py); [frontend/tests/speaking-transport.test.ts](../../frontend/tests/speaking-transport.test.ts); [frontend/tests/speaking-runner.test.tsx](../../frontend/tests/speaking-runner.test.tsx) |

## E–F. Data flow và API contracts

Prompt state → acknowledged raw chunks → committed take → normalized WAV → ASR/timings → quality/fluency/pronunciation bundle → advisory criterion scores/feedback → explicit human final workflow riêng. Xem sequence trong [AI architecture](../handbook/ai-architecture.md).

Các đường dẫn sau dùng prefix `/api/v1`; DTO, dependency và response model ở router được dẫn trong bảng. [Source map](../handbook/source-map.md) liệt kê toàn bộ route cùng khai báo gốc.

- `GET /speaking-attempts/{attempt_id}/state`
- `POST /speaking-attempts/{attempt_id}/begin`
- `POST /speaking-attempts/{attempt_id}/segments`
- `PUT /speaking-attempts/{attempt_id}/segments/{segment_id}/chunks/{sequence}`
- `POST /speaking-attempts/{attempt_id}/finish`
- `POST /speaking-attempts/{attempt_id}/transcript-runs`
- `POST /speaking-attempts/{attempt_id}/ai-runs`
- `PUT /speaking-attempts/{attempt_id}/final-score`

## G. Persistence

Part/Prompt authored content, Response/Take/PromptProgress runtime state; AudioSegment/Chunk tham chiếu private storage. NormalizedAudio, TranscriptRun/Event/Transcript và AIGradingRun/Event có identity và checkpoints. MediaCleanup lưu công việc dọn private artifacts; AttemptSpeakingScore là human final.

## H. Business rules

Recovery tạo container segment mới, không nối byte của các MediaRecorder container khác nhau tùy ý. Chunk sequence và manifest kiểm đầy đủ/idempotency. Prompt deadlines/recovery không được dùng để time farming. Scratch notes loại khỏi chấm. PR cần acoustic evidence; missing/unusable audio không sinh score mặc định.

## I. Security

Mọi private media/transcript/events kiểm owner hoặc assignment provenance. Teacher/ADMIN observer không có candidate run/cancel quyền chỉ vì đọc được result. API sensitive errors không echo body/paths. Retained classwork artifacts xử lý khác personal deletion.

## J. Failure và recovery

FFmpeg normalization trước ASR; cached derivatives có fingerprint/integrity check và rebuild path. Lease fencing ngăn stale worker checkpoint sau recovery. Startup recover Speaking workers; cleanup outbox xử lý raw/derived storage. Explicit cancel không được phá transcript task dùng chung.

## K. Focused testing

Media retry/sequence/lost-ack tests, transcript/evidence/AI workers bằng fake provider, Full Mock Speaking, private range/storage và frontend transport tests. Live microphone/browser/ASR/GPU chưa chạy trong audit này.

## L. Extension guide

Đọc binding spec + plan + self-review trước thay Speaking. Thêm processing stage phải thiết kế cache fingerprint, lease/checkpoint, sanitized errors, cleanup và observer semantics; không nhét inference vào GET review.

## M. Giới hạn

ASR/grading optional. Pronunciation evidence là proxy giới hạn, không phoneme-level examiner guarantee. Browser codec/network failure cần thật sự test thiết bị nếu thay recorder; unit tests không bao quát mọi microphone.

## N. Câu hỏi phỏng vấn

**1. Vì sao cần segment khi recover?** Mỗi recording container có header/codec lifecycle riêng; chunk ordering không tự làm các container tương thích.

**2. Fencing token làm gì?** Chỉ worker giữ lease hiện hành được commit; worker cũ hoàn thành muộn bị chặn.

**3. Vì sao PR không lấy transcript?** Transcript không chứa đủ âm thanh để suy phát âm; cần evidence acoustic và giới hạn rõ.

## Tài liệu liên quan

[Canonical Speaking](../ai-speaking.md), [recording](../speaking-recording.md), [transcription](../speaking-transcription.md), [grading](../speaking-grading.md), [binding amendments](../superpowers/plans/2026-10-11-speaking-engine-ai-grading-self-review.md).
