# Multi-LLM Resilience

## Goal

ResumePilotAI should never fail because a single LLM provider is unavailable.

Users should experience uninterrupted analysis.

---

## Motivation

Free-tier APIs frequently return

- Rate limits
- Quota exhaustion
- Temporary outages

Instead of showing an error immediately, ResumePilotAI automatically retries using another provider.

---

## Provider Chain

Primary

Gemini

↓

Secondary

OpenRouter (Gemma → Qwen → Llama → DeepSeek, tried internally — see
"OpenRouter Model-Level Fallback" below)

↓

Future

OpenAI

Claude

Local Ollama

↓

Mock Gateway

---

## Principles

- Workflows stay provider agnostic
- Prompt builders remain unchanged
- Endpoints remain unchanged
- Gateway owns all retry/fallback logic

---

## Retry Policy (provider chain)

`GatewayChain` (`gateways/llm/chain.py`) decides whether to move from one
*provider* (Gemini, OpenRouter, Mock) to the next.

Retry (fall back to the next provider)

- 429
- timeout
- network failure
- 503
- 504

Do not retry (stop the chain immediately)

- validation failures
- authentication failures
- malformed requests

---

## OpenRouter Model-Level Fallback

OpenRouter's free-tier catalog is unreliable in ways a single fixed model
can't absorb on its own: individual free models get rate-limited, retired,
or (observed in production) silently return HTTP 200 with empty
`message.content` for reasoning-style models under long structured-output
prompts. Rather than let any one free model's bad day take down the whole
"openrouter" leg of the provider chain and fall straight through to Mock,
`OpenRouterGateway` (`gateways/llm/openrouter_gateway.py`) is configured
with an **ordered list** of models —
`RESUMEPILOT_OPENROUTER_MODELS` (default: Gemma → Qwen → Llama → DeepSeek)
— and tries them itself, one at a time, entirely internally. From
`GatewayChain`'s point of view, "openrouter" is still a single provider
that either succeeds or fails exactly as before; nothing about the
provider-level chain above changed.

```
OpenRouter
    │
    ▼
 Gemma  ──(429 / 5xx / timeout / empty response / malformed JSON / ValidationError)──▶  Qwen
                                                                                          │
                                                                    (same failure modes)  ▼
                                                                                        Llama
                                                                                          │
                                                                    (same failure modes)  ▼
                                                                                      DeepSeek
                                                                                          │
                                                            (all four models exhausted)   ▼
                                                                          TransientGatewayError
                                                                        → GatewayChain falls back
                                                                          to the next provider (Mock)
```

**Retry the next model on:**

- timeout / network error
- HTTP 429
- any HTTP 5xx
- an empty response (no `choices`, or empty/null `message.content` —
  this is the specific failure mode that motivated this feature)
- malformed JSON in a 200 response body
- a `pydantic.ValidationError` from `generate_structured`'s schema check

That last one is a deliberate broadening of the provider-chain policy
above: at the *provider* level, a validation failure still stops the
chain immediately (the request is assumed broken, and every provider
would fail the same way). At the *model* level within OpenRouter, a
schema-validation failure is instead treated as "this particular free
model didn't follow the embedded schema well enough this time" — a
different model has a real chance of doing better — and is retried
against the next configured model.

**Do not retry the next model on** (fail fast instead):

- authentication failure (HTTP 401/403)
- bad request (HTTP 400)
- invalid API key

These describe a problem with the request or credentials, which every
other OpenRouter model would fail identically against — trying the rest
of the list would only add latency, not fix anything.

**Once every configured model has failed a retryable way**, `OpenRouterGateway`
raises a single `TransientGatewayError` — exactly as it would have with
only one model configured — so `GatewayChain` falls back to the next
provider in the chain (Mock, by default) exactly as it did before this
feature existed.

**Structured logging** (all via the existing `structlog`-based logger,
same style as `GatewayChain`'s own per-attempt events, never logging
prompt/response content):

- `openrouter_model_attempt_started` — one per model tried
- `openrouter_model_failed` — a model's attempt failed a retryable way
- `openrouter_model_fallback` — logged between two attempted models
  (`from_model` / `to_model`), mirroring `GatewayChain`'s `gateway_fallback`
- `openrouter_model_succeeded` — the model that produced the final result
- `openrouter_model_chain_summary` — one terminal event on success
  (`models_tried`, `successful_model`, `attempts`, `total_elapsed_ms`)
- `openrouter_model_chain_exhausted` — one terminal event if every model failed

---

## Benefits

- Better user experience
- Higher availability
- Easier experimentation
- Future enterprise deployment