"""Unit tests for `validate_tailored_resume` (Tailoring Engine Stage 4).

Pure Python, no gateway involved. Directly covers the sprint's explicit
"unsupported evidence rejection" and "hallucination rejection" test
requirements as fast, deterministic unit tests -- plus the plan-authority
requirement added afterward: a bullet may only cite evidence the
`PlannedChange` that produced it was actually approved to use, not just
any real id anywhere in the `EvidenceStore`.
"""

from app.evidence.tailoring_validator import RewrittenChange, validate_tailored_resume
from app.models.evidence_store import EvidenceItem, EvidenceSource, EvidenceStore
from app.models.tailored_resume import TailoredBullet, TailoredSection
from app.models.tailoring_plan import PlannedChange, TailoringAction


def _store(*items: EvidenceItem) -> EvidenceStore:
    return EvidenceStore(resume_text="resume", job_description="jd", items=list(items))


def _evidence(evidence_id: str, content: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source=EvidenceSource.CONVERSATION,
        label=evidence_id,
        content=content,
    )


def _change(evidence_ids: list[str], section: str = "Experience") -> PlannedChange:
    return PlannedChange(
        section=section,
        action=TailoringAction.REWRITE,
        reason="Some reason.",
        evidence_ids=evidence_ids,
    )


def _rewritten(change: PlannedChange, *bullets: TailoredBullet) -> RewrittenChange:
    return RewrittenChange(
        change=change, section=TailoredSection(heading=change.section, bullets=list(bullets))
    )


def test_bullet_fully_supported_by_its_cited_evidence_is_accepted() -> None:
    store = _store(_evidence("conversation-turn-1", "I used Docker to containerize the service."))
    change = _change(["conversation-turn-1"])
    rewritten = _rewritten(
        change,
        TailoredBullet(
            text="Containerized the service using Docker.",
            supporting_evidence_ids=["conversation-turn-1"],
        ),
    )

    tailored_resume, report = validate_tailored_resume([rewritten], store)

    assert report.total_bullets == 1
    assert report.accepted_count == 1
    assert report.rejected_count == 0
    assert report.passed is True
    assert len(tailored_resume.sections) == 1
    assert tailored_resume.sections[0].bullets[0].text == "Containerized the service using Docker."


def test_bullet_with_no_cited_evidence_is_rejected() -> None:
    store = _store(_evidence("conversation-turn-1", "I used Docker to containerize the service."))
    change = _change(["conversation-turn-1"])
    rewritten = _rewritten(
        change,
        TailoredBullet(text="Containerized the service using Docker.", supporting_evidence_ids=[]),
    )

    tailored_resume, report = validate_tailored_resume([rewritten], store)

    assert report.rejected_count == 1
    assert report.accepted_count == 0
    assert report.passed is False
    assert "No supporting evidence cited." in report.rejected_bullets[0].reason
    assert tailored_resume.sections == []  # section with zero accepted bullets is dropped


def test_bullet_citing_an_id_not_approved_for_this_change_is_rejected() -> None:
    """A real evidence id, but one this specific change was never approved to use."""
    store = _store(_evidence("conversation-turn-1", "I used Docker to containerize the service."))
    change = _change(["conversation-turn-1"])
    rewritten = _rewritten(
        change,
        TailoredBullet(
            text="Containerized the service using Docker.",
            supporting_evidence_ids=["conversation-turn-99"],
        ),
    )

    tailored_resume, report = validate_tailored_resume([rewritten], store)

    assert report.rejected_count == 1
    assert "conversation-turn-99" in report.rejected_bullets[0].reason
    assert "did not approve" in report.rejected_bullets[0].reason
    assert tailored_resume.sections == []


def test_bullet_citing_real_evidence_from_a_different_change_is_rejected() -> None:
    """The exact gap this fixed: real, in-store evidence, but approved for a *different* change.

    Without the plan-authorization check, this would previously pass --
    "conversation-turn-2" is a real id and does contain "Kubernetes" -- but
    it was never approved for *this* change, only for some other one. The
    Planner is the single authority on what evidence a given change may
    use; the Rewrite Engine must not be able to borrow another change's
    approved evidence just because it's real.
    """
    store = _store(
        _evidence("conversation-turn-1", "I mentored two junior engineers."),
        _evidence("conversation-turn-2", "I used Kubernetes to orchestrate the platform."),
    )
    change = _change(["conversation-turn-1"])  # only turn-1 approved for this change
    rewritten = _rewritten(
        change,
        TailoredBullet(
            text="Mentored engineers while orchestrating with Kubernetes.",
            supporting_evidence_ids=["conversation-turn-2"],  # borrowed from elsewhere
        ),
    )

    tailored_resume, report = validate_tailored_resume([rewritten], store)

    assert report.rejected_count == 1
    assert "conversation-turn-2" in report.rejected_bullets[0].reason
    assert "did not approve" in report.rejected_bullets[0].reason
    assert tailored_resume.sections == []


def test_bullet_hallucinating_a_technology_not_in_cited_evidence_is_rejected() -> None:
    """The core anti-hallucination case: a technology never mentioned in the cited evidence."""
    store = _store(_evidence("conversation-turn-1", "I used Docker to containerize the service."))
    change = _change(["conversation-turn-1"])
    rewritten = _rewritten(
        change,
        TailoredBullet(
            # "Kubernetes" is never mentioned in the cited evidence.
            text="Orchestrated services using Kubernetes and Docker.",
            supporting_evidence_ids=["conversation-turn-1"],
        ),
    )

    tailored_resume, report = validate_tailored_resume([rewritten], store)

    assert report.rejected_count == 1
    assert "Kubernetes" in report.rejected_bullets[0].reason
    assert tailored_resume.sections == []


def test_bullet_hallucinating_a_metric_not_in_cited_evidence_is_rejected() -> None:
    store = _store(_evidence("conversation-turn-1", "I mentored two junior engineers."))
    change = _change(["conversation-turn-1"])
    rewritten = _rewritten(
        change,
        TailoredBullet(
            # "40%" is a fabricated metric never present in the evidence.
            text="Mentored junior engineers, improving team velocity by 40%.",
            supporting_evidence_ids=["conversation-turn-1"],
        ),
    )

    tailored_resume, report = validate_tailored_resume([rewritten], store)

    assert report.rejected_count == 1
    assert "40%" in report.rejected_bullets[0].reason


def test_bullet_must_be_supported_by_evidence_it_actually_cited_not_evidence_elsewhere() -> None:
    """A bullet can't borrow textual support from evidence its change approved but didn't cite."""
    store = _store(
        _evidence("conversation-turn-1", "I mentored two junior engineers."),
        _evidence("conversation-turn-2", "I used Kubernetes to orchestrate the platform."),
    )
    change = _change(
        ["conversation-turn-1", "conversation-turn-2"]
    )  # both approved for this change
    rewritten = _rewritten(
        change,
        TailoredBullet(
            text="Mentored engineers while orchestrating with Kubernetes.",
            # Only cites turn-1 (even though turn-2 was also approved for this
            # change) -- Kubernetes must still be unsupported.
            supporting_evidence_ids=["conversation-turn-1"],
        ),
    )

    _, report = validate_tailored_resume([rewritten], store)

    assert report.rejected_count == 1
    assert "Kubernetes" in report.rejected_bullets[0].reason


def test_mixed_accepted_and_rejected_bullets_in_the_same_section() -> None:
    store = _store(_evidence("conversation-turn-1", "I used Docker to containerize the service."))
    change = _change(["conversation-turn-1"])
    rewritten = _rewritten(
        change,
        TailoredBullet(
            text="Containerized the service using Docker.",
            supporting_evidence_ids=["conversation-turn-1"],
        ),
        TailoredBullet(
            text="Orchestrated services using Kubernetes.",
            supporting_evidence_ids=["conversation-turn-1"],
        ),
    )

    tailored_resume, report = validate_tailored_resume([rewritten], store)

    assert report.total_bullets == 2
    assert report.accepted_count == 1
    assert report.rejected_count == 1
    assert report.passed is False
    assert len(tailored_resume.sections) == 1
    assert len(tailored_resume.sections[0].bullets) == 1
    assert tailored_resume.sections[0].bullets[0].text == "Containerized the service using Docker."


def test_action_verbs_at_bullet_start_do_not_trigger_false_rejection() -> None:
    """Ordinary capitalized action verbs shouldn't be treated as unsupported claims."""
    store = _store(_evidence("conversation-turn-1", "I containerized the internal service."))
    change = _change(["conversation-turn-1"])
    rewritten = _rewritten(
        change,
        TailoredBullet(
            text="Led the containerization of the internal service.",
            supporting_evidence_ids=["conversation-turn-1"],
        ),
    )

    _, report = validate_tailored_resume([rewritten], store)

    assert report.rejected_count == 0


def test_two_changes_targeting_the_same_heading_merge_their_accepted_bullets() -> None:
    store = _store(
        _evidence("conversation-turn-1", "I used Docker to containerize the service."),
        _evidence("analysis-strength-1", "Strong ownership of internal tooling."),
    )
    change_a = _change(["conversation-turn-1"], section="Summary")
    change_b = _change(["analysis-strength-1"], section="Summary")
    rewritten_a = _rewritten(
        change_a,
        TailoredBullet(
            text="Containerized the service using Docker.",
            supporting_evidence_ids=["conversation-turn-1"],
        ),
    )
    rewritten_b = _rewritten(
        change_b,
        TailoredBullet(
            text="Demonstrated strong ownership of internal tooling.",
            supporting_evidence_ids=["analysis-strength-1"],
        ),
    )

    tailored_resume, report = validate_tailored_resume([rewritten_a, rewritten_b], store)

    assert report.accepted_count == 2
    assert len(tailored_resume.sections) == 1
    assert tailored_resume.sections[0].heading == "Summary"
    assert len(tailored_resume.sections[0].bullets) == 2


def test_empty_rewritten_changes_produces_empty_report() -> None:
    store = _store(_evidence("conversation-turn-1", "Something happened."))

    tailored_resume, report = validate_tailored_resume([], store)

    assert tailored_resume.sections == []
    assert report.total_bullets == 0
    assert report.passed is True
