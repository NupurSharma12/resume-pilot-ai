"""Domain model: the Tailoring Plan — the Tailoring Planner's blueprint for what should change.

A `TailoringPlan` is deliberately *not* rewritten resume text. Per Stage 2
of the Tailoring Engine pipeline, the planner's only job is deciding what
should change, why, and which evidence supports it — writing the actual
words is the Resume Rewrite Engine's job (Stage 3), grounded in this plan.
Keeping these as separate models (and separate LLM calls) mirrors the
`ResumeAnalysisResult` → Career Conversation split already in this
codebase: a structured decision object first, a downstream consumer that
acts on it second, rather than one call trying to reason and write at once.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TailoringAction(StrEnum):
    """The kind of change a `PlannedChange` proposes for one resume section."""

    REWRITE = "rewrite"
    EXPAND = "expand"
    REORDER = "reorder"
    TRIM = "trim"
    ADD_EMPHASIS = "add_emphasis"
    REMOVE = "remove"


class PlannedChange(BaseModel):
    """One proposed change to one resume section, and the evidence that justifies it.

    This is the exact type embedded (as a list) in `TailoringPlan`, which
    is passed to `LLMGateway.generate_structured` as `response_model` —
    its fields and descriptions are also what shapes the JSON schema the
    model is asked to conform to (see `TailoringPlannerPromptBuilder`).

    `evidence_ids` are references into an `EvidenceStore` (see
    `app.models.evidence_store`), not free text — this model does not
    itself verify those ids exist; that cross-object check belongs to
    `TailoringWorkflow`, the same way `CareerConversationWorkflow` (not
    `ConversationTurnDecision`) enforces the should_stop/question
    invariant. A plan with no supporting evidence at all
    (`evidence_ids == []`) is valid Pydantic but meaningless for this
    engine's purpose; the workflow rejects it for the same reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    section: str = Field(description="The resume section this change applies to, e.g. 'Summary'.")
    action: TailoringAction = Field(description="The kind of change proposed for this section.")
    reason: str = Field(description="Why this change would improve fit for the job description.")
    evidence_ids: list[str] = Field(
        description=(
            "Evidence Store ids that justify this change (e.g. ['conversation-turn-2', "
            "'analysis-matching-project-3']). Must never be empty — a change with no "
            "supporting evidence is not something this engine may propose."
        )
    )


class TailoringPlan(BaseModel):
    """The full set of proposed changes for one tailoring request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    changes: list[PlannedChange] = Field(
        description="Every proposed change, in the order they should be considered."
    )
