"""Career Conversation workflow: orchestrates one recruiter-style evidence-recovery turn at a time.

`CareerConversationWorkflow` composes a prompt builder and an
`LLMGateway` — the same two collaborators `ResumeAnalysisWorkflow` uses —
into "build prompt, call the gateway for a structured turn decision,
validate it, apply it to the session." Unlike `ResumeAnalysisWorkflow`,
this workflow's output is not a single final result but incremental
mutation of a `ConversationSession` across many calls, since Evidence
Recovery is inherently a multi-turn conversation rather than a
one-shot analysis.

Logs each turn's start/completion at INFO and validation/gateway failures
at ERROR — see `_advance`'s docstring. Per the no-content-logging
requirement, this module never logs resume text, job description text,
question text, or answer text; only `session_id`, elapsed time, turn
count, status, and confidence are logged.
"""

import time

from pydantic import ValidationError

from app.core.logging import get_logger
from app.gateways.llm.gateway import LLMGateway
from app.models.career_conversation import ConversationQuestion, ConversationTurnDecision
from app.prompts.career_conversation_prompt_builder import CareerConversationPromptBuilder
from app.sessions.conversation_session import ConversationSession

logger = get_logger(__name__)

# Hard, Python-enforced ceiling on how many questions a single conversation
# can ask, independent of what the LLM itself decides — see this module's
# docstring on `_advance` for why the LLM's own judgment is never trusted
# alone to terminate the conversation.
MAX_CONVERSATION_TURNS = 8

# If the LLM reports confidence at or above this threshold, the
# conversation is force-stopped even if it set `should_stop=False` for
# this turn — an independent, Python-side stop trigger layered on top of
# the LLM's own `should_stop` signal, not a replacement for it.
STOP_CONFIDENCE_THRESHOLD = 90


class ConversationTurnInconsistentError(RuntimeError):
    """Raised when a `ConversationTurnDecision` violates the should_stop/question invariant.

    A `ValidationError` from `generate_structured` means the LLM's output
    didn't match `ConversationTurnDecision`'s *schema* (wrong types,
    missing required fields). This is a different failure: the output was
    perfectly valid Pydantic, but violates a *cross-field business rule*
    that no single field's own validation can express — `should_stop=True`
    with a non-null `question`, or `should_stop=False` with any of the
    next-turn fields missing. Modeling it as its own exception (rather
    than reusing `ValidationError` or a bare `ValueError`) makes this
    specific contract violation identifiable to callers and log readers,
    distinct from a schema mismatch.
    """


class CareerConversationWorkflow:
    """Orchestrates Career Conversation turns by composing a prompt builder and gateway.

    Both collaborators are supplied by the caller (constructor injection),
    exactly matching `ResumeAnalysisWorkflow`'s pattern: this class
    depends on `CareerConversationPromptBuilder` and the `LLMGateway`
    abstraction, but owns none of their implementation details.

    This workflow does not depend on `ConversationSessionStore` — it
    receives and mutates a `ConversationSession` object directly and
    leaves the caller (the endpoint) responsible for persisting it. That
    keeps this class focused purely on turn orchestration and the
    should-we-stop decision, with no knowledge of *how* or *whether*
    sessions are stored.
    """

    def __init__(
        self,
        prompt_builder: CareerConversationPromptBuilder,
        gateway: LLMGateway,
    ) -> None:
        """Store the two injected collaborators for use by `start_conversation`/`submit_answer`."""
        self._prompt_builder = prompt_builder
        self._gateway = gateway

    async def start_conversation(self, session: ConversationSession) -> ConversationSession:
        """Generate the first turn for a freshly created, empty session.

        `session` is expected to have no history and no open question yet
        (the caller constructs it via `ConversationSession.new` and this
        is the first thing called on it). Returns the same `session`
        object, mutated in place, for the caller to persist.
        """
        await self._advance(session)
        return session

    async def submit_answer(self, session: ConversationSession, answer: str) -> ConversationSession:
        """Record an answer to the session's open question, then generate the next turn.

        Checks the hard turn cap *before* making another LLM call: once
        `session.turn_count` (which `record_answer` just incremented by
        completing an exchange) reaches `MAX_CONVERSATION_TURNS`, the
        session is force-completed without spending another request on a
        turn that will never be asked — cheaper and faster than calling
        the gateway and discarding the result.
        """
        session.record_answer(answer)
        if session.turn_count >= MAX_CONVERSATION_TURNS:
            session.complete(
                reason=f"Reached the maximum of {MAX_CONVERSATION_TURNS} conversation turns."
            )
            return session
        await self._advance(session)
        return session

    async def _advance(self, session: ConversationSession) -> None:
        """Request one turn decision from the LLM and apply it to `session`.

        This is the one place stop conditions are decided, and none of
        them trust the LLM alone:

        1. `_validate_decision` enforces the should_stop/question
           invariant structurally — an LLM response that violates it is
           treated as a contract failure (`ConversationTurnInconsistentError`),
           not silently patched or guessed at.
        2. Even a *structurally valid* "continue" decision (should_stop is
           False, all next-turn fields populated) is overridden into a
           stop if `decision.confidence >= STOP_CONFIDENCE_THRESHOLD` —
           an independent, Python-side ceiling, since trusting a model's
           own `should_stop` flag as the *only* stop signal would let a
           model that never sets it terminate the conversation only via
           the hard turn cap in `submit_answer`, asking weaker and weaker
           questions in between.
        3. The hard turn cap itself (`MAX_CONVERSATION_TURNS`) is enforced
           in `submit_answer`, not here — see its docstring.

        No prompt text, resume/job-description content, question text, or
        answer text is ever logged — only `session_id`, elapsed time, and
        (on completion) turn count/status/confidence, per the feature's
        logging requirement.
        """
        logger.info("career_conversation_turn_started", session_id=session.session_id)
        start = time.perf_counter()

        request = self._prompt_builder.build(
            resume=session.resume,
            job_description=session.job_description,
            resume_analysis=session.resume_analysis,
            history=session.history,
        )
        try:
            decision = await self._gateway.generate_structured(request, ConversationTurnDecision)
        except ValidationError as exc:
            logger.error(
                "career_conversation_turn_validation_failed",
                session_id=session.session_id,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                error=str(exc),
            )
            raise

        self._validate_decision(decision)
        session.last_confidence = decision.confidence

        elapsed_ms = (time.perf_counter() - start) * 1000
        should_stop = decision.should_stop or decision.confidence >= STOP_CONFIDENCE_THRESHOLD
        if should_stop:
            reason = decision.stop_reason or (
                f"Reached the confidence threshold ({decision.confidence} >= "
                f"{STOP_CONFIDENCE_THRESHOLD})."
            )
            session.complete(reason=reason)
        else:
            # `_validate_decision` has already guaranteed these four fields
            # are non-null when `decision.should_stop` is False.
            assert decision.topic is not None
            assert decision.evidence_goal is not None
            assert decision.estimated_impact is not None
            assert decision.question is not None
            session.set_current_question(
                ConversationQuestion(
                    topic=decision.topic,
                    question=decision.question,
                    evidence_goal=decision.evidence_goal,
                    estimated_impact=decision.estimated_impact,
                )
            )

        logger.info(
            "career_conversation_turn_completed",
            session_id=session.session_id,
            elapsed_ms=elapsed_ms,
            turn_count=session.turn_count,
            status=session.status,
            confidence=decision.confidence,
        )

    @staticmethod
    def _validate_decision(decision: ConversationTurnDecision) -> None:
        """Enforce the should_stop/question invariant Gemini's output must satisfy.

        Checked explicitly here, in the workflow, rather than as a
        `model_validator` on `ConversationTurnDecision` itself — see that
        model's docstring for why this cross-field business rule belongs
        to this layer rather than the model layer.
        """
        if decision.should_stop:
            if decision.question is not None:
                raise ConversationTurnInconsistentError(
                    "should_stop is true but question is not null."
                )
        else:
            missing = [
                name
                for name, value in (
                    ("topic", decision.topic),
                    ("evidence_goal", decision.evidence_goal),
                    ("estimated_impact", decision.estimated_impact),
                    ("question", decision.question),
                )
                if value is None
            ]
            if missing:
                raise ConversationTurnInconsistentError(
                    f"should_stop is false but required field(s) are null: {', '.join(missing)}."
                )
