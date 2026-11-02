# Kiểm toán xử lý đồng thời BandPilot

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Kiểm toán xử lý đồng thời BandPilot. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../backend/app/services/asset_cleanup.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](handbook/data-architecture.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả kiểm thử/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong lần kiểm toán này.


Ngày: 2026-10-26. Mốc ban đầu: `43fdc9d4cb0e8ba4f5e5e3f48beb06733de7b688` trên `main`; mã từ xa vừa fetch trùng khớp. Phạm vi: sửa tính đúng đắn có mục tiêu trong Next.js → FastAPI → PostgreSQL. Giữ lưu trữ, hạ tầng nhà cung cấp, UI, registry câu hỏi, hợp đồng xác thực và ranh giới điểm AI tư vấn/điểm người chấm hiện có.

Thay đổi Local không liên quan (placeholder `storage`, `.agents`, `.taste-skill`, tài liệu thiết kế và khóa skill) không thuộc bản bàn giao. Kiểm thử dùng DB PostgreSQL 17 riêng vừa migration, tên `bandpilot_concurrency_test` và `bandpilot_concurrency_fault_test`, trên cổng loopback 5544. Không sửa schema/dữ liệu development/production. Kiểm thử nhà cung cấp dùng giả lập; không mở trình duyệt hoặc suy luận trả phí.

## Lỗi đã xác nhận và cách sửa

### C1 — Đảo thứ tự khóa con/cha Full Mock (đã sửa)

- **Thao tác/tác nhân:** nộp/timeout mô-đun cuối so với `get`, `advance` hoặc xóa session; cùng bản ghi `Attempt` và `TestSession`, kết nối riêng.
- **Bảo vệ sẵn có:** `FOR UPDATE` attempt, `FOR UPDATE` session, index riêng phần duy nhất `(test_session_id, module_type)`; Speaking đã khóa cha rồi con.
- **Lỗi:** nộp thông thường giữ attempt rồi cập nhật cha. Thao tác session giữ cha rồi cập nhật/xóa con. Hai giao dịch có thể chờ nhau. Đồng bộ timeout còn dùng snapshot con tải trước không khóa.
- **Tác động:** deadlock PostgreSQL hủy thao tác vòng đời hợp lệ; snapshot cũ gây nguy cơ hoàn tất không nhất quán.
- **Bằng chứng:** ba kiểm thử ép giao dịch chồng lấn thất bại trên mốc ban đầu với `asyncpg.exceptions.DeadlockDetectedError`, gồm chờ `UPDATE test_sessions`. Điều phối dùng event và `pg_blocking_pids`, không dùng sleep.
- **Sửa:** bộ tải mutation thông thường nay khóa cha trước attempt, thống nhất Speaking; làm mới trạng thái ORM đã khóa. Đồng bộ timeout khóa/làm mới cột con tường minh, giữ collection cha. Bỏ chu trình eager-load không cần thiết qua attempt anh em.
- **Xác minh:** `test_mock_timeout_submit_and_session_operations_have_stable_lock_order[get/advance/delete]`; advance trùng; session Full Mock độc lập. Giữ thứ tự mô-đun, khóa xem lại và ràng buộc duy nhất.

### C2 — Tệp còn lại sau rollback/hủy upload (đã sửa với lỗi được xử lý)

- **Thao tác/tác nhân:** tác giả tải tài sản, tải chunk Speaking, nhập ZIP; hủy yêu cầu hoặc lỗi flush DB sau khi tạo tệp.
- **Bảo vệ sẵn có:** khóa bản ghi draft/attempt và tên lưu trữ UUID; Speaking/import có bù trừ `except Exception`, upload công khai chưa có.
- **Lỗi:** rollback DB không hoàn tác ghi tệp. `asyncio.CancelledError` cũng không đi qua `except Exception`.
- **Tác động:** tệp không được tham chiếu tồn tại sau yêu cầu lỗi, kể cả ghi âm riêng tư.
- **Bằng chứng:** tiêm lỗi flush sau ghi để lại ảnh công khai; hủy để lại chunk Speaking và cả ba tệp tài sản nhập. Các kiểm tra này thất bại trên mốc ban đầu.
- **Sửa:** bù trừ sau khi thoát giao dịch xử lý hủy/lỗi thường, chờ luồng ghi upload công khai kết thúc trước dọn dẹp và xác minh tham chiếu đã commit bằng session mới trước khi xóa đường dẫn của thao tác. Công việc filesystem được chuyển sang thread khi phù hợp.
- **Xác minh:** lỗi flush/hủy ảnh công khai và hủy thread vùng tạm; rollback/hủy chunk riêng tư; rollback/hủy import; tất cả kiểm tra nhất quán tệp/DB trong thư mục tạm.
- **Ranh giới:** kill tiến trình hoặc DB mất kết nối khiến không xác minh được tham chiếu vẫn cần đối soát; xem rủi ro hoãn lại. Đây không phải giao dịch filesystem phân tán.

### C3 — Mất xác nhận commit dẫn đến xóa media đã commit (đã sửa ở chunk/import/clone phiên bản)

- **Thao tác/tác nhân:** upload Speaking, import ZIP hoặc clone phiên bản đang commit, rồi lỗi kết nối/hủy trước khi bên gọi biết thành công; bản ghi DB và tệp vật lý tương ứng.
- **Bảo vệ sẵn có:** đường dẫn sinh tự động và bù trừ rollback, nhưng bù trừ giả định mọi exception đều đồng nghĩa rollback.
- **Lỗi:** giao dịch commit, thoát context ném lỗi, bù trừ vô điều kiện xóa tệp vẫn được bản ghi đã commit tham chiếu.
- **Tác động:** bản ghi asset/chunk đã lưu trỏ tệp nguồn thiếu; bản ghi âm/nội dung clone hoặc import không dùng được.
- **Bằng chứng:** wrapper giao dịch commit thành công rồi tiêm lỗi mất xác nhận. Kiểm thử chunk riêng tư, import và clone ban đầu tìm được bản ghi đã commit nhưng thiếu tệp.
- **Sửa:** bù trừ chung kiểm tra tài sản công khai, chunk Speaking thô và artifact Speaking chuẩn hóa trước unlink; ưu tiên tham chiếu đã commit. Nếu xác minh lỗi, giữ tệp có thể đã commit và cảnh báo đối soát không chứa nội dung.
- **Xác minh:** kiểm thử mất xác nhận commit trong `test_concurrency_hardening.py`, `test_speaking_media.py`, `test_transfer.py`, `test_asset_cloning.py`. Upload công khai kiểm tra cả exception thường và hủy sau commit. Giữ tương thích ZIP khứ hồi và ID tài sản.

### C4 — Cấp phát upload đồng thời không giới hạn / sao chép đồng bộ (đã sửa upload công khai)

- **Thao tác/tác nhân:** tác giả tải ảnh/âm thanh đồng thời; RAM, event loop và khóa Builder.
- **Bảo vệ sẵn có:** xác minh ảnh 10 MB / âm thanh 100 MB trong storage, chỉ áp dụng sau khi `await upload.read()` cấp phát toàn bộ đầu vào.
- **Lỗi:** mỗi yêu cầu đọc đầu vào lớn tùy ý trước kiểm giới hạn, rồi ghi đồng bộ khi giữ khóa soạn thảo.
- **Tác động:** nguy cơ hết bộ nhớ và tranh chấp khóa/event loop có thể tránh được ngay với số upload đồng thời vừa phải.
- **Bằng chứng:** mốc ban đầu không đạt kiểm tra đọc có giới hạn. Kiểm thử storage mới cấp 2 MiB với giới hạn 1 MiB, xác minh dừng đọc đúng giới hạn + 1 byte và không để lại đầu ra.
- **Sửa:** đọc luồng có giới hạn dùng chunk tối đa 1 MiB trên worker thread, trước khi mở giao dịch soạn thảo. Giữ giới hạn MIME/phần mở rộng/kích thước và DTO phản hồi. Tạo đích độc quyền/dọn sao chép theo quyền sở hữu tránh unlink đường dẫn tồn tại trước khi lỗi tạo tệp.
- **Xác minh:** đọc có giới hạn, từ chối quá cỡ, dữ liệu/siêu dữ liệu thành công, hủy và rollback. Ba kiểm thử giao dịch độc lập bổ sung dừng bộ ghi tệp trong khi giao dịch cạnh tranh commit trạng thái published/archived/deleted, rồi xác minh upload từ chối draft cũ và xóa tệp tạm. Không thêm giới hạn đồng thời toàn ứng dụng.

## Bảo vệ hiện có được giữ và kiểm tra

| Phạm vi | Ranh giới hiện có và kết quả | Bằng chứng |
| --- | --- | --- |
| Autosave Answer/Writing | Khóa attempt và revision từng đáp án/task. Phát lại payload đã commit giống nhau không tăng revision; giá trị cũ xung đột trả 409 hiện có. Giữ lọc chủ sở hữu. | `test_attempt_response_concurrency.py` với kết nối độc lập hiện có; không viết lại evaluator/hợp đồng revision. |
| Autosave so với nộp | Cùng tuần tự hóa qua attempt. Save commit trước được chấm; submit trước từ chối mutation đến muộn. Server đọc deadline sau khi lấy khóa. | Kiểm thử ép cả hai bên thắng khóa, deadline hết trong lúc chờ và học viên khác save/submit khi giữ attempt đầu. |
| Hoàn tất frontend | `RevisionAutosaveQueue.flush()` chờ worker liên quan; nộp chờ flush, đối soát kết quả chưa rõ, chốt vòng đời cuối từ chối mở lại muộn. | Đã đọc bốn tệp hook/queue/lifecycle được yêu cầu; giữ Vitest autosave, khôi phục draft và lifecycle. Không đổi mã frontend. |
| Duy nhất/thứ tự Full Mock | Index duy nhất riêng phần ngăn attempt mô-đun trùng; tuần tự cha bảo vệ tạo lười mô-đun kế và hoàn tất xem lại. | Kiểm thử Full Mock/lịch sử Speaking hiện có cùng ép advance trùng/cô lập session. Vẫn hỗ trợ attempt luyện tập độc lập. |
| Revision/publish Builder | Khóa actor → test → version → resource, kiểm revision, index duy nhất riêng phần draft/published và số phiên bản duy nhất. Publish chờ edit commit hoặc editor nhận xung đột phiên bản bất biến. | `test_test_version_concurrency.py` kiểm tường minh hai thứ tự publish/edit và revision tài nguyên độc lập. Không cần ràng buộc mới. |
| Kiểm duyệt | Cùng ranh giới khóa version/test đóng băng đề nghị chờ duyệt; khóa request, kiểm trạng thái cuối và khóa thông báo duy nhất tuần tự quyết định. | `test_moderation_concurrency.py`, kiểm thử governance; phê duyệt độc lập hiện có xác minh một publish/một thông báo. |
| Thử lại media Speaking | Khóa cha → attempt, ràng buộc duy nhất segment/sequence, checksum bằng nhau khi phát lại giống nhau, từ chối dữ liệu khác, yêu cầu manifest liên tục đã đóng trước hoàn tất. | Kiểm thử chunk trùng kết nối độc lập, manifest/hoàn tất/khôi phục hiện có; hủy và commit chưa rõ mới. Giữ outbox dọn media riêng tư bền vững. |
| Writing AI | Khóa attempt khử trùng tạo, `force=True` chủ ý tạo lượt mới, khóa run chỉ nhận PENDING nguyên tử, trạng thái cuối bảo vệ checkpoint/hoàn tất/hủy, sự kiện có thứ tự dưới khóa run. | Kiểm thử Writing AI hiện có và create/claim/cancel kết nối độc lập mới với provider giả được kiểm soát. Registry tác vụ Local chỉ tối ưu dispatch. |
| Speaking AI | Claim run trong DB + hàng rào lease token, heartbeat, checkpoint kiểm token; hủy đã commit không bị worker cũ đảo ngược. | `test_speaking_ai_runs.py` hiện có: create/claim độc lập, bên thắng complete/cancel và restart/fencing cũ. |
| ASR | Claim/lease/checkpoint DB riêng, duy nhất artifact/cache chuẩn hóa, tái dùng response READY, restart giữ phiên âm xong. | `test_speaking_transcript.py` hiện có: claim worker độc lập, token cũ, dừng/khôi phục, phát lại. Không gọi provider lời nói thật. |
| Classroom/auth/admin | Khóa Classroom và index lời mời chờ/thành viên hoạt động; bắt đầu bài tập kiểm lại thành viên/archive/đủ điều kiện trong giao dịch tạo; khóa actor phối hợp hạ quyền. Khóa refresh cho một session kế; yêu cầu tải lại trạng thái tài khoản. Thông báo xử lý xung đột bằng DB. | Kiểm thử Classroom, bài tập, admin, thông báo và xoay refresh độc lập hiện có; không thêm khóa tính đúng đắn cục bộ tiến trình. |

## Khôi phục và rủi ro còn lại

1. **Ngữ nghĩa khôi phục đã xác minh, không viết lại:** Writing đánh dấu run active cũ FAILED (`STALE_RUN`) khi get/list/create; thử lại tạo run mới, bảo vệ trạng thái cuối chặn run cũ. Speaking AI/ASR khôi phục PENDING/lease hết hạn lúc khởi động; create/retry tường minh cũng xếp lại việc cũ, giữ checkpoint an toàn. API hiện có vì vậy cho đường khôi phục nếu commit xảy ra trước dispatch Local. Không thêm scanner toàn cục định kỳ. Việc không ai quan sát có thể chờ khởi động hoặc retry tường minh; ghi rõ độ trễ vận hành này, không tuyên bố dispatch tự động liên tục.
2. **Khả dĩ/vận hành, hoãn lại:** tiến trình chết đột ngột sau tạo tệp trước commit/bù trừ, hoặc DB lỗi khi xác minh kết quả chưa rõ, có thể để lại tệp mồ côi. Dọn dẹp chủ ý giữ tệp chưa xác minh được commit. Nhật ký upload bền vững và đối soát theo tham chiếu có thể xử lý; không xóa mù theo tuổi hoặc ngầm hứa lưu trữ nguyên tử khi crash. Outbox Speaking hiện có vẫn xử lý xóa đã commit.
3. **Khả dĩ, cần tái hiện riêng:** sửa tài sản kế thừa cũ có đường sao chép/dọn exception riêng trong Reading/Listening/Writing; không khái quát xác minh clone phiên bản sang đó. Cần thêm kiểm thử tiêm mất xác nhận commit trước khi mở rộng sửa.
4. **Tác dụng phụ bên ngoài, hoãn lại:** lease DB bảo vệ kết quả lưu, không bảo vệ yêu cầu đã gửi provider. Tiêu thụ provider ngay trước crash/checkpoint có thể lặp khi retry nếu provider không hỗ trợ idempotency key. Không tuyên bố tính phí bên ngoài đúng một lần; `force=True` chủ ý cho đánh giá mới.
5. **Tranh chấp khả dĩ, chưa tái hiện thành lỗi tính đúng đắn:** xác minh/sao chép import ZIP và một số dọn storage vẫn đồng bộ; service có thể giữ giao dịch DB ngắn để duyệt nội dung. Chưa đo hết pool hoặc tuần tự hóa người dùng không liên quan để biện minh queue, khóa toàn cục hay đổi pool. Đã sửa trực tiếp cấp phát toàn tệp có thể tránh của upload công khai.
6. **Auth chồng lấn, chưa chứng minh lỗi mới:** refresh đang chạy có thể chồng lúc vô hiệu hóa tài khoản, nhưng yêu cầu xác thực sau tải lại trạng thái hoạt động. Giữ xoay token/khóa role/tài nguyên; không suy đoán ngữ nghĩa token mới.
7. **Lệch metadata schema có từ trước, hoãn lại:** nâng cấp Alembic sạch và head duy nhất (`20261013_0035`) đạt, nhưng `alembic check` tùy chọn báo `ix_attempt_events_attempt_type` có trong migration/DB, thiếu ORM metadata. Index đã có ở mốc ban đầu; nhiệm vụ không sửa migration hoặc xóa index.

## Xác minh và đo lường

Hồi quy tập trung chạy trước trên đường có lỗi: ba deadlock Full Mock thật, rò tệp/đọc không giới hạn upload công khai, hai lỗi chunk riêng, hai lỗi import ZIP và lỗi mất xác nhận clone phiên bản. Chạy lại ca đã sửa cùng bộ liên quan hiện có. Đồng thời thật dùng session/kết nối PostgreSQL độc lập và hàng rào tường minh; kiểm thử lỗi chủ ý tiêm tại flush hoặc sau commit thành công. Không âm thầm tính tác vụ lỗi là thành công.

Kiểm tra nhanh save/submit giới hạn tám kết nối ép tám khóa attempt chồng lấn và ghi PID backend PostgreSQL khác nhau, độ trễ, điểm đã lưu. Lần đo Local đầu dùng tám kết nối riêng: trung vị 1306.7 ms, cao nhất 1310.7 ms mỗi cặp save-cộng-submit, gồm chờ hàng rào, trong lúc xác minh khác cũng chạy. Đây là bằng chứng hồi quy loopback, không phải benchmark năng lực production. Không thêm limiter toàn cục tùy tiện hoặc hạ tầng queue mới.

| Kiểm tra Local | Kết quả |
| --- | --- |
| Toàn bộ pytest backend | 2,603 đạt, 2 bỏ qua trong 772.58 s trên PostgreSQL riêng. Ba ca upload/vòng đời bổ sung được xác minh riêng trong lần chạy mô-đun tập trung 22 ca. Bỏ qua là bảo vệ symlink Windows hiện có (`test_modal_web_runtime.py`, `test_writing_benchmark_images.py`); không bỏ qua hồi quy đồng thời. |
| Bộ backend vòng đời/storage/transfer tập trung | 78 đạt; sau đó mở rộng mô-đun hồi quy thêm ba thứ tự xen kẽ upload/vòng đời, chạy lại: 22 đạt. |
| Ruff lint và định dạng | Đạt; 362 tệp Python đã đúng định dạng. |
| TypeScript và ESLint frontend | Đạt. |
| Toàn bộ Vitest | 123 tệp, 1,406 kiểm thử đạt với `--maxWorkers=2`. Lần đầu không giới hạn worker có timeout kiểm thử cũ không liên quan khi xác minh song song; lần chạy lại toàn bộ có giới hạn đạt mà không sửa kiểm thử/timeout. |
| Alembic | Hai DB riêng nâng cấp sạch tới head duy nhất `20261013_0035`; không đổi migration. Kiểm metadata tùy chọn báo lệch index có sẵn như trên. |
| `git diff --check` | Đạt trên mọi đường dẫn bàn giao. |

Bản bàn giao là commit chứa kiểm toán này trên `main`. Chỉ dẫn cuối của người dùng yêu cầu push và kết thúc không theo dõi CI; vì vậy kết quả CI/Golden Path của bản này chưa được xác minh tại đây. Không cần migration; giữ bảo đảm duy nhất/index hiện có.
