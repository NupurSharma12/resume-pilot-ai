"""Provider-agnostic data contracts for the LLM gateway.

These models define the shape of requests to, and responses from, any LLM
provider (Gemini, OpenAI, Claude, Ollama, ...). They contain no provider
logic, no I/O, and no validation rules that are specific to a given
provider's API — that belongs in the provider adapters that will implement
the gateway protocol against these contracts.
"""

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    """Token accounting for a single LLM call, as reported by the provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_tokens: int = Field(description="Tokens consumed by the input (system + user prompt).")
    completion_tokens: int = Field(description="Tokens generated in the model's output.")
    total_tokens: int = Field(description="Total tokens billed for the call.")


class Cost(BaseModel):
    """Monetary cost of a single LLM call, as computed from provider pricing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_cost: float = Field(description="Total cost of the call, in USD.")


class LLMRequest(BaseModel):
    """A provider-agnostic request to generate a completion from an LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system_prompt: str | None = Field(
        default=None, description="Optional system-level instruction for the model."
    )
    user_prompt: str = Field(description="The user-facing prompt sent to the model.")
    model: str = Field(description="Identifier of the model to use, as named by its provider.")
    temperature: float = Field(
        description="Sampling temperature; valid range/semantics are provider-defined."
    )
    max_tokens: int | None = Field(
        default=None, description="Upper bound on generated tokens, if constrained."
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Free-form key/value context for tracing, tagging, or routing.",
    )
    response_schema: type | None = Field(
        default=None,
        description="Optional type the response content should conform to, for structured output.",
    )


class LLMResponse(BaseModel):
    """A provider-agnostic response returned from an LLM call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(description="The generated text content.")
    provider: str = Field(
        description="Name of the provider that served the request (e.g. 'openai')."
    )
    model: str = Field(description="Identifier of the model that produced the response.")
    usage: TokenUsage | None = Field(
        default=None, description="Token usage for the call, if the provider reports it."
    )
    cost: Cost | None = Field(
        default=None, description="Computed cost of the call, if pricing is available."
    )
    latency_ms: float = Field(
        description="Observed end-to-end latency of the call, in milliseconds."
    )
    finish_reason: str | None = Field(
        default=None,
        description="Provider-reported reason generation stopped (e.g. 'stop', 'length').",
    )
