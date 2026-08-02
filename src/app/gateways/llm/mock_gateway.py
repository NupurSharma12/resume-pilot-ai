"""In-memory fake implementation of `LLMGateway`.

`MockGateway` lets the rest of the application (agents, workflows, API
routes) be developed and tested end-to-end without calling any real
provider, consuming API tokens, or requiring network access. It performs no
I/O, no external SDK calls, and no business logic — it only echoes back
deterministic, clearly-fake data shaped like a real `LLMResponse`.
"""

from collections.abc import AsyncIterator
from typing import get_origin

from pydantic import BaseModel

from app.gateways.llm.gateway import LLMGateway, T
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


def _placeholder_value(annotation: object) -> object:
    """Return a type-appropriate empty/zero value for a single field annotation.

    Dispatches purely on `annotation` — never on a field's name or
    description — so this has no way to encode domain knowledge about
    what any particular field means. Nested `BaseModel` subclasses recurse
    into `_build_placeholder`; `list[...]` annotations become `[]`
    (an empty list is a valid value for every `list` field on the current
    domain model, none of which require a minimum length); primitives get
    their zero value; anything else falls back to `None`, which is only
    valid for fields already typed as optional.
    """
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _build_placeholder(annotation)
    if get_origin(annotation) is list:
        return []
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is str:
        return ""
    if annotation is bool:
        return False
    return None


def _build_placeholder(model_cls: type[T]) -> T:
    """Recursively build a validated instance of `model_cls` from type-driven placeholder values.

    Iterates `model_cls.model_fields` (Pydantic's own field metadata)
    rather than anything specific to `ResumeAnalysisResult`, so this works
    for any Pydantic model passed as `response_model` — the whole point of
    `generate_structured` being generic over `T`. Constructing via
    `model_cls(**values)` (not `model_construct()`) means the result is
    fully validated, so it's guaranteed to satisfy `frozen=True`,
    `extra="forbid"`, and any field constraints (e.g. `ge=0, le=100`)
    exactly like a real provider's structured output would.
    """
    values = {
        name: _placeholder_value(field.annotation) for name, field in model_cls.model_fields.items()
    }
    return model_cls(**values)


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

    async def generate_structured(self, request: LLMRequest, response_model: type[T]) -> T:
        """Return a validated, generically-built placeholder instance of `response_model`.

        Matches `LLMGateway.generate_structured`'s signature exactly:
        takes the caller's target type and returns an instance of that
        same type, not an `LLMResponse`. Built via `_build_placeholder`,
        which fills every field with a type-appropriate empty/zero value
        (recursing into nested `BaseModel` fields) rather than using
        `response_model.model_construct()`: `model_construct()` leaves
        unsupplied required fields entirely absent from the instance, so
        any code that reads a nested attribute (e.g.
        `result.overall_assessment.overall_score`) hits an
        `AttributeError` immediately — unusable for actually exercising
        callers end-to-end. Filling in real (if trivial) values keeps the
        mock generic and free of domain knowledge — the values are chosen
        purely from each field's *type* (`0` for `int`, `""` for `str`,
        `[]` for `list`, a recursively-built placeholder for a nested
        `BaseModel`), never from what the field means — while producing
        something callers can actually use.
        """
        return _build_placeholder(response_model)

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
