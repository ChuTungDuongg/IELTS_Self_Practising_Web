# BandPilot

<img src="frontend/public/brand/bandpilot-compass-ribbon.svg" alt="Logo BandPilot Compass Ribbon" width="64" height="64" />

**Practice smarter. Reach your band.**

BandPilot là nền tảng luyện IELTS cho **Reading, Listening, Writing và Speaking**: chọn bài luyện theo kỹ năng, làm bài thi thử, xem lại kết quả và theo dõi tiến trình. Giáo viên có không gian biên soạn đề, quản lý lớp học và giao bài; phản hồi AI tùy chọn hỗ trợ người học xem lại bài Writing và Speaking.

![Trang chủ BandPilot với các khối cầu xanh và thông điệp Practice with purpose, Progress with confidence](interface_screenshot/Screenshot%202026-10-29%20164718.png)

[Giao diện](#giao-diện) · [Tính năng](#tính-năng) · [Chạy cục bộ](#chạy-cục-bộ) · [Tài liệu kỹ thuật](#tài-liệu-kỹ-thuật) · [Liên hệ](#liên-hệ)

## Tính năng

| Không gian | Bạn có thể làm gì? |
| --- | --- |
| **Thư viện đề** | Tìm kiếm đề đã xuất bản, lọc theo kỹ năng và chọn bài luyện hoặc Full Mock. |
| **Luyện từng kỹ năng** | Chọn passage, phần nghe, Writing task hoặc phần Speaking; chọn thời lượng phù hợp với bài luyện. |
| **Làm bài và xem lại** | Lưu câu trả lời, đánh dấu câu hỏi, highlight, nộp bài và mở lại kết quả theo quyền và trạng thái bài làm. |
| **History và Analytics** | Theo dõi thời gian luyện, kết quả theo kỹ năng, xu hướng band và độ chính xác theo loại câu hỏi khi có dữ liệu phù hợp. |
| **Writing và Speaking AI** | Nhận phản hồi tham khảo theo tiêu chí; Speaking hỗ trợ ghi âm riêng tư, transcript và bằng chứng âm thanh khi được cấu hình. |
| **Builder và quản lý nội dung** | Biên soạn đề bốn kỹ năng, chỉnh đáp án, preview, validate, publish và nhập/xuất nội dung đề bằng ZIP. |
| **Lớp học** | Quản lý thành viên, bảng tin, nội dung học, bài tập, lịch, sổ điểm và phân tích tiến độ theo lớp. |
| **Tài khoản và cá nhân hóa** | Đăng nhập/đăng ký, Google OAuth tùy chọn, mục tiêu IELTS, giao diện sáng/tối và ngôn ngữ Việt/Anh. |

Quyền hiển thị và thao tác phụ thuộc vai trò **USER / TEACHER / ADMIN** cùng capability của từng lớp. Giáo viên chỉ được xem kết quả bài giao thuộc phạm vi được phép; bài luyện cá nhân vẫn có ranh giới riêng tư. ADMIN có các công cụ quản trị và duyệt nội dung, đồng thời quan sát lớp theo quyền đọc hiện hành.

## Giao diện

Bộ ảnh dưới đây do chủ dự án cung cấp ngày **29/10/2026**, lưu tại [`interface_screenshot/`](interface_screenshot/). Ảnh minh họa giao diện ở thời điểm chụp, với các màn hình tiếng Anh và tiếng Việt; các con số và danh sách đề trong ảnh là trạng thái dữ liệu tại thời điểm đó.

### Trang chủ: từ chọn kỹ năng đến sẵn sàng làm bài

Trang chủ chia thành các chương: bắt đầu luyện tập, chọn kỹ năng, nhìn lại tiến trình và chọn bài thi. Các khối cầu tạo chuyển động xuyên suốt; footer giữ wordmark BandPilot, marquee, liên kết điều hướng và hai nút điều khiển chuyển động.

<details>
<summary>Xem các chương tiếp theo và footer</summary>

**Chọn kỹ năng — Build every skill.**

![Chương chọn Reading, Listening, Writing và Speaking trên trang chủ BandPilot](interface_screenshot/Screenshot%202026-10-29%20164855.png)

**Nhìn lại tiến trình — See progress take shape.**

![Chương giới thiệu việc xem lại bài làm và tiến trình luyện tập](interface_screenshot/Screenshot%202026-10-29%20164947.png)

**Chuẩn bị làm bài — Find your focus. Feel test ready.**

![Chương chọn bài thi từ thư viện để luyện tập trong không gian tập trung](interface_screenshot/Screenshot%202026-10-29%20165129.png)

**Footer — Your next step starts here.**

![Footer BandPilot với wordmark lớn, marquee, điều hướng, Pause motion, Scatter spheres và liên hệ](interface_screenshot/Screenshot%202026-10-29%20165214.png)

</details>

### Đăng nhập và đăng ký

**“Dành chỗ cho tiến bộ.” / “Make room for progress.”** là thông điệp của không gian tài khoản. Minh họa bốn kỹ năng đi cùng form đăng nhập/đăng ký, nút hiện/ẩn mật khẩu và lựa chọn Google khi OAuth được cấu hình.

| Đăng nhập | Tạo tài khoản |
| --- | --- |
| ![Trang đăng nhập BandPilot với email, mật khẩu và Google OAuth](interface_screenshot/Screenshot%202026-10-29%20165408.png) | ![Trang tạo tài khoản BandPilot với tên, email và xác nhận mật khẩu](interface_screenshot/Screenshot%202026-10-29%20165439.png) |

### Thư viện và luyện từng kỹ năng

Thư viện tập hợp đề đã xuất bản, hỗ trợ tìm kiếm và lọc theo kỹ năng. Màn hình luyện từng kỹ năng chia nội dung thành các đơn vị nhỏ hơn để người học chọn bài và thời lượng.

![Thư viện đề với tìm kiếm, sắp xếp, thẻ đề và bộ lọc kỹ năng](interface_screenshot/Screenshot%202026-10-29%20165511.png)

<details>
<summary>Xem màn hình luyện từng kỹ năng</summary>

![Trang luyện từng kỹ năng với bộ lọc, danh sách bài đọc và lựa chọn thời lượng](interface_screenshot/Screenshot%202026-10-29%20165800.png)

</details>

### Chọn bố cục trước khi bắt đầu

Người học có thể xem trước bố cục **Luyện tập** hoặc **Legacy** trước khi tiếp tục vào bài. Nội dung trong phần preview là mẫu hư cấu được dùng để minh họa cách bố trí passage, câu hỏi, đồng hồ và thanh điều hướng.

![Hộp thoại chọn giao diện làm bài với hai bản xem trước Luyện tập và Legacy](interface_screenshot/Screenshot%202026-10-29%20165818.png)

### Biên soạn và quản lý đề

Không gian Builder hiển thị đề đang hoạt động/đã lưu trữ và trạng thái bản nháp/đã xuất bản. Người có quyền có thể tạo đề, chỉnh sửa nội dung và dùng công cụ nhập/xuất; nội dung đã publish được giữ trong phiên bản đóng băng để bảo toàn lịch sử bài làm.

![Không gian biên soạn đề IELTS với thống kê trạng thái và danh sách đề](interface_screenshot/Screenshot%202026-10-29%20165541.png)

### Không gian lớp học

Danh sách lớp kết hợp tìm kiếm, trạng thái lớp và lịch theo lớp được chọn. Bên trong lớp là bảng tin, nội dung học, bài tập, lịch, thành viên, sổ điểm và phân tích; trang tổng quan giúp theo dõi các số liệu và hoạt động của lớp.

![Danh sách lớp học với thẻ lớp, tìm kiếm, bộ lọc và lịch lớp học](interface_screenshot/Screenshot%202026-10-29%20165618.png)

<details>
<summary>Xem tổng quan và bảng tin lớp học</summary>

**Tổng quan lớp**

![Tổng quan lớp với học viên, bài tập, trạng thái nộp, hoạt động và tiến độ theo kỹ năng](interface_screenshot/Screenshot%202026-10-29%20165650.png)

**Bảng tin và bài giao**

![Bảng tin lớp với công cụ đăng thông báo, các tab học tập và bài tập được chia sẻ](interface_screenshot/Screenshot%202026-10-29%20165716.png)

</details>

## Kiến trúc và công nghệ

| Thành phần | Công nghệ / trách nhiệm |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4; App Router và HTTP clients có kiểu dữ liệu. |
| Backend | FastAPI, Pydantic v2, SQLAlchemy async; nghiệp vụ, phân quyền, timer và đánh giá câu trả lời. |
| Database | PostgreSQL 17; Alembic quản lý thay đổi schema. |
| Binary storage | File local hoặc S3/R2 theo cấu hình; PostgreSQL lưu metadata và tham chiếu. |
| AI tùy chọn | Adapter vLLM/OpenAI cho Writing/Speaking; faster-whisper cho ASR và FFmpeg cho chuẩn hóa audio Speaking. |
| Triển khai | Local development, Modal Web và template AWS EC2/Docker; các mode có cấu hình và ranh giới dữ liệu riêng. |
| Kiểm thử | Vitest, pytest, TypeScript, ESLint, Ruff và Golden Path E2E trong CI. |

```text
Trình duyệt ── Next.js
                  │ HTTP /api/v1
                  ▼
               FastAPI ── PostgreSQL
                  ├────── Asset storage: Local / S3 / R2
                  └────── AI providers tùy chọn
                          ├── Writing / Speaking LLM
                          └── Speaking ASR
```

Frontend không kết nối trực tiếp PostgreSQL. FastAPI quyết định quyền truy cập, deadline, trạng thái bài làm và kết quả chấm câu hỏi. Published `TestVersion` giữ nguyên nội dung; historical attempts luôn tham chiếu đúng phiên bản đã dùng. Đáp án không được gửi trong Active Exam DTO.

Modal demo chạy **Nginx + Next.js + FastAPI + PostgreSQL trong một Web CPU container**, nhận tối đa 8 HTTP inputs đồng thời và giữ `max_containers=1` để bảo vệ quyền sở hữu embedded PostgreSQL. Dịch vụ GPU phục vụ AI có lifecycle riêng. Xem [runtime architecture](docs/handbook/runtime-architecture.md) và [case study hiệu năng Modal](docs/case-studies/modal-web-performance.md) để hiểu topology và phạm vi kết quả staging đã đo.

## Chạy cục bộ

### Yêu cầu

- Python **3.12+** và [uv](https://docs.astral.sh/uv/).
- Node.js **20.9+**, npm và Docker Compose để chạy PostgreSQL.
- FFmpeg nếu sử dụng pipeline chuẩn hóa audio Speaking. ASR, AI grading và Google OAuth cần cấu hình riêng; không bắt buộc để bắt đầu với các luồng luyện tập không dùng chúng.

Các lệnh PowerShell sau chạy từ **thư mục gốc repository**, trên môi trường local riêng.

### 1. Tạo cấu hình

```powershell
Copy-Item backend/.env.example backend/.env
Set-Content frontend/.env.local 'NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1'
```

Trong `backend/.env`, đặt `JWT_SECRET` riêng, ít nhất **32 ký tự**. File mẫu dùng PostgreSQL local ở `localhost:5433`, frontend origin `http://localhost:3000` và `STORAGE_ROOT=../storage`. Giữ frontend và API cùng hostname `localhost` để cookie phiên hoạt động nhất quán. Không commit file `.env` hoặc thông tin đăng nhập thật.

### 2. Cài dependency và chuẩn bị database local

```powershell
docker compose up -d postgres
npm install
uv --directory backend sync --locked --group dev
uv --directory backend run alembic upgrade head
uv --directory backend run python -m app.seed
```

Root `npm install` chạy postinstall để cài frontend theo lockfile. Seed tạo nội dung mẫu hư cấu; chỉ chạy migration/seed sau khi kiểm tra `DATABASE_URL` đang trỏ đúng database local.

Để tạo ADMIN đầu tiên, đặt `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD`, `INITIAL_ADMIN_NAME` trong `backend/.env`, rồi chạy:

```powershell
uv --directory backend run python -m app.bootstrap_admin
```

### 3. Khởi động frontend và backend

```powershell
npm run dev
```

| Dịch vụ | Địa chỉ local |
| --- | --- |
| Frontend | [localhost:3000](http://localhost:3000) |
| FastAPI / OpenAPI | [localhost:8000/docs](http://localhost:8000/docs) |
| Liveness | [api/v1/health](http://localhost:8000/api/v1/health) |
| Readiness | [api/v1/ready](http://localhost:8000/api/v1/ready) |

Có thể chạy riêng bằng `npm run dev:frontend` và `npm run dev:backend`. PostgreSQL phải chạy sẵn; `Ctrl+C` dừng các tiến trình do lệnh dev quản lý.

### Luồng dùng thử

1. Đăng ký/đăng nhập; thiết lập mục tiêu IELTS và giao diện nếu muốn.
2. Vào **Thư viện đề** hoặc **Luyện từng kỹ năng**, chọn bài và bố cục làm bài.
3. Làm bài, lưu câu trả lời và nộp bài; Full Mock đi theo Listening → Reading → Writing → Speaking.
4. Mở **Lịch sử luyện tập** và **Thống kê** để xem lại kết quả phù hợp với dữ liệu đã chấm.
5. Với tài khoản có quyền, mở **Biên soạn đề** hoặc **Lớp học** để tạo nội dung và bài giao.

## Tài liệu kỹ thuật

[Engineering Knowledge Base](docs/README.md) là điểm bắt đầu cho cả người học kiến trúc hệ thống và người phát triển tính năng.

| Bạn cần tìm hiểu | Tài liệu |
| --- | --- |
| Tổng quan và ranh giới hệ thống | [System overview](docs/handbook/system-overview.md) · [Architecture](docs/architecture.md) |
| Process, ports và deployment modes | [Runtime architecture](docs/handbook/runtime-architecture.md) · [Infrastructure](docs/handbook/infrastructure.md) |
| Tìm code theo tính năng | [Module catalog](docs/handbook/module-catalog.md) · [API/model/page source map](docs/handbook/source-map.md) |
| Phát triển feature | [AGENTS.md](AGENTS.md) · [Feature playbook](docs/handbook/feature-development-playbook.md) |
| Database và tính nhất quán dữ liệu | [Data architecture](docs/handbook/data-architecture.md) |
| Writing / Speaking AI | [AI architecture](docs/handbook/ai-architecture.md) · [Writing](docs/ai-writing.md) · [Speaking](docs/ai-speaking.md) |
| Triển khai | [Modal](docs/modal-web.md) · [AWS EC2/Docker](docs/aws-deployment.md) |
| Di chuyển và khôi phục dữ liệu | [Storage migration](docs/storage-migration.md) · [Backup/restore](docs/storage-backup-restore.md) · [Transfer ZIP](docs/TEST_TRANSFER_FORMAT.md) |
| Kiểm thử, CI và bảo mật | [Testing and delivery](docs/handbook/testing-and-delivery.md) · [Security and reliability](docs/handbook/security-and-reliability.md) |
| Hiệu năng và phỏng vấn | [Modal case study](docs/case-studies/modal-web-performance.md) · [44 câu hỏi system design](docs/interview/bandpilot-system-design.md) · [Modal performance Q&A](docs/interview/modal-performance-qa.md) |
| Độ mới và phạm vi tài liệu | [Documentation audit](docs/DOCS_AUDIT.md) · [Coverage và giới hạn xác minh](docs/DOCUMENTATION_COVERAGE.md) |

Các hướng dẫn kỹ thuật mô tả cấu hình trong source; ảnh chụp không chứng minh trạng thái deployment hay CI hiện tại. Kết quả CI theo từng commit có tại [GitHub Actions](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions).

## Phạm vi và dữ liệu

- **AI là phản hồi tham khảo.** Kết quả objective do backend đánh giá; human final Writing/Speaking và phân quyền chấm được giữ riêng. Không có cam kết tăng band hoặc độ chính xác tương đương giám khảo.
- **Tôn trọng quyền sử dụng nội dung.** Tên đề hiển thị trong ảnh thuộc dữ liệu ở môi trường chụp; seed được commit là nội dung hư cấu. Chỉ nhập/xuất và sử dụng tài liệu mà bạn có quyền sử dụng.
- **Backup khác Transfer ZIP.** Backup cần cả PostgreSQL lẫn binary storage; Transfer ZIP chỉ mang nội dung đề được chọn, không thay bản sao lưu users, attempts hay bản ghi âm riêng tư.
- **Tên sản phẩm là BandPilot.** Repository, package và một số protocol vẫn giữ identifier `IELTS_Self_Practising_Web` / `devweblocalforielts` để tương thích.
- BandPilot là dự án độc lập, không liên kết chính thức với đơn vị tổ chức IELTS; điểm và phản hồi không phải chứng nhận IELTS. OCR tích hợp và thanh toán chưa thuộc các tính năng hiện có được mô tả ở đây.

## Liên hệ

[LinkedIn](https://www.linkedin.com/in/duongchunguyen/) · [Facebook](https://www.facebook.com/rendezvouss0344/) · [Zalo: 0367365703](https://zalo.me/0367365703)
