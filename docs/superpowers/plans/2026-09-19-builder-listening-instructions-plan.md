# Implementation plan

1. Add failing frontend tests for URL-backed Builder navigation, optional/shared audio UI, one Runner player, YNNG rendering, and registry-driven instructions.
2. Add failing backend tests for module audio mutation, optional publish behavior, YNNG validation/grading/normalization, DTO shape, and migration data cases.
3. Add an Alembic migration that validates/backfills `test_modules.audio_asset_id` before removing `listening_parts.audio_asset_id`.
4. Update SQLAlchemy relationships, repository loading, services, schemas, cloning, asset preservation, validation, and presentation.
5. Update frontend DTO schemas/API calls, Builder navigation/workspaces, Listening Builder, Runner, and Review.
6. Extend the frontend/backend registries for `yes_no_not_given` and add the shared instruction generator/component.
7. Run focused tests while iterating, then all frontend tests and backend non-integration tests. Run lint/typecheck/build and Ruff if time permits, without browser/E2E tests.
8. Inspect the final diff and report database verification limitations if PostgreSQL remains unavailable.
