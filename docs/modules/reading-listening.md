# Reading và Listening: objective question engine

> Mục đích và phạm vi: Luyện và đánh giá các câu khách quan qua chung registry, với presentation/policy riêng từng kỹ năng.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## A–C. Mục đích, workflow và ownership

Luyện và đánh giá các câu khách quan qua chung registry, với presentation/policy riêng từng kỹ năng.

Reading hiển thị passage và question groups, highlight/flag và autosave. Listening thêm recording module-level, section ranges và player policy. Người học chọn full module hoặc focused passage/section; submit/review dùng Attempt lifecycle chung.

Question domain sở hữu config/response/key/evaluation; runners chỉ render và gửi response. Listening service quản lý authored sections/audio reference; storage delivery quản lý bytes, không player React.

## D. Implementation map

| Lớp | Source |
| --- | --- |
| Pages/UI | [frontend/src/app/attempt/[attemptId]/page.tsx](../../frontend/src/app/attempt/[attemptId]/page.tsx); [frontend/src/app/review/[attemptId]/page.tsx](../../frontend/src/app/review/[attemptId]/page.tsx); [frontend/src/features/reading/](../../frontend/src/features/reading/); [frontend/src/features/listening/](../../frontend/src/features/listening/); [frontend/src/features/highlighting/](../../frontend/src/features/highlighting/) |
| Clients | [frontend/src/lib/api/exam.ts](../../frontend/src/lib/api/exam.ts); [frontend/src/lib/api/attempts.ts](../../frontend/src/lib/api/attempts.ts); [frontend/src/lib/api/assets.ts](../../frontend/src/lib/api/assets.ts) |
| Backend | [backend/app/api/v1/attempts.py](../../backend/app/api/v1/attempts.py); [backend/app/api/v1/listening.py](../../backend/app/api/v1/listening.py); [backend/app/services/reading.py](../../backend/app/services/reading.py); [backend/app/services/listening.py](../../backend/app/services/listening.py); [backend/app/repositories/attempts.py](../../backend/app/repositories/attempts.py) |
| Contracts/models | [backend/app/domains/questions/registry.py](../../backend/app/domains/questions/registry.py); [backend/app/schemas/attempts.py](../../backend/app/schemas/attempts.py); [backend/app/schemas/listening.py](../../backend/app/schemas/listening.py); [backend/app/models/entities.py](../../backend/app/models/entities.py) |
| Tests | [backend/tests/test_listening_audio_ranges.py](../../backend/tests/test_listening_audio_ranges.py); [backend/tests/test_completion_identity.py](../../backend/tests/test_completion_identity.py); [frontend/tests/listening-audio-ranges.test.tsx](../../frontend/tests/listening-audio-ranges.test.tsx); [frontend/tests/selectable-text.test.tsx](../../frontend/tests/selectable-text.test.tsx) |

## E–F. Data flow và API contracts

Question response → autosave queue → PUT với revision → AttemptService validate owner/scope/deadline → registry validate response → lưu. Submit đọc persisted responses → evaluator → score → review DTO đã được phép.

Các đường dẫn sau dùng prefix `/api/v1`; DTO, dependency và response model ở router được dẫn trong bảng. [Source map](../handbook/source-map.md) liệt kê toàn bộ route cùng khai báo gốc.

- `GET /attempts/{attempt_id}/exam`
- `PUT /attempts/{attempt_id}/answers/{question_id}`
- `GET /attempts/{attempt_id}/reading-review`
- `GET /attempts/{attempt_id}/listening-review`
- `POST /attempts/{attempt_id}/highlights`
- `PUT /listening/modules/{module_id}/audio`
- `GET /assets/{asset_id}/content`

## G. Persistence

ReadingPassage giữ blocks ổn định; ListeningPart có audio_start_seconds/audio_end_seconds tùy chọn, TestModule.audio_asset_id sở hữu recording chung. Answer theo question UUID; Highlight lưu source identity/semantic offsets, không HTML.

## H. Business rules

Các primitives single/multiple option, text, matching hỗ trợ MCQ, T/F/NG, Y/N/NG, matching families, sentence/summary/note/table/flow, marker labelling, short answer. Normalization và evaluation server-side. Focused unit không tạo full band; Reading/Listening band cần module 40 câu theo scoring contract.

## I. Security

Scope chọn question/passages phía server, không chỉ filter DOM. Full Mock khóa review/key đến khi session hoàn tất; audio access rechecks owner/content policy. Full Mock player hạn chế seek/speed qua policy; không coi UI là DRM.

## J. Failure và recovery

Không có audio/range metadata thì UI cần fallback đúng contract; không invent section clip. Out-of-range byte request hoặc unauthorized content không được đổi sang public URL. Highlight text phải khớp source offsets; submit phải flush pending answers.

## K. Focused testing

Question-contract tests kiểm evaluate/DTO; Listening range tests kiểm byte và section scope, player tests kiểm seek policy. Selectable text, word-boundaries, text-completion và highlight regression tests giữ semantic identity khi UI thay đổi.

## L. Extension guide

Thêm question family ở registry dùng chung; thêm Listening policy tại schema/service rồi player. Sửa passage rendering phải giữ block IDs/highlight mapping. Tính correctness không chuyển vào React để tối ưu latency.

## M. Giới hạn

Không thấy Reading/Listening LLM grading hoặc RAG trong route/provider hiện hành. Seek control là UX/exam policy chứ không ngăn người dùng kỹ thuật truy cập mọi byte họ được cấp quyền.

## N. Câu hỏi phỏng vấn

**1. Vì sao offset thay HTML?** Offset gắn nội dung semantic, ít phụ thuộc DOM và tránh lưu markup tùy ý.

**2. Vì sao không nhân bản audio mỗi section?** Một recording với ranges giảm copy và giữ nguồn chung; metadata phải được validate.

**3. Vì sao focused accuracy không thành IELTS band?** Số câu/phạm vi không tương đương module đầy đủ 40 câu.

## Tài liệu liên quan

[Attempts](attempts.md), [focused contracts](../focused-attempts.md), [question audit history](../question-engine-audit.md).
