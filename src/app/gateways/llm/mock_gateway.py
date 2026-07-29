"""In-memory fake implementation of `LLMGateway`.

`MockGateway` lets the rest of the application (agents, workflows, API
routes) be developed and tested end-to-end without calling any real
provider, consuming API tokens, or requiring network access. It performs no
I/O, no external SDK calls, and no business logic — it only echoes back
deterministic, clearly-fake data shaped like a real `LLMResponse`.
"""

from collections.abc import AsyncIterator

from app.gateways.llm.gateway import LLMGateway
from app.gateways.llm.models import Cost, LLMRequest, LLMResponse, TokenUsage

_PROMPT_PREVIEW_LIMIT = 100
_MOCK_COST_PER_TOKEN = 0.000001
_STREAM_CHUNKS = ("This ", "is ", "a ", "mocked ", "stream.")


def _preview(text: str, limit: int = _PROMPT_PREVIEW_LIMIT) -> str:
    """Truncate `text` to `limit` characters for readable debug output.

    Prompts can be arbitrarily long; embedding one in full inside a mock
    response would make logs and test assertions unwieldy. A fixed-length
    preview keeps the mock response readable while still identifying which
    request produced it.
    """
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _estimate_tokens(text: str) -> int:
    """Roughly estimate a token count from character length.

    Real tokenizers are provider-specific and are exactly what `MockGateway`
    exists to avoid depending on. A simple `len(text) // 4` heuristic (a
    commonly cited rule of thumb for English text) gives `TokenUsage` values
    that scale with input size and feel realistic, without pulling in a
    tokenizer library or any provider SDK. It is intentionally not
    precise — precision is not the point of a mock.
    """
    return max(1, len(text) // 4)


class MockGateway(LLMGateway):
    """Fake `LLMGateway` that returns deterministic, synthetic responses.

    Inherits from `LLMGateway` explicitly (even though `Protocol` conformance
    is structural) to document intent: this class is meant to be read as a
    first-class, interchangeable implementation of the gateway contract, not
    an incidental structural match. Because `LLMGateway` is
    `@runtime_checkable`, `isinstance(MockGateway(), LLMGateway)` also holds.

    All outputs are deterministic (no randomness, no timing-based values)
    so tests that use `MockGateway` can assert on exact content.
    """

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Return a synthetic response echoing the request's prompt.

        `latency_ms` is fixed at `0` rather than measured, since no call
        actually happens — reporting a real elapsed time would misleadingly
        imply work was done. `finish_reason` is fixed at `"stop"` to mimic
        the common "completed normally" case, since that is what most
        downstream code branching on `finish_reason` expects by default.
        """
        content = f"Mock response for: {_preview(request.user_prompt)}"
        return LLMResponse(
            content=content,
            provider="mock",
            model=request.model,
            usage=self._mock_usage(request.user_prompt, content),
            cost=self._mock_cost(request.user_prompt, content),
            latency_ms=0,
            finish_reason="stop",
        )

    async def generate_structured(self, request: LLMRequest) -> LLMResponse:
        """Return a synthetic response indicating structured generation.

        No JSON is produced or parsed against `request.response_schema` —
        doing so would mean interpreting the schema, which is business
        logic outside a mock's job. The content simply names that
        structured generation was requested, which is enough for callers
        developing against the gateway to distinguish this path from
        `generate` in logs and tests.
        """
        content = f"Mock structured response for: {_preview(request.user_prompt)}"
        return LLMResponse(
            content=content,
            provider="mock",
            model=request.model,
            usage=self._mock_usage(request.user_prompt, content),
            cost=self._mock_cost(request.user_prompt, content),
            latency_ms=0,
            finish_reason="stop",
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Yield a small, fixed sequence of content chunks.

        Implemented as an `async def ... yield` generator, which satisfies
        `LLMGateway.stream`'s `AsyncIterator[str]` signature structurally.
        Chunks are a hardcoded tuple rather than derived from the request,
        keeping the mock trivially predictable for tests. No `asyncio.sleep`
        is used between chunks: introducing artificial delay would only
        slow down the test suites and local dev loops this class exists to
        speed up, with no corresponding benefit since nothing here is
        actually waiting on I/O.
        """
        for chunk in _STREAM_CHUNKS:
            yield chunk

    @staticmethod
    def _mock_usage(prompt: str, content: str) -> TokenUsage:
        """Build a `TokenUsage` that scales with prompt/response size.

        Kept as a private helper shared by `generate` and
        `generate_structured` so both methods report usage the same way,
        rather than duplicating the estimate/construct logic inline.
        """
        prompt_tokens = _estimate_tokens(prompt)
        completion_tokens = _estimate_tokens(content)
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    @staticmethod
    def _mock_cost(prompt: str, content: str) -> Cost:
        """Build a `Cost` derived from the same token estimate as usage.

        Using a fixed, tiny per-token rate keeps the reported cost
        proportional to `usage` (larger prompts cost more) rather than
        always returning zero, which would be a less realistic stand-in
        for a real provider's response shape.
        """
        total_tokens = _estimate_tokens(prompt) + _estimate_tokens(content)
        return Cost(total_cost=round(total_tokens * _MOCK_COST_PER_TOKEN, 8))
