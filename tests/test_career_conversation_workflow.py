"""Unit tests for `CareerConversationWorkflow`.

Uses a small in-test fake `LLMGateway` (not `MockGateway`) that returns a
pre-programmed sequence of `ConversationTurnDecision`s — see
`get_career_conversation_workflow`'s docstring for why the generic
`MockGateway` can't exercise this workflow's happy path: its type-driven
placeholder can't satisfy the should_stop/question invariant this
workflow enforces.
"""

from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from app.gateways.llm.models import LLMRequest, LLMResponse
from app.models.career_conversation import ConversationTurnDecision, EstimatedImpact
from app.models.resume_analysis import (
    HiringRecommendation,
    OverallAssessment,
    ResumeAnalysisResult,
    SkillMatch,
)
from app.prompts.career_conversation_prompt_builder import CareerConversationPromptBuilder
from app.sessions.conversation_session import ConversationSession
from app.workflows.career_conversation_workflow import (
    MAX_CONVERSATION_TURNS,
    STOP_CONFIDENCE_THRESHOLD,
    CareerConversationWorkflow,
    ConversationTurnInconsistentError,
)


class FakeGateway:
    """Structurally satisfies `LLMGateway`, returning a pre-programmed decision sequence.

    Raises `AssertionError` if called more times than decisions were
    supplied — this is what lets `test_hard_stop_at_max_turns` assert the
    workflow never makes a 9th call once the turn cap is reached.
    """

    def __init__(self, decisions: list[ConversationTurnDecision]) -> None:
        self._decisions = list(decisions)
        self.call_count = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("Unused by CareerConversationWorkflow.")

    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]):
        assert self._decisions, "FakeGateway called more times than decisions were programmed."
        self.call_count += 1
        return self._decisions.pop(0)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError("Unused by CareerConversationWorkflow.")
        yield  # pragma: no cover - makes this an async generator


def _continue_decision(confidence: int = 40) -> ConversationTurnDecision:
    return ConversationTurnDecision(
        confidence=confidence,
        should_stop=False,
        topic="Frontend framework experience",
        evidence_goal="Determine whether internal tooling work used React.",
        estimated_impact=EstimatedImpact.HIGH,
        question="I noticed you've worked on internal tooling. What frontend tech did you use?",
    )


def _stop_decision(
    confidence: int = 95, reason: str = "No remaining high-impact gaps."
) -> ConversationTurnDecision:
    return ConversationTurnDecision(
        confidence=confidence,
        should_stop=True,
        stop_reason=reason,
    )


@pytest.fixture
def resume_analysis() -> ResumeAnalysisResult:
    return ResumeAnalysisResult(
        overall_assessment=OverallAssessment(
            overall_score=70,
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="Solid fit overall.",
        ),
        skill_matches=[
            SkillMatch(
                category="Frontend",
                score=50,
                matched_skills=["JavaScript"],
                missing_skills=["React"],
            ),
        ],
        matching_projects=[],
        strengths=["Strong backend experience."],
        weaknesses=["Frontend framework experience is unclear."],
        resume_improvements=[],
    )


def _new_session(resume_analysis: ResumeAnalysisResult) -> ConversationSession:
    return ConversationSession.new(
        resume="Built internal tooling for the platform team.",
        job_description="Looking for a frontend engineer with React experience.",
        resume_analysis=resume_analysis,
    )


async def test_start_conversation_sets_first_question(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    gateway = FakeGateway([_continue_decision(confidence=30)])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    await workflow.start_conversation(session)

    assert session.history == []
    assert session.current_question is not None
    assert session.current_question.topic == "Frontend framework experience"
    assert session.last_confidence == 30
    assert gateway.call_count == 1


async def test_submit_answer_records_history_and_advances(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    gateway = FakeGateway([_continue_decision(confidence=30), _continue_decision(confidence=50)])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)
    await workflow.start_conversation(session)

    await workflow.submit_answer(session, "I used React for the internal dashboard.")

    assert session.turn_count == 1
    assert session.history[0].answer == "I used React for the internal dashboard."
    assert session.current_question is not None
    assert session.status.value == "in_progress"


async def test_llm_should_stop_completes_session(resume_analysis: ResumeAnalysisResult) -> None:
    gateway = FakeGateway([_stop_decision(confidence=85, reason="Enough evidence recovered.")])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    await workflow.start_conversation(session)

    assert session.status.value == "complete"
    assert session.current_question is None
    assert session.stop_reason == "Enough evidence recovered."


async def test_high_confidence_forces_stop_even_if_llm_did_not_flag_it(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    """A structurally valid 'continue' decision is still overridden once confidence >= threshold."""
    gateway = FakeGateway([_continue_decision(confidence=STOP_CONFIDENCE_THRESHOLD)])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    await workflow.start_conversation(session)

    assert session.status.value == "complete"
    assert session.current_question is None
    assert str(STOP_CONFIDENCE_THRESHOLD) in (session.stop_reason or "")


async def test_should_stop_true_with_question_raises(resume_analysis: ResumeAnalysisResult) -> None:
    bad_decision = ConversationTurnDecision(
        confidence=80,
        should_stop=True,
        question="This should not be present.",
    )
    gateway = FakeGateway([bad_decision])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    with pytest.raises(ConversationTurnInconsistentError):
        await workflow.start_conversation(session)


async def test_should_stop_false_with_missing_fields_raises(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    bad_decision = ConversationTurnDecision(confidence=40, should_stop=False)
    gateway = FakeGateway([bad_decision])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    with pytest.raises(ConversationTurnInconsistentError):
        await workflow.start_conversation(session)


async def test_hard_stop_at_max_turns_without_extra_gateway_call(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    # One decision to open the conversation, plus one per turn up to the
    # cap. The gateway should never be asked for a turn beyond the cap.
    decisions = [_continue_decision(confidence=10) for _ in range(MAX_CONVERSATION_TURNS)]
    gateway = FakeGateway(decisions)
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    await workflow.start_conversation(session)
    for _ in range(MAX_CONVERSATION_TURNS - 1):
        assert session.status.value == "in_progress"
        await workflow.submit_answer(session, "Some answer.")

    # The MAX_CONVERSATION_TURNS-th answer should force-complete the
    # session without consuming another decision from the gateway.
    await workflow.submit_answer(session, "Final answer.")

    assert session.status.value == "complete"
    assert session.turn_count == MAX_CONVERSATION_TURNS
    assert "maximum" in (session.stop_reason or "").lower()
    assert gateway.call_count == MAX_CONVERSATION_TURNS
