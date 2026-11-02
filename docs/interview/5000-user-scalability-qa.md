# Khả năng mở rộng của BandPilot: câu hỏi phỏng vấn từ công việc đã làm

Nguồn đối chiếu: [báo cáo kỹ thuật](../performance/5000-user-capacity.md), [bằng chứng gốc](../performance/5000-user/evidence.json), [nghiên cứu tình huống](../case-studies/5000-user-scalability.md). Các câu trả lời phân biệt rõ điều đã kiểm chứng với kiến trúc đề xuất; không xem số người dùng chưa đo là thành tích.

## 1. BandPilot đã phục vụ được 5.000 người đồng thời chưa?

**NOT VERIFIED.** Đợt này đã chuẩn bị bộ công cụ kiểm thử tải, củng cố một số giới hạn vận hành và kiểm chứng cục bộ ở quy mô nhỏ. Chưa có lần chạy xuyên suốt trên staging với 5.000 người dùng ảo (VU). Trước khi dùng kết luận VERIFIED, tôi cần công bố kịch bản tải, cấu trúc triển khai, thời gian tải ổn định, số mẫu và lỗi theo từng endpoint cùng báo cáo gốc. RPS của endpoint kiểm tra sẵn sàng hoặc phép ngoại suy đều chưa đủ.

## 2. 5.000 người dùng khác 5.000 request thế nào?

Người học còn đọc, nghe và viết giữa các request. VU là số người dùng ảo đang duy trì trạng thái; RPS là số request mỗi giây; số request HTTP đang xử lý là số chưa nhận xong phản hồi. Tác vụ AI thuộc luồng xử lý riêng và thường kéo dài hơn. Giả định lập kế hoạch 6,6 request/phút/người học tạo khoảng 550 RPS HTTP thông thường cho 5.000 người, chưa gồm media, SSE hay suy luận AI. Đây là giả định chưa được hiệu chỉnh, không phải năng lực đã đo. Lần smoke dùng nhịp tăng tốc để kiểm tra vòng đời, nên không thể dùng thông lượng của nó làm năng lực phục vụ người học theo nhịp thực tế.

## 3. Vì sao chọn Locust và không dùng trình duyệt cho mọi người học?

Python phù hợp với dữ liệu mẫu, schema và service sẵn có trong repository; các phụ thuộc kiểm thử tải được tách khỏi môi trường chạy API. Người dùng HTTP vẫn giữ cookie và vòng đời riêng, trong khi tiêu thụ ít tài nguyên hơn hàng nghìn trình duyệt. Kiểm thử trình duyệt xuyên suốt vẫn cần cho ghi âm và hiển thị, nhưng kết quả kiểm thử HTTP không chứng minh Core Web Vitals hay hiệu năng chuyển động phía máy khách.

## 4. Ngăn chạy nhầm benchmark vào production bằng cách nào?

Chỉ chấp nhận địa chỉ loopback viết trực tiếp; không theo chuyển hướng hay dùng proxy. Mỗi lần chạy có role không phải superuser, database mới, JWT, thư mục lưu trữ, danh tính triển khai và thông tin xác thực riêng. Manifest có hạn sử dụng; bằng chứng token bí mật được gắn vào chú thích của database. Ứng dụng bọc đối chiếu danh tính thực tế trước khi nhận tải. Giới hạn cục bộ là 10 VU; cấu hình 5.000 chỉ là thiết kế. Một ô đánh dấu staging không chứng minh bucket hay database đã tách khỏi production.

## 5. Làm sao biết request lưu không làm mất câu trả lời?

Bộ tạo tải dùng ID câu hỏi thực và `expected_revision`, kiểm tra phiên bản cùng giá trị trả về, nộp bài sau khi lưu và đối chiếu phần xem lại đã chốt. Kiểm thử tích hợp dùng các kết nối PostgreSQL độc lập để buộc các thao tác lưu cạnh tranh, lưu đồng thời với nộp bài và truy cập khác người dùng. Không bỏ khóa hàng hay hạn chót do server thực thi để tăng RPS. Full Mock giữ thứ tự khóa cha→con và ràng buộc duy nhất của lượt làm bài theo học phần.

## 6. “async” có đồng nghĩa với không chặn luồng không?

Không. Ở bản gốc, AuthService gọi scrypt đồng bộ trong phương thức async. Thí nghiệm thành phần gồm 50 lần gọi, với tín hiệu kiểm tra vòng lặp sự kiện mỗi 10 ms, ghi nhận độ trễ lớn nhất 264 ms. Chuyển phép tính sang luồng có giới hạn giảm mức lớn nhất xuống khoảng 10 ms trong một lần chạy; kết quả này chưa chứng minh HTTP nhanh hơn. Session vẫn ở vòng lặp sự kiện; chi phí băm mật khẩu và cách xử lý lỗi được giữ nguyên.

## 7. Tại sao cần cơ chế giới hạn trước `to_thread`?

Bộ thực thi mặc định có số luồng hữu hạn nhưng hàng đợi nhận việc vẫn có thể tăng. Cơ chế giới hạn chỉ cho phép gửi tối đa hai phép xử lý mật khẩu thực sự trên mỗi vòng lặp. Hủy request không dừng một luồng đang chạy, nên phải chờ luồng kết thúc trước khi trả lại suất semaphore. Kiểm thử dùng điểm đồng bộ và tín hiệu hủy lặp lại để chứng minh giới hạn này.

## 8. Writing ở bản gốc đã có bản ghi database, vì sao chưa đủ bền vững?

Lưu bền vững lượt xử lý và sự kiện khác với bảo đảm tác vụ được giao cho worker. Tiến trình có thể chết sau commit nhưng trước khi khởi chạy tác vụ cục bộ. Sổ tác vụ trong bộ nhớ không có giới hạn tiếp nhận toàn hệ thống hoặc token quyền sở hữu. Mỗi lượt có semaphore provider bằng 2 vẫn có thể tạo hàng trăm lần gọi khi nhiều lượt cùng hoạt động. Bản sửa dùng lại các hàng PENDING trong PostgreSQL, số consumer cố định, ngân sách chung và lease có thời hạn.

## 9. Lease trong database có bảo đảm suy luận đúng một lần không?

Không. Token và thời hạn lease bảo vệ quyền ghi checkpoint, tức mốc tiến độ đã lưu, và trạng thái kết thúc. Lần gọi provider đã gửi vẫn có thể tiếp tục sau khi tiến trình chết hoặc tác vụ bị hủy. Thử lại có thể phát sinh chi phí bên ngoài lần nữa nếu provider không hỗ trợ tính lũy đẳng. Writing hiện kết thúc lượt có lease hết hạn bằng lỗi, giữ checkpoint và yêu cầu thử lại rõ ràng; chưa hứa tiếp tục từ từng giai đoạn khi chưa triển khai khả năng đó.

## 10. Hủy tác vụ giữa các replica hoạt động ra sao?

API commit trạng thái hủy kết thúc trước. Worker cùng tiến trình nhận tín hiệu hủy ngay; worker ở tiến trình khác phát hiện trạng thái kết thúc hoặc mất lease khi gửi heartbeat hay ghi checkpoint, rồi dừng tác vụ con. Kết quả hoàn tất từ worker cũ bị chặn bởi điều kiện token, trạng thái và thời hạn. Phép tính tại provider có thể chưa dừng; cần phân biệt quyền quyết định kết quả đã lưu với việc thực thi bên ngoài.

## 11. Vì sao không thêm Celery/Redis ngay?

PostgreSQL đã chứa dữ liệu lượt xử lý, sự kiện bền vững và ngữ nghĩa giao dịch, đủ cho cơ chế giao việc tối thiểu có giới hạn. Thêm hàng đợi ngoài sẽ kéo theo bài toán ghi đồng thời vào hai hệ thống, tính lũy đẳng và vận hành. Khi số liệu cho thấy áp lực thăm dò, nhận việc hoặc yêu cầu lập lịch vượt khả năng của cơ chế database, mới đánh giá hàng đợi riêng dựa trên bằng chứng; không chọn chỉ vì công nghệ phổ biến.

## 12. Tính số kết nối database cho toàn bộ cụm như thế nào?

`Σ(processes × (pool_size+overflow)) + operational reserve + rollout overlap`. Mặc định mỗi tiến trình API cho phép 15 kết nối; 12 tiến trình có thể đạt 180 kết nối trước khi tính worker. Phục vụ 5.000 người học không đòi hỏi 5.000 kết nối. Pool có thể cấu hình nhưng vẫn giữ mặc định 5+10 và thời gian chờ 30 s; đây là cải thiện khả năng vận hành, chưa phải mức tăng tốc đã đo. Chỉ xét PgBouncer sau khi đo và kiểm tra tính tương thích với asyncpg.

## 13. p99 có luôn đáng tin không?

Không. Với ít mẫu, p99 theo phương pháp hạng gần nhất gần bằng giá trị lớn nhất; cỡ mẫu và tính ổn định của tải quyết định cách diễn giải. Báo cáo đánh dấu endpoint dưới 1.000 mẫu là dữ liệu chẩn đoán, không dùng để quyết định đạt SLO. Lấy mẫu CPU/RAM mỗi 1 s cũng có thể bỏ lỡ đỉnh. Độ trễ phía máy khách, thời gian thực thi SQL tại cursor, độ trễ vòng lặp sự kiện và thời gian chờ ở cổng vào là các đại lượng khác nhau.

## 14. Vì sao không tăng số container của bản demo Modal?

Volume chứa dữ liệu PostgreSQL nhúng cần một tiến trình database sở hữu. Cho nhiều tiến trình PostgreSQL dùng chung thư mục không biến nó thành cụm database được quản lý. Cần PostgreSQL bên ngoài, S3/R2 và các replica HTTP không giữ trạng thái cục bộ. Mã nguồn đã hỗ trợ chế độ bên ngoài nhưng vẫn giới hạn một container Web. Chưa thay cấu hình đồng thời trên production vì thiếu bằng chứng staging.

## 15. AWS Compose có tự động mở rộng không?

Repository hiện chưa có. Compose tách frontend, backend và proxy, đồng thời khai báo tài nguyên và kiểm tra tình trạng, nhưng không tạo cơ chế tự động mở rộng trên cloud. Bước tiếp theo có thể là ECS services, ALB, database và kho đối tượng được quản lý, cùng worker Writing riêng; hoặc triển khai một cụm cố định trước. Cần kiểm chứng định tuyến, trạng thái sẵn sàng, dừng an toàn, phát lại SSE và ngân sách kết nối database tổng hợp.

## 16. Khi AI quá tải, Reading có tiếp tục được không?

Đó là mục tiêu: giới hạn tiếp nhận và worker độc lập có giới hạn để suy luận không chiếm vô hạn tác vụ Web. Writing đã có đường chạy consumer ở tiến trình riêng; lưu lượng thông thường không cần GPU. Speaking vẫn cần giới hạn chung, cách ly tài nguyên và bằng chứng staging. Chưa thể nghiệm thu khả năng chịu bão hòa của toàn bộ AI chỉ từ kiểm thử đơn vị Writing.

## 17. Có thử nghiệm nào sai không?

Có: Docker ban đầu chưa khởi động được, fixture Listening dùng sai order_index và bộ tạo tải từng hiểu sai kiểu boolean của trường đánh giá đúng/sai trong phản hồi lưu bài. Các lỗi được sửa đúng nơi chịu trách nhiệm, đồng thời giữ bằng chứng lần thử thất bại. Không đổi ngữ nghĩa bài thi để benchmark chạy xanh. Bài học là kiểm tra bộ tạo tải và hợp đồng API trước khi quy lỗi thành nút thắt của ứng dụng.

## 18. Thử nghiệm kế tiếp quan trọng nhất là gì?

Cần staging cách ly với region và SLO đã thống nhất, dữ liệu đại diện cho lịch sử, danh mục và lớp học, máy tạo tải riêng, tăng dần từ 50→5.000 VU rồi duy trì tải dài hạn. Cần đo kế hoạch truy vấn, thời gian chờ pool, khóa, đuôi độ trễ theo endpoint, lưu lượng media ra ngoài, SSE nhiều người theo dõi, hàng đợi bền vững và phục hồi; đo thông lượng provider riêng. Nhiệm vụ này chưa được cấp quyền tạo tài nguyên cloud hoặc phát sinh chi phí.
