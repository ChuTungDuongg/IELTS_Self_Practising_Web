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

## Frontend styling

- `globals.css` owns resets, account accent preferences and exam-specific defaults.
- `design-system.css` owns shared light/dark product tokens, typography, surfaces and reusable workspace patterns. Shared root tokens must not be redefined in the Gravity stylesheets.
- `gravity-home.css` owns homepage presentation, interaction and motion; its Gravity palette is scoped to `.gravity-story`. `gravity-product.css` owns the deliberate product component treatment without redefining theme tokens.
- Preserve light/dark themes, account accents, responsive exam layouts, keyboard focus and reduced-motion behavior. The homepage must render useful static content before WebGL enhancement.

## Verification

- Use Vitest for component and CSS contracts, pytest with an isolated PostgreSQL database for backend behavior and query counts, and the three Golden Path Playwright specs for Listening, Writing and Full Mock.
- Authorization tests must cover owner, admin, public, classroom-only, archived and unauthorized views. A locked Full Mock must never expose review answers, regardless of the HTTP status produced by a streamed Next.js page.
- Keep fixture exam content fictional. Never run migrations or destructive integration setup against a development or production database.

## Deliberate limits

`AttemptService` still coordinates lifecycle, autosave, review, history and grading in one module. Its methods share transaction, timer and ownership invariants; splitting those paths without a dedicated contract suite risks changing behavior. `TestService` still contains version cloning and validation, and the question registry still contains the canonical schema table. Further extraction should be driven by a concrete repeated dependency or testable boundary, not file length alone.
