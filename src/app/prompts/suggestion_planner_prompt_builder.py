"""Production prompt builder: assembles an `LLMRequest` for the Suggestion Planner (Stage 2).

`SuggestionPlannerPromptBuilder` owns the prompt engineering for deciding
*what* should change about a resume, *why*, and *which specific item* it
targets — never the rewritten text itself (that's Stage 3's job; see
`SuggestionRewritePromptBuilder`). This is the finer-grained successor to
`TailoringPlannerPromptBuilder` (superseded — see
`docs/features/tailoring-engine.md`): where that class asked "which whole
section should change," this one asks "which single existing item should
this one small edit target," and is explicit that multiple independent
changes must never be bundled into one suggestion.
"""

from app.gateways.llm.models import LLMRequest
from app.models.evidence_store import EvidenceStore
from app.models.resume_analysis import ResumeAnalysisResult
from app.models.resume_structure import StructuredResume

_PLACEHOLDER_MODEL = "placeholder-model"
_TEMPERATURE = 0.2

_SYSTEM_PROMPT = """\
You are an experienced technical recruiter planning small, targeted \
edits to a candidate's resume for a specific job description. You are \
not writing the resume. You are producing a list of individually \
reviewable suggestions that a separate step will turn into text, and \
that the candidate will accept or reject one at a time.

## Make the smallest possible change

Every suggestion must target exactly one existing resume item (never a \
whole section) and propose the smallest edit that would meaningfully \
improve fit for this job description. Prefer `append` (add a few words \
to an existing line), `insert_before`/`insert_after` (add one new \
bullet next to an existing one), or `update` (revise part of an \
existing bullet). Use `replace` only when no lighter operation could \
express the needed change, and say so explicitly in `reason`. Use \
`remove` only when a specific existing item is genuinely irrelevant to \
this job, and say why. Use `add_emphasis` only to reorder or reword an \
item's *existing* claims to foreground them — never to add a new claim.

## Never bundle independent changes together

If two facts are independently true and independently useful, they are \
two separate suggestions, not one. For example, adding "React" and \
adding "Python" to a skills line are two suggestions unless they only \
make sense as one indivisible phrase (e.g. "built with React and \
TypeScript" describing one specific piece of work). A reviewer must be \
able to accept one and reject the other; if bundling them together would \
make that impossible, they are not one suggestion.

This applies just as much to a summary or objective statement as it \
does to a skills line. Never propose one giant "rewrite the summary" \
suggestion that folds several unrelated pieces of evidence into a \
single block of new text -- split it into one `append` (or `update`) \
per independent piece of evidence, each targeting the same item, so \
the candidate can accept some and reject others. For example, if the \
evidence catalog and job description separately support that the \
candidate has (a) people-management experience, (b) hands-on AI-native \
tooling experience, (c) incident-response / reliability experience, and \
(d) cross-team leadership experience, and the summary item doesn't yet \
mention any of them, propose four separate suggestions -- "Add people \
management evidence", "Add AI-native tooling evidence", "Add \
incident-response / reliability evidence", "Add cross-team leadership \
evidence" -- each its own `append` (or `insert_after`) targeting that \
same summary item's id, each citing only the evidence it draws on, \
rather than one suggestion that rewrites the whole summary to mention \
all four at once. Only merge two pieces of evidence into a single \
suggestion when they are not independently meaningful on their own \
(e.g. a metric that only makes sense attached to the achievement it \
measures).

## Target a real, existing item

Every suggestion must set `target_item_id` to one of the exact item ids \
listed in the Resume Structure below — never invent an id, never target \
a whole section. You may only propose changes to items that already \
exist; you may not invent an entirely new section.

## Ground every change in real evidence

You are never inventing new facts, technologies, dates, responsibilities, \
achievements, or metrics — you are only deciding how to better surface \
facts that are already established in the Evidence Catalog below. Every \
suggestion's `evidence_ids` must cite at least one real id from that \
catalog and must never be empty. If a gap identified in the prior resume \
analysis has no corresponding evidence in the catalog, do not propose a \
change to address it.

## Custom instructions are constraints, never evidence

If the candidate provided custom instructions below, treat them only as \
constraints on *which* changes to propose or avoid (e.g. "keep the \
resume under two pages," "do not remove Adobe experience," "make the \
summary more engineering-focused") — never as a source of new facts. An \
instruction can never justify inventing something not in the Evidence \
Catalog.

## Prioritize by impact

Order your proposed edits by how much each one would improve this \
resume's demonstrated fit for this specific job description, weighing \
the prior resume analysis's identified gaps and weaknesses most heavily. \
Prefer a smaller number of well-justified, high-impact edits over many \
marginal ones.\
"""


class SuggestionPlannerPromptBuilder:
    """Builds an `LLMRequest` for Stage 2 (the Suggestion Planner) from the tailoring context.

    A plain class, not a `pydantic.BaseModel` — matching this codebase's
    established prompt-builder pattern (see `ResumeAnalysisPromptBuilder`).
    """

    def build(
        self,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        evidence_store: EvidenceStore,
        structured_resume: StructuredResume,
        custom_instructions: str | None,
    ) -> LLMRequest:
        """Embed the job description, prior analysis, resume structure, and evidence catalog.

        `structured_resume` is rendered as an explicit id-to-text catalog
        (see `_format_structure`) so the model can cite real
        `target_item_id`s directly, the same way `evidence_store.catalog_text()`
        lets it cite real evidence ids. All inserted with an f-string, not
        `str.format()`, so naturally occurring curly braces in any of
        this text can't be misread as template placeholders — the same
        reasoning as every other prompt builder in this codebase.
        """
        user_prompt = (
            f"Job Description:\n{job_description}\n\n"
            f"Prior Resume Analysis — Weaknesses:\n"
            f"{self._format_weaknesses(resume_analysis)}\n\n"
            f"Prior Resume Analysis — Recommended Improvements:\n"
            f"{self._format_improvements(resume_analysis)}\n\n"
            f"Resume Structure (target ids you may cite in target_item_id):\n"
            f"{self._format_structure(structured_resume)}\n\n"
            f"Evidence Catalog (cite ONLY these ids in evidence_ids):\n"
            f"{evidence_store.catalog_text()}\n\n"
            f"Candidate's custom instructions (constraints only, never evidence):\n"
            f"{custom_instructions or 'None provided.'}"
        )
        return LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=_PLACEHOLDER_MODEL,
            temperature=_TEMPERATURE,
        )

    @staticmethod
    def _format_structure(structured_resume: StructuredResume) -> str:
        if not structured_resume.sections:
            return "The resume could not be broken into sections."
        lines = []
        for section in structured_resume.sections:
            lines.append(f"[{section.section_id}] {section.heading or '(no heading)'}")
            for item in section.items:
                lines.append(f"  [{item.item_id}] {item.text}")
        return "\n".join(lines)

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
