# Infrastructure và vận hành

> Mục đích và phạm vi: Các deployment mode, configuration ownership và thao tác operator có thật.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

## Local: chạy gì và ở đâu?

[package.json](../../package.json) điều phối Next.js và FastAPI; [frontend manifest](../../frontend/package.json) định nghĩa scripts, lockfile khóa dependency. Backend dùng Python >=3.12, uv và [uv.lock](../../backend/uv.lock). PostgreSQL 17 Docker ở host 5433, frontend 3000, API 8000. Binary local nằm ở storage root cấu hình, không commit vào Git.

Các lệnh dưới đây là hướng dẫn cho operator, **không được chạy trong audit tài liệu này**:

```powershell
# Từ root; chỉ sau khi đã cấu hình môi trường local riêng
npm install
docker compose up -d postgres
uv --directory backend sync --locked
uv --directory backend run alembic upgrade head
npm run dev
```

Xác nhận DATABASE_URL trước migration. `.env` backend và frontend env có phạm vi khác nhau: `NEXT_PUBLIC_API_BASE_URL` công khai, `API_INTERNAL_BASE_URL` server-side, `DATABASE_URL` và khóa provider chỉ backend. Không copy toàn bộ env backend vào tiến trình Next.

## Modal demo

Nguồn: [app.py](../../deploy/modal/app.py), [web_runtime.py](../../deploy/modal/web_runtime.py), [nginx.conf](../../deploy/modal/nginx.conf). Runbook chuẩn: [Modal deployment](../modal-web.md). Trong working tree lúc audit, runbook này có thay đổi launcher chưa commit; audit giữ nguyên và không dùng launcher mới làm bằng chứng của source revision.

Web CPU 2/4096 MiB, 1 container, tối đa 8 inputs. Runtime lấy guard trước khi mở embedded PostgreSQL 17; database Volume và asset Volume có vai trò khác nhau. Auto-migration/seed chỉ theo mode/config đã validate. Startup đợi API readiness và Next; shutdown dừng ứng dụng/DB trước commit Volume. Nếu process/commit lỗi, cần xử lý vận hành chứ không bỏ guard để ép deploy.

```powershell
# Operator: dùng đúng Secret/Volumes và environment đã xác minh
modal deploy deploy/modal/app.py --strategy recreate
```

Recreate phù hợp single-owner demo để tránh old/new PostgreSQL cùng sở hữu directory. Không dùng nhiều replicas để chữa latency. Nginx hiện buffering off cho frontend/API; không thêm shared cache cho auth, media, analytics hay SSE.

## Modal cloud mode và GPU

Cloud mode dùng external PostgreSQL và S3/R2, marker deploy phải khớp Settings trong Secret; không mount persistent local assets/database như demo. Migration riêng qua operator function:

```powershell
modal run deploy/modal/app.py::migrate_database
```

Phải kiểm tra target trước lệnh. Web không tự seed external database. Provider config dùng `STORAGE_BACKEND`, `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_KEY_PREFIX`; credential names tại [Settings](../../backend/app/core/config.py). AWS có credential chain/IAM, R2 cần endpoint/account credentials đúng. Không fallback cloud lỗi sang local.

Writing LLM, Speaking ASR, DePlot có file deploy riêng và GPU/cache riêng; bật Web AI không chứng minh model đã ready. [AI architecture](ai-architecture.md) giải thích cold/warm và profile cost.

## Staging isolation và chi phí

Mỗi staging cần app name, DB Volume, asset Volume, Secret và guard key tách production; database synthetic/empty. Đọc [P2 evidence](../modal-web-performance.md) trước tái benchmark: đã có shared-guard incident và cleanup chậm 5h34m. Lập danh sách resource do test sở hữu trước tạo; ghi app ID, người chịu trách nhiệm stop và thời điểm kết thúc. Stop đúng test app sau kiểm chứng, giữ persistent resources nếu còn cần evidence. Không stop ứng dụng khác, không reset Volumes.

`min_containers=1` giữ Web warm có chi phí idle; GPU scale-down tùy profile. Không suy đoán bill từ CPU sample vài giây. Benchmark production cần authorization riêng, không ngầm dùng prod vì thiếu staging URL.

## AWS EC2 / Docker

[Compose](../../deploy/aws/compose.yml) có backend/frontend/proxy và tools-profile migrate. Nginx HTTPS, external DB TLS CA, private S3/R2, non-root/read-only settings và resource limits có trong template. Không có database service production ẩn trong Compose này.

```powershell
# Operator runbook; yêu cầu cert, backend.env và database đích đã kiểm tra
 docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml config --no-env-resolution --quiet
 docker compose --env-file deploy/aws/compose.env -f deploy/aws/compose.yml --profile tools run --rm --no-deps migrate
```

Build/start commands, IAM example và profile matrix nằm tại [AWS runbook](../aws-deployment.md); không nhân bản ở đây. Migrate trước rollout phải xét backward compatibility; rollback image không tự rollback schema hoặc object bytes. Giữ bản backup độc lập và destination recovery cách ly. [Backup](../storage-backup-restore.md), [storage migration](../storage-migration.md).

## Chưa xác minh bằng audit này

Không truy vấn cloud resources, không deployment, không kiểm tra TLS/cert expiry, IAM thực tế, production head hay disaster recovery drill. Configuration tests chứng minh điều kiện reject/accept trong code, không chứng minh availability cloud. Local, Modal demo, Modal external và EC2 cần checklist nghiệm thu riêng; không xem chúng như một deployment đồng nhất.
