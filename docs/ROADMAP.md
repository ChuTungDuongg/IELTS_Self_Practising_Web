# 🗺️ Lộ trình phát triển

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
- [x] Chấm thủ công theo TA/CC/LR/GRA và band tổng hợp
- [x] Feedback plain text tùy chọn theo từng tiêu chí TA/CC/LR/GRA
- [ ] AI scoring (chỉ triển khai khi có yêu cầu riêng)

## ✅ Phase 6 — Full Mock và Analytics nền tảng

- Full Mock session liên kết ba attempt theo Listening → Reading → Writing và chỉ tạo attempt khi bắt đầu module.
- Pause/resume, chuyển module, review lock, History và overall sau khi Writing được chấm.
- Overview band/time, band trend, độ chính xác theo loại câu, weak areas với ngưỡng 5 câu.
- So sánh hai attempt và timing active theo passage/Listening part/Writing task cho dữ liệu mới.
- Dữ liệu cũ không có event timing vẫn hiển thị an toàn.

## ✅ Builder resilience và Test Transfer

- [x] Autosave draft dùng mutation queue, debounce, generation tracking, retry và flush trước lifecycle actions
- [x] Transfer Portal xuất/nhập test content cùng referenced image/audio bằng ZIP versioned có checksum
- [x] Import tạo UUID/path mới, remap structured question references và không mang theo attempt/history/analytics

Chi tiết contract ZIP: [TEST_TRANSFER_FORMAT.md](TEST_TRANSFER_FORMAT.md).

## ⏳ Tiếp theo

- Mở rộng drill-down analytics và bộ lọc ngày/test version.
- Tiếp tục cải thiện accessibility, keyboard navigation và Builder ergonomics.
- Speaking, authentication và AI Writing scoring vẫn ngoài phạm vi hiện tại.
