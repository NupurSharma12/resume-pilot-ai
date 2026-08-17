# Observability

## Status

Implemented: Phase 1 (request/correlation IDs + structured logging) and Phase 2 (application
metrics). Phase 3 (tracing, OpenTelemetry, a real metrics backend/dashboard) is deliberately not
started -- see "Deferred to Phase 3" at the bottom.

## Logs vs. Metrics vs. Traces

Three different questions, three different tools. Conflating them (e.g. trying to answer "how
often" by grepping logs, or trying to answer "what happened on this one request" from a counter)
is where most home-grown observability setups go wrong.

| | Question it answers | Example | Where it lives here |
|---|---|---|---|
| **Logs** | "What happened?" (for one specific event) | "This exact request, at this exact time, failed with `TransientGatewayError` after 17.4s, on model X." | `structlog`, stdout, JSON — see `app/core/logging.py` |
| **Metrics** | "How often / how much / how slow?" (aggregated, over time) | "We're making ~40 LLM calls/minute, 3% are failing, p95 latency is 8s." | Prometheus counters/histograms — see `app/core/metrics.py` |
| **Traces** | "Where did *this one* request spend its time, across every call it made?" | "This request spent 200ms in `/analyze`, 150ms of which was one Gemini call, 30ms in the DB." | **Not built yet** (Phase 3) |

Each is the right tool for a different scale and a different question:

- A **log line** is cheap to write, expensive to query in aggregate (you're grepping/scanning
  records), and carries arbitrary detail — free text, full context, one event at a time.
- A **metric** is the opposite trade: expensive to make flexible (every distinct label
  combination is a permanent, ongoing cost — see "Cardinality" below), but *extremely* cheap to
  query in aggregate — "what's the error rate over the last 5 minutes" is an O(1)-ish read against
  a counter, not a scan over every request that ever happened.
- A **trace** answers a question neither of the above can: not "what happened" or "how often", but
  "where, structurally, did the time inside *this specific* request actually go" — which matters
  once a request fans out across multiple services/calls and you need to see the whole tree, not
  just this process's own view of it. This app is still a single process talking to external LLM
  providers, so there's no multi-service call tree to visualize yet; that's the concrete trigger
  for actually adding tracing in Phase 3, not "traces are generally good practice."

## Why `request_id` belongs in logs, not metrics

`request_id` (Phase 1 — `app/core/request_context.py`) identifies **one specific request**. It is
exactly what makes logs useful for "what happened on this one request" (you can grep every log
line across every module for one `request_id` and reconstruct the whole story) — and exactly what
Prometheus's storage model cannot afford as a label. See "Cardinality" immediately below for why.

`request_id` is bound into `structlog`'s context (`structlog.contextvars`) for a request's
lifetime, so it appears on every log line for that request automatically, without every module
needing to know it exists. It never appears as a metric label anywhere in this codebase.

## Cardinality: why metric labels stay small and fixed

Every distinct combination of label values on a Prometheus metric becomes its own permanently
tracked time series in the metrics backend's storage. A counter with labels `{method, route,
status_code}` drawn from small, fixed sets (a handful of HTTP methods, a handful of registered
routes, a handful of status codes) stays at, at most, a few hundred time series for the whole
app — trivial. The same counter with a `request_id` label would mean a **new, permanent time
series for every single request the app has ever served** — millions of them, most useful for
approximately zero seconds, never expiring, silently degrading every metrics backend that has to
store and index them all. This is the textbook Prometheus cardinality trap, and it's exactly why
this app's metric labels are drawn only from:

- `method` — a handful of HTTP verbs.
- `route` — the *route template* FastAPI/Starlette resolved (e.g.
  `/job-preparations/{job_preparation_id}`), never the raw request path. Two different
  `job_preparation_id`s hitting the same route collapse onto one label value; an unmatched/bad/bot
  path collapses onto a fixed `"unmatched"` label, never onto whatever garbage path was requested.
  See `app.core.metrics.route_label`'s docstring for the exact mechanics and one caveat (route
  labels don't include an ancestor router's `prefix=`).
- `status_code` — a small, standard, fixed set of HTTP status codes.
- `provider` / `model` / `operation` — the *configured* LLM provider/model list
  (`Settings.primary_provider`/`secondary_provider`/`tertiary_provider`,
  `Settings.openrouter_models`) and the two gateway operations (`generate`/`generate_structured`)
  — all developer-controlled, all small, all fixed at deploy time, never derived from request
  content.
- `status` (LLM metrics only) — `"success"` or `"failure"`.

None of these ever come from request content, generated IDs, or free text. That's a deliberate
design constraint, not an oversight — every time a new label is proposed for either metric, the
question to ask is "is this drawn from a small, fixed, developer-controlled set, or could it grow
without bound?" If the latter, it belongs in a log field, not a metric label.

## Why metrics stay in-process/aggregated, not in Postgres

Metrics here are held entirely in-process, by `prometheus_client`'s default registry, and
exposed as a point-in-time text snapshot at `GET /metrics` for an external scraper to pull.
Nothing about this application's metrics touches its Postgres-backed persistence layer
(`app/persistence/`), and nothing should:

- **Different data, different lifecycle.** `app/persistence/` holds durable *product* data
  (`Resume`/`ResumeVersion`/`JobPreparation`) that must survive a restart and represents something
  a user did. Metrics are operational telemetry about the *process* — they're supposed to reset
  to zero on every restart (a counter that persisted across restarts and pretended to be
  continuous would misrepresent reality after a redeploy), and they represent nothing about any
  one user or request.
- **Different access pattern.** Prometheus's whole model is "pull an in-memory snapshot on a
  schedule, aggregate over time in the *scraper's* own storage" — not "write every event to a
  relational database and aggregate with SQL." Writing a `Counter.inc()` per request into Postgres
  would be a database write on every single request, purely to reconstruct a number this process
  already knows in memory for free.
- **Different failure mode.** If the metrics registry were somehow lost (a process restart), that's
  completely fine — a fresh process starts counting from zero. If it depended on a database write,
  a database outage would now also take down request handling (or metrics would silently stop being
  recorded) for no operational benefit.

## What Phase 2 actually added

**HTTP metrics** (`app/core/metrics.py`, recorded from `app/core/request_context.py`'s existing
`RequestContextMiddleware` — see below):

- `http_requests_total{method, route, status_code}` — a `Counter`.
- `http_request_duration_seconds{method, route}` — a `Histogram` (custom bucket boundaries up to
  60s — see "Bucket boundaries" below).

**LLM metrics** (`app/core/metrics.py`, recorded from `app/gateways/llm/gemini_gateway.py` and
`app/gateways/llm/openrouter_gateway.py`):

- `llm_requests_total{provider, model, operation, status}` — one `Counter`, `status` ∈
  `{"success", "failure"}`. Filtering to `status="failure"` gives "failed LLM requests"; summing
  across `status` gives "total LLM requests" — the standard Prometheus idiom for "a total plus a
  breakdown that can't drift out of sync with itself", instead of three separately-incremented
  counters.
- `llm_request_duration_seconds{provider, model, operation}` — a `Histogram`.

**`GET /metrics`** — Prometheus text exposition format, mounted directly on the application (not
under `/v1`, unlike every other route — see `app/core/metrics.py`'s module docstring for why: it's
the fixed, unversioned path every default Prometheus `scrape_config` assumes).

### Why this extends `RequestContextMiddleware` rather than adding a second middleware

Recording the two HTTP metrics needs exactly the same inputs, computed at exactly the same two
points, as the existing `request_completed`/`request_failed` logs: method, resolved route, status
code, elapsed time — read once in the success branch, once in the `except` branch. A second
`BaseHTTPMiddleware` wrapping every request again would duplicate that same
timing/try-except/route-resolution scaffolding for zero benefit — literally the same request,
timed twice, by two independent pieces of code that have to stay in sync with each other. Metrics
recording is a three-line addition (`record_http_request(...)`) to a method that already has every
input it needs, in both branches it needs it in. There was no genuine architectural need for a
separate middleware, so none was introduced.

### Why LLM metrics are recorded per-gateway, not in `GatewayChain`

`GatewayChain` (`app/gateways/llm/chain.py`) orchestrates fallback *across* providers but has no
visibility into which specific *model* served a call within a provider — that detail is private to
each concrete gateway (`OpenRouterGateway` tries an internal list of free models before ever
reporting back to `GatewayChain`; see that module's "Model-level fallback" docstring). Recording
metrics at `GatewayChain`'s level would mean losing the `model` dimension entirely for OpenRouter
calls — a real loss, since "which provider/model is failing" is an explicit goal of this phase, and
model-level free-tier reliability is a real, previously-observed issue for this app (see the
`nemotron-3-nano-30b` schema-validation failures in production logs that partly motivated this
phase). Instrumenting each concrete gateway (`GeminiGateway.generate`/`generate_structured`,
`OpenRouterGateway`'s shared `_call_with_model_fallback` attempt loop) instead gives full
provider+model+operation coverage with no loss of information and no `LLMGateway` interface
changes — every metric call sits directly next to a log call that already computes the exact same
inputs. `MockGateway` (pure in-memory fake, no real network call, no failure modes, used for local
dev/tests) is not instrumented — there's no real LLM activity there to measure.

### Bucket boundaries

Both duration histograms use custom bucket boundaries reaching to 60 seconds
(`0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 15, 20, 30, 45, 60, +Inf`), well past `prometheus_client`'s
stock defaults (which top out at 10s). This app's own logs have already shown a single LLM attempt
taking over 17 seconds (a free-tier OpenRouter model under load), and several HTTP endpoints
(`/analyze`, `/career-conversation`, `/tailoring-suggestions`, `/interview-preparation`) call an
LLM synchronously within the request. With the stock buckets, any real request slower than 10s
would silently collapse into the `+Inf` bucket, making a `histogram_quantile(0.95, ...)` p95
estimate in PromQL meaningless for exactly the workload this app actually has.

### Durations: seconds in metrics, milliseconds in logs

Metrics record duration in seconds (the Prometheus/OpenMetrics convention, and what makes the
bucket boundaries above meaningful in PromQL); this codebase's structured logs elsewhere
(`career_conversation_workflow.py`, the LLM gateways' own log calls) use milliseconds. This is two
intentionally-diverging conventions for two different audiences (a human reading `elapsed_ms:
147.3` in a log line vs. PromQL's own second-based functions), not an inconsistency to fix.

## Answering the motivating questions

- **How many LLM calls are we making?** `sum(llm_requests_total)`, or broken down by
  `provider`/`model` to see the mix.
- **How often are they failing?** `sum(rate(llm_requests_total{status="failure"}[5m])) /
  sum(rate(llm_requests_total[5m]))`.
- **Which provider/model is failing?** `sum by (provider, model) (rate(llm_requests_total{status="failure"}[5m]))`.
- **What is the average/p95-ish latency?** `histogram_quantile(0.95,
  rate(llm_request_duration_seconds_bucket[5m]))` (p95 across all provider/model/operation
  combinations; add `by (provider, model)` to the `rate(...)` to split it).
- **Which API endpoints are generating the most traffic?** `topk(10, sum by (route)
  (rate(http_requests_total[5m])))`.

(These are the PromQL queries a real Prometheus instance would run against `/metrics` — no
Prometheus server, Grafana, or dashboard is part of this repo yet; see "Deferred to Phase 3".)

## Deferred to Phase 3

Deliberately not built in this phase:

- **OpenTelemetry** — no traces, no OTel Collector, no span propagation across the app → LLM
  provider boundary. Worth adding once there's a real multi-hop call tree to visualize (or once
  correlating "this request → this specific LLM call → this specific retry attempt" across process
  boundaries becomes a recurring debugging need that logs + `request_id` genuinely can't answer).
- **Prometheus server / Grafana / any dashboard.** `/metrics` exposes data for something to scrape;
  nothing in this repo runs that scraper or renders a dashboard. Verified in this phase by reading
  `/metrics` directly (`pytest`, and a manual `curl`/`httpx` check), not by standing up real
  Prometheus infrastructure — unnecessary to prove the exposition format is correct.
- **Alerting** — no alert rules, no paging. Not meaningful without a real Prometheus/Alertmanager
  deployment to evaluate them.
- **A metrics persistence/database store.** See "Why metrics stay in-process/aggregated" above —
  this is a deliberate, permanent design position, not a temporary gap.
- **Business/product metrics** (e.g. "resumes analyzed per day", "tailoring plans generated") —
  Phase 2 is HTTP + LLM infrastructure metrics only, per this phase's explicit scope. Worth
  revisiting once there's an actual consumer (a dashboard, a report) that needs them.
