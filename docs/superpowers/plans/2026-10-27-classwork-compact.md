# Triển khai Classwork dạng gọn

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: Compact Classwork implementation. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Phạm vi: triển khai Classwork redesign được cung cấp trên main. Giữ BandPilot tokens, FastAPI APIs, capabilities, P2 progress, resource readers, revision conflicts và assignment detail/history navigation. Không đổi backend/schema.

Màn hình giúp người học quyết định nên mở topic và learning activity nào tiếp theo. Real topic titles cùng compact resource/IELTS rows thể hiện hierarchy. Giữ achromatic-ledger composition hiện có; thay component này không cần chọn hướng thiết kế hay global theme mới.

1. Thêm focused regression tests cho grouping/counts, disclosure state, progress metadata, historical navigation, permissions và revision-aware moves. Xác minh structural regressions fail trước.
2. Normalize resolved content một lần: deduplicate canonical assignments, giữ unplaced records, tách archived assignments/resources và không đếm inaccessible references. Không tạo database topics.
3. Thay nested material disclosures bằng một controlled topic button/region. Ban đầu chỉ mở populated published topic đầu tiên; giữ lựa chọn user qua refresh. Expand/focus hash targets một lần cho mỗi navigation.
4. Thay ProgressSummary nhúng bằng ClassworkAssignmentMeta dùng existing progress context. Tối đa ba metadata parts, effective due date, finite attempt counts hữu ích; không bịa scores. Giữ full detail surface.
5. Giữ contextual authoring, resource readers, drop targets và keyboard Move/reorder alternatives. Dùng shrinkable rows, wrapping titles, shared theme tokens và visible focus tại source breakpoints375/768/1024/1440.
6. Chạy targeted Vitest files, TypeScript, scoped ESLint, Taste source lint và git diff --check; inspect task diff, cập nhật classroom docs, commit/push main không force. Tiếp tục CI monitoring cho SHA vừa tạo.

Hướng dẫn skills: Taste app-screen lists, một quiet boundary và compact identity/subline/action rows; UI/UX Pro Max có local matches đã kiểm cho visible/unobscured focus, dragging alternatives và stable React keys. Local progressive-disclosure search cùng narrower retry không trả guideline phù hợp đã xác minh; dùng supplied two-level design và native button/region semantics. Giữ actual counts/API status, không bịa fixture content trong production.

Giới hạn verification: loại trừ browser inspection, viewport screenshots, builds, local E2E, full suites và full-stack launches. Responsive/theme findings chỉ ở cấp source; không tự chấm visual screenshot score.

## Yêu cầu mở rộng đã tích hợp

Chỉ dẫn tiếp theo gồm bốn yêu cầu mở rộng frontend-only scope: safe content removal, canonical Resource Stream activity, frozen teacher-selected assignment targets và ẩn technical revision numbers trong giao diện thông thường. Đã triển khai bằng hai Alembic migrations0040/0041, classroom-scoped DELETE/target-metadata APIs, native lifecycle enforcement, compact contextual UI và focused regressions. Actual local database đã migrate; downgrade verification chỉ dùng disposable empty database. Policies/verification chi tiết nằm trong `docs/classroom-workspace.md`. Giữ local skills/design files không liên quan ở trạng thái untracked. Commit Classroom integration, revision presentation và concurrency-fixture isolation riêng, push main không force. Sau đó user hủy CI monitoring; để automation đó paused sau push.
