"""GatewayChain: tries each configured `LLMGateway` in order, falling back on transient failures.

This is the core of Multi-LLM Resilience: workflows depend on exactly one
`LLMGateway` (via constructor injection, unchanged — see
`ResumeAnalysisWorkflow`/`CareerConversationWorkflow`), and are handed a
`GatewayChain` instead of a single concrete provider. `GatewayChain` itself
implements `LLMGateway`, so from a workflow's point of view nothing is
different: it calls `generate`/`generate_structured` on "the gateway" and
gets a result or an exception, exactly as before. Which provider actually
served that call — and how many others were tried first — is entirely
this class's concern, decided fresh on every call via `Settings`-driven
DI (see `factory.py`), never hardcoded into any workflow.
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

from app.core.logging import get_logger
from app.gateways.llm.errors import GatewayChainExhaustedError, TransientGatewayError
from app.gateways.llm.gateway import LLMGateway, T
from app.gateways.llm.models import LLMRequest, LLMResponse

logger = get_logger(__name__)

R = TypeVar("R")


class GatewayChain(LLMGateway):
    """An ordered list of `LLMGateway`s, tried in order until one succeeds.

    Not a retry-the-same-provider loop: each provider in the chain gets
    exactly one attempt per call. "Retry" here means "try the next
    provider," per the sprint's explicit goal — a provider's own SDK may
    still retry internally before raising (Gemini's does; see
    `gemini_gateway`'s docstring), so by the time this class sees a
    failure, that provider has already given up for this attempt.
    """

    def __init__(self, gateways: list[LLMGateway]) -> None:
        """Store the ordered provider list.

        Raises `ValueError` immediately (not on first call) if `gateways`
        is empty — a chain with nothing in it can never succeed, and
        that's a configuration error worth surfacing at construction time,
        matching this codebase's established fail-fast philosophy for
        misconfiguration (see `GeminiGateway.__init__`'s API-key check).
        """
        if not gateways:
            raise ValueError("GatewayChain requires at least one gateway.")
        self._gateways = gateways

    @property
    def provider_name(self) -> str:
        """A composite identifier listing every provider in order, e.g. `"chain[gemini,mock]"`."""
        return f"chain[{','.join(gateway.provider_name for gateway in self._gateways)}]"

    @property
    def supports_structured_output(self) -> bool:
        return any(gateway.supports_structured_output for gateway in self._gateways)

    @property
    def supports_json_schema(self) -> bool:
        return any(gateway.supports_json_schema for gateway in self._gateways)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return await self._attempt_chain(
            method_name="generate",
            call=lambda gateway: gateway.generate(request),
            requires_structured_output=False,
        )

    async def generate_structured(self, request: LLMRequest, response_model: type[T]) -> T:
        return await self._attempt_chain(
            method_name="generate_structured",
            call=lambda gateway: gateway.generate_structured(request, response_model),
            requires_structured_output=True,
        )

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Not yet implemented.

        Streaming fallback needs its own design, same as each provider's.
        """
        raise NotImplementedError("GatewayChain.stream is not yet implemented.")

    async def _attempt_chain(
        self,
        *,
        method_name: str,
        call: Callable[[LLMGateway], Awaitable[R]],
        requires_structured_output: bool,
    ) -> R:
        """Try each gateway in order, falling back only on `TransientGatewayError`.

        Every other outcome — success, or any exception that isn't a
        `TransientGatewayError` — ends the attempt immediately:

        - Success returns the result right away; later gateways in the
          chain are never consulted for this call.
        - A `TransientGatewayError` is logged and the loop continues to
          the next gateway (fallback).
        - Any other exception — `PermanentGatewayError`, a bare
          `pydantic.ValidationError` from a schema-validation failure, or
          anything a gateway failed to classify — is logged and
          re-raised immediately, without trying the next provider. This
          is a deliberate, conservative default: an unclassified failure
          might indicate a real bug or a genuinely bad request, and both
          would very likely fail identically against the next provider
          too, so silently burning through the rest of the chain would
          only hide the problem and add latency, not fix anything.

        Providers that can't even attempt `generate_structured` (per
        their own `supports_structured_output`) are skipped without being
        called at all — logged as a skip, not a failure, since nothing
        was actually attempted; skipped providers don't consume an
        `attempt` number and aren't recorded in `providers_tried`.

        Events logged (all INFO except `gateway_attempt_failed_permanent`
        and `gateway_chain_failed`, which are ERROR): `gateway_attempt_
        started`, `gateway_attempt_succeeded`, `gateway_attempt_failed_
        transient`, `gateway_attempt_failed_permanent` (each carrying
        `provider`/`attempt`/`operation`, plus `elapsed_ms` once the call has
        returned, plus `error_type`/`error` on failure — `error` is
        `str(exc)` on a `TransientGatewayError`/`PermanentGatewayError`,
        which is always a short, provider-agnostic classification message
        such as "Gemini server error (HTTP 503)."; never provider SDK
        response bodies, request content, or user data), and `gateway_
        fallback` (`from_provider`/`to_provider`, only between two
        *attempted* providers — a skip in between doesn't break the
        from/to pairing) are per-attempt events, one per gateway tried.

        Exactly one terminal, aggregate event is logged per call, in
        addition to the per-attempt events above: `gateway_chain_summary`
        on success, or `gateway_chain_failed` once every gateway has
        failed or been skipped — both carry the same run-level counters
        (`providers_tried`, `attempts`, `fallback_count`,
        `total_elapsed_ms`), so a summary log alone answers "how many
        providers did this call need, and how long did the whole thing
        take" without needing to reconstruct it from the per-attempt
        events. `total_elapsed_ms` is wall-clock time for the entire
        chain call (every attempt plus any time between them), not the
        sum of each attempt's own `elapsed_ms`.
        """
        chain_start = time.perf_counter()
        providers_tried: list[str] = []
        previous_provider: str | None = None
        fallback_count = 0
        last_transient_error: Exception | None = None

        for gateway in self._gateways:
            if requires_structured_output and not gateway.supports_structured_output:
                logger.info(
                    "gateway_chain_provider_skipped",
                    provider=gateway.provider_name,
                    operation=method_name,
                    reason="does_not_support_structured_output",
                )
                continue

            attempt = len(providers_tried) + 1
            providers_tried.append(gateway.provider_name)

            if previous_provider is not None:
                logger.info(
                    "gateway_fallback",
                    from_provider=previous_provider,
                    to_provider=gateway.provider_name,
                )

            logger.info(
                "gateway_attempt_started",
                provider=gateway.provider_name,
                attempt=attempt,
                operation=method_name,
            )
            start = time.perf_counter()
            try:
                result = await call(gateway)
            except TransientGatewayError as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "gateway_attempt_failed_transient",
                    provider=gateway.provider_name,
                    attempt=attempt,
                    operation=method_name,
                    elapsed_ms=elapsed_ms,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                previous_provider = gateway.provider_name
                last_transient_error = exc
                fallback_count += 1
                continue
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "gateway_attempt_failed_permanent",
                    provider=gateway.provider_name,
                    attempt=attempt,
                    operation=method_name,
                    elapsed_ms=elapsed_ms,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                raise

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "gateway_attempt_succeeded",
                provider=gateway.provider_name,
                attempt=attempt,
                operation=method_name,
                elapsed_ms=elapsed_ms,
            )
            logger.info(
                "gateway_chain_summary",
                operation=method_name,
                providers_tried=providers_tried,
                successful_provider=gateway.provider_name,
                attempts=len(providers_tried),
                fallback_count=fallback_count,
                total_elapsed_ms=(time.perf_counter() - chain_start) * 1000,
            )
            return result

        logger.error(
            "gateway_chain_failed",
            operation=method_name,
            providers_tried=providers_tried,
            attempts=len(providers_tried),
            fallback_count=fallback_count,
            total_elapsed_ms=(time.perf_counter() - chain_start) * 1000,
        )
        raise GatewayChainExhaustedError(
            f"All {len(providers_tried)} attempted provider(s) failed for {method_name}."
        ) from last_transient_error


__all__ = ["GatewayChain"]
