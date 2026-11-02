# Kế hoạch triển khai ngân hàng benchmark Writing quản trị

> **Kiểm toán tài liệu: HISTORICAL.** Tham khảo lịch sử, không phải hợp đồng hiện hành.
> Mục đích: kế hoạch triển khai ngân hàng benchmark Writing quản trị. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../../../backend/app/services/writing_benchmark.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/writing.md); [kiểm toán và giới hạn](../../DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong đợt kiểm toán này.

**Trạng thái:** triển khai được cho phép và thực hiện ngày 2026-10-13. Tác vụ 1–13 và chốt cục bộ Tác vụ 14 hoàn tất; chốt từ xa theo SHA đẩy cuối được kiểm trước khi báo hoàn tất. Xem [xác minh triển khai](../../writing-benchmark-bank.md#implementation-validation--2026-10-13).

**Mục tiêu:** thêm một ngân hàng dữ liệu chuẩn Writing riêng tư do ADMIN soạn, giới hạn 100 mẫu mỗi tác vụ, sửa nháp an toàn, tổng band suy từ sản xuất, hướng dẫn phân phối, ZIP xuất tương thích và CLI benchmark Task 2 ngoại tuyến.

**Đặc tả:** [thiết kế ngân hàng Writing đã phê duyệt](../specs/2026-10-13-writing-benchmark-bank-design.md). Phê duyệt của người dùng thay thế câu trạng thái cũ “đang chờ người dùng rà soát cuối” trong đặc tả.

**Kiến trúc:** một bảng mẫu benchmark, tuyến FastAPI mỏng chỉ ADMIN, repository/dịch vụ benchmark, `LocalAssetStorage` hiện có, trang quản trị danh sách/chi tiết riêng, chỉ số đánh giá điểm dùng chung và bộ đánh giá Task 2 ngoại tuyến riêng. Chấm sản xuất không đổi.

**Công nghệ:** FastAPI, SQLAlchemy async/PostgreSQL, Alembic, Pydantic, ZIP/CSV/tệp tạm thư viện chuẩn, Next.js/React, máy khách Zod hiện có, từ điển EN/VI, pytest và Vitest/Testing Library. Dự kiến không thêm phụ thuộc.

**Thực thi:** mười bốn tác vụ tuần tự, xác minh độc lập. Mỗi tác vụ RED → triển khai tối thiểu → GREEN → commit đúng phạm vi. Ô đánh dấu theo dõi triển khai tương lai; chưa thực hiện bước nào trong lần lập kế hoạch này. Không giao tác nhân hoặc gọi nhà cung cấp trực tiếp khi xác minh thường.

## Nền và bằng chứng đã kiểm tra

- Đã đồng bộ `main` sạch bằng `git fetch origin`, `git pull --ff-only origin main`, `git status --short`, `git log --oneline -12`.
- SHA đã xem: `7a39025ad201b672c81986721eac671c24da7d67` (`Document admin Writing benchmark bank design`). Đã đọc toàn bộ đặc tả 747 dòng.
- [Lượt CI 38392866057](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions/runs/38392866057) từ xa **hoàn tất / thành công** trên đúng SHA. [Lượt Golden path E2E 38392866113](https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web/actions/runs/38392866113) từ xa **hoàn tất / thành công**. Không thấy lỗi CI cũ; không có sửa mã nền trong lần này.
- Đọc `uv run alembic heads` từ `backend/`: đúng `20261013_0034 (head)`, cha là `20261013_0033`. Chỉ dành `20261013_0035_writing_benchmark_bank.py` / revision `20261013_0035` nếu đầu vẫn như vậy lúc triển khai; nếu đổi, tạo một revision mới sau đầu vừa kiểm.
- Khi lập kế hoạch không sửa tệp sản xuất, kiểm thử, lược đồ hoặc migration. Không chạy bộ kiểm cục bộ, trình duyệt, Playwright, suy luận trực tiếp hoặc triển khai.

### Điểm tái sử dụng thực tế

| Khu vực | Triển khai đã xem | Hệ quả cho kế hoạch |
| --- | --- | --- |
| Truy cập quản trị | `frontend/src/app/admin/layout.tsx`, `features/auth/admin-guard.tsx`, `admin-only.tsx`, `auth-provider.tsx`; `backend/app/api/dependencies.py::AdminUser`, `require_admin` | Tái sử dụng chốt máy chủ/máy khách và phụ thuộc ADMIN backend hiện có; không xác thực mới hoặc biến thể giáo viên. |
| API quản trị | `backend/app/api/v1/admin.py`, `api/v1/router.py`; `schemas/admin.py`, `services/admin.py` | Thêm router riêng dưới `/admin/writing-benchmark`; giữ router mỏng, giao dịch do dịch vụ sở hữu. |
| ORM/repository | `models/base.py`, `models/__init__.py`, `models/enums.py`, `models/entities.py`, `models/writing_ai.py`, `repositories/tests.py`, `repositories/writing_ai.py` | Dùng mixin UUID/dấu thời gian, ràng buộc có tên, cột Decimal, giao dịch rõ và đọc có khóa. Không gắn mẫu với lượt người học/phiên bản đề đóng băng. |
| Lược đồ kiểm thử | `backend/tests/conftest.py`, `test_focused_scope_migration.py`, `test_teacher_domain_models.py`, `test_subjective_grading.py` | Fixture chính dùng PostgreSQL/giao dịch hoàn tác với savepoint và áp migration gần đây có điều kiện. Tìm thấy kiểm siêu dữ liệu/ràng buộc, chưa có fixture `Base.metadata.create_all` hoặc bộ dựng lược đồ ORM SQLite hiện tại. Thêm đăng ký mô hình/bao phủ lược đồ rõ; không bịa hoặc viết lại fixture SQLite không tồn tại. |
| Lưu trữ | `storage/local.py`, `storage/__init__.py`, `api/v1/assets.py`, `services/tests.py::resolve_owned_or_inherited_asset`, `_delete_files` | `store`/`store_file` chỉ chọn MIME hình khi `category="images"`; nhóm lồng tùy ý hiện dùng quy tắc âm thanh. Mở có chủ đích cùng lớp lưu trữ. Tài sản chung cần `test_version_id`; hình benchmark không thành dòng `Asset` chung hoặc kế thừa truy cập đề. |
| Trả ZIP | `api/v1/transfer.py`, `frontend/src/lib/api/transfer.ts` | Dùng ZIP tạm + `FileResponse` xác thực + dọn dẹp và quy ước tải nhị phân `apiResponse` hiện có. Dựng trên đĩa, không `BytesIO` backend có thể tới gigabyte. |
| Phép tính Writing | `domains/scoring/writing.py::validate_writing_criterion_score`, `calculate_task_overall`; `ai_writing.py::aggregate_ai_task_two`; `ielts_band.py::round_to_half` | Suy trung bình bốn tiêu chí và nửa band làm tròn của bài đơn qua hàm sản xuất. Không áp trọng số toàn mô-đun Task 1/Task 2 vào mẫu đơn. |
| Đánh giá Task 1 | `evaluation/task1/models.py`, `manifest.py`, `metrics.py`, `runner.py`, `report.py`, `scripts/benchmark_task1.py`, `test_task1_benchmark_metrics.py`, `test_task1_benchmark.py` | Kiểm trực tiếp JSONL xuất bằng `BenchmarkSample` hiện hành; tách chỉ số điểm, không chuyển logic nhận thức. Giữ ngữ nghĩa có kiểu cho tiếp tục/lần thử/lỗi. |
| Danh tính bộ chấm hiện tại | Task 1 tổng hợp/chấm v12, thị giác v3; `mts_prompts.py::AI_WRITING_PROMPT_VERSION` / `effective_prompt_version` cho Task 2 v12; `services/mts_writing.py::MTSWritingScoringService.assess`, `_assess_task2_criterion` | Benchmark Task 2 gọi dịch vụ sản xuất: chỉ điểm → bằng chứng → nhận xét, có độ liên quan và giới hạn đồng thời. Điểm đích người chấm không vào `WritingScoringRequest`. Không đổi phiên bản lời nhắc/hiệu chuẩn cho tính năng. |
| Chưa có benchmark Task 2 | Đã tìm `backend/app/evaluation/`, `scripts/`, `benchmarks/` | Chưa có CLI/gói benchmark Task 2 riêng. `evaluation/task1/legacy_task2_v6.py` là phụ thuộc đánh giá Task 1 đóng băng, không phải bộ chạy Task 2 hiện hành. |
| Hợp đồng frontend | `lib/api/client.ts::{apiRequest,apiResponse,ApiError}`, `admin.ts`, `assets.ts`, `server-client.ts` | Dùng DTO kiểm bằng Zod, yêu cầu theo cookie/phiên, `ApiError.details`, tải multipart, xuất nhị phân. Frontend không truy cập PostgreSQL. |
| Tự lưu/hộp thoại | `features/test-builder/builder-lifecycle.tsx::{BuilderLifecycleProvider,useBuilderAutosave}`, `writing-builder.tsx`, `autosave-link.tsx`, `components/ui/confirm-dialog.tsx` | Dùng cơ chế tự lưu/đẩy hết cấu hình được 1000 ms và hộp thoại hiện có. Hook hỗ trợ ngữ cảnh vòng đời tùy chọn; provider có thể cấp trạng thái/chốt đẩy hết ngoài Builder. Không dùng trạng thái `beginDelete` vĩnh viễn cả bản nháp để xóa một dòng ngân hàng. |
| UI/i18n | `features/auth/admin-content.tsx`, `components/ui/page-heading.tsx`, `app/globals.css`, `lib/i18n/{en,vi,types}.ts`, `features/writing/task-types.ts` | Giữ bề mặt quản trị BandPilot/ngữ nghĩa Writing. Thêm CSS riêng trang, nhãn EN/VI; dùng ID loại Task 1, không dùng nhãn hiện chỉ tiếng Anh. |
| CI | `.github/workflows/ci.yml` | CI kiểm mã/định dạng từ `backend/`, gồm `../scripts`, rồi migration PostgreSQL mới, một đầu và toàn bộ kiểm backend; frontend kiểm kiểu/mã/đơn vị. Kiểm cục bộ có mục tiêu phải cùng thư mục/cấu hình backend. |

`benchmarks/writing_task1/README.md` vẫn mô tả v11 dù CLI hiện v12. Sửa tham chiếu ở Tác vụ 13; đây là lệch tài liệu, không phải lỗi CI phát hiện. `pie_chart` chữ thường minh họa trong đặc tả không là enum hiện tại: xuất `PIE_CHART`/giá trị registry chuẩn, kiểm theo mô hình thay vì chép ví dụ nguyên xi.

## Quyết định triển khai trong thiết kế đã duyệt

1. **Một bảng và vị trí ổn định.** `WritingBenchmarkSample` dùng UUID, `(task_number, sequence_number)` duy nhất, tác vụ `1|2`, vị trí `1..100`. Chỉ ràng buộc này đã ngăn vượt 100 dòng mỗi tác vụ. Khóa tư vấn PostgreSQL theo tác vụ trong giao dịch làm cấp vị trí trống nhỏ nhất/lỗi đầy dung lượng tất định khi cạnh tranh, kể cả ngân hàng rỗng. Xóa có thể trả vị trí; mã lân cận không đổi. Nháp/hoàn tất đều chiếm dung lượng.
2. **Chỉ revision sửa kỹ thuật.** Thêm số nguyên nội bộ `revision` để tự lưu lạc quan an toàn theo `expected_revision`/`advance_revision` của Builder. Đây là mã đồng thời của dòng, không phiên bản ngân hàng/dữ liệu, bảng lịch sử hoặc bộ chọn phiên bản. Máy chủ quản lý số tác vụ/vị trí/UUID/khóa hình; PATCH không đổi được. Khóa dòng + revision bảo vệ PATCH, Hoàn tất, đổi hình, Xóa.
3. **Vòng đời nháp/hoàn tất.** Tạo luôn DRAFT, mặc định DEV, đề/bài trống, nhãn null. PATCH giữ đúng chuỗi nhập, cho nội dung thiếu; điểm/loại có gửi luôn được kiểm. Chỉ giữ COMPLETE khi đủ điều kiện, sửa làm mất hợp lệ hạ về DRAFT. Hoàn tất rõ ràng kiểm revision đã lưu mới nhất, từ chối thiếu bằng lỗi đường dẫn trường an toàn. Gỡ hình hạ Task 1 về DRAFT nguyên tử. Tự lưu không tự hoàn tất.
4. **Nhãn/tổng.** Lưu `human_ta_tr`, `human_cc`, `human_lr`, `human_gra` có thể null, đúng nửa band sản xuất; UI ghi TA/TR theo tác vụ. Dùng PostgreSQL Numeric không ấn định số lẻ, kiểm khoảng/mod để không ép 6.49 sai thành 6.5 có vẻ hợp lệ trước kiểm. Suy `human_overall` có thể null trong DTO/tóm tắt/CSV bằng `aggregate_ai_task_two`, không lưu. Xuất `ta` Task 1, `tr` Task 2. Mọi 0–9 hợp lệ dù hướng dẫn phân phối bắt đầu 4.0.
5. **Giới hạn trường.** Khớp bản kê Task 1 chuẩn: đề 20,000 ký tự, bài 100,000, ghi chú nguồn 2,000. Kiểm không trống bằng `.strip()`, không sửa chuỗi lưu. Giới hạn ngữ cảnh nhà cung cấp vẫn áp ngoại tuyến; đầu vào suy luận quá lớn báo lỗi rõ, không âm thầm cắt hoặc đổi chính sách sản xuất.
6. **Khóa hình riêng tư bất biến.** Dùng `LocalAssetStorage` với hàm phạm vi hẹp `store_benchmark_writing_image(sample_id, ...)`. Đường dẫn `benchmark/writing/task1/<sample-uuid>/<fresh-asset-uuid>.<ext>` để thay đồng thời không ghi đè cùng tệp. Dùng chốt MIME/phần mở rộng/kích thước/chữ ký ảnh tin cậy hiện có; trần `min(max_image_upload_mb, 10)` MiB khớp `ImagePart` Task 1 CLI. API không nhận khóa/đường dẫn ảnh. Kiểm không gian tên/quyền mẫu trước phân giải/xóa/xuất.
7. **Thứ tự dọn.** Ghi tệp mới duy nhất, chốt cập nhật dòng có khóa, rồi cố gắng xóa tệp cũ thuộc sở hữu. Lỗi giao dịch chỉ dọn tệp mới chắc chắn chưa chốt. Hủy/mất ACK chốt không được xóa tài sản có thể đã chốt; dùng mẫu thay đổi/checkpoint bền vững hiện có, ưu tiên giữ tệp mồ côi an toàn hơn phá dữ liệu đã chốt. Xóa/gỡ chốt DB trước dọn tệp cũ. Không hệ dọn mới hoặc tác vụ benchmark nền.
8. **Ranh giới API.** Router mới `api/v1/writing_benchmark.py` tiền tố `/admin/writing-benchmark`, ADMIN mọi tuyến: tóm tắt, danh sách/tạo, chi tiết/PATCH/xóa, `POST /samples/{id}/complete` rõ ràng, hình POST/GET/DELETE, GET xuất. Danh sách/tóm tắt bỏ bài/đề/khóa thô. Lỗi Hoàn tất dùng `{code,message,errors:[{path,message}]}` thuộc benchmark, tương thích `ApiError.details`, không đổi lỗi toàn cục.
9. **Hướng dẫn tóm tắt.** Trả tổng/nháp/hoàn tất theo tác vụ, số phần chia hoàn tất, đủ 19 ô nửa band tổng. Đích gợi ý đúng 4.0→8, 4.5→8, 5.0→9, 5.5→10, 6.0→11, 6.5→12, 7.0→12, 7.5→10, 8.0→8, 8.5→6, 9.0→6 (tổng 100), DEV 80/HOLDOUT 20. Chỉ là tư vấn. Hiện số band thấp thật, không bịa hạn ngạch; chỉ tính phân phối dòng COMPLETE. Biểu đồ tiêu chí hoãn P1.
10. **Xuất ảnh chụp.** Đọc COMPLETE theo tác vụ/vị trí ổn định dưới khóa đọc chung khi chuẩn bị hình bất biến/gói, để thay/xóa không gỡ tệp đang chép. ZIP/tệp chặn chạy ngoài vòng lặp sự kiện, luồng worker không dùng phiên SQLAlchemy. Thả khóa khi ZIP tạm xong. Tài sản COMPLETE thiếu/sai khiến xuất lỗi an toàn; không bịa byte hoặc bỏ âm thầm dòng hoàn tất sai. Ngân hàng rỗng/một phần vẫn xuất.
11. **Hợp đồng gói.** Luôn sáu tệp gốc quy định cộng `images/`; tên hình ổn định từ mã sinh/phần mở rộng đã kiểm. JSONL là chuẩn, nhãn người chấm dạng số, `raters=1`, nguồn gốc dự phòng an toàn không trống `admin-labelled benchmark sample`, không phân phối lại trừ khi đặt rõ, dữ liệu thị giác chuẩn null. Dùng trích dẫn `csv` thư viện chuẩn cho đúng nội dung nhiều dòng. Sinh lược đồ chung từ hai mô hình Pydantic thật (ví dụ hợp `TypeAdapter`) để tham chiếu `$defs` hợp lệ. Không bộ đọc CSV/trường phiên bản ngân hàng.
12. **Bộ đánh giá Task 2.** Tách hợp đồng/bản kê/bộ chạy/báo cáo/CLI; dùng `MTSWritingScoringService` sản xuất, danh tính lời nhắc có hiệu lực hiện tại, `paragraph_mode="textarea"`. Chỉ bộ tiếp hợp đánh giá ánh xạ `ta` xuất từ sản xuất thành `tr` báo cáo. Mẫu tuần tự; bộ giới hạn nhà cung cấp sản xuất chặn yêu cầu tiêu chí mỗi mẫu. CLI có `--max-concurrent-llm-requests 1..4`; không nhân mức đồng thời bằng worker mẫu song song.
13. **Tiếp tục ngoại tuyến/lỗi.** Chỉ tách nguyên thủy checkpoint/bộ đếm nhỏ không nội dung cần cho hai bộ đánh giá, giữ nhập/hành vi Task 1. Danh tính gồm nội dung/nhãn/phần chia, nhà cung cấp/mô hình, điểm cuối băm, lời nhắc có hiệu lực, cấu hình liên quan, nguồn gốc đoạn, hợp đồng/băm triển khai. Lần thành công đã kiểm có thể tiếp tục; lỗi/hỏng/điểm không nhất quán chỉ thử lại ở lần chạy tiếp được yêu cầu. Giữ lần thử/chi phí lũy kế. Báo cáo chứa ID/điểm/trạng thái, không bài/đường dẫn/bí mật/lỗi thô.
14. **Luồng frontend.** Ngân hàng ngoài Workspace/Builder, tái sử dụng tự lưu. Dùng `delay=1000`, trình soạn mẫu được chọn theo UUID, ACK bền trước đổi chọn/thẻ/Hoàn tất và kế/hình/xuất, giữ nháp cục bộ sau lỗi/xung đột. Tắt sửa khi chuyển rõ; phản hồi muộn không ghi đè chữ mới hoặc mẫu khác. Ctrl/Cmd+S đẩy hết; Ctrl/Cmd+Enter đẩy hết, hoàn tất rồi chọn dòng chưa hoàn tất đã lưu kế tiếp chỉ khi thành công. Không dựng 200 biểu mẫu.

## Quy ước xác minh các tác vụ dưới đây

- Lệnh là **lệnh triển khai tương lai**, không khẳng định đã chạy. Backend từ `backend/`, frontend từ `frontend/`, Git từ gốc kho mã.
- Bao phủ tích hợp/migration/cạnh tranh cần đặt cả `DATABASE_URL`, `TEST_DATABASE_URL` tới PostgreSQL kiểm thử cô lập rõ ràng. Không đặt lại/migration sản xuất. Fixture hoàn tác thường không hợp cạnh tranh nhiều kết nối thật vì giao dịch ngoài giữ khóa tư vấn; Tác vụ 2 cấp lược đồ PostgreSQL tạm/phiên độc lập kèm dọn.
- Viết khẳng định hồi quy trước. RED phải thể hiện hành vi thiếu, không lỗi thiết lập không liên quan; dùng API 404, khẳng định thiếu mô hình/bảng hoặc nhập trong từng kiểm cho mô-đun chưa có.
- Không chạy toàn bộ kiểm cục bộ trong lặp thường, trình duyệt/Playwright/E2E, máy chủ dev, bản dựng sản xuất, LLM/ASR/GPU trực tiếp, Modal/dịch vụ mới. Kiểm giả tập trung xác lập hợp đồng/kết nối, không đo độ chính xác.
- Kiểm lại main/head trước triển khai, ghi lỗi nền từ xa mới. Không bắt đầu tính năng trên hồi quy nền chưa giải thích. Lần lập kế hoạch không sửa mã sản xuất.

---

### Tác vụ 1: Tách chỉ số điểm Writing dùng chung, không đổi Task 1

**Tệp:**

- Tạo `backend/app/evaluation/writing/__init__.py` và `metrics.py`.
- Tạo `backend/tests/test_writing_benchmark_metrics.py`.
- Sửa `backend/app/evaluation/task1/metrics.py` và `backend/tests/test_task1_benchmark_metrics.py`.
- Sửa `backend/app/evaluation/task1/runner.py`, `backend/tests/test_task1_benchmark.py` để bao phủ phụ thuộc chung mới trong danh tính bộ nhớ đệm.

**Giao diện:** chuyển nguyên `score_metrics(pairs, *, minimum_qwk_samples=10)` vào mô-đun chung. Mở `overall_score(scores, *, traits=("ta","cc","lr","gra"))` dùng tổng hợp sản xuất; Task 2 có thể cấp `("tr","cc","lr","gra")`. Tái xuất rõ cả hai từ Task 1 để tương thích nhập. Giữ hàm nhận thức/`perception_metrics` ở Task 1. Không đổi chỉ số Speaking hoặc thêm tương quan.

- [x] **Kiểm RED:** nhập chung/bí danh Task 1 tương đương; tính tay chính xác/±0.5/±1/độ lệch/MAE/RMSE/QWK; đủ 19 ô; rỗng/quá nhỏ/phương sai 0; giữ phép tính ngoài nửa band, không lượng tử hóa nhãn QWK; ánh xạ tổng Task 1/2, làm tròn điểm giữa của sản xuất. Kiểm băm phụ thuộc hiện có phải phát hiện sửa tệp chỉ số mới tách.
- [x] **Lệnh RED:** `uv run pytest tests/test_writing_benchmark_metrics.py tests/test_task1_benchmark_metrics.py -q`.
- [x] **Triển khai tối thiểu:** chỉ chuyển phép điểm, tham số hóa chọn tiêu chí tổng, giữ khóa chỉ số/trạng thái QWK/số tối thiểu. Mở mẫu `implementation_hash()` Task 1 với `evaluation/writing/*.py`; hiện chỉ gồm `evaluation/task1/*.py` cho mã đánh giá. Không QWK thứ hai.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_writing_benchmark_metrics.py tests/test_task1_benchmark_metrics.py tests/test_task1_benchmark.py -q`.
- [x] **Commit:** `Share Writing benchmark score metrics`.

### Tác vụ 2: Thêm mô hình mẫu duy nhất, migration và repository an toàn cạnh tranh

**Tệp:**

- Tạo `backend/app/models/writing_benchmark.py`.
- Sửa `backend/app/models/enums.py` và `backend/app/models/__init__.py`.
- Tạo `backend/alembic/versions/20261013_0035_writing_benchmark_bank.py` (xác nhận lại cha trước).
- Tạo `backend/app/repositories/writing_benchmark.py`.
- Tạo `backend/tests/benchmark_helpers.py`, `test_writing_benchmark_models.py`, và `test_writing_benchmark_migration.py`.
- Chỉ sửa `backend/tests/conftest.py` cho nhánh lược đồ hoàn tác có điều kiện mới; không thay fixture giao dịch/xác thực.

**Giao diện:** `WritingBenchmarkSample`, `WritingBenchmarkStatus`, `WritingBenchmarkSplit`; repository `lock_task_capacity(task_number)`, `allocate_slot(task_number)`, `get(sample_id, lock=False)`, `list_rows(task_number)`, `complete_rows(lock_shared=False)`, `summary_labels()`. Dùng `pg_advisory_xact_lock(namespace, task_number)` không gian tên cố định trong giao dịch tạo/xóa; khi cần cả hai, luôn khóa dung lượng trước khóa dòng mẫu.

- [x] **Kiểm RED:** đăng ký mô hình trong `Base.metadata`; ràng buộc có tên duy nhất/tác vụ/vị trí/loại/nửa band/COMPLETE/revision; nhãn DRAFT null; không cột tổng; Task 2 từ chối trường Task 1; SQL trực tiếp không cấp vị trí 101/trùng/nhãn 6.3 hoặc 6.49/COMPLETE sai; mã ổn định, tái dùng chỗ trống UUID mới. Nâng/hạ/nâng migration thật chỉ chạm bảng/kiểu mới.
- [x] **Lệnh RED:** `uv run pytest tests/test_writing_benchmark_models.py tests/test_writing_benchmark_migration.py -q`.
- [x] **Triển khai tối thiểu:** một bảng UUID/dấu thời gian, vị trí, tác vụ, trạng thái/phần chia, đúng đề/bài, loại/khóa Task 1 null, bốn nhãn Numeric null, ghi nguồn hữu hạn, mặc định không phân phối lại, revision kỹ thuật không âm. Phản chiếu quy tắc lược đồ/dịch vụ trong SQL có tên khi được. Đóng băng loại Task 1 cho phép trong migration; không nhập registry chạy có thể đổi vào migration lịch sử.
- [x] **Fixture cạnh tranh:** hàm tạo lược đồ PostgreSQL tạm duy nhất trên DB kiểm rõ và kết nối chốt độc lập; áp migration mới thật. Không dùng kết nối hoàn tác chung hoặc `Base.metadata.create_all` toàn bảng để kiểm tranh chấp. Dọn trong `finally`; báo bỏ qua là giới hạn, không đạt.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_writing_benchmark_models.py tests/test_writing_benchmark_migration.py -q`; kiểm một đầu bằng `uv run alembic heads`. Tác vụ 14 còn yêu cầu nâng đầy đủ trên DB PostgreSQL kiểm rỗng riêng.
- [x] **Commit:** `Add Writing benchmark sample persistence`.

### Tác vụ 3: CRUD chỉ ADMIN, dung lượng và hoàn tất rõ ràng

**Tệp:**

- Tạo `backend/app/schemas/writing_benchmark.py`.
- Tạo `backend/app/services/writing_benchmark.py`.
- Tạo `backend/app/api/v1/writing_benchmark.py` và sửa `backend/app/api/v1/router.py`.
- Tạo `backend/tests/test_writing_benchmark_api.py` và `test_writing_benchmark_capacity.py`.
- Mở rộng `backend/tests/benchmark_helpers.py` với mẫu ngân hàng hư cấu và máy khách theo vai trò.

**Giao diện:** `BenchmarkSampleCreate`, `BenchmarkSamplePatch`, `BenchmarkSampleDetail`, `BenchmarkSampleListItem`, `BenchmarkMutation(expected_revision)`, `BenchmarkCompletionFailure`; `WritingBenchmarkService.create/patch/complete/delete/detail/list`. `completion_issues(sample)` trả lỗi đường dẫn trường an toàn. Dùng kiểm điểm/loại sản xuất và revision; DTO điểm/tổng dạng số có thể null, không chuỗi Decimal. Thêm tuyến nêu trên; hình/xuất/tóm tắt ở tác vụ sau.

- [x] **Kiểm RED:** ADMIN thành công; vô danh 401, USER/TEACHER 403 gọi trực tiếp; lưu DRAFT rỗng/thiếu; giữ đúng CRLF/emoji/khoảng trắng; từ chối nhãn sai/ngoài khoảng/không hữu hạn/6.3; từ chối trường máy chủ lạ/giả; tác vụ/vị trí bất biến; Task 1 thiếu hình không hoàn tất; Task 2 cần đủ nhãn; tổng khớp sản xuất tại điểm giữa; sửa COMPLETE sai hạ nháp; revision cũ bị từ chối không ghi đè.
- [x] **RED dung lượng:** lấp 100 kể cả DRAFT; lần 101 trả 409 an toàn. Hai tạo cạnh tranh ở 99 qua giao dịch độc lập: một thành công, một đầy, đúng 100 dòng. Cạnh tranh tạo đầu phải khác vị trí/UUID. Xóa 37 không đánh lại 38; mẫu mới dùng lại 37 UUID mới. Task 2 độc lập.
- [x] **Lệnh RED:** `uv run pytest tests/test_writing_benchmark_api.py tests/test_writing_benchmark_capacity.py -q`.
- [x] **Triển khai tối thiểu:** router dùng `AdminUser`; dịch vụ sở hữu begin/khóa/kiểm/flush/commit. Hoàn tất rõ riêng với PATCH thiếu. Mẫu thành công Task 1 tạo hình riêng hợp lệ do backend quản; PATCH công khai không nhận đường dẫn. Lỗi hoàn tất chỉ thông điệp cố định/đường dẫn trường, không nội dung gửi/SQL/nội bộ nhà cung cấp. Ghi nguồn mặc định null; không lược đồ tài khoản tác giả/người chấm.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_writing_benchmark_api.py tests/test_writing_benchmark_capacity.py -q`.
- [x] **Commit:** `Add admin Writing benchmark authoring API`.

### Tác vụ 4: Vòng đời hình Task 1 riêng tư qua kho hiện có

**Tệp:**

- Sửa `backend/app/storage/local.py` (và `storage/__init__.py` chỉ khi cần xuất).
- Mở rộng `backend/app/services/writing_benchmark.py` và `api/v1/writing_benchmark.py`.
- Tạo `backend/tests/test_writing_benchmark_images.py`, mở rộng `benchmark_helpers.py`.
- Sửa `backend/tests/test_storage.py` kiểm hành vi hình/âm thanh chung không đổi; hồi quy nhân bản hiện ở `backend/tests/test_asset_cloning.py`.

**Giao diện:** `LocalAssetStorage.store_benchmark_writing_image(sample_id, mime_type, original_name, content, max_bytes)`, tái dùng hẹp nội bộ đích/kiểm hình, dịch vụ `replace_image/remove_image/image_content`. `owns_image_key(sample_id,key)` riêng bảo vệ mọi phân giải/dọn/xuất. Đổi hình cần `expected_revision`; tải multipart `file` và revision. GET hình trả `FileResponse` xác thực, tên an toàn từ mã, `Cache-Control: no-store`.

- [x] **Kiểm RED:** PNG/JPEG/WebP hợp lệ gồm phần mở rộng JPEG tương thích; từ chối giả/sai MIME/phần mở rộng/chữ ký, tệp rỗng/quá lớn, hình Task 2; không gian tên bất biến sinh máy chủ; DTO không khóa thô, vô danh/Asset chung không truy cập; cấm vai trò GET/POST/DELETE. Thiếu tệp chặn Hoàn tất. Gỡ hình hạ COMPLETE nguyên tử. Thay giữ ảnh cũ nếu cập nhật DB lỗi, chỉ xóa tệp mới chưa chốt; dọn sau chốt không xóa ảnh hiện tại. Cạnh tranh thay/gỡ/xóa, revision cũ/mất ACK. Khóa vượt đường dẫn/liên kết tượng trưng/tài sản khác không phục vụ hoặc xóa được.
- [x] **Lệnh RED:** `uv run pytest tests/test_writing_benchmark_images.py -q`.
- [x] **Triển khai tối thiểu:** giữ hành vi hình/âm thanh; không truyền thư mục benchmark như `category` chung. Thêm một đường dẫn máy chủ kiểm soát trong `LocalAssetStorage`, tái dùng chốt/chữ ký ảnh tin cậy. Đọc tối đa giới hạn+1 byte. Khóa/kiểm revision và đúng thứ tự dọn đã duyệt. I/O qua lớp kho hiện có, chẩn đoán an toàn hữu hạn khi dọn cố gắng thất bại.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_writing_benchmark_images.py tests/test_storage.py tests/test_asset_cloning.py -q`.
- [x] **Commit:** `Add private Writing benchmark image lifecycle`.

### Tác vụ 5: Tóm tắt nhẹ và hướng dẫn phân phối

**Tệp:**

- Mở rộng `backend/app/schemas/writing_benchmark.py`, `repositories/writing_benchmark.py`, `services/writing_benchmark.py`, và `api/v1/writing_benchmark.py`.
- Tạo `backend/tests/test_writing_benchmark_summary.py`.

**Giao diện:** `BenchmarkBankSummary`, `BenchmarkTaskSummary`; `summary_labels()` chỉ chọn tác vụ/trạng thái/phần chia/bốn điểm; `summary()` tính số lượng/biểu đồ làm tròn sản xuất. `GET /summary` chỉ ADMIN. Hằng hướng dẫn ở miền/dịch vụ benchmark, không quy tắc chấm mới.

- [x] **Kiểm RED:** nháp chiếm dung lượng nhưng không tính biểu đồ/phần chia hoàn tất; không dữ liệu; cô lập từng tác vụ; band thấp/cao hợp lệ và làm tròn sản xuất; tổng đích đúng 100, chia 80/20; không hạn ngạch chặn lưu/Hoàn tất; tóm tắt/danh sách không đề/bài/khóa ảnh; cấm vai trò.
- [x] **Lệnh RED:** `uv run pytest tests/test_writing_benchmark_summary.py -q`.
- [x] **Triển khai tối thiểu:** trả số thật trong 19 ô hữu hạn, đích gợi ý từng band có thể null; tổng/nháp/hoàn tất và DEV/HOLDOUT hoàn tất. Không nạp toàn bài, đệm tổng trùng hoặc bắt buộc biểu đồ tiêu chí.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_writing_benchmark_summary.py tests/test_writing_benchmark_api.py -q`.
- [x] **Commit:** `Add Writing benchmark distribution summary`.

### Tác vụ 6: Định nghĩa hợp đồng JSONL Task 2 nghiêm trước xuất

**Tệp:**

- Tạo `backend/app/evaluation/task2/__init__.py`, `models.py`, và `manifest.py`.
- Tạo `backend/tests/test_task2_benchmark_contracts.py`.

**Giao diện:** Task 2 `HumanScores(tr,cc,lr,gra)`, `BenchmarkSample`, `BenchmarkConfig`, `EvaluationRecord`, `LoadedSample`, `load_manifest(path,split,limit)`, lỗi mã cố định an toàn `BenchmarkInputError`. `schema_version: 1` chỉ là định dạng, ID ASCII an toàn, đề/bài đúng hữu hạn, nửa band, siêu dữ liệu một người chấm, nguồn không trống, bool phân phối lại nghiêm. Không trường hình/thị giác/chuyên đọc. Bản hoàn tất cần đủ bốn dự đoán hợp lệ; bản lỗi có thể giữ tiêu chí xong và phải giữ lỗi; suy hai tổng qua phép chung sản xuất.

- [x] **Kiểm RED:** từ chối trường dư/thị giác/điểm không nhất quán, nửa band sai, nhãn thiếu; Task 2 dùng `tr`, không `ta` bản kê; chuỗi đúng, chia/giới hạn/ID trùng, giới hạn tệp/chẩn đoán an toàn, từ chối trống, không đọc CSV. Nhãn số/mặc định lược đồ khứ hồi. Danh tính có lời nhắc Task 2/mô hình/cấu hình chạy, không bí mật điểm cuối; phiên bản định dạng không thành siêu dữ liệu ngân hàng.
- [x] **Lệnh RED:** `uv run pytest tests/test_task2_benchmark_contracts.py -q`.
- [x] **Triển khai tối thiểu:** hợp đồng chỉ văn bản và bộ nạp JSONL cục bộ riêng, giới hạn như Task 1. Giữ `BenchmarkSample`/cấu hình lịch sử Task 1. Không nhập worker API/DB chỉ để tạo mẫu/tính danh tính.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_task2_benchmark_contracts.py tests/test_task1_benchmark.py -q`.
- [x] **Commit:** `Define Task 2 Writing benchmark manifests`.

### Tác vụ 7: Xuất ZIP/JSONL tương thích tất định và CSV tiện xem

**Tệp:**

- Tạo `backend/app/services/writing_benchmark_export.py`.
- Mở rộng `backend/app/api/v1/writing_benchmark.py` và truy vấn ảnh chụp xuất của repository.
- Tạo `backend/tests/test_writing_benchmark_export.py`.

**Giao diện:** `WritingBenchmarkExportService.export(path)`; hàm thuần `task1_manifest_sample(row,image_path)`, `task2_manifest_sample(row)`, `write_csv(rows,task_number)`, `manifest_schema()`. GET `/export` trả `writing-benchmark.zip`, dùng tệp tạm/dọn nền hiện có. Ánh xạ Task 1 khởi tạo CURRENT `evaluation.task1.models.BenchmarkSample`, không lược đồ xuất song song. Task 2 dùng mô hình Tác vụ 6.

- [x] **Kiểm RED:** xuất 0/1/<100 mẫu; bỏ nháp; đúng sáu tệp gốc + `images/`; thứ tự tác vụ/vị trí/mã/tên ảnh ổn định; dòng Task 1 kiểm trực tiếp mô hình/`load_manifest` hiện tại với hình sinh; dòng Task 2 qua bộ nạp riêng. Luôn raters=1, mặc định không phân phối lại, thị giác chuẩn null, nguồn dự phòng trung lập không trống không bịa giấy phép. Decimal nửa band thành số JSON. CSV trích dấu phẩy/nháy/nhiều dòng CRLF/Unicode giữ đúng nội dung/tổng suy.
- [x] **RED an toàn:** khóa vượt đường dẫn/tuyệt đối/kho khác và tên tệp ác ý không thành mục ZIP/lộ tệp khác; hình hoàn tất thiếu/sai lỗi an toàn; thay/xóa khi xuất không trộn trạng thái dòng/hình; ZIP tạm xóa sau gửi/lỗi; ảnh chụp giống cho nội dung/thứ tự giống (không cần byte dấu thời gian ZIP y hệt). Cấm USER/TEACHER/vô danh xuất. Không dự đoán/báo cáo trong gói.
- [x] **Lệnh RED:** `uv run pytest tests/test_writing_benchmark_export.py -q`.
- [x] **Triển khai tối thiểu:** sinh tên chỉ từ tác vụ/vị trí/phần mở rộng MIME đã kiểm, không đóng gói đường dẫn người dùng. Khóa đọc chung dòng chọn khi dựng ZIP tạm; chép hình thuộc sở hữu đã kiểm trước thả. Dùng JSON/CSV/ZIP chuẩn và lược đồ chung sinh Pydantic có tham chiếu hợp lệ. Có đủ hai bản kê/CSV dù một tác vụ rỗng. Dùng dọn phản hồi tệp xác thực; hủy không xóa tài sản đang dùng.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_writing_benchmark_export.py tests/test_task2_benchmark_contracts.py tests/test_task1_benchmark.py -q`.
- [x] **Commit:** `Export the admin Writing benchmark bundle`.

### Tác vụ 8: Bộ chạy Task 2 dựa trên sản xuất, báo cáo chỉ điểm

**Tệp:**

- Tạo `backend/app/evaluation/writing/runtime.py` và `checkpoints.py`.
- Tạo `backend/app/evaluation/task2/runner.py` và `report.py`.
- Chỉ sửa `backend/app/evaluation/task1/runner.py` để tái dùng/tái xuất bộ đếm nhà cung cấp/checkpoint tách ra không chứa nội dung.
- Tạo `backend/tests/test_task2_benchmark.py`, `test_task2_benchmark_reports.py`; chỉ mở `test_task1_benchmark.py` kiểm tương thích tách mã.

**Giao diện:** chung `CountedProvider`, `atomic_write`, `save_attempt`, `cached_record(...,record_type=...)`, `attempt_history(...,record_type=...)`; Task 2 `configuration(settings,max_concurrent_llm_requests)`, `implementation_hash()`, `fingerprint(item,config)`, `evaluate(...)`, `run_benchmark(...)`; báo cáo `aggregate/build_report/markdown_report/write_report`. Logic chuyên đọc/nhận thức/biến thể Task 1 giữ ở Task 1.

- [x] **Kiểm RED:** đánh giá Task 2 sản xuất giả ánh xạ sự kiện/kết quả `ta` thành `tr`; đích/ghi nguồn/phân phối lại không vào tải nhà cung cấp. Chỉ đổi nhãn người chấm tạo yêu cầu giống hệt nhưng vô hiệu bộ nhớ đệm đánh giá; không kiểm lộ nhãn bằng chuỗi số trùng ngẫu nhiên. Đầu vào chỉ đề/bài đúng và ID nội bộ tất định, nguồn gốc textarea. Không cần engine DB/xác thực/worker API/nhà cung cấp biểu đồ. Đỉnh hữu hạn theo 1..4, mẫu không nhân giới hạn. Giữ mọi dự đoán hợp lệ không hiệu chỉnh.
- [x] **RED báo cáo:** TR/CC/LR/GRA/tổng khớp chính xác mã chung; tiêu chí hoàn tất một phần góp cặp so được, thiếu không bịa điểm/tổng; mẫu lỗi ở mẫu số/danh sách an toàn. Nhóm chia/band đích, lý do QWK thiếu, độ lệch có dấu, độ trễ, số gọi/token khả dụng; báo cáo/CSV không tái tạo nguồn/lỗi thô. Giữ lỗi lần đầu/mọi lần, chi phí lũy kế sau thử thành công; trúng đệm không tính gọi mới.
- [x] **Lệnh RED:** `uv run pytest tests/test_task2_benchmark.py tests/test_task2_benchmark_reports.py -q`.
- [x] **Triển khai tối thiểu:** gọi `MTSWritingScoringService.assess` theo danh tính lời nhắc hiệu lực, hành vi đồng thời/độ liên quan hiện có, không `WritingAIWorker`/lưu Attempt. Chỉ tạo dữ liệu đích sau suy luận để tính chỉ số. Dùng phép chung/checkpoint/bộ đếm có kiểu tối thiểu; không gọi bộ chạy thị giác Task 1 cho Task 2. Băm triển khai cả hai gồm tệp runtime/checkpoint chung. Task 2 đối chiếu tổng token từ mức dùng an toàn dịch vụ khi nhà cung cấp lỗi có cấp mức dùng; không đếm hai lần/bịa mức thiếu. Giữ đầu ra/hàm cũ Task 1, không bộ theo dõi thí nghiệm hoặc bảng kết quả DB.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_task2_benchmark.py tests/test_task2_benchmark_reports.py tests/test_task1_benchmark.py tests/test_writing_score_first.py tests/test_writing_concurrency.py -q`.
- [x] **Commit:** `Add production-backed Task 2 benchmark evaluation`.

### Tác vụ 9: CLI Task 2, tiếp tục và chạy ngoại tuyến an toàn

**Tệp:**

- Tạo `scripts/benchmark_task2.py`.
- Tạo `backend/tests/test_task2_benchmark_cli.py` và `test_task2_benchmark_resume.py`.
- Chỉ mở rộng `backend/app/evaluation/task2/runner.py` cho ca CLI/bộ nhớ đệm lộ qua các kiểm này.

**Giao diện:** `main(argv=None)`, cờ `--manifest`, bắt buộc `--split dev|holdout`, `--limit`, `--dry-run`, `--resume`, `--output`, `--max-concurrent-llm-requests 1..4`. Đầu ra mặc định trong `benchmarks/writing_task2/reports/` đã bỏ qua. Mã thoát theo Task 1: 0 thành công/chạy thử không suy luận, 1 lỗi đánh giá, 2 lỗi đầu vào/cấu hình, 130 gián đoạn rõ. Không tự thử lại cả mẫu hoặc gọi trực tiếp trong kiểm.

- [x] **Kiểm RED:** giới hạn đối số, sai/CSV/lựa chọn rỗng, stdout/stderr an toàn, chạy thử không tạo nhà cung cấp, gọi từ gốc/backend tương thích, không cần DB/xác thực sản xuất. Kiểm giả chứng minh đổi bài/đề/nhãn/chia/mô hình/nhà cung cấp/lời nhắc/nguồn gốc đoạn/triển khai/timeout vô hiệu bộ nhớ đệm; riêng đường dẫn/nhãn hiển thị không cần. Điểm kiểm hỏng/không nhất quán và lần lỗi không là trúng tiếp tục thành công.
- [x] **RED tiếp tục:** ngắt sau một thành công; tiếp lại giữ thành công, lỗi thử lại lần sau, giữ mọi lần; phục hồi checkpoint ghi dở từ lần hoàn tất đã kiểm; từ chối bản thiếu/tổng suy sai; báo cáo vẫn có trạng thái INTERRUPTED/lỗi. Không điểm cuối/khóa API bí mật trong khóa/bản ghi/nhật ký; không nhãn người chấm trong suy luận sau trượt bộ nhớ đệm.
- [x] **Lệnh RED:** `uv run pytest tests/test_task2_benchmark_cli.py tests/test_task2_benchmark_resume.py -q`.
- [x] **Triển khai tối thiểu:** theo quy ước CLI an toàn Task 1, cấu hình nhà cung cấp hiện có, checkpoint nguyên tử có kiểu; Task 2 độc lập thị giác. `schema_version: 1` là trường định dạng, không phiên bản ngân hàng lộ ra. Giữ ngoại lệ `noqa: E402` của script sau thêm backend vào `sys.path`.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_task2_benchmark_cli.py tests/test_task2_benchmark_resume.py tests/test_task1_benchmark.py -q`.
- [x] **Commit:** `Add resumable Task 2 benchmark CLI`.

### Tác vụ 10: Hợp đồng API/Zod frontend, máy khách nhị phân/hình

**Tệp:**

- Tạo `frontend/src/lib/api/writing-benchmark.ts`.
- Tạo `frontend/tests/writing-benchmark-api.test.ts`.

**Giao diện:** `benchmarkSampleSchema`, lược đồ danh sách/tóm tắt nhẹ, PATCH một phần, lỗi hoàn tất cấu trúc; `getWritingBenchmarkSummary/listWritingBenchmarkSamples/getWritingBenchmarkSample/createWritingBenchmarkSample/updateWritingBenchmarkSample/completeWritingBenchmarkSample/deleteWritingBenchmarkSample/uploadWritingBenchmarkImage/removeWritingBenchmarkImage/exportWritingBenchmarkBundle`. Dùng `ApiRequester` tiêm được cho JSON; `apiResponse` hiện có cho ZIP xác thực và quy ước yêu cầu/URL hình phù hợp. Giữ nhãn số null và tổng backend suy.

- [x] **Kiểm RED:** đúng đường/phương thức/query/body/revision, nửa band số/trường DRAFT null, xử lý hình/loại chỉ Task 1, danh sách không đủ nội dung, lỗi hoàn tất giữ đường dẫn qua `ApiError.details`, multipart tệp/revision không tự đặt Content-Type, URL xem riêng không khóa thô, phản hồi/tên ZIP/hành vi lỗi. Từ chối ghi tổng/tác vụ/vị trí/khóa giả. Không tải `/assets/images` bằng TestVersion bịa.
- [x] **Lệnh RED:** `npx vitest run tests/writing-benchmark-api.test.ts`.
- [x] **Triển khai tối thiểu:** một mô-đun HTTP có kiểu khớp DTO backend, dùng máy khách theo phiên/tải nhị phân hiện có. Không bộ đọc CSV, bộ chọn phiên bản dữ liệu hoặc DB frontend.
- [x] **Lệnh GREEN:** `npx vitest run tests/writing-benchmark-api.test.ts tests/admin-api.test.ts`; rồi `npm run typecheck`.
- [x] **Commit:** `Add typed admin Writing benchmark clients`.

### Tác vụ 11: Trình soạn quản trị danh sách/chi tiết, tự lưu, điều khiển hình riêng

**Tệp:**

- Tạo `frontend/src/app/admin/writing-benchmark/page.tsx`.
- Tạo `frontend/src/features/writing-benchmark/bank-page.tsx`, `sample-list.tsx`, `sample-editor.tsx`, `image-field.tsx`, và `bank.module.css`.
- Sửa `frontend/src/features/auth/admin-content.tsx` thêm liên kết quản trị.
- Sửa `frontend/src/lib/i18n/en.ts` và `vi.ts`.
- Tạo `frontend/tests/writing-benchmark-page.test.tsx`, `writing-benchmark-autosave.test.tsx`; mở `admin-dashboard.test.tsx` kiểm hiện liên kết.

**Giao diện:** `WritingBenchmarkBankPage`, `BenchmarkSampleList`, `BenchmarkSampleEditor`, `BenchmarkImageField`, hàm nhỏ riêng trang nháp→PATCH, hàm số tổng chỉ trình bày. Dùng `AdminLayout`, `AdminGuard`, `PageHeading`, `BuilderLifecycleProvider/useBuilderAutosave` với khóa `writing-benchmark:<uuid>`, chờ 1000 ms và `ConfirmDialog`. Dùng chốt `runTransition/flushAutosaves`; không `beginDelete` tắt vĩnh viễn ngân hàng. Không cần tái cấu trúc hook Builder chung trừ khi hồi quy tập trung chứng minh cần.

- [x] **Kiểm RED:** trang/link ADMIN; chặn USER/TEACHER cả trực tiếp; thẻ tác vụ, danh sách nhẹ, chỉ chi tiết chọn; mã/chia/trạng thái/tổng ổn định; tổng 100 tắt tạo dù nhiều nháp; lỗi tranh dung lượng khôi phục danh sách. Bộ đếm giả chứng minh một lưu sau nhập ổn định 1000 ms; giữ sửa trong khi đang lưu; lỗi/xung đột giữ biểu mẫu; Thử lại/Lưu ngay; đúng xuống dòng/Unicode; phản hồi cũ không thay UUID khác đang chọn.
- [x] **RED chuyển bước:** Ctrl/Cmd+S đẩy ngay/chặn mặc định; Ctrl/Cmd+Enter không chọn mẫu thiếu kế trước PATCH ACK mới nhất và Complete ACK. Lỗi kiểm/lưu giữ trình soạn với lỗi trường/nội dung. Chuyển thẻ/chọn đẩy an toàn trước tháo, không tự Hoàn tất. Xóa/gỡ hình đã xác nhận chờ thay đổi bền thành công, giữ lỗi nếu từ chối, không để dòng COMPLETE thiếu ảnh. Xem/thay/gỡ chỉ đúng UUID/revision hiện tại.
- [x] **RED trình bày:** EN/VI gồm loại, TA/TR, trạng thái/thao tác; nhãn/nút/thẻ ngữ nghĩa, dòng/trạng thái rõ ngoài màu, khôi phục tiêu điểm/bàn phím hộp thoại. Màn hẹp xếp danh sách/chi tiết bằng `min-width:0`, xuống dòng/cột lưới giới hạn, không tràn do chiều rộng cố định. Tôn trọng token giao diện/giảm chuyển động. Kiểm cấu trúc/đơn vị + xem CSS, không tuyên bố kiểm trình duyệt cục bộ.
- [x] **Lệnh RED:** `npx vitest run tests/writing-benchmark-page.test.tsx tests/writing-benchmark-autosave.test.tsx`.
- [x] **Triển khai tối thiểu:** một trình soạn chọn, nháp cục bộ theo UUID, ref revision chỉ cập nhật từ phản hồi thành công khớp, dùng hạ tầng đẩy tự lưu/hộp thoại. Nháp được thiếu nội dung; Hoàn tất thực thi lỗi backend. Hiện trạng thái lưu bản địa hóa nhẹ. Tổng máy khách chỉ tạm tiện dụng, thay bằng giá trị máy chủ sau ACK; phép nửa band phải khớp mẫu điểm giữa sản xuất. Dùng ảnh xác thực không tối ưu như Writing Builder thay proxy tối ưu Next công khai. Điều khiển tải/xem an toàn, không UI ngân hàng/tập dữ liệu/người chấm.
- [x] **Lệnh GREEN:** `npx vitest run tests/writing-benchmark-page.test.tsx tests/writing-benchmark-autosave.test.tsx tests/builder-autosave.test.tsx tests/writing-builder.test.tsx tests/admin-dashboard.test.tsx`; `npm run typecheck`.
- [x] **Commit:** `Add admin Writing benchmark master-detail editor`.

### Tác vụ 12: Tích hợp giao diện phân phối/xuất

**Tệp:**

- Tạo `frontend/src/features/writing-benchmark/distribution.tsx` và `export-button.tsx`.
- Sửa `bank-page.tsx`, `bank.module.css`, `frontend/src/lib/i18n/en.ts`, và `vi.ts`.
- Tạo `frontend/tests/writing-benchmark-distribution.test.tsx` và `writing-benchmark-export.test.tsx`.

**Giao diện:** `BenchmarkDistribution(summary)` dựng số tổng thật/gợi ý và hướng dẫn chia đã hoàn tất; `BenchmarkExportButton` đẩy sửa, làm mới tóm tắt, hiện số hoàn tất/nháp/chia, gọi một thao tác ZIP. Dùng hộp thoại hiện có cho tóm tắt xuất và mẫu dọn tải/object-URL.

- [x] **Kiểm RED:** đúng 11 đích/tổng 100; biểu đồ/chia chỉ COMPLETE; band thấp/vượt đích vẫn hợp lệ; phân phối không chặn Hoàn tất/xuất; tiến độ hai tác vụ độc lập. Xuất trước đầy, loại nháp rõ, tóm tắt rỗng/một phần, biểu mẫu bẩn đẩy trước xuất; lỗi giữ biểu mẫu/cho thử; một tải gói xác thực, giải phóng object URL. EN/VI, tiêu điểm/giảm chuyển động/bố cục hẹp.
- [x] **Lệnh RED:** `npx vitest run tests/writing-benchmark-distribution.test.tsx tests/writing-benchmark-export.test.tsx`.
- [x] **Triển khai tối thiểu:** dùng tóm tắt máy chủ, không tải 200 bài hoặc tổng lưu riêng. Hướng dẫn chỉ tư vấn; không trạng thái chỉ màu, phiên bản tập dữ liệu/chỉ số dự đoán trong ứng dụng. Biểu đồ tiêu chí ngoài P0.
- [x] **Lệnh GREEN:** `npx vitest run tests/writing-benchmark-distribution.test.tsx tests/writing-benchmark-export.test.tsx tests/writing-benchmark-page.test.tsx`; `npm run typecheck`.
- [x] **Commit:** `Add benchmark distribution and bundle export controls`.

### Tác vụ 13: Tài liệu, công bố lược đồ, hướng dẫn Colab

**Tệp:**

- Tạo `docs/writing-benchmark-bank.md`.
- Sửa `docs/ai-writing.md` và `benchmarks/writing_task1/README.md`.
- Tạo `benchmarks/writing_task2/README.md`, `manifest.schema.json`, `private/.gitkeep`, và `reports/.gitkeep`.
- Sửa `.gitignore` với quy tắc riêng Task 2 cho dữ liệu/báo cáo/bộ nhớ đệm/lần thử theo Task 1; cho rõ hai tệp `.gitkeep` qua quy tắc bỏ thư mục.
- Mở `backend/tests/test_writing_benchmark_export.py`, `test_task2_benchmark_cli.py` cho hợp đồng README/lược đồ/chạy thử ngoại tuyến.

**Giao diện:** lược đồ Task 2 sinh khớp JSON schema mô hình; README xuất dùng cờ thật, quy ước chạy backend/gốc, Task 1 v12 và nhãn lời nhắc hiệu lực Task 2. Giữ `schema_version:1` rõ là trường tương thích định dạng.

- [x] **Kiểm RED:** tệp gốc/tham chiếu lược đồ xuất khớp mô hình; lệnh README dùng cờ hỗ trợ thật, đường dẫn bản kê/hình tương đối an toàn; quy trình một mẫu giả/chạy thử không DB/JWT/phiên sản xuất, không nhà cung cấp trực tiếp. Đường dẫn riêng/báo cáo vẫn bỏ qua; không theo dõi bài/hình/nhãn thật. Giữ nhập bản kê/kiểm Task 1, truy cập bản lịch sử.
- [x] **Lệnh RED:** `uv run pytest tests/test_writing_benchmark_export.py tests/test_task2_benchmark_cli.py -q`.
- [x] **Tài liệu tối thiểu:** giải thích ADMIN → ZIP → tải Colab → sao chép/cài phụ thuộc backend → giải nén → bí mật nhà cung cấp → CLI Task 1/2 riêng → báo cáo. Có lệnh chạy thử và suy luận thủ công một mẫu nhưng không thực hiện trực tiếp. Nêu Task 1 v12/cấu hình Task 2 hiện tại, kỷ luật DEV/HOLDOUT, một người chấm, ghi nguồn trung lập, mặc định không phân phối lại, công bố nội dung gửi nhà cung cấp. Không thông tin PostgreSQL sản xuất, JWT quản trị, nhập API trực tiếp, DB dự đoán, tự hiệu chuẩn, GPU mới hoặc bắt buộc tích hợp notebook.
- [x] **Lệnh GREEN:** `uv run pytest tests/test_writing_benchmark_export.py tests/test_task2_benchmark_cli.py tests/test_task1_benchmark.py -q`; xem đường dẫn theo dõi/bỏ qua bằng `git status --short`, `git check-ignore`, chỉ dùng đường dẫn tạm hư cấu.
- [x] **Commit:** `Document Writing benchmark export and Colab evaluation`.

### Tác vụ 14: Hồi quy tích hợp tập trung, migration mới, chốt CI từ xa

**Tệp:**

- Sửa `backend/tests/test_writing_benchmark_export.py` cho `test_bank_bundle_fake_cli_pipeline` và khẳng định cô lập bản ghi sản xuất.
- Sửa `frontend/tests/writing-benchmark-page.test.tsx` thêm khẳng định soạn/ACK tích hợp còn thiếu.
- Sửa `docs/writing-benchmark-bank.md` ghi kết quả xác minh thực khi xong.
- Lỗi mới tái hiện có thể cần đúng tệp triển khai/kiểm sở hữu trong Tác vụ 1–13; ghi tệp/cách tái hiện tập trung trước sửa. Không đổi chấm Speaking/Writing không liên quan.

**Giao diện:** toàn đường ngân hàng → gói chuẩn → CLI Task 1/2 giả; không ghi Attempt/điểm/lượt AI người học, không lưu dự đoán ngân hàng. CI không đổi trừ khi chứng minh yêu cầu tìm kiểm riêng tính năng cần sửa tối thiểu.

- [ ] **Kiểm tích hợp RED:** thêm Task 1/2 hư cấu do ADMIN sở hữu, tự lưu nội dung thiếu, chứng minh không hoàn tất khi thiếu hình/nhãn, tải/gán nhãn/Hoàn tất, xuất, nạp cả hai hiện tại, chấm giả/kiểm báo cáo. Khẳng định cấm vai trò, chống cuộc đua lần 101, vị trí độc lập ổn định, gỡ hạ nháp, tổng khớp sản xuất, loại nháp, không thoát đường dẫn/lộ nhãn, chỉ số chung, vô hiệu tiếp tục, lỗi rõ. Chứng minh dòng người học/lịch sử/điểm cuối không đổi, không bảng/mô hình dự đoán. Thêm khẳng định thiếu trước sửa/triển khai.
- [ ] **Lệnh RED:** `uv run pytest tests/test_writing_benchmark_export.py::test_bank_bundle_fake_cli_pipeline -q`; dùng `npx vitest run tests/writing-benchmark-page.test.tsx` cho khẳng định soạn thiếu.
- [ ] **Sửa tối thiểu:** sửa nguyên nhân tất định ở lớp sở hữu. Giữ ranh giới ngân hàng đã duyệt, hợp đồng chấm Task 1/2 hiện tại, tương thích lịch sử Task 1 và toàn lịch sử migration.
- [ ] **GREEN backend (tệp tính năng tập trung):**

  ```powershell
  uv run pytest tests/test_writing_benchmark_metrics.py tests/test_writing_benchmark_models.py tests/test_writing_benchmark_migration.py tests/test_writing_benchmark_api.py tests/test_writing_benchmark_capacity.py tests/test_writing_benchmark_images.py tests/test_writing_benchmark_summary.py tests/test_writing_benchmark_export.py tests/test_task2_benchmark_contracts.py tests/test_task2_benchmark.py tests/test_task2_benchmark_reports.py tests/test_task2_benchmark_cli.py tests/test_task2_benchmark_resume.py tests/test_task1_benchmark_metrics.py tests/test_task1_benchmark.py -q
  ```

- [ ] **GREEN frontend (tệp tính năng tập trung):**

  ```powershell
  npx vitest run tests/writing-benchmark-api.test.ts tests/writing-benchmark-page.test.tsx tests/writing-benchmark-autosave.test.tsx tests/writing-benchmark-distribution.test.tsx tests/writing-benchmark-export.test.tsx tests/builder-autosave.test.tsx tests/writing-builder.test.tsx tests/admin-dashboard.test.tsx
  npm run typecheck
  ```

- [ ] **Kiểm mã/định dạng có mục tiêu:** từ `backend/`, chạy `uv run ruff check`, `uv run ruff format --check` trên đường backend mới/sửa và `../scripts/...` đã chạm. Không tự sửa script từ gốc/cấu hình khác rồi xóa ngoại lệ E402 bắt buộc. Từ `frontend/`, chạy `npx eslint` chỉ tệp frontend đã sửa.
- [ ] **GREEN PostgreSQL mới:** trên DB kiểm rỗng cô lập rõ, chạy `uv run alembic upgrade head`; kiểm đúng một đầu bằng `uv run alembic heads`, `ScriptDirectory.get_heads()`. Kiểm migration/cạnh tranh của revision mới thật trên PostgreSQL, so ràng buộc/mặc định mô hình với migration. Không đặt lại DB sản xuất.
- [ ] **Chốt Git/CI:** chạy `git diff --check`; kiểm phạm vi tệp dự kiến/không theo dữ liệu nguồn. Commit tích hợp xong hoặc sửa hồi quy nhỏ (`Verify Writing benchmark bank integration` nếu cần commit cuối), đẩy không force, xem CI + Golden path E2E nếu kích hoạt trên đúng SHA cuối. Đọc log job lỗi, chỉ chạy tái hiện cục bộ liên quan, sửa/commit/đẩy đến khi CI bắt buộc đạt. Ghi số đạt thật, đầu migration, SHA, link/trạng thái quy trình, cây sạch; không tuyên bố kiểm chưa chạy/độ chính xác mô hình trực tiếp.
- [ ] **Ranh giới commit:** chỉ kết thúc tính năng khi kiểm tập trung và CI bắt buộc đúng SHA đẩy đạt. Commit tác vụ trước vẫn rà độc lập được.

## Danh sách rà soát nghiệm thu

- [ ] Một ngân hàng/một bảng; không kho tập dữ liệu/phiên bản/người chấm/phân xử/thí nghiệm/dự đoán.
- [ ] Frontend và mọi CRUD/tóm tắt/hình/xuất backend chỉ ADMIN; cấm USER/TEACHER trực tiếp.
- [ ] DRAFT cho nội dung thiếu, nửa band gửi luôn hợp lệ; Hoàn tất/gỡ ảnh không để bản hoàn tất sai.
- [ ] Dung lượng gồm nháp; ràng buộc DB và kiểm tạo cạnh tranh lần 101 thật giới hạn 100 mỗi tác vụ.
- [ ] UUID/vị trí ổn định; xóa không đánh lại lân cận, tái dùng có UUID mới.
- [ ] Tổng khớp trung bình/làm tròn bốn tiêu chí sản xuất, không Writing đầy đủ trọng số, không lưu hai lần.
- [ ] Hình dùng kho hiện có, khóa riêng thuộc sở hữu bất biến, MIME/kích thước/chữ ký/đường dẫn an toàn và dọn an toàn chốt.
- [ ] Tóm tắt/danh sách nhẹ, phân phối chỉ hoàn tất, tổng hướng dẫn đúng, chia 80/20 tư vấn; band thấp hợp lệ được nhận.
- [ ] Xuất trước 100/100, bỏ nháp, ID/thứ tự/đường dẫn tất định, tương thích mô hình Task 1 CURRENT trực tiếp, hợp đồng Task 2 nghiêm, raters=1, nguồn an toàn, CSV nhiều dòng.
- [ ] CLI Task 2 dựa sản xuất, độc lập DB/xác thực, chỉ văn bản, giới hạn, suy luận không nhãn; cùng chỉ số chung, lỗi rõ, danh tính/tiếp tục/lịch sử lần thử vững.
- [ ] Tự lưu/phím tắt/chuyển giữ nội dung cục bộ, chờ ACK bền; Builder/xác thực/chú thích/đoạn chung giữ nguyên.
- [ ] EN/VI, điều khiển/tiêu điểm/hộp thoại ngữ nghĩa, bố cục thích ứng hữu hạn và hệ thị giác hiện có.
- [ ] Migration PostgreSQL mới, một đầu Alembic, xác minh tập trung và CI từ xa đúng SHA cuối đạt.

## Quyết định rà soát còn cần

Không phát hiện. Lựa chọn đã duyệt quyết định phạm vi sản phẩm. Không gian lưu trữ, revision dòng kỹ thuật, Hoàn tất rõ, tách chỉ số, bộ tiếp hợp tiêu chí Task 2 là chi tiết đã giải quyết từ mã hiện tại ở trên. Người dùng sau đó cho phép triển khai; không cần quyết định thiết kế/phê duyệt thêm.
