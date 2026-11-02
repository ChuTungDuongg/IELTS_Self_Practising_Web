# BandPilot — Thiết kế khảo sát khả năng phục vụ 5.000 người học

Nguồn yêu cầu: nhiệm vụ kiểm toán hiệu năng và phần bổ sung tài liệu/bàn giao ngày 2026-11-02. Mốc ban đầu đã fetch: `9027c413f2bf48c6fe760940e6e324848c496d98`. Đây là kế hoạch thực hiện trong phạm vi người dùng đã cho phép; không cho phép triển khai cloud, thử tải production hay gọi inference trả phí.

## Mục tiêu và ranh giới

Xây công cụ đo quy trình HTTP thực với dữ liệu mẫu hư cấu, bằng chứng có thể tái lập và tài liệu tiếng Việt. Phân biệt người học đồng thời, request HTTP đang xử lý, RPS và inference. Giữ kiến trúc nguyên khối chia mô-đun, quy tắc chấm điểm/thời hạn/phân quyền, phiên bản bất biến, lưu có revision và thứ tự khóa bản ghi cha trước con của Full Mock. Không thay UI hay cấu hình Modal production.

## Các lựa chọn

- k6: bộ tạo tải gọn, nhưng cần công cụ JavaScript và phần điều phối dữ liệu mẫu/xác thực riêng.
- Locust: Python phù hợp schema/service và dữ liệu mẫu hư cấu hiện có; phụ thuộc benchmark tách khỏi runtime. Chọn Locust với điểm vào có chốt kiểm tra, tài khoản riêng biệt, client HTTP và báo cáo JSON.
- Framework hàng đợi bên ngoài: chưa có bằng chứng cần Redis/Celery. Chọn bảng run/event PostgreSQL hiện có, token bảo vệ quyền sở hữu và số bộ xử lý Writing giới hạn. Speaking giữ hợp đồng/lease hiện có và ghi rõ giới hạn.

## Thay đổi dự kiến

`benchmarks/load/` sở hữu manifest an toàn, tạo dữ liệu mẫu, kịch bản A/B/C/D, cấu hình tải, báo cáo JSON và hướng dẫn tái lập. Đích phải có định danh và tài nguyên riêng; chỉ một cờ staging là chưa đủ. Chốt an toàn cục bộ giới hạn tối đa 10 VU trên loopback khi đã xác nhận DB và storage có thể bỏ đi; đợt kiểm chứng này thực chạy tối đa 5 VU. Nếu chưa có môi trường cách ly thì ghi NOT RUN.

Writing: điều phối PENDING bền vững, thực thi có giới hạn, token/hạn lease và hủy giữa replica. RUNNING hết hạn chuyển sang thất bại kết thúc, giữ checkpoint đã commit và yêu cầu retry tường minh; không tự chạy lại toàn bộ MTS hay hứa lời gọi bên ngoài chỉ diễn ra đúng một lần. Cấu hình pool DB giữ mặc định để người vận hành tính được ngân sách kết nối tổng.

Báo cáo chuẩn nằm tại `docs/performance/5000-user-capacity.md`; nghiên cứu tình huống và tài liệu phỏng vấn giải thích/liên kết bằng chứng thay vì sao chép báo cáo. Đo trước/sau cùng cấu hình khi khả thi; không gán tăng tốc cho thay đổi chỉ về kiến trúc.

## Nghiệm thu và bàn giao

Chạy test tập trung hiện có trước thay đổi; test hồi quy dùng DB độc lập cho nhận việc/hủy/khôi phục, test hợp đồng an toàn cho công cụ thử tải, cùng smoke giới hạn khi có PostgreSQL cách ly. Không dùng endpoint readiness để đạt điều kiện khả năng phục vụ. Định nghĩa SLO theo endpoint/khu vực trước đợt kiểm chứng staging tương lai; p99 ít mẫu phải ghi INCONCLUSIVE. Rà soát toàn bộ diff, liên kết, bí mật, lint/typecheck và migration; fetch/đối chiếu, push branch tính năng rồi tích hợp/push `origin/main` theo yêu cầu bổ sung, không force hay deploy.
