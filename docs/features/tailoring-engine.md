# Tailoring Engine (superseded)

> **Superseded.** `POST /v1/tailor-resume` and everything below describe the
> original whole-section rewrite pipeline. It has been removed from the
> codebase and replaced by the Interactive Resume Tailoring feature — see
> [`docs/features/interactive-tailored-resume.md`](interactive-tailored-resume.md)
> for the pipeline as it exists today: per-item edit *suggestions* a user
> reviews and approves, not an automatic section rewrite. This document is
> kept for historical context (the two-call-per-change pattern, the
> evidence-scoping guarantee, and the validation approach described below
> were all carried forward, refined, into the new pipeline) — nothing on
> this page reflects the current API or domain model.

Sprint 12 shipped `POST /v1/tailor-resume`. This document describes the
pipeline as implemented, replacing the earlier design brainstorms
(`docs/features/tailoring_engine_1.md`, `docs/tailored-resume-planning.md`
— kept for historical context, superseded by this document).

## Vision

A resume is not a person's career. It is a compressed summary of that
career. The biggest problem experienced professionals face is not lack of
experience — it is that years of valuable work never make it into the
resume because of page limits, forgotten projects, changing roles, or the
need to tailor for different job descriptions.

## Core principle

This is **not** an AI resume writer. It is an **Evidence-Based Resume
Tailoring Engine**.

Every modification made to a resume must be supported by evidence that
already exists, either in the original resume or in the Career
Conversation. The engine never invents experience, technologies, dates,
responsibilities, achievements, or metrics.

---

## Pipeline

```
Resume
      │
      ▼
Resume Analysis
      │
      ▼
Career Conversation
      │
      ▼
Evidence Store          <- pure aggregation, no LLM call
      │
      ▼
Tailoring Planner        <- LLM call #1: decides WHAT/WHY, never writes text
      │
      ▼
Resume Rewrite Engine     <- LLM call #2: writes text, grounded in the plan
      │
      ▼
Validation                <- pure checking, no LLM call
      │
      ▼
Tailored Resume
```

Only two of the five pipeline stages call an LLM at all — the Planner and
the Rewrite Engine — and they call it in a deliberately asymmetric way.
**The Planner is this pipeline's single authority on what evidence may be
used**: it makes one `generate_structured` call and is shown the entire
Evidence Store. **The Rewrite Engine executes, it doesn't decide**: it
makes one `generate_structured` call *per planned change*, and each call
is shown only the evidence that specific change was approved to use — not
the full store. This isn't just a prompt instruction; the restricted
evidence is all the Rewrite Engine is ever given, so it is structurally
incapable of citing a fact the Planner didn't approve for that change,
regardless of how the prompt is worded. Stage 4 then re-checks the same
guarantee explicitly, as defense in depth (see Stage 4 below). Evidence
Store construction and Validation are both deterministic Python, by
design: trusting an LLM to build its own citable-fact catalog, or to
grade its own (or another model's) work, would reintroduce exactly the
hallucination risk this pipeline exists to prevent.

Implementation: `src/app/workflows/tailoring_workflow.py`
(`TailoringWorkflow`), composing `src/app/evidence/evidence_store_builder.py`,
`src/app/prompts/tailoring_planner_prompt_builder.py`,
`src/app/prompts/resume_rewrite_prompt_builder.py`, and
`src/app/evidence/tailoring_validator.py`.

### Stage 1 — Evidence Store

`EvidenceStoreBuilder.build(resume, job_description, resume_analysis,
conversation_history)` combines everything already established about the
candidate into one flat catalog of atomic, independently-citable
`EvidenceItem`s (`src/app/models/evidence_store.py`). Nothing is
rewritten, scored, or judged here — it's the "facts database" every later
stage cites from.

Evidence ids follow a stable, human-readable scheme so a Validation
Report or plan reads naturally:

| id | source |
|---|---|
| `resume-full-text` | the original resume, verbatim |
| `analysis-summary` | the resume analysis's overall summary |
| `analysis-strength-{n}` | one per `resume_analysis.strengths` entry |
| `analysis-matching-project-{n}` | one per `resume_analysis.matching_projects` entry |
| `analysis-skill-match-{category-slug}` | one per skill category with at least one matched skill |
| `conversation-turn-{n}` | one per completed Career Conversation exchange |

Only *positive*, already-established facts become evidence.
`resume_analysis.weaknesses` and `.resume_improvements` describe gaps,
not facts about the candidate, so they're deliberately excluded from the
catalog itself — a later stage can't cite "this is missing" as support
for a claim. They're still passed to the Planner as context (so it knows
*why* something might be worth changing), just not as citable evidence.

A Career Conversation session is useful additional evidence, not a hard
requirement: `conversation_history` may be empty.

### Stage 2 — Tailoring Planner

`TailoringPlannerPromptBuilder` + one `generate_structured` call against
`TailoringPlan` (`src/app/models/tailoring_plan.py`). The planner's only
job is deciding what should change, why, and which evidence supports it —
it never writes resume text. Each `PlannedChange` has:

```
section: str            # e.g. "Summary"
action: TailoringAction  # rewrite | expand | reorder | trim | add_emphasis | remove
reason: str              # why this improves fit for the job description
evidence_ids: list[str]  # references into the Evidence Store; never empty
```

`TailoringWorkflow._validate_plan_evidence` enforces, in Python (not
trusted to the model), that every `PlannedChange.evidence_ids` is
non-empty and every id it lists actually exists in the Evidence Store —
mirroring how `CareerConversationWorkflow._validate_decision` enforces its
own cross-object invariant. A violation raises
`TailoringPlanInvalidEvidenceError` and the pipeline stops before the
Rewrite Engine is ever called — there's no point writing text from a plan
that already failed its own grounding check.

### Stage 3 — Resume Rewrite Engine

`ResumeRewritePromptBuilder` + one `generate_structured` call **per
`PlannedChange`**, against `TailoredSection` (`src/app/models/tailored_resume.py`)
— not one call for the whole plan. `TailoringWorkflow._generate_rewrite`
loops `plan.changes`, and for each one, the prompt embeds:

- the full original resume (for style/structure context only — matching
  tone and section layout, never a source of facts to cite), and
- `evidence_store.catalog_text_for_ids(change.evidence_ids)` — **only**
  the evidence that specific change was approved to use, never
  `catalog_text()`'s full catalog.

Rules enforced by the prompt (and checked by Stage 4, not just asked for):

- Never invent information.
- Never exaggerate.
- Never fabricate metrics.
- Never add unsupported technologies.
- Never add unsupported responsibilities.

The rewrite may only improve wording, ordering, emphasis, clarity, and
readability, using existing evidence. Every `TailoredBullet` must cite the
`supporting_evidence_ids` it's based on — this is what Stage 4 checks.

### Stage 4 — Validation

`validate_tailored_resume` (`src/app/evidence/tailoring_validator.py`) is
pure Python — not another LLM call. It operates on a list of
`RewrittenChange`, each pairing one `PlannedChange` with the
`TailoredSection` the Rewrite Engine produced for it — this pairing is
what makes the second check below possible. For every proposed bullet, in
order:

1. Reject if it cites no evidence at all.
2. Reject if it cites an evidence id that the Planner did not approve
   *for the specific change that produced this bullet* — not merely a
   real id somewhere in the Evidence Store. A bullet cannot borrow
   another change's approved evidence just because that evidence happens
   to be real; the Planner is this pipeline's single evidence authority,
   and this check is what makes that a validated guarantee rather than
   only a prompt instruction (see Stage 3's evidence-scoping above, which
   makes this violation structurally unreachable in practice — this
   check exists anyway, as defense in depth).
3. Reject if it contains a claim-like term (a technology, tool, metric, or
   other proper-noun-style detail) that doesn't appear anywhere in the
   text of the evidence it specifically cited — not just anywhere in the
   whole store. A bullet can't borrow support from evidence it didn't
   actually reference.

Two or more `PlannedChange`s can legitimately target the same section
heading (e.g. a "rewrite" and a later "add_emphasis" change, both for
"Summary"); their accepted bullets are merged under one `TailoredSection`
per distinct heading in the final `TailoredResume`.

The term-extraction heuristic (`_claim_terms`) is deliberately
conservative, not real NLP: a word is treated as a claim if it's an
ALL-CAPS acronym, contains a digit (a version, a percentage, a year), or
is capitalized outside a short list of common resume-bullet vocabulary
(action verbs, articles, prepositions). The bullet's first word is never
treated as a claim, since resume bullets conventionally open with a
past-tense action verb, and matching every possible verb by an exhaustive
list is both fragile and prone to tense mismatches between a bullet
("Containerized...") and its evidence ("...I used Docker to
containerize..."). This over-flags some ordinary words as needing
evidence rather than under-flags a real hallucination — a rejected but
actually-fine bullet is a far cheaper mistake than an accepted
fabrication.

Nothing is silently kept. Every proposed bullet is accounted for in the
`ValidationReport`: it either contributes to the final `TailoredResume`
(counted in `accepted_count`) or appears in `rejected_bullets` with a
specific reason. A section left with zero accepted bullets is dropped
from the output entirely, rather than kept as an empty, misleading
heading.

---

## API

`POST /v1/tailor-resume`

Request (`TailorResumeRequest`, `src/app/api/v1/models/tailor_resume.py`):

```json
{
  "resume": "...",
  "job_description": "...",
  "resume_analysis": { "...": "exactly what POST /v1/analyze returned" },
  "career_conversation": { "...": "exactly what the Career Conversation endpoints return" }
}
```

Response (`TailorResumeResponse`):

```json
{
  "tailored_resume": { "sections": [ { "heading": "...", "bullets": [ { "text": "...", "supporting_evidence_ids": ["..."] } ] } ] },
  "tailoring_plan": { "changes": [ { "section": "...", "action": "rewrite", "reason": "...", "evidence_ids": ["..."] } ] },
  "validation_report": { "total_bullets": 0, "accepted_count": 0, "rejected_count": 0, "rejected_bullets": [], "passed": true }
}
```

The Evidence Store itself is never part of the response — it's the
pipeline's internal facts database (Stage 1's output, consumed by Stages
2 and 3), not a public contract.

Error handling matches `analyze.py`/`career_conversation.py`'s existing
convention exactly: the endpoint logs and re-raises any exception via a
bare `raise`, letting FastAPI's default handling produce the response (an
uncaught exception becomes an HTTP 500). There is no special status-code
mapping for `TailoringPlanInvalidEvidenceError` or a validation-schema
failure — a bullet that fails Stage 4's validation is not an error; it's
reported in `validation_report` inside a normal `200` response. Only a
genuine pipeline failure (the LLM's plan cites nonexistent evidence, a
gateway failure, a schema-validation failure) produces a `500`.

---

## Structured logging

All events follow the same `structlog` pattern already used by
`ResumeAnalysisWorkflow`/`CareerConversationWorkflow`/`GatewayChain`:
snake_case event names, structured kwargs, `elapsed_ms` on every
completion event, never resume/JD/evidence/plan/bullet content.

| event | level | when |
|---|---|---|
| `tailoring_started` | INFO | pipeline entry |
| `evidence_store_built` | INFO | Stage 1 complete (`evidence_item_count`, `conversation_turn_count`) |
| `tailoring_plan_generated` | INFO | Stage 2 complete (`change_count`) |
| `tailoring_plan_validation_failed` | ERROR | Stage 2's structured output failed schema validation |
| `resume_rewritten` | INFO | Stage 3 complete (`section_count`, `bullet_count`) |
| `resume_rewrite_validation_failed` | ERROR | Stage 3's structured output failed schema validation |
| `validation_completed` | INFO | Stage 4 complete (`total_bullets`, `accepted_count`, `rejected_count`, `passed`) |
| `tailoring_completed` | INFO | pipeline exit (`elapsed_ms`, `change_count`, `accepted_bullet_count`, `rejected_bullet_count`) |
| `tailor_resume_request_received` / `_completed` / `_failed` | INFO/ERROR | endpoint-level, matching `analyze_request_*`'s pattern |

---

## Tradeoffs and future work

- **Closed gap: evidence misattribution across planned changes.** An
  earlier version of this pipeline sent the Rewrite Engine the *entire*
  Evidence Store in one call covering the whole plan, and Stage 4 only
  checked that a cited id was *some* real id in the store — which meant a
  bullet could cite real evidence that was approved for a *different*
  change than the one that produced it (e.g. splicing an unrelated
  conversation turn into a bullet because it happened to contain a
  matching keyword). This is now closed two ways: structurally, each
  Rewrite Engine call only ever sees `catalog_text_for_ids(change.evidence_ids)`
  for its own change, and, as defense in depth, Stage 4 checks a bullet's
  cited ids against `RewrittenChange.change.evidence_ids` specifically,
  not just `EvidenceStore` membership.
- **The Rewrite Engine is grounded, but not verified word-by-word by
  Stage 4 for anything beyond claim-like terms.** The validator catches
  fabricated technologies, metrics, unknown evidence citations, and
  cross-change evidence borrowing; it does not perform full semantic
  entailment checking (e.g. a subtly exaggerated *degree* of involvement
  that reuses only words already present in the cited evidence — "I'm
  familiar with X" evidence being written up as "Owned X" — would still
  pass, since the term "X" is textually present). A stronger future
  version could add an LLM-based "recruiter review" self-critique pass —
  deliberately not built in this sprint to keep Validation a pure, fast,
  deterministic check with no additional hallucination surface of its own.
- **One tailored resume per request, no versioning.** `ROADMAP.md`'s
  Phase 3 "Multiple Resume Versions" item is still open.
- **No persistence.** Like Career Conversation's session store, nothing
  about a tailoring run is stored server-side; the response is the only
  record.
