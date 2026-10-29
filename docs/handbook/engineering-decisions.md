# Engineering decisions và trade-offs

> Mục đích và phạm vi: Giải thích lựa chọn hiện hành; tách quyết định đã ghi với rationale suy luận.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

**Recorded** là quy tắc được ghi trong AGENTS/spec/runbook; **Interpretation** là cách giải thích hợp lý từ code, không khẳng định tác giả từng họp/chọn tất cả alternatives dưới đây. Alternatives là phương án để so sánh hôm nay. Mỗi dòng liên kết bằng chứng, không phải một ADR lịch sử mới được bịa.

| Concern và context/problem | Selected design + evidence | Alternatives | Benefits | Trade-offs | Khi nào xem lại | Loại |
| --- | --- | --- | --- | --- | --- | --- |
| Domain thi, lớp, scoring chia sẻ transactions | Modular monolith trong [architecture](../architecture.md) | Domain microservices | Chung model/policy, ít distributed consistency | Deploy/failure coupling | Ownership/team/scale thực sự cần độc lập và có telemetry | Recorded boundary; rationale Interpretation |
| UI tương tác khác domain authority | Next typed clients → FastAPI [router](../../backend/app/api/v1/router.py) | Next-only backend, SPA độc lập | Server enforce invariants; UI reuse contracts | Hai runtime và DTO sync | Có evidence chi phí integration lớn hơn lợi ích | Recorded |
| Ownership/version/attempt cần FK/transactions | PostgreSQL [models](../../backend/app/models/entities.py) | Document DB, embedded file DB | Constraints/joins/locks | Migration/pool/operations | Workload mới có access pattern khác và migration plan | Recorded authority; alternatives Interpretation |
| Layout question đa hình | JSONB validated + normalized identity [registry](../../backend/app/domains/questions/registry.py) | Một table mỗi subtype; opaque blob toàn bộ test | Linh hoạt schema trong một registry | Validation/migration JSON phức tạp | Query/update subtype cần indexing/constraints riêng | Interpretation |
| Historical grading cần đề/key ổn định | Frozen published content + new draft [AccessPolicy](../../backend/app/services/access_policy.py) | Edit in-place | Reproducible review/history | Clone/storage/version lifecycle | Không bỏ invariant; thêm explicit compatible version migration | Recorded |
| Client không đáng tin cho thời gian/điểm | Server timer/evaluator [AttemptService](../../backend/app/services/attempts.py) | Client clock/score | Enforce deadline, không lộ key | API availability cần thiết | Offline mode mới phải có threat model riêng | Recorded |
| Nhiều objective types cần cùng behavior | Backend/frontend registries [module](../modules/authoring.md) | Per-page conditionals | Tìm extension points, coverage rõ | Đăng ký hai stack phải đồng bộ | Contract generation nếu drift có evidence | Recorded |
| Binary lớn và private media | Metadata DB + storage adapter [storage](../storage-architecture.md) | Bytea blobs, public URLs | Streaming/provider portability | Cross-store compensation | Nhu cầu khác phải giữ authorized delivery/backup inventory | Recorded |
| Demo cần ít service vận hành | Embedded PG + guarded single Web [runtime](runtime-architecture.md) | Managed DB ngay từ đầu | Deployment demo gọn | Single owner, Volume durability, shared CPU | Multi-replica/HA hoặc production retention | Recorded topology; cost rationale Interpretation |
| Cloud portability và ownership ngoài container | External PostgreSQL + S3/R2 [AWS profiles](../aws-deployment.md) | Local files trong nhiều replicas | Stable shared storage | IAM/TLS/cost, live validation | Sau staged DR/permission tests và capacity evidence | Recorded optional mode |
| HTTP input queue trong staging | Modal max_inputs=8, max_containers=1 [case study](../case-studies/modal-web-performance.md) | 16 inputs; more replicas; more CPU | Giảm concurrent p95 đã đo | Contention khi CPU-bound; không giảm RTT | Rebenchmark workload/headroom, external DB trước replica | Recorded measured decision |
| LLM provider/compute biến đổi | Factory vLLM hoặc OpenAI [providers](../../backend/app/providers/writing_llm/__init__.py) | Hardcode vendor vào service | Transport tách scoring | Compatibility/output validation | Đổi provider có eval và cache identity version | Recorded implementation; rationale Interpretation |
| Inference chậm, observer có thể đóng tab | Detached worker + DB checkpoints [AI guide](ai-architecture.md) | Synchronous request; dedicated queue broker | Reconnect giữ progress | Process-local execution cần leases/recovery | Throughput/HA yêu cầu worker fleet và durable dispatch | Recorded |
| Model cần nguồn nhất quán | Whole essay/source IDs và whole-attempt Speaking evidence [Writing](../ai-writing.md), [Speaking](../ai-speaking.md) | Retrieval/chunking độc lập | Exact grounding/context và criterion scope | Input/context budgets, latency | Inputs vượt giới hạn phải eval cách chia, không âm thầm bỏ nội dung | Recorded flows; không claim full-passage RAG |
| Web host và AI GPU khác tài nguyên | Modal CPU Web, GPU inference riêng; EC2 template [infra](infrastructure.md) | Một GPU host tất cả | Scale/cost profiles khác nhau | Nhiều provider lifecycle/ops | So sánh traffic/cost/latency thật, không định kiến vendor | Recorded topology; rationale Interpretation |

## Cách trả lời trade-off

Bắt đầu từ invariant rồi workload, không từ buzzword. Ví dụ “tại sao không Redis?”: hiện authority nằm PostgreSQL, các query/retries đã bounded theo module; repository không triển khai Redis. Redis có thể giúp một nhu cầu cụ thể trong tương lai nhưng cần invalidate, privacy và failure semantics. Không thêm cache chỉ để có tên công nghệ.

“Tại sao không chia service?”: nếu chỉ có một bottleneck admission trước Nginx, chia domain service không xử lý nguyên nhân; P2 thay concurrency giữ nguyên CPU/replica đã có benchmark. Nếu cần replicas, embedded database ownership và storage trở thành điều kiện tiên quyết, không chỉ sửa `max_containers`.

Giới hạn: đây không phải lịch sử phỏng vấn/team decisions. Chỉ các báo cáo linked có measurements; alternatives/scaling triggers là đề xuất kiến trúc. [Interview](../interview/bandpilot-system-design.md) luyện cách phát biểu chính xác.
