# 🗺️ Lộ trình phát triển BandPilot

## ✅ Phase 1 — Nền tảng

Next.js, FastAPI, PostgreSQL, SQLAlchemy/Alembic, version bất biến, attempt, timer phía server,
AFK, lưu asset cục bộ, API typed, seed hư cấu và bộ kiểm thử nền đã hoàn thành.

## ✅ Phase 2 — Reading MVP

- Reading Builder với passage block ổn định.
- Nhiều question group trong một passage.
- Multiple Choice — Single, T/F/NG, Text Completion, Matching Headings.
- Answer key nhập trực tiếp trong Builder.
- Edit/Preview dùng chung renderer với màn hình thi.
- Reading runner chia đôi, autosave, flag, timer countdown/count-up, heartbeat/AFK.
- Highlight semantic offset, snap theo nguyên từ, lưu và xóa qua FastAPI.
- Chấm điểm backend và review giữ nguyên bố cục.
- Active Exam DTO không chứa answer key.

## ✅ Phase 3 — Đủ loại câu hỏi Reading

- [x] Multiple Choice — Multiple Answers
- [x] Yes / No / Not Given
- [x] Matching Information
- [x] Matching Features
- [x] Matching Sentence Endings
- [x] Sentence Completion
- [x] Summary Completion — Text
- [x] Summary Completion — Word List
- [x] Note Completion
- [x] Table Completion
- [x] Flow-chart Completion
- [x] Diagram Label Completion
- [x] Short Answer

Mỗi loại chỉ được đánh dấu hoàn thành khi có Builder, key editor, Pydantic/Zod validation,
exam renderer, backend evaluator, review renderer và tests.

## ✅ Phase 4 — Listening

- [x] Part 1–4, audio upload và nhiều group mỗi part
- [x] MCQ Single/Multiple, Matching
- [x] Plan/Map/Diagram Labelling với tọa độ chuẩn hóa
- [x] Form, Note, Table, Flow-chart, Summary, Sentence Completion và Short Answer
- [x] Audio policy: practice linh hoạt, Full Mock khóa seek/rewind/speed
- [x] Autosave, timer, AFK, scoring và review

## ✅ Phase 5 — Writing

- [x] Task 1 + hình ảnh, Task 2
- [x] Plain-text editor, word count, autosave, timer, AFK, history/review
- [x] Chấm thủ công theo TA/TR, CC, LR, GRA và band tổng hợp
- [x] Feedback plain text tùy chọn theo từng tiêu chí
- [x] AI Academic Writing Task 1/Task 2: score-first và phản hồi tham khảo; [kiến trúc/giới hạn hiện tại](ai-writing.md)

## ✅ Phase 6 — Full Mock và Analytics nền tảng

- Full Mock mới liên kết bốn attempt theo Listening → Reading → Writing → Speaking và chỉ tạo attempt khi bắt đầu module; lịch sử mock ba kỹ năng cũ vẫn đọc được.
- Pause/resume theo policy kỹ năng, chuyển module, review lock đến khi toàn bộ mock hoàn tất, History và overall khi có đủ bốn band; Speaking AI luôn là tham khảo.
- Overview band/time, band trend, độ chính xác theo loại câu, weak areas với ngưỡng 5 câu.
- So sánh hai attempt và timing active theo passage/Listening part/Writing task cho dữ liệu mới.
- Dữ liệu cũ không có event timing vẫn hiển thị an toàn.

## ✅ Speaking P1–P8

- [x] Builder ba phần, prompt có cấu trúc và published version bất biến
- [x] Runner với microphone preflight, timestamp/deadline phía server và recovery
- [x] Chunk upload riêng tư, container segment tách biệt sau recovery và review có kiểm tra quyền
- [x] FFmpeg normalization, transcript verbatim/clean, quality/fluency/pronunciation evidence
- [x] Advisory AI score-first theo FC/LR/GRA/PR, durable worker/event và xử lý thiếu bằng chứng
- [x] Full Mock, History và kết quả lớp học chỉ đọc theo assignment provenance
- [x] Benchmark tooling offline/configured; chưa xác lập độ chính xác tương đương giám khảo

Chi tiết: [ai-speaking.md](ai-speaking.md). Trên Modal, faster-whisper ASR dùng T4 riêng; Web xử lý normalization trên CPU, Writing/Speaking dùng chung Ministral/vLLM L4, hai GPU scale-to-zero. Xem [modal-web.md](modal-web.md).

## ✅ Builder resilience và Test Transfer

- [x] Autosave draft dùng mutation queue, debounce, generation tracking, retry và flush trước lifecycle actions
- [x] Transfer Portal xuất/nhập test content cùng referenced image/audio bằng ZIP versioned có checksum
- [x] Import tạo UUID/path mới, remap structured question references và không mang theo attempt/history/analytics

Chi tiết contract ZIP: [TEST_TRANSFER_FORMAT.md](TEST_TRANSFER_FORMAT.md).

## ✅ MVP engineering baseline

- Reading, Listening, Writing, Speaking và Full Mock; authentication/phiên đăng nhập liên tục giữa các tab, Profile và quản trị tài khoản đã triển khai.
- Personalization cho Accent Color, Light/Dark và EN/VI theo tài khoản; Teacher/Classroom với duyệt nội dung, bài giao và kết quả chỉ đọc.
- Published version bất biến; historical asset access; autosave/revision và xử lý xung đột, khôi phục draft sau reload/mất mạng ngắn hạn.
- Transfer ZIP cho nội dung đề; backup/restore offline cho toàn bộ PostgreSQL và binary storage.
- Pytest, Vitest, Playwright golden paths và GitHub Actions CI/E2E là các gate kiểm thử hiện có.

Mốc này là baseline kỹ thuật của MVP, **không đồng nghĩa sẵn sàng vận hành thương mại hoặc cloud production**.

## ⏳ Tiếp theo

- Mở rộng drill-down analytics và bộ lọc ngày/test version.
- Tiếp tục cải thiện accessibility, keyboard navigation và Builder ergonomics.
- Tăng độ bền deployment/observability và bảo vệ backup khi có nhu cầu vận hành production; deployment Modal hiện có không đồng nghĩa dữ liệu local/cloud tự đồng bộ.
