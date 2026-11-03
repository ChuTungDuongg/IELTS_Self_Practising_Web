# Đánh giá Task 1 (T1-C)

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: mô tả đánh giá Task 1 (T1-C). Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../../scripts/benchmark_task1.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../docs/modules/writing.md); [kiểm toán và giới hạn](../../docs/DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải kết quả chạy lại trong đợt kiểm toán này.

CLI tái sử dụng tiếp nhận thị giác có căn cứ từ sản xuất, DePlot tùy chọn cho phép tiếp tục khi lỗi, dữ kiện tất định, kiểm chứng phát biểu, bằng chứng nguồn và MTS bốn tiêu chí. Không cần cơ sở dữ liệu. Sản xuất dùng dấu vân tay tổng hợp `mts-task1-visual-v12`, hợp đồng nhận thức `mts-task1-visual-v3` và hướng dẫn chấm `mts-task1-scoring-v12`. Phiên bản ứng viên mặc định là v12, gồm nhận xét ngắn và chú thích nội tuyến tư vấn. V12 thêm kiểm chứng thận trọng nhận xét LR/GRA; ngữ nghĩa điểm không đổi từ v10. Bản v11 đóng băng vẫn có qua --scoring-version v11. V7/v8 lịch sử giữ hợp đồng đầu ra gộp; báo cáo lịch sử vẫn đọc được. `--scoring-version both` so nền v5 đóng băng với v12, tái sử dụng cùng bài viết, điểm người chấm, chuỗi/hợp đồng nhận thức, nhà cung cấp/mô hình và cấu hình bộ chuyên đọc biểu đồ. Lời nhắc v3 lịch sử vẫn có rõ ràng qua `--scoring-version v3`; v4/v6 không đóng băng không phải bí danh lời nhắc hiện hành. Siêu dữ liệu báo cáo v6 cũ vẫn đọc được. CLI này không chạy Task 2.

V6 đưa vào phân biệt Task Achievement theo mức khớp mô tả band lân cận: Band 7 cho phép vài thiếu sót/sơ suất cục bộ, Band 8 cho phép thỉnh thoảng có, không đòi hoàn hảo hoặc bỏ qua điểm yếu đáng kể. Chọn bằng chứng TA thể hiện mức đáp ứng toàn bài thay vì đào tìm lỗi. Không có độ lệch cộng, sàn, trần hoặc tự tăng tay điểm. Nền tảng dữ kiện, nhận thức v3 và ngữ cảnh mô tả LR/GRA không đổi; hợp đồng đầu ra đổi ở v9.

V7 giữ hướng dẫn TA và thêm phân biệt CC theo tiến triển, nhóm ý, quan hệ và liên kết thật toàn bài. Từ nối thông thường nhìn thấy và lặp thực thể chính xác không tự là điểm yếu. Bằng chứng CC thể hiện toàn bài, không có band mục tiêu hoặc hạn ngạch. Không cộng độ lệch, sàn hoặc thưởng điểm. Không tuyên bố tăng độ chính xác nếu thiếu so sánh có nhãn người chấm.

## Tập dữ liệu cục bộ

Dùng bản kê UTF-8 JSONL: mỗi dòng một mẫu có phiên bản lược đồ. `schema_version: 1` là tương thích định dạng, không phải phiên bản ngân hàng/tập dữ liệu. Ngân hàng ADMIN xuất bản kê một người chấm tương thích trực tiếp; xem [hướng dẫn ngân hàng/Colab](../../docs/writing-benchmark-bank.md). `manifest.schema.json` được sinh là hợp đồng đầu vào. Trường cần có:

- `schema_version: 1`, `id` ASCII duy nhất, `split: dev | holdout` và `task_type` Task 1 từ registry sản xuất.
- `prompt`, `essay`, `image_path`. Đường dẫn tuyệt đối hoặc tương đối với bản kê. Chỉ nhận hình PNG/JPEG/WebP cục bộ tối đa 10 MiB; không tải hình từ URL.
- `human_scores` gồm `ta`, `cc`, `lr`, `gra`, mỗi điểm 0–9 theo nửa band. Dùng điểm người chấm đã thống nhất/phân xử hoặc nguồn tham chiếu được cho phép. Không gán dự đoán mô hình khác thành dữ liệu chuẩn.
- `raters` (mặc định 1), `provenance` mô tả tác giả/giấy phép và nguồn điểm, `redistributable`. Một người chấm là đủ; giữ điểm đích thống nhất và số người chấm, không âm thầm làm tròn trung bình.
- `visual_truth` tùy chọn: cấu trúc VisualReference có kiểu của sản xuất, với nhãn nhóm/chuỗi/ô và giá trị biểu đồ/bảng được gán độc lập. Cần chú giải ngữ nghĩa đầy đủ cho thành phần đã chọn. Nhãn và đơn vị có ý nghĩa; ID thành phần/chuỗi không diễn giải nội dung thì không. Dữ liệu chuẩn chưa biết hoặc ước lượng không xác nhận nhận thức chính xác. Họ thị giác khác có thể benchmark điểm nhưng hiện chưa có chỉ số dữ kiện tự động.

Với nhiều biểu đồ tròn chung chú giải/đơn vị, chú giải một thành phần `pie_chart`: nhóm là vùng, chuỗi là nhóm trong chú giải, mỗi chuỗi có một điểm cho mỗi vùng. Phần trăm dùng đơn vị số biểu đồ: 48 nghĩa là 48%, không phải 0.48.

Giữ dữ liệu riêng tư/có giấy phép ở `private/` hoặc ngoài kho mã. Benchmark không sao chép hình/bài viết nguồn hoặc tải nội dung lên ngoài nhà cung cấp chấm đã cấu hình và DePlot hiện có được yêu cầu rõ ràng. `private/`, tập JSONL/hình và báo cáo/bộ nhớ đệm sinh ra được bỏ qua ở đây. Đường dẫn đầu ra tùy chọn ngoài cây này cần quy tắc bỏ qua riêng. Báo cáo/điểm kiểm tra không chứa bài viết, trích dẫn, phản hồi thô, nhãn/giá trị biểu đồ hoặc URL bí mật; chỉ giữ ID, băm, điểm, số đếm và mã trạng thái an toàn.

## Lệnh

Từ `backend/`, trước hết xác thực dữ liệu cục bộ không suy luận:

```powershell
uv run python ../scripts/benchmark_task1.py --manifest ../benchmarks/writing_task1/private/manifest.jsonl --split dev --scoring-version v12 --chart-specialist off --dry-run --output ../benchmarks/writing_task1/reports/dev-plan
```

Chạy thử thật một mẫu rõ ràng, dùng cấu hình nhà cung cấp backend hiện có:

```powershell
uv run python ../scripts/benchmark_task1.py --manifest ../benchmarks/writing_task1/private/manifest.jsonl --split dev --limit 1 --scoring-version v12 --chart-specialist off --allow-live --resume --output ../benchmarks/writing_task1/reports/dev-smoke
```

So sánh nền v5 / ứng viên v12 có kiểm soát với cấu hình bộ chuyên đọc cố định:

```powershell
uv run python ../scripts/benchmark_task1.py --manifest ../benchmarks/writing_task1/private/manifest.jsonl --split dev --scoring-version both --chart-specialist off --allow-live --resume --output ../benchmarks/writing_task1/reports/dev-v5-v12
```

Để so thêm DePlot tắt/bật:

```powershell
uv run python ../scripts/benchmark_task1.py --manifest ../benchmarks/writing_task1/private/manifest.jsonl --split dev --scoring-version both --chart-specialist both --allow-live --resume --output ../benchmarks/writing_task1/reports/dev-ablation
```

`both` × `both` chạy bốn cấu hình **mỗi mẫu**: v5/v12 × DePlot tắt/bật. So sánh biến thể chấm báo v5 là nền, v12 là ứng viên, kèm độ lệch có dấu TA, MAE và chênh lệch đồng thuận theo ứng viên trừ nền. `--limit` giới hạn số mẫu duy nhất, không phải số yêu cầu nhà cung cấp. Chế độ bật bộ chuyên đọc chỉ áp dụng họ biểu đồ/bảng, cho phép tiếp tục khi lỗi và có thể quay về dự phòng nếu không khả dụng. Chạy thử một mẫu/một cấu hình trước. Ứng dụng không tự khởi động benchmark. Từ gốc kho mã, điểm vào tương đương là `uv run --project backend python -m scripts.benchmark_task1 ...`.

Dùng `--split holdout` với thư mục đầu ra khác cho tập đánh giá cuối chưa đụng tới. Chỉ phát triển lời nhắc trên dev; xem/tinh chỉnh lặp dựa vào holdout làm mất mục đích giữ riêng. Điểm đích và chú giải không được gửi tới nhà cung cấp chấm hoặc bộ chuyên đọc.

Mọi lệnh không có `--dry-run` cần `--allow-live`; API key không tự bật inference. Cờ này không bảo đảm trần dollar. So sánh OpenAI Luna A–D có chế độ `--openai-ablation --dry-run` riêng; live bị khóa đến khi có cost admission đáng tin cậy. Xem [giao thức, giới hạn và lệnh chuẩn](../../docs/writing-benchmark-bank.md#openai-luna-ablation); baseline v5/v12 ở trên là đối chiếu prompt lịch sử, không phải A–D inference policy.

## Báo cáo và tiếp tục

Mỗi thư mục đầu ra chứa `report.json`, `report.md`, `disagreements.csv`, điểm kiểm tra `cache/` nguyên tử mỗi mẫu/cấu hình và bản ghi `attempts/` chỉ thêm để giữ lỗi/chi phí trước. Mặc định báo cáo dùng ID thay cho bài viết đầy đủ. Nội dung gồm:

- Đồng thuận chính xác, ±0.5, ±1.0, MAE, độ lệch dự đoán trừ điểm đích có dấu, RMSE và QWK cho tiêu chí cùng tổng Task 1 làm tròn bởi backend.
- Số mẫu cho mọi tổng hợp, nhóm loại/họ tác vụ/phần chia và nhóm band đích từng tiêu chí. QWK cần ít nhất 10 cặp nửa band so sánh được và phương sai kỳ vọng khác 0; nếu không JSON ghi lý do không khả dụng.
- Nhận thức chính và sau đối chiếu riêng: đồng thuận số có nhãn, khớp ngữ nghĩa, giá trị thiếu/thừa/chưa biết và bất đồng đối chiếu.
- Phân rã lỗi từng mẫu, thời gian thực, số yêu cầu hoàn thành/mức dùng token, số gọi/thời gian/dự phòng bộ chuyên đọc và điểm ngôn ngữ một phần sau lỗi chính thật. Đồng thuận tổng chỉ dùng kết quả đủ bốn tiêu chí.
- So sánh biến thể theo cặp và bất đồng điểm lớn nhất theo ID. Lượt thất bại vẫn hiển thị, không biến mất khỏi thống kê lỗi. Chênh lệch điểm dùng cùng cặp hợp lệ cho từng tiêu chí. So lỗi/độ trễ cũng gồm ca thất bại; rơi mẫu không được giả thành đồng thuận tốt hơn.

Danh tính tiếp tục gồm nội dung/điểm đích/dữ liệu thị giác chuẩn, byte hình, nhà cung cấp/mô hình, điểm cuối đã băm, phiên bản nhận thức/chấm riêng, mô hình/bản sửa/hợp đồng bộ chuyên đọc đã ghim, cấu hình thời gian chờ, phiên bản benchmark và băm triển khai. Đường dẫn/nhãn trình bày không đổi danh tính. Đổi chú giải vô hiệu hóa điểm kiểm tra để tránh chỉ số cũ. `--resume` chỉ tái sử dụng bản ghi thành công đã xác thực; điểm kiểm tra hỏng có thể phục hồi từ lần thử mới nhất đã xác thực, còn thất bại hoặc bản ghi hợp lệ không khả dụng sẽ thử lại. Lần thử/điểm kiểm tra nguyên tử được ghi sau mỗi lần chạy để gián đoạn không mất thành công trước. Trúng bộ nhớ đệm giữ độ trễ/mức dùng lịch sử; `new_*_calls` không tính lần trúng. Chỉ số điểm mô tả kết quả mới nhất. Thống kê vận hành tách tỷ lệ lỗi lần đầu và mọi lần ghi nhận, cùng số gọi, mức dùng và độ trễ lũy kế. Thử lại thành công không xóa lỗi/chi phí đã ghi trước đó. Yêu cầu đang chạy bị gián đoạn có mức dùng cuối chưa biết; thống kê chỉ bao phủ bản ghi lần thử đã hoàn tất.

## Diễn giải

Độ lệch có dấu dương nghĩa là chấm rộng, âm nghĩa là chấm thấp. Đọc riêng từng tiêu chí để lỗi trái dấu không triệt tiêu trong tổng. Với v5/v12, xem độ lệch TA có dấu, MAE và đồng thuận chính xác/trong khoảng band cùng nhau; riêng dịch điểm lên không chứng minh chính xác hơn. Hai phiên bản gọi cùng chuỗi nhận thức nhưng nhận thức trực tiếp vẫn có thể biến thiên giữa lần chạy. Dùng chỉ số nhận thức chính/sau đối chiếu để nhận ra yếu tố nhiễu thay vì quy mọi chênh lệch TA cho lời nhắc.

- Nhận thức sai và TA bất đồng: kiểm tra nhận thức/đối chiếu.
- Nhận thức đúng nhưng TA bất đồng: kiểm tra hướng dẫn Task Achievement.
- CC/LR/GRA lệch dương khi nhận thức tốt: kiểm tra hiệu chuẩn bộ chấm.
- Thiên lệch diện rộng còn sau sửa lời nhắc: đánh giá bộ chấm mạnh hơn hoặc bộ phân xử mô tả chỉ dùng benchmark trước khi đưa công cụ vào sản xuất.

Nhóm lỗi gồm nhận thức đúng với điểm đúng/cao/thấp/hỗn hợp, PERCEPTION_ERROR, SPECIALIST_DISAGREEMENT, UNUSABLE và biến thể nhận thức chưa chú giải rõ ràng. Điểm đúng nghĩa là mỗi tiêu chí cách tham chiếu không quá 0.5; quy ước đánh giá này không đổi dự đoán. Bất đồng bộ chuyên đọc không xác lập bên đọc nào đúng; cần dữ liệu thị giác chuẩn độc lập.

Chưa triển khai bộ phân xử thử nghiệm, giám khảo thứ hai, tự triển khai, độ lệch số cộng thêm, trần band hoặc tự hiệu chuẩn sản xuất. Kiểm thử tổng hợp nhỏ chứng minh phép tính/điều phối; hiệu quả cần tập có nhãn người chấm.
