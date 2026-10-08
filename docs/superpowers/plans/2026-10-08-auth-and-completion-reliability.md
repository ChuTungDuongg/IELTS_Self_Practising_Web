# Auth and Writing completion reliability

Starting point: 7a23d5b88fe17efd64c2443892dbc42c5fff3d47; clean local main.
Implement the supplied two-bug specification without changing refresh security,
IELTS guidance, Task 1 perception, or T1-B/T1-C evaluation semantics.

1. Confirm both existing refresh owners and the provider's current output schema
   and caps. Inspect backend one-time token rotation and existing concurrency tests.
2. Add failing frontend regressions for proxy 401 restoration, single refresh
   ownership, loading/authenticated login guards, safe destinations, full replacement
   navigation, restoration failure, and protected sidebar prefetch. Preserve logout.
   Implement a shared destination helper and an unprotected restoration route using
   the existing browser API client. Proxy checks access only and never rotates tokens.
3. Add failing backend tests at actual completion request boundaries. Introduce
   typed CompletionOptions with optional max_tokens; keep adapter parameter names
   inside providers. Give evidence and scoring separate bounded budgets, with larger
   headroom only on a length-specific bounded repair. Preserve all validation rules
   and historical persisted scoring DTOs; inference requests use only four score fields.
4. Forward options through existing evaluation instrumentation and update fake
   providers for the interface without changing benchmark identity or scoring rules.
   Verify success uses one scoring call, length failure uses at most two, and other
   repairs do not gain length headroom.
5. Run focused frontend auth/proxy/restoration tests, typecheck, targeted ESLint;
   focused backend auth/concurrency, MTS/provider, Task 1 and Task 2 regressions;
   exact CI Ruff lint/format commands and git diff --check. Independently review the
   combined diff. No browser, Playwright, real GPU requests, full benchmark, or push.

Frontend and backend implementation are delegated independently. The parent
owns integration review and verification, including unchanged refresh concurrency.

Review focus: access 401 versus transient failures; unsafe destinations and restore
loops; no Login form while session state is unresolved/authenticated; length retry
versus semantic repair; actual guided provider schema and all completion wrappers.
