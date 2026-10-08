# Task 1 calibration and evaluation implementation plan

Implement the supplied two-part specification against 78a742d. Preserve the
current Task 1 perception contract, optional fail-open DePlot, source grounding,
and Task 2 v6. Do not add another judge or production score correction.

1. Replace Task 1's string-edited Task 2 guidance with four dedicated criterion
   scopes, feedback boundaries and original descriptor paraphrases. Test whole
   response/adjacent profile fit and half-band interpolation before changing
   builders. Retain the shared MTS engine and Vietnamese output contracts.
2. Version the production Task 1 scoring change as mts-task1-visual-v4. Report
   perception v3 and scoring v4 separately without a persistence migration.
   Preserve benchmark-only v3 guidance behind protected prompt-builder hooks;
   production continues using v4 only.
3. Add backend/app/evaluation/task1: a strict versioned JSONL sample schema,
   local-image loading, deterministic score/perception metrics, service-level
   runner, private content-addressed checkpoints, and JSON/Markdown/CSV reports.
   Human scores and annotations are evaluation-only and never scorer inputs.
4. Add python -m scripts.benchmark_task1 with explicit dev/holdout selection,
   limit, dry-run, output, resume, scoring-version v3/v4/both and specialist
   off/on/both. Compare only matching samples and separate primary perception,
   reconciled perception, scores, failure rates, latency and usage.
5. Add benchmark README, generated manifest schema and ignored private/report
   directories. Commit no benchmark essays, target labels or binary images.
   Tests use original synthetic examples; they establish plumbing, not real
   calibration effectiveness.
6. Verify with focused prompt, metric, manifest, runner/cache, Task 1 perception
   and Task 2 regression tests, Ruff, CLI dry-run and git diff --check. Review the
   integrated changes. Do not run a real labelled benchmark automatically,
   enable an adjudicator, commit or push.

Independent implementation ownership: Task 1 guidance and pure metrics are
delegated to separate agents. The parent owns manifests, orchestration, reports,
CLI, documentation and integration verification.
