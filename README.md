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

## Career Conversation (NEW)

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
  by default, model configurable via `RESUMEPILOT_OPENROUTER_MODEL`)
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

## 🚧 Sprint 7
Multi-LLM Failover

Automatic fallback across multiple LLM providers.

## 🚧 Sprint 8
Tailored Resume Generation

Generate a recruiter-ready resume using:

- Resume
- JD
- Evidence recovered during conversation

without inventing experience.

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