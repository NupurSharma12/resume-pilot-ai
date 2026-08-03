# Tailored Resume - Planning

## Goal

Generate a recruiter-ready resume customized for a specific Job Description.

This is NOT a simple LLM rewrite.

It should behave like an experienced recruiter interviewing the candidate.

---

## Problem

Resumes rarely contain everything a candidate has done.

Example

Candidate says

"I don't know React."

Reality

- Built React dashboard
- Used Hooks
- Used TypeScript
- Built Components
- Used API integration

The experience exists.

The resume simply does not mention it.

---

## Principle

Do NOT ask

"Do you know React?"

Instead

Infer experience from

- Resume
- Projects
- Job Description

Then ask intelligent follow-up questions.

---

## AI Behaviour

The AI should behave like an interviewer.

Example

AI

"I noticed you worked on a React dashboard.

Were those reusable components?"

User

"Yes."

AI

"Did the UI fetch backend APIs?"

User

"Yes."

AI

"Did you use Hooks?"

User

"Yes."

AI

"Did you maintain application state?"

User

"Yes."

The AI now has enough confidence to improve the resume.

---

## Confidence Model

Every important JD skill should have

High Confidence

Medium Confidence

Low Confidence

Unknown

Low confidence skills trigger clarification questions.

---

## Resume Tailoring Flow

Resume

↓

JD

↓

Resume Analysis

↓

Skill Gap Detection

↓

Generate Clarification Questions

↓

Candidate Answers

↓

Update Candidate Knowledge

↓

Generate Tailored Resume

↓

Candidate Review

↓

Export PDF / DOCX

---

## Future Feature

Skill Evidence Engine

Instead of

React
Yes / No

Generate

Evidence

✓ Built Components

✓ Used Hooks

✓ REST APIs

✓ TypeScript

Confidence

Medium

Need 2 more answers

---

## Guiding Principle

The AI should never quiz the user.

It should help the user remember forgotten experience.

The goal is to uncover existing evidence, not invent experience.