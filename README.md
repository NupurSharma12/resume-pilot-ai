# ResumePilotAI

> Helping professionals tell the right story for the job they want.

ResumePilotAI is an AI-powered career intelligence platform that goes beyond traditional ATS resume checkers.

Most resume tools simply compare keywords between a resume and a job description. ResumePilotAI is designed to understand the candidate's complete career, identify missing evidence, coach the candidate through recruiter-style conversations, and eventually generate tailored resumes that accurately reflect their experience for each job.

Our goal is simple:

> **A resume is not a person's career. It is a compressed summary of it. ResumePilotAI helps professionals tell that story according to what a specific job actually demands.**

---

# Vision

ResumePilotAI is being built as an AI Career Coach.

Instead of only answering:

> "How well does my resume match this JD?"

it will answer:

- Why is my resume not getting interview calls?
- Which experience am I failing to communicate?
- Which parts of my career actually matter for this role?
- What evidence is missing?
- What projects should I highlight?
- How can I rewrite my resume without inventing experience?
- How should I prepare for interviews?

Eventually ResumePilotAI should become an intelligent career companion rather than another ATS checker.

---

# Current Features

## Resume Upload

- Upload PDF
- Upload DOCX
- Upload TXT
- Upload Markdown

Entirely client-side extraction.

---

## Job Description Input

- Paste Job Description
- Upload PDF
- Upload DOCX
- Upload TXT
- Upload Markdown

---

## AI Resume Analysis

Analyzes

- Overall Match
- ATS Compatibility
- Technical Match
- Experience Match
- Domain Match

Generates

- Executive Summary
- Why this Score
- Top Strengths
- Top Risks
- Skill Match
- Missing Skills
- Resume Improvements
- Recruiter-style Recommendations

---

## Career Conversation

Instead of asking generic interview questions, ResumePilotAI starts an adaptive recruiter-style conversation.

The AI asks:

- clarification questions
- missing evidence questions
- leadership questions
- ownership questions
- architecture questions

The goal is **not interviewing**.

The goal is **recovering valuable career evidence that never made it into the resume.**

Example:

Resume says

> Built React dashboard.

Career Conversation asks

> I noticed you built a React dashboard.
>
> Did you own the architecture?
>
> Did you work with Redux?
>
> Was this customer-facing?
>
> Did you work with REST APIs?
>
> Did you optimize performance?

The candidate slowly reconstructs forgotten experience.

---

## Intelligent Conversation

The AI can now:

- answer clarification questions
- acknowledge corrections
- continue naturally
- remember previous answers
- stop automatically when enough evidence has been collected

This makes the conversation feel much closer to speaking with an experienced recruiter than filling out a questionnaire.

---

## Interactive Resume Tailoring (NEW)

ResumePilotAI does not rewrite resumes automatically. It proposes small,
evidence-backed edit **suggestions** — one existing bullet at a time —
that the candidate reviews and individually approves before anything
changes. Nothing is invented: every suggestion must be traceable to the
original resume, the resume analysis, or the Career Conversation
transcript.

Three endpoints, matching the review workflow:

1. `POST /v1/tailoring-suggestions` — generates a plan of minimal edit
   suggestions (`append`, `insert_before`/`insert_after`, `update`,
   `replace`, `remove`, `add_emphasis` — never a whole-section rewrite),
   each with a reason, cited evidence, and a validation status.
2. `POST /v1/tailoring-suggestions/{plan_id}/apply` — applies only the
   suggestions the candidate selected (plus any custom instructions),
   deterministically, and returns the final resume and a validation
   report.
3. `POST /v1/tailoring-suggestions/{plan_id}/export` — downloads the
   final resume as TXT, Markdown, DOCX, or PDF, honestly labeled as
   content-faithful or freshly regenerated (no original PDF/DOCX layout
   is ever preserved — see the feature doc for why).

The frontend's Tailored Resume page walks through five stages: Generate
Tailoring Plan → Review Suggestions → Custom Instructions → Apply
Selected Changes → Preview and Download. See
`docs/features/interactive-tailored-resume.md` for the full pipeline,
domain model, and API design (supersedes the earlier whole-section
`docs/features/tailoring-engine.md`, kept for historical context).

---

# Current Architecture

```
Resume
      │
      ▼
Resume Parser
      │
      ▼
Job Description
      │
      ▼
Resume Analysis
      │
      ▼
Career Conversation
      │
      ▼
Evidence Recovery
      │
      ▼
Tailored Resume
      │
      ▼
Interview Preparation
```

---

# Technology Stack

Backend

- Python 3.12
- FastAPI
- Pydantic
- Google Gemini
- structlog
- pytest
- Ruff

Frontend

- React
- TypeScript
- Tailwind CSS
- React Router

Infrastructure

- Docker
- Docker Compose

---

# Multi-LLM Architecture

ResumePilotAI uses a provider-independent gateway, chained for automatic
failover: `GatewayChain` (`gateways/llm/chain.py`) tries each configured
provider in order and falls back to the next one only on a transient
failure (rate limit, quota, timeout, 5xx) — never on a validation/auth/bad-
request error, which fails the same way on every provider. Configured via
`RESUMEPILOT_PRIMARY_PROVIDER` / `_SECONDARY_PROVIDER` / `_TERTIARY_PROVIDER`
(see `.env`); every workflow depends on exactly one `LLMGateway` interface
and is unaffected by how many providers are actually behind it.

Implemented providers

- Google Gemini (native structured output via JSON Schema)
- OpenRouter (JSON-object mode + prompt-embedded schema; free models only
  by default, an ordered fallback list configurable via
  `RESUMEPILOT_OPENROUTER_MODELS` — `OpenRouterGateway` tries each model in
  turn internally on a retryable failure (timeout, 429, 5xx, empty
  response, malformed JSON, schema-validation failure) before the
  "openrouter" provider itself is considered failed; see
  `docs/features/multi-llm-resilience.md`)
- Mock (deterministic, no network — a valid chain tier on its own, e.g.
  for local dev/tests)

Planned providers

- OpenAI
- Anthropic Claude
- Groq
- Ollama (local)

---

# Project Layout

```
src/

app/
    api/
    agents/
    core/
    evidence/
    gateways/
    ingestion/
    models/
    parsers/
    prompts/
    sessions/
    workflows/

frontend/

docs/

tests/
```

---

# Development

Backend

```
uv sync

uv run uvicorn src.app.app:create_app --factory --reload
```

Frontend

```
cd frontend

npm install

npm run dev
```

---

# Testing

Backend

```
uv run pytest

uv run ruff check .

uv run ruff format --check .
```

Frontend

```
npm run lint

npx tsc --noEmit

npm run build
```

---

# Docker

```
docker compose up --build
```

API

```
http://localhost:8000
```

Health

```
GET /v1/health
```

---

# Roadmap

## ✅ Sprint 1
Foundation

## ✅ Sprint 2
Provider-agnostic LLM Gateway

## ✅ Sprint 3
Resume Parsing

## ✅ Sprint 4
Job Description Parsing

## ✅ Sprint 5
Resume Analysis Engine

- ATS Match
- Technical Match
- Executive Summary
- Why this Score

## ✅ Sprint 6
Career Conversation

Adaptive recruiter-style conversations for evidence recovery.

## ✅ Sprint 7
Multi-LLM Failover

Automatic fallback across multiple LLM providers, including per-model
fallback within OpenRouter's free-tier catalog (Gemma → Qwen → Llama →
DeepSeek). See `docs/features/multi-llm-resilience.md`.

## ✅ Sprint 8
Evidence-Based Tailoring Engine

Generates a recruiter-ready resume using:

- Resume
- JD
- Resume Analysis
- Evidence recovered during the Career Conversation

without inventing experience, technologies, dates, responsibilities,
achievements, or metrics. Every change is planned before it's written,
and every written bullet is validated against its cited evidence before
it's returned — see `docs/features/tailoring-engine.md` (superseded, kept
for historical context).

## ✅ Interactive Resume Tailoring

Replaced the whole-section Tailoring Engine above with a review-and-approve
workflow: small, evidence-backed edit suggestions the candidate selects
individually, rather than an automatic rewrite. Adds deterministic
apply-time conflict detection, per-suggestion evidence revalidation for
user edits, and downloadable exports (TXT/Markdown/DOCX/PDF) with honest
formatting-fidelity labels. See
`docs/features/interactive-tailored-resume.md`.

## 🚧 Sprint 9
Interview Coach

Generate:

- technical interview questions
- behavioural questions
- architecture discussions

based on the recovered evidence.

## 🚧 Sprint 10
Evaluation & Observability

- Prompt evaluation
- Quality scoring
- Hallucination detection
- Cost tracking
- Performance metrics

## 🚧 Sprint 11
Production Deployment

- Authentication
- Persistence
- History
- Resume Library
- Cloud deployment

---

# Long-Term Vision

Most resume tools answer:

> "How well does your resume match the job?"

ResumePilotAI aims to answer a much more important question:

> "How can you best communicate your real career to maximize your chances of getting the interview?"

Our philosophy is simple:

> **Don't invent experience. Recover it.**

People rarely fail interviews because they lack experience.

They fail because their resume never communicated the experience they already had.

ResumePilotAI is being built to solve exactly that problem.