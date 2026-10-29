# Module catalog và ownership map

> Mục đích và phạm vi: Điểm bắt đầu để xác định domain chịu trách nhiệm và tài liệu tương ứng.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

Chọn module theo **state và policy nó sở hữu**, không theo URL gần giống. Bảng map cả frontend/backend; source map liệt kê toàn bộ route/model/page ở revision được kiểm tra. Những services nhỏ được nhóm dưới domain liên quan để tránh hàng chục trang trùng lặp.

| Module | Canonical guide | Scope sở hữu / integration |
| --- | --- | --- |
| Identity, accounts, profile và preferences | [identity](../modules/identity.md) | Auth local/OAuth, refresh/restore/logout, profile/goals/preferences |
| Test Builder, question registry và content governance | [authoring](../modules/authoring.md) | Draft/publish/moderation, content graph, question/key registry, covers |
| Reading và Listening: objective question engine | [reading-listening](../modules/reading-listening.md) | Reading passage/highlights, Listening player/ranges, objective evaluation |
| Attempts, Full Mock, timers và history | [attempts](../modules/attempts.md) | Autosave, deadline/pause, focused scope, Full Mock, review/history |
| Writing: authored tasks, human grading và advisory AI | [writing](../modules/writing.md) | Task1/Task2, human final, advisory snapshots, annotations, benchmark bank |
| Speaking: recording, processing, scoring và recovery | [speaking](../modules/speaking.md) | Prompts/recording/recovery, media, ASR/evidence, advisory/human scoring |
| Classrooms, staff, assignments, content và gradebook | [classrooms](../modules/classrooms.md) | Membership/staff, feed/classwork, schedule/targets/extensions, gradebook, archive/delete |
| Analytics, learning goals và improvement plans | [analytics](../modules/analytics.md) | Personal metrics, classroom evidence/recommendations/goals/plans |
| Administration, moderation và benchmark bank | [administration](../modules/administration.md) | Users/directory, moderation, admin benchmark operations, observer boundary |
| Asset storage, transfer, migration và recovery | [assets-transfer](../modules/assets-transfer.md) | Local/S3/R2, private ranges, transfer/draft import, migration/backup/restore |
| Shared platform: shell, localization, notifications và probes | [shared-platform](../modules/shared-platform.md) | Shell/i18n/themes, homepage motion, notifications, errors, health/timings |

## Shared ownership rules

- API/domain mutations đi FastAPI. Bổ sung UI không tạo nguồn authority mới.
- Classroom assignments gọi existing attempt/session engine. Gradebook/learning analytics reuse selected roots/human final, không fork scoring.
- Storage provider factory dùng chung cả content, covers, speech, classroom resources và benchmark images; metadata owner vẫn thuộc domain.
- AI provider/worker không sở hữu authentication, final objective grading hay human final records.
- Notification service ghi recipient events do domain phát sinh; không cấp quyền cho link đích.

## Tình trạng implementation

Các module trong bảng có code, route và test files hiện hữu. AI/OAuth/cloud/reminders tùy cấu hình; không phải tất cả đang bật ở một deployment. RAG/pgvector, payments, email delivery/realtime presence không được xác nhận là capabilities hiện hành. Legacy AI scorers dưới evaluation là experimental/historical benchmark candidates, không default runtime.

[Coverage matrix](../DOCUMENTATION_COVERAGE.md) ghi Partial/Not verified chứ không báo 100%. [Playbook](feature-development-playbook.md) hướng dẫn thay đổi, [source map](source-map.md) tra cứu endpoint chính xác.
