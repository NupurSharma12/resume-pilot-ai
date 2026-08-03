"""Unit tests for `GeminiGateway`'s exception classification and construction.

`_classify_exception` is tested directly, as a pure function, rather than
by mocking `google.genai.Client` and forcing a real (or faked) network
call to fail — it's the one piece of `GeminiGateway` the whole retry
policy hinges on, so it's worth testing in isolation, cheaply and
deterministically.
"""

import httpx
import pytest
from google.genai.errors import ClientError, ServerError

from app.core.config import Settings
from app.gateways.llm.errors import PermanentGatewayError, TransientGatewayError
from app.gateways.llm.gemini_gateway import GeminiGateway, _classify_exception


def _client_error(code: int) -> ClientError:
    return ClientError(code, {"error": {"message": "client error", "status": "ERROR"}}, None)


def _server_error(code: int) -> ServerError:
    return ServerError(code, {"error": {"message": "server error", "status": "ERROR"}}, None)


@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_server_errors_are_transient(code: int) -> None:
    classified = _classify_exception(_server_error(code))
    assert isinstance(classified, TransientGatewayError)


def test_rate_limit_429_is_transient() -> None:
    classified = _classify_exception(_client_error(429))
    assert isinstance(classified, TransientGatewayError)


def test_request_timeout_408_is_transient() -> None:
    classified = _classify_exception(_client_error(408))
    assert isinstance(classified, TransientGatewayError)


@pytest.mark.parametrize("code", [400, 401, 403])
def test_bad_request_and_auth_errors_are_permanent(code: int) -> None:
    classified = _classify_exception(_client_error(code))
    assert isinstance(classified, PermanentGatewayError)


def test_other_client_errors_default_permanent() -> None:
    """A 404 (or any other unlisted 4xx) is not explicitly "retryable", so it stays permanent."""
    classified = _classify_exception(_client_error(404))
    assert isinstance(classified, PermanentGatewayError)


def test_connect_timeout_is_transient() -> None:
    classified = _classify_exception(httpx.ConnectTimeout("connect timed out"))
    assert isinstance(classified, TransientGatewayError)


def test_read_timeout_is_transient() -> None:
    classified = _classify_exception(httpx.ReadTimeout("read timed out"))
    assert isinstance(classified, TransientGatewayError)


def test_connect_error_is_transient() -> None:
    classified = _classify_exception(httpx.ConnectError("connection reset"))
    assert isinstance(classified, TransientGatewayError)


def test_unclassified_exception_defaults_permanent() -> None:
    """Anything not explicitly recognized as transient is treated as non-retryable by default."""
    classified = _classify_exception(RuntimeError("something unexpected"))
    assert isinstance(classified, PermanentGatewayError)


def test_construction_requires_api_key() -> None:
    settings = Settings(gemini_api_key=None)
    with pytest.raises(ValueError, match="gemini_api_key is required"):
        GeminiGateway(settings)


def test_construction_succeeds_with_api_key() -> None:
    settings = Settings(gemini_api_key="a-real-looking-key")
    gateway = GeminiGateway(settings)
    assert gateway.provider_name == "gemini"
    assert gateway.supports_structured_output is True
    assert gateway.supports_json_schema is True
