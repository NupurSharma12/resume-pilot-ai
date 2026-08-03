"""Unit tests for `GatewayChain` — the core of Multi-LLM Resilience.

Uses small in-test fake providers (not real `GeminiGateway`/
`OpenRouterGateway`/`MockGateway` instances) so every scenario is
deterministic and instant: no network, no SDK mocking, just controllable
`LLMGateway`-shaped objects that raise exactly what each scenario needs.
"""

from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from app.gateways.llm.chain import GatewayChain
from app.gateways.llm.errors import (
    GatewayChainExhaustedError,
    PermanentGatewayError,
    TransientGatewayError,
)
from app.gateways.llm.models import LLMRequest, LLMResponse


class _DummyResult(BaseModel):
    value: str


class FakeProvider:
    """A controllable `LLMGateway`: succeeds, raises, or is unsupported, per scenario."""

    def __init__(
        self,
        name: str,
        *,
        supports_structured_output: bool = True,
        supports_json_schema: bool = True,
        generate_error: Exception | None = None,
        structured_error: Exception | None = None,
        generate_result: LLMResponse | None = None,
        structured_result: BaseModel | None = None,
    ) -> None:
        self._name = name
        self._supports_structured_output = supports_structured_output
        self._supports_json_schema = supports_json_schema
        self._generate_error = generate_error
        self._structured_error = structured_error
        self._generate_result = generate_result or LLMResponse(
            content=f"response from {name}",
            provider=name,
            model="fake-model",
            usage=None,
            cost=None,
            latency_ms=1.0,
            finish_reason="stop",
        )
        self._structured_result = structured_result or _DummyResult(value=name)
        self.generate_calls = 0
        self.structured_calls = 0

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def supports_structured_output(self) -> bool:
        return self._supports_structured_output

    @property
    def supports_json_schema(self) -> bool:
        return self._supports_json_schema

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.generate_calls += 1
        if self._generate_error:
            raise self._generate_error
        return self._generate_result

    async def generate_structured(self, request: LLMRequest, response_model):
        self.structured_calls += 1
        if self._structured_error:
            raise self._structured_error
        return self._structured_result

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError("Unused in these tests.")


def _request() -> LLMRequest:
    return LLMRequest(user_prompt="irrelevant", model="fake-model", temperature=0.0)


async def test_gemini_succeeds() -> None:
    """The primary provider succeeding returns its result without touching anyone else."""
    gemini = FakeProvider("gemini")
    openrouter = FakeProvider("openrouter")
    chain = GatewayChain([gemini, openrouter])

    result = await chain.generate(_request())

    assert result.content == "response from gemini"
    assert gemini.generate_calls == 1
    assert openrouter.generate_calls == 0


async def test_gemini_fails_openrouter_succeeds() -> None:
    """A transient Gemini failure falls back to OpenRouter, which succeeds."""
    gemini = FakeProvider(
        "gemini", generate_error=TransientGatewayError("Gemini rate limited (429).")
    )
    openrouter = FakeProvider("openrouter")
    chain = GatewayChain([gemini, openrouter])

    result = await chain.generate(_request())

    assert result.content == "response from openrouter"
    assert gemini.generate_calls == 1
    assert openrouter.generate_calls == 1


async def test_gemini_timeout_openrouter_succeeds() -> None:
    """A Gemini timeout is exactly as retryable as any other transient failure."""
    gemini = FakeProvider(
        "gemini", generate_error=TransientGatewayError("Gemini network error: TimeoutException.")
    )
    openrouter = FakeProvider("openrouter")
    chain = GatewayChain([gemini, openrouter])

    result = await chain.generate(_request())

    assert result.content == "response from openrouter"
    assert gemini.generate_calls == 1
    assert openrouter.generate_calls == 1


async def test_both_fail_mock_succeeds() -> None:
    """Two consecutive transient failures still fall all the way through to the third provider."""
    gemini = FakeProvider("gemini", generate_error=TransientGatewayError("Gemini 503."))
    openrouter = FakeProvider("openrouter", generate_error=TransientGatewayError("OpenRouter 503."))
    mock = FakeProvider("mock")
    chain = GatewayChain([gemini, openrouter, mock])

    result = await chain.generate(_request())

    assert result.content == "response from mock"
    assert gemini.generate_calls == 1
    assert openrouter.generate_calls == 1
    assert mock.generate_calls == 1


async def test_non_retryable_error_stops_immediately() -> None:
    """A PermanentGatewayError (e.g. a 401) must not fall back to the next provider."""
    gemini = FakeProvider(
        "gemini", generate_error=PermanentGatewayError("Gemini client error (HTTP 401).")
    )
    openrouter = FakeProvider("openrouter")
    chain = GatewayChain([gemini, openrouter])

    with pytest.raises(PermanentGatewayError):
        await chain.generate(_request())

    assert gemini.generate_calls == 1
    assert openrouter.generate_calls == 0


async def test_unclassified_error_also_stops_immediately() -> None:
    """An exception a provider failed to classify (not a GatewayError at all) stops the chain too.

    Not every non-retryable failure needs to be an explicit
    `PermanentGatewayError` — a raw, unclassified exception (e.g. a
    `pydantic.ValidationError` from a malformed-schema response) must
    stop the chain too, not silently fall through to the next provider.
    """
    gemini = FakeProvider("gemini", generate_error=ValueError("Something unexpected broke."))
    openrouter = FakeProvider("openrouter")
    chain = GatewayChain([gemini, openrouter])

    with pytest.raises(ValueError, match="Something unexpected broke."):
        await chain.generate(_request())

    assert gemini.generate_calls == 1
    assert openrouter.generate_calls == 0


async def test_all_providers_exhausted_raises() -> None:
    """When every provider fails transiently, the chain raises its own terminal error."""
    gemini = FakeProvider("gemini", generate_error=TransientGatewayError("Gemini 429."))
    openrouter = FakeProvider("openrouter", generate_error=TransientGatewayError("OpenRouter 429."))
    chain = GatewayChain([gemini, openrouter])

    with pytest.raises(GatewayChainExhaustedError):
        await chain.generate(_request())

    assert gemini.generate_calls == 1
    assert openrouter.generate_calls == 1


async def test_generate_structured_skips_provider_without_support() -> None:
    """A provider that can't do structured output at all is skipped, not attempted and failed."""
    unsupported = FakeProvider("legacy", supports_structured_output=False)
    capable = FakeProvider("gemini")
    chain = GatewayChain([unsupported, capable])

    result = await chain.generate_structured(_request(), _DummyResult)

    assert result.value == "gemini"
    assert unsupported.structured_calls == 0
    assert capable.structured_calls == 1


async def test_generate_structured_falls_back_on_transient_failure() -> None:
    gemini = FakeProvider(
        "gemini", structured_error=TransientGatewayError("Gemini quota exceeded.")
    )
    mock = FakeProvider("mock")
    chain = GatewayChain([gemini, mock])

    result = await chain.generate_structured(_request(), _DummyResult)

    assert result.value == "mock"
    assert gemini.structured_calls == 1
    assert mock.structured_calls == 1


def test_empty_chain_raises_immediately() -> None:
    with pytest.raises(ValueError, match="at least one gateway"):
        GatewayChain([])


def test_provider_name_lists_every_provider_in_order() -> None:
    chain = GatewayChain([FakeProvider("gemini"), FakeProvider("openrouter"), FakeProvider("mock")])
    assert chain.provider_name == "chain[gemini,openrouter,mock]"


def test_supports_structured_output_true_if_any_provider_supports_it() -> None:
    unsupported = FakeProvider("legacy", supports_structured_output=False)
    chain = GatewayChain([unsupported, FakeProvider("gemini")])
    assert chain.supports_structured_output is True


def test_stream_not_implemented() -> None:
    chain = GatewayChain([FakeProvider("gemini")])
    with pytest.raises(NotImplementedError):
        chain.stream(_request())
