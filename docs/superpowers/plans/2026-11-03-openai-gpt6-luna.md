# Kế hoạch tích hợp OpenAI GPT-6 Luna

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans theo từng nhiệm vụ, kết hợp dispatching-parallel-agents cho các phạm vi file độc lập. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tích hợp `gpt-6-luna` cho Writing/Speaking qua adapter hiện có, hỗ trợ Modal CPU và giữ các hợp đồng chấm điểm.

**Architecture:** Giữ FastAPI modular monolith, HTTPX Chat Completions và JSON mode được validation cục bộ. Cấu hình provider Modal được đóng băng rõ ràng; chỉ vLLM được chọn tường minh mới gắn LLM GPU. Thêm giới hạn request OpenAI dùng chung và usage Speaking qua các checkpoints có lease.

**Tech Stack:** FastAPI, Pydantic, HTTPX, PostgreSQL/SQLAlchemy, Modal; pytest/MockTransport.

**Spec:** Yêu cầu 10 phase của người dùng trong task hiện tại; ranh giới tại [architecture](../../architecture.md), [Speaking design](../specs/2026-10-11-speaking-engine-ai-grading-design.md), phased plan và self-review. Baseline `33f40c78756ea203ba1819111409557db02f9915`.

## Ràng buộc chung

- Chỉ model `gpt-6-luna` khi chọn profile OpenAI; không tự đổi model/provider, không thay rubric hoặc official human scores.
- Không đọc/in key vào output/log/báo cáo; `.env` không được Git theo dõi. Không gọi paid API trước xác nhận cấu hình; không deploy/tạo tài nguyên cloud.
- Dùng mock mặc định. Smoke thật opt-in, tối thiểu request, báo riêng kết quả API và deployment.
- Giữ ASR/acoustic evidence độc lập; PR không thể chấm chỉ từ transcript. Giữ leases, checkpoints, quyền, historical data và vLLM.
- Không thay topology DB/assets hoặc frontend. Giữ các local changes có sẵn trong checkout chính.

## Các tình huống cần rà soát

- OpenAI-only không import/include/resolve URL vLLM GPU, kể cả local/remote import graph.
- 429 hết credit khác rate limit tạm thời; không replay completion POST khi kết quả tính phí không rõ.
- Gate dùng chung giữa Writing/Speaking, có giới hạn hàng chờ và trả suất khi hủy.
- Model/reasoning/output policy đổi phải thay cache identity phù hợp, không đổi lịch sử đã lưu.
- Usage sau crash chỉ là quan sát, không chứng minh hóa đơn chính xác hay exactly-once inference.

## Nhiệm vụ

### 1. Audit và baseline

- [x] Fetch origin/main, kiểm status, ghi baseline, tái dùng worktree cô lập trên `codex/openai-gpt6-luna`.
- [x] Đọc adapter, Settings, Modal/setup, kiến trúc và tài liệu OpenAI chính thức cho đúng model.
- [x] Chạy focused baseline với JWT giả; ghi riêng lỗi thiếu cấu hình môi trường nếu có.

### 2. Transport/config dùng chung

Files: `backend/app/core/config.py`, `backend/app/providers/writing_llm/`, `backend/app/providers/speaking_llm/configured.py`, tests.

- [x] Viết tests model mặc định/selection, bounded requests/cancellation/queue-full, single POST cho 401/429/timeouts/outages, sanitized billing exhaustion.
- [x] Chạy tests đỏ; triển khai giới hạn chung theo event loop/process, timeout/output caps và retry chỉ cho readiness GET an toàn với backoff+jitter.
- [x] Giữ JSON validation hiện có, bỏ parameters không phù hợp, cập nhật cache identity cho policy đầu ra.
- [x] Chạy provider tests và focused grading suites.

### 3. Modal CPU và setup

Files: `deploy/modal/app.py`, `deploy/modal/web_runtime.py`, `scripts/modal_web_setup.py`, deployment tests.

- [x] Viết tests đỏ cho OpenAI-only graph, flags ASR độc lập/frozen, mixed providers, secret preservation và explicit vLLM.
- [x] Chỉ import/include/resolve LLM GPU khi cần; freeze selectors không chứa secret; cấu hình key qua Modal Secret.
- [x] Setup giữ backend-only secrets, hỗ trợ cập nhật có chủ đích; test dùng Settings giả, không đọc `.env` thật.

### 4. Speaking usage

Files: `backend/app/services/speaking_scorer.py`, `speaking_ai_worker.py`, focused tests.

- [x] Viết tests đỏ cho usage success/repair/failure, bounded allowlist và fenced persistence.
- [x] Dùng callback mặc định tùy chọn, ghi usage vào JSON hiện có ngoài provider I/O; không đổi DTO/rubric/PR/checkpoints.

### 5. Hướng dẫn và smoke opt-in

Files: `backend/.env.example`, `docs/ai-writing.md`, `docs/speaking-grading.md`, `docs/modal-web.md`, coverage/index khi phù hợp; CLI smoke nhỏ và tests.

- [x] Viết hướng dẫn tiếng Việt cho local/Modal Secret/CPU/ASR/AWS/vLLM, usage cost và Mermaid.
- [x] Smoke thật mặc định từ chối chạy; sau xác nhận người dùng mới thực hiện một completion nhỏ. Không in provider response thô/key.
- [x] Ghi baseline, files, tests và các phần NOT VERIFIED trong báo cáo gắn với tài liệu chuẩn.

### 6. Kiểm chứng và bàn giao

- [x] Review full diff, check links/Mermaid/format/lint/typecheck và grading regressions/isolated PostgreSQL.
- [ ] Fetch/reconcile origin/main, giữ local changes, commit và push main sau kiểm chứng.
- [ ] Kiểm đúng SHA trên remote, CI và E2E; phân biệt mock/API thật/deployment thật.

## Kết quả trước bàn giao

- Focused integration: 363 pass, 1 symlink skip trên Windows (194,13 s); follow-up provider/usage/scorer/smoke: 132 pass (1,52 s), các nhóm có overlap. OpenAI worker persistence/cache/human-score mock PostgreSQL: 4 pass (1,92 s).
- Smoke thật sau xác nhận: 1 completion, model gpt-6-luna, 17 input + 11 output tokens, PASS. Không chạy full grading thật hoặc deployment Modal.
- Ruff lint/format đạt; frontend typecheck/lint đạt. 102 tài liệu/1.804 local links hợp lệ; 27 Mermaid diagrams parse thành công.
- Review độc lập phát hiện usage bị mất trên malformed/refusal content; đã sửa qua chu kỳ đỏ/xanh, giữ metadata allowlisted. Không còn P1/P2 chưa xử lý.
- Không cần migration hoặc SDK mới. Rollback: chọn provider vLLM/cấu hình cũ và restart workers; không sửa/xóa historical results.
