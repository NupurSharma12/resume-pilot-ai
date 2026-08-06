"""Unit tests for `SuggestionApplier`."""

import pytest

from app.models.evidence_store import EvidenceItem, EvidenceSource, EvidenceStore
from app.models.resume_structure import ResumeItem, ResumeSection, StructuredResume
from app.models.tailoring_suggestions import (
    SuggestionOperation,
    SuggestionPlan,
    SuggestionValidationStatus,
    TailoringSuggestion,
)
from app.tailoring.applier import (
    SuggestionApplier,
    SuggestionConflictError,
    SuggestionRevalidationFailedError,
    UnknownSuggestionIdError,
)


def _structured_resume() -> StructuredResume:
    return StructuredResume(
        sections=[
            ResumeSection(
                section_id="section-0",
                heading="SKILLS",
                items=[
                    ResumeItem(item_id="section-0-item-0", text="Python"),
                    ResumeItem(item_id="section-0-item-1", text="Django"),
                ],
            )
        ]
    )


def _evidence_store() -> EvidenceStore:
    return EvidenceStore(
        resume_text="SKILLS\nPython\nDjango\n",
        job_description="Backend role.",
        items=[
            EvidenceItem(
                evidence_id="resume-section-0-item-0",
                source=EvidenceSource.RESUME,
                label="Resume: SKILLS",
                content="Python",
            ),
            EvidenceItem(
                evidence_id="resume-section-0-item-1",
                source=EvidenceSource.RESUME,
                label="Resume: SKILLS",
                content="Django",
            ),
        ],
    )


def _append_suggestion(suggestion_id: str = "s1") -> TailoringSuggestion:
    return TailoringSuggestion(
        suggestion_id=suggestion_id,
        target_section_id="section-0",
        target_item_id="section-0-item-0",
        operation=SuggestionOperation.APPEND,
        current_text="Python",
        suggested_text="Python, up to date",
        reason="Freshen the phrasing.",
        evidence_ids=["resume-section-0-item-0"],
        evidence_sources=["Resume: SKILLS"],
        confidence=90,
        selected_by_default=True,
        validation_status=SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME,
        validation_issues=[],
    )


def _remove_suggestion(suggestion_id: str = "s2") -> TailoringSuggestion:
    return TailoringSuggestion(
        suggestion_id=suggestion_id,
        target_section_id="section-0",
        target_item_id="section-0-item-1",
        operation=SuggestionOperation.REMOVE,
        current_text="Django",
        suggested_text="",
        reason="Not relevant to this job.",
        evidence_ids=["resume-section-0-item-1"],
        evidence_sources=["Resume: SKILLS"],
        confidence=80,
        selected_by_default=False,
        validation_status=SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME,
        validation_issues=[],
    )


def _insert_after_suggestion(suggestion_id: str = "s3") -> TailoringSuggestion:
    return TailoringSuggestion(
        suggestion_id=suggestion_id,
        target_section_id="section-0",
        target_item_id="section-0-item-0",
        operation=SuggestionOperation.INSERT_AFTER,
        current_text=None,
        suggested_text="TypeScript",
        reason="Add a closely related skill.",
        evidence_ids=["resume-section-0-item-0"],
        evidence_sources=["Resume: SKILLS"],
        confidence=70,
        selected_by_default=False,
        validation_status=SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME,
        validation_issues=[],
    )


def test_only_selected_suggestions_are_applied() -> None:
    plan = SuggestionPlan(
        plan_id="plan-1", suggestions=[_append_suggestion(), _remove_suggestion()]
    )
    applier = SuggestionApplier()

    result = applier.apply(
        _structured_resume(),
        plan,
        _evidence_store(),
        selected_suggestion_ids=["s1"],
        edited_texts={},
    )

    skills = result.final_resume.get_section("section-0")
    assert skills is not None
    texts = [item.text for item in skills.items]
    assert texts == ["Python, up to date", "Django"]
    assert result.applied_suggestion_ids == ["s1"]
    assert result.final_validation.is_valid is True


def test_remove_operation_drops_the_target_item() -> None:
    plan = SuggestionPlan(plan_id="plan-1", suggestions=[_remove_suggestion()])
    applier = SuggestionApplier()

    result = applier.apply(
        _structured_resume(),
        plan,
        _evidence_store(),
        selected_suggestion_ids=["s2"],
        edited_texts={},
    )

    skills = result.final_resume.get_section("section-0")
    assert skills is not None
    assert [item.text for item in skills.items] == ["Python"]


def test_insert_after_adds_a_new_item_without_removing_the_anchor() -> None:
    plan = SuggestionPlan(plan_id="plan-1", suggestions=[_insert_after_suggestion()])
    applier = SuggestionApplier()

    result = applier.apply(
        _structured_resume(),
        plan,
        _evidence_store(),
        selected_suggestion_ids=["s3"],
        edited_texts={},
    )

    skills = result.final_resume.get_section("section-0")
    assert skills is not None
    assert [item.text for item in skills.items] == ["Python", "TypeScript", "Django"]


def test_unknown_suggestion_id_is_rejected() -> None:
    plan = SuggestionPlan(plan_id="plan-1", suggestions=[_append_suggestion()])
    applier = SuggestionApplier()

    with pytest.raises(UnknownSuggestionIdError):
        applier.apply(
            _structured_resume(),
            plan,
            _evidence_store(),
            selected_suggestion_ids=["does-not-exist"],
            edited_texts={},
        )


def test_two_selected_suggestions_targeting_the_same_item_conflict() -> None:
    other_append = _append_suggestion(suggestion_id="s4")
    other_append = other_append.model_copy(update={"suggested_text": "Python, expert level"})
    plan = SuggestionPlan(plan_id="plan-1", suggestions=[_append_suggestion(), other_append])
    applier = SuggestionApplier()

    with pytest.raises(SuggestionConflictError):
        applier.apply(
            _structured_resume(),
            plan,
            _evidence_store(),
            selected_suggestion_ids=["s1", "s4"],
            edited_texts={},
        )


def test_insert_after_does_not_conflict_with_a_mutation_of_its_own_anchor() -> None:
    plan = SuggestionPlan(
        plan_id="plan-1", suggestions=[_append_suggestion(), _insert_after_suggestion()]
    )
    applier = SuggestionApplier()

    result = applier.apply(
        _structured_resume(),
        plan,
        _evidence_store(),
        selected_suggestion_ids=["s1", "s3"],
        edited_texts={},
    )

    skills = result.final_resume.get_section("section-0")
    assert skills is not None
    assert [item.text for item in skills.items] == ["Python, up to date", "TypeScript", "Django"]


def test_valid_edited_text_is_applied_after_revalidation() -> None:
    plan = SuggestionPlan(plan_id="plan-1", suggestions=[_append_suggestion()])
    applier = SuggestionApplier()

    result = applier.apply(
        _structured_resume(),
        plan,
        _evidence_store(),
        selected_suggestion_ids=["s1"],
        edited_texts={"s1": "Python, well documented"},
    )

    skills = result.final_resume.get_section("section-0")
    assert skills is not None
    assert skills.items[0].text == "Python, well documented"


def test_edited_text_introducing_an_unsupported_claim_is_rejected() -> None:
    plan = SuggestionPlan(plan_id="plan-1", suggestions=[_append_suggestion()])
    applier = SuggestionApplier()

    with pytest.raises(SuggestionRevalidationFailedError):
        applier.apply(
            _structured_resume(),
            plan,
            _evidence_store(),
            selected_suggestion_ids=["s1"],
            # "Kubernetes" is never in the cited evidence -- a hallucinated
            # addition the user typed in, not something the model proposed.
            edited_texts={"s1": "Python, Kubernetes"},
        )


def test_unaffected_items_remain_byte_identical() -> None:
    plan = SuggestionPlan(plan_id="plan-1", suggestions=[_append_suggestion()])
    applier = SuggestionApplier()

    result = applier.apply(
        _structured_resume(),
        plan,
        _evidence_store(),
        selected_suggestion_ids=["s1"],
        edited_texts={},
    )

    skills = result.final_resume.get_section("section-0")
    assert skills is not None
    assert skills.items[1].item_id == "section-0-item-1"
    assert skills.items[1].text == "Django"


def test_no_selected_suggestions_leaves_the_resume_unchanged() -> None:
    plan = SuggestionPlan(plan_id="plan-1", suggestions=[_append_suggestion()])
    applier = SuggestionApplier()

    result = applier.apply(
        _structured_resume(), plan, _evidence_store(), selected_suggestion_ids=[], edited_texts={}
    )

    skills = result.final_resume.get_section("section-0")
    assert skills is not None
    assert [item.text for item in skills.items] == ["Python", "Django"]
    assert result.applied_suggestion_ids == []
