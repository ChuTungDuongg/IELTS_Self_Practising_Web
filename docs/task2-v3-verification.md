> HISTORICAL verification of Task 2 v3. Current Task 2 is MTS v7; Task 1 is Hybrid TACS. See [the current overview](ai-writing.md). Original results and Git state below are preserved as history.

# Task 2 v3 verification — 2026-10-08

1. **Previous LR root cause:** the model generated a quote, then exact/conservative Unicode-whitespace matching rejected punctuation or copying differences as `QUOTE_NOT_EXACT`. A second invalid evidence response escaped the sequential loop and prevented GRA from running. Provider connectivity was already working.
2. **Evidence identity:** the v3 model selects only `source_id` plus concise Vietnamese `assessment`; optional `focus` does not determine validity and is not persisted. Unknown IDs cause one targeted repair, then a local criterion failure. The four independent evidence/scoring pairs remain.
3. **Segmentation:** deterministic pure `essay_sources.segment_essay` numbers non-empty blank-line paragraphs and conservatively splits sentences. It retains original Python character offsets and exact slices, supports CRLF/LF, repeated sentences, abbreviations/decimals, quotes, apostrophes, dashes, multiple spaces and Unicode terminal punctuation. Every segment is tested against `essay[start:end]`.
4. **Exact quotes:** backend source-map lookup supplies `source_id`, exact original `quote`, and assessment to snapshots/SSE. v3 never calls legacy quote matching. Long original sentences no longer hit the previous 600-character model-copy limit. English evidence is never translated.
5. **Prompt/fingerprint:** `mts-task2-v3`. Configured v1/v2 use effective v3, and custom labels include v3. Old completed history remains readable but is not reused as v3 cache. Integration tests cover both old versions.
6. **Finish reasons:** transport reads and sanitises metadata, preserving stop/length/abort/error and safe buckets for other, missing, filter or tool reasons. vLLM 0.13 semantics were checked in its primary source. Length is rejected even for complete-looking JSON; exactly one shorter repair is allowed. Evidence is max 4 items, assessment max 320 characters with two concise sentences requested. Guided JSON output, temperature 0/seed 0 and the existing 1800-token vLLM budget remain. No global token increase, deployment change or GPU job.
7. **Failure isolation/completion:** persist and emit `criterion.failed`, then continue later traits. TA/CC success + LR failure + GRA success ends FAILED with three visible results and no raw mean/overall. Four successes alone produce COMPLETED and aggregates. Shutdown/stale recovery also preserves an interrupted later criterion alongside previous failures.
8. **SSE/UI:** completed cards and Bands appear immediately. Exactly four vertical steps retain completed/active/waiting/failed styling and reduced-motion support. Live counts distinguish successes/errors/current work. Final failure notices only appear at terminal state. Persisted snapshots, sequence replay and reconnect retain completed cards and individual failures without restarting inference. Heartbeats affect only liveness.
9. **Vietnamese/calibration:** generated assessments, feedback, strengths, improvements and concise comparison summaries explicitly request Vietnamese; safe errors/progress are Vietnamese. Only the four official IELTS criteria are used. Current official Task 2 descriptors (publication updated May 2023, checked 2026-10-08) are faithfully paraphrased, including lower bands and scope/extent distinctions. Scoring compares adjacent whole-band descriptors holistically; half-bands interpolate. High scores require concise affirmative justification within the same scoring interaction. Source IDs, comparison structure, next official whole-band value and the absence of an impossible higher-band blocker at 9 are validated. There are no score subtraction constants, error-count rules or deterministic severity caps. Prompts require score/feedback consistency. Fake tests establish the contract; they do not prove real-model calibration against human scores.
10. **Focused verification:** all commands below passed. PostgreSQL integration used an isolated temporary local `postgres:17-alpine` container at port 55433, migrated with the repository's existing Alembic migrations, then stopped. All automated grading used fake providers. An initial attempt against the configured unavailable local DB was stopped and rerun against the isolated DB. Initial red tests and review regressions were repaired before the final runs. No unrelated suite, browser or Playwright.

```text
# backend (DATABASE_URL directed to the temporary test database)
uv run pytest tests/test_essay_sources.py tests/test_mts_writing_v3.py tests/test_mts_writing_validation.py tests/test_writing_llm_providers.py tests/test_writing_llm_readiness.py tests/test_writing_ai.py -q --tb=short
# 170 passed in 20.36s

uv run ruff check app/api/v1/writing_ai.py app/core/config.py app/domains/scoring/essay_sources.py app/domains/scoring/ai_writing_validation.py app/domains/scoring/mts_prompts.py app/providers/writing_llm/base.py app/providers/writing_llm/http.py app/providers/writing_llm/__init__.py app/schemas/writing_ai.py app/services/mts_writing.py app/services/writing_ai.py app/services/writing_ai_worker.py tests/test_essay_sources.py tests/test_mts_writing_validation.py tests/test_mts_writing_v3.py tests/test_writing_ai.py tests/test_writing_llm_providers.py tests/test_writing_llm_readiness.py
# All checks passed

# frontend
npx vitest run tests/writing-ai-assessment.test.tsx tests/writing-ai-progress.test.tsx tests/writing-review.test.tsx
# 3 files passed; 24 tests passed
npm run typecheck
# passed
npx eslint src/lib/api/writing-ai.ts src/features/writing/writing-ai-progress.tsx src/features/writing/writing-ai-assessment.tsx tests/writing-ai-assessment.test.tsx tests/writing-ai-progress.test.tsx
# passed

# repository
git diff --check
# passed (Git emits only existing LF/CRLF conversion notices)
```

11. **Files changed:**

- `backend/app/api/v1/writing_ai.py`
- `backend/app/core/config.py`
- `backend/app/domains/scoring/ai_writing_validation.py`
- `backend/app/domains/scoring/mts_prompts.py`
- `backend/app/providers/writing_llm/__init__.py`
- `backend/app/providers/writing_llm/base.py`
- `backend/app/providers/writing_llm/http.py`
- `backend/app/schemas/writing_ai.py`
- `backend/app/services/mts_writing.py`
- `backend/app/services/writing_ai.py`
- `backend/app/services/writing_ai_worker.py`
- `backend/tests/test_mts_writing_validation.py`
- `backend/tests/test_writing_ai.py`
- `backend/tests/test_writing_llm_providers.py`
- `backend/tests/test_writing_llm_readiness.py`
- `docs/ai-writing.md`
- `frontend/src/features/writing/writing-ai-assessment.module.css`
- `frontend/src/features/writing/writing-ai-assessment.tsx`
- `frontend/src/features/writing/writing-ai-progress.tsx`
- `frontend/src/lib/api/writing-ai.ts`
- `frontend/tests/writing-ai-assessment.test.tsx`
- `frontend/tests/writing-ai-progress.test.tsx`
- `backend/app/domains/scoring/essay_sources.py`
- `backend/tests/test_essay_sources.py`
- `backend/tests/test_mts_writing_v3.py`
- `docs/superpowers/plans/2026-10-08-task2-source-calibration.md`
- `docs/task2-v3-verification.md`

12. **Git status:** branch `main`, starting HEAD `e1a951b` containing the prior local fixes. No staged changes; no reset, clean or remote checkout. The pre-existing untracked `docs/MTS.pdf` is preserved. Final status:

```text
 M backend/app/api/v1/writing_ai.py
 M backend/app/core/config.py
 M backend/app/domains/scoring/ai_writing_validation.py
 M backend/app/domains/scoring/mts_prompts.py
 M backend/app/providers/writing_llm/__init__.py
 M backend/app/providers/writing_llm/base.py
 M backend/app/providers/writing_llm/http.py
 M backend/app/schemas/writing_ai.py
 M backend/app/services/mts_writing.py
 M backend/app/services/writing_ai.py
 M backend/app/services/writing_ai_worker.py
 M backend/tests/test_mts_writing_validation.py
 M backend/tests/test_writing_ai.py
 M backend/tests/test_writing_llm_providers.py
 M backend/tests/test_writing_llm_readiness.py
 M docs/ai-writing.md
 M frontend/src/features/writing/writing-ai-assessment.module.css
 M frontend/src/features/writing/writing-ai-assessment.tsx
 M frontend/src/features/writing/writing-ai-progress.tsx
 M frontend/src/lib/api/writing-ai.ts
 M frontend/tests/writing-ai-assessment.test.tsx
 M frontend/tests/writing-ai-progress.test.tsx
?? backend/app/domains/scoring/essay_sources.py
?? backend/tests/test_essay_sources.py
?? backend/tests/test_mts_writing_v3.py
?? docs/MTS.pdf
?? docs/superpowers/plans/2026-10-08-task2-source-calibration.md
?? docs/task2-v3-verification.md
```

13. **Scope:** Task 1-A was NOT implemented. No Task 1 schema, UI, prompt or scoring code was added. No official Writing score writes; the existing Copy-to-form and explicit human Save policy remains. Integration tests confirm official score isolation. No model/deployment changes, new schema migration or secrets.
14. **Publication:** nothing was pushed, staged or committed.

Sources: [official IELTS Writing Band Descriptors](https://ielts.org/cdn/ielts-guides/ielts-writing-band-descriptors.pdf), [vLLM 0.13 finish semantics](https://github.com/vllm-project/vllm/blob/v0.13.0/vllm/v1/engine/__init__.py), [vLLM structured JSON output](https://docs.vllm.ai/en/v0.13.0/features/structured_outputs/).
