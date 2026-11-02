# Định dạng gói chuyển nội dung đề thi

> **Phân loại tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đối chiếu boundaries/API từ source, không xác minh deployment đang chạy.
> Mục đích: định dạng gói chuyển nội dung đề thi. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/schemas/transfer.py).
> Đọc cùng [hướng dẫn module hiện hành](modules/assets-transfer.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả tests/benchmark bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Gói đề thi BandPilot dùng format identifier `devweblocalforielts-test-bundle`. Bản export không có cover giữ schema version 1; bản có test cover dùng schema version 2. Import chấp nhận cả hai versions; gói version 1 hiện có không bắt buộc bổ sung cover.

```text
ielts-test-bundle.zip
├── manifest.json
├── tests/<source-test-uuid>.json
└── assets/<sha256>-<source-asset-uuid>.<extension>
```

Manifest liệt kê mọi test JSON và asset được tham chiếu. Các phần tử `assets` của version 1 xác định TestVersion nguồn, package path, asset type, MIME type, tên file gốc, kích thước và SHA-256 checksum. Version 2 thêm mảng `covers`: mỗi cover có source ID riêng, `source_test_id` sở hữu, package path an toàn, MIME type, filename, size và checksum. Test JSON tương ứng tham chiếu cover qua `cover_id`. Cover thuộc logical Test, không thuộc version. Không đưa absolute local storage paths vào gói.

Test JSON contract tường minh chứa logical tests, version numbers và lifecycle states, modules, Reading passages, Listening parts, Writing tasks gồm structured `task_type` tags tùy chọn, Speaking parts/prompts, question groups, questions, configurations và answer keys. Gói cũ thiếu `task_type` sẽ import tasks ở trạng thái chưa phân loại; module cũ thiếu `speaking_parts` mặc định là danh sách rỗng. Module durations được giữ nguyên; legacy durations bị thiếu nhận canonical defaults khi import. Chỉ cover, Listening audio, question images và Writing Task images thực sự được tham chiếu mới có trong gói. Candidate Speaking recordings, transcripts và grading results là private attempt data nên bị loại trừ.

Gói không chứa attempts, responses, highlights, flags, events, Writing scores/feedback, History, Analytics hoặc Full Mock sessions. Đây là cơ chế chuyển nội dung đề thi, không phải bản backup ứng dụng.

Trước commit, import kiểm safe paths, số file và tổng dung lượng sau giải nén, JSON schemas, tính nhất quán lifecycle, MIME/extension/signature, kích thước cover, byte sizes, checksums, ownership và references. Tất cả database identifiers và storage filenames được tạo mới; các structured references `question_id` được ánh xạ lại theo domain. Import cùng gói nhiều lần tạo các tests/covers độc lập. Nếu import thất bại, hệ thống dọn những file do operation tạo; nếu không truy vấn được database sau một commit có kết quả chưa rõ, phải giữ các file có thể đang được tham chiếu để đối soát, không xóa ngay.
