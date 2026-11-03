# Speaking hybrid v1 — implementation handoff

Date: 2026-11-03. Baseline and HEAD at start: `3cf5c9a`.
Branch: `codex/speaking-hybrid-v1`. User subsequently authorized commit/push and CI fixes;
delivery checks are recorded below. No deployment, production provider switch or historical band update.
Unrelated pre-existing untracked files were preserved.

Delivery follow-up: Windows launcher now selects the hybrid profile from `.env.modal`,
forwards Azure credentials and the full Speaking Luna policy through private ephemeral
Secrets, and checks the pinned VAD asset before starting Modal. The ignored local staging
configuration selects hybrid + OpenAI; shared defaults remain legacy. Azure key/region
are still absent: offline preflight correctly refuses to start and makes zero calls.
User will add credentials later. The existing classroom page prop type error was fixed
with a route wrapper. Full frontend typecheck and ESLint now pass; Ruff lint/format and
lock validation pass. Updated offline adapter/launcher/Modal/feature selection: **118 passed**.
CI now runs on `codex/**` pushes as well as main and pull requests.
Production `npm run build` also passed locally and is now a CI check so generated
Next.js route contracts used by the Modal image are validated. The native Docker
probe was repeated with network disabled and again passed with zero provider calls.
The launcher explicitly selects both graders, overriding stale shell selectors.

## Changed interfaces and ownership

| Area | Files / interface |
| --- | --- |
| Neutral contract | `backend/app/schemas/speech_analysis.py`: versioned `SpeechAnalysisResult`, lexical/display transcript, utterances, optional word confidence, observations, uncertain regions, capabilities, usage and latency |
| Azure SDK | `backend/app/providers/speech_analysis/azure.py`: `AzureSpeechAnalyzer.analyze(NormalizedAudio, response_id, take_number, segment_id)`; `azure_analysis_identity(settings)` without SDK import |
| Coordinator | `backend/app/services/speaking_hybrid.py`: `analyze_response` processes each continuous recorder segment once; `analysis_to_asr` reuses lexical transcript and word timings |
| Durable speech cache | `speaking_analysis_cache.py`, existing normalized-audio JSONB; request intent before provider call, per-segment result checkpoint, uncertain-billing fence, no blind retry |
| Timeline | `schemas/speaking_timeline.py`, `services/speaking_audio.py`: exact frame boundaries internally, integer ms playback mapping, unknown recovery gaps, immutable raw audio |
| CPU fluency | `services/speaking_vad.py`, `speaking_hybrid_features.py`, `speaking_features.py`; controlled Silero v6.0 ONNX asset, checksum, CPU executor/admission, VAD spans/runs and heuristic lexical candidates |
| Scoring | `speaking_scorer.py`, `schemas/speaking_grading.py`, `domains/scoring/speaking_prompts.py`: criterion projection, whole-attempt FC/PR eligibility, bounded stratified PR observations, preserved score-first/overall rules |
| Feedback | `services/speaking_feedback.py`: validates evidence IDs, resolves one response/take/segment span; model timestamps are forbidden; safe observations may remain without a band |
| Workers and API | `speaking_transcript_worker.py`, `speaking_ai_worker.py`, `speaking_transcript.py`, `speaking_ai.py`; partial checkpoints and analysis/accounting propagation; existing media/auth access; authenticated `/speaking-attempts/analysis-profile` |
| Public DTOs | `schemas/speaking_ai.py`, `speaking_ai_runs.py`, `speaking.py`; optional versioned evidence, partial transcript state, server-resolved local comments, external-processing notice |
| Existing review UI | `frontend/src/features/speaking/speaking-{review,ai-assessment,transcript-panel,audio-player,audio-replay}.tsx`; typed clients in `frontend/src/lib/api/`, EN/VI labels, existing CSS; exclusive/bounded keyboard-accessible replay |
| Evaluation | `backend/app/evaluation/speaking/`, `scripts/evaluate_speaking.py`: speaker splits, label isolation, fidelity/timing/false-positive metrics, FC/PR error metrics, usage/calls/latency/repeat stability, guarded live/resume |
| Deployment/setup | `deploy/modal/app.py`, `speaking_cpu.py`, CPU probe Dockerfile/startup script, `scripts/setup_speaking_vad.py`; optional pinned extras in `backend/pyproject.toml` and `uv.lock`; `.env.example`, ignored model binaries |
| Documentation/tests | Current `docs/ai-speaking.md`, `speaking-transcription.md`, `modal-web.md`; provider notes/checklist and focused backend/frontend tests |

## Enable explicitly

Install `uv sync --extra azure-speech --extra speech-vad` in `backend/`.
From repo root, run:

```powershell
backend/.venv/Scripts/python.exe scripts/setup_speaking_vad.py storage/models/silero-v6.0.onnx
```

Configure backend only (never Next.js):

```dotenv
SPEAKING_PROFILE=speaking_hybrid_v1
SPEAKING_ASR_ENABLED=true
SPEAKING_AZURE_KEY=<backend-secret>
SPEAKING_AZURE_REGION=<resource-region>
SPEAKING_AZURE_LOCALE=en-US
SPEAKING_AZURE_PROSODY=true
SPEAKING_AZURE_TIMEOUT_SECONDS=180
SPEAKING_AZURE_MAX_CONCURRENCY=2
SPEAKING_AZURE_MAX_QUEUE=8
SPEAKING_VAD_MODEL_PATH=../storage/models/silero-v6.0.onnx
SPEAKING_VAD_MODEL_SHA256=597d30b3ec076608d059477bb14cfeffdf951bf5cae370d38f65d33bbfe82004
SPEAKING_AI_ENABLED=true
SPEAKING_AI_PROVIDER=openai
SPEAKING_AI_MODEL=gpt-6-luna
```

Reuse the existing backend OpenAI credential/policy. `en-US` is a technical locale,
not an American-accent requirement. Missing Azure/VAD config does not prevent Writing
or application startup. The profile endpoint reports configuration, never verified live readiness.
For Modal, use the explicit frozen profile/VAD asset selectors documented in `modal-web.md`.
Other optional Writing/chart services retain their own provider choices.

## Reuse and integrity

The speech result is durable and independent of Luna prompt/feature cache identity.
ASR and PR adapters do not separately call Azure. Each recovered continuous segment
is its own session and accounting record. Lexical text is preserved (including
`Yesterday I go`); display formatting does not repair grammar. No-match after a
successful final is partial, with uncertainty retained. Missing confidence stays unknown.

Quality/access checks precede external audio processing. Raw recording bytes are never
trimmed, denoised or time-stretched. Normalization keeps exact sample boundaries and
maps feedback to the private original segment. Feedback cannot cross recovery joins.
Derivative repair preserves the speech billing ledger. Interrupted/unknown requests
require operator reconciliation; internal idempotency does not guarantee provider billing.

FC/PR gates are documented technical coverage policies, not band thresholds and not
examiner calibration. Missing criteria keep overall unavailable; saved valid scores and
authorized human final scores remain intact. Low accuracy never proves a sound substitution.

## Verification actually performed

- TDD red/green for neutral/timeline/VAD contracts, shared-result worker/cache, partial/no-match,
  unknown billing, source-frame recovery splits, eligibility, feedback IDs and long PR payloads.
- Backend combined regression: **742 passed in 426.50s** on a dedicated migrated PostgreSQL
  Docker test database, with live Speaking/ASR/Writing disabled in the test environment.
  Selection: every `backend/tests/test_speaking*.py`, `test_azure_speech_analysis.py`,
  `test_modal_speaking_hybrid.py`, `test_full_mock_speaking.py`, `test_full_mock_sessions.py`,
  `test_full_mock_history_delete.py`, `test_task1_writing_ai.py`, `test_writing_ai.py`,
  `test_writing_score_first.py` and `test_writing_attempts.py`.
  Separate evaluation/Modal composition regression: **118 passed**. Final focused
  projection/feedback/adapter/evaluation/CPU tests: **57 passed** after the review fixes.
  Final durable hybrid worker + projection/feedback recheck: **19 passed** on the test DB.
  The initially interrupted shared-DB runs are not claimed as passing evidence.
- Frontend: `node node_modules/vitest/vitest.mjs run --maxWorkers=1 tests/speaking`:
  **150 passed**. Scoped ESLint passed. Source TypeScript passed.
- Full `tsc --noEmit` is blocked by the existing generated classroom route validation:
  `.next/types/app/classrooms/[classroomId]/overview/page.ts:39`, extra `teacher` prop TS2344.
  No unrelated classroom code was changed.
- Actual Chromium: fictional review at desktop 1440px EN/light and mobile 375px VI/light/dark;
  no autoplay, keyboard replay loads the matching private segment only, seeks 1.5s for a
  2–4s span and stops at approximately 4.508s with bounded context. Mobile width equals
  viewport, button height 44px, no page JS errors. Ignored screenshots:
  `frontend/test-results/speaking-hybrid/`. Disposable preview route/server removed.
- Actual pinned Silero model checksum verified and ONNX inference ran with only
  `CPUExecutionProvider`; synthetic audio, zero provider calls.
- Actual Docker native probe with `--network none`: `CPU_NATIVE_PROBE_OK`, zero calls,
  GPU false. Actual full FastAPI CPU backend lifecycle against a dedicated empty migrated
  test DB: `CPU_BACKEND_STARTUP_OK`, health/readiness passed, zero calls, no Whisper/torch imports.
- Offline Modal graph tests verify the hybrid branch omits bundled T4/Whisper. No Modal
  account, cloud container, production integration or live speech/LLM benchmark was run.

Representative commands (PowerShell; use explicitly isolated test DB environment values):

```powershell
# In backend/: DATABASE_URL must be a dedicated migrated test DB; TEST_DATABASE_URL
# must name a second isolated DB if the selected fixture requires it.
$env:SPEAKING_AI_ENABLED = "false"
$env:SPEAKING_ASR_ENABLED = "false"
$env:AI_WRITING_ENABLED = "false"
$tests = @(Get-ChildItem tests/test_speaking*.py | ForEach-Object FullName)
.venv/Scripts/python.exe -m pytest @tests tests/test_azure_speech_analysis.py tests/test_modal_speaking_hybrid.py tests/test_full_mock_speaking.py tests/test_full_mock_sessions.py tests/test_full_mock_history_delete.py tests/test_task1_writing_ai.py tests/test_writing_ai.py tests/test_writing_score_first.py tests/test_writing_attempts.py -q
# In frontend/:
node node_modules/vitest/vitest.mjs run --maxWorkers=1 tests/speaking
# In repository root:
docker build --file deploy/modal/Dockerfile.speaking-hybrid-probe --target backend-startup --tag bandpilot-speaking-hybrid-backend-probe:local .
```

The temporary PostgreSQL container and fictional databases were created only for this
verification and removed afterward. Local probe images, ignored model asset and screenshots
remain available for inspection. Existing deployments/data were not touched.

## Live limits, estimate and rollback

**LIVE_UNVERIFIED**: transcript fidelity, real timings, accent false positives, regional
prosody capability, billing and examiner agreement need independently labelled human audio.
Mocks/TTS do not establish IELTS ground truth. Full Modal Web runtime remains
**CONTAINER_UNVERIFIED** despite the local native/backend startup probes.

Official price sources and verification date (2026-11-03) are in `docs/ai-speaking.md`.
Example estimate only: 15 continuous segments totalling 720 submitted seconds imply
15 Azure sessions and approximately `0.2 × (regional baseline hourly rate + applicable
prosody hourly rate)`, before account-specific billing rules/failed or uncertain calls.
Two extra recovery segments mean two extra sessions; sum their submitted durations,
never infer wall-clock silence. Add Luna input/output token usage at the configured rate,
plus CPU/storage/network. No project-specific USD rate or invoice was verified.

Live CLI needs explicit opt-in, speaker-disjoint splits, sample and estimate limits;
it never runs automatically. Hybrid resume does not resend an already-started speech
request. Estimate admission is not a hard cloud billing cap.

Rollback by disabling the hybrid flags or explicitly selecting `SPEAKING_PROFILE=legacy`
with the previously verified local/Modal ASR settings. For a future Modal rollout, rebuild
with the legacy frozen marker. Preserve old cache/history and human final scores; do not
rewrite historical bands or delete/stop existing deployments. No schema migration required.
