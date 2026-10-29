# Analytics, learning goals và improvement plans

> Mục đích và phạm vi: Chuyển persisted results thành thống kê có scope rõ, không tạo điểm hay forecast mới.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## A–C. Mục đích, workflow và ownership

Chuyển persisted results thành thống kê có scope rõ, không tạo điểm hay forecast mới.

Personal analytics chọn skill/date, xem trend/accuracy/time và compare attempts. Classroom staff xem cohort/skill/weakness, học sinh xem own progress/recommendations; authorized staff tạo learning plan tham chiếu assignment/resource có sẵn.

AnalyticsService owns personal cohort/metrics; ClassroomLearningRepository owns P4 aggregate SQL, ClassroomLearningService resolves deterministic evidence; LearningPlanService owns normalized activity references. Gradebook selection/provenance là dependency chung.

## D. Implementation map

| Lớp | Source |
| --- | --- |
| Pages/UI/clients | [frontend/src/app/analytics/page.tsx](../../frontend/src/app/analytics/page.tsx); [frontend/src/features/analytics/](../../frontend/src/features/analytics/); [frontend/src/lib/api/analytics.ts](../../frontend/src/lib/api/analytics.ts); [frontend/src/lib/api/classroom-learning.ts](../../frontend/src/lib/api/classroom-learning.ts) |
| Router/schemas | [backend/app/api/v1/analytics.py](../../backend/app/api/v1/analytics.py); [backend/app/api/v1/classroom_learning.py](../../backend/app/api/v1/classroom_learning.py); [backend/app/schemas/analytics.py](../../backend/app/schemas/analytics.py); [backend/app/schemas/classroom_learning.py](../../backend/app/schemas/classroom_learning.py) |
| Services/repositories | [backend/app/services/analytics.py](../../backend/app/services/analytics.py); [backend/app/services/classroom_learning.py](../../backend/app/services/classroom_learning.py); [backend/app/services/classroom_learning_plans.py](../../backend/app/services/classroom_learning_plans.py); [backend/app/services/learning_goals.py](../../backend/app/services/learning_goals.py); [backend/app/repositories/classroom_learning.py](../../backend/app/repositories/classroom_learning.py); [backend/app/repositories/classroom_grades.py](../../backend/app/repositories/classroom_grades.py) |
| Models/tests | [backend/app/models/classroom_learning.py](../../backend/app/models/classroom_learning.py); [backend/app/models/entities.py](../../backend/app/models/entities.py); [backend/tests/test_analytics_date_scope.py](../../backend/tests/test_analytics_date_scope.py); [backend/tests/test_classroom_learning.py](../../backend/tests/test_classroom_learning.py); [frontend/tests/analytics-scope.test.ts](../../frontend/tests/analytics-scope.test.ts); [frontend/tests/classroom-learning-ui.test.tsx](../../frontend/tests/classroom-learning-ui.test.tsx) |

## E–F. Data flow và API contracts

Persisted attempt roots → authorized cohort/query → validated metrics DTO → client SVG/chart. Learning plan → existing assignment/resource references; không tạo independent attempt hoặc score lifecycle.

Các đường dẫn sau dùng prefix `/api/v1`; DTO, dependency và response model ở router được dẫn trong bảng. [Source map](../handbook/source-map.md) liệt kê toàn bộ route cùng khai báo gốc.

- `GET /analytics`
- `GET /analytics/compare`
- `GET /classrooms/{classroom_id}/analytics`
- `GET /classrooms/{classroom_id}/students/{student_id}/analytics`
- `GET /classrooms/{classroom_id}/my-progress`
- `GET /classrooms/{classroom_id}/my-recommendations`
- `POST /classrooms/{classroom_id}/students/{student_id}/learning-plans`

## G. Persistence

Đọc Attempt/Answer/events/human scores và selected assignment roots; plan/item là bảng riêng có FK đến activities. Skill goals nằm trên User; explicit overall target có thể override fallback computed target trong learning-goal presentation.

## H. Business rules

Personal dates dùng timezone-aware UTC half-open interval từ calendar UTC+7; recorded duration là tổng active time của cohort, không số giây nằm trong window. Classroom selection trước date filter; completion cohort khác performance sample. Null denominator → null percentage, missing human grades không thành zero. Focused evidence không thành full band.

## I. Security

Personal API luôn user-scoped; classroom analytics cần analytics.view hoặc own-progress path. Student drill-down chỉ assignment-origin work. Recommendation/plan API rechecks membership/capability; không dùng dashboard data để suy quyền ghi.

## J. Failure và recovery

Validate naive/reversed/out-of-bound dates; empty datasets hiển thị no-data. Không interpolate fabricated scores giữa observations. Stable pagination/bounded exports tránh query cả hệ thống; đổi grade selection có thể đổi sample và cần caption rõ.

## K. Focused testing

Query scope/date validation/date scope, accepted-root gradebook, learning-plan access và frontend scope/chart tests. Khi thêm metric phải thử missing human score, focused scope, legacy mock và membership removal.

## L. Extension guide

Bắt đầu định nghĩa numerator/denominator/cohort/time/provenance. Query backend → response schema → typed client → chart; reuse selected_grades cho lớp. Nếu cần persisted metric mới, chứng minh aggregate query chưa đủ rồi mới đề xuất migration.

## M. Giới hạn

Recommendations deterministic thresholds, không embeddings/RAG hay dự báo band. Trends không suy nhân quả hoặc cam kết tăng điểm. Không đo query performance mới trong documentation audit.

## N. Câu hỏi phỏng vấn

**1. Vì sao null khác zero?** Null là chưa có bằng chứng/grade, zero là kết quả đo; trộn làm sai average và weak-area rules.

**2. Date filter có đủ mô tả metric?** Chưa: cần biết filter theo finish/start và grade selection trước hay sau date.

**3. Recommendation có phải AI?** Ở P4 là luật từ evidence/targets, không model được huấn luyện.

## Tài liệu liên quan

[Personal metrics](../analytics-dashboard.md), [Classroom metric definitions](../classroom-learning-analytics.md), [data architecture](../handbook/data-architecture.md).
