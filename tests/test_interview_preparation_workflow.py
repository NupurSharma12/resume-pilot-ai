"""Unit tests for `InterviewPreparationWorkflow`.

Uses a small in-test fake `LLMGateway` (matching
`test_career_conversation_workflow.py`'s `FakeGateway` convention) rather
than `MockGateway`, since `GeneratedInterviewPreparation` needs
domain-shaped placeholder data (a `Difficulty` enum value, non-empty
question lists) that `MockGateway`'s generic type-driven placeholder
cannot reliably produce.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from app.gateways.llm.models import LLMRequest, LLMResponse
from app.models.career_conversation import ConversationExchange
from app.models.interview_preparation import (
    BehavioralQuestion,
    BehavioralQuestionSource,
    CodingQuestion,
    Difficulty,
    GeneratedInterviewPreparation,
    GeneratedTechnicalPreparation,
    InterviewPreparationResult,
    InterviewPreparationStage,
    SystemDesignQuestion,
)
from app.prompts.interview_preparation_prompt_builder import InterviewPreparationPromptBuilder
from app.workflows.interview_preparation_workflow import InterviewPreparationWorkflow


class FakeGateway:
    """Structurally satisfies `LLMGateway`, returning one pre-programmed generation result.

    See `test_career_conversation_workflow.py`'s own `FakeGateway` for the
    reason `MockGateway` isn't used instead.
    """

    def __init__(
        self, result: GeneratedInterviewPreparation | GeneratedTechnicalPreparation | BaseException
    ) -> None:
        self._result = result
        self.call_count = 0
        self.last_request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("Unused by InterviewPreparationWorkflow.")

    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]):
        self.call_count += 1
        self.last_request = request
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError("Unused by InterviewPreparationWorkflow.")
        yield  # pragma: no cover - makes this an async generator


def _generated(additional_behavioral: list[str] | None = None) -> GeneratedInterviewPreparation:
    return GeneratedInterviewPreparation(
        system_design_questions=[
            SystemDesignQuestion(
                question="Design a distributed document-analysis pipeline.",
                rationale="The resume shows large-scale backend systems experience.",
            )
        ],
        coding_questions=[
            CodingQuestion(
                title="Merge Intervals",
                topic="Sorting",
                difficulty=Difficulty.MEDIUM,
                relevance="The role involves scheduling logic.",
            )
        ],
        additional_behavioral_questions=additional_behavioral or [],
    )


async def test_generate_calls_the_gateway_exactly_once() -> None:
    gateway = FakeGateway(_generated())
    workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)

    await workflow.generate(
        resume="SUMMARY\nBackend engineer.",
        job_description="Senior Backend Engineer.",
        job_title="Senior Backend Engineer",
        company="Acme Corp",
        career_conversation_exchanges=[],
    )

    assert gateway.call_count == 1


async def test_generate_returns_the_llms_system_design_and_coding_questions_unchanged() -> None:
    generated = _generated()
    gateway = FakeGateway(generated)
    workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)

    result = await workflow.generate(
        resume="SUMMARY\nBackend engineer.",
        job_description="Senior Backend Engineer.",
        job_title="Senior Backend Engineer",
        company=None,
        career_conversation_exchanges=[],
    )

    assert result.system_design_questions == generated.system_design_questions
    assert result.coding_questions == generated.coding_questions


async def test_behavioral_questions_combine_career_conversation_and_llm_gap_fill() -> None:
    gateway = FakeGateway(
        _generated(additional_behavioral=["Tell me about a time you led a migration."])
    )
    workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
    exchanges = [
        ConversationExchange(
            topic="Leadership",
            question="Describe a time you led a team through a difficult migration.",
            answer="I led a 4-engineer migration off a legacy monolith.",
            assistant_response=None,
        )
    ]

    result = await workflow.generate(
        resume="SUMMARY\nBackend engineer.",
        job_description="Senior Backend Engineer.",
        job_title="Senior Backend Engineer",
        company=None,
        career_conversation_exchanges=exchanges,
    )

    assert len(result.behavioral_questions) == 2
    from_conversation = result.behavioral_questions[0]
    assert from_conversation.source == BehavioralQuestionSource.CAREER_CONVERSATION
    assert from_conversation.question == exchanges[0].question
    assert from_conversation.context == exchanges[0].answer
    suggested = result.behavioral_questions[1]
    assert suggested.source == BehavioralQuestionSource.SUGGESTED
    assert suggested.question == "Tell me about a time you led a migration."
    assert suggested.context is None


async def test_generate_works_when_no_career_conversation_exists_yet() -> None:
    gateway = FakeGateway(
        _generated(additional_behavioral=["Tell me about a challenging project."])
    )
    workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)

    result = await workflow.generate(
        resume="SUMMARY\nBackend engineer.",
        job_description="Senior Backend Engineer.",
        job_title="Senior Backend Engineer",
        company=None,
        career_conversation_exchanges=[],
    )

    assert gateway.call_count == 1
    assert len(result.behavioral_questions) == 1
    assert result.behavioral_questions[0].source == BehavioralQuestionSource.SUGGESTED


async def test_generate_reraises_validation_errors_from_the_gateway() -> None:
    from pydantic import ValidationError

    try:
        GeneratedInterviewPreparation(
            system_design_questions=[],
            coding_questions=[],
            additional_behavioral_questions="not-a-list",
        )
        raise AssertionError(
            "expected GeneratedInterviewPreparation construction to fail validation"
        )
    except ValidationError as exc:
        validation_error = exc
    gateway = FakeGateway(validation_error)
    workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)

    with pytest.raises(ValidationError):
        await workflow.generate(
            resume="Resume",
            job_description="JD",
            job_title="Role",
            company=None,
            career_conversation_exchanges=[],
        )


def _existing_result(
    *,
    stage: InterviewPreparationStage = InterviewPreparationStage.INITIAL,
    behavioral_questions: list[BehavioralQuestion] | None = None,
) -> InterviewPreparationResult:
    return InterviewPreparationResult(
        system_design_questions=[
            SystemDesignQuestion(
                question="Design a distributed document-analysis pipeline.",
                rationale="The resume shows large-scale backend systems experience.",
            )
        ],
        coding_questions=[
            CodingQuestion(
                title="Merge Intervals",
                topic="Sorting",
                difficulty=Difficulty.MEDIUM,
                relevance="The role involves scheduling logic.",
            )
        ],
        behavioral_questions=behavioral_questions
        if behavioral_questions is not None
        else [
            BehavioralQuestion(
                question="Tell me about a challenging project.",
                source=BehavioralQuestionSource.SUGGESTED,
                context=None,
            )
        ],
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        stage=stage,
    )


class TestEnrichWithCareerConversation:
    """Stage 2: deterministic, zero-LLM-call enrichment."""

    def test_does_not_call_the_gateway(self) -> None:
        gateway = FakeGateway(_generated())
        workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
        existing = _existing_result()

        workflow.enrich_with_career_conversation(
            existing,
            [
                ConversationExchange(
                    topic="Leadership",
                    question="Describe a time you led a migration.",
                    answer="I led a 4-engineer migration off a legacy monolith.",
                    assistant_response=None,
                )
            ],
        )

        assert gateway.call_count == 0

    def test_preserves_system_design_and_coding_questions_unchanged(self) -> None:
        gateway = FakeGateway(_generated())
        workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
        existing = _existing_result()

        result = workflow.enrich_with_career_conversation(existing, [])

        assert result.system_design_questions == existing.system_design_questions
        assert result.coding_questions == existing.coding_questions

    def test_replaces_behavioral_questions_with_conversation_exchanges_plus_preserved_suggested(
        self,
    ) -> None:
        gateway = FakeGateway(_generated())
        workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
        existing = _existing_result(
            behavioral_questions=[
                BehavioralQuestion(
                    question="Tell me about a challenging project.",
                    source=BehavioralQuestionSource.SUGGESTED,
                    context=None,
                )
            ]
        )
        exchanges = [
            ConversationExchange(
                topic="Leadership",
                question="Describe a time you led a migration.",
                answer="I led a 4-engineer migration off a legacy monolith.",
                assistant_response=None,
            )
        ]

        result = workflow.enrich_with_career_conversation(existing, exchanges)

        assert len(result.behavioral_questions) == 2
        from_conversation = result.behavioral_questions[0]
        assert from_conversation.source == BehavioralQuestionSource.CAREER_CONVERSATION
        assert from_conversation.question == exchanges[0].question
        assert from_conversation.context == exchanges[0].answer
        preserved = result.behavioral_questions[1]
        assert preserved.source == BehavioralQuestionSource.SUGGESTED
        assert preserved.question == "Tell me about a challenging project."

    def test_sets_stage_to_career_conversation_enriched(self) -> None:
        gateway = FakeGateway(_generated())
        workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)

        result = workflow.enrich_with_career_conversation(_existing_result(), [])

        assert result.stage == InterviewPreparationStage.CAREER_CONVERSATION_ENRICHED


class TestEnrichWithTailoring:
    """Stage 3: one LLM call, technical questions only."""

    def _technical(self) -> GeneratedTechnicalPreparation:
        return GeneratedTechnicalPreparation(
            system_design_questions=[
                SystemDesignQuestion(
                    question="Design a scalable resume-tailoring pipeline.",
                    rationale="The tailored resume now emphasizes the tailoring engine.",
                )
            ],
            coding_questions=[
                CodingQuestion(
                    title="Diff Two Strings",
                    topic="Strings",
                    difficulty=Difficulty.MEDIUM,
                    relevance="The tailored resume emphasizes diff-based editing.",
                )
            ],
        )

    async def test_calls_the_gateway_exactly_once(self) -> None:
        gateway = FakeGateway(self._technical())
        workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
        existing = _existing_result(stage=InterviewPreparationStage.CAREER_CONVERSATION_ENRICHED)

        await workflow.enrich_with_tailoring(
            existing,
            resume="SUMMARY\nTailored backend engineer.",
            job_description="Senior Backend Engineer.",
            job_title="Senior Backend Engineer",
            company=None,
            tailoring_summary="- Emphasized the tailoring engine work.",
        )

        assert gateway.call_count == 1

    async def test_replaces_system_design_and_coding_questions(self) -> None:
        technical = self._technical()
        gateway = FakeGateway(technical)
        workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
        existing = _existing_result(stage=InterviewPreparationStage.CAREER_CONVERSATION_ENRICHED)

        result = await workflow.enrich_with_tailoring(
            existing,
            resume="SUMMARY\nTailored backend engineer.",
            job_description="Senior Backend Engineer.",
            job_title="Senior Backend Engineer",
            company=None,
            tailoring_summary="",
        )

        assert result.system_design_questions == technical.system_design_questions
        assert result.coding_questions == technical.coding_questions

    async def test_preserves_behavioral_questions_unchanged(self) -> None:
        gateway = FakeGateway(self._technical())
        workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
        existing = _existing_result(
            stage=InterviewPreparationStage.CAREER_CONVERSATION_ENRICHED,
            behavioral_questions=[
                BehavioralQuestion(
                    question="Describe a time you led a migration.",
                    source=BehavioralQuestionSource.CAREER_CONVERSATION,
                    context="I led a 4-engineer migration off a legacy monolith.",
                )
            ],
        )

        result = await workflow.enrich_with_tailoring(
            existing,
            resume="SUMMARY\nTailored backend engineer.",
            job_description="Senior Backend Engineer.",
            job_title="Senior Backend Engineer",
            company=None,
            tailoring_summary="",
        )

        assert result.behavioral_questions == existing.behavioral_questions

    async def test_sets_stage_to_tailoring_aligned(self) -> None:
        gateway = FakeGateway(self._technical())
        workflow = InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
        existing = _existing_result(stage=InterviewPreparationStage.INITIAL)

        result = await workflow.enrich_with_tailoring(
            existing,
            resume="SUMMARY\nTailored backend engineer.",
            job_description="Senior Backend Engineer.",
            job_title="Senior Backend Engineer",
            company=None,
            tailoring_summary="",
        )

        assert result.stage == InterviewPreparationStage.TAILORING_ALIGNED
