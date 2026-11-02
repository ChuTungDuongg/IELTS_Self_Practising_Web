# Quy ước ngôn ngữ tài liệu BandPilot

Tài liệu giải thích cho người phát triển ưu tiên **tiếng Việt kỹ thuật**: câu rõ chủ ngữ, mô tả trách nhiệm và nguyên nhân cụ thể, giải thích thuật ngữ khi dùng lần đầu. Giữ thuật ngữ English đã phổ biến khi dịch làm giảm độ chính xác, như API, endpoint, request, transaction, checkpoint, lease, fencing, replica, throughput, p50/p95/p99 và SLO.

Tên sản phẩm, role/enums, identifiers, API paths, file paths, environment variables, lệnh và payload mẫu phải khớp mã nguồn. Không dịch một identifier rồi khiến người đọc không tìm được nó trong repository. Dùng khoảng trắng giữa số và đơn vị: 20 ms, 2 CPU, 1 GiB; không tách p95 thành “p 95”, S3 thành “S 3” hay tên CPU thành các từ rời.

## Phạm vi lượt chuẩn hóa ngày 2026-11-02

Đã rà tài liệu Markdown trong `docs/` và README benchmark. Các tài liệu trước đây có phần thân hoàn toàn bằng tiếng Anh đã được dịch, gồm architecture, AI, storage/deployment, classroom và plans/specs lịch sử. Lời mở đầu tiếng Việt không được coi là đã dịch nếu phần thân vẫn là English prose. Mục lục chuẩn tiếp tục ở [docs/README](../README.md).

Code fences, payloads, ví dụ đề hư cấu, identifiers và các báo cáo JSON giữ ngôn ngữ gốc để tái lập. Các hướng dẫn máy như AGENTS và tài liệu được công cụ sinh không thuộc phạm vi dịch văn xuôi này. Tệp local/untracked có sẵn của người dùng không được đưa vào commit của nhiệm vụ.

## Giữ nguyên ý nghĩa và bằng chứng

- Giữ độ mạnh của yêu cầu: “phải”, “không được” và điều kiện ngoại lệ không trở thành gợi ý tùy chọn khi dịch.
- Giữ trạng thái CURRENT/HISTORICAL/SUPERSEDED và ngày/source revision. Kế hoạch cũ không trở thành contract hiện hành chỉ vì đổi ngôn ngữ.
- Giữ số liệu gốc, phạm vi đo, failures, skips và các mục NOT RUN/NOT RECORDED/NOT VERIFIED. Không làm tròn hoặc diễn giải theo hướng tạo thành tích chưa đo.
- Giữ đích liên kết. Khi dịch heading có liên kết tới, thêm anchor tương thích hoặc sửa toàn bộ nơi tham chiếu.
- Chỉ đổi code fences khi sửa lỗi cú pháp hoặc cập nhật sơ đồ cho kiến trúc thực sự thay đổi; ghi rõ ngoại lệ trong hồ sơ kiểm chứng.

Lượt này sửa ba Mermaid blocks: hai sơ đồ cũ có dấu chấm phẩy gây lỗi parser; sơ đồ Writing đồng thời được cập nhật theo durable dispatch mới. Toàn bộ 26 Mermaid blocks đã qua parser 11.12.2; đây là kiểm cú pháp, chưa phải kiểm hình ảnh render. Các code fences thực thi còn lại được đối chiếu giữ nguyên. [Hồ sơ kiểm chứng](../performance/5000-user/verification.json) phân biệt kiểm tài liệu với tests runtime.
