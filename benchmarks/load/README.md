# Kiểm thử tải BandPilot an toàn

Locust 2.43.3 tạo người dùng HTTP có cookie và vòng đời riêng. Các lần chạy dùng dữ liệu hư cấu và provider giả, không dùng dữ liệu người học thật hay suy luận có tính phí. [Báo cáo kỹ thuật](../../docs/performance/5000-user-capacity.md) là nguồn số liệu chính thức; [nghiên cứu tình huống](../../docs/case-studies/5000-user-scalability.md) giải thích các quyết định. Việc có bộ công cụ kiểm thử tải chưa chứng minh hệ thống phục vụ được 5.000 người học.

## Xác minh cách ly trước mọi request

Chỉ chấp nhận địa chỉ viết trực tiếp `http://127.0.0.1:<port>`, tối đa 10 VU cục bộ. Mỗi lần chạy dùng database `ielts_load_<12hex>`, role `load_<12hex>` không phải superuser, cùng thư mục lưu trữ, JWT, thông tin xác thực và danh tính triển khai mới. Manifest có hạn sử dụng; chú thích database chứa mã băm token bí mật dùng làm bằng chứng. Ứng dụng bọc xác minh database, role, bằng chứng và mã băm mã nguồn ứng dụng thực tế trước khi import. Máy khách không theo chuyển hướng hay dùng proxy từ môi trường. Môi trường tiến trình con chỉ nhận các biến được cho phép; Uvicorn được cố định một worker. `staging=true` chưa đủ chứng minh cách ly. Cấu hình high dành cho 5.000 VU bị chặn khi chạy cục bộ; muốn chạy cloud cần bộ tích hợp đã được review và quyền riêng cho đích chạy, tài nguyên, chi phí.

## Cài riêng phụ thuộc kiểm thử tải

Từ thư mục gốc repository, dùng Python >=3.12:

```powershell
uv --directory backend sync --locked --group dev
uv pip install --python backend/.venv/Scripts/python.exe -r benchmarks/load/requirements.txt
```

Trên Linux, thay đường dẫn trình thông dịch bằng `backend/.venv/bin/python`. Không import Locust vào tiến trình Uvicorn; việc gevent thay đổi hành vi thư viện chỉ được thực hiện ở tiến trình tạo tải. Phụ thuộc benchmark không được đưa vào bộ phụ thuộc chạy API.

## Tạo database dùng một lần

Ví dụ PowerShell dưới đây yêu cầu port, container và ID lần chạy chưa tồn tại. Không dùng Compose ở thư mục gốc vì cấu hình đó gắn volume phát triển. Không xóa container khác để lấy port.

```powershell
$loadId = 'baddad001122' # đổi mỗi run, đúng12hex
$loadContainer = "bandpilot-load-$loadId"
$loadDb = "ielts_load_$loadId"
$loadRole = "load_$loadId"
$loadPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
docker run --detach --name $loadContainer --publish 127.0.0.1:5548:5432 --tmpfs /var/lib/postgresql/data:rw --cpus 2 --memory 1g -e POSTGRES_USER=loadprovisioner -e "POSTGRES_PASSWORD=$loadPassword" -e POSTGRES_DB=postgres postgres:17 -c max_connections=100 -c shared_buffers=128MB
docker exec $loadContainer pg_isready -U loadprovisioner -d postgres
# Chỉ tiếp tục khi pg_isready thành công. Không echo password vào reports.
"CREATE ROLE $loadRole LOGIN PASSWORD '$loadPassword' NOSUPERUSER NOCREATEDB NOCREATEROLE;" | docker exec -i $loadContainer psql -U loadprovisioner -d postgres -v ON_ERROR_STOP=1
"CREATE DATABASE $loadDb OWNER $loadRole;" | docker exec -i $loadContainer psql -U loadprovisioner -d postgres -v ON_ERROR_STOP=1
$env:LOAD_DATABASE_URL = "postgresql+asyncpg://${loadRole}:${loadPassword}@127.0.0.1:5548/$loadDb"
$env:DATABASE_URL = $env:LOAD_DATABASE_URL
Push-Location backend
& .venv/Scripts/python.exe -m alembic upgrade head
Pop-Location
Remove-Item Env:DATABASE_URL
& backend/.venv/Scripts/python.exe -m benchmarks.load.runner init --users 5 --port 18991
```

Migration là thao tác của người vận hành, không chạy khi Web khởi động. `init` yêu cầu database đã migration và các bảng nghiệp vụ trống; ngoại lệ duy nhất là tài khoản chủ sở hữu cũ đã bị vô hiệu hóa, không có thông tin xác thực, do migration 0012 tạo. Lệnh dùng service hiện có để khởi tạo quản trị viên hư cấu, rồi tạo bằng chứng database, JWT, mật khẩu và thư mục lưu trữ riêng trong `.runs/<id>/` đã được Git bỏ qua. Trên Windows, chmod không thay thế NTFS ACL: giữ thư mục trong hồ sơ người dùng riêng tư và xóa thông tin xác thực sau kiểm thử. Không công bố URL chứa thông tin môi trường.

## Chạy server, tạo dữ liệu mẫu và tạo tải

Terminal 1, tại thư mục gốc repository; dùng Ctrl+C để dừng:

```powershell
& backend/.venv/Scripts/python.exe -m benchmarks.load.runner serve --directory benchmarks/load/.runs/baddad001122
```

Terminal 2:

```powershell
& backend/.venv/Scripts/python.exe -m benchmarks.load.runner seed --directory benchmarks/load/.runs/baddad001122 --users 5
& backend/.venv/Scripts/python.exe -m benchmarks.load.runner run --directory benchmarks/load/.runs/baddad001122 --users 5 --scenario mixed --profile smoke
```

Dữ liệu mẫu được tạo qua API biên soạn, quản trị và lớp học thực sự, có xác thực: một đề hư cấu đã xuất bản, 3 đoạn Reading với 40 câu hỏi, 4 phần Listening với 40 câu hỏi, tệp âm thanh im lặng tự tạo dài 4 s, 2 đề Writing và 3 câu gợi ý Speaking. Mỗi VU có nhóm giáo viên, học sinh, lớp và bài giao riêng. Chỉ tạo dữ liệu mẫu một lần cho mỗi database. Nếu thất bại giữa chừng, cần lần chạy mới hoặc dọn dẹp trong phạm vi đã được phép; không dùng lại trạng thái chưa xác định.

| Kịch bản | Hợp đồng cần kiểm tra |
| --- | --- |
| A | Đăng nhập, xem danh mục, bắt đầu Reading hoặc Listening, nhận đề không lộ đáp án, lưu 44 phiên bản cho 40 câu hỏi, điều hướng, nộp bài, đối chiếu giá trị đã lưu trong phần xem lại và kiểm tra lịch sử |
| B | Full Mock theo thứ tự Listening→Reading→Writing→Speaking; tự lưu, chuyển học phần, kiểm tra mã 409 dự kiến khi phần xem lại còn khóa, thăm dò giai đoạn do server quyết định, kết thúc không có âm thanh và kiểm tra phiên hoàn tất/lịch sử |
| C | Học sinh xem lớp, bài giao, thông báo; kiểm tra lượt làm bài theo bài giao, tiến độ, gợi ý; giáo viên xem kết quả và phân tích đúng nhóm |
| mixed | Luân phiên A/B/C theo vị trí VU và lượt lặp; chưa đại diện cho tỷ lệ lưu lượng production |
| D | Đo thành phần riêng bằng provider giả; không cộng vào RPS HTTP thông thường |

B chưa đo ghi âm, tải lên, chuẩn hóa hay ASR. Kết thúc Speaking không có âm thanh là luồng được hệ thống hỗ trợ. Provider giả ở D không chứng minh chất lượng chấm điểm hoặc thông lượng GPU.

| Cấu hình | Tăng tải | Tải ổn định | Chờ hoàn tất | VU mặc định |
| --- | ---: | ---: | ---: | ---: |
| smoke | 5 s | 70 s | 10 s | 5 |
| ramp | 60 s | 180 s | 30 s | 10 |
| burst | 2 s | 45 s | 15 s | 10 |
| soak | 30 s | 1.800 s | 30 s | 5 |
| high | 900 s | 1.800 s | 300 s | 5.000, chỉ thiết kế |

`--users` xác định số VU đích thực tế, không được vượt số nhóm dữ liệu mẫu hoặc giới hạn trong manifest. Smoke dùng nhịp tăng tốc để kiểm tra vòng đời: dừng 0,15 s giữa các câu trả lời, 0,5 s ở bước Writing của B và 2–4 s giữa các hành trình; Listening dùng âm thanh im lặng dài 4 s, không phát toàn bộ bài nghe. Đây không phải nhịp học hay thời lượng thi thực tế. Ví dụ, `LOAD_THINK_SCALE=100` đưa khoảng dừng tự lưu từ 0,15 s lên khoảng 15 s; vẫn cần hiệu chỉnh theo hành vi người học. Giả định 6,6 request/phút/người trong mô hình 5.000 người ở báo cáo là giả định lập kế hoạch riêng, chưa được hiệu chỉnh từ smoke.

Mô hình số VU cố định tạo RPS phụ thuộc thời gian phản hồi và khoảng nghỉ; server chậm có thể làm tốc độ phát sinh request giảm. Kiểm thử quá tải theo mô hình tốc độ đến cố định cần thiết kế riêng. Khi đổi cấu hình, phải lưu cấu hình thực sự có hiệu lực; không gọi hai kịch bản tải khác nhau là phép so sánh trước/sau tương đương.

Các biến sau chỉ được truyền vào tiến trình tạo tải sau khi validation, không thay guard về đích hoặc VUs:

| Biến | Ý nghĩa | Giá trị cho phép |
| --- | --- | --- |
| `LOAD_RAMP_SECONDS` | Thời gian tăng tải, ghi đè profile | 1–7.200 s, hữu hạn |
| `LOAD_STEADY_SECONDS` | Thời gian steady dự kiến | 1–7.200 s, hữu hạn |
| `LOAD_DRAIN_SECONDS` | Đợi hành trình đang chạy kết thúc | 1–7.200 s, hữu hạn |
| `LOAD_THINK_SCALE` | Nhân khoảng nghỉ trong journey; mặc định 1 | 1–1.000 |
| `LOAD_MAX_RPS_PER_USER` | Giới hạn phát request của mỗi VU; mặc định 0 là tắt giới hạn phụ | 0–100 requests/s |

Ví dụ thiết kế nhịp chậm hơn, **chưa phải cấu hình đã đo**:

```powershell
$env:LOAD_THINK_SCALE = '100'
$env:LOAD_STEADY_SECONDS = '1800'
$env:LOAD_DRAIN_SECONDS = '300'
$env:LOAD_MAX_RPS_PER_USER = '1'
& backend/.venv/Scripts/python.exe -m benchmarks.load.runner run --directory benchmarks/load/.runs/baddad001122 --users 5 --scenario A --profile soak
```

Giới hạn RPS là trần trên mỗi VU, không phải cơ chế bảo đảm một tốc độ đến cố định. Khi dùng think time dài, đặt steady/drain đủ cho các journeys dự kiến; mọi lượt chưa hoàn tất phải được diễn giải đúng trong báo cáo.

## Danh tính mã nguồn và so sánh công bằng

`init --application-source <absolute/backend>` chọn mã nguồn gốc để so sánh; PYTHONPATH của tiến trình con trỏ đúng backend. Manifest và báo cáo lưu Git HEAD, SHA256 của các byte thực tế trong `app/**/*.py` và mã băm phần thay đổi của các tệp được Git theo dõi. Chỉ ghi HEAD khi cây làm việc còn thay đổi là chưa đủ, nên bắt buộc có mã băm nội dung thực tế. Nếu mã nguồn thay đổi trước lần khởi động lại, lần chạy bị từ chối. Cần so sánh trên database mới có cùng hình dạng dữ liệu, cùng phụ thuộc Python, bộ tạo tải, tài nguyên, cấu hình, công cụ đo và thứ tự thực thi. Không chạy bộ kiểm thử tính đúng đắn hoặc phép đo GPU cùng lúc. Một cặp lần chạy chưa cho phép xác định khoảng tin cậy.

## Báo cáo và cách diễn giải

`results-<profile>-<scenario>.json` chứa thời điểm UTC, danh tính mã nguồn, cấu hình có hiệu lực, số VU thực tế, số request/mã trạng thái/lỗi theo endpoint, RPS của phản hồi 2xx thành công, RPS toàn bộ, p50/p95/p99, số hành trình hoàn tất/thất bại và dữ liệu chẩn đoán. Sao chép sang ID thí nghiệm riêng trước khi chạy lại vì tên tệp cũ sẽ bị ghi đè. Tiến trình trả mã thoát khác 0 nếu HTTP, hợp đồng API hoặc hành trình thất bại. Phản hồi 409 dự kiến khi phần xem lại bị khóa được tính là kiểm tra hợp đồng thành công nhưng vẫn xuất hiện trong phân bố 4xx.

Histogram dùng phương pháp hạng gần nhất theo mili giây. Cửa sổ tải ổn định bắt đầu khi đạt số VU đích sau giai đoạn tăng tải, kết thúc ở thời điểm đã định hoặc khi dừng sớm. Cửa sổ toàn bộ giữ cả giai đoạn tăng tải và chờ hoàn tất. p99 ở endpoint dưới 1.000 mẫu chỉ dùng chẩn đoán, không dùng để quyết định đạt SLO. Không lấy trung bình các phân vị của nhiều endpoint. Request thiết lập không nằm trong tổng hợp HTTP của cửa sổ ổn định.

Ứng dụng bọc thu thập CPU/RSS bằng psutil, heartbeat vòng lặp sự kiện mỗi 20 ms, số lần/thời gian/lỗi thực thi SQL tại cursor của SQLAlchemy và mẫu kết nối, chờ khóa, giao dịch, bộ đếm deadlock từ `pg_stat_activity/database` mỗi 1 s. Việc theo dõi thêm một kết nối và có chi phí riêng. Bộ đếm tích lũy cần tính chênh lệch; lấy mẫu mỗi 1 s có thể bỏ lỡ đỉnh. Thời gian cursor chưa gồm chờ pool, xử lý ORM hay commit. Các đại lượng chưa đo như hàng đợi nền tảng, mạng và frontend phải ghi NOT RECORDED. CPU, RSS và số VU thực tế của máy tạo tải giúp phát hiện chính máy tạo tải bị bão hòa. Dừng khi có lỗi, hỏng dữ liệu, lỗi dây chuyền hoặc cạn tài nguyên; giữ báo cáo thất bại để điều tra.

## Đo AI và các thành phần riêng

Phép đo Writing dùng worker database thực cùng `FakeLatencyProvider` xác định trước, không gọi suy luận qua mạng. Tạo **một database/role mới và chạy `runner init` riêng** theo phần thiết lập phía trên; chưa chạy `serve` hoặc `seed` trên database đó. Truyền thư mục manifest mới qua `--directory`. Probe xác minh ownership proof, role không phải superuser, không có connection khác và không có dữ liệu nghiệp vụ; chỉ chấp nhận tài khoản bootstrap và sentinel do migration tạo. Tên có `_test` hoặc biến `P2_TEST_DATABASE_URL` không đủ bằng chứng cách ly và không được dùng để chọn đích probe.

```powershell
& backend/.venv/Scripts/python.exe -m benchmarks.load.writing_queue_probe --directory benchmarks/load/.runs/baddad001122 --output writing-queue.local.json
```

Cấu hình gồm 10 tác vụ, 2 consumer, giới hạn RUNNING toàn hệ thống bằng 2, tối đa 2 lần gọi LLM trên mỗi lượt, mỗi lần gọi giả 20 ms, pool 5 và overflow 0. Dữ liệu mẫu đã commit được dọn trong khối finally. Thời gian chờ hàng đợi, thời gian hoàn tất, đỉnh số lượt đang chạy/tác vụ/lần gọi, hủy từ tiến trình khác và hết hạn lease không phải năng lực suy luận thực. Lần thử trước dùng NullPool không hoàn tất trong thời hạn 90 s được ghi rõ; không xem việc đổi cấu hình đó là bằng chứng tăng tốc.

Phép đo xác thực dùng 50 lần gọi scrypt thực, mỗi đợt 5 lần, heartbeat 10 ms và ranh giới database được kiểm soát; không đo HTTP hay database. Từ thư mục gốc, chọn mã nguồn backend qua PYTHONPATH; script bên dưới nằm trong repository hiện tại:

```powershell
$env:PYTHONPATH = '<absolute backend source>'
& backend/.venv/Scripts/python.exe benchmarks/load/auth_component.py --label bounded-thread-scrypt --output auth-component.local.json
Remove-Item Env:PYTHONPATH
```

## Dọn dẹp và kiểm tra

Dừng đúng server bằng Ctrl+C, xác nhận port/PID đã dừng, sao chép báo cáo đã loại thông tin nhạy cảm, rồi chạy:

```powershell
& backend/.venv/Scripts/python.exe -m benchmarks.load.runner teardown --directory benchmarks/load/.runs/baddad001122
docker stop $loadContainer
docker rm $loadContainer
Remove-Item Env:LOAD_DATABASE_URL
& backend/.venv/Scripts/python.exe -m pytest backend/tests/test_load_harness.py backend/tests/test_load_journeys.py backend/tests/test_load_telemetry.py -q
Push-Location backend
& .venv/Scripts/ruff.exe check app tests ../benchmarks/load
Pop-Location
```

Lệnh dọn dẹp kiểm tra bằng chứng database trước khi xóa schema của **database riêng**, kiểm tra đường dẫn lưu trữ đã phân giải nằm đúng thư mục lần chạy trước khi xóa đệ quy, rồi xóa thông tin xác thực và dữ liệu mẫu nhưng giữ báo cáo. Dừng container làm mất database trên tmpfs. Không commit `.runs`, âm thanh, thông tin xác thực hay log server thô chứa SQL. Bằng chứng nhỏ đã loại thông tin nhạy cảm nằm trong [chỉ mục bằng chứng](../../docs/performance/5000-user/evidence.json). Các kiểm thử thuần không thay thế kiểm thử cạnh tranh dùng kết nối PostgreSQL độc lập hoặc kiểm chứng trên cloud.

Kiểm tra bằng chứng đã lưu mà không tạo tải hoặc mở database:

```powershell
& backend/.venv/Scripts/python.exe -m benchmarks.load.validate_evidence
& backend/.venv/Scripts/python.exe -m benchmarks.load.validate_docs
```

Lệnh parse JSON, kiểm SHA-256 của từng báo cáo gốc, tính lại ba HTTP summaries và đối chiếu mức VU tối đa. JSON bằng chứng được cố định line ending LF để checksum nhất quán trên Windows/Linux. `psutil` nằm trong nhóm dev đã khóa của backend để tests telemetry chạy được trên môi trường CI sạch; Locust vẫn là dependency benchmark riêng.
