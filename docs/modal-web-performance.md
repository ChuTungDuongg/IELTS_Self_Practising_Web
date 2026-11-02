# Điều tra độ trễ Modal Web

> **Kiểm toán tài liệu: CURRENT.** Tài liệu chuẩn cho nội dung này; đã đối chiếu ranh giới/API trong mã nguồn, chưa xác minh môi trường đang chạy.
> Mục đích: Điều tra độ trễ Modal Web. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../scripts/benchmark_modal_web.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](case-studies/modal-web-performance.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


Để đọc giải thích bằng tiếng Việt về kiến trúc, quá trình điều tra và kết quả, xem [nghiên cứu tình huống](case-studies/modal-web-performance.md). Để luyện phỏng vấn, xem [câu hỏi và trả lời kỹ thuật hiệu năng](interview/modal-performance-qa.md).

## Phát hiện và giới hạn (điều tra ban đầu)

- Revision khởi đầu: `4a6b5b0850bb39161a308de3207f6d93b1c3a7e7`.
- Tóm tắt sự cố được cung cấp báo waterfall tài sản tĩnh theo bước khoảng 0.63 s và trung vị khoảng 1.84 s trên 201 yêu cầu. Không có log yêu cầu gốc để phân tích độc lập. Chỉ số thực thi Modal được báo không tương đương thời gian handler FastAPI/Next.js.
- Lớp Web có một container, chưa có decorator input concurrency. [Tài liệu đồng thời của Modal](https://modal.com/docs/guide/concurrent-inputs) nêu mặc định một input mỗi container. Decorator cấp lớp được tài liệu mô tả được SDK Modal Python 1.5.3 đã cài chấp nhận với dạng lớp/web-server này, nhưng khai báo Local không phải kiểm thử đồng thời đã triển khai. Waterfall được báo phù hợp hiện tượng xếp hàng, chưa xác định vị trí hoặc tỷ lệ thời gian chờ.
- Không có staging cô lập đang chạy đã xác minh cho điều tra này. App dev trong danh sách đã dừng; Volume tài sản mặc định dev có thể dùng chung production. Không benchmark từ xa, tra region, triển khai, đổi Volume hoặc gửi tải production. Vì vậy region tính toán, RTT từ Việt Nam, CPU/bộ nhớ đã triển khai, p50/p95 và thông lượng vẫn **chưa đo**. Không suy ra cải thiện độ trễ từ thời gian localhost tổng hợp.
- Nginx cho nhiều kết nối và proxy tới tiến trình Next.js/Uvicorn riêng; điều đó chưa chứng minh thông lượng chịu tải. Cấu hình SQLAlchemy Local dùng pool 5 cộng tối đa 10 kết nối overflow mỗi engine; chưa đo độ trễ checkout hoặc truy vấn. Không đổi pool DB, replica, đệm Nginx, cache, streaming, upload hoặc range.
- Auth đã phối hợp refresh đang chạy và dùng browser lock cho refresh xuyên tab. Thăm dò/khôi phục session phục vụ bảo mật/khôi phục. Điều hướng header đã prefetch theo ý định, tắt với liên kết nhạy cảm. Chưa đủ bằng chứng đổi các luồng này.
- Mốc kiểm thử thành phần ghi một yêu cầu danh sách thông báo khi panel đóng, thêm một khi mở. Yêu cầu đầu không cần: thành phần mới chỉ fetch số chưa đọc tới khi mở. Cùng harness, yêu cầu danh sách trước mở đổi **1 → 0**, mở vẫn fetch danh sách/số đếm mới. Đây là kết quả số yêu cầu, không phải độ trễ triển khai.

## Benchmark an toàn

Chỉ dùng staging được cho phép tường minh, cô lập, với DB, tài sản, secret và quyền sở hữu đã xác minh độc lập production. Script không tự thiết lập cô lập. Không trỏ production nếu chưa được cho phép tường minh. Nó chỉ gửi GET không xác thực tới `/`, `/api/v1/ready`, `/icon.svg` và một tài sản Next.js tĩnh thật cùng origin tìm từ HTML. Không theo redirect hoặc gửi thông tin xác thực. Endpoint ready kiểm readiness DB. Mặc định 16 yêu cầu mỗi endpoint tại từng mức đồng thời 1, 4, 8, 16, hai lượt làm nóng tuần tự mỗi endpoint và một GET tìm HTML: tối đa 265 yêu cầu nếu tìm thấy tài sản. Giảm mức/số lượng nếu vẫn không phù hợp môi trường.

```powershell
python scripts/benchmark_modal_web.py --base-url https://YOUR-ISOLATED-STAGING.modal.run --confirm-staging --requests 16 --concurrency 1,4,8,16 --warmup 2 --timeout 15 --output modal-before.json
```

Sau thay đổi chỉ staging được xác minh độc lập, lặp đúng lệnh với `--output modal-after.json`, cùng chế độ triển khai, origin, làm nóng, endpoint, mạng và region. So p50/p90/p95/max yêu cầu thành công, TTFB, lỗi, trạng thái, kích thước phản hồi, thông lượng/thời gian mỗi endpoint và mức đồng thời. Ghi riêng CPU/bộ nhớ/region Modal. Lần chạy lỗi HTTP, xác minh, tìm tài sản hoặc làm nóng thoát khác không; dữ liệu thiếu/lỗi không phải thành công độ trễ. JSON tách từng mức; thời gian dùng phân vị nearest-rank của yêu cầu thành công, cung cấp thông lượng mọi yêu cầu và yêu cầu thành công. Với 16 mẫu, p95 là giá trị lớn nhất: lặp có kiểm soát và tăng mẫu trong trần 100 yêu cầu của script để so đuôi có ý nghĩa. Mỗi yêu cầu mở kết nối urllib mới nên gồm overhead kết nối/TLS, không tương đương trình duyệt tái dùng kết nối. TTFB bắt đầu trước DNS/kết nối, không phải thời gian server thuần hoặc RTT địa lý thuần.

Có thể chạy kiểm tra fixture ngoại tuyến của benchmark không cần triển khai:

```powershell
python -m unittest discover -s scripts/tests -p test_benchmark_modal_web.py -v
```

## Chẩn đoán thời gian tùy chọn

Đặt `IELTS_MODAL_WEB_TIMINGS=true` trong môi trường runtime triển khai đã cô lập phù hợp, khởi động lại để bật chẩn đoán tạm. Mặc định tắt. Nginx ghi request ID sinh tự động, trạng thái, thời gian yêu cầu, địa chỉ upstream, thời gian phản hồi/kết nối upstream, rồi chuyển ID tới upstream. FastAPI ghi ID đó, phương thức, trạng thái và tổng thời gian yêu cầu ASGI. Không ghi URL, query, header, cookie, body yêu cầu/phản hồi, ID người dùng hoặc địa chỉ client. Gỡ cấu hình, khởi động lại để tắt log. Giữ kiểm soát truy cập/lưu giữ log vận hành thông thường.

Thời gian Nginx chỉ bắt đầu sau ingress gửi yêu cầu tới container; không đo queue Modal. Thời gian upstream/ASGI gồm streaming/backpressure, không coi là CPU hoặc chỉ handler. Dùng ID sinh tự động tương quan yêu cầu API; Next.js không phát log thời gian tương ứng. Streaming vẫn không đệm; middleware chuyển ASGI message nguyên vẹn. Xác minh streaming, media được bảo vệ, range và upload trên môi trường cô lập trước tối ưu proxy khác.

## Trạng thái so sánh ban đầu (trước P2)

| Chỉ số | Trước | Sau |
| --- | --- | --- |
| GET / p50 / p95 | Chưa đo | Chưa đo |
| Readiness p50 / p95 | Chưa đo | Chưa đo |
| Tài sản tĩnh p95 | Chưa đo | Chưa đo |
| RPS đồng thời / lỗi HTTP | Chưa đo | Chưa đo |
| CPU / bộ nhớ Modal Web | Chưa đo | Chưa đo |

Trên staging đã xác minh, lập mốc trước thử `@modal.concurrent(max_inputs=8)` hoặc `16` có giới hạn ở cấp lớp. Giữ `max_containers=1` và khóa chủ sở hữu DB hiện có. So độ tin cậy/độ trễ đuôi, giám sát CPU, bộ nhớ/kết nối DB, hoàn tác ứng viên làm xấu chúng. Cấu hình mặc định một input Modal chưa đổi trong revision ban đầu vì chưa có dữ liệu triển khai an toàn để chọn. Điều tra địa lý/RTT riêng, không di chuyển Volume PostgreSQL hoặc đổi region. Chỉ xem thời gian API/kế hoạch truy vấn khi quan sát chỉ ra chi phí backend/DB.

## Thí nghiệm staging cô lập P2 — 2026-10-29

**Quyết định: đặt `@modal.concurrent(max_inputs=8)` cấp lớp, giữ một container Web.** Hai lần chạy tương đương: readiness p95 với 16 yêu cầu client giảm 9.86/10.22 s xuống 2.13/2.14 s, thông lượng tăng 1.57/1.54 lên 6.82/6.87 yêu cầu/s, không lỗi HTTP trong phép đo. Đây là kết quả staging có kiểm soát, không hứa production hoặc điều hướng trình duyệt. Readiness p95 một yêu cầu trước 1.29/1.48 s, sau 1.32/1.29 s: đồng thời input không loại bỏ độ trễ mạng nền.

Thử nghiệm dùng app Modal dev tên riêng `bandpilot-perf-p2-app-265b0d2e`, Volume riêng `bandpilot-perf-p2-db-265b0d2e`, `bandpilot-perf-p2-assets-265b0d2e`, `bandpilot-perf-p2-snapshots-265b0d2e`, Secret `bandpilot-perf-p2-config-265b0d2e`, Dict `bandpilot-perf-p2-owners-265b0d2e`. Dùng LocalAssetStorage/PostgreSQL nhúng, không nhập snapshot hoặc dữ liệu học viên. DB rỗng ban đầu được migration bằng cơ chế khởi động hiện có; migration `20260923_0012` tạo một chủ sở hữu cũ tổng hợp không hoạt động. Tắt AI/tải GPU.

Bản sao điểm vào khởi đầu tạm chỉ đổi tên owner Dict cho baseline, tránh dùng khóa production chung. Ứng viên thêm decorator đồng thời cấp lớp đã kiểm thử và chỉ cố định container **staging** tại `ap-south`, giá trị `MODAL_REGION` thực quan sát trong container baseline. Cả hai dùng cùng URL app, region định tuyến `us-east`, DB, tài sản, Secret, 2 CPU, 4096 MiB, `min_containers=1`, `max_containers=1`; dừng container đầu/giải phóng khóa riêng trước chạy container thứ hai. Xóa bản sao điểm vào sau thử. Mã production không cố định region. Nhãn region rộng không chứng minh cùng host vật lý hoặc zone; triển khai lại có thể đổi cả hai. [Tài liệu region Modal](https://modal.com/docs/guide/region-selection) phân biệt region container/định tuyến HTTP và mô tả phí bổ sung khi cố định region.

Hai lần thăm dò trước dùng Volume/Secret riêng nhưng Dict `ielts-web-database-owner` chung hiện có vì runtime gốc cố định tên. Chúng tạm ghi khóa riêng staging vào Dict chung rồi xóa. Không đổi khóa production; xác minh khóa staging không còn sau thử. Giữ kết quả đầu dưới tên `shared-guard-*`, không dùng làm so sánh chính. Container đó tình cờ chạy `us-east`: không thấy cùng mẫu queue mạnh, mức đồng thời 8 không có tác động đáng kể lặp lại. Vì vậy topology region/định tuyến là yếu tố đóng góp khả dĩ, không chứng minh topology production.

**Sự cố dọn tài nguyên:** app staging cuối tiếp tục chạy sau lần đo sau thứ hai kết thúc 09:52:44 (UTC+7), dừng lúc 15:26:34, khoảng 5 h 34 min sau. Có thể phát sinh phí Modal bổ sung. Modal thay container sau đo; app nay dừng, không container chạy; khóa owner staging không còn trong Dict riêng/chung. Giữ Volume, Secret, Dict riêng thử nghiệm theo yêu cầu.

Mỗi báo cáo chính dùng 16 GET mỗi endpoint tại mức đồng thời 1, 4, 8, 16, hai lượt làm nóng tuần tự và timeout 30 giây, CSS `/_next/static/chunks/4013uxh3niqjj.css` (42,141 bytes) tìm từ HTML. Hai phiên bản được đo hai lần từ cùng client Windows tại Việt Nam. Mỗi yêu cầu urllib mở kết nối mới, yêu cầu identity encoding; không phải điều hướng trình duyệt. p95 nearest-rank là lớn nhất 16 quan sát nên nhạy nhiễu. Báo cáo đầy đủ gồm TTFB/kích thước/trạng thái/lỗi từng mức: [mốc ban đầu](performance/modal-p2/baseline.json), [lặp mốc](performance/modal-p2/baseline-repeat.json), [ứng viên](performance/modal-p2/after-8.json), [lặp ứng viên](performance/modal-p2/after-8-repeat.json), [mốc localhost](performance/modal-p2/baseline-local.json), [tổng hợp thời gian server](performance/modal-p2/server-timings.json).

Hai giá trị mỗi ô lần lượt là lần chạy đầu/thứ hai, không phải khoảng tin cậy. Độ trễ tính mili giây; RPS đếm yêu cầu thành công.

| Endpoint | Đồng thời client | Mốc ban đầu p50 / p95 | Đồng thời 8 p50 / p95 | RPS mốc ban đầu | Đồng thời 8 RPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| / | 1 | 1312.86, 1298.99 / 1770.70, 1634.89 | 1312.68, 1306.00 / 1936.68, 1630.91 | 0.72, 0.74 | 0.68, 0.72 |
| / | 4 | 2380.78, 2542.91 / 3669.11, 3372.62 | 1434.54, 1596.26 / 1903.08, 1823.78 | 1.48, 1.43 | 2.52, 2.37 |
| / | 8 | 4892.50, 4872.66 / 5757.81, 5913.29 | 1692.43, 1608.55 / 2145.27, 2000.14 | 1.47, 1.46 | 4.15, 4.41 |
| / | 16 | 5823.78, 5541.64 / 10777.38, 10670.86 | 1781.25, 1791.32 / 2371.24, 2317.91 | 1.47, 1.45 | 6.07, 6.50 |
| /api/v1/ready | 1 | 1054.59, 1056.08 / 1290.24, 1479.91 | 1046.55, 1058.74 / 1320.39, 1286.56 | 0.90, 0.87 | 0.89, 0.87 |
| /api/v1/ready | 4 | 2472.85, 2438.81 / 2950.40, 3018.96 | 1067.06, 1122.85 / 1610.81, 1467.90 | 1.54, 1.53 | 3.17, 3.04 |
| /api/v1/ready | 8 | 4867.89, 4898.71 / 5318.87, 5404.96 | 1470.44, 1452.90 / 1700.56, 1504.42 | 1.55, 1.52 | 4.76, 5.22 |
| /api/v1/ready | 16 | 5142.21, 5142.76 / 9856.98, 10218.82 | 1539.27, 1572.08 / 2129.83, 2137.18 | 1.57, 1.54 | 6.82, 6.87 |
| /icon.svg | 1 | 1233.00, 1254.09 / 1493.08, 1498.33 | 1246.59, 1257.17 / 1506.44, 1759.00 | 0.77, 0.76 | 0.76, 0.74 |
| /icon.svg | 4 | 2506.17, 2488.92 / 3106.61, 3248.66 | 1283.19, 1316.75 / 1694.45, 1603.11 | 1.49, 1.50 | 2.60, 2.66 |
| /icon.svg | 8 | 4978.59, 4973.73 / 5669.88, 5724.44 | 1513.72, 1453.94 / 1810.32, 1689.04 | 1.50, 1.50 | 4.75, 4.84 |
| /icon.svg | 16 | 5563.69, 5476.73 / 10442.29, 10381.65 | 1514.81, 1666.75 / 2109.00, 2125.18 | 1.48, 1.49 | 6.96, 6.76 |
| CSS tĩnh | 1 | 1564.55, 1539.27 / 1954.04, 1904.52 | 1565.42, 1562.51 / 1913.51, 1987.85 | 0.58, 0.63 | 0.59, 0.59 |
| CSS tĩnh | 4 | 2472.47, 2497.72 / 4010.45, 3700.02 | 1665.07, 1810.17 / 1981.68, 2095.78 | 1.45, 1.46 | 2.11, 2.15 |
| CSS tĩnh | 8 | 4832.38, 4812.58 / 6152.04, 6122.16 | 1808.49, 1777.22 / 2238.15, 2269.78 | 1.46, 1.48 | 3.60, 3.68 |
| CSS tĩnh | 16 | 5933.25, 5829.77 / 11114.79, 10897.65 | 2008.86, 2010.92 / 2627.78, 2589.90 | 1.42, 1.42 | 5.70, 5.31 |

| Chỉ số bổ sung | Mốc ban đầu | Đồng thời 8 |
| --- | --- | --- |
| Lỗi HTTP | 0 / 512 yêu cầu được đo | 0 / 512 yêu cầu được đo |
| Readiness TTFB p95 khi client đồng thời 16 | 9,856.64 / 10,218.39 ms | 2,043.63 / 1,941.90 ms |
| Thời gian yêu cầu Nginx p50 / p95, upstream Next | 3 / 14 ms | 3 / 20 ms |
| Thời gian phản hồi upstream Nginx p50 / p95, Next | 3 / 14 ms | 3 / 20 ms |
| Thời gian yêu cầu Nginx p50 / p95, upstream FastAPI | 4 / 6 ms | 4 / 5 ms |
| Thời gian phản hồi upstream Nginx p50 / p95, FastAPI | 4 / 6 ms | 4 / 5 ms |
| Tổng ASGI FastAPI p50 / p95 | 2.87 / 5.24 ms | 2.40 / 4.96 ms |
| Mẫu CPU / bộ nhớ cgroup năm giây | 0.086 lõi / 534.1–535.6 MiB | 0.036 lõi / 541.6–545.9 MiB |

Tổng hợp Nginx có 531 mục mỗi cấu hình (gồm tìm tài sản/làm nóng): 398 upstream Next, 133 upstream API. Log ASGI có 269 sự kiện, gồm thăm dò auth nội bộ Next. Không ghép một-một với yêu cầu benchmark; thời gian ASGI/upstream có thể gồm streaming/backpressure. Mỗi quan sát CPU/bộ nhớ là mẫu năm giây, không phải đỉnh hoặc trung bình toàn lượt. Một mẫu PostgreSQL ứng viên thấy bốn kết nối gồm kết nối kiểm tra, không phải số đỉnh.

Benchmark localhost trong container ở mốc ban đầu bỏ qua ingress Modal/mạng ngoài: readiness với 16 client p95 49.69 ms, 224 yêu cầu/s. Endpoint công khai tương ứng p95 khoảng 10 s, 1.5 yêu cầu/s. Waterfall công khai gần tuyến tính, thời gian nội bộ ngắn và cải thiện từ cấu hình input giới hạn là bằng chứng mạnh rằng xử lý input Modal từng lượt trên đường định tuyến `us-east` → container `ap-south` là nút thắt lớn trong kịch bản staging này. Công cụ không tách chính xác thời gian queue Modal, ingress và mạng, không xác lập region/hành vi queue production thật. Cũng không đo waterfall trình duyệt thật.

Kiểm an toàn staging xác nhận `/library` trả 307 riêng tư no-store tới khôi phục session, auth/analytics/tài sản riêng không xác thực và endpoint SSE trả 401, range CSS tĩnh thật trả 206 với Content-Range đúng. Kiểm thử Local tập trung bao phủ redirect xác thực, byte range storage có quyền, phát Speaking và chuyển tiếp message streaming. Chưa thực hiện stream media riêng/SSE có xác thực đang chạy. Không đổi đệm/cache Nginx, pool PostgreSQL, số replica, region production, tải GPU hoặc triển khai production. Đánh giá riêng định tuyến/triển khai cô lập gần địa lý hơn; không chuyển Volume PostgreSQL hiện có chỉ để thử độ trễ.

## Điều hướng kho kiến thức

Xem [mục lục kỹ thuật](README.md), [hướng dẫn phỏng vấn thiết kế hệ thống](interview/bandpilot-system-design.md), [kiến trúc runtime](handbook/runtime-architecture.md). Giữ artifact benchmark và phép đo gốc bên trên.
