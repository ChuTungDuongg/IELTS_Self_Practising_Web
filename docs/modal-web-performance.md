# Modal Web latency investigation

For a Vietnamese explanation of the architecture, investigation and results, see the
[educational case study](case-studies/modal-web-performance.md). For interview practice,
see [performance engineering questions and answers](interview/modal-performance-qa.md).

## Findings and limits (initial investigation)

- Starting revision: `4a6b5b0850bb39161a308de3207f6d93b1c3a7e7`.
- The supplied incident summary reports a static-asset waterfall in roughly 0.63 s steps and a median of approximately 1.84 s across 201 requests. The original request log was not available for independent analysis. The reported Modal execution metric is not equivalent to FastAPI/Next.js handler time.
- The Web class has one container and no input-concurrency decorator. [Modal's concurrency documentation](https://modal.com/docs/guide/concurrent-inputs) states that the default is one input per container. Its documented class-level decorator is accepted by the installed Modal Python SDK 1.5.3 with this class/web-server shape, but this local declaration is not a deployed concurrency test. The reported waterfall is consistent with queueing; it does not establish where the delay occurs or how much is queueing.
- No running, verified isolated staging deployment was available for this investigation. Listed dev apps were stopped; dev's default asset volume can be shared with production. There was no remote benchmark, region lookup, deployment, volume change, or production traffic. Consequently the compute region, Vietnam RTT, deployed CPU/memory, p50/p95 and throughput remain **unmeasured**. Do not infer a latency improvement from synthetic localhost timings.
- Nginx allows multiple connections and proxies to separate Next.js and Uvicorn processes; that alone does not demonstrate their throughput under load. SQLAlchemy's local configuration uses a pool size of 5 plus up to 10 overflow connections per engine; database checkout or query latency has not been measured. No database pool, replica, Nginx buffering, caching, streaming, upload or range settings were changed.
- Auth already coordinates refreshes in flight and uses a browser lock for cross-tab refresh. Session probes and restoration have security/recovery roles. Header navigation already uses intent-based prefetch and disables it for sensitive links. There was insufficient evidence to change these flows.
- A focused component baseline showed one notification-list request while the panel was closed, followed by another on opening. The first is unnecessary: the updated component fetches only the unread count until the panel opens. With the same test harness, list requests before opening changed **1 → 0** and opening still fetches the current list and count. This is a request-count result, not a deployed latency measurement.

## Safe benchmark

Use only an explicitly authorized, isolated staging deployment whose database, assets, secrets and ownership are verified independent of production. The script does not establish isolation for you. Do not point it at production without explicit authorization. It sends only unauthenticated GETs to `/`, `/api/v1/ready`, `/icon.svg` and a real same-origin Next.js static asset discovered in the HTML. It does not follow redirects or send credentials. The ready endpoint performs a database readiness check. The default is 16 requests per endpoint at each of concurrency 1, 4, 8 and 16, with two sequential warmups per endpoint, plus one HTML discovery request: at most 265 requests when an asset is found. Reduce the levels/count if even this is inappropriate for the environment.

```powershell
python scripts/benchmark_modal_web.py --base-url https://YOUR-ISOLATED-STAGING.modal.run --confirm-staging --requests 16 --concurrency 1,4,8,16 --warmup 2 --timeout 15 --output modal-before.json
```

After an independently validated staging-only change, repeat the exact command with `--output modal-after.json`, using the same deployment mode, origin, warmup, endpoints, network and region. Compare successful-request p50/p90/p95/max and TTFB, errors, statuses, response sizes, throughput and elapsed time for each endpoint and concurrency. Also record Modal CPU/memory and region separately. A run with HTTP, validation, discovery or warmup failures exits nonzero; missing or failed data is not a latency success. The JSON reports each level separately; timings use nearest-rank percentiles of successful requests, and both all-request and successful-request throughput are provided. With 16 samples, p95 is the highest observed value: repeat controlled runs and use more samples within the script's 100-request cap for a meaningful tail comparison. Each request creates a new urllib connection, so the numbers include connection/TLS overhead and are not equivalent to a browser's reused connections. TTFB starts before DNS/connection establishment and is not a pure server or geographic RTT measurement.

The benchmark's offline fixture checks can be run without a deployment:

```powershell
python -m unittest discover -s scripts/tests -p test_benchmark_modal_web.py -v
```

## Optional timing diagnostics

Set `IELTS_MODAL_WEB_TIMINGS=true` in an appropriately isolated deployment's runtime environment and restart that deployment to enable temporary diagnostics. Default is off. Nginx then logs a generated request ID, status, request time, upstream address, upstream response time and upstream connection time, and sends its generated ID to the upstream. FastAPI logs that ID, method, status and total ASGI request time. No URL, query, headers, cookies, request/response body, user identifier or client address is logged. Remove the setting and restart to disable logging. Preserve normal operational access controls and retention for logs.

Nginx timings start only after ingress has sent the request to the container; they do not measure the Modal queue. Upstream and ASGI times include streaming and backpressure and should not be treated as CPU or handler-only duration. Correlate the generated ID for API requests; Next.js does not emit a corresponding timing log. Streaming stays unbuffered, and the timing middleware forwards ASGI messages unchanged. Validate streaming, protected media, range requests and uploads on the isolated environment before enabling any further proxy optimization.

## Initial comparison status (before P2)

| Metric | Before | After |
| --- | --- | --- |
| GET / p50 / p95 | Not measured | Not measured |
| Ready p50 / p95 | Not measured | Not measured |
| Static asset p95 | Not measured | Not measured |
| Concurrent RPS / HTTP errors | Not measured | Not measured |
| Modal Web CPU / memory | Not measured | Not measured |

On a verified staging instance, establish the baseline before trying bounded class-level `@modal.concurrent(max_inputs=8)` or `16`. Keep `max_containers=1` and the existing database ownership guard. Compare reliability and tail latency, monitor CPU, memory and database connections, and revert a candidate that worsens them. Modal's default one-input setting remained unchanged in the initial revision because no safe deployment data was available to choose a value. Investigate actual geography and RTT separately, without moving the PostgreSQL volume or changing regions. Check API timings and query plans only if the observations identify backend or database cost.



## P2 isolated staging experiment — 2026-10-29

**Decision: set class-level `@modal.concurrent(max_inputs=8)` while retaining one Web container.** In two comparable runs the readiness p95 at 16 client requests fell from 9.86/10.22 s to 2.13/2.14 s, while throughput rose from 1.57/1.54 to 6.82/6.87 requests/s, with zero measured HTTP errors. This is a controlled staging result, not a promise about production or a browser navigation. Single-request readiness p95 was 1.29/1.48 s before and 1.32/1.29 s after: input concurrency does not remove the underlying network latency.

The test used a separately named Modal dev app `bandpilot-perf-p2-app-265b0d2e`, private Volumes `bandpilot-perf-p2-db-265b0d2e`, `bandpilot-perf-p2-assets-265b0d2e`, `bandpilot-perf-p2-snapshots-265b0d2e`, Secret `bandpilot-perf-p2-config-265b0d2e`, and Dict `bandpilot-perf-p2-owners-265b0d2e`. LocalAssetStorage and embedded PostgreSQL were used, without importing any snapshot or learner data. The initially empty database was migrated by the existing startup mechanism; migration `20260923_0012` creates one inactive synthetic legacy owner. AI and GPU workloads were disabled.

A temporary copy of the starting entrypoint changed only the owner Dict name for the baseline, preventing the experiment from using the shared production guard. The candidate added the tested class-level concurrency decorator and pinned only the **staging** container to `ap-south`, the actual `MODAL_REGION` observed in the baseline container. Both used the same app URL, routing region `us-east`, database, assets, Secret, 2 CPU, 4096 MiB and `min_containers=1`, `max_containers=1`; the first container was stopped and its dedicated guard released before the second was started. The entrypoint copy was removed after testing. The production code is not pinned to a region. A broad region label does not prove the identical physical host or zone; redeployment may change either. Modal's [region documentation](https://modal.com/docs/guide/region-selection) distinguishes the container region from HTTP routing and describes the extra cost of pinning a region.

Two earlier exploratory runs used separate Volumes and a Secret but the existing shared `ielts-web-database-owner` Dict because the original runtime hardcodes its name. They temporarily wrote a staging-specific key in that shared Dict, then removed it. No production key was changed; the staging key was verified absent afterward. Those initial results are preserved as `shared-guard-*` reports and are not the main comparison. Their containers happened to run in `us-east`: the same strong queueing pattern was not observed there, and concurrency 8 had no repeatable material effect. This makes region/routing topology a plausible contributor, not proof of the production topology.

**Cleanup incident:** the final staging app continued running after the second after-run completed at 09:52:44 (UTC+7) and was stopped at 15:26:34, approximately 5 h 34 min later. It may have incurred additional Modal charges. Modal replaced its container after measurement; the app is now stopped with zero running containers, and the staging owner key is absent from both the dedicated and shared Dicts. Test Volumes, Secret and dedicated Dict were retained as requested.

Each main report uses 16 GET requests per endpoint at concurrency 1, 4, 8 and 16, two sequential warmups and a 30-second timeout, with HTML-discovered `/_next/static/chunks/4013uxh3niqjj.css` (42,141 bytes). Both versions were measured twice from the same Windows client in Vietnam. Each urllib request opens a new connection and asks for identity encoding; this is not a browser navigation. Nearest-rank p95 is the maximum of 16 observations, so it is sensitive to noise. Complete reports include per-level TTFB, sizes, statuses and errors: [baseline](performance/modal-p2/baseline.json), [baseline repeat](performance/modal-p2/baseline-repeat.json), [candidate](performance/modal-p2/after-8.json), [candidate repeat](performance/modal-p2/after-8-repeat.json), [baseline localhost](performance/modal-p2/baseline-local.json), and [server timing aggregates](performance/modal-p2/server-timings.json).

The two values in each cell are the first and second run, in order (not a confidence interval). Latencies are milliseconds; RPS counts successful requests.

| Endpoint | Client concurrency | Baseline p50 / p95 | Concurrency 8 p50 / p95 | Baseline RPS | Concurrency 8 RPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| / | 1 | 1312.86, 1298.99 / 1770.70, 1634.89 | 1312.68, 1306.00 / 1936.68, 1630.91 | 0.72, 0.74 | 0.68, 0.72 |
| / | 4 | 2380.78, 2542.91 / 3669.11, 3372.62 | 1434.54, 1596.26 / 1903.08, 1823.78 | 1.48, 1.43 | 2.52, 2.37 |
| / | 8 | 4892.50, 4872.66 / 5757.81, 5913.29 | 1692.43, 1608.55 / 2145.27, 2000.14 | 1.47, 1.46 | 4.15, 4.41 |
| / | 16 | 5823.78, 5541.64 / 10777.38, 10670.86 | 1781.25, 1791.32 / 2371.24, 2317.91 | 1.47, 1.45 | 6.07, 6.50 |
| /api/v1/ready | 1 | 1054.59, 1056.08 / 1290.24, 1479.91 | 1046.55, 1058.74 / 1320.39, 1286.56 | 0.90, 0.87 | 0.89, 0.87 |
| /api/v1/ready | 4 | 2472.85, 2438.81 / 2950.40, 3018.96 | 1067.06, 1122.85 / 1610.81, 1467.90 | 1.54, 1.53 | 3.17, 3.04 |
| /api/v1/ready | 8 | 4867.89, 4898.71 / 5318.87, 5404.96 | 1470.44, 1452.90 / 1700.56, 1504.42 | 1.55, 1.52 | 4.76, 5.22 |
| /api/v1/ready | 16 | 5142.21, 5142.76 / 9856.98, 10218.82 | 1539.27, 1572.08 / 2129.83, 2137.18 | 1.57, 1.54 | 6.82, 6.87 |
| /icon.svg | 1 | 1233.00, 1254.09 / 1493.08, 1498.33 | 1246.59, 1257.17 / 1506.44, 1759.00 | 0.77, 0.76 | 0.76, 0.74 |
| /icon.svg | 4 | 2506.17, 2488.92 / 3106.61, 3248.66 | 1283.19, 1316.75 / 1694.45, 1603.11 | 1.49, 1.50 | 2.60, 2.66 |
| /icon.svg | 8 | 4978.59, 4973.73 / 5669.88, 5724.44 | 1513.72, 1453.94 / 1810.32, 1689.04 | 1.50, 1.50 | 4.75, 4.84 |
| /icon.svg | 16 | 5563.69, 5476.73 / 10442.29, 10381.65 | 1514.81, 1666.75 / 2109.00, 2125.18 | 1.48, 1.49 | 6.96, 6.76 |
| static CSS | 1 | 1564.55, 1539.27 / 1954.04, 1904.52 | 1565.42, 1562.51 / 1913.51, 1987.85 | 0.58, 0.63 | 0.59, 0.59 |
| static CSS | 4 | 2472.47, 2497.72 / 4010.45, 3700.02 | 1665.07, 1810.17 / 1981.68, 2095.78 | 1.45, 1.46 | 2.11, 2.15 |
| static CSS | 8 | 4832.38, 4812.58 / 6152.04, 6122.16 | 1808.49, 1777.22 / 2238.15, 2269.78 | 1.46, 1.48 | 3.60, 3.68 |
| static CSS | 16 | 5933.25, 5829.77 / 11114.79, 10897.65 | 2008.86, 2010.92 / 2627.78, 2589.90 | 1.42, 1.42 | 5.70, 5.31 |


| Additional metric | Baseline | Concurrency 8 |
| --- | --- | --- |
| HTTP errors | 0 / 512 measured requests | 0 / 512 measured requests |
| Readiness TTFB p95 at client concurrency 16 | 9,856.64 / 10,218.39 ms | 2,043.63 / 1,941.90 ms |
| Nginx request-time p50 / p95, Next upstream | 3 / 14 ms | 3 / 20 ms |
| Nginx upstream-response p50 / p95, Next | 3 / 14 ms | 3 / 20 ms |
| Nginx request-time p50 / p95, FastAPI upstream | 4 / 6 ms | 4 / 5 ms |
| Nginx upstream-response p50 / p95, FastAPI | 4 / 6 ms | 4 / 5 ms |
| FastAPI ASGI total p50 / p95 | 2.87 / 5.24 ms | 2.40 / 4.96 ms |
| Five-second cgroup CPU / memory sample | 0.086 cores / 534.1–535.6 MiB | 0.036 cores / 541.6–545.9 MiB |

Nginx aggregates contain 531 entries per configuration (including discovery and warmups): 398 Next upstream and 133 API upstream. ASGI logs contain 269 events, including internal Next auth probes. They are not paired one-to-one with benchmark requests; ASGI and upstream timing can include streaming/backpressure. Each CPU/memory observation is a five-second sample, not a peak or full-run average. A candidate PostgreSQL sample found four connections including the inspection connection, not a peak.

The baseline localhost benchmark inside the container bypassed Modal ingress and the external network: readiness at 16 clients had p95 49.69 ms and 224 requests/s. By contrast the public endpoint had p95 around 10 s and 1.5 requests/s. The nearly linear public waterfall, short internal timings and improvement from the bounded input setting provide strong evidence that one-at-a-time Modal input handling on the `us-east` routing → `ap-south` container path was a major bottleneck in this staging scenario. The instrumentation cannot precisely partition Modal queue time, ingress execution and network time, or establish the production deployment's actual region and queue behavior. It also does not measure the real browser waterfall.

Staging safety checks confirmed `/library` returns a private no-store 307 to session restoration, unauthenticated auth/analytics/private assets and an SSE endpoint return 401, and a real static CSS range returns 206 with the expected Content-Range. Focused local tests cover authentication redirects, authorized storage byte ranges, speaking playback and streaming message forwarding. A live authenticated private-media or SSE stream was not exercised. No Nginx buffering/cache, PostgreSQL pool, replica count, production region, GPU workload or production deployment was changed. Evaluate routing and geographically closer isolated deployments separately; do not move an existing PostgreSQL Volume merely for a latency test.
