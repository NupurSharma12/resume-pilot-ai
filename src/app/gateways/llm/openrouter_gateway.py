"""OpenRouter implementation of `LLMGateway`, using OpenRouter's OpenAI-compatible chat endpoint.

`OpenRouterGateway` exists as a fallback provider for `GatewayChain` (see
`chain.py`), not a primary one — it implements only enough of OpenRouter's
`/chat/completions` endpoint to satisfy `LLMGateway`: a single, non-streamed
completion (`generate`) and a best-effort structured completion
(`generate_structured`). `stream()` is left raising `NotImplementedError`,
same as `GeminiGateway`.

OpenRouter's free-tier models don't reliably support strict, provider-
enforced JSON Schema output (see `supports_json_schema`), so
`generate_structured` uses JSON-object mode plus the target schema embedded
directly in the prompt, then validates the response against `response_model`
on receipt — a softer guarantee than `GeminiGateway`'s native
`response_json_schema`, but sufficient for a fallback path: if the model
doesn't follow the embedded schema well enough to validate, that's a
`pydantic.ValidationError`, which `GatewayChain` already treats as
non-retryable (see `PermanentGatewayError`'s docstring) — the failure
surfaces to the caller instead of masking a genuine model-quality problem
as a transient one.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.gateways.llm.errors import GatewayError, PermanentGatewayError, TransientGatewayError
from app.gateways.llm.gateway import LLMGateway, T
from app.gateways.llm.models import LLMRequest, LLMResponse, TokenUsage

logger = get_logger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT_SECONDS = 30.0

# Status codes worth retrying against another provider — the same
# reasoning as GeminiGateway's `_RETRYABLE_CLIENT_STATUS_CODES`: 429 is
# rate limiting, 408 a request timeout, and any 5xx is the server's own
# transient failure, not a problem with the request.
_RETRYABLE_STATUS_CODES = {408, 429}


def _classify_status(status_code: int) -> GatewayError:
    """Classify an OpenRouter HTTP status code as transient or permanent.

    A plain function (not a method) for the same reason
    `gemini_gateway._classify_exception` is: directly unit-testable
    without a real request or a mocked client.
    """
    if status_code in _RETRYABLE_STATUS_CODES or 500 <= status_code < 600:
        return TransientGatewayError(f"OpenRouter returned HTTP {status_code}: transient.")
    return PermanentGatewayError(f"OpenRouter returned HTTP {status_code}: not retryable.")


class OpenRouterGateway(LLMGateway):
    """`LLMGateway` adapter backed by OpenRouter's OpenAI-compatible chat completions endpoint."""

    def __init__(self, settings: Settings) -> None:
        """Build the HTTP client once from injected `Settings`, mirroring `GeminiGateway.__init__`.

        `settings.openrouter_api_key` is required to construct this class
        — same fail-fast philosophy as `GeminiGateway`'s key check: a
        provider named in the chain but missing its credentials is a
        misconfiguration that should surface immediately and loudly, not
        as a confusing 401 on first use.
        """
        if not settings.openrouter_api_key:
            raise ValueError(
                "openrouter_api_key is required to construct OpenRouterGateway "
                "(set RESUMEPILOT_OPENROUTER_API_KEY, or remove 'openrouter' from the chain)."
            )
        self._model = settings.openrouter_model
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            timeout=_TIMEOUT_SECONDS,
        )

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def supports_structured_output(self) -> bool:
        return True

    @property
    def supports_json_schema(self) -> bool:
        # See this module's docstring: structured output here is JSON-mode
        # plus a prompt-embedded schema, not provider-native enforcement.
        return False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Call OpenRouter's chat completions endpoint and map the response onto `LLMResponse`."""
        payload = self._build_payload(request, user_prompt=request.user_prompt)
        start = time.perf_counter()
        data = await self._post(payload)
        latency_ms = (time.perf_counter() - start) * 1000

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"]["content"] or "",
            provider="openrouter",
            model=self._model,
            usage=self._extract_usage(data),
            cost=None,
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason"),
        )

    async def generate_structured(self, request: LLMRequest, response_model: type[T]) -> T:
        """Request JSON-object output with the schema embedded in the prompt, then validate it.

        See this module's docstring for why: OpenRouter's free-tier models
        aren't reliably capable of `response_format: json_schema`, so the
        schema is instead described in plain instructions appended to the
        user prompt, `response_format: {"type": "json_object"}` asks the
        model to at least return well-formed JSON, and
        `response_model.model_validate_json(...)` does the actual
        structural enforcement — the same validation step
        `GeminiGateway.generate_structured` ends with, left equally
        unwrapped here so a `pydantic.ValidationError` propagates as-is
        (see `_classify_status`'s module docstring on why that's still
        correctly treated as non-retryable by `GatewayChain`).
        """
        schema_instructions = (
            f"{request.user_prompt}\n\n"
            "Respond with ONLY a single JSON object conforming exactly to this JSON Schema "
            "— no prose, no markdown code fences, no explanation:\n"
            f"{json.dumps(response_model.model_json_schema())}"
        )
        payload = self._build_payload(request, user_prompt=schema_instructions, json_mode=True)

        start = time.perf_counter()
        data = await self._post(payload)
        latency_ms = (time.perf_counter() - start) * 1000

        content = data["choices"][0]["message"]["content"] or ""
        usage = self._extract_usage(data)
        logger.info(
            "openrouter_generate_structured",
            provider="openrouter",
            model=self._model,
            response_model=response_model.__name__,
            latency_ms=latency_ms,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
        )

        return response_model.model_validate_json(content)

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Not yet implemented — see `GeminiGateway.stream`."""
        raise NotImplementedError("OpenRouterGateway.stream is not yet implemented.")

    def _build_payload(
        self, request: LLMRequest, *, user_prompt: str, json_mode: bool = False
    ) -> dict[str, Any]:
        """Build an OpenAI-compatible chat completions request body.

        `request.system_prompt`/`.temperature`/`.max_tokens` map directly
        onto the equivalent OpenAI-shaped fields, the same fields
        `GeminiGateway` reads from `request` for its own config object —
        `user_prompt` is passed separately (not read from `request`
        directly) so `generate_structured` can substitute the
        schema-augmented prompt without mutating `request` itself, which
        is a frozen model shared with `generate`.
        """
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to `/chat/completions`, classifying any failure via `_classify_status`.

        Network-level failures (`httpx.TimeoutException`/`NetworkError` —
        the request never got a response at all) are classified as
        transient directly, the same way `GeminiGateway` treats them; an
        HTTP response that *did* come back is classified by its status
        code via `_classify_status`. Neither the request payload nor the
        response body is ever logged — only the outcome (status code,
        classification, latency) — per the no-content-logging policy.
        """
        start = time.perf_counter()
        try:
            response = await self._client.post("/chat/completions", json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            classified = TransientGatewayError(f"OpenRouter network error: {type(exc).__name__}.")
            logger.error(
                "openrouter_request_failed",
                provider="openrouter",
                model=self._model,
                latency_ms=elapsed_ms,
                error_type=type(exc).__name__,
                retryable=True,
            )
            raise classified from exc

        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.status_code == 200:
            return response.json()

        classified = _classify_status(response.status_code)
        logger.error(
            "openrouter_request_failed",
            provider="openrouter",
            model=self._model,
            latency_ms=elapsed_ms,
            status_code=response.status_code,
            retryable=isinstance(classified, TransientGatewayError),
        )
        raise classified

    @staticmethod
    def _extract_usage(data: dict[str, Any]) -> TokenUsage | None:
        """Build a `TokenUsage` from OpenRouter's OpenAI-shaped `usage` object, if present.

        Mirrors `GeminiGateway._extract_usage`'s "`None` means unreported,
        not zero" distinction.
        """
        usage = data.get("usage")
        if not usage:
            return None
        return TokenUsage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
