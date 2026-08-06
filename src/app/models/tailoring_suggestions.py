"""Domain model: evidence-backed, per-item resume edit suggestions.

Replaces the earlier whole-section `PlannedChange`/`TailoredSection` pair
(the original Tailoring Engine pipeline — see
`docs/features/tailoring-engine.md`'s "superseded" note) with suggestions
scoped to one exact resume item at a time — see
`docs/features/interactive-tailored-resume.md` for why: a user reviewing
"rewrite the whole Experience section" has no way to accept half of it; a
user reviewing "append 'TypeScript' to this one skills line" does. The
two-call-per-change shape is otherwise unchanged: a `SuggestedEdit`
(Stage 2, planner) carries no rewritten text, only what should change,
why, and which evidence justifies it; only Stage 3 (the rewrite call, one
per suggestion, scoped to only that suggestion's evidence) produces
`suggested_text`, turning it into a full `TailoringSuggestion`.

## Operation semantics (every operation anchors to one existing item)

Every operation targets `target_item_id`, an id of an item that already
exists in the parsed resume — including insertions, which are anchored
relative to an existing neighbor rather than "somewhere in this section."
This keeps every suggestion's position in the resume unambiguous and
keeps `SuggestionApplier` deterministic (see that module). Adding an
entirely new *section* that doesn't already exist is out of scope for
this version — see this feature's docs on why.

- `append`: extends `target_item_id`'s existing text. `suggested_text` is
  the item's *full* resulting text (not just the appended fragment), and
  must contain the item's current text as a substring — enforced by
  `app.evidence.suggestion_validator`, not just requested by the prompt.
- `update` / `replace`: revises `target_item_id`'s text. `suggested_text`
  is the full resulting text; unlike `append`, it need not contain the
  original verbatim (a genuine revision may reword it). `replace` is
  reserved for changes `update` can't express — the Planner's `reason`
  must say why.
- `add_emphasis`: same mechanics as `update`, reserved for reordering or
  rewording *existing* claims to foreground them, never introducing a
  claim the item didn't already make.
- `remove`: removes `target_item_id` entirely. `suggested_text` is empty.
- `insert_before` / `insert_after`: adds a brand-new item immediately
  before/after `target_item_id` (the anchor). `current_text` is null on
  the resulting `TailoringSuggestion` — there is nothing "current" at a
  position that doesn't exist yet.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SuggestionOperation(StrEnum):
    """The exact, constrained kind of edit a suggestion proposes.

    Listed in the order the Planner's system prompt is instructed to
    prefer them: `APPEND`/`INSERT_BEFORE`/`INSERT_AFTER`/`UPDATE` add or
    lightly revise content without discarding anything; `REPLACE` is
    destructive and only used when a lighter operation can't satisfy the
    suggestion's own `reason` — the Planner must say so explicitly, not
    just default to it. `ADD_EMPHASIS` reorders/rewords existing content
    to foreground it without introducing any new claim. `REMOVE` deletes
    an item entirely and is used only when clearly justified (e.g.
    genuinely irrelevant to the target job).
    """

    APPEND = "append"
    INSERT_BEFORE = "insert_before"
    INSERT_AFTER = "insert_after"
    UPDATE = "update"
    REPLACE = "replace"
    REMOVE = "remove"
    ADD_EMPHASIS = "add_emphasis"


# Operations where `current_text`/`suggested_text` describe the *same*
# item's before/after state (a true replacement, per this module's
# docstring) — the frontend uses this to decide whether to show a
# "Current vs Suggested" comparison or a plain addition. `INSERT_BEFORE`/
# `INSERT_AFTER` are the only operations *not* in this set: they add a
# new item, so there is no "current" state to compare against.
REPLACEMENT_OPERATIONS = frozenset(
    {
        SuggestionOperation.APPEND,
        SuggestionOperation.UPDATE,
        SuggestionOperation.REPLACE,
        SuggestionOperation.ADD_EMPHASIS,
        SuggestionOperation.REMOVE,
    }
)


class SuggestionValidationStatus(StrEnum):
    """How a suggestion's `suggested_text` relates to available evidence.

    `SUPPORTED_BY_ORIGINAL_RESUME` is a fully valid, non-degraded status —
    a suggestion doesn't need Career Conversation evidence to be sound;
    the original resume is itself a valid evidence source (see
    `EvidenceSource.RESUME` in `app.models.evidence_store`).
    `STRUCTURALLY_INVALID` covers a suggestion whose operation/target/text
    combination is internally inconsistent (e.g. an `append` whose
    `suggested_text` doesn't actually contain the original text, or a
    target item that doesn't exist). `CONFLICT` is never set at
    generation time (Stage 2/3 have no way to know about other
    suggestions' selections yet) — it's only ever produced by
    `SuggestionApplier` at apply time, when two *selected* suggestions
    turn out to target the same item destructively.
    """

    SUPPORTED_BY_ORIGINAL_RESUME = "supported_by_original_resume"
    SUPPORTED_BY_CONVERSATION = "supported_by_conversation"
    SUPPORTED_BY_BOTH = "supported_by_both"
    UNSUPPORTED = "unsupported"
    STRUCTURALLY_INVALID = "structurally_invalid"
    CONFLICT = "conflict"


class SuggestedEdit(BaseModel):
    """Stage 2 (Planner) output: WHAT should change and WHY — no text yet.

    This is the exact type passed to `LLMGateway.generate_structured` as
    `response_model` for the planner call (see
    `SuggestionPlannerPromptBuilder`) — its fields and descriptions shape
    the JSON schema the model is asked to conform to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_section_id: str = Field(
        description="The id of the resume section this suggestion applies to."
    )
    target_item_id: str = Field(
        description="The id of the existing resume item this suggestion anchors to."
    )
    operation: SuggestionOperation = Field(description="The exact kind of edit proposed.")
    reason: str = Field(description="Why this change would improve fit for the job description.")
    evidence_ids: list[str] = Field(
        description="Evidence Store ids that justify this change. Must never be empty."
    )


class PlannedEdits(BaseModel):
    """The Planner's full structured-output payload: every proposed edit, still textless.

    `generate_structured` requires one top-level response model; a bare
    `list[SuggestedEdit]` isn't a model, so this thin wrapper is what's
    actually passed as `response_model` to the planner's
    `generate_structured` call (see `TailoringSuggestionWorkflow`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edits: list[SuggestedEdit] = Field(
        description="Every proposed edit, in priority order, before any text is written."
    )


class TailoringSuggestion(BaseModel):
    """One fully-formed, evidence-backed edit suggestion, ready for user review.

    `suggestion_id` is stable for the lifetime of the `SuggestionPlan` it
    belongs to (see `TailoringPlanStore`) — the frontend selects by this
    id, and the backend's apply step verifies every selected id against
    the same plan, so frontend selection and backend application can
    never drift apart (see `docs/features/interactive-tailored-resume.md`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    suggestion_id: str = Field(description="Stable identifier within this suggestion plan.")
    target_section_id: str = Field(description="The id of the resume section this targets.")
    target_item_id: str = Field(description="The id of the existing resume item this anchors to.")
    operation: SuggestionOperation = Field(description="The exact kind of edit proposed.")
    current_text: str | None = Field(
        description=(
            "The existing item's text, for a true replacement (see `REPLACEMENT_OPERATIONS`); "
            "null for insert_before/insert_after, which add a new item instead."
        )
    )
    suggested_text: str = Field(
        description="The proposed text (full resulting text, not a diff/fragment)."
    )
    reason: str = Field(description="Why this change would improve fit for the job description.")
    evidence_ids: list[str] = Field(description="Evidence Store ids this suggestion is based on.")
    evidence_sources: list[str] = Field(
        description="Human-readable labels for `evidence_ids` (e.g. 'Conversation Turn 2')."
    )
    confidence: int = Field(ge=0, le=100, description="The model's own confidence in this edit.")
    selected_by_default: bool = Field(
        description="Whether this suggestion should start pre-selected in the review UI."
    )
    validation_status: SuggestionValidationStatus = Field(
        description="How this suggestion's text relates to its cited evidence."
    )
    validation_issues: list[str] = Field(
        default_factory=list,
        description="Human-readable reasons behind `validation_status`, if not cleanly supported.",
    )


class SuggestionText(BaseModel):
    """The Rewrite Engine's structured-output payload for one suggestion.

    This is the exact type passed to `LLMGateway.generate_structured` as
    `response_model` for the per-suggestion rewrite call (see
    `SuggestionRewritePromptBuilder`) — one call per `SuggestedEdit`,
    scoped to only that edit's approved evidence, mirroring the
    superseded pipeline's per-change rewrite call exactly (see
    `docs/features/tailoring-engine.md`). `evidence_ids` here lets the
    model narrow which of the *offered* evidence it actually ended up
    using for this specific text — it may not need all of it — but it can
    never introduce an id that wasn't offered; `TailoringSuggestionWorkflow`
    enforces that the same way the superseded pipeline enforced
    plan-to-rewrite evidence scoping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    suggested_text: str = Field(description="The proposed text (full resulting text).")
    evidence_ids: list[str] = Field(
        description="Which of the offered evidence ids this text is actually based on."
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="The model's own confidence that this text is fully evidence-backed.",
    )


class SuggestionPlan(BaseModel):
    """The full set of suggestions produced by one generation run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str = Field(description="Stable identifier for this plan, used by the apply step.")
    suggestions: list[TailoringSuggestion] = Field(
        description="Every proposed suggestion, in the order they should be considered."
    )
