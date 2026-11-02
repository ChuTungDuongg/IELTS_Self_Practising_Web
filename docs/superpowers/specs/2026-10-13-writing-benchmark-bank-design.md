# Thiết kế kho dữ liệu đánh giá chuẩn Writing cho quản trị viên

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Thiết kế kho dữ liệu đánh giá chuẩn Writing cho quản trị viên. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/services/writing_benchmark.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Trạng thái

Thiết kế trao đổi được phê duyệt ngày 2026-10-13; đặc tả văn bản chờ người dùng rà soát cuối trước lập kế hoạch triển khai.

Mở rộng kiến trúc này thêm một kho dữ liệu đánh giá chuẩn Writing duy nhất chỉ ADMIN vào ứng dụng hiện có. Ứng dụng web chỉ chịu trách nhiệm biên soạn, xác thực, lưu và xuất mẫu đánh giá đã gán nhãn. Suy luận đánh giá vẫn là luồng CLI ngoại tuyến/Colab, phải tái sử dụng chỉ số Writing và bộ máy đánh giá Task 1 hiện có của kho mã, không trở thành tác vụ nền production.

## Mục tiêu

Cung cấp một kho đánh giá chuẩn Writing chứa tối đa:

- 100 mẫu Academic Writing Task 1;
- 100 mẫu Writing Task 2.

Mỗi mẫu được một ADMIN nhập và gán nhãn. Không có phiên bản bộ dữ liệu, khái niệm kho v1/v2, luồng nhiều người chấm hoặc phân hệ phân xử.

Kho phải hỗ trợ:

- nhập nhanh chỉ ADMIN ngoài Workspace/Builder;
- đề Task 1 + ảnh + bài viết + nhãn con người TA/CC/LR/GRA;
- đề Task 2 + bài viết + nhãn con người TR/CC/LR/GRA;
- band tổng suy ra nhất quán production;
- gán phân tập DEV/HOLDOUT;
- hướng dẫn phân bố band tổng để tạo tập hiệu chỉnh cân bằng;
- tự lưu nháp và xác thực đầy đủ rõ ràng;
- xuất ZIP cho Google Colab chứa JSONL chuẩn, ảnh Task 1 và bản CSV tiện xem;
- tái dùng CLI đánh giá Task 1 hiện có;
- CLI đánh giá Task 2 dùng cùng định nghĩa chỉ số đồng thuận/sai số nơi áp dụng.

## Ngoài phạm vi

Tính năng này không:

- tạo nhiều bộ dữ liệu đánh giá hoặc phiên bản dữ liệu;
- thêm tài khoản người chấm, độ tin cậy giữa người chấm hoặc phân xử;
- chạy đánh giá 200 mẫu từ ứng dụng web production;
- ghi dự đoán, báo cáo, độ trễ hoặc lịch sử thử nghiệm đánh giá vào cơ sở dữ liệu production;
- cung cấp mẫu đánh giá cho USER/TEACHER;
- tái dùng Attempt/WritingTask/AttemptWritingScore học viên thường làm nhãn chuẩn đánh giá;
- dùng CSV làm đầu vào chuẩn đánh giá;
- commit bài viết/ảnh riêng tư hoặc được cấp phép vào Git;
- tự tinh chỉnh, dịch điểm, đặt trần hoặc triển khai điểm AI từ kết quả đánh giá.

## Kiến trúc hiện có cần tái sử dụng

Kho mã đã có hệ thống đánh giá Task 1 đáng kể dưới `backend/app/evaluation/task1/` cùng `scripts/benchmark_task1.py`. Hợp đồng manifest cục bộ gồm ID mẫu, phân tập `dev | holdout`, loại Task 1, đề, đường ảnh cục bộ, bài viết và điểm người chấm TA/CC/LR/GRA. Báo cáo đã gồm chỉ số đồng thuận tiêu chí/tổng như khớp chính xác, trong ±0.5, trong ±1.0, độ lệch có dấu, MAE, RMSE, QWK, cùng độ trễ/lỗi/mức dùng vận hành và chẩn đoán tri giác Task 1.

`BenchmarkSample` Task 1 hiện có cũng mang metadata riêng đánh giá như `raters`, `provenance`, `redistributable`. Kho web mới có đúng một người gán nhãn mỗi mẫu; vì vậy xuất ghi `raters=1` xác định và ánh xạ metadata nguồn/nguồn gốc của kho vào hợp đồng manifest hiện có. Cơ sở dữ liệu production không cần mô hình từng người chấm.

Kho mã đã có `LocalAssetStorage` và xử lý tài sản PNG/JPEG/WebP có xác thực. Ảnh đánh giá Task 1 cần tái dùng lớp lưu trữ này thay vì lưu byte/base64 ảnh trong PostgreSQL.

Task 2 hiện có chấm production nhưng chưa có CLI đánh giá chuyên biệt tương đương. Thiết kế thêm luồng đánh giá Task 2 mà không sao chép toàn hệ thống tri giác riêng Task 1.

## 1. Tuyến quản trị và ranh giới truy cập

Thêm trang ADMIN độc lập:

```text
/admin/writing-benchmark
```

Trang nằm ngoài Workspace/Builder và các trang Teacher.

Cả hai lớp cưỡng chế truy cập chỉ ADMIN:

- tuyến/trình bày frontend dùng quy ước xác thực/chốt quản trị hiện có;
- mọi tuyến CRUD, ảnh và xuất backend dùng `AdminUser` hoặc dependency ADMIN tương đương dự án;
- ẩn mục điều hướng tuyệt đối không được xem là phân quyền;
- USER/TEACHER gọi API trực tiếp nhận phản hồi từ chối an toàn bình thường của kho mã.

Có thể liên kết từ khu Admin nhưng trang cần giữ là công cụ dữ liệu đánh giá riêng, không nhúng vào Test Builder.

## 2. Một kho chuẩn duy nhất và dung lượng

Chỉ có một kho đánh giá logic.

Dung lượng cố định:

```text
Task 1: maximum 100 samples
Task 2: maximum 100 samples
```

Backend cưỡng chế giới hạn trong giao dịch; vô hiệu hóa frontend chỉ tiện ích. Không được tạo mẫu 101 bằng yêu cầu API cạnh tranh hoặc bỏ qua điều khiển giao diện.

Không có bảng `BenchmarkDataset`, phiên bản kho, thực thể phát hành hoặc bộ chọn kho.

## 3. Mô hình lưu trữ

Tạo mô hình nhãn chuẩn đánh giá riêng thay tái dùng lượt học viên.

Về khái niệm:

```text
WritingBenchmarkSample
- id: UUID primary key
- task_number: 1 | 2
- sequence_number: 1..100
- status: DRAFT | COMPLETE
- split: DEV | HOLDOUT
- prompt: text
- essay: text
- task1_task_type: nullable, Task 1 only
- task1_image_key: nullable, Task 1 only
- human_ta_tr: nullable decimal half-band
- human_cc: nullable decimal half-band
- human_lr: nullable decimal half-band
- human_gra: nullable decimal half-band
- source_note/provenance: nullable bounded text
- redistributable: boolean, default false
- created_at
- updated_at
```

Ràng buộc:

- duy nhất `(task_number, sequence_number)`;
- `sequence_number` từ 1 đến 100;
- nhãn tiêu chí phải là nửa band Writing hợp lệ production từ 0 đến 9;
- Task 1 có thể mang `task1_task_type`/ảnh; Task 2 không được yêu cầu chúng;
- Task 1 COMPLETE yêu cầu đề, bài viết, loại task, ảnh, phân tập và đủ bốn nhãn;
- Task 2 COMPLETE yêu cầu đề, bài viết, phân tập và đủ bốn nhãn;
- DRAFT cho trường nhập từng phần cần cho tự lưu;
- đổi/gỡ trường bắt buộc khỏi bản ghi COMPLETE đưa về DRAFT hoặc từ chối cập nhật COMPLETE rõ ràng; dịch vụ tuyệt đối không để lại COMPLETE không hợp lệ.

Chủ động không lưu `human_overall`. Nó suy ra bằng cùng hàm tổng hợp/làm tròn bốn tiêu chí Writing production của chấm điểm, ngăn giá trị cơ sở dữ liệu lệch tổng hiển thị/xuất.

Không thêm bảng mẫu Task 1/Task 2 riêng trừ khi ràng buộc triển khai khiến mô hình có kiểu duy nhất kém an toàn đáng kể. Ưu tiên một bảng với xác thực theo task vì dùng chung giao diện, logic phân bố và xuất.

## 4. Ngữ nghĩa gán nhãn con người

Đúng một ADMIN nhập nhãn con người chuẩn cho mỗi mẫu.

Nhãn Task 1:

```text
TA
CC
LR
GRA
```

Nhãn Task 2:

```text
TR
CC
LR
GRA
```

Không lưu hoặc yêu cầu phản hồi văn bản.

Giao diện cung cấp nhãn tiêu chí qua select/combobox nửa band có kiểm soát, không trường số văn bản tùy ý.

Tổng hiển thị chỉ đọc, suy ra trực tiếp cho tiện; backend tính lại độc lập khi trình bày, xác thực và xuất dữ liệu.

Không điểm AI nào được âm thầm điền vào trường con người chuẩn. Nhãn chuẩn là dữ liệu con người nhập.

## 5. DEV và HOLDOUT

Mỗi mẫu có:

```text
DEV | HOLDOUT
```

Đây là nguyên tắc giữ đánh giá độc lập trong một kho, không phải tạo phiên bản dữ liệu.

Mục tiêu khuyến nghị xấp xỉ:

```text
80 DEV
20 HOLDOUT
```

cho mỗi task.

DEV dùng khảo sát prompt/hiệu chỉnh lặp. HOLDOUT dành đánh giá cuối, không nên liên tục xem hoặc tinh chỉnh theo nó.

Ứng dụng hiện số lượng phân tập/hướng dẫn, không tự chuyển mẫu giữa tập.

Mẫu mới có thể mặc định DEV để nhập nhanh.

## 6. Danh tính mẫu

Danh tính cơ sở dữ liệu là UUID.

Mã ổn định cho người dùng dùng task + vị trí:

```text
T1-001 ... T1-100
T2-001 ... T2-100
```

`sequence_number` là vị trí ổn định, không vị trí mảng. Xóa T1-037 không được đánh lại T1-038..T1-100. Mẫu mới tương lai được dùng lại vị trí 037 trống nhưng nhận UUID mới.

Bản xuất dùng mã ổn định hướng người dùng làm `id` mẫu đánh giá để dễ đối chiếu báo cáo với kho quản trị.

## 7. UX biên soạn

Trang dùng trình danh sách/chi tiết thay hiển thị 200 biểu mẫu đầy đủ.

Ý tưởng trên máy tính:

```text
Writing Benchmark Bank
Task 1 63/100 complete   Task 2 41/100 complete

[Task 1] [Task 2]

Samples                    Selected sample
T1-001 ✓ 7.0               Prompt
T1-002 Draft               [textarea]
T1-003 ✓ 6.5               Image / task type
...                         Essay
[+ New sample]              [textarea]
                            Human labels
                            Derived overall
```

Danh sách mẫu hiển thị ít nhất:

- mã ổn định;
- trạng thái DRAFT/COMPLETE;
- tổng suy ra khi đủ nhãn;
- trạng thái DEV/HOLDOUT khi hữu ích.

Trên màn hình hẹp, danh sách/chi tiết có thể xếp hoặc điều hướng theo quy ước thích ứng hiện có; không ép hai khung quá hẹp không dùng được cạnh nhau.

## 8. Tự lưu nháp và luồng nhập nhanh

Khối lượng dự kiến là nhập thủ công tối đa 200 mẫu, nên mất dữ liệu biểu mẫu là không chấp nhận.

Dùng tự lưu có trì hoãn gộp thay đổi cho DRAFT/bản ghi đang sửa, khoảng 800–1200 ms sau đầu vào ổn định, theo quy ước yêu cầu/lỗi dự án. Không lưu mỗi phím khi chưa gộp.

Cung cấp lưu tức thì chủ động, gồm:

```text
Ctrl/Cmd + S -> save immediately
Ctrl/Cmd + Enter -> validate/mark COMPLETE and move to next incomplete sample when successful
```

Có thể bỏ phím tắt ở ngữ cảnh không hỗ trợ, nhưng biên soạn máy tính cần hỗ trợ nếu không xung đột hành vi trình duyệt/trình sửa hiện có.

Trạng thái tự lưu cần nhẹ và rõ, ví dụ Saving / Saved / Retry required, không ngắt bằng hộp thoại.

Tự lưu thất bại không được xóa nội dung biểu mẫu cục bộ.

## 9. Xử lý ảnh Task 1

Bản ghi Task 1 COMPLETE yêu cầu một ảnh đề.

Tái dùng `LocalAssetStorage` và quy ước xác thực MIME/kích thước ảnh hiện có:

```text
PNG
JPEG
WebP
```

Chỉ lưu khóa/đường tương đối lưu trữ trong bảng đánh giá.

Dùng namespace đánh giá riêng, về khái niệm:

```text
benchmark/writing/task1/<sample-uuid>.<ext>
```

Trình quản trị cung cấp xem trước, thay thế và gỡ.

Thay/xóa ảnh phải dùng mẫu dọn an toàn hiện có để tài sản cũ không tích lũy không cần thiết. Gỡ ảnh khỏi mẫu Task 1 COMPLETE làm mẫu thành DRAFT.

Ảnh đánh giá không cần URL công khai không xác thực. Xem trước/API quản trị giữ xác thực, xuất ZIP đọc tài sản phía máy chủ.

## 10. Xác thực tính đầy đủ

Task 1 COMPLETE yêu cầu:

- đề không trống;
- bài viết không trống;
- loại Task 1 hợp lệ từ registry production;
- ảnh lưu hợp lệ;
- phân tập DEV/HOLDOUT;
- nhãn nửa band TA, CC, LR, GRA.

Task 2 COMPLETE yêu cầu:

- đề không trống;
- bài viết không trống;
- phân tập DEV/HOLDOUT;
- nhãn nửa band TR, CC, LR, GRA.

Không yêu cầu phản hồi.

API trả lỗi xác thực có cấu trúc để trình chi tiết gắn với trường.

Bản ghi DRAFT có thể chưa đầy đủ vô thời hạn.

## 11. Công cụ lập phân bố

Đầu trang hiển thị số lượng/tiến độ hiện tại Task 1/Task 2 cùng phân bố band tổng gợi ý.

Mục tiêu gợi ý cho mỗi kho task 100 mẫu:

| Band tổng | Gợi ý |
| ---: | ---: |
| 4.0 | 8 |
| 4.5 | 8 |
| 5.0 | 9 |
| 5.5 | 10 |
| 6.0 | 11 |
| 6.5 | 12 |
| 7.0 | 12 |
| 7.5 | 10 |
| 8.0 | 8 |
| 8.5 | 6 |
| 9.0 | 6 |

Tổng: 100.

Đây chỉ là hướng dẫn, không ràng buộc lưu/xuất. Chủ động tăng mật độ vùng hiệu chỉnh thường gặp 6.0–7.5, vẫn phủ có ý nghĩa hai đầu thang.

Mỗi band, giao diện có thể hiện:

```text
8.0: 5 / suggested 8 -> ~3 more recommended
```

Chỉ tính phân bố từ mẫu COMPLETE.

Trang có thể thêm chế độ phân bố tiêu chí gọn TA/TR, CC, LR, GRA để thấy nhãn tập trung, nhưng không có chỉ tiêu cứng theo tiêu chí.

Split guidance also shows approximate progress toward 80 DEV / 20 HOLDOUT cho mỗi task.

## 12. Hành vi xuất

Cung cấp một thao tác:

```text
Export benchmark bundle
```

Xuất chỉ gồm mẫu COMPLETE. Tuyệt đối không âm thầm chuyển đổi hoặc xuất một phần mẫu DRAFT.

Người dùng được xuất trước đạt 100/100 để kiểm tra nhanh luồng CLI/Colab bằng kho nhỏ.

Trước xuất, hiện tóm tắt gọn như:

```text
Task 1: 93 complete, 7 draft
Task 2: 100 complete
DEV/HOLDOUT counts
```

Backend tạo ZIP đủ xác định để nội dung/danh tính manifest tái tạo được từ cùng trạng thái mẫu đã lưu. Không yêu cầu ZIP giống từng byte thời gian, nhưng thứ tự mẫu, ID và đường dẫn ổn định.

## 13. Hợp đồng ZIP chuẩn

Cấu trúc gói:

```text
writing-benchmark.zip
├── task1.jsonl
├── task2.jsonl
├── task1.csv
├── task2.csv
├── manifest.schema.json
├── README.txt
└── images/
    ├── T1-001.png
    ├── T1-002.webp
    └── ...
```

JSONL là đầu vào đánh giá chuẩn. CSV chỉ tiện xem.

Tên ảnh Task 1 là mã mẫu ổn định cộng phần mở rộng nguồn đã xác thực. `task1.jsonl` tham chiếu đường cục bộ tương đối như:

```text
images/T1-001.png
```

Không đặt ảnh base64 trong JSONL/CSV.

`manifest.schema.json` có thể chứa định nghĩa Task 1/Task 2 riêng hoặc wrapper nhỏ ghi cả hai hợp đồng. Nó phải phản ánh đầu vào CLI phát hành thực sự chấp nhận.

`README.txt` cung cấp hướng dẫn gọi Colab/cục bộ ngắn, nêu rõ ZIP chứa tư liệu nguồn đánh giá có thể riêng tư/được cấp phép.

## 14. Tương thích JSONL Task 1

Ưu tiên tương thích trực tiếp hợp đồng `backend/app/evaluation/task1/models.py::BenchmarkSample` hiện có để `scripts/benchmark_task1.py` dùng manifest Task 1 xuất ra không cần script chuyển đổi.

Về khái niệm, xuất mỗi mẫu Task 1 dạng:

```json
{
  "schema_version": 1,
  "id": "T1-001",
  "split": "dev",
  "task_type": "pie_chart",
  "prompt": "...",
  "image_path": "images/T1-001.png",
  "essay": "...",
  "human_scores": {
    "ta": 7.5,
    "cc": 7.0,
    "lr": 8.0,
    "gra": 7.5
  },
  "raters": 1,
  "provenance": "admin-labelled benchmark sample...",
  "redistributable": false,
  "visual_truth": null
}
```

Kho web không thêm mô hình nhiều người chấm chỉ vì CLI có `raters`; luôn xuất `raters=1`.

Trang biên soạn này không yêu cầu `visual_truth`, có thể giữ `null`. Chỉ số điểm Task 1 hiện có vẫn hoạt động; chỉ số đối chiếu tri giác với nhãn chuẩn không có khi thiếu chú giải hình ảnh chuẩn độc lập.

Nguồn gốc xuất chuỗi không trống có giới hạn. Nếu quản trị viên không nhập ghi chú nguồn, dùng giá trị trung tính xác định như `admin-labelled benchmark sample`; không bịa tuyên bố tác giả/giấy phép. `redistributable` mặc định false trừ khi ADMIN đánh dấu khác rõ ràng.

## 15. Hợp đồng JSONL Task 2

Thêm mô hình mẫu đánh giá Task 2 nghiêm ngặt riêng, về khái niệm:

```json
{
  "schema_version": 1,
  "id": "T2-001",
  "split": "holdout",
  "prompt": "...",
  "essay": "...",
  "human_scores": {
    "tr": 7.0,
    "cc": 7.0,
    "lr": 7.5,
    "gra": 7.0
  },
  "raters": 1,
  "provenance": "admin-labelled benchmark sample...",
  "redistributable": false
}
```

Dùng `tr` trong hợp đồng đánh giá Task 2 cho ngữ nghĩa Task Response hướng người dùng dù nội bộ production dùng `ta` làm khóa tiêu chí chung. Bộ chuyển đổi đánh giá ánh xạ nhãn Task 2 an toàn sang tiêu chí Task Response production mà không đổi ngữ nghĩa chấm.

Schema xác thực cùng miền nửa band 0–9 như tiêu chí Writing production.

## 16. Bản xuất CSV tiện xem

`task1.csv` và `task2.csv` chỉ để xem trong Excel/Google Sheets.

Dùng quoting CSV UTF-8 chuẩn để đề/bài nhiều dòng vẫn hợp lệ.

Cột phẳng gồm ít nhất:

```text
id
split
task_type (Task 1 only)
prompt
essay
image_path (Task 1 only)
human_ta_or_tr
human_cc
human_lr
human_gra
human_overall
provenance
redistributable
```

CSV không được thành luồng phân tích đầu vào chuẩn thứ hai của trình đánh giá.

## 17. Chỉ số điểm dùng chung

Task 1 đã triển khai phép tính đồng thuận điểm thuần gồm:

- khớp chính xác;
- trong ±0.5;
- trong ±1.0;
- độ lệch có dấu dự đoán trừ điểm người;
- MAE;
- RMSE;
- Quadratic Weighted Kappa trên 19 nhóm nửa band.

Task 2 phải dùng cùng định nghĩa.

Chỉ tái cấu trúc đủ chia sẻ hàm chỉ số chỉ điểm, ví dụ vào `backend/app/evaluation/writing/metrics.py` nhỏ, giữ chỉ số tri giác Task 1 riêng Task 1. Bảo toàn tương thích import/kiểm thử Task 1 bằng cập nhật import trực tiếp hoặc tái xuất chủ động.

Không tạo bản triển khai QWK/MAE thứ hai khác tinh vi.

Tổng Task 2 phải dùng cùng tổng hợp bốn tiêu chí/làm tròn nửa band Writing production như chấm thường.

## 18. CLI đánh giá Task 2

Thêm CLI Task 2 riêng thay nhồi vào trình ảnh/tri giác Task 1.

Về khái niệm:

```text
scripts/benchmark_task2.py
```

CLI dùng `task2.jsonl`, gọi luồng Writing Task 2 chấm trước production với cấu hình nhà cung cấp/mô hình, ghi dự đoán mà không đưa nhãn người vào yêu cầu.

Hành vi CLI bắt buộc cần tương ứng phần hữu ích không tri giác của Task 1:

- `--manifest`;
- `--split dev|holdout`;
- `--limit` cho kiểm tra nhanh;
- đồng thời có giới hạn;
- `--resume` có danh tính cache gồm nội dung/nhãn mẫu, nhà cung cấp/mô hình, hợp đồng prompt/chấm và danh tính triển khai liên quan;
- thư mục đầu ra chứa `report.json`, `report.md`, `disagreements.csv`, `cache/` và `attempts/` hoặc quy ước hiện có tương đương;
- mẫu thất bại vẫn xuất hiện trong thống kê lỗi, không biến mất;
- nhãn chỉ dùng chỉ số sau suy luận, tuyệt đối không vào prompt mô hình.

Không thêm trường ảnh/tri giác/DePlot Task 2.

Không tạo dịch vụ theo dõi thử nghiệm hoặc bảng cơ sở dữ liệu lượt đánh giá.

## 19. Chỉ số và báo cáo

Task 1 giữ ngữ nghĩa báo cáo hiện có.

Task 2 báo tối thiểu cho TR, CC, LR, GRA và tổng suy ra:

- số mẫu so sánh được;
- khớp chính xác;
- trong ±0.5;
- trong ±1.0;
- độ lệch có dấu;
- MAE;
- RMSE;
- QWK khi đủ yêu cầu số mẫu/phương sai;
- tỷ lệ thất bại/không đủ điều kiện chấm;
- độ trễ thời gian thực;
- số yêu cầu nhà cung cấp/mức dùng token nếu có.

Nếu hạ tầng đánh giá hiện có cung cấp Pearson/Spearman trong mô-đun chỉ số Writing/Speaking tái dùng được, Task 2 có thể thêm nhất quán. Không thêm công thức thứ hai chỉ để tăng diện tích báo cáo. Yêu cầu nghiệm thu cốt lõi là tập chỉ số đồng thuận/sai số Task 1 hiện có cùng thông tin độ trễ/lỗi vận hành.

Báo cáo cần có phân tầng nhóm band và phân tập nơi chi phí thấp, nhất quán quy ước Task 1 để thấy chấm thấp/cao ở band người cụ thể.

## 20. Luồng Google Colab

Tuyệt đối không cần Colab truy cập trực tiếp cơ sở dữ liệu production.

Luồng khuyến nghị:

```text
ADMIN web page
-> export writing-benchmark.zip
-> upload ZIP to Colab
-> clone/current repository checkout
-> install backend dependencies
-> unzip dataset
-> configure model/provider secrets in Colab environment
-> run Task 1 or Task 2 benchmark CLI
-> inspect report.json/report.md/disagreements.csv
```

Cách này chủ động tránh đưa thông tin xác thực PostgreSQL production hoặc token quản trị vào Colab.

README gói cần nêu lệnh tương thích quy ước chạy root/backend thực của kho mã.

## 21. Riêng tư và xử lý dữ liệu

Tư liệu nguồn đánh giá có thể riêng tư hoặc được cấp phép.

Yêu cầu:

- CRUD/xuất chỉ ADMIN;
- không cung cấp ảnh đánh giá thành tài sản công khai ẩn danh chỉ vì tính năng;
- ứng dụng không commit bài viết/ảnh vào Git;
- không ghi dữ liệu đánh giá vào log ngoài ID/trạng thái an toàn;
- xuất là thao tác ADMIN chủ động;
- `redistributable` mặc định false;
- báo cáo CLI tiếp tục mặc định ID mẫu/chỉ số, không chép đầy đủ bài hoặc ảnh;
- gọi nhà cung cấp bắt buộc gửi đầu vào đánh giá cần để chấm, nên README/tài liệu phải nêu chạy đánh giá sẽ tải nội dung mẫu tới nhà cung cấp đã cấu hình theo thiết lập đó.

## 22. Hành vi xóa/thay

Xóa mẫu chỉ xóa dữ liệu kho đánh giá và tài sản ảnh riêng của nó. Không được ảnh hưởng đề IELTS biên soạn, lượt học viên hoặc lịch sử AI.

Xóa yêu cầu quy ước xác nhận thao tác phá hủy hiện có.

Dọn ảnh thay thế theo khả năng tốt nhất nhưng tuyệt đối không xóa tài sản mới cam kết khi yêu cầu cạnh tranh/lỗi. Theo mẫu dịch vụ lưu trữ hiện có về thứ tự ghi-rồi-cập nhật/dọn.

Số thứ tự ổn định của mẫu lân cận tuyệt đối không được đánh lại.

## 23. Cấu trúc API

Đường cụ thể theo quy ước `/api/v1/admin/...` hiện tại. Về khái niệm cung cấp:

```text
GET    /admin/writing-benchmark/summary
GET    /admin/writing-benchmark/samples?task=1|2
POST   /admin/writing-benchmark/samples
GET    /admin/writing-benchmark/samples/{id}
PATCH  /admin/writing-benchmark/samples/{id}
DELETE /admin/writing-benchmark/samples/{id}
POST   /admin/writing-benchmark/samples/{id}/image     # Task 1
DELETE /admin/writing-benchmark/samples/{id}/image
GET    /admin/writing-benchmark/export
```

Lớp service sở hữu quy tắc dung lượng, đầy đủ, tính tổng, lưu và xuất. Router giữ mỏng.

PATCH tự lưu phải cho payload DRAFT từng phần nhưng xác thực mọi giá trị tiêu chí/trường riêng task được gửi.

Không triển khai bản tương đương công khai/giáo viên.

## 24. Endpoint tổng hợp

Trang không nên tải mọi bài viết chỉ để tạo thống kê phân bố đầu trang.

Cung cấp phản hồi tổng hợp có giới hạn gồm ít nhất:

- số tổng/nháp/hoàn tất theo task;
- số DEV/HOLDOUT theo task;
- biểu đồ tần suất band tổng mẫu hoàn tất theo task;
- biểu đồ tần suất tiêu chí tùy chọn;
- hằng số biểu đồ mục tiêu gợi ý.

Endpoint danh sách trả hàng nhẹ. Chỉ tải đầy đủ đề/bài cho mẫu/chi tiết chọn, không lặp toàn bộ 200 bài mỗi lần làm mới tổng hợp.

## 25. Migration

Tạo một migration Alembic cho bảng/ràng buộc đánh giá sau head duy nhất hiện tại.

Không bảng production hiện có nào cần sửa phá hủy.

Thay đổi cơ sở dữ liệu dự kiến chỉ riêng đánh giá.

Xác minh:

- nâng cấp mới thành công trên PostgreSQL;
- giữ một head Alembic;
- ràng buộc dung lượng/vị trí duy nhất có bảo vệ cạnh tranh cấp service ở nơi CHECK SQL đơn lẻ không biểu diễn được số hàng mỗi task.

Không đặt lại hoặc thay dữ liệu production khi triển khai.

## 26. Chiến lược kiểm thử

Dùng TDD và kiểm thử có trọng tâm khi phát triển.

Kiểm thử backend tối thiểu gồm:

- ADMIN truy cập thành công; USER/TEACHER bị từ chối;
- tạo/cập nhật DRAFT với trường từng phần;
- yêu cầu Task 1 COMPLETE;
- yêu cầu Task 2 COMPLETE;
- xác thực nửa band;
- tổng suy ra khớp tổng hợp production;
- vị trí duy nhất và dung lượng 100 mỗi task, kể cả hành vi service đồng thời/an toàn cạnh tranh khi thực tế;
- xử lý MIME/kích thước/đường lưu ảnh Task 1;
- gỡ/thay ảnh hạ bản ghi COMPLETE không hợp lệ an toàn;
- xóa dọn ảnh thuộc kho đánh giá, không chạm tài sản không liên quan;
- số tổng hợp/phân bố và số DEV/HOLDOUT;
- xuất loại DRAFT;
- cho xuất trước đủ 100 mẫu;
- JSONL Task 1 xác thực qua mô hình `BenchmarkSample` Task 1 hiện có;
- xuất ghi `raters=1` cùng giá trị nguồn gốc/redistributable an toàn;
- đường ZIP không thể vượt thư mục gốc gói;
- CSV quote đúng đề/bài nhiều dòng;
- mô hình đánh giá Task 2 từ chối nhãn không hợp lệ/trường dư;
- định nghĩa chỉ số Task 2 khớp chỉ số điểm Task 1 dùng chung;
- nhãn người Task 2 tuyệt đối không vào prompt nhà cung cấp;
- danh tính tiếp tục/cache Task 2 đổi khi mẫu/nhãn/mô hình/hợp đồng prompt đổi;
- suy luận Task 2 thất bại vẫn có trong báo cáo.

Kiểm thử frontend có trọng tâm gồm:

- chốt truy cập `/admin/writing-benchmark`;
- thẻ Task 1/Task 2 và số tiến độ;
- chọn danh sách/chi tiết;
- trạng thái DRAFT/COMPLETE;
- trì hoãn gộp tự lưu và giữ dữ liệu khi lỗi lưu;
- lưu ngay Ctrl/Cmd+S nơi triển khai;
- luồng hoàn tất và tiếp theo;
- xem trước/thay/gỡ ảnh Task 1;
- bộ chọn tiêu chí và tổng suy ra;
- công cụ lập phân bố band tổng;
- số DEV/HOLDOUT;
- tóm tắt/thao tác xuất;
- hành vi nút mẫu mới tối đa 100;
- hiển thị danh sách/chi tiết thích ứng không tràn ngang.

Xác minh tính năng thường không yêu cầu trình duyệt/Playwright/AI thật trừ khi kiểm thử có trọng tâm phát hiện vấn đề không thể chẩn đoán cách khác.

## 27. CI và ràng buộc triển khai

Triển khai phải kiểm tra mốc CI từ xa hiện tại trước làm tính năng và SHA cuối đã push sau đó.

Dùng kiểm thử cục bộ có trọng tâm khi lặp. Không dùng hạn mức cho gọi mô hình thật, Modal, suy luận GPU hoặc E2E trình duyệt rộng cho tính năng quản lý dữ liệu này.

Kiểm thử CLI Task 2 dùng nhà cung cấp/dữ liệu mẫu giả. Kiểm tra nhanh Colab thật một mẫu là luồng thủ công sau triển khai, không là kiểm thử CI.

Thay đổi cuối cần giữ:

- một head Alembic;
- tương thích đánh giá Task 1 hiện có;
- hành vi Writing chấm trước production hiện có;
- ngữ nghĩa prompt AI Task 1/Task 2 trừ khi nhiệm vụ hiệu chỉnh độc lập sau thay đổi;
- ranh giới dữ liệu học viên/quản trị/Builder bình thường.

## 28. Luồng vận hành sau triển khai

Luồng người dùng dự kiến:

```text
1. ADMIN opens /admin/writing-benchmark
2. enters/labels samples over time; autosave keeps DRAFT state
3. completes up to 100 Task 1 and 100 Task 2 samples
4. watches distribution planner while curating labels
5. marks ~80 DEV / ~20 HOLDOUT per task
6. exports ZIP at any point, including before bank completion
7. uploads ZIP to Google Colab
8. runs Task 1 and/or Task 2 CLI
9. compares MAE/QWK/bias/agreement/latency/failures
10. prompt/model changes are evaluated on DEV; HOLDOUT is reserved for final checks
```

Kho quản trị chỉ giữ dữ liệu nhãn chuẩn nguồn. Đầu ra đánh giá nằm ngoài cơ sở dữ liệu production.

## 29. Tiêu chí nghiệm thu

Tính năng được chấp nhận khi mọi điều sau thỏa:

- chỉ ADMIN truy cập được CRUD/ảnh/xuất;
- có một kho, không UX/schema phiên bản dữ liệu;
- Task 1/Task 2 giới hạn độc lập 100 mẫu;
- một bộ nhãn con người bốn tiêu chí do ADMIN nhập là chuẩn mỗi mẫu;
- tổng luôn suy ra bằng phép tính chấm production;
- tự lưu DRAFT hỗ trợ bài chưa đủ an toàn;
- xác thực COMPLETE ngăn mẫu thiếu vào bản xuất;
- ảnh Task 1 lưu riêng tư qua lưu trữ tài sản hiện có;
- trang hướng dẫn rõ band tổng/phân tập mà không ép chỉ tiêu giả;
- bản xuất Task 1 dùng trực tiếp được bởi CLI Task 1 hiện tại;
- Task 2 có CLI riêng cùng định nghĩa chỉ số đồng thuận điểm;
- ZIP gồm JSONL chuẩn, ảnh và CSV tiện xem;
- Colab chỉ cần gói xuất, mã kho và cấu hình nhà cung cấp chấm, không thông tin cơ sở dữ liệu production/quản trị;
- không ghi dự đoán/kết quả đánh giá vào cơ sở dữ liệu ứng dụng;
- CI và hành vi đánh giá Task 1 hiện có tiếp tục đạt.
