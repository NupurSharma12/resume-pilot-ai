# Persistent Backend Workflow State

## Status
Planned

## Why this matters

ResumePilotAI currently uses in-memory backend stores for:

- Career Conversation sessions
- Tailoring plans

That works for local development, but it does not survive:

- backend restarts
- reloads
- redeploys
- multiple backend processes
- lost worker instances

As a result, the user can see data in the frontend cache while the backend has already forgotten it.

## Problem we want to solve

We want the backend to be the durable source of truth for:

- conversation history
- tailoring plan history
- selected suggestions
- edited suggestions
- final tailored resume
- validation results
- export metadata

This is necessary for both reliability and user trust.

## Desired behavior

After a refresh or later revisit, the user should be able to:

- reload their previous conversation
- see their tailoring history
- continue from where they left off
- avoid regenerating work unnecessarily
- recover safely after a temporary backend issue

## Current limitation

Today the backend stores workflow state in memory only.

That means conversation and tailoring history are only available while the exact backend process remains alive.

This is acceptable for early development, but not for a production workflow that users expect to return to later.

## Decision

Introduce persistent backend storage for workflow state.

The backend should own the long-term record of:

- career conversations
- tailoring plans
- user selections
- final tailored resume results

The frontend may keep a small session cache for convenience, but it should not be the source of truth.

## Expected outcome

With persistent backend storage:

- the user can return later and continue
- the app can show full history
- refreshes no longer depend on a single process lifetime
- stale plan/session errors are greatly reduced
- recovery flows become more reliable
- interview preparation can reuse the saved history later

## Scope note

This document does not implement the storage layer.

It records the product and architecture decision so that the current in-memory approach can be replaced with a durable backend store in a future sprint.