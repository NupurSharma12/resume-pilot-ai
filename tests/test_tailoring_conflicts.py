"""Unit tests for `app.tailoring.conflicts.compute_conflicts`."""

from app.models.tailoring_suggestions import (
    SuggestionOperation,
    SuggestionValidationStatus,
    TailoringSuggestion,
)
from app.tailoring.conflicts import compute_conflicts


def _suggestion(
    suggestion_id: str,
    target_item_id: str,
    operation: SuggestionOperation,
    current_text: str | None = "Original text.",
) -> TailoringSuggestion:
    return TailoringSuggestion(
        suggestion_id=suggestion_id,
        target_section_id="section-0",
        target_item_id=target_item_id,
        operation=operation,
        current_text=current_text,
        suggested_text="New text.",
        reason="Test reason.",
        evidence_ids=["resume-" + target_item_id],
        evidence_sources=["Resume: test"],
        confidence=90,
        selected_by_default=True,
        validation_status=SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME,
        validation_issues=[],
    )


def test_suggestions_targeting_different_items_never_conflict() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.UPDATE),
        _suggestion("s2", "item-1", SuggestionOperation.UPDATE),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": [], "s2": []}


def test_multiple_independent_appends_on_the_same_item_do_not_conflict() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.APPEND),
        _suggestion("s2", "item-0", SuggestionOperation.APPEND),
        _suggestion("s3", "item-0", SuggestionOperation.APPEND),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": [], "s2": [], "s3": []}


def test_two_rewrites_of_the_same_item_conflict() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.UPDATE),
        _suggestion("s2", "item-0", SuggestionOperation.REPLACE),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": ["s2"], "s2": ["s1"]}


def test_rewrite_and_append_on_the_same_item_conflict() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.UPDATE),
        _suggestion("s2", "item-0", SuggestionOperation.APPEND),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": ["s2"], "s2": ["s1"]}


def test_remove_conflicts_with_append_on_the_same_item() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.REMOVE),
        _suggestion("s2", "item-0", SuggestionOperation.APPEND),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": ["s2"], "s2": ["s1"]}


def test_rewrite_does_not_conflict_with_insert_on_the_same_anchor() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.UPDATE),
        _suggestion("s2", "item-0", SuggestionOperation.INSERT_AFTER, current_text=None),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": [], "s2": []}


def test_append_does_not_conflict_with_insert_on_the_same_anchor() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.APPEND),
        _suggestion("s2", "item-0", SuggestionOperation.INSERT_AFTER, current_text=None),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": [], "s2": []}


def test_two_insert_after_on_the_same_anchor_conflict() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.INSERT_AFTER, current_text=None),
        _suggestion("s2", "item-0", SuggestionOperation.INSERT_AFTER, current_text=None),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": ["s2"], "s2": ["s1"]}


def test_two_insert_before_on_the_same_anchor_conflict() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.INSERT_BEFORE, current_text=None),
        _suggestion("s2", "item-0", SuggestionOperation.INSERT_BEFORE, current_text=None),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": ["s2"], "s2": ["s1"]}


def test_insert_before_and_insert_after_on_the_same_anchor_do_not_conflict() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.INSERT_BEFORE, current_text=None),
        _suggestion("s2", "item-0", SuggestionOperation.INSERT_AFTER, current_text=None),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts == {"s1": [], "s2": []}


def test_the_four_atomic_evidence_example_all_independently_selectable() -> None:
    """The exact motivating scenario: four independent "add evidence" appends to one Summary."""
    suggestions = [
        _suggestion("s1", "summary-item-0", SuggestionOperation.APPEND),
        _suggestion("s2", "summary-item-0", SuggestionOperation.APPEND),
        _suggestion("s3", "summary-item-0", SuggestionOperation.APPEND),
        _suggestion("s4", "summary-item-0", SuggestionOperation.APPEND),
    ]

    conflicts = compute_conflicts(suggestions)

    assert all(others == [] for others in conflicts.values())


def test_a_suggestion_conflicting_with_multiple_others_lists_all_of_them() -> None:
    suggestions = [
        _suggestion("s1", "item-0", SuggestionOperation.UPDATE),
        _suggestion("s2", "item-0", SuggestionOperation.REPLACE),
        _suggestion("s3", "item-0", SuggestionOperation.ADD_EMPHASIS),
    ]

    conflicts = compute_conflicts(suggestions)

    assert conflicts["s1"] == ["s2", "s3"]
    assert conflicts["s2"] == ["s1", "s3"]
    assert conflicts["s3"] == ["s1", "s2"]
