"""Interview Preparation workflow: the three-stage incremental-enrichment state machine.

`InterviewPreparationWorkflow` composes a prompt builder and an
`LLMGateway` across the product's three-stage Interview Preparation
lifecycle (see `app.models.interview_preparation`'s docstring for the
`InterviewPreparationStage` enum this mirrors):

    Stage 1 -- `generate()`: resume + job description alone, immediately
    after Resume Analysis. One LLM call (`GeneratedInterviewPreparation`),
    exactly mirroring `ResumeAnalysisWorkflow`'s shape. The one addition
    beyond a pure pass-through: assembling `behavioral_questions` by
    combining the Career Conversation's own exchanges (if any already
    exist at generation time) with the LLM's gap-fill questions, entirely
    in Python, with no second LLM call.

    Stage 2 -- `enrich_with_career_conversation()`: once the Career
    Conversation completes. Zero LLM calls -- purely a deterministic
    re-derivation of the `CAREER_CONVERSATION`-sourced behavioral
    questions from the now-available transcript, keeping whatever
    `SUGGESTED` gap-fill questions Stage 1 already produced.
    `system_design_questions`/`coding_questions` are carried over
    completely untouched -- the Career Conversation has nothing to say
    about system design or coding preparation.

    Stage 3 -- `enrich_with_tailoring()`: once a tailored resume has
    actually been applied. One LLM call, but scoped to system-design and
    coding questions only (`GeneratedTechnicalPreparation` has no
    behavioral field) -- `behavioral_questions` is carried over
    completely untouched, since tailoring the resume doesn't change what
    the candidate said in their Career Conversation.

Every stage only ever regenerates the portion of the guide that
genuinely depends on the new context that just became available -- see
each method's own docstring. None of the three ever throws away data a
prior stage produced that the new context has no bearing on.

Logs each step's start/completion at INFO, and logs (then re-raises)
structured-output validation failures at ERROR, matching
`ResumeAnalysisWorkflow.analyze`. Never logs resume/job-description/
conversation content or the resulting guide's content.
"""

from datetime import UTC, datetime

from pydantic import ValidationError

from app.core.logging import get_logger
from app.gateways.llm.gateway import LLMGateway
from app.models.career_conversation import ConversationExchange
from app.models.interview_preparation import (
    BehavioralQuestion,
    BehavioralQuestionSource,
    GeneratedInterviewPreparation,
    GeneratedTechnicalPreparation,
    InterviewPreparationResult,
    InterviewPreparationStage,
)
from app.prompts.interview_preparation_prompt_builder import InterviewPreparationPromptBuilder

logger = get_logger(__name__)


class InterviewPreparationWorkflow:
    """Orchestrates the three-stage Interview Preparation lifecycle.

    Both collaborators are supplied by the caller (constructor injection),
    matching `ResumeAnalysisWorkflow`'s own convention -- see its
    docstring for the full reasoning, which applies unchanged here.
    """

    def __init__(
        self,
        prompt_builder: InterviewPreparationPromptBuilder,
        gateway: LLMGateway,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._gateway = gateway

    async def generate(
        self,
        *,
        resume: str,
        job_description: str,
        job_title: str,
        company: str | None,
        career_conversation_exchanges: list[ConversationExchange],
    ) -> InterviewPreparationResult:
        """Stage 1: build a prompt, request structured output, and assemble the guide.

        `career_conversation_exchanges` is passed to the prompt so the LLM
        can identify genuine behavioral gaps (see the prompt builder's
        docstring), and is also used directly here, in Python, to build
        each `CAREER_CONVERSATION`-sourced `BehavioralQuestion` -- the
        LLM's own output only ever contributes `SUGGESTED` ones
        (`additional_behavioral_questions`). Works unchanged when
        `career_conversation_exchanges` is empty (no completed Career
        Conversation exists yet): the guide is still generated from resume
        + job description alone.

        Ordinarily called with an empty `career_conversation_exchanges`
        (this is Stage 1, generated immediately after Resume Analysis,
        before a Career Conversation can have completed) -- but a
        `JobPreparation` whose Interview Preparation is generated for the
        very first time *after* its Career Conversation (or even its
        tailoring) has already completed still lands here with whatever
        context already exists, since there is nothing yet to preserve
        from a prior stage. The caller (see the endpoint's docstring)
        computes the resulting `stage` from what was actually available,
        not just `INITIAL`.
        """
        logger.info("prompt_creation_started")
        request = self._prompt_builder.build(
            resume=resume,
            job_description=job_description,
            job_title=job_title,
            company=company,
            career_conversation_exchanges=career_conversation_exchanges,
        )
        logger.info("prompt_creation_completed")

        logger.info("llm_request_started", model=request.model)
        try:
            generated = await self._gateway.generate_structured(
                request, GeneratedInterviewPreparation
            )
        except ValidationError as exc:
            logger.error("structured_response_validation_failed", error=str(exc))
            raise
        logger.info("llm_request_completed")
        logger.info("structured_response_validated")

        behavioral_questions = [
            BehavioralQuestion(
                question=exchange.question,
                source=BehavioralQuestionSource.CAREER_CONVERSATION,
                context=exchange.answer,
            )
            for exchange in career_conversation_exchanges
        ] + [
            BehavioralQuestion(
                question=question,
                source=BehavioralQuestionSource.SUGGESTED,
                context=None,
            )
            for question in generated.additional_behavioral_questions
        ]

        return InterviewPreparationResult(
            system_design_questions=generated.system_design_questions,
            coding_questions=generated.coding_questions,
            behavioral_questions=behavioral_questions,
            generated_at=datetime.now(UTC),
        )

    def enrich_with_career_conversation(
        self,
        existing: InterviewPreparationResult,
        career_conversation_exchanges: list[ConversationExchange],
    ) -> InterviewPreparationResult:
        """Stage 2: deterministically fold the completed Career Conversation in. No LLM call.

        `existing.system_design_questions`/`existing.coding_questions` are
        carried over completely unchanged -- this stage has nothing new
        to say about them. Only `behavioral_questions` is recomputed:
        every exchange becomes a `CAREER_CONVERSATION`-sourced question
        (exactly as `generate()`'s own merge does), and every `SUGGESTED`
        question `existing` already carried over from Stage 1 is kept --
        Stage 1's gap-fill questions were the LLM's own judgment about
        what the Career Conversation transcript, once available, might
        still leave uncovered, and nothing about that judgment is
        invalidated by the transcript actually arriving. There is
        deliberately no LLM call here to ask for *new* gap-fill questions
        against the real transcript -- see this module's docstring.
        """
        preserved_suggested = [
            question
            for question in existing.behavioral_questions
            if question.source == BehavioralQuestionSource.SUGGESTED
        ]
        behavioral_questions = [
            BehavioralQuestion(
                question=exchange.question,
                source=BehavioralQuestionSource.CAREER_CONVERSATION,
                context=exchange.answer,
            )
            for exchange in career_conversation_exchanges
        ] + preserved_suggested

        return existing.model_copy(
            update={
                "behavioral_questions": behavioral_questions,
                "generated_at": datetime.now(UTC),
                "stage": InterviewPreparationStage.CAREER_CONVERSATION_ENRICHED,
            }
        )

    async def enrich_with_tailoring(
        self,
        existing: InterviewPreparationResult,
        *,
        resume: str,
        job_description: str,
        job_title: str,
        company: str | None,
        tailoring_summary: str,
    ) -> InterviewPreparationResult:
        """Stage 3: regenerate technical questions against the applied resume. One LLM call.

        `resume` is expected to be the *applied* (tailored) resume text,
        not the original -- the caller (see the endpoint) is responsible
        for that resolution, this method just grounds its one call in
        whatever resume text it's given. `existing.behavioral_questions`
        is carried over completely unchanged: the Career Conversation
        transcript has nothing to do with the resume being tailored, so
        there's nothing there for this stage to update.
        """
        logger.info("tailoring_enrichment_prompt_creation_started")
        request = self._prompt_builder.build_tailoring_enrichment(
            resume=resume,
            job_description=job_description,
            job_title=job_title,
            company=company,
            tailoring_summary=tailoring_summary,
        )
        logger.info("tailoring_enrichment_prompt_creation_completed")

        logger.info("tailoring_enrichment_llm_request_started", model=request.model)
        try:
            generated = await self._gateway.generate_structured(
                request, GeneratedTechnicalPreparation
            )
        except ValidationError as exc:
            logger.error(
                "tailoring_enrichment_structured_response_validation_failed", error=str(exc)
            )
            raise
        logger.info("tailoring_enrichment_llm_request_completed")

        return existing.model_copy(
            update={
                "system_design_questions": generated.system_design_questions,
                "coding_questions": generated.coding_questions,
                "generated_at": datetime.now(UTC),
                "stage": InterviewPreparationStage.TAILORING_ALIGNED,
            }
        )
