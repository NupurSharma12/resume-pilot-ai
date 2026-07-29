"""Provider-agnostic contract every LLM provider adapter must satisfy.

This module defines the interface only: no provider (Gemini, OpenAI, Claude,
Ollama, ...) is implemented here, and no network or subprocess calls are
made. Concrete provider adapters will live alongside this module and be
type-checked against `LLMGateway` structurally, without inheriting from it.
"""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.gateways.llm.models import LLMRequest, LLMResponse


@runtime_checkable
class LLMGateway(Protocol):
    """Structural interface for an LLM provider adapter.

    Using `typing.Protocol` instead of an abstract base class means provider
    adapters satisfy this contract by implementing matching method
    signatures, without needing to inherit from a shared base. This keeps
    the gateway layer decoupled from any particular provider SDK's class
    hierarchy and avoids forcing unrelated adapters (e.g. a local Ollama
    client vs. a hosted OpenAI client) into an artificial inheritance tree.
    """

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a single, complete completion for the given request.

        This is the standard non-streaming call: the caller awaits one
        `LLMResponse` containing the full generated content.
        """
        ...

    async def generate_structured(self, request: LLMRequest) -> LLMResponse:
        """Generate a completion constrained to `request.response_schema`.

        Kept as a distinct method from `generate` (rather than an implicit
        branch on whether `response_schema` is set) because structured
        output is a materially different capability per provider — some
        implement it via tool/function calling, others via native JSON
        mode — and a separate method makes that distinction explicit at
        the call site and lets adapters implement (or reject) it
        independently.
        """
        ...

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream incrementally generated content chunks for the request.

        Declared as a plain (non-`async`) method returning an
        `AsyncIterator[str]`, which is the correct way to describe an
        async-generator-shaped method in a `Protocol`: structural typing
        matches on the call signature (called directly, then iterated with
        `async for`), not on whether the implementation happens to use
        `async def ... yield`. Chunks are plain `str` deltas rather than
        partial `LLMResponse` objects, since usage/cost/finish_reason are
        only known once generation completes and shouldn't be faked
        mid-stream; callers that need the final `LLMResponse` should use
        `generate` instead, or accumulate chunks themselves.
        """
        ...
