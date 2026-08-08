"""Unit tests for `TailoringSuggestionWorkflow`.

Uses the same in-test `FakeGateway` pattern as `test_tailoring_workflow.py`
(the superseded pipeline's tests): a pre-programmed response sequence, one
`PlannedEdits` for the Planner call (Stage 2), then one `SuggestionText`
per planned edit for the Rewrite Engine (Stage 3) — one `generate_structured`
call each, scoped to that edit's approved evidence only.
"""

from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.gateways.llm.models import LLMRequest, LLMResponse
from app.models.career_conversation import ConversationExchange
from app.models.resume_analysis import (
    HiringRecommendation,
    OverallAssessment,
    ResumeAnalysisResult,
    SkillMatch,
)
from app.models.tailoring_suggestions import (
    PlannedEdits,
    SuggestedEdit,
    SuggestionOperation,
    SuggestionText,
    SuggestionValidationStatus,
)
from app.prompts.suggestion_planner_prompt_builder import SuggestionPlannerPromptBuilder
from app.prompts.suggestion_rewrite_prompt_builder import SuggestionRewritePromptBuilder
from app.resume_structure.parser import ResumeStructureParser
from app.workflows.tailoring_suggestion_workflow import (
    SuggestionPlanInvalidError,
    TailoringSuggestionWorkflow,
)

_RESUME_TEXT = (
    "SUMMARY\n"
    "Backend engineer with strong Python skills.\n\n"
    "SKILLS\n"
    "- Python\n"
    "- Django\n\n"
    "EXPERIENCE\n"
    "- Built internal tools using Python and Django.\n"
)


class FakeGateway:
    """Structurally satisfies `LLMGateway`, returning a pre-programmed response sequence."""

    def __init__(self, responses: list[BaseModel]) -> None:
        self._responses = list(responses)
        self.call_count = 0
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("Unused by TailoringSuggestionWorkflow.")

    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]):
        assert self._responses, "FakeGateway called more times than responses were programmed."
        self.call_count += 1
        self.requests.append(request)
        return self._responses.pop(0)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError("Unused by TailoringSuggestionWorkflow.")
        yield  # pragma: no cover - makes this an async generator


@pytest.fixture
def resume_analysis() -> ResumeAnalysisResult:
    return ResumeAnalysisResult(
        overall_assessment=OverallAssessment(
            overall_score=70,
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="Solid fit overall.",
        ),
        skill_matches=[
            SkillMatch(category="Backend", score=80, matched_skills=["Python"], missing_skills=[]),
        ],
        matching_projects=[],
        strengths=["Strong backend ownership."],
        weaknesses=["Frontend experience is unclear."],
        resume_improvements=[],
    )


@pytest.fixture
def conversation_history() -> list[ConversationExchange]:
    return [
        ConversationExchange(
            topic="Frontend",
            question="Have you built any UI applications?",
            answer="I built the internal dashboard using React and TypeScript.",
            assistant_response=None,
        ),
    ]


def _workflow(gateway: FakeGateway) -> TailoringSuggestionWorkflow:
    return TailoringSuggestionWorkflow(
        structure_parser=ResumeStructureParser(),
        evidence_store_builder=EvidenceStoreBuilder(),
        planner_prompt_builder=SuggestionPlannerPromptBuilder(),
        rewrite_prompt_builder=SuggestionRewritePromptBuilder(),
        gateway=gateway,
    )


def _skills_item_id() -> str:
    structured = ResumeStructureParser().parse(_RESUME_TEXT)
    return next(
        item.item_id
        for section in structured.sections
        for item in section.items
        if item.text == "Python"
    )


async def test_full_pipeline_happy_path(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    item_id = _skills_item_id()
    evidence_id = f"resume-{item_id}"
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="TypeScript experience is missing from Skills.",
                # Two sources: the resume item covers "Python" (the
                # retained original text), the conversation turn covers
                # "TypeScript" (the addition) -- both are needed for the
                # full appended text to be fully evidence-backed.
                evidence_ids=[evidence_id, "conversation-turn-1"],
            )
        ]
    )
    text = SuggestionText(
        suggested_text="Python, TypeScript",
        evidence_ids=[evidence_id, "conversation-turn-1"],
        confidence=90,
    )
    gateway = FakeGateway([edits, text])
    workflow = _workflow(gateway)

    result = await workflow.generate_suggestions(
        resume=_RESUME_TEXT,
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
        custom_instructions=None,
    )

    assert gateway.call_count == 2
    assert len(result.plan.suggestions) == 1
    suggestion = result.plan.suggestions[0]
    assert suggestion.operation == SuggestionOperation.APPEND
    assert suggestion.target_item_id == item_id
    assert suggestion.current_text == "Python"
    assert suggestion.suggested_text == "Python, TypeScript"
    assert suggestion.validation_status == SuggestionValidationStatus.SUPPORTED_BY_BOTH
    assert suggestion.selected_by_default is True
    assert suggestion.suggestion_id == "suggestion-0"


async def test_rewrite_request_for_one_edit_only_embeds_that_edits_approved_evidence(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    """Structural proof that the Rewrite Engine cannot see evidence outside its one edit's scope."""
    item_id = _skills_item_id()
    evidence_id = f"resume-{item_id}"
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="TypeScript experience is missing from Skills.",
                evidence_ids=[evidence_id],
            )
        ]
    )
    text = SuggestionText(
        suggested_text="Python, TypeScript",
        evidence_ids=[evidence_id],
        confidence=90,
    )
    gateway = FakeGateway([edits, text])
    workflow = _workflow(gateway)

    await workflow.generate_suggestions(
        resume=_RESUME_TEXT,
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
        custom_instructions=None,
    )

    rewrite_request = gateway.requests[1]
    assert "Python" in rewrite_request.user_prompt
    # Real evidence that exists in the store, but never approved for this
    # one edit -- it must never leak into the scoped rewrite prompt.
    assert "React and TypeScript" not in rewrite_request.user_prompt
    assert "Strong backend ownership" not in rewrite_request.user_prompt


async def test_edit_targeting_unknown_item_raises(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id="section-99-item-99",
                operation=SuggestionOperation.APPEND,
                reason="Some reason.",
                evidence_ids=["resume-full-text"],
            )
        ]
    )
    gateway = FakeGateway([edits])
    workflow = _workflow(gateway)

    with pytest.raises(SuggestionPlanInvalidError, match="section-99-item-99"):
        await workflow.generate_suggestions(
            resume=_RESUME_TEXT,
            job_description="Looking for a full-stack engineer.",
            resume_analysis=resume_analysis,
            conversation_history=conversation_history,
            custom_instructions=None,
        )

    # The Rewrite Engine must never be called against an edit that failed
    # its own contract check.
    assert gateway.call_count == 1


async def test_edit_with_no_evidence_raises(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    item_id = _skills_item_id()
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="Some reason.",
                evidence_ids=[],
            )
        ]
    )
    gateway = FakeGateway([edits])
    workflow = _workflow(gateway)

    with pytest.raises(SuggestionPlanInvalidError):
        await workflow.generate_suggestions(
            resume=_RESUME_TEXT,
            job_description="Looking for a full-stack engineer.",
            resume_analysis=resume_analysis,
            conversation_history=conversation_history,
            custom_instructions=None,
        )
    assert gateway.call_count == 1


async def test_edit_citing_unknown_evidence_id_raises(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    item_id = _skills_item_id()
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="Some reason.",
                evidence_ids=["resume-nonexistent-item"],
            )
        ]
    )
    gateway = FakeGateway([edits])
    workflow = _workflow(gateway)

    with pytest.raises(SuggestionPlanInvalidError, match="resume-nonexistent-item"):
        await workflow.generate_suggestions(
            resume=_RESUME_TEXT,
            job_description="Looking for a full-stack engineer.",
            resume_analysis=resume_analysis,
            conversation_history=conversation_history,
            custom_instructions=None,
        )
    assert gateway.call_count == 1


async def test_rewrite_citing_evidence_outside_its_edits_approval_is_dropped_not_trusted(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    """Defense in depth: a hallucinated evidence id from the rewrite call must not be trusted.

    Simulates a `FakeGateway` "misbehaving" the way real prompt drift
    could -- the resulting suggestion should have that id filtered out,
    which (with no evidence left) makes it UNSUPPORTED rather than
    silently accepted.
    """
    item_id = _skills_item_id()
    approved_evidence_id = f"resume-{item_id}"
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="Some reason.",
                evidence_ids=[approved_evidence_id],
            )
        ]
    )
    text = SuggestionText(
        suggested_text="Python, TypeScript",
        # Real id in the store, but never approved for this edit.
        evidence_ids=["resume-full-text"],
        confidence=90,
    )
    gateway = FakeGateway([edits, text])
    workflow = _workflow(gateway)

    result = await workflow.generate_suggestions(
        resume=_RESUME_TEXT,
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
        custom_instructions=None,
    )

    suggestion = result.plan.suggestions[0]
    assert suggestion.evidence_ids == []
    assert suggestion.validation_status == SuggestionValidationStatus.UNSUPPORTED
    assert suggestion.selected_by_default is False


async def test_multiple_independent_appends_to_the_same_item_are_annotated_conflict_free(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    """The motivating scenario: several atomic "add this evidence" suggestions for one item."""
    item_id = _skills_item_id()
    evidence_id = f"resume-{item_id}"
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="Add TypeScript.",
                evidence_ids=[evidence_id, "conversation-turn-1"],
            ),
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="Add React.",
                evidence_ids=[evidence_id, "conversation-turn-1"],
            ),
        ]
    )
    gateway = FakeGateway(
        [
            edits,
            SuggestionText(
                suggested_text="Python, TypeScript",
                evidence_ids=[evidence_id, "conversation-turn-1"],
                confidence=90,
            ),
            SuggestionText(
                suggested_text="Python, React",
                evidence_ids=[evidence_id, "conversation-turn-1"],
                confidence=90,
            ),
        ]
    )
    workflow = _workflow(gateway)

    result = await workflow.generate_suggestions(
        resume=_RESUME_TEXT,
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
        custom_instructions=None,
    )

    suggestions = result.plan.suggestions
    assert len(suggestions) == 2
    assert suggestions[0].conflicts_with == []
    assert suggestions[1].conflicts_with == []
    # Neither suggestion needed to be downgraded -- independent appends
    # can both stay pre-selected.
    assert suggestions[0].selected_by_default is True
    assert suggestions[1].selected_by_default is True


async def test_two_rewrites_of_the_same_item_are_annotated_as_mutually_exclusive(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    item_id = _skills_item_id()
    evidence_id = f"resume-{item_id}"
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.UPDATE,
                reason="Reword for emphasis, option A.",
                evidence_ids=[evidence_id],
            ),
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.UPDATE,
                reason="Reword for emphasis, option B.",
                evidence_ids=[evidence_id],
            ),
        ]
    )
    gateway = FakeGateway(
        [
            edits,
            SuggestionText(
                suggested_text="Python (expert)", evidence_ids=[evidence_id], confidence=90
            ),
            SuggestionText(suggested_text="Pythonista", evidence_ids=[evidence_id], confidence=90),
        ]
    )
    workflow = _workflow(gateway)

    result = await workflow.generate_suggestions(
        resume=_RESUME_TEXT,
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
        custom_instructions=None,
    )

    first, second = result.plan.suggestions
    assert first.conflicts_with == [second.suggestion_id]
    assert second.conflicts_with == [first.suggestion_id]
    # Only the first-seen suggestion in a conflicting group stays
    # pre-selected, so the default selection is never self-contradictory.
    assert first.selected_by_default is True
    assert second.selected_by_default is False
