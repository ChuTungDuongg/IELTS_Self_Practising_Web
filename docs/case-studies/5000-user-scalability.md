# Từ “5.000 người dùng” đến một thí nghiệm năng lực có thể tin được

Đợt điều tra ngày 2026-11-02 bắt đầu từ câu hỏi sản phẩm: BandPilot có phục vụ ổn định 5.000 người học IELTS đang hoạt động cùng lúc không? Kết luận hiện tại là **NOT VERIFIED**. Giá trị của đợt này nằm ở việc định nghĩa đúng câu hỏi, xây dựng phép đo an toàn, xác nhận nút thắt qua mã nguồn và kiểm thử, đồng thời sửa một số ranh giới xử lý lỗi trước khi đầu tư kiểm thử tải trên cloud.

Số liệu chính thức, phiên bản mã nguồn và giới hạn diễn giải nằm trong [báo cáo kỹ thuật](../performance/5000-user-capacity.md); [chỉ mục bằng chứng gốc](../performance/5000-user/evidence.json) dẫn tới từng thí nghiệm. Bài này giải thích các quyết định theo trình tự, không thay thế hướng dẫn vận hành hay tạo một bộ số liệu khác.

## Bắt đầu từ bản gốc thay vì xây một bản demo mới

Repository đã có Next.js, FastAPI, PostgreSQL, lớp trừu tượng hóa kho đối tượng, vòng đời bài thi, cùng AI Writing và Speaking. `origin/main` sau khi fetch là `9027c413f2bf48c6fe760940e6e324848c496d98`. Bản làm việc chính có thay đổi cục bộ ngoài nhiệm vụ; worktree và nhánh hiệu năng riêng giúp giữ nguyên chúng.

Đọc mã nguồn quan trọng hơn suy đoán từ sơ đồ. Bản demo Modal thực sự chạy Nginx, Next.js, FastAPI và PostgreSQL nhúng trong một container, có cơ chế bảo vệ quyền sở hữu database, `max_containers=1` và mức đồng thời đầu vào bằng 8. PostgreSQL bên ngoài và S3/R2 đã được hỗ trợ nhưng chưa tự hình thành cụm nhiều replica. AWS Compose tách các service, có kiểm tra tình trạng và mẫu TLS, nhưng chưa có chính sách tự động mở rộng.

Vì vậy, chưa có lý do để chuyển kiến trúc nguyên khối phân mô-đun thành microservices. Ranh giới cần tách trước là **tài nguyên và thời gian sống của tác vụ suy luận**, không phải nghiệp vụ chấm điểm hay lớp học. PostgreSQL vẫn là nguồn dữ liệu có thẩm quyền; frontend không truy cập database trực tiếp, server quyết định hạn chót và lượt làm bài vẫn tham chiếu TestVersion đã đóng băng.

## Làm rõ “đồng thời”

Một người học có thể đọc đoạn văn 30 giây rồi lưu một câu trả lời. Trong 30 giây đó họ vẫn hoạt động nhưng không phát sinh 30 request HTTP. Vì vậy phải đo riêng thông lượng và mức đồng thời. VU là số máy trạng thái người dùng đang tồn tại; RPS là số request hoàn thành theo thời gian. Request đang xử lý là request chưa nhận xong phản hồi. Tác vụ AI đồng thời lại thuộc nhóm khác: một tác vụ có nhiều lần gọi provider và tồn tại lâu hơn request HTTP tạo nó.

Nếu gửi 5.000 request cùng lúc vào `/ready`, phép đo chỉ kiểm tra đợt tăng tải đột ngột trên endpoint kiểm tra sẵn sàng. Nó chưa kiểm tra 5.000 người học. Endpoint này chỉ truy vấn database đơn giản, không xác nhận phiên bản khi tự lưu, đánh giá lúc nộp bài, tiến trình Full Mock hay phân quyền giáo viên. Kết quả Modal P2 trước đây hữu ích khi điều tra hàng đợi ở cổng vào, nhưng không phải chứng nhận năng lực phục vụ bài thi.

Kiểm thử tải hỏi hệ thống có đáp ứng kịch bản đã định nghĩa hay không. Kiểm thử vượt ngưỡng tăng tải để tìm giới hạn và kiểu lỗi. Kiểm thử duy trì tải dài hạn giúp phát hiện tích tụ bộ nhớ, kết nối và tác vụ. Kiểm thử tăng tải đột ngột xem hệ thống phản ứng thế nào khi tốc độ request đến tăng nhanh. BandPilot cần thiết kế cả bốn; thiếu hạ tầng không cho phép coi các phép đo chưa chạy là đã hoàn thành.

## Chọn bộ tạo tải đi qua luồng nghiệp vụ thực

Locust được chọn vì dữ liệu mẫu và hợp đồng backend đều ở Python, dễ review hơn tập payload JSON viết theo trí nhớ. Phụ thuộc nằm riêng trong `benchmarks/load`, không trở thành phụ thuộc chạy API. Uvicorn thực nhận HTTP; không thay kiểm thử tải bằng lời gọi service trực tiếp rồi gọi kết quả đó là độ trễ mạng.

Kịch bản A đi qua đăng nhập→danh mục→bắt đầu→nhận đề→lưu theo phiên bản→điều hướng→nộp bài→xem lại. B dùng phiên và thao tác chuyển học phần của Full Mock, thay vì tạo bốn lượt độc lập rồi gộp số. C dùng tài khoản giáo viên và học sinh riêng để kiểm tra phân quyền có ý nghĩa. D dùng suy luận giả, tách khỏi request thông thường, không tạo hàng nghìn lần gọi tính phí.

Mỗi VU sở hữu nhóm dữ liệu và cookie riêng. Khi phản hồi lỗi, hành trình dừng thay vì tiếp tục nộp một lượt không tồn tại hoặc bỏ qua lỗi lưu. Kiểm tra không lộ đáp án áp dụng cho DTO đề đang làm; chỉ kiểm tra phần xem lại sau khi chốt bài. Phản hồi lưu được đối chiếu với schema hiện có, không tự đặt hợp đồng khác rồi sửa ứng dụng cho phù hợp benchmark.

Lần smoke đã chạy dùng nhịp tăng tốc: khoảng dừng trả lời 0,15 s, bước Writing của B 0,5 s và Listening dùng âm thanh im lặng dài 4 s, không phát toàn bộ bài nghe. Mục đích là kiểm tra vòng đời trong thời gian ngắn. Thông lượng đo được chưa đại diện cho người học theo nhịp thực tế. Giả định 6,6 request/phút/người trong mô hình 5.000 người là giả định riêng, chưa hiệu chỉnh từ smoke. Chẳng hạn, LOAD_THINK_SCALE=100 đưa khoảng dừng tự lưu lên khoảng 15 s thay vì 0,15 s; vẫn cần dữ liệu hành vi để chọn nhịp phù hợp.

Fixture Listening ban đầu đặt `order_index=0` cho mỗi phần, trong khi backend thực yêu cầu thứ tự nhóm ở cấp học phần. Việc tạo dữ liệu mẫu thất bại với mã 500, nên phải sửa bộ tạo tải và xóa bản nháp dở dang qua API được phân quyền. Một lần thử khác giả định `is_correct` trong phản hồi lưu luôn null, nhưng schema thực cho phép boolean/null. Đây là lỗi phương pháp của bộ tạo tải. Giữ dấu vết và giải thích chúng đáng tin hơn xóa các lần chạy xấu rồi chỉ công bố một con số đẹp.

## Cách ly phải có bằng chứng

Docker ban đầu chưa chạy; nhóm không chuyển sang dùng database phát triển cho tiện. Sau khi người dùng bật engine, môi trường mới dùng PostgreSQL 17 riêng, loopback 5548, tmpfs, 2 CPU/1 GiB. Mỗi lần chạy tải còn có role không phải superuser, database, mật khẩu, JWT issuer/secret, thư mục lưu trữ và danh tính triển khai riêng.

Manifest có hạn sử dụng; chú thích database gắn mã băm bằng chứng bí mật. Ứng dụng bọc yêu cầu token và xác minh danh tính thực tế của ứng dụng/database. Host phải là địa chỉ 127.0.0.1 viết trực tiếp, không dùng DNS hay tùy chọn đổi đích tùy ý; máy khách không theo chuyển hướng hoặc dùng proxy từ môi trường. Cấu hình high chỉ là thiết kế và bị chặn khi thực thi cục bộ. Một cờ staging đơn lẻ không chứng minh database, bucket hay thông tin xác thực đã tách khỏi production.

Cách này cũng giúp kiểm chứng việc dọn dẹp: chỉ được xóa schema, thư mục lưu trữ và thông tin xác thực thuộc đúng lần chạy. Không xóa đệ quy đường dẫn chưa xác minh hay xóa database khác chỉ vì tên chứa chữ test. Báo cáo gốc chỉ chứa dữ liệu tổng hợp, không đưa cookie, mật khẩu, âm thanh hoặc nội dung đề thật vào Git.

## Nút thắt thứ nhất: scrypt trong vòng lặp sự kiện

`AuthService` là async nhưng gọi scrypt đồng bộ trực tiếp. Một hàm dùng CPU không trở nên không chặn luồng chỉ vì nằm trong `async def`. Trong một tiến trình Uvicorn, nó giữ luồng vòng lặp sự kiện, khiến request Reading không liên quan hoặc heartbeat của worker phải chờ.

Thí nghiệm thành phần dùng 50 lần xác minh mật khẩu thực, chia 10 đợt × 5 lần, với ranh giới lưu trữ được kiểm soát và heartbeat 10 ms. Bản gốc có độ trễ lớn nhất khoảng 264 ms. Sau khi chuyển phép tính sang luồng có giới hạn, mức lớn nhất khoảng 10 ms. Tham số scrypt và ngữ nghĩa thông tin xác thực/lỗi được giữ nguyên; chỉ hàm tính toán thuần dùng CPU được đưa vào luồng, không đưa session SQLAlchemy theo.

Không dùng riêng `to_thread` rồi tạo hàng đợi CPU vô hạn. Cơ chế giới hạn cho phép hai phép xử lý đã gửi trên mỗi vòng lặp. Khi request bị hủy, luồng vẫn có thể chạy; chỉ trả lại suất khi luồng thực sự kết thúc, kể cả khi nhận nhiều tín hiệu hủy. Kiểm thử dùng điểm đồng bộ để chứng minh giới hạn thực, không dựa vào ngưỡng thời gian mong manh.

Có đánh đổi rõ ràng: CPU tiến trình tăng trong phép đo thành phần; cơ chế giới hạn mật khẩu có thể làm đăng nhập phải chờ, trong khi giao dịch vẫn mở như trước. Độ trễ heartbeat lớn nhất giảm không có nghĩa toàn bộ API nhanh hơn 26 lần. Đây là cải thiện khả năng phản hồi có mục tiêu, kèm chi phí được ghi rõ.

## Nút thắt thứ hai: tác vụ nền chưa đủ bền vững

Writing ở bản gốc đã lưu bền vững lượt xử lý/sự kiện và nhận lượt PENDING bằng khóa hàng. Nhờ vậy, bấm lặp không đơn giản tạo hai bên cùng có quyền ghi kết quả. Nhưng mỗi `launch` vẫn tạo tác vụ cục bộ; semaphore provider chỉ giới hạn trong một lượt. 100 lượt với giới hạn 2 có thể tạo 200 lần gọi provider, dù từng đối tượng riêng đều có giới hạn.

Tiến trình chết sau commit nhưng trước lúc khởi chạy cục bộ cũng có thể để lại hàng PENDING không được xử lý liên tục. Speaking đã có lease database và phục hồi, nhưng không thể suy ra Writing tự có cùng bảo đảm. Cần đọc riêng từng đường xử lý trọng yếu.

Thay đổi nhỏ nhất là dùng chính các hàng lượt xử lý trong PostgreSQL làm hàng đợi. Khi tiếp nhận, áp giới hạn PENDING toàn hệ thống; số consumer cố định nhận việc dưới giới hạn RUNNING chung. Quyền sở hữu gắn token và hạn chót theo đồng hồ database; mọi lần ghi checkpoint và trạng thái kết thúc đều kiểm tra quyền này. Provider chỉ được gọi sau giao dịch nhận việc, không giữ kết nối trong lúc chờ GPU. `launch` chỉ đánh thức bộ quét; mất tín hiệu này vẫn không mất tác vụ bền vững.

Khả năng phục hồi phải phù hợp với luồng xử lý hiện có. Writing MTS chưa có hợp đồng tiếp tục mọi giai đoạn từ checkpoint, nên RUNNING hết hạn chuyển thành `RUN_INTERRUPTED`, giữ điểm một phần và cho phép thử lại rõ ràng bằng lượt mới. Speaking có quy tắc checkpoint/tiếp tục riêng và được giữ nguyên. Điều kiện bảo vệ trong database chặn worker cũ ghi sau khi hủy hoặc phục hồi, nhưng không thu hồi lần gọi bên ngoài đã gửi ngay trước sự cố. Không có bảo đảm chỉ tính phí đúng một lần.

Review độc lập tìm thêm hai lỗi dễ bỏ sót: worker ở replica tắt AI vẫn có thể lấy tác vụ nếu không kiểm tra cấu hình provider; SIGTERM trên Unix không tự đi qua phần dọn dẹp của `asyncio.run` như SIGINT. Các lỗi được xử lý bằng kiểm thử hồi quy tập trung thay vì đợi kiểm thử quy mô lớn tình cờ gặp.

Review cuối còn tìm thấy đường lỗi kết nối database báo như đã nhận việc, khiến consumer thử lại ngay thay vì đợi poll interval. Bản sửa chỉ công nhận claim sau commit và cho lỗi trước đó đi qua thời gian chờ; tests buộc lỗi mở kết nối/commit đã fail trước và pass sau. Review harness cũng phát hiện probe giả phải kiểm database mới có ownership proof, không chỉ nhìn tên `_test`; `psutil` cần có trong dev lockfile của CI; và benchmark phải tương thích Python 3.12. Những phát hiện này cho thấy kiểm chứng phải bao gồm môi trường sạch và đường sự cố, không chỉ đường thành công local.

## Pool database là ngân sách của toàn cụm

Pool ở bản gốc mặc định 5 kết nối cộng 10 overflow mỗi tiến trình, chờ 30 s. Công khai và kiểm tra ba cấu hình giúp người vận hành tính số kết nối, nhưng giữ nguyên mặc định chưa tạo mức tăng tốc. Tăng pool có thể chỉ chuyển hàng đợi từ ứng dụng sang database hoặc làm PostgreSQL hết kết nối.

Ngân sách tổng phải cộng mọi tiến trình API, worker riêng, phần chạy chồng khi triển khai, theo dõi và migration. 12 tiến trình API với mặc định có thể dùng 180 kết nối trước khi thêm worker. Nếu database được quản lý chỉ cấp 100 kết nối sử dụng được thì cấu trúc này không hợp lệ, dù mỗi tiến trình chỉ dùng 15. Phục vụ 5.000 người học không cần 5.000 kết nối database; cũng không thể chọn kích thước pool chỉ từ số người học.

Mã nguồn còn cho thấy thao tác lưu tải một đồ thị dữ liệu khá rộng, lịch sử/danh mục chưa phân trang và SSE thăm dò mỗi 1 s cho mỗi người theo dõi. Đây là các hướng phân tích hiệu năng tiếp theo. Chưa thêm chỉ mục, cache hay PgBouncer theo phỏng đoán. Cần dữ liệu lớn, kế hoạch truy vấn, thời gian chờ lấy kết nối và thông tin chặn để phân biệt thiếu chỉ mục, lượt trao đổi ORM và cạnh tranh cần thiết cho tính toàn vẹn.

## Đọc kết quả đúng mức

Độ trễ phía máy khách gồm ngăn xếp HTTP, thời gian chờ trong ứng dụng, SQL và truyền phản hồi. Thời gian cursor của SQLAlchemy chưa gồm xử lý ORM hay chờ pool. Độ trễ vòng lặp sự kiện đo heartbeat trễ bao nhiêu, không phải p95 của endpoint. Mẫu `pg_stat_activity` mỗi 1 s có thể bỏ lỡ lần chờ khóa dài 20 ms. Các đại lượng cùng mô tả hệ thống nhưng không thay thế nhau.

p95 là mốc mà 95% quan sát không vượt qua; p99 tập trung vào phần đuôi hiếm hơn. Với 16 mẫu, p95 gần giá trị lớn nhất; báo hai chữ số thập phân không làm nó đáng tin hơn. Báo cáo giữ số mẫu, cửa sổ ổn định thực tế và lỗi; không lấy trung bình các phân vị endpoint hay so hai lần chạy khác tải mà thiếu giải thích.

Kết quả đã chạy, kể cả lỗi bộ tạo tải và kiểm thử bị bỏ qua, nằm trong [báo cáo](../performance/5000-user-capacity.md#6-chứng-cứ-thực-thi). Khi đọc, phân biệt **đã đo**, **đã kiểm chứng bằng mã nguồn/kiểm thử tính đúng đắn** và **ước tính/đề xuất**. Kết quả cục bộ nhỏ không thể trở thành VERIFIED cho 5.000 người bằng phép nhân tuyến tính.

## Mở rộng theo chiều ngang thay đổi ràng buộc gì?

Mở rộng theo chiều dọc tăng CPU/RAM của một máy; có thể giúp trước mắt nhưng vẫn giữ một miền sự cố. Mở rộng theo chiều ngang thêm replica, đòi hỏi trạng thái và quyền sở hữu không phụ thuộc một tiến trình. Next.js và API có thể đi theo hướng HTTP không giữ trạng thái cục bộ với cấu hình JWT chung, PostgreSQL bên ngoài và S3/R2. Trạng thái người dùng vẫn ở database; quyền truy cập tài sản vẫn qua chính sách.

Không thể nhân bản PostgreSQL nhúng của demo bằng cách cho nhiều tiến trình PostgreSQL dùng chung Volume dữ liệu. Hướng production phải tách database và kho đối tượng. Service worker cần thời gian sống và ngân sách tài nguyên riêng; replica chỉ phục vụ HTTP tắt consumer Writing. Kết nối lại/phát lại SSE, quyền sở hữu tác vụ định kỳ, hạn mức provider, chờ hoàn tất khi dừng và ngân sách pool đều cần được nghiệm thu trước triển khai.

AWS có thể dùng ECS, ALB và PostgreSQL được quản lý; chưa cần lập tức dùng Kubernetes hoặc tách nghiệp vụ thành microservices. Modal có thể dùng chế độ bên ngoài rồi thử cấu hình mức đồng thời/số container trên staging. Cả hai đều cần phép đo riêng; không đổi cấu hình production chỉ vì biểu đồ localhost trông đẹp.

## Bài học và công việc tiếp theo

- Định nghĩa kịch bản tải trước khi chọn số VU. Khoảng nghỉ, tỷ lệ luồng nghiệp vụ, âm thanh và AI làm năng lực phục vụ khác nhau rất lớn.
- Phân tích tính đúng đắn có thể chứng minh công việc không giới hạn hoặc thiếu điều kiện bảo vệ quyền ghi ngay khi chưa đo bão hòa. Gọi đúng đây là củng cố kiến trúc/độ tin cậy cho tới khi đo được tác động.
- Dữ liệu mẫu và bộ tạo tải cũng là phần mềm có lỗi. Hợp đồng API và báo cáo thất bại giúp tránh sửa nhầm ứng dụng để chiều bộ tạo tải.
- Giới hạn công việc phải bao gồm hủy và vòng đời: trả suất semaphore khi luồng/provider còn chạy chỉ tạo giới hạn trên giấy.
- Điều đã làm tốt: dùng nhận việc qua database trong kiến trúc phân mô-đun hiện có, provider giả không tốn suy luận, kiểm thử buộc các thao tác xen kẽ để bảo vệ bài thi, phép đo có bằng chứng gốc và giới hạn diễn giải.
- Điều chưa làm: kế hoạch truy vấn với dữ liệu quy mô production, duy trì tải dài hạn, 500–5.000 VU, máy tạo tải phân tán, năng lực GPU/ASR thực, thông lượng SSR/nội dung tĩnh của Next.js và chuyển đổi khi cloud gặp sự cố. Không chạy thí nghiệm tốn kém chỉ để lấp ô tài liệu.

Lần tiếp theo cần staging cách ly được duyệt tài nguyên/chi phí, manifest dữ liệu đại diện, máy tạo tải riêng, region/SLO đã chốt và tiến trình 50→100→250→500→1.000→2.500→5.000. Chỉ nâng kết luận sau khi tải ổn định, duy trì tải dài hạn và kiểm tra tính đúng đắn đều đạt. Bộ tài liệu này giúp lần thử tiếp theo bắt đầu từ phương pháp rõ ràng thay vì lặp lại suy đoán.
