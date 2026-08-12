# Persistent Backend Workflow State

## Status
Implemented (Phase 3): the persistence abstraction (Phase 1: schema/store; Phase 2: PostgreSQL
backend) is now wired into the real application lifecycle and the real resume/tailoring workflow.
Interview Preparation, History UI, and multi-user/authorization remain future work -- see
"Phase 3 scope" below.

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

## Scope note (Phase 1 / 2)

Phases 1 and 2 defined and froze the persistence model without wiring it into the running
application: the `PersistenceStore` protocol, `InMemoryPersistenceStore`,
`PostgresPersistenceStore`, and the three-table schema (`resumes`, `resume_versions`,
`job_preparations`) all existed, fully tested, but nothing in `app.py` or any endpoint used them.
Phase 3 (below) is what actually connects this to the running app.

## Phase 3: application wiring

### Configuration: memory vs. postgres

`RESUMEPILOT_PERSISTENCE_BACKEND` selects the backend (`app.core.config.Settings.persistence_backend`):

- `memory` (default) -- `InMemoryPersistenceStore`. No `RESUMEPILOT_DATABASE_URL` required; a
  fresh clone runs with zero database configuration. State does not survive a process restart.
- `postgres` -- `PostgresPersistenceStore`, backed by one pooled `AsyncEngine`/`asyncpg`
  connection for the process's lifetime. Requires `RESUMEPILOT_DATABASE_URL`
  (`postgresql+asyncpg://...`); `build_persistence_store` (`app.persistence.factory`) raises a
  clear `ValueError` at startup if `postgres` is selected without it -- never a confusing failure
  on the first read/write.

Both backends satisfy the exact same `PersistenceStore` Protocol (`app.persistence.store`), so the
API layer below never branches on which one is configured.

### Application lifecycle

`create_app` (`app.app`) builds the configured store once, per app instance
(`app.state.persistence_store = build_persistence_store(settings)`) -- the same
process-lifetime-singleton treatment already given to `ConversationSessionStore`/
`TailoringPlanStore`. On shutdown, `lifespan` disposes it if it supports disposal:
`if isinstance(store, Disposable): await store.dispose()`, where `Disposable`
(`app.persistence.lifecycle`) is a small `runtime_checkable` Protocol with one method,
`async def dispose(self)`. `PostgresPersistenceStore` implements it (releases its connection
pool); `InMemoryPersistenceStore` does not (nothing to release), and is not forced to implement a
meaningless no-op just for symmetry.

### The `PersistenceStore` dependency

`app.persistence.dependencies.get_persistence_store(request)` returns
`request.app.state.persistence_store`, typed as the `PersistenceStore` Protocol -- mirroring
`get_conversation_session_store`/`get_tailoring_plan_store` exactly. Endpoints depend on this
Protocol, never on `InMemoryPersistenceStore`/`PostgresPersistenceStore` directly.

### Transient stores vs. durable persistence

`ConversationSessionStore` and `TailoringPlanStore` are unchanged: they still own in-flight,
per-request-sequence workflow state (an active Career Conversation session; a generated-but-not-
yet-applied tailoring plan), always in-process, regardless of `PERSISTENCE_BACKEND`. Persistence
is the separate, durable *historical* copy, written once a workflow boundary actually completes --
never a replacement for either transient store.

### What gets persisted, and where

All durable writes go through `app.orchestration.job_preparation_persistence` (a handful of plain
functions, not a service framework) called from three endpoint modules:

| Boundary | Endpoint | What's written |
|---|---|---|
| A + B + C: resume upload, job preparation, analysis | `POST /v1/analyze` | New `Resume` + `ResumeVersion(1, original_upload)` + `JobPreparation(draft -> active)` with `analysis_result` |
| D: career conversation | `POST /v1/career-conversation` (if it completes on turn one) or `POST /v1/career-conversation/{id}/answer` | `career_conversation`, once the session reaches `complete` |
| E: tailoring plan (generated half) | `POST /v1/tailoring-suggestions` | `tailoring_plan.generated_plan` (`selection` starts null) |
| E + F: tailoring plan (selection) + apply | `POST /v1/tailoring-suggestions/{plan_id}/apply` | One new `ResumeVersion(applied)`, `applied_resume_version_id`, and `tailoring_plan.selection` |
| G: post-apply analysis | `POST /v1/tailoring-suggestions/{plan_id}/reanalyze` | `post_apply_analysis` (`analysis` + `comparison` + `reanalyzed_at`) |

`POST /v1/analyze` is where boundaries A, B, and C collapse into one request: this backend is
otherwise stateless per call (no separate "upload" endpoint exists -- resume text extraction
happens client-side), so `/analyze` is the first point resume text and a job description arrive
together. It always creates a brand-new `Resume` -- no attempt is ever made to match an uploaded
resume against a prior one.

The resulting `job_preparation_id` is returned as an additive, optional field on
`AnalyzeResumeResponse`. A caller that wants the later boundaries (D-G) recorded threads it through
exactly once more: as an optional `job_preparation_id` on `StartConversationRequest` and
`GenerateSuggestionsRequest`. From there it rides along on the existing transient state
(`ConversationSession.job_preparation_id`, `StoredPlan.job_preparation_id`) the same way
`job_description` already does -- `/answer`, `/apply`, `/export`, and `/reanalyze` never need it
re-sent. Omitting it anywhere is a no-op, not an error: every existing request/response field is
unchanged, so current frontend behavior is unaffected by this phase. Threading this id through the
actual frontend session state is Phase 4 work.

**Completion is deliberately never triggered automatically.** The frozen rule
(`completed -> applied_resume_version_id IS NOT NULL`) is a necessary condition enforced by the
store, not a trigger -- nothing in today's product has an explicit "mark this preparation done"
action, so Phase 3 leaves every preparation `active` after apply/reanalyze rather than inventing one.

**Idempotency:** there is no retry/idempotency mechanism at this layer, matching the rest of the
application today (e.g. `/apply` has none either). A retried `/analyze` call creates a second,
independent `Resume`; a retried `/apply` call creates a second `ResumeVersion` and moves the
applied-version link to it. This is a documented, deliberate non-goal for this phase, not an
oversight -- see the Phase 3 report for the full reasoning.

**Transactionality:** each `PersistenceStore` method call is its own transaction (see
`PostgresPersistenceStore`'s module docstring); a multi-step boundary like `/analyze`
(create resume -> create version -> create preparation -> save analysis) is *not* wrapped in one
outer transaction. If a later step fails, earlier steps' writes are not rolled back -- see the
Phase 3 report's "transaction/atomicity behavior" section for exactly what durable state remains
in each failure case, for both `/analyze` and `/apply`.

## Scope note (product decision)

This document also records the original product and architecture decision: the backend should own
the durable source of truth for conversation history, tailoring history, and resume versions,
while the frontend's own session cache stays a convenience copy, not the source of truth. That
decision is now implemented as described above.
