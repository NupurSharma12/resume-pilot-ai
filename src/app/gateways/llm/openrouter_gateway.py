"""OpenRouter implementation of `LLMGateway`, using OpenRouter's OpenAI-compatible chat endpoint.

`OpenRouterGateway` exists as a fallback provider for `GatewayChain` (see
`chain.py`), not a primary one — it implements only enough of OpenRouter's
`/chat/completions` endpoint to satisfy `LLMGateway`: a single, non-streamed
completion (`generate`) and a best-effort structured completion
(`generate_structured`). `stream()` is left raising `NotImplementedError`,
same as `GeminiGateway`.

Model-level fallback
---------------------
OpenRouter's free-tier catalog is unreliable in ways a single fixed model
can't absorb: individual free models get rate-limited, retired, or (as
observed in production — see `config.py`'s `openrouter_models` docstring)
silently return empty `message.content` for reasoning-style models under
this app's long structured-output prompts. Rather than let any one of
those take down the whole "openrouter" leg of `GatewayChain` and fall
straight through to `MockGateway`, this gateway is configured with an
*ordered list* of models (`Settings.openrouter_models`) and tries them
itself, one at a time, before ever raising back to `GatewayChain` — so
from `GatewayChain`'s point of view, "openrouter" is still a single
provider that either succeeds or fails, exactly as before; the multi-model
retry is entirely internal (see `_call_with_model_fallback`).

A per-model attempt is retried against the *next* model on: a timeout or
network error, HTTP 429, HTTP 404 (an invalid/retired model id, or
OpenRouter reporting no provider currently serving that free model — see
`_RETRYABLE_STATUS_CODES`'s comment for why this is treated as per-model,
not per-request), any HTTP 5xx, an empty response (no `choices`, or
empty `message.content`), malformed JSON, or a `pydantic.ValidationError`
from `generate_structured`'s schema check. All of these are treated as
"this particular model didn't work this time," not "the request itself is
broken" — the same request, replayed against a different model, has a
real chance of succeeding. A per-model attempt is *not* retried against
another model on an authentication failure, a bad request, or an invalid
API key (HTTP 401/403/400, still classified via `_classify_status`): those
describe a problem with the request or credentials, which every other
OpenRouter model would fail identically against, so failing fast (raising
`PermanentGatewayError` immediately, matching the pre-fallback behavior)
avoids burning through the whole model list for no benefit.

If every configured model fails a retryable way, `_call_with_model_
fallback` raises a single `TransientGatewayError` — precisely so that
`GatewayChain` still sees "openrouter" as one transient failure and falls
back to the next configured provider (typically `MockGateway`) exactly as
it did when there was only one model. This is a deliberate broadening of
`generate_structured`'s validation-failure handling from before this
feature: a `pydantic.ValidationError` used to propagate unwrapped (treated
as non-retryable by `GatewayChain`); now it's retried across this
gateway's own model list first, and only surfaces as
`TransientGatewayError` once that list is exhausted.
"""

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.gateways.llm.errors import GatewayError, PermanentGatewayError, TransientGatewayError
from app.gateways.llm.gateway import LLMGateway, T
from app.gateways.llm.models import LLMRequest, LLMResponse, TokenUsage

logger = get_logger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT_SECONDS = 30.0

# Status codes worth retrying against the next configured model: 429 is
# rate limiting, 408 a request timeout, and any 5xx is the server's own
# transient failure — the same reasoning as GeminiGateway's
# `_RETRYABLE_CLIENT_STATUS_CODES`. 404 is the one deliberate difference
# from Gemini's classification: OpenRouter returns HTTP 404 both for a
# genuinely invalid/retired model id and for "no provider is currently
# serving this free model" (a real, documented OpenRouter capacity
# condition, functionally transient) — either way it describes a problem
# with *that one model*, not the request, and the next configured model
# has a real chance of working. Gemini has no equivalent per-provider
# model list to route around, so a 404 there still means "this request is
# broken" and stays permanent (see `gemini_gateway._classify_exception`).
_RETRYABLE_STATUS_CODES = {404, 408, 429}

R = TypeVar("R")


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
        as a confusing 401 on first use. `settings.openrouter_models`
        being empty is the same kind of misconfiguration — a provider in
        the chain with nothing to actually call.
        """
        if not settings.openrouter_api_key:
            raise ValueError(
                "openrouter_api_key is required to construct OpenRouterGateway "
                "(set RESUMEPILOT_OPENROUTER_API_KEY, or remove 'openrouter' from the chain)."
            )
        if not settings.openrouter_models:
            raise ValueError(
                "openrouter_models must contain at least one model "
                "(set RESUMEPILOT_OPENROUTER_MODELS, or remove 'openrouter' from the chain)."
            )
        self._models = list(settings.openrouter_models)
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
        """Call OpenRouter's chat completions endpoint, trying each configured model in order."""

        async def attempt(model: str) -> LLMResponse:
            payload = self._build_payload(request, user_prompt=request.user_prompt, model=model)
            start = time.perf_counter()
            data = await self._post(payload, model=model)
            latency_ms = (time.perf_counter() - start) * 1000

            choice = self._first_choice(data, model=model)
            content = self._require_content(choice, model=model)
            return LLMResponse(
                content=content,
                provider="openrouter",
                model=model,
                usage=self._extract_usage(data),
                cost=None,
                latency_ms=latency_ms,
                finish_reason=choice.get("finish_reason"),
            )

        return await self._call_with_model_fallback("generate", attempt)

    async def generate_structured(self, request: LLMRequest, response_model: type[T]) -> T:
        """Request JSON-object output with the schema embedded in the prompt, then validate it.

        See this module's docstring for why: OpenRouter's free-tier models
        aren't reliably capable of `response_format: json_schema`, so the
        schema is instead described in plain instructions appended to the
        user prompt, `response_format: {"type": "json_object"}` asks the
        model to at least return well-formed JSON, and
        `response_model.model_validate_json(...)` does the actual
        structural enforcement. Unlike before this feature, a
        `pydantic.ValidationError` here is caught and treated as a
        retryable-against-the-next-model failure (see
        `_call_with_model_fallback`), not propagated unwrapped — a schema
        mismatch from one free model is exactly the kind of "this model
        didn't cooperate" failure the model list exists to route around.
        """
        schema_instructions = (
            f"{request.user_prompt}\n\n"
            "Respond with ONLY a single JSON object conforming exactly to this JSON Schema "
            "— no prose, no markdown code fences, no explanation:\n"
            f"{json.dumps(response_model.model_json_schema())}"
        )

        async def attempt(model: str) -> T:
            payload = self._build_payload(
                request, user_prompt=schema_instructions, model=model, json_mode=True
            )
            start = time.perf_counter()
            data = await self._post(payload, model=model)
            latency_ms = (time.perf_counter() - start) * 1000

            choice = self._first_choice(data, model=model)
            content = self._require_content(choice, model=model)
            usage = self._extract_usage(data)

            try:
                result = response_model.model_validate_json(content)
            except ValidationError as exc:
                raise TransientGatewayError(
                    f"OpenRouter model {model!r} returned a response that failed schema "
                    f"validation ({response_model.__name__})."
                ) from exc

            logger.info(
                "openrouter_generate_structured",
                provider="openrouter",
                model=model,
                response_model=response_model.__name__,
                latency_ms=latency_ms,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
            )
            return result

        return await self._call_with_model_fallback("generate_structured", attempt)

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Not yet implemented — see `GeminiGateway.stream`."""
        raise NotImplementedError("OpenRouterGateway.stream is not yet implemented.")

    async def _call_with_model_fallback(
        self, method_name: str, attempt: Callable[[str], Awaitable[R]]
    ) -> R:
        """Try `attempt(model)` against each configured model in order until one succeeds.

        Mirrors `GatewayChain._attempt_chain`'s shape deliberately (same
        per-attempt/summary event structure, same "transient continues,
        permanent stops immediately" split) so a reader already familiar
        with the provider-level chain recognizes this as the same pattern
        one level down, at the model level. The key difference:
        `GatewayChain` fails a whole call the moment one gateway raises
        anything other than `TransientGatewayError`; this loop's terminal
        failure (every model exhausted) is *always* re-raised as
        `TransientGatewayError`, regardless of which specific retryable
        failures the individual models hit, so `GatewayChain` can fall
        back to the next provider (e.g. `MockGateway`) exactly as it would
        for a single-model OpenRouter failure. A `PermanentGatewayError`
        from any model (auth/bad-request/invalid key) still stops
        immediately without trying the rest of the list — see this
        module's docstring.

        Logs `openrouter_model_attempt_started`, `openrouter_model_
        failed` (+ `openrouter_model_fallback` when there's another model
        left to try), `openrouter_model_succeeded`, and exactly one
        terminal event per call: `openrouter_model_chain_summary` on
        success, or `openrouter_model_chain_exhausted` once every model
        has failed. Never logs prompt/response content — only outcome
        metadata, matching `_post`'s existing policy.
        """
        chain_start = time.perf_counter()
        models_tried: list[str] = []
        last_transient_error: Exception | None = None

        for index, model in enumerate(self._models):
            attempt_number = index + 1
            models_tried.append(model)
            logger.info(
                "openrouter_model_attempt_started",
                method=method_name,
                model=model,
                attempt=attempt_number,
                models_configured=len(self._models),
            )
            start = time.perf_counter()
            try:
                result = await attempt(model)
            except TransientGatewayError as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "openrouter_model_failed",
                    method=method_name,
                    model=model,
                    attempt=attempt_number,
                    elapsed_ms=elapsed_ms,
                    error_type=type(exc).__name__,
                    error=str(exc),
                    retryable=True,
                )
                if attempt_number < len(self._models):
                    logger.info(
                        "openrouter_model_fallback",
                        method=method_name,
                        from_model=model,
                        to_model=self._models[attempt_number],
                    )
                last_transient_error = exc
                continue

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "openrouter_model_succeeded",
                method=method_name,
                model=model,
                attempt=attempt_number,
                elapsed_ms=elapsed_ms,
            )
            logger.info(
                "openrouter_model_chain_summary",
                method=method_name,
                models_tried=models_tried,
                successful_model=model,
                attempts=len(models_tried),
                total_elapsed_ms=(time.perf_counter() - chain_start) * 1000,
            )
            return result

        logger.error(
            "openrouter_model_chain_exhausted",
            method=method_name,
            models_tried=models_tried,
            attempts=len(models_tried),
            total_elapsed_ms=(time.perf_counter() - chain_start) * 1000,
        )
        raise TransientGatewayError(
            f"All {len(models_tried)} configured OpenRouter model(s) failed for {method_name}: "
            f"{models_tried}."
        ) from last_transient_error

    def _build_payload(
        self, request: LLMRequest, *, user_prompt: str, model: str, json_mode: bool = False
    ) -> dict[str, Any]:
        """Build an OpenAI-compatible chat completions request body for one specific model.

        `request.system_prompt`/`.temperature`/`.max_tokens` map directly
        onto the equivalent OpenAI-shaped fields, the same fields
        `GeminiGateway` reads from `request` for its own config object —
        `user_prompt` is passed separately (not read from `request`
        directly) so `generate_structured` can substitute the
        schema-augmented prompt without mutating `request` itself, which
        is a frozen model shared with `generate`. `model` is passed
        explicitly (not read from a single stored field) so each attempt
        in `_call_with_model_fallback`'s loop targets a different model.
        """
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _post(self, payload: dict[str, Any], *, model: str) -> dict[str, Any]:
        """POST to `/chat/completions` for one model, classifying any failure.

        Network-level failures (`httpx.TimeoutException`/`NetworkError` —
        the request never got a response at all) are classified as
        transient directly, the same way `GeminiGateway` treats them; an
        HTTP response that *did* come back is classified by its status
        code via `_classify_status`. A 200 response whose body isn't valid
        JSON — OpenRouter has been observed doing this for some free
        models under load — is also transient: the request itself was
        fine, this particular model's response wasn't usable. Neither the
        request payload nor the response body is ever logged — only the
        outcome (status code, classification, latency) — per the
        no-content-logging policy.
        """
        start = time.perf_counter()
        try:
            response = await self._client.post("/chat/completions", json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            classified = TransientGatewayError(
                f"OpenRouter network error (model={model}): {type(exc).__name__}."
            )
            logger.error(
                "openrouter_request_failed",
                provider="openrouter",
                model=model,
                latency_ms=elapsed_ms,
                error_type=type(exc).__name__,
                retryable=True,
            )
            raise classified from exc

        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.status_code == 200:
            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                logger.error(
                    "openrouter_request_failed",
                    provider="openrouter",
                    model=model,
                    latency_ms=elapsed_ms,
                    error_type=type(exc).__name__,
                    reason="malformed_json",
                    retryable=True,
                )
                raise TransientGatewayError(
                    f"OpenRouter model {model!r} returned malformed JSON."
                ) from exc

        classified = _classify_status(response.status_code)
        logger.error(
            "openrouter_request_failed",
            provider="openrouter",
            model=model,
            latency_ms=elapsed_ms,
            status_code=response.status_code,
            retryable=isinstance(classified, TransientGatewayError),
        )
        raise classified

    @staticmethod
    def _first_choice(data: dict[str, Any], *, model: str) -> dict[str, Any]:
        """Return the response's first choice, or raise transient on an empty `choices` list.

        An empty `choices` array is a valid-JSON, 200-status response that
        still has nothing usable in it — treated the same as any other
        "this model didn't produce a usable response" failure, not an
        unhandled `IndexError`.
        """
        choices = data.get("choices") or []
        if not choices:
            raise TransientGatewayError(
                f"OpenRouter model {model!r} returned no choices (empty response)."
            )
        return choices[0]

    @staticmethod
    def _require_content(choice: dict[str, Any], *, model: str) -> str:
        """Return the choice's message content, or raise transient if it's empty/missing.

        This is the fix for the specific failure mode that motivated
        model-level fallback: some free/reasoning models return HTTP 200
        with `finish_reason=stop` but a null or empty `message.content` —
        previously silently coerced to `""` (see this file's git history),
        which surfaced downstream as a confusing empty-string parse
        failure instead of triggering fallback to the next model.
        """
        content = (choice.get("message") or {}).get("content")
        if not content:
            raise TransientGatewayError(f"OpenRouter model {model!r} returned empty content.")
        return content

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
