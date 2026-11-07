# Kho kiến thức kỹ thuật BandPilot

> Mục đích: tài liệu học hệ thống và bản đồ triển khai tính năng cho chủ dự án/Codex. Revision mã nguồn được kiểm toán: `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Phạm vi là mã nguồn đã commit; không xác nhận trạng thái cloud/cơ sở dữ liệu đang chạy.

## Lộ trình A — Hiểu hệ thống BandPilot

1. [Tổng quan hệ thống](handbook/system-overview.md): sản phẩm, role, quyền thao tác và giới hạn.
2. [Ranh giới kiến trúc](architecture.md) → [sơ đồ môi trường chạy](handbook/runtime-architecture.md): tiến trình và mạng.
3. [Danh mục mô-đun](handbook/module-catalog.md): chọn mô-đun, đọc bản đồ mã nguồn.
4. [Kiến trúc dữ liệu](handbook/data-architecture.md): ER, JSONB, transaction, tính nhất quán lưu trữ.
5. [Vòng đời attempt](modules/attempts.md) → [quy trình lớp học](modules/classrooms.md): request/trạng thái/sự kiện.
6. [Kiến trúc AI](handbook/ai-architecture.md) → [Writing](ai-writing.md) / [Speaking](ai-speaking.md).
7. [Hạ tầng](handbook/infrastructure.md) → [vận hành Modal](modal-web.md) / [cấu hình AWS](aws-deployment.md).
8. [Bảo mật và độ tin cậy](handbook/security-and-reliability.md).
9. [Kiểm thử và bàn giao](handbook/testing-and-delivery.md).
10. [Nghiên cứu tình huống hiệu năng Modal](case-studies/modal-web-performance.md), [thử nghiệm độ trễ Writing](enhance_latency.md).
11. [Quyết định kỹ thuật](handbook/engineering-decisions.md).
12. [Hướng dẫn phỏng vấn thiết kế hệ thống: 44 câu hỏi](interview/bandpilot-system-design.md), [hỏi đáp chuyên sâu về Modal](interview/modal-performance-qa.md).
13. [Khảo sát khả năng phục vụ 5.000 người dùng](performance/5000-user-capacity.md) → [nghiên cứu tình huống](case-studies/5000-user-scalability.md) → [tái lập thử tải](../benchmarks/load/README.md) → [hỏi đáp về mở rộng](interview/5000-user-scalability-qa.md).

## Lộ trình B — Phát triển BandPilot

1. [AGENTS ở root](../AGENTS.md) và [chỉ dẫn frontend được sinh tự động](../frontend/AGENTS.md).
2. [Ranh giới kiến trúc](architecture.md), rồi [mô-đun chịu trách nhiệm](handbook/module-catalog.md).
3. Hướng dẫn mô-đun liên quan → router/schema/model/client có kiểu trong [bản đồ mã nguồn](handbook/source-map.md).
4. [Ranh giới dữ liệu](handbook/data-architecture.md) và [quyền thao tác/bảo mật](handbook/security-and-reliability.md).
5. [Hướng dẫn phát triển tính năng và ma trận ảnh hưởng](handbook/feature-development-playbook.md).
6. [Kiểm thử tập trung](handbook/testing-and-delivery.md), rồi hướng dẫn vận hành chuẩn nếu nhiệm vụ có phạm vi triển khai.

Không cần đọc mọi kế hoạch lịch sử. Khi thay đổi Speaking vẫn phải đọc [thiết kế có tính ràng buộc](superpowers/specs/2026-10-11-speaking-engine-ai-grading-design.md), [kế hoạch](superpowers/plans/2026-10-11-speaking-engine-ai-grading.md) và [bổ sung tự rà soát](superpowers/plans/2026-10-11-speaking-engine-ai-grading-self-review.md) theo AGENTS.

## Mục lục tài liệu chuẩn theo chủ đề

| Chủ đề | Giải thích chuẩn | Liên quan |
| --- | --- | --- |
| Phân chia trách nhiệm kiến trúc | [kiến trúc](architecture.md) | cẩm nang giải thích/sơ đồ, không thay các bất biến |
| Triển khai nghiệp vụ | [danh mục mô-đun](handbook/module-catalog.md) | [mục lục API/model/trang](handbook/source-map.md) |
| AI Writing | [AI Writing](ai-writing.md) | [OpenAI GPT-6 Luna: local/Modal CPU/AWS](ai-writing.md#openai-gpt6-luna), [ngân hàng benchmark](writing-benchmark-bank.md) |
| AI/runtime Speaking | [AI Speaking](ai-speaking.md) | [ghi âm](speaking-recording.md), [chép lời](speaking-transcription.md), [chấm điểm](speaking-grading.md), [replay MP3/WAV offline và live opt-in](testing/speaking-audio-replay.md) |
| Admin Speaking Benchmark Lab | [Phase 1: dataset và review](testing/admin-speaking-benchmark.md), [Phase 2: AI evaluation và metrics](testing/admin-speaking-benchmark-evaluation.md) | upload riêng tư, phân tách người nói CPU, manifest được duyệt, nhãn người chấm, durable request ledger, AI grading worker, dashboard đối sánh Human vs AI và formula-safe export |
| Lưu trữ | [kiến trúc](storage-architecture.md) | [di chuyển](storage-migration.md), [sao lưu](storage-backup-restore.md) |
| Chuyển dữ liệu / import bản nháp | [hợp đồng ZIP](TEST_TRANSFER_FORMAT.md) | [hợp đồng JSON bản nháp](draft-import-format.md) |
| Chính sách lớp học | [hướng dẫn mô-đun](modules/classrooms.md) | [lịch bài giao](classroom-assignment-scheduling.md), [sổ điểm](classroom-gradebook.md), [học tập](classroom-learning-analytics.md), [lưu trữ/xóa](classroom-archive-calendar.md) |
| Triển khai | [Modal](modal-web.md), [AWS](aws-deployment.md) | [tổng quan cấu trúc triển khai](handbook/infrastructure.md) |
| Hiệu năng Modal đã đo | [báo cáo gốc](modal-web-performance.md) | [nghiên cứu tình huống để học](case-studies/modal-web-performance.md) |
| Khả năng phục vụ người học đang hoạt động | [báo cáo 5.000 người dùng](performance/5000-user-capacity.md) | [bằng chứng](performance/5000-user/evidence.json), [công cụ thử tải](../benchmarks/load/README.md) |

## Bằng chứng lịch sử và tính cập nhật

[Quy ước tiếng Việt kỹ thuật](handbook/documentation-language.md) nêu cách giữ thuật ngữ, code, liên kết và bằng chứng khi biên tập tài liệu.

[DOCS_AUDIT](DOCS_AUDIT.md) phân loại mọi tài liệu được Git theo dõi ở mốc ban đầu. [Mục lục Superpowers](superpowers/README.md) chỉ rõ kế hoạch/đặc tả lịch sử và ngoại lệ Speaking còn ràng buộc. [DOCUMENTATION_COVERAGE](DOCUMENTATION_COVERAGE.md) ghi phạm vi/khoảng trống đã biết. Không xóa JSON benchmark, đổi số liệu hay biến báo cáo giai đoạn thành hợp đồng hiện hành.

Khi đổi tuyến/schema/thực thể/bất biến/provider/triển khai, cập nhật tài liệu chuẩn cùng commit; hướng dẫn mô-đun chỉ giữ tóm tắt và đường dẫn, không sao chép prompt hay hướng dẫn vận hành dài. Ghi commit mã nguồn thực sự đã đối chiếu và giới hạn kiểm chứng, không ghi ngày cập nhật giả định. Với báo cáo lịch sử, thêm đính chính/trạng thái riêng, không sửa phép đo cũ. Nếu hai tài liệu mâu thuẫn, kiểm tra mã/test rồi sửa nguồn chuẩn và liên kết từ nơi khác.

Đường dẫn mã nguồn, liên kết cục bộ, khai báo API, tên model, phép tính và cấu trúc sơ đồ được kiểm tra ngoại tuyến; không có trình duyệt/triển khai/bộ test trong lần kiểm toán này. Tài liệu không chứng minh mọi khả năng runtime đều đang bật. Hướng dẫn vận hành có thể chứa lệnh thay đổi trạng thái: chỉ chạy trong phạm vi người dùng/người vận hành cho phép, với cơ sở dữ liệu/Secret/Volume đã xác nhận.
