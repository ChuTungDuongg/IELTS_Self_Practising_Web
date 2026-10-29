# BandPilot Engineering Knowledge Base

> Mục đích: tài liệu học hệ thống và bản đồ triển khai feature cho chủ dự án/Codex. Source revision được audit: `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Phạm vi là mã nguồn đã commit; không xác nhận trạng thái cloud/database đang chạy.

## Learning Path A — Understand BandPilot

1. [System overview](handbook/system-overview.md): sản phẩm, roles, capabilities và giới hạn.
2. [Architecture boundaries](architecture.md) → [runtime diagrams](handbook/runtime-architecture.md): process và network.
3. [Module catalog](handbook/module-catalog.md): chọn module, đọc code map.
4. [Data architecture](handbook/data-architecture.md): ER, JSONB, transactions, storage consistency.
5. [Attempt lifecycle](modules/attempts.md) → [Classroom workflows](modules/classrooms.md): request/state/events.
6. [AI architecture](handbook/ai-architecture.md) → [Writing](ai-writing.md) / [Speaking](ai-speaking.md).
7. [Infrastructure](handbook/infrastructure.md) → [Modal operations](modal-web.md) / [AWS profiles](aws-deployment.md).
8. [Security and reliability](handbook/security-and-reliability.md).
9. [Testing and delivery](handbook/testing-and-delivery.md).
10. [Modal performance case study](case-studies/modal-web-performance.md), [Writing latency experiment](enhance_latency.md).
11. [Engineering decisions](handbook/engineering-decisions.md).
12. [System-design interview guide: 44 questions](interview/bandpilot-system-design.md), [Modal deep-dive Q&A](interview/modal-performance-qa.md).

## Learning Path B — Develop BandPilot

1. [Root AGENTS](../AGENTS.md) và [frontend generated instructions](../frontend/AGENTS.md).
2. [Architecture boundaries](architecture.md), rồi [module owner](handbook/module-catalog.md).
3. Relevant module guide → router/schema/model/typed client trong [source map](handbook/source-map.md).
4. [Data boundaries](handbook/data-architecture.md) và [capabilities/security](handbook/security-and-reliability.md).
5. [Feature playbook + change-impact matrix](handbook/feature-development-playbook.md).
6. [Focused testing](handbook/testing-and-delivery.md), rồi canonical runbook nếu task có deployment scope.

Không cần đọc tất cả historical plans. Speaking vẫn phải đọc [binding design](superpowers/specs/2026-10-11-speaking-engine-ai-grading-design.md), [plan](superpowers/plans/2026-10-11-speaking-engine-ai-grading.md) và [self-review amendments](superpowers/plans/2026-10-11-speaking-engine-ai-grading-self-review.md) theo AGENTS.

## Canonical concern index

| Concern | Canonical explanation | Liên quan |
| --- | --- | --- |
| Architecture ownership | [architecture](architecture.md) | handbook giải thích/diagram, không thay invariants |
| Domain implementation | [module catalog](handbook/module-catalog.md) | [API/model/page index](handbook/source-map.md) |
| Writing AI | [ai-writing](ai-writing.md) | [benchmark bank](writing-benchmark-bank.md) |
| Speaking AI/runtime | [ai-speaking](ai-speaking.md) | [recording](speaking-recording.md), [transcription](speaking-transcription.md), [grading](speaking-grading.md) |
| Storage | [architecture](storage-architecture.md) | [migration](storage-migration.md), [backup](storage-backup-restore.md) |
| Transfer / draft import | [ZIP contract](TEST_TRANSFER_FORMAT.md) | [draft JSON contract](draft-import-format.md) |
| Classroom policies | [module guide](modules/classrooms.md) | [scheduling](classroom-assignment-scheduling.md), [Gradebook](classroom-gradebook.md), [learning](classroom-learning-analytics.md), [archive/delete](classroom-archive-calendar.md) |
| Deployment | [Modal](modal-web.md), [AWS](aws-deployment.md) | [topology overview](handbook/infrastructure.md) |
| Measured Modal performance | [original report](modal-web-performance.md) | [educational case study](case-studies/modal-web-performance.md) |

## Historical evidence và độ mới

[DOCS_AUDIT](DOCS_AUDIT.md) phân loại mọi tài liệu tracked ở baseline. [Superpowers index](superpowers/README.md) chỉ rõ kế hoạch/spec lịch sử và ngoại lệ Speaking còn binding. [DOCUMENTATION_COVERAGE](DOCUMENTATION_COVERAGE.md) ghi scope/known gaps. Không xóa benchmark JSON, đổi số liệu hay biến phase report thành current contract.

Khi đổi route/schema/entity/invariant/provider/deployment, cập nhật canonical concern cùng commit; module guide chỉ giữ summary và đường dẫn, không copy prompt hoặc runbook dài. Ghi source commit thực sự đã đối chiếu và giới hạn verification, không “last updated” giả định. Với historical report, thêm correction/status riêng, không sửa measurement cũ. Nếu hai docs mâu thuẫn, kiểm code/tests rồi sửa source-of-truth và link từ nơi khác.

Source paths, local links, API declarations, model names, math và diagram structure được kiểm offline; không có browser/deployment/test suite trong audit này. Tài liệu không chứng minh runtime capabilities đều enabled. Hướng dẫn operations có thể chứa lệnh có side effect: chỉ chạy trong scope được user/operator cho phép, với database/Secret/Volumes đã xác nhận.
