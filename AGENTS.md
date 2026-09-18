# Engineering invariants

- Frontend is Next.js.
- Backend is FastAPI.
- Frontend never connects directly to PostgreSQL.
- All domain mutations go through FastAPI.
- Never hard-code exam content in React or Python. Test fixtures and fictional seed data are the only exception.
- PostgreSQL is authoritative.
- Published `TestVersion` records are immutable.
- Historical attempts reference frozen `TestVersion` records.
- Timer state derives from timestamps; `setInterval` is display-only.
- FastAPI enforces deadlines.
- Question correctness is evaluated server-side.
- Highlights store semantic offsets, not HTML.
- Assets are stored outside PostgreSQL.
- Do not implement Speaking.
- Do not implement authentication.
- Do not implement AI scoring until explicitly requested.
- Do not commit copyrighted test content.

## Repository boundaries

- `frontend/` contains UI and typed HTTP clients only.
- `backend/` owns domain rules, persistence, validation, evaluation, and lifecycle transitions.
- `storage/` contains generated local binary assets; only `.gitkeep` files are committed.
- Add schema changes through Alembic migrations.
- Keep question-type behavior in the centralized registries, not scattered conditionals.

## Question architecture

- Every supported objective type must have a structured Builder editor, inline answer-key editor,
  backend config/response/key schemas, evaluator, exam renderer, review renderer, and tests.
- Reuse the four answer primitives where practical: single option, multiple options, text, and matching.
- Completion layouts use stable per-question gap IDs; never persist one opaque response for a whole group.
- Active exam DTOs must never expose answer keys. Builder DTOs may contain keys; review DTOs may contain
  keys only after an attempt is finalized.
- Displayed question numbers are presentation metadata. UUIDs remain the identity when questions move.
- Complex group layouts belong in validated JSONB backed by matching Pydantic and Zod schemas.
- Reading coverage expands in Phase 3 only after the Phase 2 Reading MVP is healthy.
- Listening reuses shared registry/rendering primitives and begins only after full Reading coverage.
- Structured families include MCQ single/multiple, T/F/NG, Y/N/NG, matching variants, sentence/summary/
  note/table/flow completion, image-marker labelling, and short answer.
- Image markers use normalized coordinates in the inclusive range 0–1, never browser pixels.
