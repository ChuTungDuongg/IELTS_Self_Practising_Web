# ✨ DevWebLocalforIELTS

Ứng dụng luyện thi IELTS trên máy tính, ưu tiên chạy cục bộ và riêng tư. Dự án cho phép tạo đề bằng giao diện, xuất bản phiên bản bất biến, làm bài nhiều lần, tự động lưu đáp án, chấm câu hỏi khách quan ở backend và xem lại lịch sử.

> 📚 Nội dung mẫu trong repository là nội dung hư cấu do dự án tự tạo, không chứa đề Cambridge/IELTS có bản quyền.

## 🌟 Tính năng hiện có

### Nền tảng

- ✅ Next.js 16 + React 19 + TypeScript + Tailwind CSS
- ✅ FastAPI + Pydantic v2 + SQLAlchemy async
- ✅ PostgreSQL là nguồn dữ liệu chính thức
- ✅ Alembic migration, Docker Compose và fictional seed
- ✅ `Test` → nhiều `TestVersion`; bản đã publish không thể sửa
- ✅ Attempt riêng biệt, lịch sử không bị ghi đè
- ✅ Countdown 70/60/50/40 phút và count-up không giới hạn
- ✅ Backend kiểm tra deadline, AFK 5 phút và trạng thái attempt
- ✅ Light/Dark mode theo hệ điều hành, có nút chuyển trên header 🌙☀️

### Tài khoản, mục tiêu và quản trị

- ✅ Đăng ký/đăng nhập tài khoản local với phiên đăng nhập; hỗ trợ cấu hình Google OAuth
- ✅ `/profile`: thông tin cá nhân tùy chọn, ngày thi mục tiêu và band mục tiêu Listening, Reading, Writing, Speaking
- ✅ Overall **mục tiêu** tự tính từ đủ bốn band kỹ năng; không nhập Overall riêng
- ✅ Đổi mật khẩu cho tài khoản dùng mật khẩu local
- ✅ ADMIN: Builder, Transfer ZIP, thống kê nền tảng và danh sách tài khoản đang hoạt động/đã vô hiệu hóa
- ✅ ADMIN có thể nâng/hạ quyền, vô hiệu hóa/kích hoạt lại và xóa vĩnh viễn tài khoản đã vô hiệu hóa
- ✅ Draft Import CLI chuyển JSON có cấu trúc do OCR/ChatGPT chuẩn bị bên ngoài thành Builder DRAFT để quản trị viên rà soát

### Luyện thi và Full Mock

- ✅ Reading, Listening và Writing Builder/runner/review hoàn chỉnh
- ✅ Full Mock theo thứ tự Listening → Reading → Writing, tạo attempt theo từng chặng để timer không chạy sớm
- ✅ Full Mock dùng thời lượng khuyến nghị của module; review/key chỉ mở khi toàn bộ mock hoàn tất
- ✅ Listening practice cho seek, ±10 giây và tốc độ; Full Mock khóa seek và tốc độ bằng policy từ backend
- ✅ Pause/Resume giữ nguyên attempt và thời gian active; History nhóm theo skill, test version và Full Mock
- ✅ Writing lưu riêng từng task, đếm từ và chấm thủ công theo TA/CC/LR/GRA, kèm feedback tùy chọn cho từng tiêu chí
- ✅ Band khách quan chỉ chính thức khi module có 40 câu; overall dùng Reading + Listening + Writing
- ✅ Analytics: tổng thời gian active, band trend, độ chính xác theo loại câu, weak areas, so sánh attempt và timing theo nội dung

### Reading

- ✅ Reading Builder tạo passage bằng các block có UUID ổn định
- ✅ Một passage có nhiều question group
- ✅ Editor có cấu trúc và answer key ngay trong cùng giao diện
- ✅ Edit/Preview dùng chung renderer với màn hình thi
- ✅ Split-pane Reading runner, hai vùng cuộn độc lập
- ✅ Autosave có debounce, flush an toàn định kỳ và trạng thái Saving/Saved
- ✅ Flag câu hỏi, question navigator và timer phía server
- ✅ Highlight bám theo nguyên từ, lưu semantic offset thay vì HTML
- ✅ Submit/chấm điểm ở FastAPI và review giữ nguyên bố cục câu hỏi
- ✅ Active Exam DTO không gửi answer key trước khi nộp bài
- ✅ Builder tự lưu draft sau khoảng 1 giây, hiển thị Saved/Unsaved/Saving/Error và flush trước Preview/Validate/Publish
- ✅ Transfer Portal xuất/nhập test, version, câu hỏi, hình và audio bằng ZIP có checksum; không chứa attempt/history

Các dạng câu hỏi Reading hiện có:

1. Multiple Choice — Single / Multiple
2. True / False / Not Given; Yes / No / Not Given
3. Matching Headings, Information, Features và Sentence Endings
4. Sentence, Summary (text/word list), Note, Table và Flow-chart Completion
5. Diagram Label Completion và Short Answer

Các family dùng chung editor/renderer/evaluator khi data shape giống nhau; key và chấm điểm vẫn do backend quản lý.

### Profile và IELTS goals

Đăng ký không yêu cầu hoàn tất profile. Tại `/profile`, người dùng có thể lưu thông tin cá nhân, bốn band mục tiêu và ngày thi dự kiến; hiện không có ảnh đại diện. Tài khoản dùng mật khẩu local có thể đổi mật khẩu; tài khoản chỉ dùng Google hiện không dùng chức năng Change Password.

Overall **mục tiêu cá nhân** = trung bình của **đủ bốn** band mục tiêu Listening, Reading, Writing, Speaking, rồi làm tròn đến band 0,5 gần nhất (mốc giữa làm tròn lên). Thiếu bất kỳ kỹ năng nào thì Overall mục tiêu chưa có. Ví dụ `6.0 + 6.5 + 7.5 + 8.5` cho Overall mục tiêu `7.0`. Giá trị này không phải điểm bài làm. Điểm thực tế hiện dựa trên Reading, Listening và Writing theo logic chấm hiện có; Speaking chỉ là trường **mục tiêu** trong profile, không có module luyện/chấm Speaking.

### Draft Import

OCR/ChatGPT chuẩn bị JSON có cấu trúc **bên ngoài** ứng dụng; ứng dụng không tự thực hiện OCR. Từ thư mục `backend/`:

```powershell
Set-Location backend
uv run python -m app.import_draft path/to/manifest.json
```

Kết quả luôn là phiên bản `DRAFT`. ADMIN mở trong Builder để kiểm tra, chỉnh sửa và Publish theo quy trình thường. Định dạng và manifest hư cấu: [docs/draft-import-format.md](docs/draft-import-format.md).

### Giao diện minh họa

Ảnh chụp từ giao diện local với tài khoản và mục tiêu hư cấu. Overall `7.0` được tính từ bốn mục tiêu `6.0 / 6.5 / 7.5 / 8.5`.

**Trang chủ (desktop)**

![Trang chủ với IELTS goals](docs/screenshots/homepage-goals-desktop.png)

**Profile: chỉnh mục tiêu từng kỹ năng**

![Profile với Overall target được tính tự động](docs/screenshots/profile-goals.png)

**IELTS goals trên màn hình nhỏ**

![IELTS goals trên màn hình điện thoại](docs/screenshots/homepage-goals-mobile.png)

## 🧭 Kiến trúc

```text
Trình duyệt
    │
    ▼
Next.js frontend (cổng 3000)
    │  HTTP / REST /api/v1
    ▼
FastAPI backend (cổng 8000)
    │
    ├── Application services
    ├── Question registry + evaluator
    ├── Timer / AFK / attempt state machine
    ├── Repository + SQLAlchemy async
    └── Local asset storage
    │
    ▼
PostgreSQL
```

Frontend không kết nối trực tiếp PostgreSQL. Mọi thao tác thay đổi dữ liệu, publish, deadline và chấm điểm đều đi qua FastAPI.

## 📁 Cấu trúc repository

```text
backend/              FastAPI, domain, model, service, Alembic, pytest
frontend/             Next.js App Router, API client, Vitest, Playwright
storage/audio/        File âm thanh cục bộ, không commit binary
storage/images/       File hình ảnh cục bộ, không commit binary
docs/ROADMAP.md       Lộ trình và phạm vi từng phase
docker-compose.yml    PostgreSQL cho môi trường local
.env.example          Mẫu cấu hình
AGENTS.md             Các nguyên tắc kiến trúc bắt buộc
```

## 🧰 Yêu cầu hệ thống

- Python 3.12 trở lên
- [`uv`](https://docs.astral.sh/uv/) để quản lý Python dependency
- Node.js 20.9 trở lên và npm
- Docker Desktop có Docker Compose; hoặc một PostgreSQL riêng

Lockfile hiện tại được tạo bằng Python 3.14 và Node.js 24, nhưng backend vẫn hỗ trợ Python 3.12+.

## 🚀 Hướng dẫn chạy nhanh

### 1. Tạo file môi trường

Tại thư mục gốc của repository:

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item .env.example frontend/.env.local
```

Giá trị mặc định dùng cho local:

| Biến | Ý nghĩa | Giá trị mẫu |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL URL cho SQLAlchemy async | `postgresql+asyncpg://ielts:ielts@localhost:5432/ielts` |
| `FRONTEND_ORIGIN` | Origin được CORS cho phép | `http://localhost:3000` |
| `JWT_SECRET` | Secret bắt buộc cho xác thực trong `backend/.env`; ít nhất 32 ký tự, không commit | Tự tạo |
| `AUTH_COOKIE_SECURE` / `AUTH_COOKIE_SAMESITE` | Cookie local trên HTTP | `false` / `lax` |
| `STORAGE_ROOT` | Nơi lưu binary asset | `../storage` |
| `MAX_IMAGE_UPLOAD_MB` | Giới hạn hình ảnh | `10` |
| `MAX_AUDIO_UPLOAD_MB` | Giới hạn audio | `100` |
| `MAX_TRANSFER_ZIP_MB` | Giới hạn ZIP nén khi import | `300` |
| `MAX_TRANSFER_UNCOMPRESSED_MB` | Giới hạn tổng dung lượng giải nén | `600` |
| `MAX_TRANSFER_FILES` | Giới hạn số file trong ZIP | `5000` |
| `NEXT_PUBLIC_API_BASE_URL` | API URL phía frontend | `http://localhost:8000/api/v1` |

Google OAuth là tùy chọn: đặt `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` và `GOOGLE_REDIRECT_URI` theo `backend/.env.example` khi cần. Không đưa client secret hoặc JWT secret thật vào repository.

Giữ cùng hostname `localhost` cho frontend và backend. Cookie phiên đăng nhập được gắn với hostname, nên `127.0.0.1:8000` không dùng chung cookie với `localhost:3000`. Sau khi đổi `.env.local`, khởi động lại Next.js.

### 2. Khởi động PostgreSQL 🐘

```powershell
docker compose up -d postgres
docker compose ps
```

PostgreSQL chạy ở `localhost:5432`. Dữ liệu được giữ trong Docker named volume.

### 3. Chạy backend ⚡

Mở terminal thứ nhất:

```powershell
Set-Location backend
uv sync --group dev
uv run alembic upgrade head
uv run python -m app.seed
uv run fastapi dev app/main.py
```

`uv` và [`backend/uv.lock`](backend/uv.lock) là workflow phát triển được ưu tiên. Với môi trường triển khai chỉ hỗ trợ `pip`, repository cũng cung cấp bản export runtime đã khóa phiên bản:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

`backend/requirements.txt` được tạo từ dependency set do `uv` quản lý; không chỉnh version trực tiếp trong file này. Tạo lại từ thư mục `backend/` bằng `uv export --format requirements.txt --no-dev --no-emit-project --locked --output-file requirements.txt`.

Sau khi chạy:

- API: [http://localhost:8000](http://localhost:8000)
- Health: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- Swagger/OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

`app.seed` có thể chạy lại an toàn; script bỏ qua seed nếu dữ liệu mẫu đã tồn tại.

Để tạo ADMIN local lần đầu, đặt `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD` và `INITIAL_ADMIN_NAME` trong `backend/.env`, rồi chạy `uv run python -m app.bootstrap_admin` từ `backend/`.

### 4. Chạy frontend 🎨

Mở terminal thứ hai:

```powershell
Set-Location frontend
npm install
npm run dev
```

Mở [http://localhost:3000](http://localhost:3000).

### 5. Luồng dùng thử đề xuất

1. Đăng ký/đăng nhập; có thể đặt mục tiêu tại **Profile**. ADMIN vào **Builder** → **New test**.
2. Mở Version 1 → tạo Reading, Listening và Writing module cùng thời lượng khuyến nghị.
3. Thêm passage, Listening parts/audio và Writing tasks.
4. Thêm question group bằng registry loại câu hỏi dùng chung.
5. Nhập câu hỏi và answer key ngay trong editor.
6. Bấm **Preview**, sau đó **Validate** và **Publish**.
7. Vào **Library** để bắt đầu Full Mock hoặc luyện riêng từng skill với timer tự chọn.
8. Trả lời, flag/highlight nếu cần, rồi **Submit**; Full Mock chuyển sang module kế tiếp.
9. Mở **History** → **Review** hoặc **Analytics** để xem kết quả và tiến trình.

## 🧪 Chạy kiểm thử

### Backend

```powershell
Set-Location backend
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run alembic upgrade head --sql
```

### Frontend

```powershell
Set-Location frontend
npm run lint
npm run typecheck
npm test
npm run build
```

### Playwright E2E

Backend và PostgreSQL phải đang chạy. Lần đầu cần cài Chromium:

```powershell
Set-Location frontend
npx playwright install chromium
npm run test:e2e
```

Kiểm tra riêng phiên đăng nhập: tạo admin local bằng `uv run python -m app.bootstrap_admin` từ `backend/` với các giá trị `INITIAL_ADMIN_*` trong `backend/.env`. Sau đó đặt `E2E_ADMIN_EMAIL` và `E2E_ADMIN_PASSWORD` tương ứng trong terminal chạy frontend và dùng `npx playwright test tests/e2e/auth-session.spec.ts`. Spec tự tạo USER thử nghiệm; không commit mật khẩu hoặc JWT secret.

## 🔐 Nguyên tắc dữ liệu quan trọng

### Version bất biến

```text
Tạo Test → Draft → Validate → Publish (đóng băng)
Published → Clone → Draft mới → Chỉnh sửa → Publish
```

Attempt luôn tham chiếu đúng `TestVersion` đã dùng lúc bắt đầu. Passage, câu hỏi, key, highlight và review cũ vì vậy luôn tái hiện được.

### Timer phía server

Frontend chỉ vẽ đồng hồ. Thời gian thật được suy ra từ `started_at`, `deadline_at` và `server_time`. Mỗi autosave đều được FastAPI kiểm tra lại deadline, AFK và trạng thái attempt.

### Answer key

- Builder DTO có key để tác giả chỉnh sửa.
- Active Exam DTO không có key.
- Review DTO chỉ có key sau khi attempt kết thúc; module thuộc Full Mock còn bị khóa đến khi session hoàn tất.
- Frontend không gửi `isCorrect`; FastAPI tự tải key từ bản đề đã đóng băng và chấm.

### Asset

Binary không nằm trong PostgreSQL. Backend kiểm tra MIME, đuôi file, kích thước, tạo tên UUID và chỉ ghi vào `storage/audio` hoặc `storage/images`.

### Quản trị tài khoản

ADMIN xem thống kê nền tảng, danh sách USER/ADMIN đang hoạt động hoặc đã vô hiệu hóa, nâng/hạ quyền và kích hoạt lại tài khoản. Xóa vĩnh viễn chỉ thực hiện sau khi vô hiệu hóa; thao tác xóa lịch sử học cá nhân của tài khoản đó (attempt và test session), không xóa nội dung đề dùng chung đã được tạo trong Builder.

## 🔌 API chính

### Xác thực và Profile

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/profile`
- `PATCH /api/v1/auth/profile`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/auth/oauth/google/start` và callback Google OAuth (khi đã cấu hình)

### ADMIN

- `GET /api/v1/admin/stats`
- `GET /api/v1/admin/users`
- `GET /api/v1/admin/users/{id}`
- `PATCH /api/v1/admin/users/{id}`
- `DELETE /api/v1/admin/users/{id}`

### Test và Builder

- `GET/POST /api/v1/tests`
- `GET /api/v1/tests/{test_id}`
- `POST /api/v1/tests/{test_id}/versions`
- `GET /api/v1/test-versions/{id}/builder`
- `POST /api/v1/test-versions/{id}/modules`
- `POST /api/v1/test-versions/{id}/reading/passages`
- `PUT/DELETE /api/v1/reading/passages/{id}`
- `POST /api/v1/reading/passages/{id}/question-groups`
- `PUT/DELETE /api/v1/question-groups/{id}`
- `POST /api/v1/test-versions/{id}/validate`
- `POST /api/v1/test-versions/{id}/publish`
- `POST /api/v1/transfer/export`
- `POST /api/v1/transfer/import`

### Attempt

- `POST /api/v1/attempts`
- `GET /api/v1/attempts/{id}/exam`
- `POST /api/v1/attempts/{id}/activity`
- `POST /api/v1/attempts/{id}/navigation`
- `PUT /api/v1/attempts/{id}/answers/{question_id}`
- `PUT /api/v1/attempts/{id}/flags/{question_id}`
- `POST/DELETE /api/v1/attempts/{id}/highlights`
- `POST /api/v1/attempts/{id}/submit`
- `GET /api/v1/attempts/{id}/reading-review`
- `GET /api/v1/history`
- `POST/GET /api/v1/test-sessions`
- `POST /api/v1/test-sessions/{id}/advance`
- `GET /api/v1/analytics`
- `GET /api/v1/analytics/compare`

Lỗi ứng dụng có cấu trúc ổn định:

```json
{
  "code": "ATTEMPT_EXPIRED",
  "message": "The countdown period has ended."
}
```

## 🛣️ Trạng thái phát triển

- **Hiện có:** Reading/Listening/Writing, Full Mock, pause/resume, chấm Writing thủ công, Builder autosave, Transfer ZIP, Draft Import CLI, History/Analytics, xác thực, Profile/mục tiêu IELTS và quản trị tài khoản.
- **Tiếp theo:** tăng độ sâu của analytics, accessibility và độ bền của Builder workflow.
- **Cố ý không làm:** module luyện/chấm Speaking (chỉ có Speaking target trong Profile), OCR tích hợp, thanh toán và AI Writing scoring.

Xem checklist chi tiết tại [docs/ROADMAP.md](docs/ROADMAP.md). 💫
