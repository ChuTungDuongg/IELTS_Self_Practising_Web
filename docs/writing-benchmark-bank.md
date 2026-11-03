# Ngân hàng benchmark Writing dành cho quản trị

<a id="ta-evidence-dev"></a>

## DEV kiểm tra ảnh hưởng nhận định evidence lên TA — 2026-11-03

Không có case TA 8→7 đã xác thực hoặc manifest có nhãn thật trong checkout; người yêu cầu xác nhận đây là mong muốn kiểm tra khách quan. Giao thức `task1-ta-evidence-v1` bổ sung vào runner hiện có, không thay các arm A–D lịch sử:

```powershell
uv run --project backend python scripts/benchmark_task1.py --manifest benchmarks/writing_task1/private/manifest.jsonl --split dev --ta-evidence-ablation --dry-run --max-cost-usd 0.50 --output benchmarks/writing_task1/reports/dev-ta-evidence-plan
```

Hai cấu hình `selector_assessments` và `source_ids_only` giữ cùng effective OpenAI policy, model Luna, prompt/rubric, image checksum/detail, v12 và DePlot off. Biến duy nhất trong score input TA là bỏ trường `evidence[].assessment` ở nhánh đối chứng. Source IDs, trích dẫn trong toàn bài, ảnh nguồn, facts/claims và reconciliation vẫn giữ; không đưa target/human scores/provenance vào scorer. Task 2, Speaking và vLLM production không đổi.

Field benchmark `ta_evidence_mode` tạo config/cache key riêng cho hai nhánh; mode absent giữ cách tính key cũ. Version prompt/policy production không tăng vì không đổi inference production. Implementation hash tiếp tục bao phủ mã đánh giá theo contract hiện có. Checkpoint cũ vẫn đọc được; metadata provider attempt mới là additive và được allowlist; không giả metadata cũ bằng cấu hình hiện tại.

CLI và cả entrypoint `run_benchmark/evaluate` khóa suy luận cho hai mode, kể cả có `--allow-live` hoặc injected provider factory. Chỉ dry-run DEV được phép; HOLDOUT bị từ chối trước khi gọi provider. Nhánh prompt đối chứng được chạy bằng provider giả trong contract tests, chưa được mở cho paid inference. Trần 0.50 USD trong plan là yêu cầu, `bound_verified=false`; cần reservation cho input/image, mọi arm, repair và request đang chạy trước khi mở live.

| Kết quả kiểm chứng hiện có | Trạng thái thật |
| --- | --- |
| Test hợp đồng hai nhánh với điểm giả 4/7/8 | Giữ nguyên band; chỉ thay nhận định evidence, không thay ảnh/toàn bài/criteria khác; không phải nhãn IELTS tin cậy |
| CLI dry-run trên fixture hư cấu | 2 scoring runs được lên kế hoạch, **0 inference**, paired samples đã đo = 0 |
| Case thật / số bài DEV có nhãn đã chạy | 0 / 0 |
| MAE TA, signed bias, tỷ lệ trong ±0.5, under/over scoring theo case/toàn tập | Chưa đo, không điền 0 giả |
| Factual feedback bị báo sai / stability chạy lặp | Chưa đo; cần adjudicated feedback labels và giao thức repeat độc lập |
| Lỗi/truncation, calls/latency/usage/cost của inference thật | Chưa đo; calls thật trong nhiệm vụ = 0 |

Khi được mở live sau này, dùng báo cáo per-case và aggregate hiện có (MAE, signed predicted-minus-human bias, within ±0.5, failure/truncation, calls/latency/usage), so cả under/over-scoring trên nhiều mức bài và chart/map/process. Không chọn điểm cao nhất qua nhiều lần chạy. Thí nghiệm reasoning medium/high là biến riêng, không gộp với evidence. HOLDOUT chỉ dùng đánh giá cuối, không chỉnh prompt lặp lại. [AI Writing](ai-writing.md#kiểm-tra-ta-khách-quan--2026-11-03) ghi nguyên nhân đã xác nhận, giả thuyết còn lại và công cụ đọc metadata của run thật.

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: mô tả ngân hàng benchmark Writing dành cho quản trị. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../backend/app/services/writing_benchmark.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/writing.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải kết quả chạy lại trong đợt kiểm toán này.

`/admin/writing-benchmark` chỉ dành cho ADMIN, nằm ngoài Workspace/Builder. Chốt bảo vệ frontend hiện có và mọi thao tác backend đều thực thi ranh giới này. Một ngân hàng chỉ lưu dữ liệu chuẩn: tối đa 100 mẫu Task 1 và 100 mẫu Task 2, kể cả bản nháp. Không có phiên bản tập dữ liệu, tài khoản người chấm, phân xử, lượt thí nghiệm, bảng dự đoán hoặc bảng báo cáo.

## Soạn dữ liệu

Trang danh sách/chi tiết hiển thị mã vị trí ổn định `T1-001` / `T2-001`, trạng thái Nháp/Hoàn tất, DEV/HOLDOUT và điểm tổng suy ra. Xóa không đánh lại số vị trí lân cận. Tái sử dụng vị trí đã xóa cấp UUID mới cho mẫu mới. Tạo mới luôn bắt đầu ở trạng thái Nháp.

Tự lưu chờ 1000 ms. Ctrl/Cmd+S lưu ngay. Ctrl/Cmd+Enter lưu chỉnh sửa mới nhất, chờ PATCH ACK, chuyển hoàn tất, chờ Complete ACK, rồi chọn mẫu chưa hoàn tất kế tiếp đã được lưu. `revision` kỹ thuật của dòng ngăn ghi cũ, không phải phiên bản tập dữ liệu. Lỗi/xung đột lưu giữ văn bản cục bộ. Tải lại khi xung đột yêu cầu xác nhận rõ việc bỏ chỉnh sửa cục bộ. Chọn mẫu, chuyển thẻ, hình ảnh, xóa và xuất đều đẩy hết/tuần tự hóa chỉnh sửa đang chờ.

Hoàn tất Task 1 cần đề, bài viết, loại tác vụ từ sản xuất, hình riêng tư hợp lệ và TA/CC/LR/GRA. Task 2 cần đề, bài viết và TR/CC/LR/GRA. Cả hai cần phần chia dữ liệu. Chỉ chấp nhận 0–9 theo nửa band trước khi cơ sở dữ liệu làm tròn. Điểm tổng dùng trung bình bốn tiêu chí/làm tròn nửa band hướng lên của sản xuất và không lưu riêng. Trọng số toàn mô-đun Writing không áp dụng cho bài đơn lẻ. Không lưu nhận xét của người chấm.

Tự lưu không tự chuyển hoàn tất. Khi bản ghi Hoàn tất mất tính hợp lệ, nó về Nháp; xóa hình Task 1 cũng vậy. Yêu cầu hoàn tất rõ ràng trả lỗi an toàn theo đường dẫn trường. Phân phối chỉ mẫu hoàn tất và mục tiêu DEV 80 / HOLDOUT 20 là hướng dẫn, không phải hạn ngạch. Band thấp hợp lệ vẫn được chấp nhận. Biểu đồ tần suất tiêu chí thuộc P1.

## API và lưu trữ

Các tuyến tương đối với `/api/v1/admin/writing-benchmark`, đều dùng `AdminUser`:

| Thao tác | Phương thức / đường dẫn |
| --- | --- |
| Tóm tắt | `GET /summary` |
| Danh sách nhẹ | `GET /samples?task=1` hoặc `task=2` |
| Bản nháp mới | `POST /samples` với `task_number` |
| Chi tiết | `GET /samples/{uuid}` |
| Tự lưu | `PATCH /samples/{uuid}` với `expected_revision` |
| Hoàn tất | `POST /samples/{uuid}/complete` với `expected_revision` |
| Xóa | `DELETE /samples/{uuid}?expected_revision=...` |
| Tải hình lên | `POST /samples/{uuid}/image`, tệp/revision dạng multipart |
| Đọc hình riêng tư | `GET /samples/{uuid}/image` |
| Gỡ hình | `DELETE /samples/{uuid}/image?expected_revision=...` |
| ZIP | `GET /export` |

`writing_benchmark_samples` là bảng mới duy nhất. Migration `20261013_0035` kế tiếp `20261013_0034`. Ràng buộc có tên bao phủ tác vụ, vị trí duy nhất, nửa band chính xác, điều kiện Hoàn tất và revision. Khóa tư vấn PostgreSQL ở cấp giao dịch theo từng tác vụ cấp vị trí trống nhỏ nhất an toàn khi tạo đồng thời. Truy vấn danh sách/tóm tắt không nạp toàn bộ bài viết. Máy chủ quản lý định danh, vị trí, khóa hình và điểm tổng. Không dùng lưu trữ Attempt, điểm hoặc lượt AI của người học.

## Hình ảnh và gói xuất

LocalAssetStorage giữ hình ngoài PostgreSQL trong không gian tên riêng: `benchmark/writing/task1/<sample-uuid>/<fresh-asset-uuid>.<ext>`. PNG/JPEG/WebP tái sử dụng kiểm tra MIME, phần mở rộng và chữ ký. Giới hạn là `min(max_image_upload_mb, 10 MiB)`. Mỗi lần thay dùng khóa bất biến: ghi tệp mới → chốt dòng/revision → cố gắng xóa tệp cũ. ACK chốt không chắc chắn sẽ giữ hình mới có thể đã chốt. Vượt đường dẫn, khóa của đối tượng khác và liên kết tượng trưng bị từ chối. Đọc riêng tư cần xác thực và `no-store`; sao chép số byte có giới hạn trong khóa dòng trước khi trả để tránh cuộc đua xóa tệp. Không tạo dòng Asset chung với quyền sở hữu TestVersion giả.

Xuất đẩy hết chỉnh sửa và xem lại số lượng Hoàn tất/Nháp/DEV/HOLDOUT mới. Chỉ gồm dòng Hoàn tất. Cho phép gói rỗng, một phần và đầy đủ:

```text
writing-benchmark.zip
├── task1.jsonl
├── task2.jsonl
├── task1.csv
├── task2.csv
├── manifest.schema.json
├── README.txt
└── images/
    └── T1-XXX.png|jpg|webp
```

Cả sáu tệp gốc đều hiện diện kể cả khi một tác vụ rỗng. JSONL là chuẩn; CSV giữ trích dẫn nhiều dòng và không có bộ phân tích đầu vào. Đường dẫn trong gói sinh từ mã/phần mở rộng an toàn, không từ tên tệp tải lên hoặc khóa thô. Khóa đọc chung của dòng bảo vệ ảnh chụp hình/bản kê đang chuẩn bị, kể cả khi hủy. ZIP tạm được xóa sau khi gửi xong/thất bại.

Task 1 khởi tạo `app.evaluation.task1.models.BenchmarkSample` CURRENT, dùng loại chuẩn như `PIE_CHART`, nên không cần chuyển đổi. Xuất dùng `raters=1`, `visual_truth=null` và giá trị trung lập `admin-labelled benchmark sample` khi ghi chú nguồn trống. Không tự tạo tuyên bố tác giả/giấy phép. Mặc định không cho phân phối lại. Task 2 chỉ có văn bản với TR; bộ tiếp hợp đánh giá ánh xạ `ta` sản xuất sang `tr`. `schema_version=1` thể hiện tương thích định dạng tệp.

## Quy trình Google Colab / cục bộ

Quản trị → xuất ZIP → tải ZIP lên Colab → sao chép kho mã → cài phụ thuộc backend → giải nén → cấu hình bí mật nhà cung cấp → CLI Task 1 hoặc Task 2 → báo cáo cục bộ. Không cần thông tin xác thực PostgreSQL sản xuất, JWT/phiên quản trị hoặc truy cập API sản xuất. Không có cơ chế Colab lấy trực tiếp từ API sản xuất.

Trong ô lệnh/terminal Colab, chỉnh đường dẫn khi cần:

```sh
git clone https://github.com/ChuTungDuongg/IELTS_Self_Practising_Web.git
cd IELTS_Self_Practising_Web
pip install uv
uv sync --project backend --locked --group dev
unzip /content/writing-benchmark.zip -d /content/writing-benchmark
uv run --project backend python scripts/benchmark_task1.py --manifest /content/writing-benchmark/task1.jsonl --split dev --scoring-version v12 --chart-specialist off --dry-run --output benchmarks/writing_task1/reports/dev-plan
uv run --project backend python scripts/benchmark_task2.py --manifest /content/writing-benchmark/task2.jsonl --split dev --dry-run --max-concurrent-llm-requests 2 --output benchmarks/writing_task2/reports/dev-plan
```

Đặt Colab Secrets/biến môi trường cho các trường nhà cung cấp hiện hành trong `backend/.env.example`: `AI_WRITING_ENABLED=true`, `AI_WRITING_PROVIDER`, URL/mô hình/khóa API của nhà cung cấp và thông tin proxy hiện có nếu cần. Mặc định cấu hình và lời nhắc sản xuất không đổi. CLI đọc biến môi trường và `backend/.env` tùy chọn. Không đưa bí mật vào notebook đã commit.

Tùy chọn suy luận **thủ công** một mẫu sau khi cấu hình nhà cung cấp (không phải kiểm thử CI):

```sh
uv run --project backend python scripts/benchmark_task1.py --manifest /content/writing-benchmark/task1.jsonl --split dev --limit 1 --scoring-version v12 --chart-specialist off --allow-live --resume --output benchmarks/writing_task1/reports/dev-smoke
uv run --project backend python scripts/benchmark_task2.py --manifest /content/writing-benchmark/task2.jsonl --split dev --limit 1 --max-concurrent-llm-requests 2 --allow-live --resume --output benchmarks/writing_task2/reports/dev-smoke
```

Suy luận gửi đề, bài viết và hình Task 1 đến nhà cung cấp đã cấu hình. Giữ riêng tư các gói riêng tư/có giấy phép. Dùng DEV để cải tiến, đầu ra HOLDOUT riêng để đánh giá cuối; tinh chỉnh lặp trên HOLDOUT làm suy yếu ranh giới này.

Các mẫu Task 2 chạy tuần tự. Giới hạn 1–4 chặn số yêu cầu tiêu chí sản xuất trong mỗi mẫu. MTSWritingScoringService chạy trực tiếp, không cần lưu người học, worker AI, nhận thức hình ảnh hoặc DePlot. Nhãn người chấm không vào lời nhắc suy luận. Chỉ số dùng chung gồm đồng thuận chính xác/±0.5/±1, độ lệch có dấu, MAE, RMSE và QWK. QWK cần 10 cặp nửa band so sánh được, phương sai kỳ vọng khác 0.

Đầu ra: `report.json`, `report.md`, `disagreements.csv`, `cache/`, `attempts/`. Lỗi vẫn hiển thị; tiêu chí hợp lệ một phần góp vào chỉ số, còn tổng cần bốn dự đoán. Báo cáo thể hiện độ trễ, số gọi và mức sử dụng hiện có, không chứa văn bản nguồn/URL bí mật/lỗi nhà cung cấp. Danh tính tiếp tục bao phủ nội dung, nhãn, phần chia, nhà cung cấp/mô hình/điểm cuối đã băm, lời nhắc có hiệu lực, cấu hình chạy, nguồn gốc đoạn văn, hợp đồng và phần triển khai. Đường dẫn/chú thích hiển thị không làm mất hiệu lực. Bản ghi thất bại/hỏng/không nhất quán không phải kết quả thành công trong bộ nhớ đệm. Lượt thất bại/chi phí trước vẫn giữ khi thử lại thành công. Chi phí yêu cầu đang chạy bị gián đoạn là chưa biết, không được bịa. Dự đoán/báo cáo chỉ nằm trong đầu ra CLI/Colab, không tự đổi chấm điểm sản xuất. Độ chính xác phải được xác lập riêng.

<a id="openai-luna-ablation"></a>

## Đối chiếu OpenAI Luna A–D — chuẩn bị ngoại tuyến

Đối chiếu source tại HEAD nền `f950d30c47dd4e40d7a0aba9a01b2014888ed9da` xác nhận reasoning `none`, completion cap `min(legacy stage cap, OpenAI cap)`, ảnh không có `detail` và TA chỉ nhận reference/facts/claims dạng văn bản. Đây là hành vi code đã xác nhận; chưa có bài lỗi thực tế hoặc bộ ảnh/bài viết riêng tư trong checkout để xác định nguyên nhân TA lệch. Khả năng reasoning, ngân sách, mức detail hoặc đối chiếu ảnh giúp TA vẫn là giả thuyết cần đo trên cùng dữ liệu có nhãn.

Tái sử dụng CLI Task 1, không tạo dashboard hay bảng dự đoán trong PostgreSQL. Chọn `AI_WRITING_PROVIDER=openai`, `AI_WRITING_OPENAI_MODEL=gpt-6-luna` và cấu hình profile hợp lệ theo [AI Writing](ai-writing.md#openai-gpt6-luna), rồi chạy từ root:

```powershell
uv run --project backend python scripts/benchmark_task1.py --manifest benchmarks/writing_task1/private/manifest.jsonl --split dev --limit 1 --openai-ablation --dry-run --max-cost-usd 0.50 --output benchmarks/writing_task1/reports/dev-luna-ablation-plan
```

Lệnh xác thực cùng bộ mẫu DEV và ảnh địa phương, sinh bốn cấu hình có identity riêng và ba cặp A→B/B→C/C→D, **không gọi provider**. Có thể chạy khi chưa có API key. Mỗi arm dùng cùng `gpt-6-luna`, transport Chat Completions, DePlot tắt và cùng ID/nội dung/checksum ảnh; nhãn band, `visual_truth`, provenance chỉ dùng tính chỉ số bên ngoài pipeline. Chế độ này từ chối HOLDOUT để tránh dùng tập giữ riêng cho phát triển.

| Arm | Thay đổi được lên kế hoạch | Reasoning / completion | Ảnh / TA |
| --- | --- | --- | --- |
| A | Nền lịch sử tại `f950d30c`, prompt v12 | `none`; cap từng bước cũ với trần 4096 | Bỏ `detail`; TA chỉ văn bản |
| B | A + policy reasoning, ngân sách và repair mới; giữ timeout mặc định 300 giây | `low` 8192; grounding/verification/TA `medium` 16384; budget repair tối đa một lần trong cap 32768 | Giữ detail mặc định của endpoint và TA văn bản |
| C | B + `image_url.detail=high` tường minh | Như B | Detail `high`; TA văn bản |
| D | C + TA nhận lại ảnh gốc và đối chiếu reference; bỏ text relevance gate chạy trước assessment ảnh | Như C | Ảnh tại TA; tối đa một vòng đọc ảnh lại độc lập rồi cập nhật facts/claims; tránh nhãn đọc sai tự kích hoạt Band 1 trước đối chiếu |

Các arm là **bản kê kế hoạch**, không phải bốn chế độ runtime đã đóng băng. A/B/C giữ phiên bản prompt v12 trong bản kê; D ghi phiên bản prompt production hiện tại. Adapter mới luôn chỉ định detail, nên không được chạy adapter này rồi gọi kết quả là baseline A hoặc B. Các giá trị kế hoạch là giao thức mặc định cố định, không giả là effective settings khi operator đã có stage overrides. Detail `original` hiện bị từ chối tại provider boundary; chỉ mở khi có tài liệu xác nhận rõ cặp Luna + Chat Completions, rồi đánh giá bằng giao thức DEV và identity riêng. Effort `high` cũng cần thí nghiệm DEV riêng. `high` không mặc nhiên tốt hơn `auto`.

### Live, ngân sách và kết quả chưa đo

Cả CLI Task 1/Task 2 giờ yêu cầu `--allow-live` cho lượt thường không có `--dry-run`; tìm thấy key không tự cho phép suy luận. Cờ này không phải bộ chặn chi phí. `--limit 1` giới hạn bài, không giới hạn số POST: các tiêu chí, validation repair và budget repair có thể tạo nhiều request.

**Live A–D bị khóa kể cả có `--allow-live --max-cost-usd 0.50`.** Runner và CLI trả `BENCHMARK_ABLATION_LIVE_DISABLED` trước khi tạo provider. Hệ thống chưa có reservation đáng tin cậy tính trước input/image tokens, giá hiện hành, mọi arm, mọi repair và request đang chạy. Vì vậy `0.50` trong dry-run chỉ là trần yêu cầu, `bound_verified=false`, không phải cam kết chi phí. CLI thường từ chối cờ `--max-cost-usd` để không tạo cảm giác có bảo vệ chưa triển khai. Cần bổ sung và kiểm thử cost admission trước mọi POST, cùng các chế độ A/B/C thực sự đóng băng, rồi mới cân nhắc smoke live được người dùng cho phép; không chạy benchmark hàng loạt trong trạng thái hiện tại.

Runner hiện có sẵn MAE TA, signed bias (dự đoán trừ nhãn), tỷ lệ trong ±0.5, failure rate, số call và latency. Số call ghi cả POST repair nằm trong một lần `complete`; usage của attempt thất bại được cộng cùng attempt thành công và giữ trong lịch sử, không cộng lặp với bookkeeping của scorer. `reasoning_tokens` là tập con của `completion_tokens`, không cộng thêm lần nữa để tính giá. Báo cáo ghi truncation theo số call có telemetry; checkpoint lịch sử không có counter giữ trạng thái chưa biết. Không có bảng giá đã xác minh thì `cost_usd=null`, không giả chi phí bằng 0.

`visual_truth` độc lập chỉ hỗ trợ đo trích xuất chart/table theo contract hiện có. Export ADMIN mặc định `visual_truth=null`, nên không thể suy ra độ chính xác hình từ confidence của model. Độ chính xác factual feedback cần nhãn từng nhận xét đã đối chiếu; hiện ghi `unmeasured_missing_adjudicated_feedback_labels`. Map/process chưa có phép đo factual tự động. Repeat stability cần chọn trước một tập con DEV và số lần lặp, chạy không dùng cache giữa các lần, báo độ phân tán TA cùng failure/latency/cost; hiện ghi `unmeasured_no_repeat_protocol`.

Trong lần triển khai này chỉ chạy kiểm thử ngoại tuyến với dữ liệu hư cấu. Không có bài/ảnh lỗi thực tế, bộ DEV được cấp quyền và lệnh live được cho phép; cost admission cũng chưa đủ để bảo đảm trần smoke. Không chạy API thật và chưa có MAE/bias/độ ổn định/chi phí thực nghiệm, không tuyên bố TA chính xác hơn.

### Cache và tái lập kiểm thử

Benchmark Task 1/Task 2 thêm identity riêng OpenAI từ provider: model/API/profile, reasoning, detail, budgets, timeout/repair và cờ TA ảnh; các tham số này cùng prompt/implementation hash, nội dung mẫu và image checksum Task 1 tách kết quả mới khỏi none/auto/text-only. Đổi config riêng OpenAI không đổi key vLLM. Runner từ chối runtime OpenAI có identity khác cấu hình ghi trong report trước khi gọi provider. Dry-run không đọc/ghi scoring checkpoint; kết quả lịch sử vẫn đọc được, không bị xóa. Task 1 giữ riêng perception ban đầu và sau đối chiếu; `ta_assessment` chỉ ghi trạng thái, số vòng đọc lại và loại xung đột, không ghi reasoning hoặc dữ liệu biểu đồ.

```powershell
uv run --project backend pytest backend/tests/test_task1_openai_ablation.py backend/tests/test_task1_benchmark.py backend/tests/test_task1_benchmark_metrics.py backend/tests/test_task2_benchmark_cli.py
```

Xác minh ngoại tuyến ban đầu: **155 passed** trong 54,06 giây khi chạy thêm các suite Task 2 benchmark/reports/resume/contracts cùng bốn tệp trong lệnh trên; không gọi API hoặc PostgreSQL. Sau review, thêm ba ca admission busy/timeout/cancellation kiểm chứng request chưa gửi không tăng số POST hoặc tự tạo finish metadata; bộ ablation hiện có 15 ca. Chạy lại ablation, OpenAI policy và Task 2 benchmark: **72 passed** trong 4,28 giây. Giữ lỗi perception ban đầu khi đối chiếu TA sửa reference và usage đã biết khi hủy repair cũng có kiểm thử. Các test chứng minh opt-in, isolation của arm, identity, repair usage và phép tính/điều phối. Mock hoặc dữ liệu hư cấu không chứng minh band đúng chuẩn IELTS. Dùng DEV để phát triển; chỉ đánh giá HOLDOUT sau khi chốt giao thức, qua runner thường với output riêng và quyền live rõ ràng. Không đưa nhãn hoặc `visual_truth` vào prompt để làm kết quả gần nhãn hơn.

<a id="implementation-validation--2026-10-13"></a>

## Xác minh triển khai — 2026-10-13

Triển khai bắt đầu từ main sạch `1ad0465a2b96d19fd41df3a117927f9d5cfa2989`. Lượt CI đúng SHA `38396464810` và Golden Path E2E `38396464698` đều đạt; không cần sửa nền. Đã commit mười bốn tác vụ TDD tuần tự.

Tập backend tập trung cuối cùng đạt **224 kiểm thử**, **một bỏ qua** vì máy Windows này không tạo được liên kết tượng trưng; Linux CI kiểm tra chốt bảo vệ trên hệ thống tệp thật đó. Tập frontend tập trung đạt **58 kiểm thử**, gồm hồi quy Builder/Admin chịu ảnh hưởng. Kiểm tra kiểu frontend, Ruff kiểm mã/định dạng có mục tiêu, ESLint có mục tiêu và `git diff --check` đều đạt. Chỉ `.gitkeep` được theo dõi trong thư mục đầu vào riêng tư/lưu trữ và báo cáo sinh ra; không thêm dữ liệu benchmark riêng tư.

PostgreSQL mới cô lập `bandpilot_benchmark_20261013_2138` nâng từ rỗng bằng `alembic upgrade head`. Đầu migration duy nhất là `20261013_0035`. Kiểm thử nâng/hạ thực và cuộc đua cấp vị trí dùng kết nối PostgreSQL độc lập cùng lược đồ tạm, không chỉ dựng lược đồ ORM.

Kiểm thử tích hợp API → ZIP → cả hai bộ nạp hiện hành → cả hai CLI nhà cung cấp giả hoàn tất mà không đổi dòng Attempt/điểm cuối/lượt AI của người học. Nó phát hiện và bao phủ hủy xuất lặp lại: khóa ảnh chụp nay được giữ tới khi luồng chuẩn bị xong, rồi ZIP đã hủy mới bị xóa.

Không dùng trình duyệt, E2E cục bộ, nhà cung cấp trực tiếp, suy luận GPU, triển khai hoặc toàn bộ bộ kiểm thử cục bộ. Các quy trình từ xa bắt buộc được kiểm trên SHA đẩy cuối trước khi báo hoàn tất. Biểu đồ tần suất tiêu chí vẫn được chủ đích hoãn sang P1.
