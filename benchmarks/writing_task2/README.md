# Offline Writing Task 2 benchmark

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Offline Writing Task 2 benchmark. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../../scripts/benchmark_task2.py).
> Đọc cùng [current module/guide](../../docs/modules/writing.md); [audit và giới hạn](../../docs/DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

The admin bank's `task2.jsonl` works directly with the CLI. JSONL is canonical;
CSV is inspection only. `schema_version: 1` identifies the file format, not a
bank/dataset version. The schema is generated from
`app.evaluation.task2.models.BenchmarkSample`.

Human labels are `tr`, `cc`, `lr`, `gra`, each 0–9 in half bands. Export uses
one rater, a neutral provenance fallback, and false-default redistribution.
Labels never enter inference. Task 2 has no image, perception or DePlot.

From the repository root, validate without a provider:

```sh
uv run --project backend python scripts/benchmark_task2.py --manifest benchmarks/writing_task2/private/task2.jsonl --split dev --dry-run --output benchmarks/writing_task2/reports/dev-plan
```

Optional **manual** one-sample provider smoke (not an implementation/CI test):

```sh
uv run --project backend python scripts/benchmark_task2.py --manifest benchmarks/writing_task2/private/task2.jsonl --split dev --limit 1 --max-concurrent-llm-requests 2 --resume --output benchmarks/writing_task2/reports/dev-smoke
```

Samples execute sequentially. Inside a sample, the production service bounds
criterion requests to 1–4. Its effective prompt is currently `mts-task2-v12`;
the evaluator does not change production prompts/calibration. Use DEV for
iteration and a separate `--split holdout` output for final evaluation.

Output: `report.json`, `report.md`, `disagreements.csv`, `cache/`, `attempts/`.
Task 2 shares Task 1's exact/±0.5/±1.0 agreement, bias, MAE, RMSE and QWK code.
QWK requires 10 comparable half-band pairs and nonzero expected variance.
Failures remain visible; valid partial criteria may contribute metrics, while
overall requires all four predictions. Earlier failed attempts/costs remain
after retry-to-success. Cache hits add zero new requests. Interrupted in-flight
costs are unknown, never manufactured.

Resume identity includes contents, labels, split, provider/model, hashed endpoint,
effective prompt, runtime settings, textarea provenance, contract and implementation.
Paths/presentation labels do not affect it. Failed/corrupt/inconsistent records
are not successful cache hits.

Keep private inputs and reports ignored or outside Git. Reports contain safe IDs,
hashes, scores and counters, not source text or raw provider errors. Inference
sends the prompt/essay to the configured provider. No production DB, admin
session or API connection is needed. See [the Colab guide](../../docs/writing-benchmark-bank.md).
