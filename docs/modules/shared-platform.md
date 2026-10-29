# Shared platform: shell, localization, notifications và probes

> Mục đích và phạm vi: Các hạ tầng dùng chung của UI/API mà không chứa luật thi hoặc quyền cấp từ frontend.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## A–C. Mục đích, workflow và ownership

Các hạ tầng dùng chung của UI/API mà không chứa luật thi hoặc quyền cấp từ frontend.

Root layout cung cấp locale/personalization/auth và AppShell. Header/footer dùng chung trừ exam/preview exclusions. Homepage enhancement có scene/controls qua provider; static content vẫn hữu ích khi WebGL unavailable. Notification bell fetch count khi đóng, list khi mở; read actions explicit.

Design-system tokens sở hữu shared surfaces/type; gravity-home styles scope homepage, globals giữ reset/exam defaults, gravity-product xử lý product components. Typed API client giữ errors/refresh; backend notifications sở hữu recipient/read state. Health/readiness không phải UI state.

## D. Implementation map

| Lớp | Source |
| --- | --- |
| UI/pages | [frontend/src/app/layout.tsx](../../frontend/src/app/layout.tsx); [frontend/src/components/ui/app-shell.tsx](../../frontend/src/components/ui/app-shell.tsx); [frontend/src/components/ui/app-footer.tsx](../../frontend/src/components/ui/app-footer.tsx); [frontend/src/components/home/gravity/](../../frontend/src/components/home/gravity/); [frontend/src/features/notifications/notification-center.tsx](../../frontend/src/features/notifications/notification-center.tsx) |
| Clients/locale | [frontend/src/lib/api/client.ts](../../frontend/src/lib/api/client.ts); [frontend/src/lib/api/server-client.ts](../../frontend/src/lib/api/server-client.ts); [frontend/src/lib/api/notifications.ts](../../frontend/src/lib/api/notifications.ts); [frontend/src/lib/i18n/](../../frontend/src/lib/i18n/) |
| Backend | [backend/app/api/v1/notifications.py](../../backend/app/api/v1/notifications.py); [backend/app/services/notifications.py](../../backend/app/services/notifications.py); [backend/app/repositories/notifications.py](../../backend/app/repositories/notifications.py); [backend/app/models/notifications.py](../../backend/app/models/notifications.py); [backend/app/api/v1/health.py](../../backend/app/api/v1/health.py); [backend/app/core/exceptions.py](../../backend/app/core/exceptions.py); [backend/app/core/request_timing.py](../../backend/app/core/request_timing.py) |
| Styles/tests | [frontend/src/app/design-system.css](../../frontend/src/app/design-system.css); [frontend/src/app/gravity-home.css](../../frontend/src/app/gravity-home.css); [frontend/tests/app-shell.test.tsx](../../frontend/tests/app-shell.test.tsx); [frontend/tests/gravity-field.test.tsx](../../frontend/tests/gravity-field.test.tsx); [frontend/tests/notification-center.test.tsx](../../frontend/tests/notification-center.test.tsx); [frontend/tests/localization-matrix.test.tsx](../../frontend/tests/localization-matrix.test.tsx) |

## E–F. Data flow và API contracts

RootLayout → locale/personalization/AuthProvider → AppShell. Domain transaction → Notification → unread-count → bell; open → paginated list. Homepage GravityMotionProvider connects footer controls to original scene, ticker có state riêng.

Các đường dẫn sau dùng prefix `/api/v1`; DTO, dependency và response model ở router được dẫn trong bảng. [Source map](../handbook/source-map.md) liệt kê toàn bộ route cùng khai báo gốc.

- `GET /notifications`
- `GET /notifications/unread-count`
- `POST /notifications/read-all`
- `POST /notifications/{notification_id}/read`
- `GET /health`
- `GET /ready`

## G. Persistence

Notification recipient/type/entity/payload/read_at ở PostgreSQL; domain event creation cùng transaction và dedup. UserPreference giữ locale/theme/accent. Motion/ticker state là UI-only, không cần database. Diagnostics timing không lưu student body.

## H. Business rules

Không dịch nội dung authored exam bằng system translation. Preserve display font/logo và theme hydration. Sphere controls chỉ homepage, ticker pause độc lập scene pause. Reduced motion/Save-Data/offscreen không được recreate WebGL chỉ vì footer click. Exam layout bypass global shell đúng path; preview không thêm footer.

## I. Security

Notification target vẫn cần backend authorization; unseen/read không cấp quyền. API errors giữ code/status để caller phân biệt denial với lỗi mạng. CSS state/hidden button không enforce role.

## J. Failure và recovery

UI stale request version bảo vệ recipient change. Scene failed/unavailable có fallback, dispose khi unmount. Health chỉ process liveness; ready kiểm DB timeout, không ngụ ý asset/model ready. Timing logging optional, disabled mặc định.

## K. Focused testing

App shell/footer/localization/hydration contracts, motion provider + scene cleanup, notification closed-panel list count=0 và unread behavior. Focus/keyboard/reduced-motion checks; rendering thật trên thiết bị không được khẳng định từ jsdom.

## L. Extension guide

Thêm system string phải cập nhật en/vi và types/tests; shared component dùng tokens thay root override rải rác. Thêm notification type cập nhật enum/schema/transaction dedup/payload → translated text/link → recipient tests. Không fetch full list chỉ để badge.

## M. Giới hạn

Notifications hiện in-app, không hệ thống email/push tổng quát. Homepage decoration không có scientific physics claim. HTTP benchmark không đo user-perceived layout/rendering hay Core Web Vitals.

## N. Câu hỏi phỏng vấn

**1. Vì sao list chỉ khi mở?** Badge chỉ cần unread count; bỏ request dư nhưng vẫn giữ read/load-more semantics.

**2. Readiness khác liveness?** Process sống chưa chắc DB phản hồi; ready thêm kiểm dependency đã định nghĩa.

**3. Tại sao i18n không translate đề?** System UI locale không được sửa authored exam content/answer semantics.

## Tài liệu liên quan

[Architecture styling boundaries](../architecture.md), [performance case study](../case-studies/modal-web-performance.md), [Identity](identity.md).
