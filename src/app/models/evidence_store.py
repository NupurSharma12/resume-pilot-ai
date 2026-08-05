"""Domain model: the Evidence Store — the Tailoring Engine's single source of truth.

An `EvidenceStore` is a flat catalog of atomic, independently-citable facts
about one candidate, gathered from everything already established about
them: the original resume, the prior resume analysis, and the Career
Conversation transcript. It contains no rewriting, no scoring, and no
judgment of its own (see `app.evidence.evidence_store_builder`, which
builds one) — it exists purely so the Tailoring Planner and Resume Rewrite
Engine have something concrete to cite, and so Validation has something
concrete to check citations against. Every `EvidenceItem.evidence_id` is
stable for the lifetime of one tailoring request, so a planner decision or
a rewritten bullet can reference exactly which fact(s) it relies on.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceSource(StrEnum):
    """Which of the three inputs an `EvidenceItem` was extracted from."""

    RESUME = "resume"
    RESUME_ANALYSIS = "resume_analysis"
    CONVERSATION = "conversation"


class EvidenceItem(BaseModel):
    """One atomic, citable fact about the candidate.

    `content` is always a fact already established elsewhere (a resume
    excerpt, an analysis-confirmed strength, or a conversation answer) —
    never generated or summarized by an LLM. `label` is a short,
    human-readable name (e.g. "Conversation Turn 2", "Resume Project #3")
    for use in a Validation Report or any UI that shows why a change was
    made, distinct from `evidence_id`, which is the stable machine-facing
    key the Planner and Rewrite Engine actually cite.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(
        description="Stable identifier this item is cited by, e.g. 'conversation-turn-2'."
    )
    source: EvidenceSource = Field(description="Which input this fact was extracted from.")
    label: str = Field(description="Short, human-readable name, e.g. 'Conversation Turn 2'.")
    content: str = Field(description="The fact itself, verbatim or near-verbatim from its source.")


class EvidenceStore(BaseModel):
    """The full evidence catalog for one candidate, plus the raw context it was built from.

    `resume_text`/`job_description` are kept alongside `items` (not just
    folded into evidence items) because the Planner and Rewrite Engine
    both need the *whole* resume as continuous text to reason about
    structure, ordering, and existing wording — not only the discrete
    facts extracted from it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    resume_text: str = Field(description="The original resume text, verbatim.")
    job_description: str = Field(description="The job description text this tailoring is for.")
    items: list[EvidenceItem] = Field(description="The full catalog of atomic, citable evidence.")

    def get(self, evidence_id: str) -> EvidenceItem | None:
        """Look up one evidence item by id, or `None` if it doesn't exist in this store."""
        for item in self.items:
            if item.evidence_id == evidence_id:
                return item
        return None

    def unknown_ids(self, evidence_ids: list[str]) -> list[str]:
        """Return the subset of `evidence_ids` that don't exist in this store, in order."""
        known = {item.evidence_id for item in self.items}
        return [evidence_id for evidence_id in evidence_ids if evidence_id not in known]

    def text_for_ids(self, evidence_ids: list[str]) -> str:
        """Concatenate the `content` of every known item in `evidence_ids`, for grounding checks.

        Unknown ids are silently skipped here (callers that need to reject
        unknown ids should check `unknown_ids` explicitly first — see
        `app.evidence.tailoring_validator`); this method only answers "what
        do the ids that *do* exist actually say."
        """
        return "\n".join(item.content for item in self.items if item.evidence_id in evidence_ids)

    def catalog_text(self) -> str:
        """Render the full evidence catalog as plain text, for embedding in the Planner's prompt.

        The Planner is this pipeline's single authority on what evidence
        may be used at all, so it — and only it — is shown everything
        (see `TailoringPlannerPromptBuilder`). The Rewrite Engine must
        never see this; it gets `catalog_text_for_ids` instead, scoped to
        exactly what the Planner approved for one specific change (see
        `ResumeRewritePromptBuilder`).
        """
        return self._render(self.items)

    def catalog_text_for_ids(self, evidence_ids: list[str]) -> str:
        """Render only the given evidence ids as plain text, in `evidence_ids`' order.

        This is what scopes the Resume Rewrite Engine's evidence access
        to exactly one `PlannedChange`'s approved ids — the engine is
        never handed `catalog_text()`'s full catalog, so it structurally
        cannot cite a fact the Planner didn't authorize for this
        particular change, not merely instructed not to. Unknown ids are
        silently skipped (by this point they've already been rejected by
        `TailoringWorkflow._validate_plan_evidence`, so this method only
        needs to answer "render whichever of these ids are real").
        """
        items_by_id = {item.evidence_id: item for item in self.items}
        matched = [
            items_by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in items_by_id
        ]
        return self._render(matched)

    @staticmethod
    def _render(items: list[EvidenceItem]) -> str:
        """Render `items` as plain text, numbered implicitly by `evidence_id`.

        Implicit numbering (not a separate index) so the model cites the
        exact same identifier a human reader of this catalog sees — no
        translation step between "which evidence did you mean" and
        "which evidence_id do I cite."
        """
        if not items:
            return "No evidence items are available."
        lines = []
        for item in items:
            lines.append(f"[{item.evidence_id}] ({item.label}, source: {item.source.value})")
            lines.append(f"    {item.content}")
        return "\n".join(lines)
