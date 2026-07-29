# ADR-001

## Title

Provider Agnostic LLM Gateway

## Status

Accepted

## Context

The application will support multiple LLM providers
(OpenAI, Gemini, Claude and local models).

Business logic should not depend on any vendor SDK.

## Decision

Introduce a Gateway layer responsible for all
communication with LLM providers.

All agents communicate only with the gateway.

## Consequences

Advantages

- Easy provider switching
- Easier testing
- Centralized retries
- Unified logging
- Cost tracking
- Better observability

Tradeoffs

- One extra abstraction layer