# Recruiter Fit Engine

## Vision

ResumePilotAI should not behave like a keyword matcher.

It should behave like an experienced recruiter.

The objective is not to maximize the Resume Match score.

The objective is to estimate the probability that a recruiter would shortlist the candidate.

---

# Problem

Most resume tools answer:

"How similar is this resume to the job description?"

This produces misleading results.

Example

Job Description

Experience Required

4-6 years

Candidate

15 years

Traditional ATS

Excellent Match

Real Recruiter

Potentially overqualified.

May reject before interview.

Resume similarity and recruiter fit are different problems.

---

# Product Principle

ResumePilotAI should optimize for

Recruiter Fit

instead of

Keyword Match.

---

# Two Independent Scores

The product should eventually expose two scores.

## Resume Match

Measures

- Skills
- Technologies
- Domain knowledge
- Responsibilities
- Keywords

Question answered

"How well does the resume match the JD?"

---

## Recruiter Fit

Measures

- Experience range
- Mandatory requirements
- Preferred requirements
- Seniority
- Role expectations
- Hiring risk
- Overqualification
- Underqualification

Question answered

"How likely is a recruiter to shortlist this candidate?"

---

# Experience Scoring

Experience should not be linear.

More experience is not always better.

Example

JD

4-6 years

Suggested scoring

4-6

100%

6-8

90%

8-12

75%

12+

60%

Likewise

Candidate below required experience receives a stronger penalty.

The scoring curve should resemble recruiter behaviour rather than mathematical comparison.

---

# Mandatory vs Preferred Skills

Every JD requirement should be classified into one of two groups.

Mandatory

Preferred

Missing mandatory skills should reduce Recruiter Fit significantly.

Missing preferred skills should reduce the score only slightly.

Example

Mandatory

React

TypeScript

REST APIs

Node.js

Preferred

Docker

Redis

GraphQL

A missing mandatory skill should never be treated the same as a missing preferred skill.

---

# Explainability

The score should always explain itself.

Example

Recruiter Fit

74%

Reasons

✓ Strong distributed systems experience

✓ Leadership background

✗ Missing Kubernetes

✗ Missing Node.js

✗ Experience exceeds target range

---

# Potential Score

ResumePilotAI should estimate

Current Score

Potential Score

Example

Current Recruiter Fit

72%

Potential Recruiter Fit

91%

Gap

19%

The gap should be explained.

Example

Improve evidence for

- React
- REST APIs
- Docker

Clarify project ownership

Mention production scale

---

# Evidence Recovery

A missing skill should never immediately be treated as absent.

The AI should first determine whether evidence simply isn't present.

Example

Instead of asking

"Do you know React?"

Ask

"What UI did you build?"

Then

"Were reusable components involved?"

Then

"Did the UI call backend APIs?"

Then

"Did you use Hooks?"

The AI should infer skills through conversation.

---

# AI Interview

ResumePilotAI should interview the candidate.

The goal is not to test knowledge.

The goal is to recover forgotten experience.

Candidates frequently under-report their own work.

The AI should identify hidden evidence before concluding that a skill is missing.

---

# Resume Generation

Resume generation should happen only after

Resume Analysis

↓

Recruiter Fit

↓

Evidence Recovery

↓

Clarification Questions

↓

Updated Candidate Knowledge

↓

Resume Rewrite

↓

Final Recruiter Fit

The rewritten resume should be based only on verified information supplied by the candidate.

No fabricated experience should ever be introduced.

---

# Long-term Goal

ResumePilotAI should become an AI Recruiting Coach rather than an AI Resume Writer.

The product should help candidates

- understand recruiter expectations,
- identify genuine gaps,
- recover forgotten experience,
- improve resume quality,
- and apply only when Recruiter Fit is genuinely high.