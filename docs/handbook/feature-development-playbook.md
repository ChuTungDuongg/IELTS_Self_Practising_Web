# Feature development playbook cho Codex

> Mục đích và phạm vi: Xác định chính xác nơi thay đổi và tác động mà không xây lại hệ thống.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## Bắt đầu một feature

1. Đọc [AGENTS](../../AGENTS.md), [frontend instructions](../../frontend/AGENTS.md) khi chạm UI; generated block của Next phải giữ nguyên.
2. Kiểm `git status`, HEAD và user constraints. Đừng stage thay đổi có sẵn không thuộc task.
3. Đọc [architecture boundaries](../architecture.md) và [module catalog](module-catalog.md), chọn module owner.
4. Mở route → typed client → router → service → repository/model/schema thực tế. [Source map](source-map.md) là mục lục, không thay đọc implementation.
5. Xác định data contract, actor/capability, frozen version, scope và provenance bị ảnh hưởng.
6. Xem style ownership/i18n nếu UI; schema/migration nếu persistence; provider config nếu AI; storage inventory nếu bytes.
7. Viết một change-impact note nhỏ: input, invariant, failure, migration/cancellation, tests và docs cần sửa.
8. Làm thay đổi nhỏ nhưng trọn workflow; không tạo parallel auth/scoring/attempt system.
9. Test đúng failure/security/race. Typecheck/lint không thay integration tests; xem [testing guide](testing-and-delivery.md).
10. Cập nhật canonical docs và verification revision; đánh dấu limitation chưa chạy. Inspect diff, secrets/assets, unrelated changes trước commit.
11. Fetch/reconcile/push theo authorization của task. Deployment, migrations vào database thật và paid inference là thao tác riêng, không tự suy từ “push”.

Kế hoạch cũ trong superpowers là reference, không lệnh tự động chạy lại. Riêng Speaking spec/plan/self-review vẫn binding theo AGENTS. Không dùng checklist hoàn thành cũ để khẳng định behavior hiện tại.

## A. Thêm Reading question type

**Ví dụ thiết kế, chưa implement:** thêm subtype objective mới vào [Python registry](../../backend/app/domains/questions/registry.py): config/response/key schemas, normalize/evaluate. Xem [normalization](../../backend/app/domains/questions/normalization.py) và [numbering](../../backend/app/domains/questions/numbering.py) để giữ UUID/gap identity. Nếu cần layout phức tạp, schema JSONB có validation, không opaque HTML.

Ở frontend sửa [types](../../frontend/src/features/questions/types.ts), [registry](../../frontend/src/features/questions/registry.tsx), editor/key editor và exam/review renderer. Reuse single/multiple/text/matching primitives nếu phù hợp. Kiểm [API schema](../../frontend/src/lib/api/schema.ts), [content schemas](../../backend/app/schemas/content.py), clone và [transfer ID mapping](../../backend/app/services/transfer_ids.py). Không cần migration chỉ vì thêm renderer; chỉ khi persisted constraint/schema thay đổi.

Test malformed config, missing key, reorder ID, export/import roundtrip, active DTO không lộ key, correct/wrong answers và historical review. Bắt đầu [question-registry UI test](../../frontend/tests/question-registry.test.tsx), [completion identity](../../backend/tests/test_completion_identity.py), [draft answer keys](../../backend/tests/test_draft_answer_keys.py). Update [authoring](../modules/authoring.md) và transfer format nếu đổi compatibility.

## B. Thêm analytics metric

Định nghĩa trước: “độ chính xác gần đây” dùng attempts nào, date theo finish hay start, null ra sao, focused có được tính, human final/AI nguồn nào. Personal query bắt đầu [AnalyticsService](../../backend/app/services/analytics.py); classroom dùng [learning repository](../../backend/app/repositories/classroom_learning.py) và reuse [selected grades](../../backend/app/repositories/classroom_grades.py).

Mở [analytics schema](../../backend/app/schemas/analytics.py) → [typed client](../../frontend/src/lib/api/analytics.ts) → [analytics components](../../frontend/src/features/analytics/). Chỉ aggregate từ nguồn đã authorized. Test cohort khác người, half-open timezone date, no-data, focused, legacy mock, pending human score và query-count/scope nếu query thêm. Update [metric definitions](../analytics-dashboard.md); không chép định nghĩa lệch vào chart tooltip riêng.

## C. Thêm asset-backed feature

Chọn entity owner trước: TestCover thuộc Test; ảnh task thuộc version; learner recording thuộc Attempt. Mở [factory](../../backend/app/storage/factory.py), [base interface](../../backend/app/storage/base.py), [delivery](../../backend/app/storage/delivery.py), [asset access](../../backend/app/services/asset_access.py). Bytes không vào PostgreSQL, URL public không thay policy.

Thiết kế MIME/size/signature, bounded upload, key format, private range/download và no-store. Metadata attach transaction phải có compensation; bổ sung reference query trong [asset_cleanup](../../backend/app/services/asset_cleanup.py) và [operations inventory](../../backend/app/storage/operations.py) nếu có key field mới. Cập nhật clone/Transfer/backup/recovery nếu feature cần portability. Test Local và fake S3, lost commit acknowledgement, cancellation, unauthorized ranges. Update [storage architecture](../storage-architecture.md).

## D. Thêm AI capability

Đọc [provider boundary](../../backend/app/providers/writing_llm/base.py) và [Writing worker](../../backend/app/services/writing_ai_worker.py) hoặc Speaking worker theo domain. Xác định input tối thiểu, dữ liệu private gửi provider, configuration names, timeout/token/concurrency budget, valid output schema, version/cache identity, advisory status.

Tạo durable run/event checkpoint nếu task cần sống lâu hơn HTTP; đừng giữ SQL transaction khi chờ GPU. Định nghĩa retry bounded, cancel, stale lease và provider-unavailable UI. Xem [writing execution](../../backend/app/services/writing_execution.py), [Speaking AI worker](../../backend/app/services/speaking_ai_worker.py). Fakes kiểm contract; private labelled benchmark kiểm model quality riêng sau authorization. Human final không bị AI overwrite. Update [AI overview](ai-architecture.md) và canonical pipeline guide, không claim “implemented” trước khi nối đủ flow.

## E. Thêm classroom feature

Bắt đầu [capabilities](../../backend/app/services/classroom_capabilities.py), không `role == TEACHER` ở component rồi bỏ backend. Quyết định OWNER/CO_TEACHER/TA flag/student/ADMIN observer ai đọc/ghi; archived room và former member xử lý thế nào. Reuse [content service](../../backend/app/services/classroom_classwork.py) hoặc [assignment service](../../backend/app/services/classroom_assignments.py) tùy owner.

Nếu reorder/content dùng content_revision và room locks; nếu assignment activity giữ frozen version/provenance. Notification event cùng transaction, recipient-scope và dedup trong [notifications](../../backend/app/services/notifications.py). Sửa schema → [classroom client](../../frontend/src/lib/api/classroom-content.ts) → component. Tests gồm outsider, hidden section, archived room, stale revision, ADMIN denial và private personal attempt. Update classroom guide đúng concern, không fork Gradebook logic.

## Change impact matrix

| Change | Owner / likely files | DB implications | Security | Required test focus | Docs |
| --- | --- | --- | --- | --- | --- |
| Question type | Python/TS registry + renderers | JSON compatibility, migration nếu constraint đổi | Active keys/confidentiality | Editor→evaluator→review, transfer | Authoring/format |
| Attempt/timer | attempts, state_machine, timers, exam queue | Transitions/locks/revisions | Owner/deadline/provenance | Concurrent save-submit, mock lock order | Attempts |
| Profile/auth | auth service/schema + clients | User/RefreshSession migration nếu đổi model | Rotation, active account, safe redirect | Cross-tab/recovery/role | Identity |
| Metric | analytics service/repository/schema | Query/index chỉ khi có evidence | User/class scope, score source | Dates/null/focused/query counts | Analytics definitions |
| Asset | storage + domain service + inventory | Key metadata + compensation | Private read, MIME/path/range | Cross-provider/cancel/restore | Storage/transfer |
| AI stage | provider + worker + schemas | Run identity/events/checkpoint | Private input, advisory final boundary | Output failure, stale worker, reconnect | AI module |
| Classroom | capability + room/assignment services | FKs/revision/policy history | ADMIN observer/staff/provenance | Permission matrix, schedule/retention | Classroom contracts |
| Shell/i18n | app-shell/tokens/translations | Preference only nếu contract đổi | Không dùng UI guard thay backend | Locale/theme/exam exclusions | Shared platform |
| Deployment | runtime validation/config | DB owner/migrations/Volume topology | Env/Secret isolation | Offline config + authorized staging | Operations runbook |

## Giới hạn và definition of done

Ví dụ trên không implement feature và không cho phép deployment. Nếu source và doc mâu thuẫn, kiểm current code/tests, ghi discrepancy; AGENTS invariants vẫn phải giữ. Một feature “xong” cần workflow end-to-end ở phạm vi task, focused evidence, migration/rollback nếu có, và docs canonical cập nhật — không chỉ có endpoint hoặc UI mock.
