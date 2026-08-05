"""Unit tests for `OpenRouterGateway`, using `httpx.MockTransport` — no real network calls.

Each test swaps the gateway's internal `httpx.AsyncClient` for one wired
to a `MockTransport` handler, so the full `generate`/`generate_structured`
code path (payload construction, response parsing, status classification)
is exercised exactly as it would be against the real API, deterministically
and instantly.
"""

import json

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.gateways.llm.errors import PermanentGatewayError, TransientGatewayError
from app.gateways.llm.models import LLMRequest
from app.gateways.llm.openrouter_gateway import OpenRouterGateway, _classify_status


class _DummyResult(BaseModel):
    value: str
    count: int


def _make_gateway(handler, model: str | None = None) -> OpenRouterGateway:
    settings = Settings(
        openrouter_api_key="test-openrouter-key",
        **({"openrouter_model": model} if model else {}),
    )
    gateway = OpenRouterGateway(settings)
    gateway._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://openrouter.ai/api/v1"
    )
    return gateway


def _request() -> LLMRequest:
    return LLMRequest(
        system_prompt="You are a helpful assistant.",
        user_prompt="Say hello.",
        model="ignored-by-openrouter",
        temperature=0.5,
    )


async def test_generate_success_parses_response_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # Asserted against an explicit, test-owned model string (not
        # Settings' real default) so this test never breaks just because
        # OpenRouter retires whatever free model happens to be the
        # project's current default — see config.py's openrouter_model
        # docstring on why that default can go stale.
        assert body["model"] == "test/explicit-model:free"
        assert body["messages"] == [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello."},
        ]
        assert body["temperature"] == 0.5
        assert "response_format" not in body
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    gateway = _make_gateway(handler, model="test/explicit-model:free")
    response = await gateway.generate(_request())

    assert response.content == "Hello!"
    assert response.provider == "openrouter"
    assert response.finish_reason == "stop"
    assert response.usage is not None
    assert response.usage.total_tokens == 13


async def test_generate_structured_embeds_schema_and_requests_json_mode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        user_message = body["messages"][-1]["content"]
        assert "JSON Schema" in user_message
        assert "value" in user_message  # the schema's field names are embedded
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"value": "ok", "count": 2})}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            },
        )

    gateway = _make_gateway(handler)
    result = await gateway.generate_structured(_request(), _DummyResult)

    assert result == _DummyResult(value="ok", count=2)


async def test_generate_structured_invalid_json_raises_validation_error() -> None:
    """A response that doesn't match the schema fails validation, left unwrapped like Gemini's."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not valid json at all"}}]}
        )

    gateway = _make_gateway(handler)
    with pytest.raises(ValidationError):
        await gateway.generate_structured(_request(), _DummyResult)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_transient_status_codes_raise_transient_error(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "boom"})

    gateway = _make_gateway(handler)
    with pytest.raises(TransientGatewayError):
        await gateway.generate(_request())


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_permanent_status_codes_raise_permanent_error(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "boom"})

    gateway = _make_gateway(handler)
    with pytest.raises(PermanentGatewayError):
        await gateway.generate(_request())


async def test_network_error_raises_transient_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    gateway = _make_gateway(handler)
    with pytest.raises(TransientGatewayError):
        await gateway.generate(_request())


def test_classify_status_boundary_values() -> None:
    assert isinstance(_classify_status(429), TransientGatewayError)
    assert isinstance(_classify_status(408), TransientGatewayError)
    assert isinstance(_classify_status(500), TransientGatewayError)
    assert isinstance(_classify_status(599), TransientGatewayError)
    assert isinstance(_classify_status(400), PermanentGatewayError)
    assert isinstance(_classify_status(404), PermanentGatewayError)


def test_construction_requires_api_key() -> None:
    settings = Settings(openrouter_api_key=None)
    with pytest.raises(ValueError, match="openrouter_api_key is required"):
        OpenRouterGateway(settings)


def test_construction_uses_configured_model() -> None:
    settings = Settings(openrouter_api_key="key", openrouter_model="some/other-model:free")
    gateway = OpenRouterGateway(settings)
    assert gateway.provider_name == "openrouter"
    assert gateway.supports_structured_output is True
    assert gateway.supports_json_schema is False
