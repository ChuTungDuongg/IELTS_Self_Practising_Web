# Task 1 evaluation (T1-C)

The CLI reuses production visual grounding, optional fail-open DePlot,
deterministic facts, claim verification, source evidence and four-criterion MTS.
It needs no database. Production uses `mts-task1-visual-v4` with perception
contract `mts-task1-visual-v3` and scoring guidance `mts-task1-scoring-v4`.
The v3 benchmark candidate preserves the former scoring/evidence prompts with
the same current perception and scoring engine. Task 2 is unchanged.

## Local dataset

Use a UTF-8 JSONL manifest: one versioned sample per line. The generated
`manifest.schema.json` is the input contract. Required fields are:

- `schema_version: 1`, a unique ASCII `id`, `split: dev | holdout`, and a Task 1
  `task_type` from the production registry.
- `prompt`, `essay`, and `image_path`. Paths may be absolute or relative to the
  manifest. Only local PNG/JPEG/WebP images up to 10 MiB are accepted; URL images
  are never fetched.
- `human_scores` containing `ta`, `cc`, `lr`, `gra`, each from 0 to 9 in half-band
  increments. Use agreed/adjudicated human or authorised reference scores.
  Do not label another model's predictions as ground truth.
- `raters` (defaults to 1), `provenance` describing authorship/licence and score
  source, and `redistributable`. One rater is sufficient; keep the agreed target
  and the number of raters rather than silently rounding their mean.
- Optional `visual_truth`: the production typed VisualReference shape, with
  independently annotated chart/table categories, series or cells and values.
  Provide complete semantic annotation for the selected components. Labels and
  units matter; opaque component/series IDs do not. Unknown or estimated truth
  cannot certify exact perception. Other visual families may be benchmarked for
  scores, but currently have no automated factual metric.

For repeated pies sharing a legend/unit, annotate one `pie_chart` component:
categories are regions, series are legend categories, and each series has a
point per region. Percentages use numeric chart units: 48 means 48%, not 0.48.

Keep private/licensed datasets in `private/` or outside the repository. The
benchmark does not copy source images/essays or upload content except to the
configured scoring provider and explicitly requested existing DePlot provider.
`private/`, JSONL/image datasets and generated reports/cache are ignored here.
Custom output paths outside this tree need your own ignore rules. No essays,
quotations, raw completions, chart labels/values or secret URLs are in reports
or checkpoints; only IDs, hashes, scores, counts and safe status codes remain.

## Commands

From `backend/`, first validate your local data without inference:

```powershell
uv run python ../scripts/benchmark_task1.py --manifest ../benchmarks/writing_task1/private/manifest.jsonl --split dev --scoring-version v4 --chart-specialist off --dry-run --output ../benchmarks/writing_task1/reports/dev-plan
```

An explicit one-sample real smoke, using existing backend provider settings:

```powershell
uv run python ../scripts/benchmark_task1.py --manifest ../benchmarks/writing_task1/private/manifest.jsonl --split dev --limit 1 --scoring-version v4 --chart-specialist off --resume --output ../benchmarks/writing_task1/reports/dev-smoke
```

Controlled v3/v4 and DePlot off/on comparisons:

```powershell
uv run python ../scripts/benchmark_task1.py --manifest ../benchmarks/writing_task1/private/manifest.jsonl --split dev --scoring-version both --chart-specialist both --resume --output ../benchmarks/writing_task1/reports/dev-ablation
```

`both` × `both` runs four configurations **per sample**. `--limit` limits unique
samples, not the number of provider requests. Specialist-on applies only to
chart/table families, remains fail-open, and may fall back if unavailable.
Run one-sample/single-configuration smoke first. No benchmark is started by the
application. From repository root, the equivalent entry point is
`uv run --project backend python -m scripts.benchmark_task1 ...`.

Use `--split holdout` with a different output directory for the final untouched
evaluation set. Develop prompts on dev only; repeated inspection/tuning against
holdout invalidates its purpose. Targets and annotations never enter requests
to the scoring or specialist provider.

## Reports and resume

Each output directory contains `report.json`, `report.md`,
`disagreements.csv`, an atomic `cache/` checkpoint per sample/configuration,
and append-only `attempts/` records preserving earlier failures and costs.
Reports default to IDs rather than full essays. They include:

- Criterion and backend-rounded Task 1 overall exact, ±0.5, ±1.0 agreement,
  MAE, signed prediction-minus-target bias, RMSE, and QWK.
- Counts for every aggregate, task-type/family/split strata and each criterion's
  target-band bucket. QWK requires at least 10 comparable half-band pairs and
  nonzero expected variance; otherwise JSON records the reason it is unavailable.
- Separate primary and reconciled perception: labelled numeric agreement,
  semantic alignment, missing/extra/unknown values and reconciliation disagreements.
- Per-sample error decomposition, wall time, completion request counts/token
  usage, specialist calls/time/fallbacks, and partial linguistic scores after a
  genuine primary failure. Overall agreement uses only all-four-criterion results.
- Paired ablations and largest score disagreements by sample ID. Failed runs
  remain visible rather than silently disappearing from failure statistics.
  Score deltas use the same valid paired cases for each criterion. Failure and
  latency comparisons also include failed cases; dropout cannot masquerade as
  better score agreement.

Resume identity includes sample content/targets/truth, image bytes, provider and
model, hashed endpoints, separate perception/scoring versions, pinned specialist
model/revision/contract, timeout settings, benchmark version and implementation
hash. Paths and presentation labels do not change identity. Changing annotations
invalidates checkpoints to prevent stale metrics. `--resume` reuses only validated
successful records; a corrupt checkpoint can recover from its validated latest
attempt, while failures or unavailable valid records retry. Atomic attempts and
checkpoints are written after each run, so interruption does not lose previous successes.
Cache hits retain historical latency/usage; report `new_*_calls` excludes hits.
Scoring metrics describe the latest outcome. Operational statistics separately
show first-attempt and all-recorded-attempt failure rates and cumulative recorded
calls, usage and latency. Retrying to success never erases an earlier failure or
its recorded cost. An interrupted in-flight request has unknown final usage;
these statistics cover completed attempt records only.

## Interpretation

Positive signed bias means generosity; negative bias means under-scoring. Read
each criterion separately so mixed errors cannot cancel in overall.

- Bad perception and TA disagreement: investigate perception/reconciliation.
- Accurate perception but TA disagreement: investigate Task Achievement guidance.
- CC/LR/GRA positive bias with good perception: investigate scorer calibration.
- Persisting broad bias after prompt work: evaluate stronger scoring or a
  benchmark-only descriptor adjudicator before promoting any production tool.

Error categories include perception OK with scores OK/high/low/mixed,
PERCEPTION_ERROR, SPECIALIST_DISAGREEMENT, UNUSABLE, and explicit unannotated
perception variants. Score OK means each criterion is within 0.5 of its reference;
this evaluation convention never changes a predicted score. Specialist disagreement
does not establish which reader is correct; consult independent visual truth.

No experimental adjudicator, second judge, automatic deployment, numeric offset,
band cap, or production auto-calibration is implemented. Small synthetic tests
prove arithmetic and orchestration; effectiveness requires a labelled human set.
