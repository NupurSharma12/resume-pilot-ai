"""Request/correlation ID middleware: Phase 1 observability.

`RequestContextMiddleware` gives every request a `request_id` — reused
from the incoming `X-Request-ID` header when the caller supplies one
(letting an upstream proxy/gateway's own correlation ID survive end to
end), or generated fresh otherwise — and binds it into structlog's
context-local storage via `structlog.contextvars.bind_contextvars` for
the lifetime of the request. Binding it into context (rather than only
passing it explicitly to this module's own log calls) is what makes it
free: every log statement anywhere in the call stack for this request —
workflow, gateway, persistence — picks it up automatically via the
`merge_contextvars` processor already wired into `configure_logging`
(see `app/core/logging.py`), with no caller anywhere else needing to
know `request_id` exists.

Emits exactly three lifecycle events per request: `request_started`
(before the route runs), and then exactly one of `request_completed`
(any response, including a 4xx/5xx `HTTPException` — those are already
converted to a normal `Response` by Starlette's `ExceptionMiddleware`
before this middleware's `call_next` returns) or `request_failed` (an
exception that was *not* converted to a response anywhere downstream —
i.e. a genuinely unhandled exception). `request_failed` logs and
re-raises, never swallows: Starlette's `ServerErrorMiddleware` (always
outermost, wrapping every user middleware including this one) is left
completely untouched to produce its existing default 500 response
exactly as it did before this middleware existed. This is deliberate —
the point is to make `request_id` recoverable from the logs for an
unexpected failure, not to change what the caller receives.

Only request metadata is ever logged here: `method`, `path`,
`status_code`, `elapsed_ms`, `error_type` (a class name, never
`str(exc)`, which could echo request content back into logs) — never
headers, query params, or body content, matching this codebase's
existing no-content-logging policy (see `career_conversation_workflow`'s
module docstring for the same policy applied to LLM calls).
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds a per-request `request_id` into structlog context and logs the request's lifecycle."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        # `tokens` is what makes this safe under concurrent requests: each
        # request's own coroutine gets its own contextvars.Token, and
        # `reset_contextvars` below restores exactly the prior value for
        # this context only — never a blanket `clear_contextvars()`, which
        # would be correct here too (there is no outer request-scoped
        # context to preserve) but would silently stop being correct the
        # moment anything upstream of this middleware ever binds its own
        # contextvars.
        tokens = structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        # `request_id` is passed explicitly on all three lifecycle events
        # below, even though context binding above already makes it
        # appear on them (and on every other log statement for this
        # request) for free via the `merge_contextvars` processor -- these
        # three events are this module's own direct contract, so they
        # stay self-contained and correct even if a caller's processor
        # chain doesn't happen to include `merge_contextvars`.
        logger.info(
            "request_started", request_id=request_id, method=request.method, path=request.url.path
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                error_type=type(exc).__name__,
            )
            raise
        else:
            logger.info(
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            structlog.contextvars.reset_contextvars(**tokens)
