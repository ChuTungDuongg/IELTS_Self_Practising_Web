# Modal Web latency investigation

## Findings and limits

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

## Pending comparison and next steps

| Metric | Before | After |
| --- | --- | --- |
| GET / p50 / p95 | Not measured | Not measured |
| Ready p50 / p95 | Not measured | Not measured |
| Static asset p95 | Not measured | Not measured |
| Concurrent RPS / HTTP errors | Not measured | Not measured |
| Modal Web CPU / memory | Not measured | Not measured |

On a verified staging instance, establish the baseline before trying bounded class-level `@modal.concurrent(max_inputs=8)` or `16`. Keep `max_containers=1` and the existing database ownership guard. Compare reliability and tail latency, monitor CPU, memory and database connections, and revert a candidate that worsens them. Modal's default one-input setting remains unchanged in this revision because no safe deployment data is available to choose a value. Investigate actual geography and RTT separately, without moving the PostgreSQL volume or changing regions. Check API timings and query plans only if the observations identify backend or database cost.
