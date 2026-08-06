# Interview Preparation Engine

**Status:** Planned

**Owner:** ResumePilotAI

**Depends on:**
- Resume Analysis Engine
- Career Conversation Engine
- Tailoring Engine

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