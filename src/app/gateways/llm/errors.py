"""Provider-agnostic error taxonomy every `LLMGateway` implementation classifies failures into.

`GatewayChain` (see `chain.py`) only knows how to make one decision: fall
back to the next provider, or stop immediately. It makes that decision by
`isinstance` on these two types, never by inspecting a provider SDK's own
exception types or HTTP status codes directly — that classification is
each concrete gateway's own responsibility (see `GeminiGateway` and
`OpenRouterGateway`), so the chain itself stays provider-agnostic and new
providers only need to satisfy this one contract to participate in
fallback correctly.
"""


class GatewayError(Exception):
    """Base class for errors an `LLMGateway` implementation raises after classifying a failure.

    Never raised directly — always one of the two subclasses below, so
    that catching `GatewayError` alone is never ambiguous about whether
    the caller should retry.
    """


class TransientGatewayError(GatewayError):
    """A retryable failure: rate limiting, quota exhaustion, a timeout, or a network error.

    Examples: HTTP 429, 503, 504, connection reset, connect/read timeout.
    `GatewayChain` falls back to the next configured provider when a
    gateway raises this.
    """


class PermanentGatewayError(GatewayError):
    """A non-retryable failure: an invalid request, an auth failure, or an invalid response.

    Examples: HTTP 400, 401, 403, a prompt/schema validation error, a
    response that fails to validate against the requested model.
    `GatewayChain` stops immediately when a gateway raises this — trying
    the next provider would very likely fail the same way, since the
    problem is with the request or its interpretation, not with any one
    provider's availability.
    """


class GatewayChainExhaustedError(GatewayError):
    """Raised when every gateway in a `GatewayChain` failed or was skipped for one call.

    Distinct from `TransientGatewayError`/`PermanentGatewayError`: this is
    the chain's own terminal failure, not a single provider's — there is
    no further fallback to attempt once this is raised. The original
    provider errors are not swallowed: this exception's `__cause__` is
    set to the last transient error encountered (via `raise ... from
    last_error`), so `str(exc.__cause__)` (never logged, only available
    to a caller/debugger) still carries the real underlying reason.
    """
