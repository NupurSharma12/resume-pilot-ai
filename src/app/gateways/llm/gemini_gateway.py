"""Gemini implementation of `LLMGateway`, using the official `google-genai` SDK.

`GeminiGateway` is the first real (non-mock) provider adapter: it makes
actual network calls to Google's Gemini API and is the concrete class that
maps this project's provider-agnostic `LLMRequest`/`LLMResponse` contracts
onto `google-genai`'s request/response shapes. Only `generate()` is
implemented; `generate_structured()` and `stream()` are left raising
`NotImplementedError` until a structured-output and streaming strategy is
decided.
"""

import time
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.core.config import Settings
from app.gateways.llm.gateway import LLMGateway
from app.gateways.llm.models import LLMRequest, LLMResponse, TokenUsage


class GeminiGateway(LLMGateway):
    """`LLMGateway` adapter backed by Google's Gemini API.

    Inherits from `LLMGateway` explicitly, for the same reason
    `MockGateway` does: `Protocol` conformance here is structural, but
    inheriting documents that this class is meant to be read as a
    first-class, interchangeable implementation of the gateway contract.
    """

    def __init__(self, settings: Settings) -> None:
        """Build the Gemini client once from injected `Settings`.

        `Settings` is accepted as a single constructor parameter — not
        individual `api_key`/`model` strings, and no direct
        `os.environ`/`os.getenv` calls — so this class has exactly one way
        to receive configuration, consistent with how the rest of the
        application (e.g. `app.py`'s `configure_logging(settings)`) is
        wired. `genai.Client` is constructed here, once, rather than per
        call in `generate()`: the client encapsulates connection/transport
        setup, and building it once per gateway instance (mirroring how
        `MockGateway` and other adapters are expected to be cheap to
        construct and reused across requests, per
        `analyze.py`'s `get_resume_analysis_workflow`) avoids repeating
        that setup on every request.

        `settings.gemini_model` is captured now, in `__init__`, rather
        than re-read from `settings` inside `generate()`: this keeps
        `generate()`'s only dependency on external state the constructed
        `self._client` and `self._model`, and matches the requirement to
        use `settings.gemini_model` rather than the model name that
        happens to be set on any given `LLMRequest` (which, while this
        provider-agnostic field exists on `LLMRequest`, is not what
        selects which concrete Gemini model this adapter calls — that is
        this adapter's own configuration, not a per-request choice made
        by callers that don't know they're talking to Gemini).
        """
        self._model = settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Call the Gemini API and map its response onto `LLMResponse`.

        Uses `client.aio.models.generate_content`, the SDK's async
        variant, rather than the sync `client.models.generate_content`
        wrapped in a thread: `generate` is declared `async` on
        `LLMGateway`, and the SDK already provides a native coroutine for
        this call, so there is no reason to introduce thread-pool
        indirection.

        `request.system_prompt`, `.temperature`, and `.max_tokens` are
        passed straight through into `types.GenerateContentConfig`
        (Gemini's per-call configuration object); `request.metadata` and
        `request.response_schema` are not used here — `metadata` has no
        corresponding Gemini API parameter for a plain `generate_content`
        call, and `response_schema` is a `generate_structured` concern,
        not `generate`'s.

        Latency is measured with `time.perf_counter()` around the network
        call specifically (not including config construction, which is
        negligible and local), since `perf_counter` is the standard choice
        for measuring elapsed wall-clock time for performance purposes —
        unlike `time.time()`, it's monotonic and unaffected by system
        clock adjustments.
        """
        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
        )

        start = time.perf_counter()
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=request.user_prompt,
            config=config,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        return LLMResponse(
            content=response.text or "",
            provider="gemini",
            model=self._model,
            usage=self._extract_usage(response),
            cost=None,
            latency_ms=latency_ms,
            finish_reason=self._extract_finish_reason(response),
        )

    async def generate_structured(self, request: LLMRequest) -> LLMResponse:
        """Not yet implemented.

        Gemini supports structured output via `response_schema`/
        `response_mime_type` on `GenerateContentConfig`, but deciding how
        `LLMRequest.response_schema` (a plain `type`) should map onto that
        — and how to validate/parse the result — is a design decision left
        for a dedicated change, not bundled into this first adapter.
        """
        raise NotImplementedError("GeminiGateway.generate_structured is not yet implemented.")

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Not yet implemented.

        Left as a plain method raising immediately, matching
        `LLMGateway.stream`'s declared (non-`async`) signature: streaming
        will need its own mapping from Gemini's
        `generate_content_stream` chunks to `str` deltas, which is left
        for a dedicated change.
        """
        raise NotImplementedError("GeminiGateway.stream is not yet implemented.")

    @staticmethod
    def _extract_usage(response: types.GenerateContentResponse) -> TokenUsage | None:
        """Build a `TokenUsage` from Gemini's `usage_metadata`, if present.

        Gemini's `usage_metadata` fields are individually optional (the
        SDK types them as `int | None`), so each is defaulted to `0`
        rather than propagating `None` into `TokenUsage`, whose fields are
        plain `int`. Returns `None` entirely (rather than a
        `TokenUsage` of zeros) when the API reports no usage metadata at
        all, so callers can distinguish "usage unknown" from "usage was
        zero".
        """
        usage_metadata = response.usage_metadata
        if usage_metadata is None:
            return None
        return TokenUsage(
            prompt_tokens=usage_metadata.prompt_token_count or 0,
            completion_tokens=usage_metadata.candidates_token_count or 0,
            total_tokens=usage_metadata.total_token_count or 0,
        )

    @staticmethod
    def _extract_finish_reason(response: types.GenerateContentResponse) -> str | None:
        """Return the first candidate's finish reason as a plain string, if any.

        Gemini reports `finish_reason` as a `FinishReason` enum per
        candidate, and only generates one candidate for a standard
        `generate_content` call (no `candidate_count` override is set
        above). `.value` is used to store the plain string form (e.g.
        `"STOP"`) on `LLMResponse.finish_reason`, which is typed as
        `str | None` and provider-agnostic — it shouldn't carry a
        Gemini-specific enum type.
        """
        if not response.candidates:
            return None
        finish_reason = response.candidates[0].finish_reason
        return finish_reason.value if finish_reason is not None else None
