"""Tests for `RequestContextMiddleware` -- Phase 1 observability's request/correlation ID layer.

Drives a small standalone FastAPI app (not the full `create_app()`
application) with `RequestContextMiddleware` as its only middleware, so
these tests exercise the middleware in isolation from CORS/routing/
persistence concerns. `test_wired_into_real_app` at the bottom is the one
exception -- it proves the middleware is actually mounted on the real
application, using the shared `client`/`settings` fixtures from
`conftest.py`.

Lifecycle-event assertions (`request_started`/`request_completed`/
`request_failed`) monkeypatch `app.core.request_context.logger` directly
with `_RecordingLogger`, the same pattern `test_app_lifespan.py` and
`test_llm_gateway_factory.py` already establish -- see `_RecordingLogger`'s
docstring for why `structlog.testing.capture_logs()` can't be trusted
here: `cache_logger_on_first_use=True` (set by `configure_logging`, which
many other tests in this suite trigger via `create_app`/the shared
`client` fixture) freezes a module-level logger the first time it's ever
used anywhere in the process to whichever processors were active *then*
-- and since this middleware is now wired into the real app, plenty of
other test files' real requests reach it well before this file runs.
Because `request_id` is passed explicitly to all three lifecycle events
(see `RequestContextMiddleware.dispatch`), monkeypatching the logger
still lets these tests assert on it directly, with no dependency on
structlog's processor pipeline actually running.

Context-binding assertions (does `request_id` actually reach an arbitrary
downstream log call, does it leak across concurrent requests, is it
cleared afterward) instead inspect `structlog.contextvars.get_contextvars()`
directly from inside route handlers -- the underlying fact ("is this
contextvar bound to this value in this request's context") is what
actually matters, and checking it directly sidesteps the same logger-
caching fragility entirely, rather than depending on any particular
logger's frozen render pipeline to surface it.
"""

import asyncio
import uuid

import pytest
import structlog
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.request_context import REQUEST_ID_HEADER, RequestContextMiddleware


class _RecordingLogger:
    """A minimal stand-in for `request_context.py`'s module-level structlog logger.

    See this module's docstring for why monkeypatching, not
    `capture_logs()`, is what reliably works here.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.calls.append({"event": event, **kwargs})

    def error(self, event: str, **kwargs: object) -> None:
        self.calls.append({"event": event, **kwargs})


def _build_app(*, context_probe: list[dict] | None = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ok")
    async def ok() -> dict:
        return {"status": "ok"}

    @app.get("/not-found")
    async def not_found() -> None:
        raise HTTPException(status_code=404, detail="Nope.")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("unexpected failure")

    @app.get("/probe/{n}")
    async def probe(n: int) -> dict:
        # Only n=0 sleeps -- gives n=1 room to race ahead first, which is
        # what makes the concurrency test a faithful check of context
        # isolation rather than something that would pass even with a
        # single shared/global request_id.
        if n == 0:
            await asyncio.sleep(0.05)
        if context_probe is not None:
            context_probe.append({"n": n, **structlog.contextvars.get_contextvars()})
        return {"n": n}

    return app


@pytest.fixture
def context_probe() -> list[dict]:
    return []


@pytest.fixture
def app(context_probe: list[dict]) -> FastAPI:
    return _build_app(context_probe=context_probe)


@pytest.fixture
async def probe_client(app: FastAPI):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def fake_logger(monkeypatch: pytest.MonkeyPatch) -> _RecordingLogger:
    logger = _RecordingLogger()
    monkeypatch.setattr("app.core.request_context.logger", logger)
    return logger


def _events(calls: list[dict], event: str) -> list[dict]:
    return [entry for entry in calls if entry.get("event") == event]


# --- Request ID generation/propagation ---------------------------------


async def test_generates_a_request_id_when_none_is_supplied(probe_client: AsyncClient) -> None:
    response = await probe_client.get("/ok")

    assert response.status_code == 200
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id is not None
    # A real UUID4 -- proves it was generated, not just any non-empty string.
    uuid.UUID(request_id)


async def test_preserves_an_incoming_request_id(probe_client: AsyncClient) -> None:
    response = await probe_client.get("/ok", headers={REQUEST_ID_HEADER: "client-supplied-id"})

    assert response.status_code == 200
    assert response.headers.get(REQUEST_ID_HEADER) == "client-supplied-id"


async def test_generates_a_fresh_id_when_the_incoming_header_is_blank(
    probe_client: AsyncClient,
) -> None:
    """An empty header value is treated the same as no header at all -- never propagated as-is."""
    response = await probe_client.get("/ok", headers={REQUEST_ID_HEADER: ""})

    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id
    uuid.UUID(request_id)


async def test_two_requests_without_a_supplied_id_get_different_ids(
    probe_client: AsyncClient,
) -> None:
    first = await probe_client.get("/ok")
    second = await probe_client.get("/ok")

    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


# --- structlog context binding / isolation ------------------------------


async def test_request_id_is_bound_into_context_for_the_whole_request(
    probe_client: AsyncClient, context_probe: list[dict]
) -> None:
    """`request_id` reaches `structlog.contextvars.get_contextvars()` from inside an ordinary
    route handler -- proof this is real context binding, not just a field this module's own
    log calls pass explicitly.
    """
    response = await probe_client.get("/probe/0", headers={REQUEST_ID_HEADER: "handler-visible-id"})

    assert response.status_code == 200
    assert len(context_probe) == 1
    assert context_probe[0]["request_id"] == "handler-visible-id"


async def test_context_does_not_leak_between_concurrent_requests(
    probe_client: AsyncClient, context_probe: list[dict]
) -> None:
    await asyncio.gather(probe_client.get("/probe/0"), probe_client.get("/probe/1"))

    assert len(context_probe) == 2
    by_n = {entry["n"]: entry["request_id"] for entry in context_probe}
    # Two distinct, real request ids -- if context had leaked between the
    # two concurrent requests, both entries would carry the same id.
    assert by_n[0] != by_n[1]
    uuid.UUID(by_n[0])
    uuid.UUID(by_n[1])


async def test_context_is_cleared_after_the_request_completes(probe_client: AsyncClient) -> None:
    """`request_id` must not leak into logging that happens outside any request."""
    await probe_client.get("/ok", headers={REQUEST_ID_HEADER: "should-not-leak"})

    assert "request_id" not in structlog.contextvars.get_contextvars()


async def test_context_is_cleared_even_when_the_request_fails(probe_client: AsyncClient) -> None:
    await probe_client.get("/boom", headers={REQUEST_ID_HEADER: "should-not-leak-either"})

    assert "request_id" not in structlog.contextvars.get_contextvars()


# --- Lifecycle logging: request_started / request_completed / request_failed ---


async def test_successful_request_logs_started_then_completed(
    probe_client: AsyncClient, fake_logger: _RecordingLogger
) -> None:
    response = await probe_client.get("/ok", headers={REQUEST_ID_HEADER: "lifecycle-success-id"})

    assert response.status_code == 200
    assert [call["event"] for call in fake_logger.calls] == ["request_started", "request_completed"]

    started, completed = fake_logger.calls
    assert started["method"] == "GET"
    assert started["path"] == "/ok"
    assert started["request_id"] == "lifecycle-success-id"

    assert completed["method"] == "GET"
    assert completed["path"] == "/ok"
    assert completed["status_code"] == 200
    assert isinstance(completed["elapsed_ms"], float)
    assert completed["request_id"] == "lifecycle-success-id"


async def test_handled_http_exception_logs_completed_not_failed(
    probe_client: AsyncClient, fake_logger: _RecordingLogger
) -> None:
    """A 404 raised via `HTTPException` is the existing, expected/safe error path -- it must
    log as a normal completion (with its real status code), never as `request_failed`.
    """
    response = await probe_client.get("/not-found")

    assert response.status_code == 404
    assert _events(fake_logger.calls, "request_failed") == []
    completed = _events(fake_logger.calls, "request_completed")
    assert len(completed) == 1
    assert completed[0]["status_code"] == 404


async def test_unexpected_exception_logs_failed_with_request_id_and_reraises(
    probe_client: AsyncClient, fake_logger: _RecordingLogger
) -> None:
    response = await probe_client.get("/boom", headers={REQUEST_ID_HEADER: "failure-id"})

    # The existing safe API error behavior: FastAPI's default handler for
    # an unhandled exception, completely untouched by this middleware.
    assert response.status_code == 500

    assert _events(fake_logger.calls, "request_completed") == []
    failed = _events(fake_logger.calls, "request_failed")
    assert len(failed) == 1
    assert failed[0]["request_id"] == "failure-id"
    assert failed[0]["method"] == "GET"
    assert failed[0]["path"] == "/boom"
    assert failed[0]["error_type"] == "RuntimeError"
    assert isinstance(failed[0]["elapsed_ms"], float)
    # Never the exception message itself -- only its type name.
    assert "unexpected failure" not in str(failed[0])


async def test_unexpected_exception_never_logged_as_request_completed(
    probe_client: AsyncClient, fake_logger: _RecordingLogger
) -> None:
    await probe_client.get("/boom")

    assert [call["event"] for call in fake_logger.calls] == ["request_started", "request_failed"]


# --- Wired into the real application ------------------------------------


async def test_wired_into_real_app(client: AsyncClient) -> None:
    """Confirms the middleware is actually mounted on `create_app()`'s app, not just testable
    in isolation -- hits a real, existing endpoint and checks the response header round-trips.
    """
    response = await client.get("/v1/job-preparations", headers={REQUEST_ID_HEADER: "real-app-id"})

    assert response.status_code == 200
    assert response.headers.get(REQUEST_ID_HEADER) == "real-app-id"
