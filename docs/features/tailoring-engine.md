# Tailoring Engine Design

## Vision

A resume is not a person's career.

It is a compressed summary of that career.

The biggest problem experienced professionals face is not lack of experience—it is that years of valuable work never make it into the resume because of page limits, forgotten projects, changing roles, or the need to tailor for different job descriptions.

ResumePilotAI aims to recover the complete story of a person's career and then tell the right story for the job they are applying to.

---

# Core Principle

We never invent experience.

We only recover experience that already exists but is not reflected in the resume.

Every statement added to the tailored resume must be backed by evidence gathered during Career Conversation.

---

# Current Flow

Resume
+
Job Description

↓

Resume Analysis

↓

Career Conversation

↓

Tailored Resume

---

# Proposed Flow

Resume

↓

Resume Analysis

↓

Career Conversation

↓

Career Knowledge Base

↓

Evidence Selection

↓

Tailored Resume

---

# Career Knowledge Base

Career Conversation does not directly rewrite the resume.

Instead, it continuously builds a structured representation of the candidate's career.

Example

Career Profile

Experience

Projects

Leadership examples

Architecture examples

Technical skills

Product skills

Achievements

Metrics

Evidence

Confidence

Every conversation enriches this profile.

The profile becomes richer over time.

---

# Evidence Recovery

During Career Conversation the AI discovers hidden experience.

Example

Resume says

Worked as Product Manager.

Conversation discovers

• Built React UI
• Built FastAPI backend
• Integrated Gemini APIs
• Worked directly with founders
• Increased annotation productivity
• Led roadmap
• Conducted customer interviews
• Still wrote production code

None of these should disappear.

They become verified evidence.

Example

Recovered Evidence

React
confidence: High

FastAPI
confidence: High

LLM Integration
confidence: High

Founder Collaboration
confidence: High

Engineering Leadership
confidence: High

Hands-on Development
confidence: High

---

# Tailoring Philosophy

Different jobs require different parts of the same career.

Engineering Manager

Highlight

• Engineering leadership
• Architecture
• Backend systems
• React
• Python
• FastAPI

De-emphasize

• Roadmaps
• Product Strategy

-------------------------------------

Senior Product Manager

Highlight

• Product ownership
• Customer interviews
• Metrics
• Founder collaboration
• AI product design

De-emphasize

• React implementation
• Backend implementation

Same career.

Different story.

---

# Resume Generation

The Tailoring Engine receives

Current Resume

Career Knowledge Base

Job Description

Resume Analysis

It selects the most relevant verified evidence.

It rewrites the resume using only evidence supported by the Career Knowledge Base.

---

# Prompting Rules

The model must

• Never invent experience.

• Never fabricate technologies.

• Never exaggerate ownership.

• Prefer recovered evidence over generic statements.

• Maximize alignment with the target Job Description.

• Preserve chronology.

• Preserve factual accuracy.

---

# Candidate Approval

Before rewriting the resume the candidate should be able to review recovered evidence.

Example

✓ Built React application

✓ Worked with founders

✓ Built FastAPI APIs

✓ Conducted customer interviews

✓ Improved annotation speed by 40%

The candidate can

Accept

Reject

Edit

This keeps the generated resume trustworthy.

---

# Future Vision

Career Conversation becomes a long-term memory of the candidate's career.

The candidate never has to explain the same project twice.

Future conversations build on previously recovered evidence.

ResumePilotAI gradually becomes a personal AI Career Coach rather than just a resume rewriting tool.