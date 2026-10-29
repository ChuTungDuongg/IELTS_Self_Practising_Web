# Testing và delivery

> Mục đích và phạm vi: Chọn tầng kiểm thử đúng, đọc CI và bảo vệ database test.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## Mỗi tầng trả lời một câu hỏi

| Tầng | Công cụ/source | Xác nhận được | Không xác nhận được |
| --- | --- | --- | --- |
| Typecheck | TypeScript `tsc --noEmit` | Contract type frontend | Runtime auth/DB đúng |
| Lint/format | ESLint, Ruff | Lỗi tĩnh/quy ước | Hành vi nghiệp vụ |
| Unit/component | Vitest/jsdom, pytest pure/fakes | Schema, UI interaction, thuật toán nhỏ | Browser geometry, provider thật |
| PostgreSQL integration | pytest + DB cách ly | Constraints, lock order, transaction, query scope | Cloud durability |
| E2E | Playwright | Luồng browser qua API/DB | SLO production hay mọi case bảo mật |
| Build | Next build, Docker build | Bundle/image tạo được | Deployment thực sự hoạt động |
| Smoke | Modal smoke, health/ready | Target được kiểm tra phản hồi | Toàn bộ dữ liệu/luồng học tập |
| Performance experiment | HTTP/model benchmark | Workload đã đo | Core Web Vitals nếu chỉ HTTP script |

## CI thực tế

[ci.yml](../../.github/workflows/ci.yml) chạy trên pull_request và push main: backend uv locked, Ruff check/format, Alembic upgrade, một migration head, pytest; frontend npm ci, typecheck, lint, Vitest. Có Postgres test chính, P2 riêng và container P5 disposable, cleanup `always()`.

[e2e.yml](../../.github/workflows/e2e.yml) chạy push main/manual, tạo DB/fictional admin, backend, production Next build và Chromium. **Bốn specs**: Listening, Writing, Full Mock, Reading Practice. Report failure được redact trước upload. Các mô tả cũ “ba Golden Paths” là scope trước khi bổ sung Reading. Hai workflow này không triển khai production tự động; không được gọi đây là continuous deployment đã hoàn chỉnh.

## Test isolation

[conftest](../../backend/tests/conftest.py) có fixtures kiểm `TEST_DATABASE_URL`/`P2_TEST_DATABASE_URL` và rollback/savepoints; [test support](../../backend/testsupport/) giữ validator. Một số concurrency/backup tests cần connection/transaction thật và DB riêng, không thể thay bằng một mock session. Đọc fixture của test trước chạy. Không trỏ test destructive vào DB development hoặc production; đừng bỏ validator để vượt test.

[frontend tests](../../frontend/tests/), [backend tests](../../backend/tests/) được map theo module trong [catalog](module-catalog.md). Contract fixtures là hư cấu. Auth tests cần phân biệt resource-specific 401, session expired và transient errors; exam tests phải kiểm DTO không lộ key.

## Lệnh focused cho thay đổi tương lai

```powershell
# Từ root; ví dụ kiểm đúng module, không chạy trong audit này
npm --prefix frontend run test -- tests/auth.test.tsx tests/auth-session-restore.test.tsx
npm --prefix frontend run typecheck
uv --directory backend run pytest tests/test_ielts_band.py -q
uv --directory backend run ruff check app/domains/scoring/ielts_band.py
# Với integration: provision và kiểm tra URL database test riêng trước
```

Không dùng `-m 'not integration'` để khẳng định không chạm DB nếu file chưa đánh marker nhất quán. Đọc imports/fixtures. Chọn E2E khi thay lifecycle/browser media thực sự cần; documentation-only chỉ validate links/source/math và diff, không cần chạy ứng dụng.

## Delivery và evidence

Diff review → focused tests → static checks → kiểm scope/secrets → commit → fetch/reconcile → push không force. Test “đã có” khác “đã chạy lần này”. Ghi rõ command, pass/skip/fail, database mode và hạn chế. Không sửa workflow chỉ để bypass lỗi. Không coi `health` 200 là schema hoặc storage ready; `ready` kiểm DB có timeout.

Chưa thực thi CI/E2E tại revision này trong audit tài liệu; mô tả dựa workflow/source. [Playbook](feature-development-playbook.md) giúp chọn test theo change; [security](security-and-reliability.md) ghi threat-specific checks.
