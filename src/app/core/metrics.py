"""Phase 2 observability: Prometheus-compatible application metrics.

Logs vs. Metrics vs. Traces (see `docs/observability.md` for the full
writeup this module implements): logs answer "what happened?" for one
specific event, with as much detail as that event needs; metrics answer
"how often / how much / how slow?" in aggregate, cheaply, over the whole
process's lifetime; traces (not built yet -- explicitly out of scope for
this phase) would answer "where did *this one* request spend its time?"
across service boundaries. `request_id` (see `app.core.request_context`)
is a logging/correlation concept, not a metric: it identifies one
specific request, which is exactly the kind of unbounded, high-
cardinality value Prometheus's storage model is not designed to hold as
a label -- every distinct label combination becomes its own permanently-
retained time series, so a label that's different on every request would
mean a new time series per request, forever. Metrics stay aggregated by
design: `method`/`route`/`status_code` and `provider`/`model`/`operation`
are all drawn from small, fixed, developer-controlled sets (the
configured routes and the configured LLM provider/model list), never
from request content or generated IDs.

Uses the official `prometheus_client` library directly against its
default global `REGISTRY` -- no FastAPI-specific instrumentation
library (e.g. `prometheus-fastapi-instrumentator`): this app's request
lifecycle is already owned by `RequestContextMiddleware`, and recording
two counters/histograms there is a few lines, not enough to justify a
second abstraction layer over the same request path. Metric objects
below are created once, at import time, as module-level singletons --
never inside `create_app()` (called many times across this app's test
suite) or per-request, which is what keeps them safe against
`prometheus_client`'s "duplicated time series" error and what makes
values persist correctly across the whole process's lifetime, which is
the entire point of a counter.

Durations are recorded in seconds (Prometheus/OpenMetrics convention,
and what makes the default and below custom bucket boundaries meaningful
in PromQL), even though this codebase's structured logs deliberately use
milliseconds elsewhere (see `career_conversation_workflow.py` and the
LLM gateways) -- these are two different, intentionally-diverging
conventions for two different audiences, not an inconsistency to fix.

Bucket boundaries for both histograms below are widened well past
`prometheus_client`'s stock defaults (which top out at 10s): this
application's own logs have already shown a single LLM attempt taking
over 17 seconds (a free-tier OpenRouter model under load), and several
HTTP endpoints (`/analyze`, `/career-conversation`, `/tailoring-
suggestions`, `/interview-preparation`) call an LLM synchronously within
the request -- with the stock buckets, any real request slower than 10s
would silently collapse into the `+Inf` bucket, making a p95 estimate
meaningless for exactly the workload this app actually has.
"""

from collections.abc import Iterable

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request

_DURATION_BUCKETS: Iterable[float] = (
    0.05,
    0.1,
    0.25,
    0.5,
    1,
    2.5,
    5,
    10,
    15,
    20,
    30,
    45,
    60,
    float("inf"),
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests received, by method, route template, and status code.",
    ["method", "route", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds, by method and route template.",
    ["method", "route"],
    buckets=_DURATION_BUCKETS,
)

# One counter with a `status` label ("success"/"failure"), not three
# separate counters -- `llm_requests_total` summed across `status` is
# "total LLM requests"; filtered to `status="failure"` it's "failed LLM
# requests"; this is the standard Prometheus idiom for "total plus a
# breakdown" and can't drift out of sync with itself the way three
# independently-incremented counters could.
LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total LLM gateway calls, by provider, model, operation, and outcome.",
    ["provider", "model", "operation", "status"],
)

LLM_REQUEST_DURATION_SECONDS = Histogram(
    "llm_request_duration_seconds",
    "LLM gateway call duration in seconds, by provider, model, and operation.",
    ["provider", "model", "operation"],
    buckets=_DURATION_BUCKETS,
)

# The one path an unmatched request (a bad/bot/probing URL that hits no
# registered route) collapses onto -- the alternative, the raw request
# path, is exactly the unbounded/attacker-controlled label this module's
# docstring says metrics must never carry.
_UNMATCHED_ROUTE = "unmatched"


def route_label(request: Request) -> str:
    """Return the *route template* Starlette resolved for `request` (e.g.
    `/job-preparations/{job_preparation_id}`), or `"unmatched"` if no route matched.

    Only meaningful once routing has actually run -- `request.scope["route"]` is set by
    Starlette's router before the endpoint is invoked, so it's already present by the time a
    caller reaches this function from either branch of a `try/except` wrapped around
    `call_next`, success or a raised exception alike. Deliberately never falls back to
    `request.url.path`: an arbitrary/attacker-supplied path is exactly the kind of unbounded
    value that would make `route` a high-cardinality label.

    Note the label is `APIRoute.path` exactly as registered on its own router -- it does not
    include an ancestor `include_router(..., prefix="/v1")`'s prefix, even though that prefix is
    very much part of the real URL a client requests (this app's real routes are labeled
    `/job-preparations`, `/analyze`, etc., never `/v1/job-preparations`). This is standard
    FastAPI/Starlette behavior, not something this function adds or could easily change; it is
    still a small, fixed, developer-controlled set of values either way, so it stays safe as a
    label -- just be aware of it if you introduce a second versioned prefix (e.g. `/v2`) sharing
    route names with `/v1`, since their labels would then collide.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else _UNMATCHED_ROUTE


def record_http_request(
    *, method: str, route: str, status_code: str, elapsed_seconds: float
) -> None:
    """Record one completed (or failed) HTTP request against both HTTP metrics above."""
    HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status_code=status_code).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, route=route).observe(elapsed_seconds)


def record_llm_request(
    *, provider: str, model: str, operation: str, status: str, elapsed_seconds: float
) -> None:
    """Record one completed (or failed) LLM gateway call against both LLM metrics above."""
    LLM_REQUESTS_TOTAL.labels(
        provider=provider, model=model, operation=operation, status=status
    ).inc()
    LLM_REQUEST_DURATION_SECONDS.labels(
        provider=provider, model=model, operation=operation
    ).observe(elapsed_seconds)


# Deliberately not versioned under `/v1` (unlike the rest of this app's
# API -- see `app/api/v1/router.py`): `/metrics` is a fixed, unversioned
# path by Prometheus convention -- it's the default `metrics_path` every
# `scrape_config` assumes unless overridden, so putting it anywhere else
# is a small, easy-to-forget footgun for zero benefit. Mounted directly
# on the application in `app.py`, not through `api_router`.
router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Expose all registered metrics in Prometheus text exposition format for scraping."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
