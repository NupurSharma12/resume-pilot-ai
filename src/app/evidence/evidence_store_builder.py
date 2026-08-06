"""Stage 1 of the Tailoring Engine: builds the Evidence Store.

`EvidenceStoreBuilder` combines the original resume (at per-item
granularity — see below), the prior resume analysis, and the Career
Conversation transcript into one flat `EvidenceStore` — the "facts
database" every later stage cites from. Per the pipeline's explicit
design, nothing here rewrites, rephrases, scores, or judges anything:
every `EvidenceItem` this class produces is a fact already established by
an earlier stage (resume text as submitted, analysis-confirmed
strengths/projects/matched-skills, or a candidate's own conversation
answer), copied through close to verbatim. If it isn't already true
somewhere else, it doesn't belong here.

Every resume item gets its own evidence entry (`resume-{item_id}`), not
just one whole-document blob — this is what lets a suggestion cite
*exactly* which existing bullet it's grounded in, and what lets
Validation say "supported by the original resume" with a real,
checkable citation rather than a vague appeal to the whole document. A
single whole-document item (`resume-full-text`) is still included
alongside the per-item ones, for the rare case a suggestion is
genuinely about something holistic (e.g. overall years of experience)
that no single item states on its own — citing it is allowed, just not
preferred (see `SuggestionPlannerPromptBuilder`'s system prompt).

Only *positive*, already-established facts become evidence items —
`resume_analysis.weaknesses` and `resume_analysis.resume_improvements`
describe gaps, not facts about the candidate, so they are deliberately
excluded from the Evidence Store itself (a later stage can't cite "this is
missing" as support for a claim). They're still available as context to
the Tailoring Planner via the full `resume_analysis` object passed
alongside the store — see `SuggestionPlannerPromptBuilder` — just not as
citable evidence.
"""

import re

from app.models.career_conversation import ConversationExchange
from app.models.evidence_store import EvidenceItem, EvidenceSource, EvidenceStore
from app.models.resume_analysis import ResumeAnalysisResult
from app.models.resume_structure import StructuredResume

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    """Turn a category name into a short, id-safe slug.

    E.g. 'Backend Systems' -> 'backend-systems'.
    """
    slug = _SLUG_NON_ALNUM.sub("-", text.lower()).strip("-")
    return slug or "category"


class EvidenceStoreBuilder:
    """Builds an `EvidenceStore` from a structured resume, its analysis, and a conversation.

    A plain class, not a `pydantic.BaseModel`, matching this codebase's
    prompt-builder convention (see `ResumeAnalysisPromptBuilder`): it
    holds no state and validates nothing of its own, so there's no
    external data being deserialized through it.
    """

    def build(
        self,
        structured_resume: StructuredResume,
        resume_text: str,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        conversation_history: list[ConversationExchange],
    ) -> EvidenceStore:
        """Assemble every evidence item and return the finished store.

        `resume_text` is kept alongside `structured_resume` only for the
        whole-document `resume-full-text` item and `EvidenceStore.resume_text`
        (needed by prompts that want the resume as continuous prose, e.g.
        for style/structure context) — every *citable* per-item fact comes
        from `structured_resume`, never re-derived from the raw string.

        `conversation_history` may be empty — the Career Conversation is
        optional context, not a hard requirement of the Tailoring Engine;
        a candidate whose resume analysis alone already provides enough
        evidence can still be tailored using only resume/analysis-derived
        items.
        """
        items: list[EvidenceItem] = [
            EvidenceItem(
                evidence_id="resume-full-text",
                source=EvidenceSource.RESUME,
                label="Original Resume (whole document)",
                content=resume_text,
            ),
            EvidenceItem(
                evidence_id="analysis-summary",
                source=EvidenceSource.RESUME_ANALYSIS,
                label="Resume Analysis Summary",
                content=resume_analysis.overall_assessment.summary,
            ),
        ]
        items.extend(self._resume_item_items(structured_resume))
        items.extend(self._strength_items(resume_analysis))
        items.extend(self._matching_project_items(resume_analysis))
        items.extend(self._skill_match_items(resume_analysis))
        items.extend(self._conversation_items(conversation_history))

        return EvidenceStore(resume_text=resume_text, job_description=job_description, items=items)

    @staticmethod
    def _resume_item_items(structured_resume: StructuredResume) -> list[EvidenceItem]:
        items = []
        for section in structured_resume.sections:
            heading_label = section.heading or "Header"
            for item in section.items:
                items.append(
                    EvidenceItem(
                        evidence_id=f"resume-{item.item_id}",
                        source=EvidenceSource.RESUME,
                        label=f"Resume: {heading_label}",
                        content=item.text,
                    )
                )
        return items

    @staticmethod
    def _strength_items(resume_analysis: ResumeAnalysisResult) -> list[EvidenceItem]:
        return [
            EvidenceItem(
                evidence_id=f"analysis-strength-{index}",
                source=EvidenceSource.RESUME_ANALYSIS,
                label=f"Analysis Strength #{index}",
                content=strength,
            )
            for index, strength in enumerate(resume_analysis.strengths, start=1)
        ]

    @staticmethod
    def _matching_project_items(resume_analysis: ResumeAnalysisResult) -> list[EvidenceItem]:
        return [
            EvidenceItem(
                evidence_id=f"analysis-matching-project-{index}",
                source=EvidenceSource.RESUME_ANALYSIS,
                label=f"Resume Project #{index}",
                content=f"{project.title} — relevant because: {project.reason}",
            )
            for index, project in enumerate(resume_analysis.matching_projects, start=1)
        ]

    @staticmethod
    def _skill_match_items(resume_analysis: ResumeAnalysisResult) -> list[EvidenceItem]:
        # Only categories with at least one matched skill become evidence --
        # a category with none is a gap, not a fact to cite (see this
        # module's docstring on why weaknesses/improvements are excluded
        # the same way).
        items = []
        for skill_match in resume_analysis.skill_matches:
            if not skill_match.matched_skills:
                continue
            items.append(
                EvidenceItem(
                    evidence_id=f"analysis-skill-match-{_slug(skill_match.category)}",
                    source=EvidenceSource.RESUME_ANALYSIS,
                    label=f"Matched Skills: {skill_match.category}",
                    content=(
                        f"Matched skills in {skill_match.category}: "
                        f"{', '.join(skill_match.matched_skills)}."
                    ),
                )
            )
        return items

    @staticmethod
    def _conversation_items(history: list[ConversationExchange]) -> list[EvidenceItem]:
        items = []
        for index, exchange in enumerate(history, start=1):
            content = f"Q: {exchange.question}\nA: {exchange.answer}"
            if exchange.assistant_response:
                content = f"{content}\n(Recruiter note: {exchange.assistant_response})"
            items.append(
                EvidenceItem(
                    evidence_id=f"conversation-turn-{index}",
                    source=EvidenceSource.CONVERSATION,
                    label=f"Conversation Turn {index}",
                    content=content,
                )
            )
        return items
