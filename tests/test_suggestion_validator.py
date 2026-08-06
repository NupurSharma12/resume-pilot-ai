"""Unit tests for `validate_suggestion` (per-suggestion evidence + structural validation)."""

from app.evidence.suggestion_validator import validate_suggestion
from app.models.evidence_store import EvidenceItem, EvidenceSource, EvidenceStore
from app.models.resume_structure import ResumeItem, ResumeSection, StructuredResume
from app.models.tailoring_suggestions import SuggestionOperation, SuggestionValidationStatus


def _resume(*items: tuple[str, str]) -> StructuredResume:
    """Build a one-section structured resume from (item_id, text) pairs."""
    return StructuredResume(
        sections=[
            ResumeSection(
                section_id="section-0",
                heading="EXPERIENCE",
                items=[ResumeItem(item_id=item_id, text=text) for item_id, text in items],
            )
        ]
    )


def _store(*items: EvidenceItem) -> EvidenceStore:
    return EvidenceStore(resume_text="resume", job_description="jd", items=list(items))


def _resume_evidence(evidence_id: str, content: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id, source=EvidenceSource.RESUME, label="x", content=content
    )


def _conversation_evidence(evidence_id: str, content: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id, source=EvidenceSource.CONVERSATION, label="x", content=content
    )


def test_update_supported_by_resume_only() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(_resume_evidence("resume-section-0-item-0", "Built internal tooling."))

    result = validate_suggestion(
        operation=SuggestionOperation.UPDATE,
        target_item_id="section-0-item-0",
        current_text="Built internal tooling.",
        suggested_text="Built and maintained internal tooling.",
        evidence_ids=["resume-section-0-item-0"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME
    assert result.issues == []


def test_update_supported_by_conversation_only() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(_conversation_evidence("conversation-turn-1", "I used Docker and Kubernetes."))

    result = validate_suggestion(
        operation=SuggestionOperation.UPDATE,
        target_item_id="section-0-item-0",
        current_text="Built internal tooling.",
        suggested_text="Built internal tooling deployed with Docker and Kubernetes.",
        evidence_ids=["conversation-turn-1"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.SUPPORTED_BY_CONVERSATION


def test_update_supported_by_both() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(
        _resume_evidence("resume-section-0-item-0", "Built internal tooling."),
        _conversation_evidence("conversation-turn-1", "I used Docker and Kubernetes."),
    )

    result = validate_suggestion(
        operation=SuggestionOperation.UPDATE,
        target_item_id="section-0-item-0",
        current_text="Built internal tooling.",
        suggested_text="Built internal tooling deployed with Docker and Kubernetes.",
        evidence_ids=["resume-section-0-item-0", "conversation-turn-1"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.SUPPORTED_BY_BOTH


def test_unsupported_when_no_evidence_cited() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(_resume_evidence("resume-section-0-item-0", "Built internal tooling."))

    result = validate_suggestion(
        operation=SuggestionOperation.UPDATE,
        target_item_id="section-0-item-0",
        current_text="Built internal tooling.",
        suggested_text="Built internal tooling.",
        evidence_ids=[],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.UNSUPPORTED
    assert "No supporting evidence" in result.issues[0]


def test_unsupported_when_evidence_id_unknown() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(_resume_evidence("resume-section-0-item-0", "Built internal tooling."))

    result = validate_suggestion(
        operation=SuggestionOperation.UPDATE,
        target_item_id="section-0-item-0",
        current_text="Built internal tooling.",
        suggested_text="Built internal tooling.",
        evidence_ids=["does-not-exist"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.UNSUPPORTED
    assert "does-not-exist" in result.issues[0]


def test_unsupported_when_suggested_text_hallucinates_a_technology() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(_resume_evidence("resume-section-0-item-0", "Built internal tooling."))

    result = validate_suggestion(
        operation=SuggestionOperation.UPDATE,
        target_item_id="section-0-item-0",
        current_text="Built internal tooling.",
        suggested_text="Built internal tooling using Kubernetes.",
        evidence_ids=["resume-section-0-item-0"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.UNSUPPORTED
    assert "Kubernetes" in result.issues[0]


def test_structurally_invalid_when_target_item_does_not_exist() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(_resume_evidence("resume-section-0-item-0", "Built internal tooling."))

    result = validate_suggestion(
        operation=SuggestionOperation.UPDATE,
        target_item_id="does-not-exist",
        current_text="Built internal tooling.",
        suggested_text="Built internal tooling.",
        evidence_ids=["resume-section-0-item-0"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.STRUCTURALLY_INVALID


def test_append_must_retain_the_original_text() -> None:
    resume = _resume(("section-0-item-0", "Python, Java"))
    store = _store(_resume_evidence("resume-section-0-item-0", "Python, Java"))

    result = validate_suggestion(
        operation=SuggestionOperation.APPEND,
        target_item_id="section-0-item-0",
        current_text="Python, Java",
        suggested_text="React, TypeScript",  # dropped the original text entirely
        evidence_ids=["resume-section-0-item-0"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.STRUCTURALLY_INVALID
    assert "append" in result.issues[0].lower()


def test_append_that_retains_original_text_passes() -> None:
    resume = _resume(("section-0-item-0", "Python, Java"))
    store = _store(
        _resume_evidence("resume-section-0-item-0", "Python, Java, React, and TypeScript work.")
    )

    result = validate_suggestion(
        operation=SuggestionOperation.APPEND,
        target_item_id="section-0-item-0",
        current_text="Python, Java",
        suggested_text="Python, Java, React, TypeScript",
        evidence_ids=["resume-section-0-item-0"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME


def test_replacement_operation_requires_current_text() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(_resume_evidence("resume-section-0-item-0", "Built internal tooling."))

    result = validate_suggestion(
        operation=SuggestionOperation.UPDATE,
        target_item_id="section-0-item-0",
        current_text=None,
        suggested_text="Built internal tooling.",
        evidence_ids=["resume-section-0-item-0"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.STRUCTURALLY_INVALID


def test_insert_operation_must_not_carry_current_text() -> None:
    resume = _resume(("section-0-item-0", "Built internal tooling."))
    store = _store(_resume_evidence("resume-section-0-item-0", "Built internal tooling."))

    result = validate_suggestion(
        operation=SuggestionOperation.INSERT_AFTER,
        target_item_id="section-0-item-0",
        current_text="This should not be here.",
        suggested_text="New bullet text.",
        evidence_ids=["resume-section-0-item-0"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.STRUCTURALLY_INVALID


def test_remove_operation_only_needs_valid_evidence_and_target() -> None:
    resume = _resume(("section-0-item-0", "Irrelevant certification."))
    store = _store(_resume_evidence("resume-section-0-item-0", "Irrelevant certification."))

    result = validate_suggestion(
        operation=SuggestionOperation.REMOVE,
        target_item_id="section-0-item-0",
        current_text="Irrelevant certification.",
        suggested_text="",
        evidence_ids=["resume-section-0-item-0"],
        evidence_store=store,
        structured_resume=resume,
    )

    assert result.status == SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME
