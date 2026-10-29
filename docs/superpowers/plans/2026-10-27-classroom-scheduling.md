# Classroom P2 implementation and verification ledger

> **Documentation audit: HISTORICAL.** Historical reference; không phải contract hiện hành.
> Mục đích: Classroom P2 implementation and verification ledger. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../../backend/app/services/classroom_capabilities.py).
> Đọc cùng [current module/guide](../../modules/classrooms.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Scope: user attachment `2ac4d7c5-1241-4028-a6d5-fc6ecc47e77d/Pasted text.txt`. Extend P1 in place on main; preserve existing dirty files. No browser/E2E/full suites/build/dev stack. Apply local migration as already requested in this conversation.

## Policy decisions

- Instants are timezone-aware UTC. Availability opens inclusively; submissions/starts exactly at due/cutoff are allowed. Late means completion strictly after due; completion strictly after cutoff is not accepted.
- Legacy assignments default to no windows/limit and `allow_late_submission=true`.
- Root Attempt SUBMITTED/AUTO_SUBMITTED is a submission; INTERRUPTED/ABANDONED are not. A Full Mock requires parent COMPLETED and all expected modules submitted/auto-submitted; child completion alone never satisfies the assignment.
- Append-only normalized policy events record base changes and individual override changes. Read models resolve the effective policy **at the authoritative root completion timestamp**, independently of read time. Later schedule/extension edits cannot relabel earlier completions. Pre-P2 completions resolve legacy unrestricted policy. In-progress work uses changes effective before it completes. Existing engine finalization paths remain unchanged (including Speaking, timeout and Full Mock).
- Overrides use explicit override booleans: false inherits; true plus null removes the deadline. Extensions cannot shorten a finite base deadline. Additional attempts do not cap unlimited policies. Revocation appends history and restores inheritance for future completion/start decisions.
- Start checks run under existing actor→version→classroom→assignment locks; successful root starts of all modes consume one shared slot, including abandoned work. Resume never creates a root.
- Progress prioritizes the most recent accepted completion, otherwise active work, otherwise latest unaccepted submission. MISSED requires an eligible enrollment at/before closure; members joining after closure are NOT_STARTED. All counts and status decisions use scoped SQL roots and bulk queries, never personal practice.
- Reminders: bounded one-shot CLI; 24-hour due-soon and overdue. Idempotency keys include effective deadlines/policy. Deployment scheduling is documented, not claimed deployed.

## Tasks

- [x] Audit origin/main, P1, locks, engine finalization, notification/storage conventions.
- [x] Add fields, extensions, immutable audit event model and migration0037.
- [x] Central pure policy + SQL progress roots and historical acceptance.
- [x] Integrate transactional starts, schedule edits, extensions and immediate notifications.
- [x] Bounded student progress, teacher monitoring/calendar and reminder CLI.
- [x] Focused frontend schedule editor/progress/monitor/extensions/calendar integrated across P1.
- [x] Focused unit/PostgreSQL/concurrency/component tests; migration test and local upgrade.
- [x] Documentation, source review and scoped delivery preparation. Commit/push results are reported from Git after execution.

## Design direction

Keep the P1 editorial tokens and classroom identity. Actual assignment deadlines and root attempt usage form the content. Assignment schedule editor uses native datetime-local controls with explicit browser timezone, serialized as UTC; monitoring uses a narrow filterable table with mobile overflow contained locally. Calendar is an accessible agenda, without a new dependency.

## Verification

Origin/main and local HEAD started aligned at fb529c9. Fresh isolated PostgreSQL database created; upgrade, empty downgrade/re-upgrade successful. 145 focused backend cases passed, 65 frontend cases passed; TypeScript/ESLint/Ruff clean. CLI smoke returned a successful empty batch report. Local database upgraded and confirmed at 20261027_0037 head. No browser/E2E/build/full suite or always-running scheduler was launched.
