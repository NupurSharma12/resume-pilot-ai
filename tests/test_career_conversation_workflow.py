"""Unit tests for `CareerConversationWorkflow`.

Uses a small in-test fake `LLMGateway` (not `MockGateway`) that returns a
pre-programmed sequence of `ConversationTurnDecision`s — see
`get_career_conversation_workflow`'s docstring for why the generic
`MockGateway` can't exercise this workflow's happy path: its type-driven
placeholder can't satisfy the should_stop/question invariant this
workflow enforces.
"""

import asyncio
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
    MAX_DECISION_ATTEMPTS,
    STOP_CONFIDENCE_THRESHOLD,
    CareerConversationWorkflow,
    ConversationTurnInconsistentError,
)


class FakeGateway:
    """Structurally satisfies `LLMGateway`, returning a pre-programmed decision sequence.

    Raises `AssertionError` if called more times than decisions were
    supplied — this is what lets `test_hard_stop_at_max_turns` assert the
    workflow never makes a 9th call once the turn cap is reached.

    `delay_seconds` (default `0`, no behavior change for existing tests)
    inserts a real `asyncio.sleep` before returning — a real Gemini call
    always has some latency, which is exactly what gives two concurrent
    requests room to interleave around it. Without any delay here, an
    in-process test that fires two "concurrent" requests via
    `asyncio.gather` never actually observes them interleave: with no
    `await` between the endpoint's pre-lock status check and this call
    returning, the first request's coroutine runs to completion before
    the event loop even starts the second one. A small delay is what
    makes `test_concurrent_answers_...` in `test_career_conversation_api.py`
    a faithful reproduction of the real race, not just an assertion about
    code that happens to look correct.
    """

    def __init__(
        self,
        decisions: list[ConversationTurnDecision | BaseException],
        delay_seconds: float = 0,
    ) -> None:
        self._decisions = list(decisions)
        self._delay_seconds = delay_seconds
        self.call_count = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("Unused by CareerConversationWorkflow.")

    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]):
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        assert self._decisions, "FakeGateway called more times than decisions were programmed."
        self.call_count += 1
        item = self._decisions.pop(0)
        # An `Exception` in the queue is raised instead of returned --
        # lets tests simulate a provider failure (e.g. standing in for
        # `GatewayChainExhaustedError`) at a specific turn without a
        # second fake class.
        if isinstance(item, BaseException):
            raise item
        return item

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError("Unused by CareerConversationWorkflow.")
        yield  # pragma: no cover - makes this an async generator


class _CountingPromptBuilder:
    """Wraps the real prompt builder, counting `.build` calls.

    Lets tests assert that `_request_decision` builds its prompt/request
    exactly once per call, even when it retries `generate_structured`
    across multiple attempts (see `MAX_DECISION_ATTEMPTS`) -- the same
    already-built request must be reused for every attempt, never
    rebuilt.
    """

    def __init__(self) -> None:
        self._inner = CareerConversationPromptBuilder()
        self.build_call_count = 0

    def build(self, **kwargs: object) -> LLMRequest:
        self.build_call_count += 1
        return self._inner.build(**kwargs)  # type: ignore[arg-type]


def _continue_decision(
    confidence: int = 40, assistant_response: str | None = None
) -> ConversationTurnDecision:
    return ConversationTurnDecision(
        confidence=confidence,
        should_stop=False,
        topic="Frontend framework experience",
        evidence_goal="Determine whether internal tooling work used React.",
        estimated_impact=EstimatedImpact.HIGH,
        question="I noticed you've worked on internal tooling. What frontend tech did you use?",
        assistant_response=assistant_response,
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


async def test_assistant_response_is_attached_to_the_next_question(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    gateway = FakeGateway(
        [
            _continue_decision(confidence=30),
            _continue_decision(
                confidence=50,
                assistant_response=(
                    "Direct P&L ownership means owning the budget and revenue targets "
                    "for a product line, not just the roadmap."
                ),
            ),
        ]
    )
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)
    await workflow.start_conversation(session)
    assert session.current_question is not None
    assert session.current_question.assistant_response is None

    await workflow.submit_answer(session, "What do you mean by direct P&L ownership?")

    assert session.current_question is not None
    assert session.current_question.assistant_response is not None
    assert "budget and revenue targets" in session.current_question.assistant_response


async def test_assistant_response_carries_into_history_once_answered(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    gateway = FakeGateway(
        [
            _continue_decision(confidence=30, assistant_response="An earlier clarification."),
            _stop_decision(confidence=95, reason="No gaps remain."),
        ]
    )
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)
    await workflow.start_conversation(session)

    await workflow.submit_answer(session, "Got it, thanks.")

    assert len(session.history) == 1
    assert session.history[0].assistant_response == "An earlier clarification."


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


async def test_should_stop_true_with_question_raises_after_exhausting_retries(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    """Both attempts return the same invariant-violating decision -- `MAX_DECISION_ATTEMPTS`
    retries a should_stop/question contract violation exactly like a single-attempt failure
    used to, just with `MAX_DECISION_ATTEMPTS` gateway calls instead of one.
    """
    bad_decision = ConversationTurnDecision(
        confidence=80,
        should_stop=True,
        question="This should not be present.",
    )
    gateway = FakeGateway([bad_decision] * MAX_DECISION_ATTEMPTS)
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    with pytest.raises(ConversationTurnInconsistentError):
        await workflow.start_conversation(session)

    assert gateway.call_count == MAX_DECISION_ATTEMPTS


async def test_should_stop_false_with_missing_fields_raises_after_exhausting_retries(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    bad_decision = ConversationTurnDecision(confidence=40, should_stop=False)
    gateway = FakeGateway([bad_decision] * MAX_DECISION_ATTEMPTS)
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    with pytest.raises(ConversationTurnInconsistentError):
        await workflow.start_conversation(session)

    # Exactly two gateway calls -- one per configured attempt, no more.
    assert gateway.call_count == MAX_DECISION_ATTEMPTS


async def test_first_attempt_inconsistent_second_attempt_succeeds(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    """A should_stop/question invariant violation on the first attempt is retried
    transparently -- the caller only ever sees the eventual successful decision.
    """
    bad_decision = ConversationTurnDecision(confidence=40, should_stop=False)
    good_decision = _continue_decision(confidence=30)
    gateway = FakeGateway([bad_decision, good_decision])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    await workflow.start_conversation(session)

    assert gateway.call_count == 2
    assert session.current_question is not None
    assert session.current_question.topic == good_decision.topic
    assert session.last_confidence == 30
    assert session.status.value == "in_progress"


async def test_prompt_is_built_only_once_across_retries(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    bad_decision = ConversationTurnDecision(confidence=40, should_stop=False)
    good_decision = _continue_decision(confidence=30)
    gateway = FakeGateway([bad_decision, good_decision])
    prompt_builder = _CountingPromptBuilder()
    workflow = CareerConversationWorkflow(prompt_builder, gateway)  # type: ignore[arg-type]
    session = _new_session(resume_analysis)

    await workflow.start_conversation(session)

    assert gateway.call_count == 2
    assert prompt_builder.build_call_count == 1


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


# --- Resilience: a failed turn must never corrupt the session ---------
#
# Regression coverage for the bug documented in
# `career_conversation_workflow.py`'s module docstring: recording the
# answer *before* the next turn's decision was known left a session with
# its answer already consumed and no replacement question if that second
# step failed. Every test below drives a real failure at that exact point
# and asserts the session is byte-for-byte unchanged from immediately
# before the failing call -- not just "didn't crash the process."


async def test_submit_answer_preserves_session_when_next_turn_decision_is_inconsistent(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    """Session stays unchanged when *both* retry attempts return an inconsistent decision --
    the in-workflow retry (`MAX_DECISION_ATTEMPTS`) is exhausted entirely before
    `_request_decision` raises, and nothing about that retrying touches `session`.
    """
    bad_decision = ConversationTurnDecision(
        confidence=40, should_stop=False
    )  # missing next-turn fields
    gateway = FakeGateway(
        [_continue_decision(confidence=30), *([bad_decision] * MAX_DECISION_ATTEMPTS)]
    )
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)
    await workflow.start_conversation(session)
    question_before = session.current_question
    history_before = list(session.history)

    with pytest.raises(ConversationTurnInconsistentError):
        await workflow.submit_answer(session, "I used React for the internal dashboard.")

    assert session.current_question == question_before
    assert session.history == history_before
    assert session.history == []
    assert session.status.value == "in_progress"
    assert session.turn_count == 0
    # One call for `start_conversation` plus one per exhausted retry attempt.
    assert gateway.call_count == 1 + MAX_DECISION_ATTEMPTS


async def test_submit_answer_preserves_session_when_gateway_fails(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    """Stands in for every provider in the chain failing (`GatewayChainExhaustedError`)."""
    gateway = FakeGateway([_continue_decision(confidence=30), RuntimeError("all providers failed")])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)
    await workflow.start_conversation(session)
    question_before = session.current_question

    with pytest.raises(RuntimeError, match="all providers failed"):
        await workflow.submit_answer(session, "I used React for the internal dashboard.")

    assert session.current_question == question_before
    assert session.history == []
    assert session.status.value == "in_progress"


async def test_start_conversation_leaves_fresh_session_untouched_on_failure(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    gateway = FakeGateway([RuntimeError("all providers failed")])
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)

    with pytest.raises(RuntimeError, match="all providers failed"):
        await workflow.start_conversation(session)

    assert session.current_question is None
    assert session.history == []
    assert session.status.value == "in_progress"


async def test_retry_after_a_failed_turn_succeeds_without_losing_or_duplicating_the_answer(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    """The end-to-end recovery story: a failed turn, then a successful retry, is exactly as if
    the failed attempt never happened -- one recorded answer, one new question, nothing lost.
    """
    gateway = FakeGateway(
        [
            _continue_decision(confidence=30),
            RuntimeError("all providers failed"),
            _continue_decision(confidence=50),
        ]
    )
    workflow = CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
    session = _new_session(resume_analysis)
    await workflow.start_conversation(session)

    with pytest.raises(RuntimeError):
        await workflow.submit_answer(session, "I used React for the internal dashboard.")

    # Retry with the same answer -- exactly what the frontend's existing
    # "Try Again" does, since it never clears the answer box on failure.
    await workflow.submit_answer(session, "I used React for the internal dashboard.")

    assert session.turn_count == 1
    assert session.history[0].answer == "I used React for the internal dashboard."
    assert session.current_question is not None
    assert session.status.value == "in_progress"
    assert gateway.call_count == 3
