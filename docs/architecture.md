# BandPilot architecture boundaries

BandPilot is a modular monolith. Next.js renders the frontend and calls FastAPI through the typed clients in `frontend/src/lib/api/`. FastAPI owns domain mutations, authorization, validation, lifecycle transitions, scoring and PostgreSQL access. Browser and server-side API clients both preserve structured `ApiError` codes; page-level guards handle only known denial codes and propagate other failures.

## Backend

- Routers authenticate requests, parse inputs and return response schemas. Services enforce business rules and own transaction scope. Repositories contain reusable SQLAlchemy loading and query logic. A service may issue a small, local query directly when a repository wrapper would add no clarity.
- Keep one `AsyncSession` through an operation. Service methods own `session.begin()` for mutations, including locks, writes and asset cleanup. Pure validation and presentation code must not create a separate database session inside that transaction.
- `AccessPolicy` is authoritative for content visibility and ownership. Listing uses a batch of approved public version IDs for the current request; it does not cache authorization across requests. Classroom approval alone does not make a version public. Archived content is excluded from public access.
- Published `TestVersion` rows remain immutable and historical attempts reference them. Active exam responses omit keys. The attempt service enforces ownership, deadlines, Full Mock progression and review locks before presenting answers.
- `backend/app/domains/questions/registry.py` owns Pydantic contracts and evaluation; `frontend/src/features/questions/registry.tsx` owns editors and renderers. Every objective type must exist in both registries and in the frontend `QuestionType` union. Add compatible schemas and tests when a type changes.
- Transfer import validates the archive, manifest, graph, checksums and content before persistence. Source-to-import ID mapping is isolated in `transfer_ids.py`; `TransferService` still owns the database transaction and compensating asset cleanup. Keep the transfer format compatible.
- AI provider integrations live under `backend/app/providers/`. Writing and Speaking workers run provider work outside HTTP requests and persist durable checkpoints through their services and repositories. AI feedback is advisory; it does not replace server-side objective grading or authorized human final scores.
- Classroom staff capabilities resolve separately from global roles in `classroom_capabilities.py`. Keep Builder ownership/moderation in AccessPolicy. Gradebook and learning analytics share P2 root acceptance/status SQL and native final-score provenance; neither is a second exam/scoring lifecycle. Roster pages, matrix columns, charts and exports must remain bounded and authorized per request.
- P4 aggregate SQL lives in `repositories/classroom_learning.py`; `ClassroomLearningService` resolves scoped dashboards and deterministic evidence/recommendations. `LearningPlanService` manages normalized references to existing activities, not attempts. Reuse profile skill targets and the optional explicit overall target. See [analytics definitions and API](classroom-learning-analytics.md) and [Classroom workspace design](classroom-workspace.md).

## Asset storage

`app/storage/factory.py` is the sole application provider selector. `local` is the
default; `s3` and `r2` use the shared boto3 adapter. PostgreSQL keeps opaque object
keys and authorized relationships, never bucket URLs. Private media is served
through FastAPI after the existing access policies. Bounded byte-range reads
preserve Listening/Speaking seeking. SDK work runs off the event loop; writes
finish before cancellation compensation inspects database references.

Cloud Settings require a bucket and region; R2 additionally requires its HTTPS
account endpoint, region `auto`, and scoped access/secret keys. AWS can use IAM
roles through the standard credential chain. Incomplete configuration fails
closed. Startup initializes only the selected backend; cloud mode does not create
`STORAGE_ROOT`. Temporary FFmpeg/ZIP files and local evaluation fixtures remain
local. Switching a provider does not migrate bytes; verify and copy referenced
keys before an operator-controlled cutover.

The P3 gates are verified offline with boto3 Stubber, fake S3 clients and isolated
PostgreSQL. Live cloud/staging validation, Modal durability and deployment remain
separate operations. The existing local-only backup/restore CLI refuses cloud
mode before database or filesystem changes. P5 must provide a consistent database
backup plus a referenced object inventory, copies, checksums and verified restore.
See [storage configuration and progress](storage-portability-work-in-progress.md).

## Frontend styling

- `globals.css` owns resets, account accent preferences and exam-specific defaults.
- `design-system.css` owns shared light/dark product tokens, typography, surfaces and reusable workspace patterns. Shared root tokens must not be redefined in the Gravity stylesheets.
- `gravity-home.css` owns homepage presentation, interaction and motion; its Gravity palette is scoped to `.gravity-story`. `gravity-product.css` owns the deliberate product component treatment without redefining theme tokens.
- Preserve light/dark themes, account accents, responsive exam layouts, keyboard focus and reduced-motion behavior. The homepage must render useful static content before WebGL enhancement.

## Verification

- Use Vitest for component and CSS contracts, pytest with an isolated PostgreSQL database for backend behavior and query counts, and the three Golden Path Playwright specs for Listening, Writing and Full Mock.
- Authorization tests must cover owner, admin, public, classroom-only, archived and unauthorized views. A locked Full Mock must never expose review answers, regardless of the HTTP status produced by a streamed Next.js page.
- Keep fixture exam content fictional. Never run migrations or destructive integration setup against a development or production database.

## Deployment configuration

P4 keeps the existing Modal demo (one Web container, guarded embedded PostgreSQL
17, original named Volumes) and adds a managed-database/S3/R2 topology. Non-secret
frozen markers select mounts; backend Secrets select the actual P3 provider and
must agree. Cloud topology has no persistent local Volume dependency. Explicit
mode-specific asset Volumes/Secrets, an opt-in strict dev isolation check, and a
matching runtime environment label guard against accidental environment reuse.
Legacy shared demo assets remain an explicitly warned compatibility default.

Modal Local uploads have asynchronous Volume durability; HTTP/database success
is not an immediate durable snapshot acknowledgement. Reload happens before
process startup only, and explicit commit follows shutdown of all application
processes. Failures are surfaced. Use managed PostgreSQL and object storage for
production. External database startup cannot seed or initialize PostgreSQL and
requires separate operator migrations; embedded startup retains its defaults.

The EC2/Docker template uses non-root backend/frontend containers and HTTPS
Nginx, an external TLS PostgreSQL URL, and S3/R2. Only proxy ports are published.
Runtime credentials never enter frontend configuration or image build inputs;
Modal restricts the Next/Nginx child-process environments as well.
Database migrations are an explicit tools-profile command, separate from Web
startup. `/api/v1/health` remains liveness; `/api/v1/ready` checks database access
with a short timeout. Offline tests validate configuration; images, live TLS,
cloud IAM/networking and durability still require staging validation.

See [Modal deployment](modal-web.md), [four profiles and EC2/Docker](aws-deployment.md)
and [storage progress](storage-portability-work-in-progress.md). P5 remains
responsible for migration inventories, verified copies and cloud backup/restore.

## Deliberate limits

`AttemptService` still coordinates lifecycle, autosave, review, history and grading in one module. Its methods share transaction, timer and ownership invariants; splitting those paths without a dedicated contract suite risks changing behavior. `TestService` still contains version cloning and validation, and the question registry still contains the canonical schema table. Further extraction should be driven by a concrete repeated dependency or testable boundary, not file length alone.
