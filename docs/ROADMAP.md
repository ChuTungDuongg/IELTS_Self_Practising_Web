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

## ⏳ Phase 3 — Đủ loại câu hỏi Reading

- [ ] Multiple Choice — Multiple Answers
- [ ] Yes / No / Not Given
- [ ] Matching Information
- [ ] Matching Features
- [ ] Matching Sentence Endings
- [ ] Sentence Completion
- [ ] Summary Completion — Text
- [ ] Summary Completion — Word List
- [ ] Note Completion
- [ ] Table Completion
- [ ] Flow-chart Completion
- [ ] Diagram Label Completion
- [ ] Short Answer

Mỗi loại chỉ được đánh dấu hoàn thành khi có Builder, key editor, Pydantic/Zod validation,
exam renderer, backend evaluator, review renderer và tests.

## ⏳ Phase 4 — Listening

- [ ] Part 1–4, audio upload và nhiều group mỗi part
- [ ] MCQ Single/Multiple, Matching
- [ ] Plan/Map/Diagram Labelling với tọa độ chuẩn hóa
- [ ] Form, Note, Table, Flow-chart, Summary, Sentence Completion và Short Answer
- [ ] Audio controller giới hạn seek/rewind/speed trong Exam Mode
- [ ] Autosave, timer, AFK, scoring và review

## ⏳ Phase 5 — Writing

- [ ] Task 1 + hình ảnh, Task 2
- [ ] Plain-text editor, word count, autosave, timer, AFK, history/review
- [ ] Không triển khai AI scoring cho đến khi có yêu cầu riêng

## ⏳ Phase 6 — Analytics & hoàn thiện

Độ chính xác theo loại câu hỏi, thời gian theo passage/group, so sánh attempt, lịch sử đổi đáp án
và cải thiện trải nghiệm Builder.
