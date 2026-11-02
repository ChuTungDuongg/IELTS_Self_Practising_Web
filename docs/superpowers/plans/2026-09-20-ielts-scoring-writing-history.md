# Kế hoạch triển khai điểm IELTS, Writing và History

> **Phân loại tài liệu: HISTORICAL.** Tham khảo lịch sử; không phải contract hiện hành.
> Mục đích: kế hoạch triển khai điểm IELTS, Writing và History. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [mã triển khai](../../../backend/app/services/mts_writing.py).
> Đọc cùng [hướng dẫn module hiện hành](../../modules/writing.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

> **Dành cho tác nhân triển khai:** bắt buộc dùng skill superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans theo từng công việc. Theo dõi bằng checkbox (`- [ ]`).

**Mục tiêu:** thêm tính band IELTS theo quy tắc sản phẩm, quy trình Writing builder/làm bài/review có lưu trữ, chấm Writing thủ công và lịch sử attempts do backend tổng hợp; không gây regression Reading/Listening.

**Kiến trúc:** mở rộng service layer SQLAlchemy/Pydantic và bổ sung REST DTOs tương thích. FastAPI giữ trách nhiệm quy đổi điểm, kiểm Writing, lưu bài, chọn dữ liệu tổng hợp và làm tròn overall. Thêm Next.js components tập trung sử dụng các contracts đó, tái dùng builder, timer, assets, review và hệ thống giao diện hiện có.

**Công nghệ:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy asyncio, PostgreSQL, Alembic, pytest, Next.js 16, React 19, TypeScript 5.9, Zod 4, Vitest, Testing Library, Tailwind/CSS.

**Đặc tả:** `docs/superpowers/specs/2026-09-20-ielts-scoring-writing-history-design.md`

## Ràng buộc chung

- Reading/Listening dùng đúng bảng quy đổi sản phẩm trong đặc tả; raw scores 0–2 và mọi module không có 40 câu đều có `band_score = null`.
- `attempts.band_score` là `NUMERIC(2,1)` nullable; giữ `raw_score`/`max_score`.
- Versions đã publish bất biến; attempts giữ tham chiếu version đóng băng.
- Writing khởi tạo đúng Task 1/order 0 và Task 2/order 1 cố định; chỉ Task 1 nhận `WRITING_TASK_IMAGE`.
- Bài Writing dùng plain text và `AttemptWritingResponse`; word count backend có thẩm quyền.
- Writing không có raw/max score khách quan hoặc band tự động.
- Backend tính overall từ đúng ba bands và làm tròn theo bước 0.5 bằng decimal half-up.
- DTO làm bài đang diễn ra không bao giờ lộ answer keys khách quan.
- Không triển khai Speaking, xác thực hoặc chấm Writing tự động.
- Giữ sửa đổi local `frontend/next-env.d.ts`; không stage hoặc ghi đè.
- Không thêm đề có bản quyền hoặc runtime dependency mới.

## Trọng tâm review

- Objective attempt hết giờ phải được chấm trước finalize, kể cả khi không có submit request rõ ràng; công việc 2 thêm integration test.
- Writing task được clone có thể giữ tham chiếu ảnh dùng chung hiện có; ảnh mới gắn phải thuộc draft có thể sửa. Công việc 3 kiểm cả hai.
- Lưu Writing rõ ràng hoặc trước submit mà fail phải giữ attempt chưa nộp, hiện lỗi có thể retry; công việc 6 kiểm.
- Xóa attempt được history group chọn phải tải lại lựa chọn/overall từ server, không tính lại trong React; công việc 7 kiểm refresh.
- Writing drafts rỗng/chưa đủ vẫn sửa được và theo chính sách publish warnings hiện tại; task identity sai và ảnh Task 2 vẫn phải chặn. Công việc 3 kiểm cả hai nhóm.

---

### Công việc 1: Domain tính band và lưu trữ

**Tệp:**
- Tạo: `backend/app/domains/scoring/ielts_band.py`
- Tạo: `backend/tests/test_ielts_band.py`
- Tạo: `backend/alembic/versions/20260920_0007_attempt_band_score.py`
- Sửa: `backend/app/domains/scoring/__init__.py`
- Sửa: `backend/app/models/entities.py`
- Sửa: `backend/app/schemas/attempts.py`

**Giao diện:**
- Đầu ra: `listening_raw_to_band(int, int) -> float | None`
- Đầu ra: `reading_raw_to_band(int, int) -> float | None`
- Đầu ra: `round_to_half(Decimal) -> Decimal`
- Đầu ra: `project_overall_band(float | Decimal | None, float | Decimal | None, float | Decimal | None) -> float | None`
- Đầu ra: `Attempt.band_score` và `AttemptResponse.band_score`

- [ ] **Bước 1: Viết pure scoring tests**

```python
PRODUCT_BANDS = {
    40: 9.0, 39: 9.0, 38: 8.5, 37: 8.5, 36: 8.0, 35: 8.0,
    34: 7.5, 33: 7.5, 32: 7.0, 30: 7.0, 29: 6.5, 27: 6.5,
    26: 6.0, 23: 6.0, 22: 5.5, 20: 5.5, 19: 5.0, 16: 5.0,
    15: 4.5, 13: 4.5, 12: 4.0, 10: 4.0, 9: 3.5, 7: 3.5,
    6: 3.0, 5: 3.0, 4: 2.5, 3: 2.5, 2: None, 0: None,
}

@pytest.mark.parametrize("raw, expected", PRODUCT_BANDS.items())
def test_reading_and_listening_use_product_table(raw, expected):
    assert reading_raw_to_band(raw, 40) == expected
    assert listening_raw_to_band(raw, 40) == expected
```

Kiểm thêm module không có 40 câu trả `None`; raw/max không hợp lệ gây `ValueError`; thiếu đầu vào overall trả `None`; ví dụ cho kết quả 7.0/7.0/7.5; và `round_to_half(Decimal("7.25")) == Decimal("7.5")`.

- [ ] **Bước 2: Chạy scoring test và xác nhận fail**

Chạy: `Set-Location backend; uv run pytest tests/test_ielts_band.py -q`

Mong đợi: import `app.domains.scoring.ielts_band` fail.

- [ ] **Bước 3: Triển khai bảng ngưỡng bất biến và làm tròn Decimal**

```python
_PRODUCT_THRESHOLDS = (
    (39, 9.0), (37, 8.5), (35, 8.0), (33, 7.5), (30, 7.0),
    (27, 6.5), (23, 6.0), (20, 5.5), (16, 5.0), (13, 4.5),
    (10, 4.0), (7, 3.5), (5, 3.0), (3, 2.5),
)
```

Kiểm đầu vào trước điều kiện `max_score == 40`, trả ngưỡng khớp đầu tiên và dùng `ROUND_HALF_UP` sau khi nhân hai.

- [ ] **Bước 4: Thêm model field, response field và migration**

Dùng `sa.Numeric(precision=2, scale=1)` trong migration và `Numeric(2, 1)` với `Decimal | None` trong SQLAlchemy. Thêm `band_score: float | None` vào `AttemptResponse` và `HistoryItem`.

- [ ] **Bước 5: Chạy tests tập trung và kiểm SQL migration**

Chạy: `Set-Location backend; uv run pytest tests/test_ielts_band.py -q; uv run alembic upgrade head --sql | Out-Null`

Mong đợi: scoring tests pass, Alembic render không exception.

- [ ] **Bước 6: Commit scoring domain**

```powershell
git add backend/app/domains/scoring backend/app/models/entities.py backend/app/schemas/attempts.py backend/alembic/versions/20260920_0007_attempt_band_score.py backend/tests/test_ielts_band.py
git commit -m "feat: add IELTS band scoring domain"
```

### Công việc 2: Finalize attempt và tổng hợp lịch sử tại backend

**Tệp:**
- Sửa: `backend/app/services/attempts.py`
- Sửa: `backend/app/repositories/attempts.py`
- Sửa: `backend/app/schemas/attempts.py`
- Sửa: `backend/tests/test_timer.py`
- Tạo: `backend/tests/test_attempt_scoring_history.py`

**Giao diện:**
- Đầu vào: scoring helpers của công việc 1 và `Attempt.band_score`
- Đầu ra: đồng bộ attempt bất đồng bộ, chấm trước finalize
- Đầu ra: `HistoryGroup` và `AttemptList.groups`

- [ ] **Bước 1: Viết tests finalize và serialization cho bài khách quan**

Tạo module khách quan giả tưởng 40 câu đã publish, lưu số câu đúng ở các biên quy đổi rồi submit; kiểm raw/max/band trong `AttemptResponse`, review và history. Thêm ca hết giờ gọi `get()` sau deadline, kiểm `AUTO_SUBMITTED` và cùng trường điểm. Thêm ca Writing `_score` xác nhận cả ba trường điểm null.

- [ ] **Bước 2: Viết tests nhóm lịch sử**

Tạo nhiều finalized attempts cùng version/module với giờ hoàn tất khác nhau, thêm attempts của version khác. Kiểm groups không gộp versions; chọn attempt finalized mới nhất từng kỹ năng; giữ mọi hàng trong `items`; cần đủ ba bands để có overall; áp dụng kết quả ví dụ công việc 1.

- [ ] **Bước 3: Chạy tests và xác nhận fail**

Chạy: `Set-Location backend; uv run pytest tests/test_attempt_scoring_history.py tests/test_timer.py -q`

Mong đợi: fail vì thiếu band fields/groups và chưa chấm khi timer finalize.

- [ ] **Bước 4: Refactor đồng bộ và tính điểm**

Chuyển `_synchronize_state` thành `async`; await từ `get`, activity, answer, flag, highlight, Writing save và submit; gọi `_score` trước mọi terminal transition do hàm tạo. `_score` phân nhánh rõ theo `ModuleType`: module khách quan tính raw/max/band, Writing xóa các giá trị đó.

- [ ] **Bước 5: Thêm history schemas và xây dữ liệu tổng hợp**

```python
class HistoryGroup(BaseModel):
    test_id: UUID
    test_version_id: UUID
    test_title: str
    version_number: int
    reading: HistoryItem | None = None
    listening: HistoryItem | None = None
    writing: HistoryItem | None = None
    overall_band_score: float | None = None
```

Chọn items mới nhất không ở `IN_PROGRESS` theo `finished_at` rồi `started_at`; tính overall bằng domain helper dùng chung, trả `AttemptList(items=..., groups=..., total=...)`.

- [ ] **Bước 6: Chạy backend tests tập trung**

Chạy: `Set-Location backend; uv run pytest tests/test_attempt_scoring_history.py tests/test_timer.py tests/test_attempt_state_machine.py -q`

Mong đợi: tất cả đều pass.

- [ ] **Bước 7: Commit domain điểm attempt và lịch sử**

```powershell
git add backend/app/services/attempts.py backend/app/repositories/attempts.py backend/app/schemas/attempts.py backend/tests/test_attempt_scoring_history.py backend/tests/test_timer.py
git commit -m "feat: score finalized attempts and aggregate history"
```

### Công việc 3: Writing Builder backend và validation

**Tệp:**
- Tạo: `backend/app/services/writing.py`
- Tạo: `backend/app/api/v1/writing.py`
- Tạo: `backend/tests/test_writing_builder.py`
- Sửa: `backend/app/api/v1/router.py`
- Sửa: `backend/app/models/entities.py`
- Sửa: `backend/app/repositories/tests.py`
- Sửa: `backend/app/schemas/content.py`
- Sửa: `backend/app/services/reading.py`
- Sửa: `backend/app/services/tests.py`
- Sửa: `backend/tests/test_version_validation.py`

**Giao diện:**
- Đầu ra: `BuilderWritingTask`, `WritingTaskWrite` và `BuilderModule.writing_tasks`
- Đầu ra: `PUT /writing/tasks/{task_id}`
- Mở rộng: tạo module chung hiện có để khởi tạo các Writing tasks cố định một cách nguyên tử

- [ ] **Bước 1: Viết tests cho Writing builder service**

Kiểm khởi tạo module nguyên tử và mặc định; sửa prompt/số từ tối thiểu/thời lượng; ảnh Task 1 hợp lệ; từ chối sai loại hoặc sai version; cấm ảnh Task 2; version đã publish bất biến; cleanup ảnh khi gỡ; xóa module.

- [ ] **Bước 2: Viết tests validation và clone**

Kiểm Writing draft chưa đủ vẫn lưu và báo readiness warnings; số/thứ tự sai và ảnh Task 2 phải chặn; clone giữ cả hai tasks và tham chiếu ảnh; repository loading cung cấp metadata ảnh.

- [ ] **Bước 3: Chạy tests và xác nhận fail**

Chạy: `Set-Location backend; uv run pytest tests/test_writing_builder.py tests/test_version_validation.py -q`

Mong đợi: thiếu hành vi DTO/service/route.

- [ ] **Bước 4: Mở rộng builder contract và tải relationships**

Thêm relationship `WritingTask.image_asset` rõ ràng, tải từ `version_detail_query`, trình bày qua `ReadingService._present_version` và bổ sung mặc định `writing_tasks=[]` tương thích.

- [ ] **Bước 5: Thêm khởi tạo nguyên tử và validation cập nhật task**

Khi `ModuleCreate.module_type == WRITING`, thêm hai task records cố định trước flush. `WritingTaskWrite` chỉ chứa `prompt`, `minimum_recommended_words`, `recommended_duration_seconds` và `image_asset_id`. Service suy ra identity từ task lưu trữ và áp dụng quy tắc assets Task 1/Task 2.

- [ ] **Bước 6: Mở rộng publish validation**

Xem ownership module, tính duy nhất số/thứ tự task và cặp cho phép, loại/chủ ảnh, quy tắc cấm ảnh Task 2 là errors. Phát readiness warnings cho thiếu task, prompt trống và recommendation không chuẩn, nhưng vẫn cho lưu draft chưa đủ.

- [ ] **Bước 7: Chạy builder tests tập trung và OpenAPI contract test**

Chạy: `Set-Location backend; uv run pytest tests/test_writing_builder.py tests/test_version_validation.py tests/test_api_contract.py -q`

Mong đợi: tất cả pass, gồm route Writing task mới trong OpenAPI.

- [ ] **Bước 8: Commit Writing builder backend**

```powershell
git add backend/app/api/v1/writing.py backend/app/api/v1/router.py backend/app/models/entities.py backend/app/repositories/tests.py backend/app/schemas/content.py backend/app/services/reading.py backend/app/services/tests.py backend/app/services/writing.py backend/tests/test_writing_builder.py backend/tests/test_version_validation.py backend/tests/test_api_contract.py
git commit -m "feat: add Writing builder backend"
```

### Công việc 4: APIs bài Writing, review và điểm thủ công

**Tệp:**
- Sửa: `backend/app/schemas/attempts.py`
- Sửa: `backend/app/schemas/content.py`
- Sửa: `backend/app/repositories/attempts.py`
- Sửa: `backend/app/services/attempts.py`
- Sửa: `backend/app/api/v1/attempts.py`
- Tạo: `backend/tests/test_writing_attempts.py`

**Giao diện:**
- Đầu ra: `WritingResponseUpdate`, `WritingResponse`, `WritingScoreUpdate`
- Đầu ra: `ExamWritingTask` trong `AttemptExam.writing_tasks`
- Đầu ra: `WritingAttemptReview`
- Đầu ra: endpoints lưu Writing, review Writing và điểm thủ công

- [ ] **Bước 1: Viết tests vòng đời bài Writing**

Bắt đầu Writing attempt đã publish; kiểm nội dung đã lưu ban đầu rỗng trong exam DTO; lưu cả hai tasks, kiểm Unicode word counts, upsert một response, tải lại DTO, submit; kiểm responses được giữ còn raw/max/band vẫn null.

- [ ] **Bước 2: Viết tests ownership và validation điểm**

Từ chối save vào objective attempts, task sai version và attempts đã finalize. Chấp nhận mọi nửa band từ 0 đến 9 cho Writing đã finalize; từ chối -0.5, 7.25, 9.5, chấm khi đang làm và chấm objective attempts. Kiểm review/history phản ánh ngay band đã lưu.

- [ ] **Bước 3: Chạy tests và xác nhận fail**

Chạy: `Set-Location backend; uv run pytest tests/test_writing_attempts.py -q`

Mong đợi: thiếu API/service methods và schemas.

- [ ] **Bước 4: Triển khai response upsert và DTO đang làm bài**

Dùng PostgreSQL `insert(...).on_conflict_do_update` trên `(attempt_id, writing_task_id)`, gọi `count_words` ở backend, cập nhật activity time và thêm metadata `WRITING_UPDATED`. Trình bày mọi task của version với nội dung lưu mặc định `""` và word count `0`.

- [ ] **Bước 5: Triển khai Writing review và điểm thủ công**

Dựng review từ tasks của version đóng băng cùng response lookup, gồm metadata ảnh Task 1. Kiểm band bằng Decimal để bước 0.5 chính xác; lưu `Attempt.band_score`, trả review hoặc attempt response đã cập nhật.

- [ ] **Bước 6: Kiểm cách ly answer keys và API contracts**

Chạy: `Set-Location backend; uv run pytest tests/test_writing_attempts.py tests/test_api_contract.py tests/test_writing_text.py -q`

Mong đợi: tất cả pass; active schemas không có answer-key field cho Writing.

- [ ] **Bước 7: Commit Writing attempt APIs**

```powershell
git add backend/app/api/v1/attempts.py backend/app/repositories/attempts.py backend/app/schemas/attempts.py backend/app/schemas/content.py backend/app/services/attempts.py backend/tests/test_writing_attempts.py backend/tests/test_api_contract.py
git commit -m "feat: persist and grade Writing attempts"
```

### Công việc 5: Writing Builder và Draft Preview frontend

**Tệp:**
- Tạo: `frontend/src/features/test-builder/writing-builder.tsx`
- Tạo: `frontend/tests/writing-builder.test.tsx`
- Sửa: `frontend/src/lib/api/builder.ts`
- Sửa: `frontend/src/lib/api/assets.ts`
- Sửa: `frontend/src/lib/routes.ts`
- Sửa: `frontend/src/features/test-builder/builder-workspace-navigation.tsx`
- Sửa: `frontend/src/features/test-builder/draft-preview.tsx`
- Sửa: `frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx`
- Sửa: `frontend/src/app/admin/tests/[testId]/versions/[versionId]/preview/page.tsx`
- Sửa: `frontend/tests/builder-workspace-navigation.test.tsx`
- Sửa: `frontend/tests/builder-workspace-page.test.tsx`
- Sửa: `frontend/tests/draft-preview.test.tsx`

**Giao diện:**
- Đầu vào: builder DTO và task update endpoint của công việc 3
- Đầu ra: `createWritingModule`, `updateWritingTask` và UI Writing workspace

- [ ] **Bước 1: Cập nhật frontend contract fixtures và viết UI tests đang fail**

Thêm `writing_tasks: []` vào builder fixtures hiện có. Kiểm liên kết/trạng thái điều hướng Writing, khởi tạo module, render đúng hai tasks, sửa prompts/minimums/durations, upload/replace/remove/preview ảnh Task 1, không có upload Task 2, xác nhận xóa và nội dung Writing draft preview.

- [ ] **Bước 2: Chạy tests tập trung và xác nhận fail**

Chạy: `Set-Location frontend; npm test -- writing-builder.test.tsx builder-workspace-navigation.test.tsx builder-workspace-page.test.tsx draft-preview.test.tsx`

Mong đợi: thiếu schemas, route acceptance và components.

- [ ] **Bước 3: Mở rộng Zod contracts và API functions**

Thêm `builderWritingTaskSchema`; mặc định `writing_tasks`, passages và listening parts thành mảng rỗng; mở rộng `builderPreviewPath` với `writing`; giữ `uploadAsset("images", ...)` cho ảnh Writing task.

- [ ] **Bước 4: Triển khai Writing builder tập trung**

Dùng lại `BuilderLifecycleProvider`, buttons hiện có, `ConfirmDialog`, `uploadAsset`, xóa module và `router.refresh`. Dùng controlled task editor cards; gửi cập nhật task đầy đủ một lần cho mỗi Save/image mutation.

- [ ] **Bước 5: Bật workspace, overview và preview routing**

Thêm `writing` vào `BuilderWorkspace`, bật hàng tương ứng, render số tasks Writing trong overview, chọn `WritingBuilder`, nhận `?module=writing` và render preview hai tasks không tương tác.

- [ ] **Bước 6: Chạy frontend tests tập trung**

Chạy: `Set-Location frontend; npm test -- writing-builder.test.tsx builder-workspace-navigation.test.tsx builder-workspace-page.test.tsx draft-preview.test.tsx`

Mong đợi: tất cả đều pass.

- [ ] **Bước 7: Commit Writing builder frontend**

```powershell
git add frontend/src/features/test-builder/writing-builder.tsx frontend/src/features/test-builder/builder-workspace-navigation.tsx frontend/src/features/test-builder/draft-preview.tsx frontend/src/lib/api/builder.ts frontend/src/lib/api/assets.ts frontend/src/lib/routes.ts frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx frontend/src/app/admin/tests/[testId]/versions/[versionId]/preview/page.tsx frontend/tests/writing-builder.test.tsx frontend/tests/builder-workspace-navigation.test.tsx frontend/tests/builder-workspace-page.test.tsx frontend/tests/draft-preview.test.tsx
git commit -m "feat: add Writing builder workspace"
```

### Công việc 6: Writing Runner và Review frontend

**Tệp:**
- Tạo: `frontend/src/features/writing/writing-runner.tsx`
- Tạo: `frontend/src/features/writing/writing-review.tsx`
- Tạo: `frontend/tests/writing-runner.test.tsx`
- Tạo: `frontend/tests/writing-review.test.tsx`
- Sửa: `frontend/src/lib/api/attempts.ts`
- Sửa: `frontend/src/lib/api/exam.ts`
- Sửa: `frontend/src/features/exam/start-attempt.tsx`
- Sửa: `frontend/src/app/library/page.tsx`
- Sửa: `frontend/src/app/attempt/[attemptId]/page.tsx`
- Sửa: `frontend/src/app/review/[attemptId]/page.tsx`
- Sửa: `frontend/src/features/reading/reading-review.tsx`
- Sửa: `frontend/src/features/listening/listening-review.tsx`

**Giao diện:**
- Đầu vào: exam/review/save/grade contracts công việc 4
- Đầu ra: giao diện làm bài và review Writing
- Mở rộng: objective review headers với `band_score`

- [ ] **Bước 1: Viết runner tests**

Kiểm hai task tabs, ảnh Task 1, khôi phục text server, cập nhật word count cục bộ, autosave debounce 750 ms, Save ngay, lỗi, thứ tự save trước submit và chặn submit khi save fail.

- [ ] **Bước 2: Viết review và routing tests**

Kiểm hiển thị response/prompt/ảnh/word count, đủ 19 lựa chọn nửa band, gọi API lưu điểm và cập nhật hiển thị, routing attempt/review riêng Writing, objective review headers có band cùng raw/max.

- [ ] **Bước 3: Chạy tests tập trung và xác nhận fail**

Chạy: `Set-Location frontend; npm test -- writing-runner.test.tsx writing-review.test.tsx`

Mong đợi: thiếu API functions và components.

- [ ] **Bước 4: Mở rộng exam và attempt API schemas**

Thêm `band_score` vào attempt schema, Writing task schema vào exam payload, `saveWritingResponse`, `getWritingReview` và `saveWritingScore`. Parse responses bằng Zod, không ép kiểu thiếu kiểm tra.

- [ ] **Bước 5: Triển khai Writing runner**

Dùng lại timer offset helpers và activity heartbeat. Giữ content, dirty revisions, debounce handles và saved/error state theo task. Save rõ ràng hủy timer và persist ngay. Submit đợi save task hiện tại thành công rồi mới gọi `submitAttempt`.

- [ ] **Bước 6: Triển khai Writing review và routing**

Render prompts đóng băng, ảnh Task 1 tùy chọn, bài plain text và word count. Sinh select bằng `Array.from({ length: 19 }, (_, index) => index / 2)`. Route `WRITING` rõ ràng trước Reading fallback.

- [ ] **Bước 7: Thêm Writing vào thư viện đã publish**

Cho `StartAttempt` nhận cả ba modules, mặc định Writing 3,600 giây, render Writing metadata theo task count và giữ objective cards hiện có.

- [ ] **Bước 8: Chạy tests tập trung**

Chạy: `Set-Location frontend; npm test -- writing-runner.test.tsx writing-review.test.tsx word-count.test.ts`

Mong đợi: tất cả đều pass.

- [ ] **Bước 9: Commit UI làm bài và review**

```powershell
git add frontend/src/features/writing frontend/src/lib/api/attempts.ts frontend/src/lib/api/exam.ts frontend/src/features/exam/start-attempt.tsx frontend/src/app/library/page.tsx frontend/src/app/attempt/[attemptId]/page.tsx frontend/src/app/review/[attemptId]/page.tsx frontend/src/features/reading/reading-review.tsx frontend/src/features/listening/listening-review.tsx frontend/tests/writing-runner.test.tsx frontend/tests/writing-review.test.tsx
git commit -m "feat: add Writing runner and manual review"
```

### Công việc 7: History frontend có hai chế độ

**Tệp:**
- Sửa: `frontend/src/lib/api/history.ts`
- Sửa: `frontend/src/features/history/attempt-history-list.tsx`
- Sửa: `frontend/src/app/history/page.tsx`
- Sửa: `frontend/tests/attempt-history-list.test.tsx`

**Giao diện:**
- Đầu vào: `AttemptList` của công việc 2 với groups do server tạo
- Đầu ra: tabs By skill và By test; không tổng hợp điểm ở frontend

- [ ] **Bước 1: Mở rộng fixtures và viết history tests đang fail**

Kiểm IDs/bands ổn định, chuyển tabs, mọi attempts riêng trong By skill, nhóm đúng version trong By test, overall từ server, dấu gạch khi chưa đủ, liên kết module mới nhất được chọn, nội dung raw/band chưa có, Writing Not graded, Continue/Review và refresh sau xóa.

- [ ] **Bước 2: Chạy history test và xác nhận fail**

Chạy: `Set-Location frontend; npm test -- attempt-history-list.test.tsx`

Mong đợi: schema và render tabs/groups fail.

- [ ] **Bước 3: Mở rộng history Zod contract**

Mô hình hóa `HistoryItem`, `HistoryGroup` và response có `items`, `groups`, `total`. Không thêm overall helper phía client.

- [ ] **Bước 4: Refactor history component thành hai góc nhìn**

Dùng chung delete state và xác nhận. Hiển thị điểm theo module/eligibility. Đồng bộ state khi có server props mới để xóa attempt đang được chọn trong nhóm cập nhật cả hai tabs từ backend data.

- [ ] **Bước 5: Chạy history tests**

Chạy: `Set-Location frontend; npm test -- attempt-history-list.test.tsx`

Mong đợi: tất cả đều pass.

- [ ] **Bước 6: Commit History mới**

```powershell
git add frontend/src/lib/api/history.ts frontend/src/features/history/attempt-history-list.tsx frontend/src/app/history/page.tsx frontend/tests/attempt-history-list.test.tsx
git commit -m "feat: add grouped attempt history views"
```

### Công việc 8: Tích hợp giao diện và kiểm chứng đầy đủ

**Tệp:**
- Sửa: `frontend/src/app/globals.css`
- Sửa: `frontend/tests/builder-route.test.tsx`
- Sửa: `frontend/tests/listening-player.test.tsx`
- Sửa: `frontend/tests/reading-instructions.test.tsx`
- Sửa: `frontend/tests/reading-navigation.test.tsx`
- Sửa: `frontend/tests/version-actions.test.tsx`

**Giao diện:**
- Đầu vào: mọi UI components trước đó và CSS tokens hiện có
- Đầu ra: bố cục Writing/History responsive và tương thích dark mode

- [ ] **Bước 1: Thêm quy tắc giao diện responsive**

Mở rộng builder/module tone selectors cho Writing; thêm classes task/editor/runner/review và history tab/group. Dùng `min-width: 0`, grids có wrapping và textarea sizing không gây tràn ngang.

- [ ] **Bước 2: Chạy toàn bộ backend validation suite**

Chạy: `Set-Location backend; uv run ruff check .; uv run ruff format --check .; uv run pytest -q; uv run alembic upgrade head --sql | Out-Null`

Mong đợi: mọi lệnh trả exit code 0.

- [ ] **Bước 3: Chạy toàn bộ frontend validation suite**

Chạy: `Set-Location frontend; npm run lint; npm run typecheck; npm test; npm run build`

Mong đợi: mọi lệnh trả exit code 0.

- [ ] **Bước 4: Kiểm final diff và tệp được bảo vệ**

Chạy: `git diff --check; git status --short; git diff -- frontend/next-env.d.ts`

Mong đợi: không lỗi khoảng trắng; `frontend/next-env.d.ts` chỉ giữ sửa đổi local có sẵn, không được stage trong nhiệm vụ này.

- [ ] **Bước 5: Commit các bản sửa tích hợp cuối**

```powershell
git add frontend/src/app/globals.css backend frontend/src frontend/tests docs/superpowers/plans/2026-09-20-ielts-scoring-writing-history.md
git commit -m "feat: complete IELTS Writing and score history flow"
```
