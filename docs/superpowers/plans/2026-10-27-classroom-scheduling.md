# Nhật ký triển khai và kiểm chứng Classroom P2

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Classroom P2 implementation and verification ledger. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Phạm vi: attachment của user `2ac4d7c5-1241-4028-a6d5-fc6ecc47e77d/Pasted text.txt`. Mở rộng P1 ngay trên main; giữ các dirty files có sẵn. Không browser/E2E/full suites/build/dev stack. Áp dụng local migration như user đã yêu cầu trong cuộc trao đổi này.

## Quyết định về chính sách

- Các mốc thời gian là timezone-aware UTC. Availability mở theo biên bao gồm; submissions/starts đúng due/cutoff được chấp nhận. Late nghĩa là hoàn tất sau due theo so sánh nghiêm ngặt; hoàn tất sau cutoff không được chấp nhận.
- Legacy assignments mặc định không có windows/limit và `allow_late_submission=true`.
- Root Attempt SUBMITTED/AUTO_SUBMITTED là submission; INTERRUPTED/ABANDONED không phải. Full Mock cần parent COMPLETED và tất cả expected modules đã submitted/auto-submitted; child completion riêng không bao giờ đáp ứng assignment.
- Append-only normalized policy events ghi base changes và individual override changes. Read models tính effective policy **tại authoritative root completion timestamp**, độc lập với thời điểm đọc. Sửa schedule/extension sau đó không được đổi nhãn earlier completions. Completions trước P2 dùng legacy unrestricted policy. In-progress work dùng những thay đổi có hiệu lực trước lúc hoàn tất. Giữ existing engine finalization paths, gồm Speaking, timeout và Full Mock.
- Overrides dùng explicit override booleans: false kế thừa; true cộng null bỏ deadline. Extensions không được rút ngắn finite base deadline. Additional attempts không giới hạn unlimited policies. Revocation nối thêm history và khôi phục inheritance cho future completion/start decisions.
- Start checks chạy dưới existing actor→version→classroom→assignment locks; successful root starts ở mọi modes dùng chung một slot, kể cả abandoned work. Resume không tạo root mới.
- Progress ưu tiên accepted completion mới nhất, rồi active work, rồi unaccepted submission mới nhất. MISSED yêu cầu eligible enrollment tại/trước closure; người tham gia sau closure là NOT_STARTED. Mọi counts/status decisions dùng scoped SQL roots và bulk queries, không lấy personal practice.
- Reminders: bounded one-shot CLI; nhắc due-soon24giờ và overdue. Idempotency keys gồm effective deadlines/policy. Deployment scheduling chỉ được hướng dẫn, không tuyên bố đã deploy.

## Công việc

- [x] Audit origin/main, P1, locks, engine finalization và notification/storage conventions.
- [x] Thêm fields, extensions, immutable audit event model và migration0037.
- [x] Central pure policy, SQL progress roots và historical acceptance.
- [x] Tích hợp transactional starts, schedule edits, extensions và immediate notifications.
- [x] Bounded student progress, teacher monitoring/calendar và reminder CLI.
- [x] Tích hợp focused frontend schedule editor/progress/monitor/extensions/calendar xuyên P1.
- [x] Focused unit/PostgreSQL/concurrency/component tests; migration test và local upgrade.
- [x] Documentation, source review và scoped delivery preparation. Commit/push results được báo từ Git sau thực thi.

## Hướng thiết kế

Giữ P1 editorial tokens và classroom identity. Actual assignment deadlines/root attempt usage là nội dung chính. Assignment schedule editor dùng native datetime-local controls, nêu rõ browser timezone và serialize UTC; monitoring dùng bảng hẹp có filter, giữ mobile overflow cục bộ. Calendar là accessible agenda, không thêm dependency.

## Kiểm chứng

Origin/main và local HEAD ban đầu cùng fb529c9. Tạo PostgreSQL database cách ly mới; upgrade, empty downgrade/re-upgrade thành công.145focused backend cases và65frontend cases pass; TypeScript/ESLint/Ruff sạch. CLI smoke trả empty batch report thành công. Local database đã upgrade, xác nhận head20261027_0037. Không browser/E2E/build/full suite hoặc always-running scheduler.
