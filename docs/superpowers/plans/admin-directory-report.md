# Admin directory implementation report

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Admin directory implementation report. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/admin_directory.py).
> Đọc cùng [current module/guide](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Implemented the bounded discovery portion of Task 3. Admin classroom capability and workspace changes are owned by the root/backend workers.

## Behavior

- `/admin/classrooms` provides distinct Teacher and Student directories, server search, person selection, classroom ownership/status, current enrolled-student counts, and independent pagination.
- Selected teachers filter classrooms by ownership; selected students filter by current enrollment. A selected person is resolved independently of the current people page, so pagination and deep links retain the correct identity.
- Observer links open the existing `/classrooms/{id}` workspace. Roster links open `/classrooms/{id}?tab=people`, coordinated with the root worker.
- The Admin primary navigation and dashboard point to the directory. Existing account administration remains at `/admin` with a clear return link.
- The directory uses BandPilot's existing typography, surface, border, spacing, accent and focus tokens in both themes; all copy supports Vietnamese/English. On narrow screens a selected person's classroom list has a return-to-directory link and does not sit below the entire people list.
- No directory mutation controls or new write endpoints were added.

## Backend contract

- `GET /admin/directory/people`: `role=TEACHER|USER`, optional `search`, `offset`, `limit` (default 25, maximum 100).
- `GET /admin/directory/people/{id}`: role-scoped minimal selected-person identity.
- `GET /admin/directory/classrooms`: optional `teacher_id`, `student_id`, `search`, `offset`, `limit` (default 25, maximum 100).
- Each list uses one SQL count and one SQL page query. Counts are correlated aggregates within the bounded page query, avoiding per-row application queries. Classroom ordering and people ordering include UUID tie-breakers.
- Enrollment counts and student classroom selection require current memberships (`left_at IS NULL`) and exclude platform Admin accounts. Legitimate Teacher accounts enrolled as students remain included, matching classroom roster counts. Teacher/Student account-directory navigation retains its global-role filters. Archived classroom status is preserved.
- Directory responses contain display names, IDs, role/account activity, classroom counts and classroom metadata. Email, phone, biography, birth dates, scores and other private profile fields are not selected or exposed.
- All routes use the existing `AdminUser` dependency. User and Teacher access receives `403 ADMIN_REQUIRED`. Role values and page bounds are validated before service queries. Search SQL wildcard characters are treated as literal text.

## Files

- Backend: `app/api/v1/admin.py`, new `app/schemas/admin_directory.py`, `app/repositories/admin_directory.py`, `app/services/admin_directory.py`, and `tests/test_admin_directory.py`.
- Frontend: new `src/app/admin/classrooms/page.tsx`, `src/features/admin/classroom-directory.tsx`, `src/features/admin/classroom-directory.module.css`, `src/lib/api/admin-directory.ts`, `tests/admin-directory-api.test.ts`, and `tests/admin-directory.test.tsx`.
- Navigation/localization: `src/components/ui/global-header.tsx`, `src/components/ui/app-shell.tsx`, `src/features/auth/admin-content.tsx`, `src/lib/i18n/en.ts`, `src/lib/i18n/vi.ts`, `tests/admin-dashboard.test.tsx`, and `tests/app-shell.test.tsx`.

## Verification

- Red tests confirmed the new backend/client/component modules were absent before implementation.
- `.venv/Scripts/python.exe -m pytest tests/test_admin_directory.py -q`: **9 passed**. This file uses recording SQL sessions and ASGI dependency overrides; it does not request `db_session` or open a database connection. Coverage includes compiled bounded/filter SQL, current enrollment semantics (including Teacher student memberships while excluding legacy Admin memberships), minimal columns, literal wildcard search, Admin-only API authorization, page bounds, role validation, and privacy-safe response serialization. The enrollment review regression failed before changing the two role predicates and passed afterward.
- Scoped Ruff for all directory backend files and the modified Admin router: **passed**.
- `npm exec -- vitest run tests/admin-directory-api.test.ts tests/admin-directory.test.tsx tests/admin-dashboard.test.tsx tests/app-shell.test.tsx`: **102 passed**. Covers API filters/page size, actual observer/roster links, independent account management, VI/EN draft preservation, selected-person loading, invalid and repeated URL inputs, dashboard/navigation routes and shell width.
- Scoped ESLint for directory and modified navigation/component/test files: **passed**.
- `npm run typecheck`: **passed**, including the final repeated-query normalization and mobile-return refinement.
- `git diff --check`: **passed** for the shared working tree at the time of review (only repository CRLF conversion notices).

## Limits

No PostgreSQL integration database was configured or exercised for this subset. Actual database execution/plans and screenshot/layout behavior were not verified. No servers, browsers, browser tests, production builds, full suites, persistent processes, migrations, database resets, commits or pushes were run by this worker. The user's no-browser restrictions take priority over skill screenshot inspection; the approved composition and existing BandPilot design system take priority over alternative skill palettes.
