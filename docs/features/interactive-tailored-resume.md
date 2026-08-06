# Interactive Resume Tailoring

## Vision

ResumePilotAI should not simply rewrite resumes.

It should behave like an experienced recruiter who:

- identifies gaps
- explains why they matter
- suggests improvements
- lets the user decide what to change
- produces a final recruiter-ready resume

The user always remains in control.

---

# Problem

Current Tailoring Engine immediately rewrites sections.

Problems:

- feels like AI is changing the user's resume
- difficult to trust
- difficult to understand
- no way to selectively accept suggestions

---

# Product Principles

1. Never invent experience.
2. Every suggestion must be evidence-backed.
3. User stays in control.
4. AI acts as an editor, not an author.
5. Final output should be downloadable.

---

# Target Experience

Resume
        ↓
Analysis
        ↓
Career Conversation
        ↓
Tailoring Plan
        ↓
Interactive Review
        ↓
Tailored Resume
        ↓
Download

---

# Stage 1 — Tailoring Plan

Already implemented.

Output:

- Expand bullets
- Add emphasis
- Add missing skills
- Update summary

Each suggestion includes:

- reason
- evidence
- confidence

---

# Stage 2 — Interactive Review (Next)

Instead of automatically rewriting:

☑ Expand Labellerr Bullet

Reason:
Microsoft values recent React experience.

Evidence:
Conversation Turn 2

Preview:
"Maintained hands-on..."

[Accept]

-------------------

☐ Add FastAPI

Reason:
Backend requirement

Evidence:
Conversation Turn 6

[Accept]

The user selects what should be applied.

---

# Stage 3 — AI Resume Rewrite

Only accepted suggestions are sent to the Rewrite Agent.

Input:

Resume
+
Accepted Suggestions

Output:

Updated Resume

---

# Stage 4 — User Instructions

Allow free-text instructions.

Examples:

- Keep resume under 2 pages.
- Remove Cisco.
- Make Adobe first.
- Reduce Product wording.
- Focus on backend.

These instructions become additional rewrite constraints.

---

# Stage 5 — Resume Validation

Run Validation Agent again.

Verify:

- evidence grounded
- formatting
- no hallucinations
- JD alignment

---

# Stage 6 — Export

Generate:

- PDF
- DOCX
- Markdown

Same format as uploaded whenever possible.

---

# Future

## Interview Preparation

After tailoring:

Generate:

- recruiter questions
- technical interview questions
- system design topics
- coding topics
- behavioural questions
- project deep-dives
- LeetCode recommendations

This becomes the next stage of ResumePilotAI.

Pipeline:

Resume
↓

Tailor

↓

Interview Prep

↓

Practice

---

# Success Criteria

The user should feel:

"I understand exactly why every change was suggested."

instead of

"The AI rewrote my resume."