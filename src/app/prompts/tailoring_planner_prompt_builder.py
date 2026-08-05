"""Production prompt builder: assembles an `LLMRequest` for the Tailoring Planner (Stage 2).

`TailoringPlannerPromptBuilder` owns the prompt engineering for deciding
*what* should change about a resume and *why* — never the rewritten text
itself (that's Stage 3's job; see `ResumeRewritePromptBuilder`). The
system prompt is explicit and repeated on this point because it is the
one most likely for a general-purpose model to drift from: asked to
improve a resume, a model's default instinct is to just write the
improved version. This prompt exists specifically to stop that instinct
one stage early, so an evidence citation is decided before any wording is.
"""

from app.gateways.llm.models import LLMRequest
from app.models.evidence_store import EvidenceStore
from app.models.resume_analysis import ResumeAnalysisResult

_PLACEHOLDER_MODEL = "placeholder-model"
_TEMPERATURE = 0.2

_SYSTEM_PROMPT = """\
You are an experienced technical recruiter planning how to tailor a \
candidate's resume for a specific job description. You are not writing \
the resume. You are producing a plan that a separate rewriting step will \
follow.

## Objective

Decide what should change about this resume, why it should change, and — \
for every single proposed change — exactly which pieces of evidence \
justify it. You will be given an Evidence Catalog: a numbered list of \
facts already established about this candidate, each with its own id. \
You may only cite ids that appear in that catalog. Never invent an \
evidence id, and never propose a change with no supporting evidence at \
all — every `PlannedChange` must cite at least one real id from the \
catalog.

## What you are deciding, per change

- `section`: which resume section this applies to (e.g. "Summary", or the \
name of a role/project already on the resume).
- `action`: the kind of change — rewrite, expand, reorder, trim, \
add_emphasis, or remove.
- `reason`: why this change would improve the resume's fit for this \
specific job description. Be specific about what gap it closes or what \
strength it surfaces — not generic advice.
- `evidence_ids`: every evidence catalog id that justifies this change.

## Ground every change in real evidence

You are never inventing new facts, technologies, dates, responsibilities, \
achievements, or metrics — you are only deciding how to better surface \
facts that are already established in the Evidence Catalog below. If a \
gap identified in the prior resume analysis has no corresponding evidence \
in the catalog (nothing in the resume or the conversation actually \
addresses it), do not propose a change to address it — there is nothing \
to ground it in, and a change with no real evidence is exactly what this \
plan must never produce.

## Prioritize by impact

Order your proposed changes by how much each one would improve this \
resume's demonstrated fit for this specific job description, weighing the \
prior resume analysis's identified gaps and weaknesses most heavily. \
Prefer a smaller number of well-justified, high-impact changes over many \
marginal ones.\
"""


class TailoringPlannerPromptBuilder:
    """Builds an `LLMRequest` for Stage 2 (the Tailoring Planner) from the tailoring context.

    A plain class, not a `pydantic.BaseModel` — matching `ResumeAnalysis
    PromptBuilder`/`CareerConversationPromptBuilder`'s established pattern
    (see either for why): this holds no state and validates nothing of
    its own.
    """

    def build(
        self,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        evidence_store: EvidenceStore,
    ) -> LLMRequest:
        """Embed the job description, prior analysis, and evidence catalog into the user prompt.

        `resume_analysis` is rendered as prose (weaknesses and
        recommended improvements only — the same "what's the gap"
        framing `CareerConversationPromptBuilder` uses, not the full
        result) so the planner reasons about *why* to change something
        the same way a recruiter briefing would; `evidence_store.catalog_text()`
        supplies the *only* facts it's allowed to cite as *why it's
        allowed*. All inserted with an f-string, not `str.format()`, so
        naturally occurring curly braces in any of this text can't be
        misread as template placeholders — the same reasoning as the
        other two prompt builders.
        """
        user_prompt = (
            f"Job Description:\n{job_description}\n\n"
            f"Prior Resume Analysis — Weaknesses:\n"
            f"{self._format_weaknesses(resume_analysis)}\n\n"
            f"Prior Resume Analysis — Recommended Improvements:\n"
            f"{self._format_improvements(resume_analysis)}\n\n"
            f"Evidence Catalog (cite ONLY these ids):\n{evidence_store.catalog_text()}"
        )
        return LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=_PLACEHOLDER_MODEL,
            temperature=_TEMPERATURE,
        )

    @staticmethod
    def _format_weaknesses(resume_analysis: ResumeAnalysisResult) -> str:
        if not resume_analysis.weaknesses:
            return "None identified."
        return "\n".join(f"- {weakness}" for weakness in resume_analysis.weaknesses)

    @staticmethod
    def _format_improvements(resume_analysis: ResumeAnalysisResult) -> str:
        if not resume_analysis.resume_improvements:
            return "None identified."
        return "\n".join(
            f"- [{improvement.section}] {improvement.recommendation} "
            f"(priority {improvement.priority})"
            for improvement in resume_analysis.resume_improvements
        )
