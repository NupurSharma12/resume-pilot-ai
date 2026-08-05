"""Production prompt builder: assembles an `LLMRequest` for the Resume Rewrite Engine (Stage 3).

`ResumeRewritePromptBuilder` owns the prompt engineering for turning one
`PlannedChange` (one line item from Stage 2's blueprint) into actual
rewritten resume text for that one section — the one stage in this
pipeline that is allowed to write prose, and only within the hard
constraints below. It performs no planning of its own (what to change and
why was already decided) and no validation of its own (whether the
result actually holds up is Stage 4's job) — it only assembles the
request.

One `LLMRequest` per `PlannedChange`, not one for the whole plan: the
Planner is this pipeline's single authority on what evidence may be used
(see `TailoringPlannerPromptBuilder`), so each rewrite call is scoped to
exactly the evidence that specific change was approved to use —
`evidence_store.catalog_text_for_ids(change.evidence_ids)`, never
`catalog_text()`'s full catalog. This is a structural guarantee, not just
an instruction: the Rewrite Engine cannot cite a fact it was never shown,
regardless of how the prompt is worded. See
`TailoringWorkflow._generate_rewrite`, which calls this once per change.
"""

from app.gateways.llm.models import LLMRequest
from app.models.evidence_store import EvidenceStore
from app.models.tailoring_plan import PlannedChange

_PLACEHOLDER_MODEL = "placeholder-model"
_TEMPERATURE = 0.3

_SYSTEM_PROMPT = """\
You are an experienced resume editor rewriting one section of a \
candidate's resume, executing a single, specific change a recruiter has \
already planned and approved. You are not an AI resume writer inventing \
an ideal candidate — you are improving the presentation of a real \
person's real, already-established experience. You do not decide what \
should change or why; that decision has already been made. Your job is \
to execute it well.

## You have been given a restricted evidence catalog

The Evidence Catalog below is NOT the candidate's full evidence store — \
it is only the evidence a recruiter's plan specifically approved for \
this one change. This is deliberate: you must never cite, in \
`supporting_evidence_ids`, any id that is not listed in this catalog. If \
producing a strong bullet for this change would benefit from a fact that \
isn't in this catalog, you do not have access to it — write a more \
modest bullet using only what's here instead. Do not invent an id, and \
do not guess that a fact might exist elsewhere in the candidate's \
history; if it isn't in the catalog below, treat it as unavailable.

## Absolute rules — never violate these

- Never invent experience, employers, job titles, dates, technologies, \
responsibilities, achievements, or metrics that are not present in the \
Evidence Catalog below.
- Never exaggerate scope, seniority, or impact beyond what the evidence \
actually supports.
- Never fabricate a number, percentage, or other metric. If the evidence \
does not state a number, do not write one — describe the outcome in \
words instead.
- Never add a technology, tool, or skill that is not named in the \
Evidence Catalog, even if it seems like a natural or likely companion to \
something that is.
- Never add a responsibility that is not named or clearly implied by the \
Evidence Catalog.

## What you ARE allowed to improve

Working only from what the Evidence Catalog actually says, you may \
improve: wording, sentence structure, ordering, emphasis, and clarity. \
You may combine two related facts from the catalog into one clearer \
bullet, as long as both are in the catalog you were given for this \
change. You may lead with what matters most for this job description \
among the evidence you have. None of that is invention — it is \
presentation of existing, approved facts.

## Cite your evidence

Every bullet you write must list, in `supporting_evidence_ids`, which \
ids from the Evidence Catalog below it is based on — and only ids from \
that catalog. This is not optional and not a formality — a downstream \
validation step will reject any bullet that cites an id outside this \
catalog, or that contains a claim-like detail not present in the \
evidence it cited. If you cannot ground a bullet in what you were given, \
do not write it — a shorter, fully-supported bullet is the correct \
output; a longer, partially-fabricated one is not.

## What you're producing

Produce exactly one resume section: the one named below, containing only \
the bullets that execute this specific planned change.\
"""


class ResumeRewritePromptBuilder:
    """Builds an `LLMRequest` for one `PlannedChange` (Stage 3) from the resume and its evidence.

    A plain class, not a `pydantic.BaseModel`, matching this codebase's
    established prompt-builder pattern — see `ResumeAnalysisPromptBuilder`
    for the full reasoning.
    """

    def build(
        self,
        resume: str,
        change: PlannedChange,
        evidence_store: EvidenceStore,
    ) -> LLMRequest:
        """Embed the original resume, one planned change, and its approved evidence only.

        `resume` is included in full (not just the section this change
        touches) so the model can see this section in its original
        surrounding context — useful for matching tone and structure to
        the rest of the resume — but the Evidence Catalog is deliberately
        restricted to `change.evidence_ids` via
        `evidence_store.catalog_text_for_ids`, not the full store: the
        resume provides *style* context, the catalog provides the only
        *facts* this call may draw on. All inserted with an f-string, not
        `str.format()`, for the same curly-brace-safety reason the other
        prompt builders use one.
        """
        user_prompt = (
            f"Original Resume (for context and structure only — every fact you use must "
            f"still come from the Evidence Catalog below, not from anything else in this "
            f"resume that isn't repeated there):\n{resume}\n\n"
            f"Planned Change:\n"
            f"  Section: {change.section}\n"
            f"  Action: {change.action.value}\n"
            f"  Reason: {change.reason}\n\n"
            f"Evidence Catalog (the ONLY evidence you may cite for this change):\n"
            f"{evidence_store.catalog_text_for_ids(change.evidence_ids)}"
        )
        return LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=_PLACEHOLDER_MODEL,
            temperature=_TEMPERATURE,
        )
