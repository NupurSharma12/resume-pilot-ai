"""Unit tests for `EvidenceStoreBuilder` (Tailoring Engine Stage 1).

Pure Python, no gateway involved — these assert on exactly which
`EvidenceItem`s get extracted from a resume analysis and a conversation
transcript, and that nothing rewrites or invents anything along the way.
"""

from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.models.career_conversation import ConversationExchange
from app.models.evidence_store import EvidenceSource
from app.models.resume_analysis import (
    HiringRecommendation,
    MatchingProject,
    OverallAssessment,
    ResumeAnalysisResult,
    ResumeImprovement,
    SkillMatch,
)
from app.models.resume_structure import StructuredResume
from app.resume_structure.parser import ResumeStructureParser

_RESUME_TEXT = "Built internal tooling for the platform team using Python and React."
_JOB_DESCRIPTION = "Looking for a full-stack engineer with React and Python experience."


def _structured_resume() -> StructuredResume:
    return ResumeStructureParser().parse(_RESUME_TEXT)


def _build(analysis: ResumeAnalysisResult, history: list[ConversationExchange]):
    return EvidenceStoreBuilder().build(
        _structured_resume(), _RESUME_TEXT, _JOB_DESCRIPTION, analysis, history
    )


def _analysis() -> ResumeAnalysisResult:
    return ResumeAnalysisResult(
        overall_assessment=OverallAssessment(
            overall_score=72,
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="A solid full-stack candidate with room to grow on cloud infrastructure.",
        ),
        skill_matches=[
            SkillMatch(
                category="Frontend",
                score=80,
                matched_skills=["React", "TypeScript"],
                missing_skills=["Next.js"],
            ),
            SkillMatch(
                category="Cloud",
                score=20,
                matched_skills=[],
                missing_skills=["AWS", "Kubernetes"],
            ),
        ],
        matching_projects=[
            MatchingProject(
                title="Internal Tooling Dashboard",
                relevance_score=85,
                reason="Directly demonstrates full-stack ownership relevant to this role.",
            ),
        ],
        strengths=["Strong ownership of internal tooling end to end."],
        weaknesses=["No demonstrated cloud infrastructure experience."],
        resume_improvements=[
            ResumeImprovement(
                section="Skills",
                recommendation="Call out React and Python explicitly in a skills section.",
                priority=1,
            ),
        ],
    )


def _history() -> list[ConversationExchange]:
    return [
        ConversationExchange(
            topic="Deployment",
            question="How was the dashboard deployed?",
            answer="We used Docker containers deployed to a small on-prem cluster.",
            assistant_response=None,
        ),
        ConversationExchange(
            topic="Code review",
            question="Did you participate in code reviews?",
            answer="Yes, I reviewed most backend PRs and mentored two junior engineers.",
            assistant_response="Got it, thanks for clarifying.",
        ),
    ]


def test_includes_full_resume_text_as_one_item() -> None:
    store = _build(_analysis(), [])

    item = store.get("resume-full-text")
    assert item is not None
    assert item.source == EvidenceSource.RESUME
    assert item.content == _RESUME_TEXT


def test_includes_analysis_summary() -> None:
    store = _build(_analysis(), [])

    item = store.get("analysis-summary")
    assert item is not None
    assert item.source == EvidenceSource.RESUME_ANALYSIS
    assert "full-stack candidate" in item.content


def test_includes_one_item_per_strength() -> None:
    store = _build(_analysis(), [])

    item = store.get("analysis-strength-1")
    assert item is not None
    assert item.content == "Strong ownership of internal tooling end to end."
    assert item.label == "Analysis Strength #1"


def test_includes_one_item_per_matching_project_numbered_from_one() -> None:
    store = _build(_analysis(), [])

    item = store.get("analysis-matching-project-1")
    assert item is not None
    assert item.label == "Resume Project #1"
    assert "Internal Tooling Dashboard" in item.content
    assert "Directly demonstrates full-stack ownership" in item.content


def test_skill_match_with_matched_skills_becomes_evidence() -> None:
    store = _build(_analysis(), [])

    item = store.get("analysis-skill-match-frontend")
    assert item is not None
    assert "React" in item.content
    assert "TypeScript" in item.content


def test_skill_match_with_no_matched_skills_is_not_evidence() -> None:
    """A category with zero matched skills is a gap, not a fact to cite."""
    store = _build(_analysis(), [])

    assert store.get("analysis-skill-match-cloud") is None


def test_weaknesses_and_improvements_are_never_evidence() -> None:
    """Gaps aren't facts about the candidate -- they must never be citable as evidence."""
    store = _build(_analysis(), [])

    for item in store.items:
        assert "No demonstrated cloud infrastructure experience" not in item.content
        assert "Call out React and Python explicitly" not in item.content


def test_conversation_turns_become_numbered_evidence_items() -> None:
    store = _build(_analysis(), _history())

    turn_1 = store.get("conversation-turn-1")
    turn_2 = store.get("conversation-turn-2")
    assert turn_1 is not None
    assert turn_1.label == "Conversation Turn 1"
    assert turn_1.source == EvidenceSource.CONVERSATION
    assert "Docker" in turn_1.content
    assert turn_2 is not None
    assert "mentored two junior engineers" in turn_2.content
    assert "Got it, thanks for clarifying." in turn_2.content  # assistant_response included


def test_empty_conversation_history_produces_no_conversation_items() -> None:
    store = _build(_analysis(), [])

    assert all(item.source != EvidenceSource.CONVERSATION for item in store.items)


def test_evidence_ids_are_unique() -> None:
    store = _build(_analysis(), _history())

    ids = [item.evidence_id for item in store.items]
    assert len(ids) == len(set(ids))


def test_catalog_text_includes_every_item_id() -> None:
    store = _build(_analysis(), _history())

    catalog = store.catalog_text()
    for item in store.items:
        assert f"[{item.evidence_id}]" in catalog
