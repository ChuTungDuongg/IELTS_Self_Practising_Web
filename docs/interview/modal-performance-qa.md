# BandPilot Performance Engineering — Interview Preparation

Tài liệu ôn tập này dựa trên [case study đầy đủ](../case-studies/modal-web-performance.md), [báo cáo thực nghiệm](../modal-web-performance.md) và JSON benchmark. Cách diễn đạt mẫu dùng ngôi thứ nhất để người đọc luyện tập, nhưng phải điều chỉnh theo phần việc thực tế của mình. Dự án dùng **AI-assisted development**: chủ dự án đặt mục tiêu, ràng buộc và hướng điều tra; Codex thực hiện các bước được ghi nhận trong lịch sử. Khi phỏng vấn, hãy nói rõ phần mình thực sự trực tiếp làm hoặc kiểm tra, không nhận mọi thao tác của Codex là do mình tự gõ hay tự triển khai.

## A. Lời giải thích trong 30 giây

> “BandPilot gặp độ trễ khi nhiều request web cùng đến Modal. Em/chúng tôi dùng Codex hỗ trợ dựng staging cô lập, chạy benchmark GET và so sánh thời gian ở client với Nginx/FastAPI. Trong topology thử, cấu hình một input có dấu hiệu xếp hàng; chuyển sang tối đa tám input trên cùng một Web container. Hai lượt đo readiness với 16 client cho p95 từ 9,86/10,22 giây xuống 2,13/2,14 giây, không có lỗi trong các request đo. Đây là kết quả staging, chưa phải kết quả browser hay production.”

## B. STAR trong khoảng hai phút

**Situation — tình huống.** “BandPilot là ứng dụng luyện IELTS với Next.js và FastAPI. Khi chạy Modal, người dùng báo chuyển trang chậm; bản tóm tắt request log có chuỗi asset chậm dần. Bản raw log không nằm trong artifact Git để em kiểm chứng lại từng dòng.”

**Task — nhiệm vụ.** “Mục tiêu là tìm phần nào tạo độ trễ và thử một thay đổi có giới hạn, trong khi vẫn giữ PostgreSQL nhúng chỉ có một owner. Em không coi việc tăng GPU hoặc tăng replica là câu trả lời mặc định.”

**Action — hành động.** “Em đặt yêu cầu đo trước, giới hạn staging và rà soát dữ liệu; Codex thực hiện script benchmark, instrumentation, deployment staging và thay đổi mã. Chúng tôi dùng database/asset/Secret riêng, sau đó sửa setup để owner Dict cũng riêng. Từng cấu hình được đo hai lần với client concurrency 1, 4, 8, 16. Thời gian qua URL công khai được đối chiếu với Nginx, FastAPI và localhost trong container. Sau baseline, ứng viên `max_inputs=8` được thử ở cùng vùng container và cùng URL, vẫn giữ một container.”

**Result — kết quả.** “Readiness p95 ở 16 client giảm từ 9,86/10,22 xuống 2,13/2,14 giây; throughput tăng từ 1,57/1,54 lên 6,82/6,87 request/s. Các batch chính không có lỗi HTTP. Em xem đây là bằng chứng mạnh cho tình huống staging, không phải bằng chứng rằng production luôn nhanh hơn 78% hay browser đạt một SLO nào đó. Cleanup staging bị chậm khoảng 5 giờ 34 phút; đó là bài học về thiết kế teardown và chi phí.”

## C. Trình bày kỹ thuật trong khoảng năm phút

1. **Kiến trúc.** “Trong topology thử, Modal ingress chuyển HTTPS đến Nginx cổng 8000 trong Web CPU container. Nginx proxy Next.js 3000 hoặc FastAPI 9001; FastAPI dùng PostgreSQL nhúng 5432 và asset storage. AI GPU là service riêng, tắt trong phép đo. Tôi phân biệt cấu hình embedded này với local và external database.”
2. **Triệu chứng.** “Người dùng báo chuyển trang chậm; log tóm tắt có các request asset tăng dần. Tôi trình bày đó là báo cáo ban đầu, không nói mình đã phân tích lại raw log.”
3. **Waterfall.** “Nếu nhiều request có thời gian tăng theo từng bước, có thể có chờ admission hay head-of-line blocking. Nhưng waterfall không cho biết queue ở Modal, Nginx, upstream hay mạng.”
4. **Giả thuyết.** “Code cũ có một Web container và không đặt `@modal.concurrent`; theo tài liệu Modal mặc định một input mỗi container. Đây là giả thuyết có cơ sở, chưa phải kết luận.”
5. **Benchmark.** “Tôi yêu cầu staging tách Volume/Secret/database và không nạp dữ liệu thật, GPU tắt. Codex dùng script GET với homepage, readiness, icon và một static CSS phát hiện từ HTML; 16 request cho mỗi endpoint/mức client 1, 4, 8, 16, warmup hai lần, lặp hai run.”
6. **Instrumentation.** “Log tùy chọn ghi Nginx request/upstream/connect và FastAPI ASGI total, không ghi cookie hay query. Mốc TTFB client là lúc nhận headers, tính cả kết nối; các đồng hồ này đo những phạm vi khác nhau.”
7. **Chẩn đoán.** “Baseline 16 client có readiness p95 gần 10 giây; trong container, localhost p95 khoảng 50 ms, Nginx/FastAPI chỉ vài ms. Sau khi cho tám input, public p95 giảm rõ. Tôi kết luận input admission là ứng viên bottleneck lớn trong staging, không tuyên bố đã đo riêng queue time.”
8. **Implementation.** “Codex thêm `@modal.concurrent(max_inputs=8)` trên lớp Web. Tôi giải thích được tại sao vẫn giữ `min_containers=1`, `max_containers=1`, 2 CPU và 4096 MiB, và tại sao nhiều input không phải nhiều container.”
9. **Verification.** “Hai lượt sau đều không lỗi HTTP trong 512 request đo và readiness throughput lên khoảng 6,8 request/s. Staging kiểm tra 307, 401 và static range 206; local test kiểm tra thêm range, stream và auth. Authenticated media/SSE dưới tải và browser thật chưa được live-test.”
10. **Trade-off.** “Tám input có thể tăng áp lực CPU, memory, database pool và slot bị giữ bởi SSE/upload. Mẫu cgroup ngắn không phải peak. Nếu traffic tăng, cần đo lại và cân nhắc external PostgreSQL trước scale-out. Ban đầu staging tạm ghi một key vào shared guard, sau đó chuyển sang Dict riêng; cleanup cuối bị trễ và có thể tốn thêm tiền.”

## D. 20 câu hỏi kỹ thuật và câu trả lời

1. **Bottleneck thực tế là gì?** Ở staging `us-east` routing tới container `ap-south`, dữ liệu ủng hộ mạnh việc giới hạn input gây chờ lớn khi đồng thời; không có số đo trực tiếp tách queue Modal khỏi ingress và mạng. Không áp kết luận đó cho mọi production topology.
2. **Head-of-line blocking là gì?** Một việc giữ slot làm các việc phía sau chờ, kể cả việc ngắn. Với một input, một request lâu có thể trì hoãn CSS hoặc readiness đến sau.
3. **Tại sao FastAPI không rõ là bottleneck?** Public readiness p95 khoảng 10 giây ở baseline 16 client, nhưng Nginx upstream FastAPI p95 6 ms và localhost p95 49,69 ms. Các tập mẫu không ghép một-một, nhưng chênh lệch đủ lớn để điều tra phần ngoài handler trước.
4. **`@modal.concurrent` làm gì?** Nó cấu hình số input đồng thời được phục vụ trong một container Modal; dự án chọn tối đa 8 trên lớp Web. Nó không cấp thêm CPU.
5. **Concurrency khác parallelism thế nào?** Concurrency là nhiều việc cùng tiến triển, có thể xen kẽ khi chờ; parallelism là thực sự chạy đồng thời trên tài nguyên tính toán. Tám HTTP input có thể overlap I/O mà không có tám core.
6. **`max_inputs` khác `max_containers`?** Cái đầu giới hạn input trên mỗi container; cái sau giới hạn số container. `8 × 1` không tương đương `1 × 8` về topology, tài nguyên hay ownership.
7. **Vì sao giữ `max_containers=1`?** PostgreSQL nhúng có data directory trên Volume và cần một owner. Nhiều Web container có thể tạo nhiều process PostgreSQL; guard hiện tại được thiết kế cho một owner.
8. **Sao không tăng GPU?** Web, Nginx, FastAPI và PostgreSQL chạy CPU; các function AI GPU riêng và tắt khi benchmark. Không có bằng chứng GPU gây độ trễ của request web.
9. **Vì sao đo readiness và CSS?** Readiness đi qua API và kiểm tra truy cập database; CSS đại diện asset Next.js. Cùng với homepage/icon, chúng giúp so sánh các loại response; không đại diện mọi endpoint hay browser.
10. **p95 là gì?** Percentile thứ 95 của phân phối latency; script chọn nearest-rank. Nó mô tả đuôi chậm của mẫu chứ không phải giới hạn tối đa bảo đảm trong tương lai.
11. **Vì sao p95 nhiễu với 16 mẫu?** `ceil(0,95 × 16)=16`, nên p95 bằng giá trị lớn nhất. Một request bất thường có thể thay đổi cả chỉ số.
12. **TTFB là gì trong script này?** Thời gian từ trước khi `urlopen` đến khi nhận response headers. Nó gồm DNS/kết nối/TLS khi phát sinh, không phải thời gian FastAPI thuần và không nhất thiết là byte body đầu tiên.
13. **Throughput được tính thế nào?** Số request thành công chia elapsed time của batch. Ví dụ readiness 16-client run đầu là 1,57 trước và 6,82 request/s sau; lỗi vẫn phải báo riêng.
14. **Vì sao lặp benchmark?** Một run có thể gặp nhiễu mạng, cold effects hoặc scheduling. Hai run cho thấy tính lặp lại cơ bản nhưng quá ít để tự tạo confidence interval.
15. **Đã kiểm soát confounder thế nào?** Cùng URL, tài nguyên staging, dữ liệu, endpoint, warmup, request count và vùng container quan sát `ap-south`. Candidate pin vùng còn baseline không pin; cùng nhãn vùng không chứng minh cùng máy hay zone.
16. **Region ảnh hưởng latency thế nào?** Client ở Việt Nam đi qua routing `us-east` tới container `ap-south` trong thí nghiệm chính. Chặng mạng và routing có thể tăng thời gian; không thể suy ra riêng RTT hay cho rằng region là nguyên nhân duy nhất.
17. **Traffic tăng 10 lần thì sao?** Không ngoại suy tuyến tính từ 16 request. Đo workload theo endpoint, theo dõi p95/error, CPU/memory và pool; thử giới hạn và backpressure trước khi quyết định scale-out.
18. **Khi nào dùng managed PostgreSQL?** Khi cần tách lifecycle database khỏi một Web container, quản lý backup/HA và mở đường cho nhiều replica. Cần kế hoạch migration, kết nối, bảo mật và consistency; managed không tự làm mọi query nhanh hơn.
19. **Cần gì trước rollout production?** Đo trên staging sát workload, kiểm tra login/session, authorization, upload, audio range, authenticated media/SSE và tải hỗn hợp; theo dõi tài nguyên, xác định rollback và chỉ triển khai theo quy trình được phê duyệt.
20. **Lần sau làm gì khác?** Tạo cả owner Dict riêng ngay từ đầu, đặt timeout/cleanup tự động kèm người chịu trách nhiệm, kiểm tra billing; tăng số mẫu có kiểm soát và dùng browser performance khi được phép.

## E. Các câu hỏi vặn tiếp

**Nếu 8 input làm request CPU-bound chậm hơn?** Concurrency không tăng CPU; đo CPU utilization, p95 và queue theo từng loại request. Giảm giới hạn, giới hạn việc nặng hoặc tách workload khi số liệu chứng minh cần; không hy sinh request ngắn chỉ để tăng RPS.

**Nếu database pool bão hòa?** Đo thời gian checkout, số connection active/idle và query chậm trước. Giới hạn concurrency và giảm truy vấn thừa nếu có bằng chứng. Tăng pool không làm PostgreSQL có thêm CPU và có thể khiến hệ thống tệ hơn.

**Nếu Nginx nhanh nhưng client vẫn chậm?** So sánh client TTFB, DNS/TLS, đường mạng, routing và admission Modal; dùng request ID/timing phù hợp. Nginx không thấy thời gian trước khi request vào container, nên không kết luận ngay lỗi của một nhà cung cấp.

**Nếu phải phục vụ 1.000 người đồng thời?** “Người đồng thời” không bằng 1.000 request/giây. Xác định mix và SLO, dùng tải được phép, thiết kế capacity/backpressure, database bên ngoài và object storage, nhiều replica khi topology an toàn; đo auth, upload, SSE và chi phí. Không ngoại suy số replica từ benchmark này.

**Nếu SSE và upload lớn cạnh tranh asset?** Xem thời gian giữ slot, bandwidth, timeout và fairness; kiểm tra stream thật, giới hạn hoặc tách workload nếu bằng chứng ủng hộ. Không bật buffering toàn cục vì có thể phá streaming.

**Sao không cache mọi thứ?** Auth/session, analytics cá nhân, private media và classroom data cần kiểm soát truy cập; cache chia sẻ sai có thể lộ dữ liệu. Chỉ cân nhắc immutable static assets với semantics đã xác minh và không thay đổi API riêng tư tùy tiện.

**Thiết kế regression test hiệu năng lặp lại thế nào?** Dùng staging riêng, dataset tổng hợp, cùng phiên bản/region/client, warmup, workload và sample size; lưu JSON, status, TTFB, p50/p95, RPS và tài nguyên; chạy nhiều lần, đặt ngưỡng theo baseline đã thống kê, cleanup có deadline. Tách synthetic performance test khỏi SLO production và browser test.

## F. Flashcards

| Câu hỏi | Trả lời | Ví dụ BandPilot |
| --- | --- | --- |
| Latency? | Thời gian một request từ bắt đầu đến hoàn tất. | Readiness public p95 baseline gần 10 s ở 16 client. |
| Throughput? | Số request thành công mỗi giây. | Readiness tăng 1,57 → 6,82 request/s ở run đầu. |
| Concurrency? | Nhiều việc cùng tiến triển. | Tối đa 8 Modal input trong một container. |
| Parallelism? | Nhiều phép tính chạy thực sự cùng lúc. | Tám input không có nghĩa tám CPU core. |
| Queue? | Việc phải chờ slot. | Asset chờ trước khi vào Web container. |
| Head-of-line blocking? | Việc trước trì hoãn việc sau. | Một input dài có thể giữ slot của CSS. |
| Reverse proxy? | Server chuyển request sang upstream. | Nginx 8000 → Next 3000 hoặc FastAPI 9001. |
| Event loop? | Điều phối tác vụ async, chuyển việc khi chờ. | FastAPI có thể xử lý I/O khác khi một tác vụ chờ. |
| p50? | Percentile 50 theo nearest-rank của script. | Số request điển hình, không phải p95. |
| p95? | Percentile 95 theo nearest-rank. | Với 16 mẫu, bằng mẫu lớn nhất. |
| TTFB? | Thời gian đến response đầu tiên; script lấy khi có headers. | Gồm kết nối/TLS, không chỉ FastAPI. |
| Warmup? | Request trước phép đo chính để ổn định điều kiện. | Hai lượt tuần tự cho mỗi endpoint. |
| Horizontal scaling? | Tăng số container. | Không tự tăng Web replica khi DB còn nhúng. |
| Owner guard? | Khóa ngăn nhiều process cùng sở hữu database. | Modal Dict keyed theo database Volume. |
| Tail latency? | Phần request chậm ở đuôi phân phối. | So p95 trước/sau cùng mức tải. |

## G. Không nên khẳng định gì

| Câu nói không chính xác | Cách nói có thể bảo vệ |
| --- | --- |
| “Tôi làm BandPilot nhanh hơn 8 lần.” | Hai run readiness throughput staging tăng khoảng 4,34×/4,46× ở 16 client; input limit là 8, không phải hệ số tăng tốc. |
| “Web luôn tải trong 2 giây.” | Readiness p95 trong hai batch cụ thể khoảng 2,13/2,14 giây; browser, endpoint khác và production chưa được đo như vậy. |
| “Tối ưu GPU sửa web.” | Web dùng CPU và GPU bị tắt trong benchmark; thay đổi là input concurrency. |
| “Tôi scale thành 8 container.” | Một container nhận tối đa 8 input; `max_containers` vẫn là 1. |
| “Đã chứng minh performance production.” | Đây là staging, sample nhỏ và topology cụ thể; cần xác minh production có kiểm soát. |
| “Backend chậm do PostgreSQL.” | Không có bằng chứng query PostgreSQL là bottleneck; thời gian FastAPI/Nginx rất ngắn so với public latency trong phép thử này. |
| “Tôi tự viết và tự chạy toàn bộ.” | Mô tả trung thực phần mình chỉ đạo, xem xét và hiểu; nêu Codex hỗ trợ thực thi khi phù hợp. |
| “Đã đo được queue Modal chính xác.” | Các số ủng hộ giả thuyết admission/queue, nhưng chưa tách được trực tiếp queue khỏi ingress và mạng. |
