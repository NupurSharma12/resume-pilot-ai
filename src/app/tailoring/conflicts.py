"""Shared conflict detection for tailoring suggestions.

One function, used two ways: `TailoringSuggestionWorkflow` calls it once,
over a whole freshly-generated plan, to annotate each suggestion's own
`conflicts_with` field (so the review UI can show mutual exclusivity
*before* the user tries to select two conflicting suggestions) --
`SuggestionApplier`/`DocxDocumentEditor` call it again, over just the
selected subset, to actually enforce it at apply time. Using the same
function both times is what guarantees the frontend's proactive warning
and the backend's hard enforcement can never disagree about what
conflicts with what.
"""

from app.models.tailoring_suggestions import (
    REWRITE_OPERATIONS,
    SuggestionOperation,
    TailoringSuggestion,
)


def compute_conflicts(suggestions: list[TailoringSuggestion]) -> dict[str, list[str]]:
    """Return, for every suggestion's id, the ids of suggestions it conflicts with.

    Two suggestions conflict exactly when they would both determine the
    same "span" of the resume -- this domain model has no sub-item
    character-offset concept, so "span" is approximated at the operation
    level, per target item:

    - Two `REWRITE_OPERATIONS` (update/replace/add_emphasis/remove) on
      the same item are genuine alternatives -- at most one may be
      selected, since each fully determines (or removes) the item's text.
    - A rewrite and an `append` on the same item conflict too: the
      append's added text is computed against the item's *original*
      text, which the rewrite invalidates or discards.
    - Two `append` suggestions on the same item do **not** conflict --
      each is computed independently against the original text and
      composes by concatenation (see `SuggestionApplier`/
      `DocxDocumentEditor`'s append handling). This is what lets one
      paragraph be broken into several independently-selectable
      "add this evidence" suggestions instead of one all-or-nothing
      rewrite -- see `docs/features/interactive-tailored-resume.md`.
    - Two `insert_before` (or two `insert_after`) suggestions anchored to
      the same item conflict -- there's no defined order between two
      "a new item goes here" claims for the same position.
    - A rewrite or an append never conflicts with an `insert_before`/
      `insert_after` on the same anchor -- insertion is purely
      positional/structural, independent of whatever the anchor's own
      text ends up being.

    Every conflicting pair shares the same `target_item_id` by
    construction -- nothing here ever compares suggestions targeting
    different items.
    """
    conflicts: dict[str, set[str]] = {s.suggestion_id: set() for s in suggestions}

    by_item: dict[str, list[TailoringSuggestion]] = {}
    for suggestion in suggestions:
        by_item.setdefault(suggestion.target_item_id, []).append(suggestion)

    for item_suggestions in by_item.values():
        for i, first in enumerate(item_suggestions):
            for second in item_suggestions[i + 1 :]:
                if _pair_conflicts(first, second):
                    conflicts[first.suggestion_id].add(second.suggestion_id)
                    conflicts[second.suggestion_id].add(first.suggestion_id)

    return {suggestion_id: sorted(others) for suggestion_id, others in conflicts.items()}


def _pair_conflicts(first: TailoringSuggestion, second: TailoringSuggestion) -> bool:
    first_is_rewrite = first.operation in REWRITE_OPERATIONS
    second_is_rewrite = second.operation in REWRITE_OPERATIONS

    if first_is_rewrite and second_is_rewrite:
        return True  # two alternative rewrites of the same item

    if first_is_rewrite or second_is_rewrite:
        # A rewrite conflicts with an append on the same item (the
        # append's basis text becomes invalid), but not with an
        # insertion (structurally independent of the anchor's text).
        other = second if first_is_rewrite else first
        return other.operation == SuggestionOperation.APPEND

    both_appends = (
        first.operation == SuggestionOperation.APPEND
        and second.operation == SuggestionOperation.APPEND
    )
    if both_appends:
        return False  # independent appends compose

    # Two inserts at the same position and side have no defined order.
    return first.operation == second.operation and first.operation in (
        SuggestionOperation.INSERT_BEFORE,
        SuggestionOperation.INSERT_AFTER,
    )
