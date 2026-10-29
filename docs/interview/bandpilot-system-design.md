# BandPilot — System Design & Engineering Interview Guide

> Mục đích và phạm vi: Ôn Software/Backend/AI/System Design bằng kiến trúc thực, không phóng đại đóng góp.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## A. Giới thiệu một phút

“Tôi xây dựng và phát triển BandPilot theo cách AI-assisted, dùng Codex để hỗ trợ implementation và kiểm thử. Đây là nền tảng luyện IELTS bốn kỹ năng, có Builder, lịch sử, classroom và phản hồi AI tham khảo. Frontend Next.js gọi FastAPI, PostgreSQL giữ trạng thái chính thức, file nằm ở storage abstraction. Điểm mạnh kỹ thuật là giữ published versions bất biến, enforce deadline/grading ở backend và phân biệt human final score với AI advisory. Một case có số đo là tối ưu Modal input concurrency trên staging: homepage p95 ở 16 clients từ khoảng 10.7 giây xuống khoảng 2.3 giây. Tôi có thể giải thích benchmark, giới hạn và các quyết định trong code; đây không phải số đo browser production.”

Chỉ dùng “tôi quyết định/kiểm chứng” cho việc bản thân thật sự đã tham gia. Có thể nói “tôi đặt yêu cầu, dùng Codex triển khai và đang học/đối chiếu thiết kế” nếu đó là mô tả đúng hơn.

## B. Walkthrough năm phút

- Phút 1: mục tiêu sản phẩm và USER/TEACHER/ADMIN; capability lớp tách global role.
- Phút 2: Next → typed client → FastAPI router/service/repository → PostgreSQL; media qua authorized storage.
- Phút 3: Builder draft/publish và Attempt frozen version, autosave revision, server deadline, Full Mock stage lazy.
- Phút 4: Writing Task1/2 và Speaking processing/AI workers; checkpoints, SSE observer, human final riêng.
- Phút 5: Local/Modal CPU/AWS topology, GPU functions riêng, single-owner DB constraint và benchmark-supported concurrency.

Dùng [runtime diagrams](../handbook/runtime-architecture.md), không vẽ GPU vào đường render Next.js. Nếu người phỏng vấn hỏi claim production, trả lời phạm vi evidence từ đầu.

## C. Deep dive mười lăm phút

| Thời gian | Nội dung giải thích | Ví dụ cụ thể / nguồn |
| --- | --- | --- |
| 0–2 | Invariants và process boundaries | [System overview](../handbook/system-overview.md), [AGENTS](../../AGENTS.md) |
| 2–4 | Data modeling, UUID, JSONB, frozen content | [Data ER](../handbook/data-architecture.md); số câu đổi nhưng UUID không đổi |
| 4–6 | Attempt consistency | Save/submit cùng lock, parent-before-child, timestamp deadline |
| 6–8 | Authorization nhiều ngữ cảnh | Personal attempt không lộ trong lớp; ADMIN observer; active DTO không key |
| 8–10 | Storage consistency | DB commit mất ack, fresh reference check trước compensation |
| 10–12 | AI pipelines | Score checkpoint trước feedback, Task1 grounding, Speaking lease/PR evidence |
| 12–14 | Performance diagnosis | Public vs local timings, 1→8 inputs, cùng resources, repeated modest benchmark |
| 14–15 | Trade-offs và verification limits | Chưa live-test toàn bộ private/SSE; staging cleanup incident; capacity chưa biết |

Hãy mở một đường code cụ thể trong [module catalog](../handbook/module-catalog.md) khi được hỏi sâu. Không cố học thuộc mọi endpoint; hiểu ai sở hữu state, ai được mutate, transaction ở đâu và failure nào đã có test.

## D. Thử thách có bằng chứng

| Thử thách | Thay đổi/evidence có thật | Giới hạn phát biểu |
| --- | --- | --- |
| Modal request queuing | [P2 JSON và case study](../case-studies/modal-web-performance.md) | Isolated staging, 16 samples/cell, không browser CWV |
| Deadlock/ambiguous media commits | [Concurrency audit](../concurrency-audit.md) | Controlled fault tests, không claim không bao giờ lỗi |
| Portable assets | [Storage architecture](../storage-architecture.md), [recovery](../storage-backup-restore.md) | Offline fake-cloud tests không thay IAM/DR thật |
| Immutable test history | [Authoring](../modules/authoring.md), [attempts](../modules/attempts.md) | Service/persistence contract, không blockchain |
| AI latency và validity | [Writing latency report](../enhance_latency.md), [Speaking](../ai-speaking.md) | Workload/version-specific, feedback advisory |
| Classroom privacy | [Capabilities/provenance](../modules/classrooms.md) | Policy matrix cần regression khi thêm route |

## E. Technical questions và follow-up

### Frontend và API

**1. BandPilot có phải microservices không?**

Hiện là modular monolith: Next presentation riêng, FastAPI dùng chung domain services/database. GPU functions tách compute không phải từng domain service độc lập. [Nguồn](../handbook/runtime-architecture.md).

**2. Server component khác client component thế nào ở dự án?**

Server pages nạp dữ liệu/guard qua server client; form/recorder/queue tương tác chạy client. Cả hai gọi FastAPI, không query PostgreSQL từ Next. [Nguồn](../modules/shared-platform.md).

**3. Typed client có thay runtime validation không?**

Không. TypeScript giúp compile-time nhưng request ngoài app vẫn tùy ý; Pydantic và domain service phải kiểm input/ownership. [Nguồn](../modules/authoring.md).

**4. Tại sao ApiError giữ code/status?**

Caller phân biệt known denial, conflict, network và transient server failure. Nuốt mọi lỗi thành redirect có thể tạo restore loop và che lỗi hạ tầng. [Nguồn](../modules/identity.md).

**5. Làm sao tránh autosave race?**

Client revision queue flush trước submit; server lock attempt, kiểm revision/deadline và persisted response. Không chỉ debounce rồi hy vọng thứ tự mạng đúng. [Nguồn](../modules/attempts.md).

**6. Vì sao không dịch đề khi đổi locale?**

Locale chỉ system UI; authored content/key giữ nguyên để bài thi và historical review không đổi semantics. [Nguồn](../modules/shared-platform.md).

### Backend, database và concurrency

**7. Router, service, repository khác nhau?**

Router nhận actor/DTO; service enforce rules và transaction; repository tái sử dụng query/loading. Service được phép local query nhỏ, không bắt mọi SQL qua wrapper vô ích. [Nguồn](../architecture.md).

**8. Vì sao PostgreSQL authoritative?**

Ownership, attempts, frozen versions và score provenance cần FK/unique constraints/transactions. File storage và React state không có quyền quyết định final state. [Nguồn](../handbook/data-architecture.md).

**9. Vì sao JSONB mà không normalize mọi field?**

Question layout/config đa hình hợp JSONB có schema validation; identity/ownership/relationships vẫn relational. Đổi lại JSON evolution cần validation và compatibility tests. [Nguồn](../handbook/data-architecture.md).

**10. Bất biến TestVersion được thực hiện thế nào?**

AccessPolicy chỉ cho draft mutable; publish/archive lifecycle vẫn đổi hợp lệ, authored published content thì sửa qua draft mới. Historical attempts giữ version FK cũ. [Nguồn](../modules/authoring.md).

**11. Deadlock đã gặp là gì?**

Báo cáo concurrency ghi child→parent và parent→child lock inversion giữa submit/advance. Sửa consistent parent-before-child, có independent-connection regression tests; không phải xóa lock. [Nguồn](../concurrency-audit.md).

**12. Timer có thể chỉ dùng setInterval?**

Không; interval trễ khi tab suspend. TimerService tính từ timestamps/pause và server kiểm deadline khi mutation, gồm sau chờ lock. [Nguồn](../modules/attempts.md).

**13. Một mock gồm bốn attempts có phải bốn submissions?**

Không ở Gradebook: TestSession là một root, child cho skill breakdown. Nếu đếm cả parent/children sẽ double-count. [Nguồn](../modules/classrooms.md).

**14. Migration mới cần kiểm gì?**

Alembic head, upgrade empty/representative DB, constraints/retention, downgrade restrictions và deploy compatibility. Source head không cho biết production đã migrate. [Nguồn](../handbook/data-architecture.md).

### Auth, authorization và security

**15. Vì sao role trong JWT chưa đủ?**

Dependency kiểm signature/claims rồi load current User active/role; resource policy kiểm ownership/capability. Token hợp lệ không tự cấp mọi quyền. [Nguồn](../modules/identity.md).

**16. Refresh concurrency xử lý ra sao?**

Backend rotation/fingerprint/locks giữ state; frontend single-flight/Web Locks phối hợp calls, probe sau ambiguous outcome. Không nói client lock đủ bảo mật. [Nguồn](../modules/identity.md).

**17. Teacher có xem personal practice không?**

Không chỉ vì cùng học sinh/test. Classroom results cần assignment provenance và capability hiện hành, personal attempt khác nguồn vẫn riêng tư. [Nguồn](../modules/classrooms.md).

**18. ADMIN có sửa classroom mọi thứ không?**

Hiện ADMIN là observer với roster/grade/analytics read capabilities; platform account/moderation quyền riêng. Không dùng mô tả P1 cũ làm quy tắc hiện tại. [Nguồn](../modules/administration.md).

**19. Ngăn lộ answer key thế nào?**

Builder DTO và active exam DTO khác nhau; service kiểm scope/finalization/Full Mock review lock. Không gửi key rồi giấu bằng CSS. [Nguồn](../modules/reading-listening.md).

**20. Private media có phải chỉ URL khó đoán?**

Không. UUID/key không phải authorization; FastAPI kiểm owner/provenance/publication trước storage/range response. [Nguồn](../modules/assets-transfer.md).

### Storage và reliability

**21. Vì sao binary nằm ngoài DB?**

Tránh trộn binary delivery với relational authority và hỗ trợ Local/S3/R2; phải chấp nhận cross-store consistency/backup complexity. [Nguồn](../handbook/data-architecture.md).

**22. DB commit error có thể đã thành công không?**

Có, acknowledgement có thể mất. Compensation dùng fresh-session check durable references trước delete; DB unavailable thì giữ object chờ reconcile. [Nguồn](../modules/assets-transfer.md).

**23. Transfer ZIP có phải backup toàn bộ app?**

Không; chuyển test content/keys/referenced assets và remap IDs. Không gồm users/attempts/recordings. Backup dùng workflow DB+objects riêng. [Nguồn](../TEST_TRANSFER_FORMAT.md).

**24. Đổi STORAGE_BACKEND có migrate dữ liệu không?**

Không. Phải inventory/copy/checksum/verify references ở destination, maintenance/cutover rõ và giữ nguồn cho rollback. [Nguồn](../storage-migration.md).

**25. Backup checksum đủ bảo đảm consistency chưa?**

Chưa; bytes có thể nguyên vẹn nhưng snapshot DB/objects khác thời điểm nếu writer còn chạy. Runbook đòi maintenance window và isolated restore verification. [Nguồn](../storage-backup-restore.md).

**26. Health 200 có nghĩa hệ thống ready không?**

Health chỉ liveness; ready thêm DB check timeout. Cả hai không chứng minh model GPU/bucket/private-media workflow khỏe toàn bộ. [Nguồn](../handbook/security-and-reliability.md).

### AI engineering

**27. AI Writing có một prompt chấm tất cả không?**

Không: multi-trait pipeline TA/TR, CC, LR, GRA có stages/output contracts. Task2 score-only trước evidence/feedback; Task1 có visual grounding riêng. [Nguồn](../ai-writing.md).

**28. Tại sao score-first?**

Score validate/checkpoint trước feedback giữ kết quả khi giải thích lỗi. Không có nghĩa score là official; human final workflow riêng. [Nguồn](../modules/writing.md).

**29. Task1 visual grounding làm gì?**

Xây context từ ảnh, kiểm claims/facts cho TA; optional DePlot hỗ trợ chart cross-check, không thay mọi visual family hoặc bịa số thiếu. [Nguồn](../handbook/ai-architecture.md).

**30. Sao không chấm pronunciation từ transcript?**

Văn bản không đủ tín hiệu phát âm. PR cần acoustic evidence; pitch/energy/alignment hiện chỉ proxies, không chứng minh phoneme/examiner agreement. [Nguồn](../modules/speaking.md).

**31. Worker có phải Celery không?**

Hiện detached asyncio tasks + durable PostgreSQL checkpoints/events, leases cho Speaking. Không có broker Celery/Redis xác nhận trong runtime; execution vẫn process-local. [Nguồn](../handbook/ai-architecture.md).

**32. SSE đóng có cancel inference?**

Không; SSE là observer. Close tab dừng đọc, explicit cancel mới tác động run theo policy. Replay sequence hỗ trợ reconnect. [Nguồn](../speaking-grading.md).

**33. Cache AI theo cái gì?**

Input/fingerprint/provider/model/prompt/rubric/config contract theo pipeline; không chỉ attempt UUID. Đổi audio hoặc scoring version phải tránh reuse kết quả cũ. [Nguồn](../modules/speaking.md).

**34. Đánh giá model khác unit test thế nào?**

Unit test với fake kiểm schema/failure/retry. Labelled benchmark đo agreement/coverage/error/latency trên dữ liệu có quyền sử dụng; không đưa ground truth vào inference. [Nguồn](../writing-benchmark-bank.md).

### Cloud, performance và scaling

**35. Website Modal dùng GPU không?**

Web CPU chứa Nginx/Next/FastAPI/embedded PostgreSQL trong demo. Writing/ASR GPU functions riêng, tăng GPU không tự sửa HTML request queue. [Nguồn](../handbook/runtime-architecture.md).

**36. max_inputs=8 khác max_containers=8?**

Input là overlap request trong container; replicas là số container. Tám inputs không tạo tám core và demo vẫn phải một DB owner. [Nguồn](../case-studies/modal-web-performance.md).

**37. Bottleneck Modal được chứng minh đến đâu?**

Public concurrent latency seconds, localhost/upstream milliseconds và cải thiện với 8 inputs hỗ trợ mạnh admission/queue bottleneck trên staging topology. Không đo exact Modal queue time riêng khỏi ingress/network. [Nguồn](../modal-web-performance.md).

**38. Con số cải thiện nào có thể nói?**

Ở 16 clients, homepage p95 10.78/10.67s xuống 2.37/2.32s; readiness RPS 1.57/1.54 lên 6.82/6.87. Hai runs là repeats, không confidence interval; không claim production/browser CWV. [Nguồn](../case-studies/modal-web-performance.md).

**39. Vì sao p95 của 16 samples đáng thận trọng?**

Nearest-rank ceil(0.95×16)=16, chính là max; nhiễu tail lớn. Không dùng làm production SLO. [Nguồn](../interview/modal-performance-qa.md).

**40. Vì sao không tăng replicas ngay?**

Embedded PostgreSQL Volume cần single owner. Muốn replicas phải external database, shared private object store và kiểm worker/lease/migration design trước. [Nguồn](../handbook/infrastructure.md).

**41. 10x traffic hoặc 1000 concurrent users thì làm gì?**

Đó là hypothetical: đo mix active requests/CPU/DB pool/GPU backlog, đặt admission/backpressure, tách workloads và externalize state khi cần. Users không bằng simultaneous inputs; không có capacity claim đã benchmark mức đó. [Nguồn](../handbook/engineering-decisions.md).

**42. EC2 template đã có HA/CD chưa?**

Compose tách containers, external DB/TLS/S3 config nhưng không tự thành multi-AZ HA. GitHub workflows kiểm CI/E2E, không xác nhận automatic production deploy. [Nguồn](../handbook/testing-and-delivery.md).

**43. Test concurrency cần làm gì khác?**

Dùng separate connections/controlled barriers để ép interleaving, assert constraints/outcomes, không chỉ mock hay sleep rồi thấy test pass. [Nguồn](../concurrency-audit.md).

**44. Nếu CPU-bound request chậm hơn khi mở concurrency?**

Giới hạn inputs theo workload/resource evidence, tách long-running CPU work khỏi request, profile trước tăng compute; revert khi p95/reliability xấu. Eight không tối ưu phổ quát. [Nguồn](../case-studies/modal-web-performance.md).

### Follow-up khó

**Nginx rất nhanh nhưng client chậm?** Kiểm public-vs-loopback cùng workload, fresh-connection/TLS, ingress/routing/admission và packet geography. Nginx timing không đo request chưa tới Nginx; không kết luận DB chậm chỉ từ client duration.

**Database pool cạn?** Đo checkout time, active transactions và query durations; xem transaction có giữ qua inference/upload không. Giới hạn admission/workers trước khi tăng pool, vì cùng 2 CPU/PostgreSQL thì nhiều connections có thể tệ hơn. Không có measurement mới trong guide này.

**SSE/upload cạnh tranh assets?** Phân loại request duration/CPU/memory, giữ streaming buffering policy và private cache semantics. Cân nhắc resource isolation sau đo; tăng inputs không làm long streams miễn phí.

**Tại sao không cache mọi thứ?** Auth, private media và personalized analytics có authorization/invalidation. Static immutable assets khác private response. Không đặt shared cache để đổi confidentiality lấy benchmark đẹp.

**Làm performance regression test thế nào?** Isolated fixed dataset/topology, warmup, repeated bounded endpoint mix, ghi commit/config/region/errors, compare p95/throughput và resource samples. Tách browser CWV, handler timing và GPU quality/latency. Cleanup thuộc test, không việc “làm sau”.

## F. Trade-off và kế hoạch giả định

Modular monolith giảm distributed consistency nhưng coupling deploy/CPU; database normalized identities + JSONB layouts cân bằng constraints với variability. External object storage hỗ trợ portability nhưng cần compensation và consistent backup. Managed PostgreSQL phù hợp khi yêu cầu replicas/HA/retention vượt demo, không tự bảo đảm application correctness.

Với 10x traffic, tôi sẽ đo request mix và tail latency trước, kiểm query plans/DB pool, GPU queue và cache an toàn; sau đó mới chọn tách compute/managed state/backpressure. Đây là hướng thiết kế tương lai, không thành tích đã đạt. [Decision table](../handbook/engineering-decisions.md) ghi selected design, alternatives và điều kiện đổi.

## G. Ownership trung thực và câu không nên nói

Codex đã thực hiện nhiều phần implementation/verification theo yêu cầu. Chủ dự án nên nói rõ phần mình trực tiếp làm: xác định yêu cầu, lựa chọn ranh giới, đọc diff/test/evidence, kiểm chứng và giải thích trade-offs. Nếu chưa tự làm một bước, nói “pipeline hiện triển khai như sau, tôi đã đối chiếu…” thay vì “tôi tự viết toàn bộ”. Không bịa team size, traffic doanh nghiệp, doanh thu hoặc SLA.

Không nói “tôi tăng GPU làm web nhanh 8x”, “đã scale 8 containers”, “website luôn load 2 giây”, “AI chấm tương đương giám khảo” hoặc “production performance đã được chứng minh”. Thay bằng workload, metric, topology, phiên bản và limitation cụ thể. CPU samples ngắn không phải peak; repetitions không phải confidence interval.

Lộ trình ôn: [overview](../handbook/system-overview.md) → [runtime](../handbook/runtime-architecture.md) → [data](../handbook/data-architecture.md) → module muốn ứng tuyển → [AI](../handbook/ai-architecture.md) / [security](../handbook/security-and-reliability.md) → [Modal Q&A](modal-performance-qa.md). Tập giải thích một failure case tới tận source và test, không chỉ liệt kê framework.
