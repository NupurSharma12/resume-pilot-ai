ResumePilotAI — History Checkpoints & Simplified Persistence Design

Status

Decision stage — architecture agreed in principle, implementation not started.

History should preserve meaningful checkpoints in a user's preparation journey so that failures in LLM providers, network, quota, or browser sessions do not erase useful progress.

The design should remain simple, understandable, queryable, and easy to render.

1. The Four Product Checkpoints

A single JobPreparation represents one resume + JD preparation journey.

Checkpoint 1 — Initial Analysis

After resume + JD are provided and the initial analysis completes.

Persist:

resume identity/reference

JD/job-preparation identity

initial analysis

timestamp/status

Checkpoint 2 — Career Conversation

After the career conversation completes.

Persist the conversation because it contains valuable candidate-specific context and may later support interview preparation.

It belongs to the same JobPreparation and does not create a ResumeVersion.

Checkpoint 3 — Tailoring Plan

After tailoring suggestions/plan generation completes.

Persist:

generated tailoring plan

suggestions

relevant selection/edited decisions when available

There is still no new ResumeVersion at this point. The preparation still operates against the same active/original resume.

Checkpoint 4 — Re-analysis / Comparator

After:

selected changes are applied

the resulting resume is persisted as a new ResumeVersion

the updated resume is re-analyzed

before/after comparison is produced

Persist:

re-analysis result

comparison

relationship to the newly created applied ResumeVersion

timestamp/status

2. Critical ResumeVersion Principle

Checkpoints are not ResumeVersion records.

Until changes are actually applied, all checkpoints relate to the same resume version.

Conceptually:

Resume
  |
  +-- ResumeVersion 1 (original / active)
  |
  +-- JobPreparation
        |
        +-- Checkpoint 1: Initial Analysis
        |
        +-- Checkpoint 2: Career Conversation
        |
        +-- Checkpoint 3: Tailoring Plan
        |
        +-- Checkpoint 4: Re-analysis / Comparator
                  |
                  +-- ResumeVersion 2 (applied tailored resume)

A checkpoint does not create a ResumeVersion. A new ResumeVersion exists only when the user actually applies/generates a changed resume.

3. Why Checkpoints Belong Inside JobPreparation

Mental model:

Resume = candidate resume identityJobPreparation = one resume + one JD preparation journeyCheckpoints = milestones inside that preparation

Do not introduce a separate top-level history/version entity unless a concrete requirement forces it.

4. Preferred Database Direction

Keep the existing three core tables:

resumes
resume_versions
job_preparations

Add only the minimum state needed to represent the four milestones, preferably within the JobPreparation aggregate.

Conceptually:

job_preparations
----------------
id
resume_id
job_title
company
job_description

status

initial_analysis
career_conversation
tailoring_plan
post_apply_analysis

applied_resume_version_id

created_at
updated_at

These are conceptual, not a final schema prescription. The implementation must inspect the existing frozen schema and propose the smallest safe delta.

5. JSON Philosophy

Do not introduce JSON merely because it is flexible.

JSON/JSONB remains appropriate for naturally structured LLM outputs such as:

analysis result

tailoring plan

comparison

conversation payload

But JSON should not become an excuse to avoid modeling real relationships.

Do not build a generic event store.

6. Search Requirements

History search should remain deliberately simple.

We need to find:

a resume / resume identity

a JobPreparation

associated JD/company/job information

the preparation's checkpoint history

We do not need search inside:

conversations

analysis JSON

tailoring suggestions

comparator output

A simple UI is enough:

History

Resume: Senior Software Engineer Resume
Company / Role: Example Company — Staff Engineer
Last updated: ...

  ✓ Initial Analysis
  ✓ Career Conversation
  ✓ Tailoring Plan
  ✓ Re-analysis

[Open Preparation]

Partial progress:

✓ Initial Analysis
✓ Career Conversation
○ Tailoring Plan
○ Re-analysis

7. Consistency Model

History must never claim a checkpoint is complete when its durable payload was not successfully persisted.

For example:

VALID:
checkpoint = CAREER_CONVERSATION
career_conversation = persisted payload

INVALID:
checkpoint = CAREER_CONVERSATION
career_conversation = null

Checkpoint completion should therefore be derived from persisted state or updated atomically with the payload.

8. Failure / Recovery Goal

Example:

Upload resume + JD
        ↓
Initial analysis succeeds
        ↓
Career conversation succeeds
        ↓
Tailoring plan succeeds
        ↓
LLM quota exhausted

History should show:

✓ Initial Analysis
✓ Career Conversation
✓ Tailoring Plan
○ Re-analysis

Another example:

Apply tailoring
        ↓
New ResumeVersion created
        ↓
Re-analysis fails because provider is unavailable

History should not claim re-analysis completed:

✓ Initial Analysis
✓ Career Conversation
✓ Tailoring Plan
✓ Tailored Resume
○ Re-analysis

The newly created ResumeVersion still exists and can be associated with the preparation.

9. Tailored Resume vs Re-analysis

The user-facing history has four major checkpoints, but internally the third/fourth stages include:

Tailoring Plan
      ↓
Apply changes
      ↓
NEW ResumeVersion
      ↓
Re-analysis

Do not treat the tailored resume as merely another checkpoint snapshot. Preserve the actual ResumeVersion relationship.

10. Explicitly NOT Building

Do not introduce:

event sourcing

generic history_events

generic checkpoints framework

arbitrary checkpoint types

per-checkpoint tables

generic repository abstractions

full-text history search

complicated resume-version graphs

history analytics

authentication/ownership as part of this change

11. Architecture

Keep the current architecture:

FastAPI endpoint
      ↓
thin application/orchestration layer
      ↓
PersistenceStore
      ↓
    +---------+
    |         |
  Memory   PostgreSQL/Neon

Checkpoint meaning belongs to the JobPreparation domain, not the persistence adapter.

The adapter stores/retrieves models; it should not contain product semantics about what a career conversation means.

12. Questions Claude Must Resolve Before Coding

What is the smallest schema change that represents the four checkpoints?

Should completion be represented by nullable payloads, explicit status fields, a small enum/status, or another simple mechanism?

How should career conversation be represented without unnecessary tables?

How should tailoring plan and post-apply comparison remain structured and typed?

How should partially completed preparations appear in History?

How should an applied ResumeVersion relate to JobPreparation?

How do we preserve consistency if one persistence operation succeeds and the next fails?

Can necessary writes be atomic where appropriate without violating the existing PersistenceStore abstraction?

What is the minimum future API surface needed by History UI?

Does the design remain compatible with both memory and PostgreSQL backends?

Claude should not implement immediately if schema implications are unclear. First present the proposed schema/API delta and reasoning for review.

13. Current Architectural Preference

Keep JobPreparation as the history aggregate. Add only the minimum durable state necessary to represent the four checkpoints. Keep ResumeVersion independent and create it only when a resume is actually changed/applied. Avoid a generic checkpoint/history framework.

Optimize for:

clarity > flexibility > abstraction

14. Next Step

First commit and merge:

feat/persistence-phase3-wiring

Then create:

feat/job-preparation-checkpoints

Claude should first review this document and the current schema/codebase, propose the exact schema/API delta, and only then implement after the proposal is reviewed.