"""Tests for Phase 2 observability: Prometheus-compatible application metrics.

Every metric object in `app.core.metrics` is a process-level singleton
(created once at import time -- see that module's docstring for why),
so its value accumulates across this entire test session, not just
within one test. Every test here therefore reads a metric's value
*before* the action under test and asserts on the delta, never on an
absolute value -- the "avoid brittle tests... unrelated process-global
metric state" requirement this suite is built to satisfy. `_sample_value`
below is the one shared helper that makes this pattern short everywhere
it's used.

HTTP-metric tests drive a small standalone FastAPI app (the same pattern
`test_request_context_middleware.py` already established) so route
paths, 404s, and unhandled exceptions are all easy to trigger precisely
-- `test_wired_into_real_app` proves the real application actually
exposes `/metrics` and records real traffic.

LLM-metric tests reuse `test_openrouter_gateway.py`'s existing
`httpx.MockTransport` fixtures (`_make_gateway`/`_request`/`_ok_response`)
rather than re-inventing them -- the same "reuse an existing test's
collaborators" precedent `test_gateway_chain_logging.py` already
established for `test_gateway_chain.py`'s `FakeProvider`. Gemini's own
call is mocked directly on `gateway._client.aio.models.generate_content`,
the one seam `GeminiGateway` itself exposes for this.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from prometheus_client.parser import text_string_to_metric_families
from pydantic import BaseModel

from app.core.config import Settings
from app.core.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    LLM_REQUEST_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
)
from app.core.request_context import RequestContextMiddleware
from app.gateways.llm.errors import TransientGatewayError
from app.gateways.llm.gemini_gateway import GeminiGateway
from tests.test_openrouter_gateway import _make_gateway, _ok_response, _request


def _sample_value(metric, suffix: str = "", **labels: str) -> float:
    """Read one exact sample's current value from a `Counter`/`Histogram`, via the fully public
    `.collect()` API -- 0.0 if that exact label combination has never been recorded.

    `suffix` selects a histogram's derived series (`"_count"`/`"_sum"`),
    unused (default `""`) for a `Counter`. A `Counter` named e.g.
    `"http_requests_total"` is registered internally as `"http_requests"`
    (`prometheus_client` strips a trailing `_total` and re-adds it only
    when rendering -- see its `Counter` docs), so its one real sample name
    is `metric._name + "_total"`, not `metric._name` itself; a `Histogram`
    has no such stripping, so its sample names are simply
    `metric._name + suffix`.
    """
    target_name = metric._name + ("_total" if metric._type == "counter" else suffix)
    for family in metric.collect():
        for sample in family.samples:
            if sample.name == target_name and sample.labels == labels:
                return sample.value
    return 0.0


def _build_http_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/probe/{item_id}")
    async def probe(item_id: str) -> dict:
        return {"item_id": item_id}

    @app.get("/not-found")
    async def not_found() -> None:
        raise HTTPException(status_code=404, detail="Nope.")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("unexpected failure")

    return app


@pytest.fixture
async def http_client():
    transport = ASGITransport(app=_build_http_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# --- HTTP request metrics -------------------------------------------------


async def test_request_counter_increments_with_method_route_and_status_labels(
    http_client: AsyncClient,
) -> None:
    labels = {"method": "GET", "route": "/probe/{item_id}", "status_code": "200"}
    before = _sample_value(HTTP_REQUESTS_TOTAL, **labels)

    await http_client.get("/probe/abc-123")
    await http_client.get("/probe/xyz-789")

    after = _sample_value(HTTP_REQUESTS_TOTAL, **labels)
    assert after - before == 2


async def test_request_duration_is_recorded(http_client: AsyncClient) -> None:
    labels = {"method": "GET", "route": "/probe/{item_id}"}
    count_before = _sample_value(HTTP_REQUEST_DURATION_SECONDS, "_count", **labels)
    sum_before = _sample_value(HTTP_REQUEST_DURATION_SECONDS, "_sum", **labels)

    await http_client.get("/probe/timing-check")

    count_after = _sample_value(HTTP_REQUEST_DURATION_SECONDS, "_count", **labels)
    sum_after = _sample_value(HTTP_REQUEST_DURATION_SECONDS, "_sum", **labels)
    assert count_after - count_before == 1
    assert sum_after >= sum_before


async def test_4xx_response_is_counted_with_its_real_status_code(
    http_client: AsyncClient,
) -> None:
    labels = {"method": "GET", "route": "/not-found", "status_code": "404"}
    before = _sample_value(HTTP_REQUESTS_TOTAL, **labels)

    response = await http_client.get("/not-found")

    assert response.status_code == 404
    after = _sample_value(HTTP_REQUESTS_TOTAL, **labels)
    assert after - before == 1


async def test_unhandled_exception_still_produces_metrics_as_a_500(
    http_client: AsyncClient,
) -> None:
    """The existing safe HTTP error behavior (an unhandled exception -> a 500 response) must
    still get a metric recorded -- exactly like `RequestContextMiddleware`'s `request_failed`
    log, this happens in the `except` branch, not only on a clean return.
    """
    counter_labels = {"method": "GET", "route": "/boom", "status_code": "500"}
    duration_labels = {"method": "GET", "route": "/boom"}
    counter_before = _sample_value(HTTP_REQUESTS_TOTAL, **counter_labels)
    duration_count_before = _sample_value(
        HTTP_REQUEST_DURATION_SECONDS, "_count", **duration_labels
    )

    response = await http_client.get("/boom")

    assert response.status_code == 500
    assert _sample_value(HTTP_REQUESTS_TOTAL, **counter_labels) - counter_before == 1
    assert (
        _sample_value(HTTP_REQUEST_DURATION_SECONDS, "_count", **duration_labels)
        - duration_count_before
        == 1
    )


async def test_route_label_is_the_template_not_the_raw_path(http_client: AsyncClient) -> None:
    """Two different ids hitting the same route must be counted under one label combination
    (the route template), never as two separate high-cardinality label sets.
    """
    labels = {"method": "GET", "route": "/probe/{item_id}", "status_code": "200"}
    before = _sample_value(HTTP_REQUESTS_TOTAL, **labels)

    await http_client.get("/probe/first-distinct-id")
    await http_client.get("/probe/second-distinct-id")

    after = _sample_value(HTTP_REQUESTS_TOTAL, **labels)
    assert after - before == 2
    # Neither raw id ever became its own label combination.
    assert (
        _sample_value(
            HTTP_REQUESTS_TOTAL, method="GET", route="/probe/first-distinct-id", status_code="200"
        )
        == 0.0
    )


async def test_unmatched_path_gets_a_fixed_route_label_not_the_raw_path(
    http_client: AsyncClient,
) -> None:
    """An arbitrary/bot-probed URL that matches no route must collapse onto one fixed label,
    never become its own time series keyed by attacker-controlled input.
    """
    labels = {"method": "GET", "route": "unmatched", "status_code": "404"}
    before = _sample_value(HTTP_REQUESTS_TOTAL, **labels)

    await http_client.get("/this/path/does/not/exist/at/all")

    after = _sample_value(HTTP_REQUESTS_TOTAL, **labels)
    assert after - before == 1
    assert (
        _sample_value(
            HTTP_REQUESTS_TOTAL,
            method="GET",
            route="/this/path/does/not/exist/at/all",
            status_code="404",
        )
        == 0.0
    )


async def test_different_request_ids_never_create_different_label_combinations(
    http_client: AsyncClient,
) -> None:
    """`request_id` must never leak into a metric label -- two requests to the same route with
    different `X-Request-ID` headers must land in exactly the same single time series.
    """
    labels = {"method": "GET", "route": "/probe/{item_id}", "status_code": "200"}
    before = _sample_value(HTTP_REQUESTS_TOTAL, **labels)

    await http_client.get("/probe/same-route", headers={"X-Request-ID": "request-a"})
    await http_client.get("/probe/same-route", headers={"X-Request-ID": "request-b"})

    after = _sample_value(HTTP_REQUESTS_TOTAL, **labels)
    assert after - before == 2
    # Confirms the label set really is fixed to {method, route, status_code}
    # -- a `request_id` label would make this collection contain samples
    # whose label keys include "request_id", which it never does.
    for family in HTTP_REQUESTS_TOTAL.collect():
        for sample in family.samples:
            assert "request_id" not in sample.labels


# --- LLM metrics -----------------------------------------------------------


async def test_openrouter_success_records_llm_metrics_with_provider_model_operation() -> None:
    gateway = _make_gateway(lambda request: _ok_response("Hello!"), models=["test/model-a:free"])
    counter_labels = {
        "provider": "openrouter",
        "model": "test/model-a:free",
        "operation": "generate",
        "status": "success",
    }
    duration_labels = {
        "provider": "openrouter",
        "model": "test/model-a:free",
        "operation": "generate",
    }
    counter_before = _sample_value(LLM_REQUESTS_TOTAL, **counter_labels)
    duration_count_before = _sample_value(LLM_REQUEST_DURATION_SECONDS, "_count", **duration_labels)

    await gateway.generate(_request())

    assert _sample_value(LLM_REQUESTS_TOTAL, **counter_labels) - counter_before == 1
    assert (
        _sample_value(LLM_REQUEST_DURATION_SECONDS, "_count", **duration_labels)
        - duration_count_before
        == 1
    )


async def test_openrouter_transient_failure_records_a_failure_metric_per_model_then_succeeds() -> (
    None
):
    """A transient failure on the first model, followed by a successful fallback to the second,
    must record exactly one failure (for the first model) and one success (for the second) --
    never a single conflated outcome.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        if body["model"] == "test/flaky-model:free":
            return httpx.Response(503, json={"error": {"message": "Server busy."}})
        return _ok_response("Recovered.")

    gateway = _make_gateway(handler, models=["test/flaky-model:free", "test/reliable-model:free"])
    failure_labels = {
        "provider": "openrouter",
        "model": "test/flaky-model:free",
        "operation": "generate",
        "status": "failure",
    }
    success_labels = {
        "provider": "openrouter",
        "model": "test/reliable-model:free",
        "operation": "generate",
        "status": "success",
    }
    failure_before = _sample_value(LLM_REQUESTS_TOTAL, **failure_labels)
    success_before = _sample_value(LLM_REQUESTS_TOTAL, **success_labels)

    response = await gateway.generate(_request())

    assert response.content == "Recovered."
    assert _sample_value(LLM_REQUESTS_TOTAL, **failure_labels) - failure_before == 1
    assert _sample_value(LLM_REQUESTS_TOTAL, **success_labels) - success_before == 1


async def test_openrouter_permanent_failure_records_a_failure_metric() -> None:
    """A non-retryable failure (e.g. HTTP 401) still records a failed LLM request before
    propagating, even though it is never retried against another model.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key."}})

    gateway = _make_gateway(handler, models=["test/model-a:free"])
    failure_labels = {
        "provider": "openrouter",
        "model": "test/model-a:free",
        "operation": "generate",
        "status": "failure",
    }
    before = _sample_value(LLM_REQUESTS_TOTAL, **failure_labels)

    with pytest.raises(Exception):  # noqa: B017 -- PermanentGatewayError, re-raised unclassified here
        await gateway.generate(_request())

    assert _sample_value(LLM_REQUESTS_TOTAL, **failure_labels) - before == 1


class _StructuredResult(BaseModel):
    value: str


async def test_openrouter_generate_structured_uses_its_own_operation_label() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"value": "ok"}'}, "finish_reason": "stop"}]
            },
        )

    gateway = _make_gateway(handler, models=["test/model-a:free"])
    labels = {
        "provider": "openrouter",
        "model": "test/model-a:free",
        "operation": "generate_structured",
        "status": "success",
    }
    before = _sample_value(LLM_REQUESTS_TOTAL, **labels)

    await gateway.generate_structured(_request(), _StructuredResult)

    assert _sample_value(LLM_REQUESTS_TOTAL, **labels) - before == 1


def _fake_gemini_response(text: str = '{"value": "ok"}') -> SimpleNamespace:
    return SimpleNamespace(text=text, usage_metadata=None, candidates=[])


async def test_gemini_generate_success_records_llm_metrics() -> None:
    settings = Settings(gemini_api_key="test-gemini-key", gemini_model="test-gemini-model")
    gateway = GeminiGateway(settings)
    gateway._client.aio.models.generate_content = AsyncMock(return_value=_fake_gemini_response())
    labels = {
        "provider": "gemini",
        "model": "test-gemini-model",
        "operation": "generate",
        "status": "success",
    }
    before = _sample_value(LLM_REQUESTS_TOTAL, **labels)

    await gateway.generate(_request())

    assert _sample_value(LLM_REQUESTS_TOTAL, **labels) - before == 1


async def test_gemini_generate_failure_records_llm_metrics() -> None:
    settings = Settings(gemini_api_key="test-gemini-key", gemini_model="test-gemini-model")
    gateway = GeminiGateway(settings)
    gateway._client.aio.models.generate_content = AsyncMock(
        side_effect=httpx.ConnectError("connection reset")
    )
    labels = {
        "provider": "gemini",
        "model": "test-gemini-model",
        "operation": "generate",
        "status": "failure",
    }
    before = _sample_value(LLM_REQUESTS_TOTAL, **labels)

    with pytest.raises(TransientGatewayError):
        await gateway.generate(_request())

    assert _sample_value(LLM_REQUESTS_TOTAL, **labels) - before == 1


async def test_gemini_generate_structured_records_its_own_operation_label() -> None:
    settings = Settings(gemini_api_key="test-gemini-key", gemini_model="test-gemini-model")
    gateway = GeminiGateway(settings)
    gateway._client.aio.models.generate_content = AsyncMock(return_value=_fake_gemini_response())
    labels = {
        "provider": "gemini",
        "model": "test-gemini-model",
        "operation": "generate_structured",
        "status": "success",
    }
    before = _sample_value(LLM_REQUESTS_TOTAL, **labels)

    await gateway.generate_structured(_request(), _StructuredResult)

    assert _sample_value(LLM_REQUESTS_TOTAL, **labels) - before == 1


# --- /metrics endpoint -------------------------------------------------


async def test_metrics_endpoint_returns_valid_prometheus_text(client: AsyncClient) -> None:
    """`client` is the shared real-application fixture from `conftest.py` -- proves `/metrics`
    is actually mounted on the real app, not just testable via a standalone harness, and that
    its body genuinely parses as Prometheus exposition format (not merely "looks like text").
    """
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    families = {family.name for family in text_string_to_metric_families(response.text)}
    # Counter family names have their "_total" suffix stripped by both the
    # writer and this parser (OpenMetrics convention) -- the *sample*
    # names in the actual response text still read "http_requests_total"/
    # "llm_requests_total" (see `_sample_value`'s docstring).
    assert "http_requests" in families
    assert "http_request_duration_seconds" in families
    assert "llm_requests" in families
    assert "llm_request_duration_seconds" in families
    assert "http_requests_total" in response.text
    assert "llm_requests_total" in response.text


async def test_metrics_endpoint_reflects_real_traffic(client: AsyncClient) -> None:
    # `route` is `APIRoute.path` as registered on its own router --
    # Starlette/FastAPI does not retroactively fold an ancestor
    # `include_router(..., prefix="/v1")` into it, even though `/v1` is
    # very much part of the URL a client must actually request (verified
    # directly: hitting anything other than `/v1/job-preparations` 404s).
    # This is standard FastAPI route-template behavior, not something
    # this module changes -- see `route_label`'s docstring.
    labels = {"method": "GET", "route": "/job-preparations", "status_code": "200"}
    before = _sample_value(HTTP_REQUESTS_TOTAL, **labels)

    response = await client.get("/v1/job-preparations")
    assert response.status_code == 200
    response = await client.get("/metrics")

    after = _sample_value(HTTP_REQUESTS_TOTAL, **labels)
    assert after - before == 1

    families = list(text_string_to_metric_families(response.text))
    # Family name has "_total" stripped (see `_sample_value`'s docstring);
    # the individual sample names inside it still read "..._total".
    http_requests_family = next(f for f in families if f.name == "http_requests")
    matching = [
        s
        for s in http_requests_family.samples
        if s.name == "http_requests_total" and s.labels == labels
    ]
    assert len(matching) == 1
    assert matching[0].value == after
