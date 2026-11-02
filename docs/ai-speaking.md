# Kiến trúc và đánh giá Speaking của BandPilot

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho chủ đề này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác thực trực tiếp trên hệ thống chạy.
> Mục đích: mô tả kiến trúc và đánh giá Speaking của BandPilot. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [phần triển khai](../backend/app/services/speaking_ai_worker.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](modules/speaking.md); [kiểm toán và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark bên dưới thuộc lần thực hiện gốc, không phải kết quả chạy lại trong đợt kiểm toán này.

Speaking P1–P8 đã được triển khai. Mọi band và nhận xét AI đều mang tính tư vấn: dự án chưa có bằng chứng benchmark xác lập độ chính xác tương đương giám khảo. P8 thêm bộ chạy đánh giá, không thay điểm hoặc lược đồ sản xuất.

## Vận hành và chấm điểm

Next.js cung cấp câu hỏi đã soạn, kiểm tra micro trước khi làm bài, ghi âm và xem lại. FastAPI sở hữu chuyển trạng thái câu hỏi, dấu thời gian/hạn chót, hạn chế thử lại và phân quyền tệp âm thanh riêng tư. PostgreSQL lưu phiên bản đề đóng băng và nguồn gốc lượt làm bài; bộ chứa âm thanh nằm trong kho riêng tư. Tải đoạn dữ liệu có thể lặp an toàn. Khôi phục sau tải lại giữ thời gian còn lại của máy chủ và cấp một khoảng chuẩn bị bù bảy giây mà không tăng hạn mức nói. Bộ ghi khôi phục tạo phân đoạn chứa riêng. Xác nhận tải lên cuối cùng phải có trước khi chuyển tiếp. Ghi chú riêng không tham gia đầu vào chấm lời nói.

Chuỗi xử lý là âm thanh gốc đã chốt → PCM mono 16 kHz chuẩn hóa → cổng chất lượng → ASR nguyên văn có mốc thời gian từ → định dạng sạch và đặc trưng độ lưu loát/âm học có phiên bản → đánh giá tổng thể FC/LR/GRA/PR. Các bộ chứa khôi phục giải mã riêng trước khi nối PCM. Văn bản sạch giữ nguyên từ và ngữ pháp của người làm bài. Trên Modal, Web chạy FFmpeg, chất lượng, độ lưu loát và bằng chứng phát âm trên CPU; chỉ WAV chuẩn hóa đi từ FastAPI đến dịch vụ faster-whisper T4 riêng được bảo vệ qua proxy. Bộ nhớ đệm mô hình large-v3 đã ghim nằm trên `ielts-speaking-asr-model-cache`; âm thanh yêu cầu dùng tệp tạm riêng tư có thể hủy ngoài Volume đó. Dịch vụ Ministral L4 hiện có phục vụ cả chấm tiêu chí Writing và Speaking. Hai dịch vụ GPU đều có số container tối thiểu bằng 0, nên riêng khởi động Web không nạp mô hình nào. Lần chép lời đầu có thể gồm tải/nạp mô hình và chờ hàng đợi; không suy độ trễ ổn định từ nó. Đặc trưng thời gian mô tả lời nói, không tự gán band theo công thức. Phát âm cần bằng chứng âm thanh đã đo, không thể thành công chỉ từ văn bản chép lời hoặc độ tin cậy ASR. Âm thanh không đánh giá được hoặc thiếu bằng chứng phát âm khiến tiêu chí không khả dụng, không bịa điểm 0 hay trung bình.

`SpeakingScorer` xác thực điểm nửa band trước, lưu qua điểm kiểm tra, rồi yêu cầu nhận xét hữu hạn. Lỗi nhận xét giữ điểm hợp lệ. Điểm tổng sản xuất dùng trọng số đều FC/LR/GRA/PR và cách làm tròn nửa band của dự án; thiếu một tiêu chí khiến tổng không khả dụng. Worker và sự kiện bền vững hỗ trợ hủy, kết nối lại và khởi động lại. Speaking tích hợp Full Mock, lịch sử và kết quả lớp học. Giáo viên đọc bản ghi/bản chép lời và AI tư vấn qua nguồn gốc bài giao, có thể lưu điểm cuối do người chấm rõ ràng cho bài giao lớp mình. Lượt cá nhân không liên quan vẫn riêng tư.

## Đầu vào benchmark riêng tư

Bộ chạy tuân theo quy ước `app/evaluation` và thư mục `scripts` gốc hiện có. Dùng bản kê UTF-8 JSONL, mỗi dòng một phần thể hiện trọn vẹn đã được gán nhãn:

```json
{"schema_version":1,"id":"synthetic-001","responses":[{"audio_path":"audio/fictional.wav","part_number":1,"prompt_type":"SHORT_ANSWER","prompt_text":"Describe a fictional garden."}],"human":{"fc":6,"lr":6.5,"gra":7,"pr":6.5,"overall":6.5},"subgroups":{"recording_environment":"quiet"},"assessor_version":"fictional-rater-v1"}
```

Ví dụ này là hư cấu, không phải bằng chứng đánh giá của người chấm. Mỗi câu trả lời cần đúng một `audio_path` hoặc `fixture_id` có kiểm soát; đường dẫn phân giải cạnh bản kê và có thể trỏ tới tệp riêng ngoài git. ID dữ liệu mẫu dành cho bộ nạp kiểm thử ngoại tuyến được tiêm; bộ nạp âm thanh thật từ chối chúng an toàn. Cần câu hỏi để tái tạo đánh giá theo ngữ cảnh. `test_reference` tùy chọn là định danh không diễn giải nội dung. Siêu dữ liệu người chấm chỉ là mã phiên bản không nhận diện cá nhân. Cả năm nhãn người chấm đều phải là số hữu hạn 0–9 theo bước nửa band; tổng của người chấm là nhãn độc lập, không tính lại từ tiêu chí. Trường lạ, ID/khóa JSON trùng và khóa phân nhóm nhạy cảm bị từ chối. Đầu vào giới hạn 16 MiB và 10,000 mẫu; xác thực xem mọi dòng kể cả khi `--max-samples` chỉ đánh giá N mẫu đầu.

Giữ âm thanh người làm bài, bản kê, cấu hình dotenv riêng và kết quả ngoài git hoặc trong `benchmarks/speaking/private/` và `benchmarks/speaking/reports/` đã bỏ qua. Cần sự cho phép và kiểm giấy phép trước khi xử lý lời nói qua nhà cung cấp bên ngoài. Không commit đề có bản quyền, bản ghi riêng hoặc bản chép lời nhận diện cá nhân. Quy tắc Git bỏ qua là lớp bảo vệ bổ sung, không phải quyền phân phối dữ liệu nơi khác.

## Quy trình ngoại tuyến

Từ `backend/`, xác thực bản kê không khởi tạo nhà cung cấp:

```powershell
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --validate-manifest
```

Để tạo báo cáo ngoại tuyến, nhập kết quả chỉ có điểm từ một lần chạy bộ chấm hiện có:

```powershell
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --predictions ../benchmarks/speaking/private/predictions.json --output ../benchmarks/speaking/reports/offline
```

JSON dự đoán có `schema_version: 1`, đối tượng `provenance` bắt buộc (hợp đồng `ScorerProvenance`) và `predictions`; mỗi mục gồm `id`, `scores` FC/LR/GRA/PR theo nửa band hoặc null và `reasons` tùy chọn thuộc danh sách cho phép. Không cung cấp tổng: bộ chạy gọi `speaking_overall` sản xuất. Mẫu/tiêu chí thiếu vẫn là lỗi trong mẫu số. ID mẫu lạ, văn bản lỗi tùy ý, bản chép lời và trường dư bị từ chối. Siêu dữ liệu nhà cung cấp nhập vào là khai báo của tác giả kết quả, không chứng minh nhà cung cấp đã được gọi.

Để chạy thử ngoại tuyến chỉ với dữ liệu tổng hợp, tạo tệp bằng đoạn Python sau từ `backend/`, rồi chạy hai lệnh trên:

```python
import json
from pathlib import Path
from app.core.config import Settings
from app.evaluation.speaking.models import provenance

root = Path("../benchmarks/speaking/private")
root.mkdir(parents=True, exist_ok=True)
sample = {"schema_version": 1, "id": "synthetic-001", "responses": [
    {"fixture_id": "fictional-tone", "part_number": 1,
     "prompt_type": "SHORT_ANSWER", "prompt_text": "Describe a fictional garden."}],
    "human": {"fc": 6, "lr": 6.5, "gra": 7, "pr": 6.5, "overall": 6.5}}
identity = provenance(Settings()).model_copy(update={
    "provider": "fixture", "model": "synthetic-v1",
    "asr_provider": "fixture", "asr_model": "synthetic-v1"})
(root / "manifest.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
(root / "predictions.json").write_text(json.dumps({"schema_version": 1,
    "provenance": identity.model_dump(mode="json"), "predictions": [
        {"id": sample["id"], "scores": {"fc": 6, "lr": 6, "gra": 6, "pr": 6}}]}),
    encoding="utf-8")
```

Dự đoán tổng hợp kiểm phép tính và hợp đồng tệp, không đo được độ chính xác thật của bộ chấm. Kiểm thử tự động dùng bằng chứng tổng hợp và nhà cung cấp giả:

```powershell
uv run pytest tests/test_speaking_benchmark.py tests/test_speaking_benchmark_metrics.py -q
```

## Chấm thủ công với cấu hình nhà cung cấp

Chấm trực tiếp yêu cầu `--allow-live` rõ ràng. CLI đọc cùng `Settings` backend với sản xuất; `--config` chọn tệp dotenv riêng mà không đặt bí mật trong đối số lệnh. Với ASR cục bộ, đặt `SPEAKING_ASR_PROVIDER=local`, cài gói bổ sung `backend[speech]` và trỏ `SPEAKING_ASR_MODEL_DIRECTORY` tới mô hình cục bộ đầy đủ. Với ASR Modal, đặt `SPEAKING_ASR_PROVIDER=modal`, `SPEAKING_ASR_ENABLED=true`, `SPEAKING_ASR_BASE_URL` được bảo vệ, `SPEAKING_ASR_MODEL` đã ghim, `SPEAKING_ASR_MODEL_REVISION`, `SPEAKING_ASR_VERSION`, cùng `AI_WRITING_MODAL_KEY`/`AI_WRITING_MODAL_SECRET` chỉ ở backend. Web sản xuất tự nạp các cấu hình này; đánh giá thủ công cục bộ cần cấu hình riêng. Bật truyền tải LLM Speaking hiện có và nhà cung cấp phát âm riêng biệt. Quy trình benchmark không thêm bộ tải tập dữ liệu/mô hình.

```powershell
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --allow-live --config ../benchmarks/speaking/private/providers.env --output ../benchmarks/speaking/reports/candidate --resume
```

Bộ tiếp hợp gọi hợp đồng bộ chuẩn hóa, chất lượng, ASR, đặc trưng và `SpeakingScorer` hiện có, không tạo bộ chấm thứ hai. WAV đầu vào phải sẵn mono 16 kHz PCM có dấu 16 bit; WebM/Ogg/MP4/M4A dùng bộ giải mã FFmpeg sản xuất có giới hạn. Một tệp biểu diễn một bộ chứa câu trả lời đầy đủ. Cung cấp đầu vào bất biến; chuyển đổi dùng tệp tạm riêng tư. Tệp gốc không hỗ trợ, thiếu hoặc quá lớn (giới hạn 128 MiB), lỗi chất lượng và lỗi nhà cung cấp tạo mã lỗi an toàn. Không đổi dòng lượt làm bài hoặc điểm sản xuất.

`predictions.json` được ghi điểm kiểm tra nguyên tử trước mỗi yêu cầu nhận xét. Tiếp tục chỉ tái sử dụng mẫu đã đủ điểm khớp chính xác mẫu, băm nội dung âm thanh, cấu hình và nguồn gốc; mẫu thất bại/một phần được thử lại. Đây là quy trình cục bộ tuần tự: không để nhiều tiến trình cùng ghi một thư mục đầu ra. Lỗi nhận xét không bị tính là không chấm được nếu điểm tiêu chí đã lưu. Lỗi nhà cung cấp vẫn hiện trong tỷ lệ thất bại cuối; CLI thoát 0 nghĩa là đã tạo báo cáo, không phải mọi mẫu đều chấm được. Lỗi đầu vào/I/O trả mã thoát 2 cùng mã lỗi hữu hạn. Kiểm thử thường không gọi ASR/LLM trực tiếp, Modal hoặc dịch vụ GPU.

## Báo cáo và chỉ số

Đầu ra tất định gồm `summary.json`, `summary.md`, `samples.csv`, `samples.jsonl` và điểm kiểm tra điểm số khi chấm có cấu hình. Báo cáo chứa ID mẫu, band, sai số có dấu và mã nguyên nhân an toàn, không chứa nội dung âm thanh, bản chép lời, câu hỏi, đường dẫn hệ thống tệp, suy luận ẩn hoặc thông điệp nhà cung cấp. Tóm tắt gồm bất đồng lớn nhất, phân phối sai số có dấu và các nhóm hiệu chuẩn mô tả theo band người chấm. Những nhóm này không hiệu chỉnh điểm.

Cả năm tiêu chí đều có số lượng tổng/hợp lệ, độ bao phủ và tỷ lệ không chấm được/thất bại. MAE là trung bình trị tuyệt đối của sai số dự đoán trừ người chấm; RMSE là căn trung bình bình phương. Pearson đo liên hệ tuyến tính; Spearman dùng hạng trung bình cho trường hợp bằng nhau. Quadratic Weighted Kappa so sánh bất đồng bình phương theo nhóm quan sát với kỳ vọng từ phân phối biên trên 19 ô nửa band từ 0 đến 9 của dự án. Đồng thuận trong ±0.5/±1.0 và chính xác là tỷ phần trên cặp hợp lệ. Tương quan không đồng nghĩa đồng thuận: bộ chấm bị lệch có thể tương quan tốt nhưng MAE lớn.

Thống kê cặp loại dự đoán thiếu, nhưng lỗi luôn giữ trong mẫu số độ bao phủ. Tương quan cần ít nhất ba cặp hợp lệ; QWK cần năm. Quá ít cặp, vector hằng hoặc bất đồng kappa kỳ vọng bằng 0 trả null kèm trạng thái giải thích, không trả NaN. Nhóm toàn lỗi vẫn tạo báo cáo. Phân nhóm tùy chọn gồm môi trường ghi âm, nhóm trình độ, nhóm câu hỏi hoặc loại micro. Mặc định mỗi nhóm cần 20 mẫu có nhãn; `--minimum-subgroup-samples` cấu hình được với sàn năm. Nhóm nhỏ bị ẩn; thống kê cặp còn lại vẫn áp giới hạn mẫu riêng. Không phân tích nhân khẩu nhạy cảm hoặc tuyên bố công bằng từ mẫu nhỏ.

Mọi kết quả ghi bộ chấm/nhà cung cấp/mô hình, thang chấm/lời nhắc, hợp đồng điểm/nhận xét, nhà cung cấp/mô hình/phiên bản/căn chỉnh ASR, phiên bản chuẩn hóa, chất lượng, độ lưu loát và phát âm, băm cấu hình/triển khai và git SHA nếu có. Bí mật và đường dẫn thư mục mô hình được băm, không xuất ra. Trọng số mô hình và hành vi triển khai phải được ghim, phiên bản khai báo phải tăng khi đổi; riêng tên mô hình không định danh được trọng số có thể thay đổi. So sánh các lần chạy phải dùng cùng băm nhóm dữ liệu, nhãn và giao thức chỉ số, đồng thời xem thay đổi tỷ lệ lỗi cùng mức đồng thuận. Không tự động đưa phiên bản mới vào sản xuất.

## Dữ liệu nghiên cứu và chính sách hiệu chuẩn

[Speak & Improve Corpus 2025](https://researchdatasets.cambridge.org/datasets/speak-and-improve-corpus-2025) chứa nhãn CEFR tổng thể mang tính chỉ dẫn. Đơn vị xuất bản hạn chế phân phối và sử dụng, gồm giấy phép nghiên cứu/giáo dục phi thương mại và yêu cầu phê duyệt khi công bố tài liệu dẫn xuất; cần kiểm điều khoản và chính sách lưu giữ của nhà cung cấp trước. [SpeechOcean762](https://github.com/jimbozhang/speechocean762) hướng tới đánh giá phát âm. [L2-ARCTIC](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/) hỗ trợ nghiên cứu lời nói/phát âm của người không bản ngữ. Các tập này và tập phát âm khác có thể hỗ trợ xác minh phụ trợ; không tập nào tự cung cấp dữ liệu chuẩn chính thức IELTS FC/LR/GRA/PR. Kiểm riêng giấy phép, sự đồng ý và cách dùng được phép hiện hành của mỗi tập. Không đóng gói bản tải xuống hoặc bản ghi ở đây.

Không ánh xạ trực tiếp điểm SpeechOcean hoặc độ tin cậy ASR sang IELTS Pronunciation hay điểm tổng. Cần benchmark phần thể hiện đại diện, gán nhãn độc lập, có mức đồng thuận giữa người chấm và đánh giá trên dữ liệu giữ riêng trước khi tuyên bố độ chính xác. Dùng kết quả để nhận diện thiên lệch, so phiên bản, phát hiện hồi quy và quyết định cần hiệu chuẩn hay không. Một lần chạy nhỏ không đủ căn cứ đặt độ lệch sản xuất. Biến đổi tương lai phải rõ ràng, có phiên bản, được xem xét riêng và xác minh trên dữ liệu giữ riêng. P8 không có hiệu chuẩn ẩn hoặc thao túng điểm.

## Luyện kỹ năng theo từng Part

`/practice` cung cấp toàn bộ Part Speaking đã xuất bản. Part 1 và Part 3 hỗ trợ luyện câu hỏi Có hướng dẫn hoặc Tự do; Part 2 luôn Có hướng dẫn. Khởi tạo dùng `SPEAKING_PART`, `PRACTICE` và đồng hồ lượt làm bài đếm tăng. Hạn chót câu hỏi đã soạn vẫn kiểm soát chuẩn bị/ghi âm. Lượt `SPEAKING_PROMPT` cũ giữ nguyên phạm vi.

Chọn tự do được lưu qua `POST /speaking-attempts/{id}/select-prompt`, không tự ghi âm. Chuyển khi đang ghi cần dừng, đóng tải lên, nhận xác nhận bền vững cho câu trả lời, rồi chọn câu khác. Lần ghi đã chốt vẫn là dự phòng tới khi bản thay thế chốt xong. `POST /speaking-attempts/{id}/finish-practice` rõ ràng cần ít nhất một câu đã lưu và cho phép còn câu chưa trả lời. Trang xem lại hiển thị câu đó không có âm thanh/bản chép lời. Điểm Part vẫn là bản ghi luyện tập có phạm vi, không góp vào band Speaking đầy đủ, điểm tổng Full Mock hoặc Analytics toàn mô-đun. Khởi tạo toàn Part từ lớp học bị từ chối. Migration `20261013_0034` thêm phạm vi và luồng này.

## Điểm cuối Speaking do người chấm

Chủ sở hữu bài luyện cá nhân có thể nhập tay FC/LR/GRA/PR hoặc chép kết quả AI hiện hành đã hoàn tất vào biểu mẫu, chỉnh sửa rồi Lưu rõ ràng. AI không tự ghi điểm cuối. Học viên lớp chỉ xem điểm cuối hoặc “Đang chờ giáo viên chấm”. Nhân sự có quyền chấm của lớp được lưu/sửa tiêu chí qua đúng nguồn gốc bài giao. ADMIN chỉ quan sát lớp và không được ghi điểm cuối cho bài của lớp, kể cả qua route cá nhân; quyền chấm bài luyện cá nhân của nền tảng được xét riêng. Chấm của giáo viên không cấp quyền tạo lại transcript hoặc sửa tệp gốc. Xem [GradingPolicy hiện hành](../backend/app/services/grading_policy.py).

Tiêu chí người chấm và nhận xét tùy chọn lưu độc lập trong `attempt_speaking_scores`, do Alembic không phá hủy `20261013_0033` thêm. Điểm tổng dùng hàm Speaking tổng thể trọng số đều hiện có. Điểm luyện tập có phạm vi không tạo band phân tích toàn mô-đun. Khóa xem lại Full Mock vẫn có thẩm quyền. `SpeakingReviewData.final_score` mang đánh giá này, `grading` mang khả năng backend cho phép. Xem [teacher-classrooms.md](teacher-classrooms.md#human-final-subjective-grading) về chính sách thẩm quyền và các tuyến dùng chung.
