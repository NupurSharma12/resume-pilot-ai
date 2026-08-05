"""Unit tests for `OpenRouterGateway`, using `httpx.MockTransport` — no real network calls.

Each test swaps the gateway's internal `httpx.AsyncClient` for one wired
to a `MockTransport` handler, so the full `generate`/`generate_structured`
code path (payload construction, response parsing, status classification,
and — the focus of most tests here — model-level fallback) is exercised
exactly as it would be against the real API, deterministically and
instantly.
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


def _make_gateway(handler, models: list[str] | None = None) -> OpenRouterGateway:
    settings = Settings(
        openrouter_api_key="test-openrouter-key",
        **({"openrouter_models": models} if models is not None else {}),
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


def _ok_response(content: str = "Hello!") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        },
    )


async def test_generate_success_parses_response_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # Asserted against an explicit, test-owned model string (not
        # Settings' real default) so this test never breaks just because
        # OpenRouter retires whatever free model happens to be the
        # project's current default — see config.py's openrouter_models
        # docstring on why those defaults can go stale.
        assert body["model"] == "test/explicit-model:free"
        assert body["messages"] == [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello."},
        ]
        assert body["temperature"] == 0.5
        assert "response_format" not in body
        return _ok_response("Hello!")

    gateway = _make_gateway(handler, models=["test/explicit-model:free"])
    response = await gateway.generate(_request())

    assert response.content == "Hello!"
    assert response.provider == "openrouter"
    assert response.model == "test/explicit-model:free"
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

    gateway = _make_gateway(handler, models=["test/explicit-model:free"])
    result = await gateway.generate_structured(_request(), _DummyResult)

    assert result == _DummyResult(value="ok", count=2)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_transient_status_codes_raise_transient_error_when_no_models_left(
    status: int,
) -> None:
    """A single-model config still ends in `TransientGatewayError` once that model fails."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "boom"})

    gateway = _make_gateway(handler, models=["only/model:free"])
    with pytest.raises(TransientGatewayError):
        await gateway.generate(_request())


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_permanent_status_codes_raise_permanent_error(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "boom"})

    gateway = _make_gateway(handler, models=["only/model:free"])
    with pytest.raises(PermanentGatewayError):
        await gateway.generate(_request())


async def test_network_error_raises_transient_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    gateway = _make_gateway(handler, models=["only/model:free"])
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


def test_construction_requires_at_least_one_model() -> None:
    settings = Settings(openrouter_api_key="key", openrouter_models=[])
    with pytest.raises(ValueError, match="openrouter_models must contain at least one model"):
        OpenRouterGateway(settings)


def test_construction_uses_configured_models() -> None:
    settings = Settings(
        openrouter_api_key="key", openrouter_models=["some/other-model:free", "another:free"]
    )
    gateway = OpenRouterGateway(settings)
    assert gateway.provider_name == "openrouter"
    assert gateway.supports_structured_output is True
    assert gateway.supports_json_schema is False
    assert gateway._models == ["some/other-model:free", "another:free"]


class TestModelFallback:
    """Model-level fallback: `OpenRouterGateway` tries its own model list before failing."""

    async def test_falls_back_to_second_model_on_transient_status(self) -> None:
        requested_models: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            requested_models.append(body["model"])
            if body["model"] == "model-a:free":
                return httpx.Response(429, json={"error": "rate limited"})
            return _ok_response("from model b")

        gateway = _make_gateway(handler, models=["model-a:free", "model-b:free"])
        response = await gateway.generate(_request())

        assert requested_models == ["model-a:free", "model-b:free"]
        assert response.content == "from model b"
        assert response.model == "model-b:free"

    async def test_falls_back_on_empty_content(self) -> None:
        """The exact bug that motivated this feature: HTTP 200 + empty message.content."""
        requested_models: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            requested_models.append(body["model"])
            if body["model"] == "reasoning-model:free":
                return _ok_response("")  # finish_reason=stop, empty content
            return _ok_response("real answer")

        gateway = _make_gateway(handler, models=["reasoning-model:free", "model-b:free"])
        response = await gateway.generate(_request())

        assert requested_models == ["reasoning-model:free", "model-b:free"]
        assert response.content == "real answer"

    async def test_falls_back_on_empty_choices_list(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["model"] == "model-a:free":
                return httpx.Response(200, json={"choices": []})
            return _ok_response("from model b")

        gateway = _make_gateway(handler, models=["model-a:free", "model-b:free"])
        response = await gateway.generate(_request())

        assert response.content == "from model b"

    async def test_falls_back_on_malformed_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["model"] == "model-a:free":
                return httpx.Response(200, content=b"not valid json{{{")
            return _ok_response("from model b")

        gateway = _make_gateway(handler, models=["model-a:free", "model-b:free"])
        response = await gateway.generate(_request())

        assert response.content == "from model b"

    async def test_falls_back_on_schema_validation_error_in_structured_mode(self) -> None:
        """Unlike before this feature, a ValidationError is retried against the next model."""

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["model"] == "model-a:free":
                return httpx.Response(
                    200, json={"choices": [{"message": {"content": "not valid json at all"}}]}
                )
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps({"value": "ok", "count": 2})}}]
                },
            )

        gateway = _make_gateway(handler, models=["model-a:free", "model-b:free"])
        result = await gateway.generate_structured(_request(), _DummyResult)

        assert result == _DummyResult(value="ok", count=2)

    async def test_single_model_schema_validation_error_exhausts_to_transient(self) -> None:
        """With only one model, a validation failure still ends in TransientGatewayError.

        This is the counterpart to the old single-model behavior (which
        let `pydantic.ValidationError` propagate unwrapped): now it's
        caught, treated as retryable, and — once the (single) model list
        is exhausted — surfaces as `TransientGatewayError` so `GatewayChain`
        can fall back to the next configured provider (e.g. mock) instead
        of stopping the whole chain immediately.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "not valid json at all"}}]}
            )

        gateway = _make_gateway(handler, models=["only/model:free"])
        with pytest.raises(TransientGatewayError) as exc_info:
            await gateway.generate_structured(_request(), _DummyResult)
        assert isinstance(exc_info.value.__cause__, TransientGatewayError)
        assert isinstance(exc_info.value.__cause__.__cause__, ValidationError)

    async def test_permanent_error_does_not_try_next_model(self) -> None:
        """Auth/bad-request/invalid-key failures fail fast, without trying other models."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(401, json={"error": "invalid api key"})

        gateway = _make_gateway(handler, models=["model-a:free", "model-b:free", "model-c:free"])
        with pytest.raises(PermanentGatewayError):
            await gateway.generate(_request())

        assert call_count == 1

    async def test_all_models_exhausted_raises_transient_with_chained_cause(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "boom"})

        gateway = _make_gateway(handler, models=["model-a:free", "model-b:free", "model-c:free"])
        with pytest.raises(TransientGatewayError) as exc_info:
            await gateway.generate(_request())

        assert "3 configured OpenRouter model(s) failed" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None

    async def test_gemma_fails_qwen_succeeds_full_fallback_flow(self) -> None:
        """The scenario named in the feature request: Gemma fails, Qwen succeeds."""
        requested_models: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            requested_models.append(body["model"])
            if body["model"] == "google/gemma-4-26b-a4b-it:free":
                return httpx.Response(429, json={"error": "rate limited"})
            if body["model"] == "qwen/qwen3-30b-a3b:free":
                return _ok_response("answer from qwen")
            raise AssertionError(f"unexpected model requested: {body['model']}")

        gateway = _make_gateway(
            handler,
            models=[
                "google/gemma-4-26b-a4b-it:free",
                "qwen/qwen3-30b-a3b:free",
                "meta-llama/llama-3.3-70b-instruct:free",
                "deepseek/deepseek-chat:free",
            ],
        )
        response = await gateway.generate(_request())

        assert requested_models == ["google/gemma-4-26b-a4b-it:free", "qwen/qwen3-30b-a3b:free"]
        assert response.content == "answer from qwen"
        assert response.model == "qwen/qwen3-30b-a3b:free"
