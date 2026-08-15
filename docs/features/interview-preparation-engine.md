# Interview Preparation Engine

**Status:** Partially implemented (v1) — see "Implementation status (v1)" below.
Everything past that section is the original, still-aspirational vision this
v1 was deliberately scoped down from; it has not been rebuilt or replaced.

**Owner:** ResumePilotAI

**Depends on:**
- Resume Analysis Engine
- Career Conversation Engine
- Tailoring Engine

---

# Implementation status (v1)

What's actually shipped today, intentionally much smaller than the "AI
Skills"/"Long-Term Vision" sections below:

- **Persistence**: one JSONB column, `job_preparations.interview_preparation`
  — no new table, no new checkpoint timestamp. Belongs to the same
  `job_preparation_id` throughout its lifecycle.
- **Domain model** (`src/app/models/interview_preparation.py`):
  `InterviewPreparationResult` — `system_design_questions`,
  `coding_questions`, `behavioral_questions` (each `BehavioralQuestion`
  tagged `career_conversation` or `suggested`, per `BehavioralQuestionSource`),
  `generated_at`, and `stage` (`InterviewPreparationStage`).
- **Three-stage lifecycle**, one API endpoint
  (`POST /v1/job-preparations/{id}/interview-preparation`,
  `src/app/api/v1/endpoints/interview_preparation.py`) that inspects what's
  already persisted and performs exactly the incremental work newly
  justified — never a blind full regeneration:
  1. `initial` — resume + job description alone, available immediately
     after Resume Analysis. One LLM call
     (`InterviewPreparationWorkflow.generate`).
  2. `career_conversation_enriched` — once the Career Conversation
     completes, behavioral questions are re-derived deterministically from
     the transcript (**zero LLM calls** —
     `InterviewPreparationWorkflow.enrich_with_career_conversation`), while
     `system_design_questions`/`coding_questions` are carried over
     unchanged.
  3. `tailoring_aligned` — once a tailored resume is applied, one LLM call
     scoped to technical questions only
     (`InterviewPreparationWorkflow.enrich_with_tailoring`, structured
     output `GeneratedTechnicalPreparation`), grounded in the applied
     resume plus a digest of the selected tailoring suggestions'
     `reason` text. `behavioral_questions` is carried over unchanged.
- **Generation is never automatic** — no LLM call fires as a side effect of
  Resume Analysis, Career Conversation, or Apply completing; a user must
  explicitly click "Generate"/"Update Interview Preparation."
- **Frontend**: reachable two ways, both reading/writing the same
  persisted guide via the same two existing endpoints (`GET
  /v1/job-preparations/{id}`, the `POST` above) — no interview-preparation-
  specific state lives in `ResumeSessionContext`:
  - `InterviewPreparationPage` (`/interview-preparation`), reachable from
    the Sidebar as soon as `resumeAnalysis` exists (same gating as
    Tailored Resume) — the *active* preparation, keyed by the session's
    current `jobPreparationId`.
  - History's own Interview Preparation card, for inspecting a *past*
    preparation.
  - Both render through one shared component,
    `frontend/src/components/InterviewPreparationCard.tsx`, including a
    maturity badge ("Initial preparation" / "Updated from Career
    Conversation" / "Aligned with your tailored resume") driven by
    `stage` (`frontend/src/lib/interviewPreparationStage.ts`).

Deliberately not built in v1 (all still true of everything below this
section): Interview Blueprint, Coding Preparation Planner as a distinct
skill, System Design Planner as a distinct skill, Project Deep Dive
Generator, Weakness Detector, Preparation Roadmap, Mock Interview Agent,
company-specific behavior, round-count prediction. What v1 calls "system
design" and "coding" questions are the closest existing equivalents to
Skills 4–5 below, generated as part of the same one/zero-call state
machine above, not as independent skills.

---

# Vision

ResumePilotAI should not stop after tailoring a resume.

A candidate who has a tailored resume should immediately know:

- What interview rounds to expect
- Which topics to prepare
- Which coding questions are likely
- Which projects will be discussed
- Which behavioural questions they will be asked
- Where their weaknesses are
- How to spend the next few days preparing

The Interview Preparation Engine transforms a tailored resume into a personalized interview preparation strategy.

The goal is not to generate random interview questions.

The goal is to simulate what **this candidate** is most likely to face for **this job**.

---

# Problem Statement

Most interview preparation tools generate generic questions.

Examples:

- Top 20 React Questions
- Top 50 NodeJS Questions
- Top Amazon Questions

These ignore:

- the candidate's experience
- the resume
- the target company
- the job description
- the candidate's strengths
- the candidate's weaknesses

As a result, candidates spend time preparing topics that may never be asked while missing the questions that recruiters are actually likely to ask.

ResumePilotAI already possesses rich candidate context.

The Interview Preparation Engine should leverage that context.

---

# Goals

Generate interview preparation that is:

- personalized
- evidence-based
- company-aware
- role-aware
- experience-aware
- actionable

Every recommendation should answer:

> Why should the candidate prepare this?

---

# Inputs

The engine consumes information produced by previous ResumePilotAI stages.

## Resume

Candidate's original resume.

---

## Resume Analysis

Including:

- strengths
- weaknesses
- missing qualifications
- recruiter score
- improvement suggestions

---

## Career Conversation

Structured evidence recovered from recruiter-style conversations.

Includes:

- technical depth
- leadership examples
- cloud experience
- architecture discussions
- AI experience
- behavioural evidence

---

## Tailoring Plan

What changes were recommended.

Why they were recommended.

Which areas of the JD mattered most.

---

## Tailored Resume

The final resume that will actually be used during interviews.

---

## Job Description

Used to determine:

- expected technologies
- interview depth
- responsibilities
- leadership expectations

---

## Company

Optional.

Different companies interview differently.

Examples:

- Microsoft
- Google
- Adobe
- Amazon
- Zscaler

---

# Architecture

```
Resume
        │
Resume Analysis
        │
Career Conversation
        │
Tailoring Engine
        │
Interview Preparation Engine
```

Internally:

```
Interview Blueprint Generator
            │
            ▼
Technical Question Generator
            │
            ▼
Behaviour Question Generator
            │
            ▼
Coding Preparation Planner
            │
            ▼
System Design Planner
            │
            ▼
Project Deep Dive Generator
            │
            ▼
Weakness Detector
            │
            ▼
Preparation Roadmap
```

---

# AI Skills

The engine consists of several independent AI skills.

---

# Skill 1 — Interview Blueprint Generator

## Purpose

Predict the interview structure before generating any questions.

### Inputs

- Job Description
- Company
- Experience Level
- Tailored Resume

### Output

InterviewBlueprint

Example

- Number of rounds
- Technical vs Behavioural weightage
- Coding importance
- System Design importance
- Leadership importance

Example

```
Round 1
Technical Screening

Round 2
Coding

Round 3
System Design

Round 4
Behaviour

Round 5
Hiring Manager
```

---

# Skill 2 — Technical Question Generator

## Purpose

Generate questions based on:

- technologies required
- technologies present on resume
- evidence recovered during Career Conversation

Instead of

> Explain React Hooks.

Ask

> You mentioned using React and TypeScript at Labellerr while remaining hands-on despite being a Product Manager. Walk me through the architecture of one feature you implemented.

---

# Skill 3 — Behaviour Question Generator

Uses Career Conversation evidence.

Instead of

> Tell me about a conflict.

Ask

> During Labellerr you described convincing stakeholders to adopt AI-powered annotation workflows. How did you handle disagreements?

These become recruiter-quality behavioural questions.

---

# Skill 4 — Coding Preparation Planner

Purpose

Recommend coding preparation.

Outputs

- LeetCode patterns
- Difficulty
- Topics
- Estimated preparation time

Example

```
Priority

Sliding Window

Binary Search

Graphs

Dynamic Programming

Medium level

Expected preparation

6–8 hours
```

---

# Skill 5 — System Design Planner

For senior candidates.

Determine whether System Design preparation is required.

Generate preparation topics.

Examples

- Distributed Systems
- Caching
- Messaging
- Scalability
- Availability
- Observability
- Event-driven Architecture

---

# Skill 6 — Project Deep Dive Generator

One of the most valuable skills.

Identify projects most likely to be discussed.

For each project generate:

- Architecture questions
- Trade-off questions
- Failure scenarios
- Scaling questions
- Metrics questions
- Alternative designs

Example

Resume Analyzer

Possible interviewer questions

- Why FastAPI?
- Why dependency injection?
- Why protocol-based gateways?
- How would you scale LLM requests?
- How do you prevent hallucinations?
- Why not combine Tailoring and Rewrite into one prompt?

---

# Skill 7 — Weakness Detector

Use

- Resume Analysis
- Tailoring Plan
- Career Conversation

to identify weak areas.

Example

```
Weak Areas

Docker

Azure

Kubernetes

Distributed Systems

Leadership Metrics
```

Each weakness should include

- why it matters
- probability of being asked
- recommended preparation

---

# Skill 8 — Preparation Roadmap

Produce a practical preparation plan.

Example

```
Today

Revise React

Tomorrow

Practice Binary Search

Weekend

System Design

Before Interview

Behaviour Questions

Mock Interview
```

Candidates should know exactly what to prepare next.

---

# Future Skill — Mock Interview Agent

Future enhancement.

The engine conducts live interviews.

Capabilities

- Voice support
- Follow-up questions
- Timers
- Scoring
- Feedback
- Confidence estimation
- Behaviour evaluation

---

# Outputs

The Interview Preparation Engine should produce:

## Interview Blueprint

Expected rounds.

---

## Technical Questions

Role-specific questions.

---

## Coding Plan

LeetCode topics.

Patterns.

Difficulty.

---

## System Design Plan

Topics to revise.

---

## Behaviour Questions

Grounded in Career Conversation evidence.

---

## Project Deep Dive

Likely discussion points.

---

## Weakness Report

Areas to strengthen before interviewing.

---

## Preparation Roadmap

Personalized study plan.

---

# Guiding Principles

## 1.

Never generate generic interview questions.

---

## 2.

Ground every question in candidate evidence.

---

## 3.

Explain why every recommendation exists.

---

## 4.

Prioritize quality over quantity.

Twenty realistic questions are better than one hundred generic ones.

---

## 5.

Be actionable.

Every weakness should include:

- why it matters
- probability
- recommended preparation

---

# Success Metrics

Candidates should feel:

- "These are exactly the questions I got."
- "The preparation roadmap was realistic."
- "The projects discussed matched my interview."
- "I knew where to spend my preparation time."

---

# Out of Scope

Current version does not include:

- Live mock interviews
- Voice interaction
- Video interviews
- Coding execution
- Whiteboard collaboration

These will be future enhancements.

---

# Long-Term Vision

ResumePilotAI becomes an end-to-end career assistant.

```
Resume
        │
Resume Analysis
        │
Career Conversation
        │
Tailoring Engine
        │
Interview Preparation Engine
        │
Mock Interview Agent
        │
Offer Readiness
```

The Interview Preparation Engine bridges the gap between a strong resume and interview success by converting candidate evidence into personalized preparation.
