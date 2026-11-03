# Chạy BandPilot trên Modal

<a id="speaking-hybrid-cpu"></a>

## CPU speech preset `speaking_hybrid_v1` (opt-in)

`SPEAKING_ASR_PROVIDER=azure` chọn profile `speaking_hybrid_v1`. Launcher đọc
provider từ backend Settings và freeze selector không chứa secret trong image.
`SPEECH_ENABLED` là feature gate; `MODAL_ASR_SERVICE_ENABLED` chỉ đúng khi provider
là `modal` và ASR bật. Azure không
import hoặc include dịch vụ faster-whisper T4 và không tải Whisper/torch/CUDA.
Writing/Speaking **grader** vẫn do provider hiện có chọn riêng: hybrid speech
không tự đổi vLLM thành OpenAI. Toàn graph chỉ CPU khi cả hai graders chọn
OpenAI và chart specialist tắt. Legacy GPU entry points vẫn nguyên và có thể
chọn lại; không tự chuyển production.

Web image hybrid thêm Azure SDK `1.53.0`, `onnxruntime==1.23.2`, `numpy==2.2.6`
và `libasound2`, `libssl3`, `ca-certificates`, `ffmpeg`. Azure key/region/locale/
prosody/deadline/concurrency đi qua backend Secret; shell `SPEAKING_AZURE_*`
overrides được chuyển bằng ephemeral Secret, không image/Next.js. Không copy
`backend/.env`. Named config Secret đã chọn phải có key/provider settings trước
chạy entry point trực tiếp; entry point không tự đọc dotenv local.

Chuẩn bị VAD bằng [setup script](../scripts/setup_speaking_vad.py), rồi chỉ định
**một** binary qua `IELTS_WEB_SPEAKING_VAD_MODEL_PATH`. Build kiểm pinned checksum
`597d30b3ec076608d059477bb14cfeffdf951bf5cae370d38f65d33bbfe82004`, copy file vào
`/opt/speaking/silero-v6.0.onnx` và backend startup đặt
`SPEAKING_VAD_MODEL_PATH`/`SPEAKING_VAD_MODEL_SHA256`. Không copy cả `storage/`,
không commit binary. Nếu không cung cấp asset thì VAD unavailable và FC có thể
không đủ điều kiện; không download khi có yêu cầu hoặc tự fallback timing proxy.

Ví dụ lựa chọn shell **chỉ cho staging đã cấu hình/được phép**, từ repository
root; đây là hướng dẫn, chưa chạy serve/deploy trong lần triển khai này:

```powershell
$env:IELTS_WEB_SPEAKING_ASR_PROVIDER = "azure"
$env:IELTS_WEB_SPEAKING_PROFILE = "speaking_hybrid_v1"
$env:IELTS_WEB_SPEAKING_VAD_MODEL_PATH = (Resolve-Path storage/models/silero-v6.0.onnx).Path
$env:IELTS_WEB_AI_PROVIDER = "openai"
$env:IELTS_WEB_SPEAKING_AI_PROVIDER = "openai"
$env:IELTS_WEB_CHART_SPECIALIST_ENABLED = "false"
$env:IELTS_WEB_SPEAKING_ASR_ENABLED = "true"
# Chọn đúng isolated config Secret/Volumes/mode theo hướng dẫn bên dưới trước:
modal serve deploy/modal/app.py
```

`IELTS_WEB_SPEAKING_ASR_ENABLED=false` vẫn tắt transcript jobs cả với hybrid.
Không dùng `--no-asr` nếu muốn Azure transcript. Windows launcher hỗ trợ profile,
kiểm credential presence và pinned VAD checksum trước khi gọi Modal.
OpenAI policy/token limits và single-owner embedded PostgreSQL không
đổi. CPU speech không làm topology Web có thể tăng replica an toàn.

Image build và container startup chạy native-load probe
`python -m deploy.modal.speaking_cpu`: import SDK/ONNX/NumPy, nạp ALSA/OpenSSL,
tạo audio format/options CPU; không tạo recognizer, không key, không model
download, không provider call. Probe này không chứng minh API access, VAD
weights/session hoặc whole Web readiness. Local verification đã thực hiện:

```powershell
docker build --file deploy/modal/Dockerfile.speaking-hybrid-probe --tag bandpilot-speaking-hybrid-probe:local .
docker run --rm --network none bandpilot-speaking-hybrid-probe:local
```

Probe riêng cho lifecycle FastAPI (không deploy): build cùng Dockerfile với
`--target backend-startup --tag bandpilot-speaking-hybrid-backend-probe:local`.
Chạy với `DATABASE_URL` trỏ **DB test trống đã migrate** có tên
`ielts_hybrid_cpu_test`; script từ chối tên khác. Không copy `.env`, private
recordings hoặc credential vào image. Đã chạy 2026-11-03: lifespan startup/shutdown,
`/api/v1/health` và `/api/v1/ready` đạt, output `CPU_BACKEND_STARTUP_OK`, zero
provider calls, không import torch/faster-whisper/ctranslate2. Speech thiếu key
được báo chưa configured. Đây là xác minh backend CPU local; topology Web đầy đủ
và Modal account/deployment thật vẫn **CONTAINER_UNVERIFIED**, Azure **LIVE_UNVERIFIED**.

Cả build và network-disabled run đạt `CPU_NATIVE_PROBE_OK`,
`provider_calls=0`, `gpu_required=false` trên Linux/amd64 Debian Bookworm,
Python 3.12, Docker Engine 29.4.3. Chỉ dependency/native compatibility probe
được xác minh; không build toàn Web image, không deploy Modal, không test Azure
live hoặc đo latency/cost/throughput. **LIVE_UNVERIFIED**; Modal runtime đầy đủ
vẫn **CONTAINER_UNVERIFIED**. Script/Dockerfile không chứa secrets.

Rollback: dừng staging session hiện tại theo quy trình single-owner, đổi
`SPEAKING_ASR_PROVIDER=modal` (hoặc launcher `--asr-provider modal`), profile legacy,
chọn lại ASR/provider config legacy đã kiểm
và rebuild/restart. Không xóa transcript/history hoặc sửa điểm human. Muốn tạm
tắt speech thay vì đổi profile, đặt speech enable flag false. Không dùng probe
hoặc offline metrics để tự động triển khai/cutover. Xem
[privacy/chi phí](ai-speaking.md) và [hợp đồng speech](speaking-transcription.md#speaking-hybrid-v1).

## One-command Windows staging with on-demand AI

### Azure configuration, secrets and canonical command

Canonical names remain `SPEAKING_AZURE_KEY`, `SPEAKING_AZURE_REGION`,
`SPEAKING_AZURE_LOCALE`; no duplicate `SPEAKING_AZURE_SPEECH_*` aliases.
On this developer machine missing fields were appended to ignored `backend/.env`,
without changing existing values. The operator fills only the empty Azure key;
region `japaneast` and locale `en-US` are prepared. Never paste keys in chat.

```dotenv
SPEAKING_ASR_ENABLED=true
SPEAKING_ASR_PROVIDER=azure
SPEAKING_AZURE_KEY=
SPEAKING_AZURE_REGION=japaneast
SPEAKING_AZURE_LOCALE=en-US
SPEAKING_AZURE_ALLOW_PAID=false
SPEAKING_AZURE_BILLING_MODE=free_only
SPEAKING_AI_ENABLED=true
SPEAKING_AI_PROVIDER=openai
SPEAKING_AI_MODEL=gpt-6-luna
```

`free_only` is an operator declaration for the selected non-billable resource AND
requested features, verified outside the worker. The user confirmed the current
resource is F0. It does not mean an arbitrary credential is free, or that Azure
has verified pricing through this application. Global default mode is `unknown`,
which blocks submissions. A paid resource requires BOTH `BILLING_MODE=paid` and
`ALLOW_PAID=true`. Do not label an S0 trial/credit resource as `free_only`.
Prosody may be unavailable on the chosen free resource; never automatically
upgrade, disable requested features or switch resources to make it succeed.

From repository root, after filling the key:

```powershell
.\start-modal.cmd --provider openai --check
.\start-modal.cmd --provider openai
```

This is the canonical Windows workflow (`uv run --locked --project backend python
scripts/modal_start.py --provider openai` is equivalent). It selects the profile,
environment and existing staging Secret/Volumes from `.env.modal`. No persistent
Secret update is needed just to forward the local key: the launcher supplies a
backend-only ephemeral Secret. The pinned VAD asset must have been prepared once
using the existing setup script below; no model download occurs per request.

To refresh the persistent backend Secret instead, reuse the existing setup script:

```powershell
uv run --locked --project backend python scripts/modal_web_setup.py --snapshot "<existing-snapshot>/database.dump" --force
```

It reads `.env.modal` for the selected CLI/profile/environment/Secret name, and
`backend/.env` for backend values. Keep the same verified snapshot reference and
JWT/settings used for that Secret. This explicitly replaces the config Secret;
it does not merge unknown remote fields. There is no snapshot-free refresh mode
that could silently discard the bootstrap reference. Optional `--secret-name`
overrides the target; use only an authorized dedicated Secret. Nothing in this
task runs this command against Modal. `--disable-ai` omits all Azure/AI keys and
writes `SPEAKING_ASR_ENABLED=false`; launch that topology with AI/ASR gates off.

Raw `modal serve deploy/modal/app.py` remains supported with the explicit frozen
provider flags shown above AND a prepared backend Secret. A named remote Secret
cannot select the local dependency graph retroactively; the canonical launcher
forwards its non-secret selectors before composition. Azure runs from Web CPU;
local ASR is rejected when enabled in this Modal image, and Modal ASR remains
an explicit rollback choice. Neither Azure errors nor other available credentials
can enable a T4/L4 or OpenAI transcription fallback.

Readiness only inspects configuration/dependency availability. It submits no
sample audio and does not prove authentication or free-tier feature availability.
429/SDK TooManyRequests yields `SPEAKING_AZURE_QUOTA_EXCEEDED`; it may be quota,
rate or concurrency throttling. Internal allowlisted reason codes preserve that
distinction when exposed, without storing/logging raw provider errors. No automatic
retry, resource rotation or ARM/pricing-tier permissions are introduced.


From the repository root, run:

```powershell
.\start-modal.cmd
```

Launcher lấy LLM/ASR provider từ `backend/.env`; CLI override tường minh được ưu tiên.
Giữ OpenAI reasoning/token settings hiện có. Với CPU speech/OpenAI, `.env.modal`
chỉ chứa các selector và staging resource names không bí mật:

```dotenv
IELTS_WEB_AI_PROVIDER=openai
IELTS_WEB_SPEAKING_VAD_MODEL_PATH=storage/models/silero-v6.0.onnx
```

Keep `SPEAKING_AZURE_KEY` and `SPEAKING_AZURE_REGION` in `backend/.env`, alongside
the existing OpenAI settings. Azure prosody defaults to true; its availability
and additional charge must be checked for the chosen resource/locale. Prepare
the pinned VAD file once, then use the usual launcher:

```powershell
python scripts/setup_speaking_vad.py storage/models/silero-v6.0.onnx
.\start-modal.cmd --check
.\start-modal.cmd
```

The launcher forwards the actual private Azure key via an ephemeral backend
Secret, not a masked SecretStr or an image variable. It forwards the complete
Speaking AI policy, checks the model checksum without loading native libraries
locally, and requires no Modal GPU proxy in this configuration. Missing Azure
settings or VAD assets stop startup with an actionable message; `--check` makes
zero API calls and does not claim live readiness. `--asr-provider modal`
selects the legacy profile for rollback; explicitly choose the intended grader
with `--provider vllm` or `--provider openai`.

For OpenAI Luna grading with speech disabled, use:

```powershell
.\start-modal.cmd --provider openai --no-asr --check
.\start-modal.cmd --provider openai --no-asr
```

The OpenAI mode reads the existing private `backend/.env`, validates the key's
presence, model and inference policy offline, and forwards Writing/Speaking AI
settings as backend-only ephemeral Secrets. It does not change the persistent
Modal Secret, JWT, database or Volumes. Structured stage overrides are serialized
as JSON. `--no-asr` disables all ASR. Azure needs its configured key/region and authorized
billing mode; only Modal ASR needs Modal proxy credentials. Keep the chart specialist disabled
in `.env.modal` for the CPU-only OpenAI topology. No API inference runs during
`--check`; a configured key is not proof of API access or successful grading.

The launcher reads the ignored root `.env.modal` configuration, explicitly selects
its Modal profile/environment and existing isolated staging Volumes/Secret, then
runs the existing `modal serve deploy/modal/app.py` entry point. Keep the terminal
open and press Ctrl+C to end the ephemeral session. The wrapper lets Modal finish
its own shutdown instead of killing it when the parent receives Ctrl+C. Windows
supports serving, but automatic source-code reload is skipped by the installed
SDK; restart the serve command after code changes.
This staging helper refuses production/shared resources. On another
machine, copy `.env.modal.example` to `.env.modal`, select pre-created staging
resources and optionally set `MODAL_CLI_PATH`. The `uv` backend environment and
Modal CLI must already be installed and authenticated.

AI proxy credentials are read from `AI_WRITING_MODAL_KEY` and
`AI_WRITING_MODAL_SECRET` in the existing backend Settings (`backend/.env`). They
are passed as backend-only ephemeral Modal Secrets through the existing entry
point; the launcher does not replace the staging JWT/Secret, copy a production
database or embed credentials in an image/Next.js. Inherited OpenAI/provider
overrides are excluded from the default vLLM command. The explicit OpenAI mode
uses backend Settings (shell overrides take precedence over `backend/.env`) and
selects OpenAI for both graders; it never silently falls back to vLLM.

Writing AI, Speaking AI and Speaking ASR are enabled by default. The shared L4
grader and T4 ASR retain zero minimum containers, at most one container per
service and a 60-second idle scaledown window. No warmup/model request is sent by
the launcher, Web health or database readiness checks. The first actual AI request
can incur model cold-start delay; idle shutdown timing is controlled by Modal.
Previously requested durable jobs recovered after a restart may also request AI;
their existing recovery behavior is preserved. The optional experimental chart
specialist remains disabled. Web/embedded PostgreSQL retain one Web container,
so this is AI scale-to-zero rather than whole-application scale-to-zero.

```powershell
.\start-modal.cmd --check  # Offline configuration check, no deployment/inference
.\start-modal.cmd --deploy # Persistent modal deploy instead of terminal-bound serve
.\start-modal.cmd --stop   # Stop the selected profile's deployed development app
```

Only `--deploy` persists after the terminal closes. End a serve session with
Ctrl+C; `--stop` addresses the named deployed app, not an arbitrary serve session.
Do not run serve and a deployed app against the same PostgreSQL Volume at once:
stop an existing deployed development app before switching to serve. `--stop`
needs no AI credentials and preserves all Volumes and Secrets. This launcher has offline regression
coverage; it does not establish that local proxy credentials are valid for a
particular live workspace or that AI inference was tested there.

P5 bổ sung [di chuyển portable](storage-migration.md) và [sao lưu cơ sở dữ liệu/đối tượng, khôi phục cô lập](storage-backup-restore.md). Backend đã cài hỗ trợ `python -m app.storage.recovery_cli backup|restore` với các đối số trong hướng dẫn. Chạy từ môi trường bảo trì do người vận hành kiểm soát, sau khi mọi tác vụ ghi Web/nền đã kết thúc, với đúng cơ sở dữ liệu và cấu hình SOURCE_/DESTINATION_ tường minh. Thao tác demo phải giữ cơ chế một chủ sở hữu cơ sở dữ liệu và đọc dữ liệu đã commit trên cùng Volume tài sản; không khởi động PostgreSQL nhúng thứ hai. Snapshot chỉ có cơ sở dữ liệu không phải sao lưu ứng dụng đầy đủ. Lưu gói đã xác minh độc lập và commit đầu ra Volume tường minh tại bước vận hành. Không thêm endpoint sao lưu tự động, triển khai, chuyển dữ liệu hoặc đổi số replica.

Sau bước thiết lập một lần bên dưới, chạy từ gốc repository:

```powershell
modal serve deploy/modal/app.py
```

Ở cấu hình vLLM mặc định, một lệnh cung cấp Web cùng dịch vụ LLM và Speaking ASR được bảo vệ. Frontend Next.js, backend FastAPI và tiến trình PostgreSQL 17 riêng tư hiện có dùng chung một container CPU; FFmpeg chuẩn hóa âm thanh Speaking riêng tư chia đoạn tại đó. Một hàm GPU L4 riêng phục vụ mô hình văn bản/hình ảnh thống nhất `mistralai/Ministral-3-8B-Instruct-2512` theo nhu cầu. Có thể chọn [Web CPU gọi OpenAI bên ngoài](#cpu-web-openai) để bỏ dịch vụ LLM GPU đi kèm. Modal in URL HTTPS công khai. Nginx chuyển `/api/` tới FastAPI, đường dẫn khác tới Next.js, kể cả SSE không đệm. Lời gọi API trình duyệt dùng `/api/v1`; yêu cầu server component/proxy dùng `API_INTERNAL_BASE_URL` qua loopback. Cookie dùng cùng origin HTTPS. Trình duyệt không kết nối PostgreSQL, LLM hoặc nhà cung cấp Speaking ASR.

`modal serve` giữ ứng dụng hoạt động trong thời gian lệnh chạy. Theo dõi mã nguồn/tải lại trực tiếp của Modal hiện chưa hỗ trợ Windows; trên Windows phải khởi động lại lệnh sau khi đổi mã. Frontend được build chế độ production trong image. Để triển khai ổn định, tiếp tục hoạt động sau khi đóng terminal:

```powershell
modal deploy deploy/modal/app.py
```

Trong chế độ vLLM mặc định, cả hai hàm GPU đi kèm có số container tối thiểu bằng không và thu hẹp sau 60 giây không hoạt động. Chúng không khởi động chỉ vì Web khởi động; Ministral bắt đầu ở yêu cầu readiness backend đầu tiên, ASR bắt đầu ở yêu cầu phiên âm đầu tiên. Web tự lấy URL đã được phân giải runtime, kể cả URL dev tạm thời. Không phải chép URL sau mỗi lần khởi động. Secret backend được chọn phải chứa `AI_WRITING_MODAL_KEY` và `AI_WRITING_MODAL_SECRET` khi dùng vLLM, ASR Modal hoặc DePlot được bảo vệ; backend dùng lại token proxy này cho endpoint ASR. Xem [ai-writing.md](ai-writing.md) về LLM. Container Web giữ một replica CPU. PostgreSQL demo nhúng vẫn chỉ có một bên ghi; chế độ external cũng giữ `max_containers=1`.

Khi `IELTS_WEB_AI_ENABLED=true`, Web bật chấm AI cho cả Writing và Speaking. Speaking kế thừa transport, mô hình và thông tin xác thực Writing; hai pipeline dùng chung OpenAI hoặc vLLM nếu không có ghi đè. Chọn `SPEAKING_AI_PROVIDER` tùy chọn trong shell **trước** lệnh Modal nếu cần hai provider khác nhau; `SPEAKING_AI_MODEL` chỉ ghi đè mô hình Speaking. App chỉ thêm vLLM khi ít nhất một grader đang bật chọn `vllm`, không thêm container LLM thứ hai cho Speaking. Log khởi động dùng danh sách trường cho phép gồm trạng thái bật/cấu hình, định danh nhà cung cấp/mô hình và cờ có transport; không in URL endpoint, thông tin xác thực hoặc nội dung thí sinh. Speaking ASR vẫn độc lập.

<a id="cpu-web-openai"></a>

## Web CPU gọi OpenAI bên ngoài

Trên Windows với bộ tài nguyên dev riêng đã ghi trong `.env.modal`, dùng
`.\start-modal.cmd --provider openai --no-asr` để nạp cả cấu hình dev và cấu hình
AI riêng tư trong `backend/.env`. Lệnh `modal serve deploy/modal/app.py` trực tiếp
**không tự đọc** hai file này: chỉ đặt provider/model trong shell không chuyển API
key local vào container. Nếu Secret đã chọn chưa có key, backend có thể báo
`writing_ai_enabled=true` nhưng `writing_ai_configured=false`. Launcher kiểm tra
thiếu key hoặc policy không tương thích trước khi khởi động và chuyển các biến
qua ephemeral Secret hiện có; không cần ghi đè Secret cấu hình đang dùng.

Profile chấm hiện hành là [`openai_task1_reasoned_v1`](ai-writing.md#openai-task1-reasoned-policy). Trước khi restart DEV, chuyển **có chủ đích** cap cũ `AI_WRITING_OPENAI_MAX_OUTPUT_TOKENS=4096` sang cấu hình tương thích; cap cũ không bị bỏ qua và sẽ báo lỗi cấu hình. Các biến `AI_WRITING_OPENAI_*` (profile, effort, detail, low/medium/repair budgets, safety cap, stage overrides, TA image flag, stage/run timeouts) đi qua Secret backend và shell overrides hiện có; không nằm trong frontend/image build. Ví dụ đầy đủ và precedence ở [AI Writing](ai-writing.md#openai-task1-reasoned-policy), áp dụng giống local. Cấu hình khởi đầu: low/8192, Task 1 grounding/verification/TA medium/16384, detail high, repair/safety 32768, stage 300s, assessment 1800s. `original` chưa được bật cho Luna + Chat.

Đổi policy làm đổi cache OpenAI, vẫn đọc kết quả cũ và không làm mất cache vLLM. Rollback nhánh ảnh bằng `AI_WRITING_OPENAI_TASK1_IMAGE_ASSESSMENT=false` rồi restart DEV; giữ reasoning/budget policy mới. Tests môi trường/CPU composition là ngoại tuyến; không xác nhận deployment, latency hay chi phí cloud. Không cần bật GPU LLM/DePlot để dùng profile này; ASR vẫn là lựa chọn riêng. Phần hướng dẫn/tài nguyên dev bên dưới được giữ nguyên.

Chế độ này dùng `AI_WRITING_PROVIDER=openai` với `AI_WRITING_OPENAI_MODEL=gpt-6-luna`; xem [cấu hình Writing](ai-writing.md) và [pipeline Speaking](ai-speaking.md). Khi cả hai grader chọn OpenAI, ASR và DePlot đều tắt, điểm vào không import/include app vLLM, không phân giải URL vLLM, không tạo dependency GPU hay bộ nhớ đệm trọng số LLM đi kèm. Web vẫn build Next.js và chạy FastAPI/PostgreSQL theo topology đã chọn. OpenAI API và tài nguyên Web/lưu trữ Modal có chi phí riêng.

Ví dụ dưới đây dành cho **dev cô lập với PostgreSQL nhúng**. Trước khi chạy, người vận hành phải chọn tên Secret dev riêng và chuẩn bị Volume PostgreSQL **v2** riêng, Volume snapshot riêng có dump/manifest đã xác minh cùng Volume tài sản riêng khớp các khóa trong dump; xem [thiết lập và cô lập Volume](#cô-lập-và-độ-bền-volume-tài-sản). Tên Volume tùy chỉnh phải tồn tại trước; app không âm thầm tạo thay thế. Dùng snapshot dev/tổng hợp đã được người vận hành xác minh và cung cấp. Không tạo bản sao database production chỉ để thử API key; các lệnh này không tự tạo, upload hoặc sao chép snapshot/tài sản. Nếu chưa có bộ tài nguyên dev phù hợp, hoàn thành quy trình vận hành cô lập trước.

1. Mở `backend/.env` riêng tư và đặt cấu hình dev; không commit file hoặc đưa key vào dòng lệnh. Các giá trị trong dấu `<...>` là chỗ thay bằng thông tin của bạn:

   ```dotenv
   JWT_SECRET=<JWT_RIENG_CHO_DEV_TOI_THIEU_32_KY_TU>
   AI_WRITING_PROVIDER=openai
   AI_WRITING_OPENAI_API_KEY=<OPENAI_API_KEY_CUA_BAN>
   AI_WRITING_OPENAI_MODEL=gpt-6-luna
   AI_WRITING_OPENAI_BASE_URL=https://api.openai.com/v1
   SPEAKING_AI_PROVIDER=
   SPEAKING_AI_MODEL=
   ```

   Key/model/base URL được đưa vào Secret backend và giữ nguyên khi Web khởi động. Speaking mặc định dùng chính cấu hình OpenAI này, không cần key Speaking thứ hai. Các biến môi trường shell có ưu tiên cao hơn `.env`; dùng phiên PowerShell sạch cho ví dụ này để không mang theo ghi đè `AI_WRITING_*` hoặc `SPEAKING_AI_*` cũ. Script không chép `DATABASE_URL` hay cấu hình storage từ `.env`; Secret dev đã chọn cũng phải không chứa kết nối database production.

2. Từ **gốc repository**, thay các tên `YOUR-...` bằng tài nguyên dev đã chuẩn bị. Giữ shell này cho cả bước tạo Secret và chạy Web:

   ```powershell
   $env:IELTS_MODAL_MODE='dev'
   $env:IELTS_MODAL_CONFIG_SECRET='YOUR-DEDICATED-DEV-CONFIG'
   $env:IELTS_MODAL_STORAGE_BACKEND='local'
   $env:IELTS_MODAL_DATABASE_MODE='embedded'
   $env:IELTS_MODAL_DATABASE_VOLUME='YOUR-PRECREATED-DEV-POSTGRES-V2'
   $env:IELTS_MODAL_SNAPSHOTS_VOLUME='YOUR-PRECREATED-DEV-SNAPSHOTS'
   $env:IELTS_MODAL_ASSETS_VOLUME='YOUR-PRECREATED-DEV-ASSETS'
   $env:IELTS_MODAL_REQUIRE_ASSET_ISOLATION='true'
   $env:IELTS_WEB_AI_ENABLED='true'
   $env:AI_WRITING_PROVIDER='openai'
   $env:IELTS_WEB_SPEAKING_ASR_ENABLED='false'
   $env:IELTS_WEB_CHART_SPECIALIST_ENABLED='false'
   ```

3. Tạo Secret chuyên biệt bằng script hiện có, rồi chạy Web. Thay `<VERIFIED_SNAPSHOT_PATH>` bằng **đúng đường dẫn snapshot đã xác minh do bạn cung cấp**, tương đối trong Volume snapshot đã chọn:

   ```powershell
   Push-Location backend
   uv run python ../scripts/modal_web_setup.py --secret-name $env:IELTS_MODAL_CONFIG_SECRET --snapshot '<VERIFIED_SNAPSHOT_PATH>/database.dump'
   Pop-Location
   modal serve deploy/modal/app.py
   ```

   Tên Secret tùy chỉnh không bị ghi đè mặc định. Khi cần cập nhật key/model/base URL hoặc cấu hình Speaking sau khi sửa `backend/.env`, dừng phiên dev hiện tại rồi chạy lại cùng script với `--force` tường minh:

   ```powershell
   Push-Location backend
   uv run python ../scripts/modal_web_setup.py --secret-name $env:IELTS_MODAL_CONFIG_SECRET --snapshot '<VERIFIED_SNAPSHOT_PATH>/database.dump' --force
   Pop-Location
   modal serve deploy/modal/app.py
   ```

   Script cũng chuyển các trường `SPEAKING_AI_*` đã cấu hình, gồm giới hạn token, timeout và phiên bản prompt/rubric. `IELTS_WEB_AI_ENABLED` vẫn quyết định bật cả hai grader tại runtime. Nếu cần app dev tiếp tục chạy sau khi đóng terminal, sau khi dừng phiên `serve` hiện tại dùng `modal deploy deploy/modal/app.py` trong cùng shell/cấu hình cô lập; một database chỉ được có một chủ sở hữu Web đang chạy.

App cố định lựa chọn provider vào các dấu không chứa secrets `IELTS_WEB_AI_PROVIDER` và `IELTS_WEB_SPEAKING_AI_PROVIDER` (rỗng nghĩa là Speaking kế thừa), đồng thời cố định cờ ASR/chart trong image. Không tự đặt các dấu provider này trong Secret; provider cũ trong Secret không được đổi dependency graph Local/từ xa. Khi đổi provider, đặt lựa chọn trong shell và chạy lại lệnh Modal. Với cấu hình hỗn hợp, ví dụ Writing OpenAI nhưng `SPEAKING_AI_PROVIDER=vllm`, app vẫn thêm dịch vụ LLM GPU cần cho Speaking và hydrate URL/mô hình vLLM đi kèm. Model/base URL/key OpenAI vẫn được giữ.

`IELTS_WEB_SPEAKING_ASR_ENABLED=false` là lựa chọn tối thiểu để thử Writing mà không tạo GPU phiên âm; Speaking AI vẫn có thể dùng transcript phù hợp đã có. Muốn tạo transcript Speaking mới qua Modal, thêm `AI_WRITING_MODAL_KEY`/`AI_WRITING_MODAL_SECRET` hợp lệ vào `backend/.env`, cập nhật Secret dev bằng bước `--force` trên, rồi đặt `$env:IELTS_WEB_SPEAKING_ASR_ENABLED='true'` trước khi chạy lại Web. Đây là [dịch vụ faster-whisper GPU riêng](#triển-khai-speaking-asr), có chi phí Modal riêng; OpenAI API key không xác thực endpoint ASR. Nếu không đặt cờ, ASR theo gate AI chung, nên ví dụ OpenAI tối thiểu luôn đặt `false` tường minh.

DePlot cũng chỉ tham gia khi chủ ý đặt `$env:IELTS_WEB_CHART_SPECIALIST_ENABLED='true'` trước lệnh Modal và có thông tin proxy phù hợp; đó là [dịch vụ biểu đồ GPU tùy chọn riêng](#optional-t1-b-chart-service), có chi phí riêng. Để OpenAI chỉ gọi API ngoài, giữ cả hai cờ ASR/chart là `false`.

Thay provider không đổi PostgreSQL, schema hay kho assets: PostgreSQL vẫn là nguồn dữ liệu chính, Volume và khóa một chủ sở hữu giữ nguyên, external database vẫn migration do người vận hành kiểm soát. Đường chạy managed PostgreSQL/S3/R2 phải dùng [topology external hiện có](#chế-độ-postgresql-managed-và-s3r2) với database/bucket dev riêng; không áp dụng lệnh embedded ở trên cho production. Các lệnh ở phần này là hướng dẫn chạy thủ công, chưa được thực thi trong lần thay đổi này. Kiểm thử ngoại tuyến đã xác minh lựa chọn dependency, bảo toàn cấu hình OpenAI và lọc log; chưa xác minh key/quyền model, kết nối OpenAI thật, tài nguyên Modal, độ bền Volume hoặc triển khai đang chạy.

## Triển khai Speaking ASR

Hàm `ielts-speaking-asr` đi kèm chạy faster-whisper 1.2.1 với `Systran/faster-whisper-large-v3` cố định revision `edaa852ec7e145841d8ffdb056a99866b5f0a478`. Nó dùng CTranslate2 4.8.2, PyAV 18.1.0 (bộ giải mã faster-whisper 1.2.1 không tương thích PyAV 19), tính toán `int8_float16`, giải mã tiếng Anh, mốc thời gian từng từ, T4, 4 CPU, RAM host 16 GiB, tối đa một container và Volume riêng `ielts-speaking-asr-model-cache`. Dịch vụ không có đường suy luận công khai không xác thực: Modal yêu cầu xác thực proxy với `/health` và `/transcribe`. Chỉ chấp nhận WAV đã chuẩn hóa mono 16 kHz signed-16-bit có giới hạn. WebM gốc vẫn trong kho Web riêng tư; WAV yêu cầu nằm trong thư mục ASR tạm có thể xóa; mã ứng dụng không ghi body âm thanh hoặc bản phiên âm vào log. Bộ nhớ đệm mô hình chỉ chứa tệp mô hình. Image Web cài FFmpeg nhưng không cài faster-whisper.

Trước khi FastAPI khởi động, Web production đặt `SPEAKING_ASR_ENABLED`, `SPEAKING_ASR_PROVIDER=modal`, URL gốc đã phân giải chỉ cho backend, mô hình, revision, phiên bản dịch vụ và giới hạn xử lý 600 giây. `IELTS_WEB_SPEAKING_ASR_ENABLED=false` tắt hàm tường minh; nếu không đặt, nó theo `IELTS_WEB_AI_ENABLED`. Development Local có thể giữ `SPEAKING_ASR_PROVIDER=local` với `backend[speech]` và thư mục mô hình Local đầy đủ. Đổi mô hình, revision hoặc phiên bản giải mã làm mất hiệu lực bộ nhớ đệm phiên âm; chỉ xoay URL endpoint thì không. Cấu hình triển khai này không cần migration cơ sở dữ liệu.

Để kiểm tra nhanh thủ công một lần, chuẩn bị WAV tiếng Anh tổng hợp ngắn mono 16 kHz ngoài Git, dùng thông tin proxy backend hiện có từ dotenv riêng tư và gọi `ModalASRProvider.transcribe` đã cấu hình một lần. Kiểm tra kết quả có văn bản không rỗng, thời gian từ hợp lệ và mô hình/phiên bản đã cố định. Endpoint được bảo vệ còn nhận trực tiếp `POST /transcribe` với `audio/wav` và header `Modal-Key`/`Modal-Secret`; không đưa giá trị vào lệnh, log hoặc báo cáo. Xem `modal app logs ielts-practice-web` khi khởi động lỗi và `modal container list` để kiểm tra GPU thu hẹp mà không in body yêu cầu. Xóa WAV tổng hợp sau kiểm tra. Một câu không đủ xác lập độ chính xác IELTS.

Để chỉ chạy Web, tắt AI tường minh trước cùng lệnh:

```powershell
$env:IELTS_WEB_AI_ENABLED='false'
modal serve deploy/modal/app.py
```

Để chọn lại dịch vụ vLLM đi kèm tường minh, dùng shell không giữ các dấu provider cố định từ phiên khác và đặt:

```powershell
$env:IELTS_WEB_AI_ENABLED='true'
$env:AI_WRITING_PROVIDER='vllm'
modal serve deploy/modal/app.py
```

`AI_WRITING_ENABLED=false` trong shell gọi lệnh cũng tắt AI nếu chưa đặt `IELTS_WEB_AI_ENABLED`. Ghi đè `AI_WRITING_*` của shell được chuyển thành Secret tạm, không thành lớp môi trường image. Với nhà cung cấp vLLM đi kèm, URL/mô hình của hàm đi kèm ghi đè giá trị Secret cũ. Nhà cung cấp OpenAI được chọn tường minh giữ cấu hình riêng. Thiếu thông tin xác thực được báo là "AI grading is not configured" trước khi tạo lượt chấm.

## Chế độ PostgreSQL managed và S3/R2

Mặc định vẫn là demo cơ sở dữ liệu nhúng/Volume Local hiện có. Với cloud, chọn topology **trước** khi gọi điểm vào hiện có:

```powershell
$env:IELTS_MODAL_STORAGE_BACKEND='r2' # or s3
$env:IELTS_MODAL_DATABASE_MODE='external'
$env:IELTS_MODAL_CONFIG_SECRET='ielts-web-production-config'
$env:IELTS_MODAL_MODE='production'
```

Tạo/cập nhật Secret theo tên đó qua dashboard Modal/công cụ vận hành. Secret phải có cấu hình backend P3, gồm `STORAGE_BACKEND` khớp topology, `DATABASE_URL` bên ngoài dùng `postgresql+asyncpg` và TLS (`?ssl=require` hoặc ưu tiên `?ssl=verify-full` với bộ CA công khai của nhà cung cấp), `IELTS_AUTO_MIGRATE=false`, `IELTS_DEPLOYMENT_ENV=production`, HTTPS `FRONTEND_ORIGIN`, `JWT_SECRET` mạnh và `AUTH_COOKIE_SECURE=true`. Với R2, thêm `S3_BUCKET`, `S3_REGION=auto`, `S3_ENDPOINT_URL` tài khoản và `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` giới hạn phạm vi. S3 dùng region thật và thông tin runtime an toàn hoặc chuỗi xác thực SDK. Modal không kế thừa role instance EC2: cấp thông tin qua Secret hoặc quy trình thông tin xác thực ngắn hạn do người vận hành quản lý. Đặt thông tin AI được bảo vệ hiện có trong cùng Secret backend. Không đưa dữ liệu nhạy cảm vào `.Image.env` hoặc Next.js. Tiến trình con Next.js/Nginx nhận môi trường giới hạn; thông tin DB, JWT, lưu trữ và AI chỉ ở FastAPI, không được các tiến trình đó kế thừa.

Để TLS cơ sở dữ liệu xác minh hostname, đặt **chứng chỉ CA công khai hoặc bộ CA khu vực nhỏ** phù hợp (trong giới hạn giá trị Secret 32 KiB) vào `IELTS_DATABASE_CA_PEM` trong Secret. Runtime ghi thành PEM tạm, đặt `PGSSLROOTCERT` cho tiến trình con và xóa sau khi chúng dừng; hàm migration tường minh dùng cùng bước này. Khóa riêng bị từ chối. Có thể thay bằng tệp `PGSSLROOTCERT` đọc được qua cấu hình runtime do người vận hành chuẩn bị; không cung cấp đồng thời hai nguồn. Chứng chỉ tạm không cần Volume tài sản, mật khẩu cơ sở dữ liệu không được nhúng trong image.

Dấu `IELTS_MODAL_STORAGE_BACKEND` cố định điều khiển mount Volume, còn `STORAGE_BACKEND` trong Secret chọn adapter P3. Không khớp sẽ thất bại trước khi khởi động dịch vụ. Cloud không mount Volume tài sản, cơ sở dữ liệu hoặc snapshot và không chạy PostgreSQL nhúng; tệp FFmpeg/ZIP tạm vẫn không bền vững. Local giữ `STORAGE_ROOT` đã cấu hình, mặc định `/storage`; dùng mount đó hoặc thư mục con để giữ tệp demo bền vững.

Tên ứng dụng công khai, tuyến HTTPS và hợp đồng `/api/v1` không đổi. Dùng Secret dev riêng có `IELTS_DEPLOYMENT_ENV=dev`, cơ sở dữ liệu riêng và bucket/tiền tố riêng đã xác minh cho dev. Nhãn môi trường không khớp bị từ chối. Nhãn không kiểm tra nội dung bucket: người vận hành phải xác minh sự tách biệt cơ sở dữ liệu/bucket/tiền tố thật. Chọn namespace khác không bao giờ sao chép đối tượng hiện có.

Khởi động Web external không chạy Alembic, khởi tạo cơ sở dữ liệu hoặc khôi phục snapshot. Sau khi mọi tác vụ ghi Web dừng, người vận hành được phép chạy đúng một lệnh:

```powershell
modal run deploy/modal/app.py::migrate_database
```

Hàm tường minh này dùng Secret backend đã chọn, bắt buộc URL bên ngoài và tối đa một container. Dùng thông tin chủ sở hữu schema cho migration, với Secret thay thế nếu cần. Phối hợp một người vận hành và một migration giữa các phiên bản ứng dụng; không chạy migration song song. Chỉ khởi động/triển khai Web sau khi thành công. Không lệnh nào trong phần này được chạy trong xác minh P4 ngoại tuyến.

## Thiết lập một lần

Xác thực Modal CLI (`modal setup`) và cấu hình `backend/.env` với JWT hiện có và thông tin AI chỉ backend. Sau đó:

```powershell
cd backend
# Creates a consistent local PostgreSQL dump, uploads and verifies its checksum:
uv run python ../scripts/modal_database_snapshot.py
# Use the exact snapshot path printed by the command above:
uv run python ../scripts/modal_web_setup.py --snapshot <snapshot>/database.dump
cd ..
# Create only if it does not already exist:
modal volume create ielts-web-assets
modal volume put ielts-web-assets storage/audio /
modal volume put ielts-web-assets storage/images /
modal serve deploy/modal/app.py
```

Script thiết lập đọc `backend/.env`, chép danh sách cho phép các cấu hình JWT/AI vào Secret Modal riêng tư `ielts-web-config`, gồm các điều chỉnh Speaking AI và ghi đè provider/model tùy chọn. Nó không in giá trị hoặc upload nguyên file `.env`. Tên mặc định giữ hành vi ghi đè tương thích; tên chuyên biệt chỉ ghi đè khi truyền `--force`. Script chủ ý không chép URL DB Local hoặc cấu hình OAuth redirect; cấu hình OAuth cloud riêng nếu cần. Tài khoản/password hash hiện có được khôi phục từ snapshot, nên quy trình đăng nhập thường được giữ.

Lần khởi động đầu khởi tạo `/database/pgdata` trên `ielts-web-postgres`, xác minh SHA-256 snapshot, khôi phục bằng `pg_restore` và áp dụng migration Alembic. Lần sau dùng lại cơ sở dữ liệu PostgreSQL, không nhập snapshot đè dữ liệu mới. Chỉ seed snapshot cho thư mục PostgreSQL mới khởi tạo; không ghi đè thư mục đã tồn tại nhưng thiếu dấu khôi phục. Tài sản nhị phân Local ở `ielts-web-assets`; tài sản tạo trên cloud cũng ở đó. Snapshot nhập gốc ở `ielts-postgres-backups`. Cơ sở dữ liệu cloud là bản sao riêng; thay đổi Local/cloud không được đồng bộ. `modal serve` dùng cơ sở dữ liệu `ielts-web-postgres-dev` riêng, seed từ cùng snapshot, nên có thể chạy cùng triển khai bền vững bằng một lệnh. Dev/production dùng chung Volume tài sản; tránh sửa tài sản chung ở dev.

Chỉ PostgreSQL loopback được tin cậy bên trong container duy nhất; cổng không công khai. Backend/Next.js cũng nghe loopback. Modal chỉ chuyển tiếp Nginx. Ứng dụng dùng xác thực và kiểm tra role hiện có, endpoint mô hình còn yêu cầu thông tin proxy Modal.

## Vòng đời cơ sở dữ liệu

### Chuyển sang workspace Modal khác

Profile chọn tài khoản/workspace; triển khai dùng cùng tên tài nguyên trong workspace được chọn. Xác thực đích mà không thay thông tin nguồn, rồi chọn đích sau khi sao chép:

```powershell
modal token new --profile <destination-profile> --no-activate
# After verified resource migration:
modal profile activate <destination-profile>
modal serve deploy/modal/app.py
```

Dừng mọi tác vụ ghi Web nguồn trước khi sao chép filesystem. Di chuyển cả `ielts-web-postgres` và `ielts-web-postgres-dev` (Volumes v2), `ielts-web-assets`, `ielts-postgres-backups` và `ielts-writing-model-cache`. Giữ quyền tệp/thư mục rỗng PostgreSQL và symlink bộ nhớ đệm Hugging Face; xác minh SHA-256 tệp cùng danh mục đầy đủ trước khi chạy Web đích. Giữ Volume nguồn và sao lưu đã xác minh tới khi xác nhận đích dùng được.

Tạo thông tin proxy mới ở đích và tạo lại Secret riêng `ielts-web-config` từ cấu hình backend hiện có. Thông tin proxy nguồn không cấp quyền yêu cầu tới workspace mới. Giữ cấu hình JWT và bản ghi DB; không chép lease đang hoạt động của Dict `ielts-web-database-owner`. Đích tạo cơ chế bảo vệ rỗng riêng. Ứng dụng đầy đủ tự phân giải URL nhà cung cấp mới. FastAPI Local chạy riêng cần URL mới và cặp proxy đích trong `.env` bị Git bỏ qua.

Lần di chuyển workspace 2026-10-08 đã xác minh SHA-256/danh mục cả năm Volume, gồm 26,493,350,173 byte bộ nhớ đệm mô hình và 11 symlink. Giữ cả hai bản DB, thư mục rỗng và quyền. Đã cấp proxy mới/Secret Web; dữ liệu nguồn được giữ. Lệnh `modal serve deploy/modal/app.py` ở đích sau đó khởi động Next.js/FastAPI và đọc DB đã chuyển thành công. Build image vLLM đầu mất khoảng 194 giây; build đó không khởi động GPU hoặc suy luận.

Volume PostgreSQL demo dùng Modal Volumes v2. Giữ sao lưu logic đã xác minh và dùng PostgreSQL managed cho dữ liệu production quan trọng. `DATABASE_URL` bên ngoài bỏ qua PostgreSQL nhúng; mặc định migration do người vận hành kiểm soát ngay cả khi giữ tài sản Local. Xem thiết lập managed bên trên và [tài liệu Volume Modal](https://modal.com/docs/guide/volumes).

Triển khai có tối đa một container. Modal Dict chỉ bảo vệ một bên ghi cho mỗi cơ sở dữ liệu, không chứa bản ghi nghiệp vụ. Mỗi DB chỉ có một bên ghi đang chạy. Dừng production trước khi triển khai lại; dừng session dev hiện có trước khi mở session dev khác. Khởi động dev thông thường không cần dừng production:

```powershell
modal app stop ielts-practice-web --yes
modal deploy deploy/modal/app.py
```

### Cô lập và độ bền Volume tài sản

Với DB staging mới, tạo Volume PostgreSQL v2 mới tường minh và chọn bằng `IELTS_MODAL_DATABASE_VOLUME` (hoặc `IELTS_MODAL_DEV_DATABASE_VOLUME` / `IELTS_MODAL_PRODUCTION_DATABASE_VOLUME` theo chế độ). Mặc định vẫn là `ielts-web-postgres[-dev]`. Volume không mặc định phải có sẵn; không âm thầm tạo khi khởi động. Khóa bảo vệ là tên Volume tường minh. Volume cũ `ielts-web-postgres-dev` / `ielts-web-postgres` luôn dùng khóa `dev` / `production` tương ứng, kể cả chọn tường minh từ chế độ khác, để cùng DB không lấy hai khóa khác nhau. Không xóa khóa của chủ sở hữu DB khác. `IELTS_MODAL_SNAPSHOTS_VOLUME` cũng chọn được Volume snapshot riêng tư có sẵn; mặc định không đổi. Dùng `modal deploy ... --strategy recreate` cho demo một chủ sở hữu và xác minh tiến trình PostgreSQL cũ đã dừng trước khi thay triển khai đang chạy.

`scripts/modal_web_setup.py --secret-name STAGING_NAME --disable-ai --snapshot PATH` tạo Secret dev riêng có JWT mới, không kế thừa thông tin AI. Chế độ này từ chối tên Secret production, không tự ghi đè Secret tùy chỉnh. Thiết lập mặc định hiện có vẫn tương thích ngược. Với dump tổng hợp do người vận hành tạo, `modal_database_snapshot.py --dump-file PATH --expected-sha256 DIGEST --volume STAGING_SNAPSHOTS` tái sử dụng xác minh tải lên/đọc lại mà không dump DB development thường. Người vận hành phải bảo đảm DATABASE_URL nguồn tường minh khớp dump. Giữ dump riêng, thông tin xác thực và log runtime ngoài Git. Chỉ đặt các biến này không làm thay đổi tài nguyên đang chạy.

Mặc định dev/production đều dùng Volume `ielts-web-assets` hiện có. Khóa DB riêng không ngăn truy cập đồng thời Volume tài sản chung; không coi hai môi trường là cô lập. `IELTS_MODAL_ASSETS_VOLUME` ghi đè tùy chọn khi triển khai. Có thể dùng `IELTS_MODAL_DEV_ASSETS_VOLUME` và `IELTS_MODAL_PRODUCTION_ASSETS_VOLUME`; ghi đè tổng quát ưu tiên hơn. `IELTS_MODAL_REQUIRE_ASSET_ISOLATION=true` từ chối Volume chung cũ ở dev. Chỉ giữ false khi chủ ý giữ hành vi demo cũ. Đặt tên đã chọn trong shell trước điểm vào Modal hiện có; không đặt để giữ Volume hiện có. Tên không mặc định phải tồn tại: triển khai không ngầm tạo kho rỗng thay thế. Tên được cố định trong image để import Local/từ xa thống nhất. Tên mới chọn Volume khác, **không** sao chép tệp DB đang tham chiếu. Trước khi đổi, dừng ghi, sao chép/xác minh mọi tệp tham chiếu bằng quy trình rà soát riêng, giữ sao lưu Volume gốc và DB, xác minh đường hoàn tác.

Runtime Web chỉ gọi `assets.commit()` tường minh khi dừng có kiểm soát. Modal còn commit nền khi container chạy. Lịch nền hay commit PostgreSQL đều không xác nhận một tệp tải lên đã được commit bền vững trước phản hồi HTTP. Container khác đang chạy cần reload để thấy commit mới; không thể reload khi có tệp Volume đang mở. Ghi đồng thời cùng tệp không được điều phối. Vì vậy dừng cưỡng bức/container đồng thời có nguy cơ mất dữ liệu hoặc thấy dữ liệu cũ. Chỉ commit định kỳ không bảo đảm nhất quán với ghi đồng thời/PostgreSQL; không coi là sao lưu giao dịch. Giữ sao lưu độc lập đã xác minh và ngừng ghi/cửa sổ bảo trì để tạo snapshot nhất quán. Xem [ngữ nghĩa Modal Volume](https://modal.com/docs/guide/volumes). Log khởi động nêu giới hạn độ bền demo và cảnh báo khi dev dùng Volume chung cũ. Runtime reload tài sản Local một lần trước khi mở tệp ứng dụng, không reload trong phục vụ. Khi dừng, mọi tiến trình ứng dụng dừng trước commit tường minh; lỗi commit được ném ra mà không lộ chẩn đoán riêng của nhà cung cấp. Không hứa độ bền từng upload/chunk, không thêm dịch vụ commit định kỳ riêng. Dùng S3/R2 cho nội dung production bền vững.

Với `DATABASE_URL` bên ngoài, `IELTS_AUTO_MIGRATE` mặc định `false`; `true` tường minh bị từ chối. Demo nhúng mặc định `true`, vẫn cho người vận hành đặt `false`. Giá trị khác `true`/`false` thất bại trước khởi động tiến trình. Hàm migration external bên trên là bước vận hành riêng, không phải khởi động. External không lấy khóa DB demo hoặc commit Volume PostgreSQL của demo.

Dừng hệ thống sẽ dừng tiến trình HTTP/PostgreSQL, commit Volume rồi giải phóng khóa. Nếu container bị kill/crash để lại khóa cũ, **trước hết xác nhận mọi container `ielts-practice-web` và `ielts-practice-web-dev` cũ đã dừng**, sau đó:

```powershell
modal dict clear ielts-web-database-owner --yes
modal serve deploy/modal/app.py
```

Không xóa khóa khi tiến trình DB vẫn chạy. Khởi động chỉ xóa PID file container cũ sau khi lấy khóa độc quyền. WAL PostgreSQL hiện có xử lý ghi Local gián đoạn; snapshot logic là bản khôi phục độc lập.

## Xác minh và dọn tài nguyên

Không mở trình duyệt, kiểm tra URL Modal đã in:

```powershell
curl.exe --fail https://YOUR-WEB-URL.modal.run/api/v1/health
curl.exe --fail https://YOUR-WEB-URL.modal.run/api/v1/ready
curl.exe --fail https://YOUR-WEB-URL.modal.run/
```

`/api/v1/auth/me` phải trả 401 khi không có session. Đăng nhập bằng tài khoản đã khôi phục để xem lại; không thêm cách bỏ qua auth. Khi khởi động lỗi, dùng `modal app logs ielts-practice-web`. Secret và prompt suy luận thô không nằm trong đầu vào build image/log yêu cầu ứng dụng.

Dừng triển khai Web bằng `modal app stop ielts-practice-web --yes`; dừng `modal serve` cũng dừng Web/hàm GPU tạm. Volume/sao lưu vẫn được giữ. Điểm vào này không cần triển khai `ielts-writing-llm` độc lập cũ; dừng riêng sau khi chuyển các client.

<a id="optional-t1-b-chart-service"></a>

## Dịch vụ biểu đồ T1-B tùy chọn

Dịch vụ vLLM Ministral thống nhất không đổi. DePlot chạy trong app/hàm Modal riêng `deploy/modal/chart_derenderer.py`, không thêm bộ Web/PostgreSQL thứ hai. Endpoint ASGI `/extract` được bảo vệ chỉ nhận dữ liệu PNG, JPEG hoặc WebP có giới hạn, tiền xử lý PIL RGB và lệnh trích xuất cố định. Backend không lộ URL hoặc thông tin proxy cho frontend.

Đặt `AI_WRITING_CHART_SPECIALIST_ENABLED=true` trong shell **trước** lệnh hiện có `modal serve deploy/modal/app.py` hoặc `modal deploy deploy/modal/app.py`. Điểm vào sẽ thêm hàm biểu đồ riêng và phân giải URL backend, checkpoint, revision. Mặc định bị tắt; chỉ chạy Web cũng tắt nó. `AI_WRITING_MODAL_KEY`/`AI_WRITING_MODAL_SECRET` hiện có phải hợp lệ cho endpoint biểu đồ. Với bộ chuyên biệt host riêng, dùng cấu hình backend trong `.env.example`. Nhiệm vụ này không triển khai production.

Phiên bản runtime cố định: Python 3.12, Transformers 5.13.0, PyTorch 2.10.0, Pillow 12.1.1, SentencePiece 0.2.1 và FastAPI 0.135.1. Checkpoint `google/deplot` có giấy phép Apache-2.0, cố định tại `6e76d62430da16986be3426bae32301fb9115397`. Tải mô hình dùng Volume `ielts-deplot-model-cache`. Hàm yêu cầu T4, 2 lõi CPU, RAM host 8 GiB, container tối thiểu bằng không, tối đa một và thu hẹp sau 60 giây. Không dùng chung tiến trình Ministral L4 hoặc bộ nhớ GPU.

Ngày 2026-10-08, [giá Modal](https://modal.com/pricing) niêm yết T4 là GPU rẻ nhất ở $0.000164/giây, so với L4 $0.000222/giây. CPU/RAM host và chi phí Volume/lưu trữ áp dụng được tính riêng; khởi động/thời gian chờ thu hẹp cũng tính phí. Chưa benchmark suy luận chỉ CPU nên không khẳng định ưu thế độ trễ hoặc chi phí CPU.

Đã chạy một kiểm tra nhanh tổng hợp nhiều biểu đồ tròn tùy chọn bằng client Modal 1.5.3 và runtime cố định trên T4. Đo tải/nạp mô hình **30.247 s**, suy luận **3.364 s**; cấp phát GPU PyTorch cao nhất **2,204,196,864 bytes** (khoảng 2.05 GiB). Tổng thời gian thực phía Local **145.25 s**, gồm build/cấp phát image lần đầu và dọn app; đây không phải độ trễ phục vụ HTTP hoặc phân bố độ trễ khi nóng. Số liệu xác minh mô hình vừa bộ nhớ và thời gian tính toán thực tế một lần trích xuất trên GPU rẻ nhất được niêm yết, không xác minh độ chính xác biểu đồ.

Mô hình trả dữ liệu bảng nhiều biểu đồ tròn sai định dạng. Một lần đối chiếu Local dùng chính đầu ra đó cho **PARSE_FAILED**, giữ T1-A đúng thay vì xác nhận dữ liệu biểu đồ. Không chạy trích xuất thứ hai hoặc lặp benchmark GPU. Kiểm thử thường xác minh độc lập sáu giá trị khớp từ fixture Region A/B tổng hợp gốc. Trích xuất nhiều biểu đồ tròn thật vẫn là giới hạn mô hình nên bộ chuyên biệt tùy chọn mặc định vẫn tắt. App kiểm tra tạm đã hoàn tất; triển khai Web/Ministral production không đổi.

Timeout bộ chuyên biệt backend mặc định 90 giây, không vượt 120. Bộ nhớ đệm lạnh/tải mô hình hoặc xếp hàng có thể vượt giới hạn; cơ chế dự phòng vẫn giữ bằng chứng sơ cấp dùng được. Chỉ yêu cầu một lượt chuyên biệt bổ sung cho nhóm biểu đồ/bảng. Không chạy ảnh IELTS thật, chấm bài thật, TinyChart hoặc đánh giá T1-C. `synthetic_smoke` là hàm chẩn đoán thủ công tường minh, không thuộc chấm thường hoặc kiểm thử tự động; tránh lặp suy luận trả phí khi xác minh thay đổi.

## Giới hạn xác minh P4 ngoại tuyến

Kiểm thử ghép ứng dụng/runtime giả lập Modal SDK, tiến trình con và thăm dò mạng. Chúng xác minh topology, Secrets, lựa chọn migration, thứ tự dừng và hợp đồng proxy. Chúng không triển khai Web, chạy GPU, migration thật, đo độ bền Volume hoặc chứng minh kết nối cơ sở dữ liệu/bucket đang chạy. Xem [bốn cấu hình triển khai và hướng dẫn EC2](aws-deployment.md), [tiến độ chuyển đổi lưu trữ](storage-portability-work-in-progress.md).
