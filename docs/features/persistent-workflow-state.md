Persistent Backend Workflow State

Status

Planned

Purpose

This document records the need for durable backend storage for ResumePilotAI workflow state.

Why this matters

The current backend workflow stores are in-memory.

That means important user state can disappear when:

the backend restarts

a process exits

a reload happens

multiple backend processes are running

a deployment replaces the running instance

For a workflow product, that is not durable enough.

What should be persisted

The backend should own the durable source of truth for:

career conversation history

tailoring plans

selected suggestions

edited suggestion text

applied phases

final tailored resume

resume analysis versions

export metadata

any recovery state needed to resume the workflow safely

What the frontend should do

The frontend can keep session state for convenience, but it should not be the only source of truth.

Frontend state should be treated as a cache or working copy, not as the permanent record.

What the backend must be able to restore

A user should be able to return later and recover:

their previous conversation

their tailoring plan

the current resume version

applied suggestions

the last analysis result

Why in-memory storage is not enough

In-memory storage is acceptable for early development, but it has these problems:

no recovery after restart

no history across sessions

no shared state across workers

hard-to-trust behavior during development reloads

no durable audit trail of edits

Recommended direction

Move workflow state to a persistent backend store.

The first persistent implementation could be lightweight, but it should support:

retrieving a conversation by session id

retrieving a tailoring plan by plan id

saving applied phases

saving resume versions

saving analysis versions

Expected outcome

With persistent workflow state:

refresh becomes safe

history becomes available

recovery becomes honest and reliable

future features like resume version comparison become possible

the product can support returning users cleanly

Scope note

This document does not implement the storage layer.

It records the architecture decision so the current in-memory approach can be replaced in a future sprint.