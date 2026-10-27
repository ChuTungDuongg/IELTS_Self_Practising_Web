# BandPilot

**Practice smarter. Reach your band.**

<img src="frontend/public/brand/bandpilot-compass-ribbon.svg" alt="BandPilot Compass Ribbon logo" width="64" height="64" />

BandPilot là nền tảng luyện tập IELTS độc lập cho **Reading, Listening, Writing và Speaking**, kết hợp đề thi thử có cấu trúc, phản hồi AI tham khảo, công cụ biên soạn đề, lớp học và theo dõi tiến trình. Có thể chạy cục bộ để giữ dữ liệu riêng tư hoặc triển khai trên Modal theo cấu hình của repository. BandPilot không liên kết chính thức với các đơn vị sở hữu hay tổ chức kỳ thi IELTS; điểm và phản hồi của ứng dụng không phải chứng nhận IELTS.

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
- ✅ Personalization popup trên header: Accent Color presets, giao diện Light/Dark và ngôn ngữ EN/VI, lưu theo tài khoản; không có nút đổi theme riêng trên header

### Tài khoản, mục tiêu và quản trị

- ✅ Đăng ký/đăng nhập tài khoản local với phiên đăng nhập; hỗ trợ cấu hình Google OAuth
- ✅ `/profile`: thông tin cá nhân tùy chọn, ngày thi mục tiêu và band mục tiêu Listening, Reading, Writing, Speaking
- ✅ Overall **mục tiêu** tự tính từ đủ bốn band kỹ năng; không nhập Overall riêng
- ✅ Đổi mật khẩu cho tài khoản dùng mật khẩu local
- ✅ USER / TEACHER / ADMIN: quyền luyện tập, biên soạn và quản trị theo vai trò
- ✅ TEACHER: Builder đề riêng, yêu cầu duyệt CLASSROOM/PUBLIC, lớp học, lời mời và bài giao gắn với phiên bản đề đã đóng băng
- ✅ Kết quả bài giao chỉ đọc theo assignment provenance; giáo viên không được xem bài luyện cá nhân không liên quan
- ✅ ADMIN: Builder, Transfer ZIP, duyệt nội dung, thống kê nền tảng và danh sách tài khoản đang hoạt động/đã vô hiệu hóa
- ✅ ADMIN có thể nâng/hạ quyền, vô hiệu hóa/kích hoạt lại và xóa vĩnh viễn tài khoản đã vô hiệu hóa
- ✅ Draft Import CLI chuyển JSON có cấu trúc do OCR/ChatGPT chuẩn bị bên ngoài thành Builder DRAFT để quản trị viên rà soát

### Luyện thi và Full Mock

- ✅ Reading, Listening, Writing và Speaking Builder/runner/review
- ✅ Full Mock mới theo thứ tự Listening → Reading → Writing → Speaking, tạo attempt theo từng chặng để timer không chạy sớm
- ✅ Full Mock dùng thời lượng khuyến nghị của module; review/key chỉ mở khi toàn bộ mock hoàn tất
- ✅ Listening practice cho seek, ±10 giây và tốc độ; Full Mock khóa seek và tốc độ bằng policy từ backend
- ✅ Pause/Resume giữ nguyên attempt và thời gian active theo policy từng kỹ năng; Speaking có lifecycle/recovery riêng. History nhóm theo skill, test version và Full Mock
- ✅ Autosave có revision/concurrency check; bản nháp chưa lưu có thể khôi phục sau reload hoặc mất mạng ngắn hạn
- ✅ Writing lưu riêng từng task, đếm từ và chấm thủ công theo TA/TR, CC, LR, GRA, kèm feedback tùy chọn cho từng tiêu chí
- ✅ AI Academic Writing Task 1 và Task 2: score-first, phản hồi tham khảo theo bốn tiêu chí và Scoring Trace; lỗi feedback không làm mất điểm AI hợp lệ đã lưu. Chấm thủ công và AI tham khảo có quy trình riêng. [Cấu hình và giới hạn](docs/ai-writing.md).
- ✅ Speaking P1–P8: ghi âm riêng tư theo từng câu, recovery thành các container segment riêng, transcript, bằng chứng quality/fluency/pronunciation và AI tham khảo theo FC/LR/GRA/PR; tích hợp History/Classroom và công cụ benchmark offline. [Kiến trúc và đánh giá](docs/ai-speaking.md).
- ✅ Modal: Web chạy Next.js + FastAPI + PostgreSQL với persistent Volume và FFmpeg; faster-whisper ASR có dịch vụ GPU riêng, Writing/Speaking dùng chung Ministral/vLLM. GPU scale-to-zero khi rảnh. [Thiết lập và triển khai](docs/modal-web.md).
- ✅ Band quy đổi cho Reading/Listening chỉ được tính khi module có 40 câu; overall dự án cần đủ bốn kỹ năng, Speaking AI luôn là tham khảo
- ✅ History tích hợp bốn kỹ năng; Analytics có tổng thời gian active, band trend, độ chính xác theo loại câu, weak areas, so sánh attempt và timing theo nội dung, tùy dữ liệu đã chấm

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
- ✅ Transfer Portal xuất/nhập nội dung bốn kỹ năng, test/version, câu hỏi/key và asset đề bằng ZIP có checksum; không chứa attempt/history hay bản ghi âm riêng tư của người học

Các dạng câu hỏi Reading hiện có:

1. Multiple Choice — Single / Multiple
2. True / False / Not Given; Yes / No / Not Given
3. Matching Headings, Information, Features và Sentence Endings
4. Sentence, Summary (text/word list), Note, Table và Flow-chart Completion
5. Diagram Label Completion và Short Answer

Các family dùng chung editor/renderer/evaluator khi data shape giống nhau; key và chấm điểm vẫn do backend quản lý.

### Speaking và phản hồi AI

Speaking đã triển khai các phase P1–P8: Builder có ba phần và prompt có cấu trúc; runner kiểm tra microphone, ghi âm/upload theo chunk và khôi phục sau reload; audio riêng tư được lưu theo segment. FastAPI quản lý chuyển prompt, deadline và quyền truy cập. Review mở sau khi attempt hoàn tất; bài trong Full Mock còn phải đợi cả mock hoàn tất.

Pipeline dùng audio đã chuẩn hóa để tạo transcript verbatim/clean, bằng chứng chất lượng âm thanh, fluency và pronunciation, rồi chấm AI tham khảo theo FC/LR/GRA/PR. Tiêu chí thiếu bằng chứng được đánh dấu không khả dụng; không tự bịa điểm. History và kết quả lớp học tái sử dụng dữ liệu đã lưu, với quyền chỉ đọc theo nguồn bài giao. P8 bổ sung công cụ benchmark, **chưa có bằng chứng xác lập độ chính xác tương đương giám khảo**. Chi tiết: [AI Speaking](docs/ai-speaking.md), [recording/recovery](docs/speaking-recording.md), [transcript/evidence](docs/speaking-transcription.md) và [advisory grading](docs/speaking-grading.md).

### Transfer và tên nội bộ ổn định

BandPilot là tên sản phẩm công khai. Tên repository `IELTS_Self_Practising_Web`, các package `devweblocalforielts*`, database/Volume, biến môi trường, khóa local storage và API vẫn giữ nguyên. Transfer ZIP tiếp tục dùng protocol `devweblocalforielts-test-bundle`, schema version `1`; backup manifest giữ nhãn `DevWebLocalforIELTS`. Đây là identifier kỹ thuật cũ được giữ để tương thích ngược, không phải tên hiển thị trong giao diện. Xem [định dạng Transfer ZIP](docs/TEST_TRANSFER_FORMAT.md).

### Profile và IELTS goals

Đăng ký không yêu cầu hoàn tất profile. Tại `/profile`, người dùng có thể lưu thông tin cá nhân, bốn band mục tiêu và ngày thi dự kiến; hiện không có ảnh đại diện. Tài khoản dùng mật khẩu local có thể đổi mật khẩu; tài khoản chỉ dùng Google hiện không dùng chức năng Change Password.

Overall **mục tiêu cá nhân** = trung bình của **đủ bốn** band mục tiêu Listening, Reading, Writing, Speaking, rồi làm tròn đến band 0,5 gần nhất (mốc giữa làm tròn lên). Thiếu bất kỳ kỹ năng nào thì Overall mục tiêu chưa có. Ví dụ `6.0 + 6.5 + 7.5 + 8.5` cho Overall mục tiêu `7.0`. Giá trị này không phải điểm bài làm. Speaking có module luyện và đánh giá AI tham khảo riêng; overall kết quả dự án cần đủ bốn band kỹ năng và không phải chứng nhận IELTS.

### Draft Import

OCR/ChatGPT chuẩn bị JSON có cấu trúc **bên ngoài** ứng dụng; ứng dụng không tự thực hiện OCR. Từ thư mục `backend/`:

```powershell
Set-Location backend
uv run python -m app.import_draft path/to/manifest.json --owner-user-id ADMIN_UUID
```

Kết quả luôn là phiên bản `DRAFT`. ADMIN mở trong Builder để kiểm tra, chỉnh sửa và Publish theo quy trình thường. Định dạng và manifest hư cấu: [docs/draft-import-format.md](docs/draft-import-format.md).

### Giao diện minh họa

Ảnh chụp từ giao diện local với tài khoản và mục tiêu hư cấu. Overall `7.0` được tính từ bốn mục tiêu `6.0 / 6.5 / 7.5 / 8.5`.

Một số ảnh chụp lịch sử còn nhận diện **IELTS Studio** và bố cục/theme controls trước khi dự án đổi tên thành BandPilot; chúng không phản ánh đầy đủ giao diện hiện tại.

**Trang chủ (desktop)**

![Trang chủ với IELTS goals](docs/screenshots/homepage-goals-desktop.png)

**Profile: chỉnh mục tiêu từng kỹ năng**

![Profile với Overall target được tính tự động](docs/screenshots/profile-goals.png)

**IELTS goals trên màn hình nhỏ**

![IELTS goals trên màn hình điện thoại](docs/screenshots/homepage-goals-mobile.png)

## 🧭 Kiến trúc

### Local

```text
Trình duyệt
    └── Next.js frontend (3000)
            └── HTTP / REST /api/v1 → FastAPI (8000)
                    ├── Domain services, registry + evaluator
                    ├── Timer / deadline / attempt lifecycle
                    ├── PostgreSQL (Docker Compose: 5433)
                    └── Storage: asset đề + audio Speaking riêng tư

AI tùy chọn, qua backend đã cấu hình:
FastAPI ──┬── Speaking ASR → faster-whisper GPU service
          └── Writing/Speaking AI → Ministral/vLLM GPU service
```

Frontend không kết nối trực tiếp PostgreSQL. Mọi thao tác thay đổi dữ liệu, publish, deadline và chấm điểm đều đi qua FastAPI.

### Modal

```text
Trình duyệt HTTPS
    └── Web CPU container: Nginx
            ├── Next.js
            └── FastAPI
                    ├── PostgreSQL process → persistent PostgreSQL Volume
                    ├── Private storage → assets Volume
                    ├── FFmpeg normalization + audio evidence (CPU)
                    ├── Speaking ASR → faster-whisper T4 (scale-to-zero)
                    └── Writing/Speaking AI → Ministral/vLLM L4 (scale-to-zero)
```

Web/PostgreSQL giữ một CPU replica; hai dịch vụ GPU có zero minimum containers. ASR chỉ nhận WAV đã chuẩn hóa, model cache nằm trên Volume riêng; Ministral được dùng chung cho Writing và Speaking. Web không nạp model GPU khi chỉ khởi động ứng dụng. Local, Modal dev và Modal production có database riêng; **không tự đồng bộ dữ liệu**. Sau thiết lập một lần, `modal serve deploy/modal/app.py` phục vụ phiên dev; `modal deploy deploy/modal/app.py` tạo deployment lâu dài. Xem [docs/modal-web.md](docs/modal-web.md) để chuẩn bị Secret, snapshot và Volume đúng quy trình.

## 📁 Cấu trúc repository

```text
backend/              FastAPI, domain, model, service, Alembic, pytest
frontend/             Next.js App Router, API client, Vitest, Playwright
storage/audio/        File âm thanh cục bộ, không commit binary
storage/images/       File hình ảnh cục bộ, không commit binary
storage/speaking-private/  Bản ghi âm Speaking riêng tư, không commit
deploy/modal/         Web/PostgreSQL, shared LLM và Speaking ASR services
docs/ROADMAP.md       Lộ trình và phạm vi từng phase
docker-compose.yml    PostgreSQL cho môi trường local
backend/.env.example  Mẫu cấu hình backend
scripts/              Backup/restore PostgreSQL + local asset storage
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
Set-Content frontend/.env.local 'NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1'
```

Giá trị mặc định dùng cho local:

| Biến | Ý nghĩa | Giá trị mẫu |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL URL cho SQLAlchemy async khi dùng Docker Compose | `postgresql+asyncpg://ielts:ielts@localhost:5433/ielts` |
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

Docker Compose mở PostgreSQL ở `localhost:5433` (cổng `5432` bên trong container). Dữ liệu được giữ trong Docker named volume. GitHub Actions dùng PostgreSQL riêng trên cổng `5432`.

### 3. Cài dependencies và chuẩn bị database

```powershell
npm install
uv --directory backend sync --group dev
uv --directory backend run alembic upgrade head
uv --directory backend run python -m app.seed
```

Chạy các lệnh trên tại thư mục gốc repository. `npm install` cài công cụ chạy song song ở root và cài frontend theo `frontend/package-lock.json`.

`uv` và [`backend/uv.lock`](backend/uv.lock) là workflow phát triển được ưu tiên. Với môi trường triển khai chỉ hỗ trợ `pip`, repository cũng cung cấp bản export runtime đã khóa phiên bản:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

`backend/requirements.txt` được tạo từ dependency set do `uv` quản lý; không chỉnh version trực tiếp trong file này. Tạo lại từ thư mục `backend/` bằng `uv export --format requirements.txt --no-dev --no-emit-project --locked --output-file requirements.txt`.

`app.seed` có thể chạy lại an toàn; script bỏ qua seed nếu dữ liệu mẫu đã tồn tại.

Để tạo ADMIN local lần đầu, đặt `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD` và `INITIAL_ADMIN_NAME` trong `backend/.env`, rồi chạy `uv --directory backend run python -m app.bootstrap_admin` từ thư mục gốc.

### 4. Local Development

Từ thư mục gốc repository, chạy toàn bộ ứng dụng bằng một lệnh:

```powershell
npm run dev
```

Hoặc chạy riêng từng dịch vụ:

```powershell
npm run dev:frontend
npm run dev:backend
```

Root npm scripts dùng lệnh `npm run dev` của frontend và launcher `scripts/dev_backend.py` của backend; cả hai server đều hỗ trợ hot reload. Launcher gọi FastAPI dev và chỉ theo dõi `backend/app`, nên sửa test không làm API reload. Trên Windows, backend chạy trong console riêng được ẩn, log vẫn chuyển về terminal hiện tại: tín hiệu `Ctrl+C` mà Uvicorn dùng khi reload không làm tắt Next.js trong console của `concurrently`. `backend/.env` được đọc như trước. PostgreSQL phải chạy sẵn (ví dụ `docker compose up -d postgres` ở bước 2). Nhấn `Ctrl+C` một lần để dừng cả hai dịch vụ. Chỉ mở một phiên `npm run dev`; sau khi cập nhật launcher, dừng các phiên cũ rồi chạy lại để áp dụng.

- Frontend: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000)
- Health: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- Swagger/OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

### 5. Luồng dùng thử đề xuất

1. Đăng ký/đăng nhập; có thể đặt mục tiêu tại **Profile**. ADMIN vào **Builder** → **New test**.
2. Mở Version 1 → tạo Reading, Listening, Writing và Speaking module; Full Mock mới cần đủ bốn kỹ năng.
3. Thêm passage, Listening parts/audio, Writing tasks và prompt Speaking cho ba phần.
4. Thêm question group bằng registry loại câu hỏi dùng chung.
5. Nhập câu hỏi và answer key ngay trong editor.
6. Bấm **Preview**, sau đó **Validate** và **Publish**.
7. Vào **Library** để bắt đầu Full Mock hoặc luyện riêng từng skill với timer tự chọn.
8. Trả lời, flag/highlight nếu cần; Speaking cần cho phép microphone và hoàn tất upload. Nộp bài rồi tiếp tục từng chặng Full Mock theo thứ tự Listening → Reading → Writing → Speaking.
9. Mở **History** → **Review** hoặc **Analytics** để xem kết quả và tiến trình.

## 🧪 Chạy kiểm thử

### Backend

```powershell
Set-Location backend
uv run ruff check . ../scripts
uv run ruff format --check app tests ../scripts
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

GitHub Actions chạy backend lint/format, Alembic và pytest; frontend typecheck, lint và Vitest. Workflow **Golden path E2E** build Next.js ở production mode và chạy ba luồng Listening, Writing, Full Mock trên Chromium. Trạng thái phụ thuộc từng commit; xem [GitHub Actions](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions) để kiểm tra kết quả hiện tại.

## 💾 Backup & Restore

Backup đầy đủ cần **cả PostgreSQL và `STORAGE_ROOT`**: database giữ tài khoản, đề, attempt/history và metadata/đường dẫn asset; file audio/hình nằm ngoài database. Công cụ này dùng mô hình **maintenance/offline**: dừng FastAPI hoặc ngăn mọi ghi dữ liệu, tạo dump, lưu storage, ghi manifest/checksum, rồi mới cho ứng dụng ghi trở lại. Dump và archive filesystem không phải snapshot nguyên tử khi ứng dụng vẫn đang ghi.

Cần `DATABASE_URL` trong `backend/.env` hoặc biến môi trường. CLI ưu tiên `pg_dump`/`pg_restore` trên `PATH`; với PostgreSQL local theo Docker Compose, nếu thiếu công cụ trên host, CLI tự dùng công cụ trong container `postgres` đang chạy. Khởi động bằng `docker compose up -d postgres` từ thư mục gốc repository. Sau đó, từ `backend/`:

```powershell
uv run python ../scripts/backup.py
# Kết quả: ../backups/<UTC-timestamp>-<suffix>/

uv run python ../scripts/restore.py ../backups/<UTC-timestamp>-<suffix> --confirm-destructive
```

Backup gồm `database.dump` (PostgreSQL custom format), `storage.tar.gz` (nội dung bên trong `STORAGE_ROOT`) và `manifest.json` với SHA-256 cho cả hai file. Restore xác minh checksum và đường dẫn archive trước khi thay thế. Thiếu `--confirm-destructive` thì restore từ chối và cho biết đích sẽ bị thay. **Dừng mọi ghi trong suốt restore.** Database được phục hồi bằng `pg_restore --clean --if-exists --no-owner` trong một transaction; storage được giải nén vào thư mục tạm trước khi đổi chỗ với thư mục hiện có. Hai tài nguyên không thể thay thế nguyên tử cùng lúc; nếu bước storage thất bại sau khi database đã phục hồi, giữ ứng dụng offline và chạy lại restore từ cùng backup. Một thư mục storage cũ có thể được giữ lại nếu không dọn được; CLI sẽ in vị trí để kiểm tra.

Restore giữ đúng schema đã lưu, không tự chạy migration. Nếu phục hồi backup cũ bằng phiên bản ứng dụng mới hơn, chạy `uv run alembic upgrade head` từ `backend/` sau restore và trước khi khởi động backend. Backup **không được mã hóa** bởi công cụ này và chứa dữ liệu riêng tư như tài khoản, lịch sử, đáp án, feedback và asset: giữ kín, bảo vệ như database, không commit/chia sẻ tùy tiện. `backups/` đã được gitignore.

Transfer ZIP chỉ mang **nội dung đề được chọn** để nhập/xuất, không có users hay attempt/history. Backup là cơ chế **khôi phục toàn ứng dụng** gồm PostgreSQL và binary storage; hai định dạng không thay thế cho nhau.

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

Binary không nằm trong PostgreSQL. Backend kiểm tra MIME, đuôi file, kích thước và tạo tên UUID cho asset đề trong `storage/audio` hoặc `storage/images`. Audio người học nằm trong `storage/speaking-private`, được kiểm tra quyền theo attempt/assignment; raw segment và các bản chuẩn hóa không phải asset đề công khai. Backup phải bao gồm toàn bộ `STORAGE_ROOT`, kể cả audio riêng tư và bản dẫn xuất.

### Quản trị tài khoản

ADMIN xem thống kê nền tảng, danh sách USER/TEACHER/ADMIN đang hoạt động hoặc đã vô hiệu hóa, nâng/hạ quyền và kích hoạt lại tài khoản. TEACHER giữ các quyền luyện tập của USER và có thêm Builder đề của mình, lớp học, bài giao và kết quả học sinh chỉ đọc theo nguồn bài giao. Hạ quyền/vô hiệu hóa Teacher yêu cầu xử lý lớp đang hoạt động, yêu cầu duyệt và bản nháp trước. Xóa vĩnh viễn tài khoản đã vô hiệu hóa bị chặn nếu có tham chiếu nội dung/lớp học/thông báo cần giữ lại.

Quy trình duyệt CLASSROOM/PUBLIC, lời mời qua email chưa có tài khoản, thông báo EN/VI và ranh giới riêng tư của kết quả: [docs/teacher-classrooms.md](docs/teacher-classrooms.md).

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

- **Hiện có:** đủ bốn kỹ năng Reading/Listening/Writing/Speaking, Full Mock bốn chặng, pause/resume theo policy từng kỹ năng, Writing thủ công và AI tham khảo Task 1/Task 2, Speaking recording/recovery/transcript/evidence/advisory AI và benchmark tooling, Builder autosave, Transfer ZIP, Draft Import CLI, History/Analytics, Personalization, xác thực/Profile/mục tiêu IELTS, quản trị tài khoản và Teacher/Classroom với duyệt nội dung, bài giao, kết quả chỉ đọc, thông báo trong ứng dụng.
- **Tiếp theo:** tăng độ sâu của analytics, accessibility và độ bền của Builder workflow.
- **Ngoài phạm vi hiện tại:** OCR tích hợp, thanh toán và chứng nhận điểm IELTS chính thức. AI chỉ hỗ trợ luyện tập; không có cam kết tăng band hay độ chính xác tương đương giám khảo.

Xem checklist chi tiết tại [docs/ROADMAP.md](docs/ROADMAP.md). 💫
