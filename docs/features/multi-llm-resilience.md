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

OpenRouter Free Models

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

## Retry Policy

Retry

- 429
- timeout
- network failure
- 503
- 504

Do not retry

- validation failures
- authentication failures
- malformed requests

---

## Benefits

- Better user experience
- Higher availability
- Easier experimentation
- Future enterprise deployment