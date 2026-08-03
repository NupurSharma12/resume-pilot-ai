"""Tests for `GatewayChain`'s structured logging: observability only, no retry logic asserted here.

Uses `structlog.testing.capture_logs()`, the standard way to assert on
structlog output regardless of the configured renderer/processors — each
captured entry is a plain dict of `{"event": ..., **bound_kwargs}`, so
these tests check exact event names and field presence without caring
whether logs are ultimately rendered as JSON or console output.

Reuses `FakeProvider`/`_request` from `test_gateway_chain.py` rather than
redefining them, so these tests exercise the exact same fake-provider
shape the functional chain tests already do.
"""

import pytest
from structlog.testing import capture_logs

from app.gateways.llm.chain import GatewayChain
from app.gateways.llm.errors import (
    GatewayChainExhaustedError,
    PermanentGatewayError,
    TransientGatewayError,
)
from app.gateways.llm.models import LLMRequest
from tests.test_gateway_chain import FakeProvider, _DummyResult, _request


def _events(logs: list[dict], event: str) -> list[dict]:
    return [entry for entry in logs if entry.get("event") == event]


async def test_first_attempt_success_logs_started_and_succeeded_only() -> None:
    gemini = FakeProvider("gemini")
    chain = GatewayChain([gemini])

    with capture_logs() as logs:
        await chain.generate(_request())

    started = _events(logs, "gateway_attempt_started")
    succeeded = _events(logs, "gateway_attempt_succeeded")
    assert len(started) == 1
    assert started[0]["provider"] == "gemini"
    assert started[0]["attempt"] == 1
    assert len(succeeded) == 1
    assert succeeded[0]["provider"] == "gemini"
    assert succeeded[0]["attempt"] == 1
    assert "elapsed_ms" in succeeded[0]

    # A single, immediately-successful provider never switched from anyone.
    assert _events(logs, "gateway_fallback") == []
    assert _events(logs, "gateway_attempt_failed_transient") == []
    assert _events(logs, "gateway_chain_failed") == []


async def test_transient_failure_then_success_logs_full_sequence() -> None:
    gemini = FakeProvider("gemini", generate_error=TransientGatewayError("Gemini rate limited."))
    openrouter = FakeProvider("openrouter")
    chain = GatewayChain([gemini, openrouter])

    with capture_logs() as logs:
        await chain.generate(_request())

    events_in_order = [entry["event"] for entry in logs]
    assert events_in_order == [
        "gateway_attempt_started",
        "gateway_attempt_failed_transient",
        "gateway_fallback",
        "gateway_attempt_started",
        "gateway_attempt_succeeded",
        "gateway_chain_summary",
    ]

    failed = _events(logs, "gateway_attempt_failed_transient")[0]
    assert failed["provider"] == "gemini"
    assert failed["attempt"] == 1
    assert failed["error_type"] == "TransientGatewayError"
    assert failed["error"] == "Gemini rate limited."
    assert "elapsed_ms" in failed

    fallback = _events(logs, "gateway_fallback")[0]
    assert fallback["from_provider"] == "gemini"
    assert fallback["to_provider"] == "openrouter"

    second_started = _events(logs, "gateway_attempt_started")[1]
    assert second_started["provider"] == "openrouter"
    assert second_started["attempt"] == 2

    succeeded = _events(logs, "gateway_attempt_succeeded")[0]
    assert succeeded["provider"] == "openrouter"
    assert succeeded["attempt"] == 2


async def test_permanent_failure_logs_failed_permanent_and_no_fallback() -> None:
    gemini = FakeProvider(
        "gemini", generate_error=PermanentGatewayError("Gemini client error (HTTP 401).")
    )
    openrouter = FakeProvider("openrouter")
    chain = GatewayChain([gemini, openrouter])

    with capture_logs() as logs, pytest.raises(PermanentGatewayError):
        await chain.generate(_request())

    failed = _events(logs, "gateway_attempt_failed_permanent")
    assert len(failed) == 1
    assert failed[0]["provider"] == "gemini"
    assert failed[0]["attempt"] == 1
    assert failed[0]["error_type"] == "PermanentGatewayError"
    assert failed[0]["error"] == "Gemini client error (HTTP 401)."

    # No fallback attempted, and openrouter never even started.
    assert _events(logs, "gateway_fallback") == []
    started_providers = [e["provider"] for e in _events(logs, "gateway_attempt_started")]
    assert started_providers == ["gemini"]


async def test_all_providers_fail_logs_chain_failed_with_providers_tried() -> None:
    gemini = FakeProvider("gemini", generate_error=TransientGatewayError("Gemini 503."))
    openrouter = FakeProvider("openrouter", generate_error=TransientGatewayError("OpenRouter 503."))
    chain = GatewayChain([gemini, openrouter])

    with capture_logs() as logs, pytest.raises(GatewayChainExhaustedError):
        await chain.generate(_request())

    failed = _events(logs, "gateway_chain_failed")
    assert len(failed) == 1
    assert failed[0]["providers_tried"] == ["gemini", "openrouter"]
    assert failed[0]["attempts"] == 2
    assert failed[0]["fallback_count"] == 2
    assert isinstance(failed[0]["total_elapsed_ms"], float)

    # No success summary was ever emitted for a run that never succeeded.
    assert _events(logs, "gateway_chain_summary") == []


async def test_successful_run_logs_chain_summary_with_counters() -> None:
    gemini = FakeProvider("gemini", generate_error=TransientGatewayError("Gemini 503."))
    openrouter = FakeProvider("openrouter")
    chain = GatewayChain([gemini, openrouter])

    with capture_logs() as logs:
        await chain.generate(_request())

    summary = _events(logs, "gateway_chain_summary")
    assert len(summary) == 1
    assert summary[0]["providers_tried"] == ["gemini", "openrouter"]
    assert summary[0]["successful_provider"] == "openrouter"
    assert summary[0]["attempts"] == 2
    assert summary[0]["fallback_count"] == 1
    assert isinstance(summary[0]["total_elapsed_ms"], float)

    # Exactly one terminal event for a successful run -- no failure summary.
    assert _events(logs, "gateway_chain_failed") == []


async def test_first_attempt_success_logs_summary_with_zero_fallbacks() -> None:
    gemini = FakeProvider("gemini")
    chain = GatewayChain([gemini])

    with capture_logs() as logs:
        await chain.generate(_request())

    summary = _events(logs, "gateway_chain_summary")[0]
    assert summary["providers_tried"] == ["gemini"]
    assert summary["successful_provider"] == "gemini"
    assert summary["attempts"] == 1
    assert summary["fallback_count"] == 0


async def test_skipped_provider_does_not_break_fallback_pairing() -> None:
    """A skipped (unsupported) provider in between two attempts isn't logged as a fallback hop."""
    gemini = FakeProvider(
        "gemini", structured_error=TransientGatewayError("Gemini quota exceeded.")
    )
    unsupported = FakeProvider("legacy", supports_structured_output=False)
    mock = FakeProvider("mock")
    chain = GatewayChain([gemini, unsupported, mock])

    with capture_logs() as logs:
        await chain.generate_structured(_request(), _DummyResult)

    skipped = _events(logs, "gateway_chain_provider_skipped")
    assert len(skipped) == 1
    assert skipped[0]["provider"] == "legacy"

    fallback = _events(logs, "gateway_fallback")
    assert len(fallback) == 1
    assert fallback[0]["from_provider"] == "gemini"
    assert fallback[0]["to_provider"] == "mock"

    # The skipped provider never consumed an attempt number.
    started = _events(logs, "gateway_attempt_started")
    assert [(e["provider"], e["attempt"]) for e in started] == [("gemini", 1), ("mock", 2)]


async def test_no_prompt_or_user_content_in_any_log_field() -> None:
    """Every logged value must be plain metadata -- never the request/response content itself."""
    secret_prompt = "The candidate's SSN is 123-45-6789 and their salary is $999,999."
    gemini = FakeProvider("gemini", generate_error=TransientGatewayError("Gemini 429."))
    mock = FakeProvider("mock")
    chain = GatewayChain([gemini, mock])

    request = LLMRequest(user_prompt=secret_prompt, model="fake-model", temperature=0.0)

    with capture_logs() as logs:
        await chain.generate(request)

    for entry in logs:
        for value in entry.values():
            assert secret_prompt not in str(value)
