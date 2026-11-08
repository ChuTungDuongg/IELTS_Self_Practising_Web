# Ranh giới kiến trúc BandPilot

BandPilot là một modular monolith. Next.js dựng giao diện và gọi FastAPI qua các typed clients trong `frontend/src/lib/api/`. FastAPI chịu trách nhiệm thay đổi dữ liệu nghiệp vụ, phân quyền, validation, chuyển trạng thái vòng đời, chấm điểm và truy cập PostgreSQL. API clients trên browser và server đều giữ mã lỗi có cấu trúc `ApiError`; guards ở cấp page chỉ xử lý những mã từ chối đã biết và chuyển tiếp các lỗi khác.

> Đối chiếu ranh giới và source tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`; chỉ kiểm tra tĩnh. Mục đích là mô tả trách nhiệm hiện hành; kết quả deployment và tests giữ phạm vi xác minh riêng.
> Bắt đầu từ [kho kiến thức](README.md), [bản đồ module](handbook/module-catalog.md), [sơ đồ runtime](handbook/runtime-architecture.md) và [quy trình phát triển feature](handbook/feature-development-playbook.md). Xem [giới hạn audit](DOCS_AUDIT.md).

## Backend

- Routers xác thực request, phân tích input và trả response theo schema. Services thực thi quy tắc nghiệp vụ và sở hữu phạm vi transaction. Repositories chứa logic query và loading SQLAlchemy có thể tái sử dụng. Service có thể trực tiếp thực hiện một query nhỏ, cục bộ nếu thêm repository wrapper không giúp mã rõ hơn.
- Giữ một `AsyncSession` xuyên suốt operation. Service methods sở hữu `session.begin()` cho mutations, gồm locks, ghi dữ liệu và dọn assets. Mã validation hoặc presentation thuần túy không được tạo database session riêng bên trong transaction đó.
- `AccessPolicy` là nơi quyết định quyền xem và quyền sở hữu nội dung. Listing dùng batch IDs của các public versions đã được duyệt cho request hiện tại; không cache authorization giữa các requests. Chỉ được classroom phê duyệt không làm version trở thành public. Nội dung đã archive không được truy cập công khai.
- Các bản ghi `TestVersion` đã publish là bất biến và historical attempts tham chiếu chúng. Response của bài thi đang diễn ra không chứa answer keys. Attempt service kiểm ownership, deadlines, tiến trình Full Mock và review locks trước khi trình bày đáp án.
- `backend/app/domains/questions/registry.py` sở hữu Pydantic contracts và evaluation; `frontend/src/features/questions/registry.tsx` sở hữu editors và renderers. Mọi objective type phải có trong cả hai registries và frontend union `QuestionType`. Khi thay đổi type, bổ sung schemas tương thích và tests.
- Transfer import kiểm archive, manifest, graph, checksums và nội dung trước khi lưu. Ánh xạ IDs nguồn sang IDs sau import được tách trong `transfer_ids.py`; `TransferService` vẫn sở hữu database transaction và asset cleanup để bù trừ khi lỗi. Giữ tương thích transfer format.
- Tích hợp AI providers nằm trong `backend/app/providers/`. Writing và Speaking workers gọi provider ngoài HTTP requests và lưu durable checkpoints qua services/repositories của chúng. AI feedback chỉ mang tính tham khảo, không thay thế objective grading phía server hoặc human final scores được người có quyền nhập.
- Quyền của classroom staff được phân giải riêng với global roles trong `classroom_capabilities.py`. Ownership/moderation của Builder vẫn thuộc AccessPolicy. Gradebook và learning analytics dùng chung SQL acceptance/status của P2 roots và nguồn gốc final score từ các bảng nghiệp vụ; không tạo vòng đời thi/chấm điểm thứ hai. Roster pages, matrix columns, charts và exports phải luôn có giới hạn và được phân quyền theo từng request.
- Aggregate SQL của P4 nằm trong `repositories/classroom_learning.py`; `ClassroomLearningService` xử lý dashboards đúng phạm vi và evidence/recommendations theo quy tắc xác định. `LearningPlanService` quản lý normalized references tới activities hiện có, không quản lý attempts. Tái sử dụng skill targets của profile và explicit overall target tùy chọn. Xem [định nghĩa và API analytics](classroom-learning-analytics.md) và [thiết kế Classroom workspace](classroom-workspace.md).

## Lưu trữ assets

`app/storage/factory.py` là nơi duy nhất chọn storage provider của ứng dụng. Mặc định là `local`; `s3` và `r2` dùng chung boto3 adapter. PostgreSQL lưu opaque object keys và quan hệ được phân quyền, không lưu bucket URLs. Private media được phục vụ qua FastAPI sau các access policies hiện có. Đọc byte range có giới hạn giữ khả năng seek của Listening/Speaking. SDK chạy ngoài event loop; thao tác ghi hoàn tất trước khi cancellation compensation kiểm tra database references.

Cloud Settings yêu cầu bucket và region; R2 cần thêm HTTPS account endpoint, region `auto` và access/secret keys có scope phù hợp. AWS có thể dùng IAM roles qua standard credential chain. Cấu hình thiếu bị từ chối theo nguyên tắc fail closed. Startup chỉ khởi tạo backend đã chọn; cloud mode không tạo `STORAGE_ROOT`. FFmpeg/ZIP temporary files và local evaluation fixtures vẫn ở local. Chuyển provider không tự di chuyển bytes: phải xác minh và copy các keys đang được tham chiếu trước khi operator chuyển hệ thống sang provider mới.

Các P3 gates đã được kiểm offline bằng boto3 Stubber, fake S3 clients và PostgreSQL cách ly. Kiểm cloud/staging thật, Modal durability và deployment là các thao tác riêng. Local backup/restore cũ vẫn tương thích và từ chối cloud mode. Workflow `--portable` được gọi tường minh tạo v2 database/object backups, kiểm checksums và restore vào destination cách ly. Operator tools cần maintenance window; chúng không tự đổi providers hoặc xóa dữ liệu nguồn. Xem [kiến trúc storage](storage-architecture.md), [migration](storage-migration.md), [backup/recovery](storage-backup-restore.md) và [cấu hình, tiến độ storage](storage-portability-work-in-progress.md).

## Nguồn bằng chứng Speaking

Speaking hybrid có nguồn lexical được chọn riêng qua `providers/speaking_asr/lexical.py`:
default tái dùng Azure PA; opt-in regular Azure STT hoặc adapters Faster-Whisper hiện có.
`speaking_hybrid.transcribe_hybrid` điều phối durable checkpoints JSONB độc lập
`speech_analysis` (PA) và `lexical_asr`. Feature/scorer projection lấy LR/GRA/FC từ
canonical lexical, PR từ PA, FC temporal từ CPU VAD; không implicit cross-provider
word alignment. Model lexical/Luna prompt không invalidate PA. Worker giữ state,
lease, retry-consent và authorization hiện có; không có domain mutation từ frontend.
[Private ASR comparison](testing/speaking-audio-replay.md#compare-asr) chỉ gửi những
candidate windows đã duyệt, cần provider selection/budget/live permission tường minh,
không được import/deploy GPU service từ CPU graph. [Cấu hình và rollback](speaking-transcription.md#independent-lexical-asr).

## Admin Speaking Benchmark dataset

Admin Speaking Benchmark Phase 1 là module riêng tại `/admin/speaking-benchmark`, có
owner scope bổ sung ngoài ADMIN, dữ liệu PostgreSQL/revision append-only và audio
AssetStorage riêng tư. HTTP chỉ enqueue; worker PostgreSQL lease chạy riêng và gọi
Community-1 trong subprocess CPU đã pin. Web không import/install Torch/Pyannote.
Approval dùng chung policy của replay CLI; nhãn người chấm không đi vào inference.
Remote worker yêu cầu PostgreSQL ngoài và R2/S3 chung; Modal embedded/local Volume
không được coi là storage chia sẻ. Xem [sơ đồ, API và vận hành](testing/admin-speaking-benchmark.md).

## Styling frontend

- `globals.css` sở hữu resets, account accent preferences và exam-specific defaults.
- `design-system.css` sở hữu product tokens chung cho light/dark, typography, surfaces và workspace patterns tái sử dụng. Không định nghĩa lại shared root tokens trong Gravity stylesheets.
- `gravity-home.css` sở hữu cách trình bày, tương tác và chuyển động của homepage; Gravity palette của nó được giới hạn trong `.gravity-story`. `gravity-product.css` sở hữu cách thể hiện các product components, không định nghĩa lại theme tokens.
- Giữ light/dark themes, account accents, responsive exam layouts, keyboard focus và reduced-motion behavior. Homepage phải có nội dung tĩnh hữu ích trước khi bổ sung WebGL.

## Kiểm chứng

- Dùng Vitest cho component/CSS contracts, pytest với PostgreSQL cách ly cho backend behavior và query counts; bốn browser specs được chọn bởi `.github/workflows/e2e.yml` là Listening, Writing, Full Mock và Reading Practice.
- Authorization tests phải bao phủ owner, admin, public, classroom-only, archived và unauthorized views. Full Mock đang bị khóa không bao giờ được lộ đáp án review, bất kể HTTP status của streamed Next.js page.
- Exam fixtures phải là nội dung hư cấu. Không chạy migrations hoặc destructive integration setup trên development/production database.

## Cấu hình deployment

Bổ sung ngày 2026-11-02: [capacity audit](performance/5000-user-capacity.md) thêm DB pool budget có cấu hình, giữ defaults 5+10/30s, và durable bounded Writing dispatch dùng PostgreSQL run rows, leases và admission control. Writing consumers có thể chạy riêng qua [entrypoint](../backend/app/workers/writing.py); HTTP-only replicas tắt consumers. Code đã có nhưng chưa cloud deployed hoặc được xác minh với 5.000 VUs. Giới hạn Speaking và single-owner Modal demo vẫn là các ràng buộc riêng.

### Concurrency của Modal Web

Modal Web class dùng `@modal.concurrent(max_inputs=8)` để nhận tối đa tám inputs/container, đồng thời giữ `min_containers=1` và `max_containers=1`. Embedded PostgreSQL topology yêu cầu một owner duy nhất cho database Volume; muốn thêm Web replicas cần kiến trúc database/storage riêng đã được review. Web chạy CPU; các AI inference functions được cấu hình chạy riêng trên GPU. Xem [case study Modal performance](case-studies/modal-web-performance.md) để biết staging evidence, trade-offs và giới hạn đo lường.

P4 giữ Modal demo hiện có: một Web container, embedded PostgreSQL 17 có guard và các named Volumes ban đầu; đồng thời bổ sung managed-database/S3/R2 topology. Frozen markers không chứa secrets chọn mounts; backend Secrets chọn P3 provider thực và hai bên phải khớp. Cloud topology không phụ thuộc persistent local Volumes. Asset Volumes/Secrets riêng theo mode, strict dev isolation check bật tùy chọn và runtime environment label tương ứng giúp ngăn reuse nhầm môi trường. Legacy shared demo assets vẫn là compatibility default có cảnh báo rõ.

Modal Local uploads có Volume durability bất đồng bộ; HTTP/database success không phải xác nhận durable snapshot ngay lập tức. Reload chỉ diễn ra trước process startup, còn explicit commit diễn ra sau khi mọi application process đã dừng. Lỗi được báo ra ngoài. Production nên dùng managed PostgreSQL và object storage. Startup với external database không được seed/init PostgreSQL và cần operator migrations riêng; embedded startup giữ defaults hiện có.

EC2/Docker template dùng backend/frontend containers chạy non-root, HTTPS Nginx, external TLS PostgreSQL URL và S3/R2. Chỉ proxy publish ports. Runtime credentials không đi vào frontend config hoặc image build inputs; Modal cũng giới hạn environment của Next/Nginx child processes. Database migrations là explicit tools-profile command, tách khỏi Web startup. `/api/v1/health` vẫn là liveness; `/api/v1/ready` kiểm database access với timeout ngắn. Offline tests kiểm configuration; images, TLS thật, cloud IAM/networking và durability vẫn cần staging validation.

Xem [Modal deployment](modal-web.md), [bốn profiles và EC2/Docker](aws-deployment.md), [tiến độ storage](storage-portability-work-in-progress.md). P5 operator tools cung cấp migration inventories, verified copies và cloud backup/restore cách ly; production cutover và disaster-recovery drills là thao tác live riêng.

## Những giới hạn được giữ có chủ đích

`AttemptService` vẫn điều phối lifecycle, autosave, review, history và grading trong một module. Các methods chia sẻ invariants về transaction, timer và ownership; tách các paths này khi chưa có contract suite riêng có nguy cơ đổi hành vi. `TestService` vẫn chứa version cloning/validation và question registry vẫn giữ canonical schema table. Chỉ nên tiếp tục tách khi có dependency lặp lại cụ thể hoặc boundary có thể kiểm thử, không dựa đơn thuần vào độ dài file.


## Admin Speaking Research boundary

[Phase 3](testing/admin-speaking-benchmark-research.md) adds four additive research tables, an owner-scoped FastAPI API and a separate CPU research consumer. ASR-only uses the existing lexical adapters without OpenAI; paired mode schedules immutable P2 runs serially. Human transcripts/bands are report inputs only, never inference identities. PostgreSQL enforces immutable configurations/results and source bindings. Private storage and existing deletion outbox remain authoritative; embedded Modal PostgreSQL/local Volumes do not become shared worker storage.

Paired report provenance comes from the linked P2 run's stage checkpoints and
nonbillable cache receipts, rather than searching for the newest provider output.
Research and linked P2 cancellation share one transaction. Research normalization
is a pure evaluation contract shared by reference validation and metrics; it does
not modify learner transcripts, provider prompts or the legacy replay CLI.


## Admin Speaking Quality, Consensus and Regression Gates boundary

[Phase 4](testing/admin-speaking-benchmark-quality-and-gates.md) adds eleven additive tables (`20261108_0048`), examiner-question extraction, multi-rater human assessments, owner adjudication (`human-adjudication-v1`), dataset QA (`speaking-dataset-quality-v1`), immutable evaluation suites, regression gates (`speaking-regression-gate-v1`), and an offline CI CLI (`scripts/speaking_benchmark_gate_cli.py`). The blind reviewer API boundary (`/reviewer-assignments/{id}`) enforces strict security server-side: no AI predictions, peer ratings, or ground truth labels are returned. Gate evaluations compute pure paired statistical metrics and bootstrap confidence intervals over immutable persisted artifacts without invoking external AI providers.
